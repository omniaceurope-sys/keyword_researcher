"""
scraper.py — Extracts search keywords from ecommerce pages using Claude Sonnet.
"""
import json
import logging
import time

import anthropic
import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config.settings import ANTHROPIC_API_KEY, CLAUDE_MODEL, KEYWORDS_PER_PAGE

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

KEYWORD_EXTRACTION_PROMPT = """\
You are a keyword research expert. Given the content of an ecommerce page, generate approximately {n} search keywords that potential customers would type into Google when looking for these products.

Rules:
- Generate functional search queries, NOT product names or brand names
- Focus on how real people search: problems they want to solve, features they want, comparisons they make
- Include a mix of:
  - Symptom/problem keywords (e.g. "how to fix back pain")
  - Product category keywords (e.g. "ergonomic office chair")
  - Feature-specific keywords (e.g. "noise cancelling headphones under 200")
  - Comparison keywords (e.g. "best wireless earbuds 2026")
  - Long-tail keywords (e.g. "comfortable headphones for long flights")
- Write keywords in the same language as the page content
- Do NOT include brand names from the page
- Return one keyword per line, nothing else

Page URL: {url}
Page content:
{content}"""


@retry(
    retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _fetch_html(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
    resp.raise_for_status()
    return resp.text


def _extract_content(html: str, url: str) -> str:
    """Extract meaningful text from HTML, stripping nav/footer/scripts."""
    soup = BeautifulSoup(html, "lxml")

    # Priority 1: JSON-LD structured data — extract BEFORE stripping scripts
    json_ld_texts = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                items = data
            else:
                items = [data]
            for item in items:
                _type = item.get("@type", "")
                if _type in ("Product", "ItemList", "CollectionPage", "BreadcrumbList"):
                    for field in ("name", "description", "alternateName"):
                        val = item.get(field)
                        if isinstance(val, str):
                            json_ld_texts.append(val)
                    items_list = item.get("itemListElement", [])
                    for el in items_list:
                        if isinstance(el, dict):
                            for field in ("name", "description"):
                                val = el.get(field, "")
                                if isinstance(val, str):
                                    json_ld_texts.append(val)
        except (json.JSONDecodeError, AttributeError):
            pass

    if json_ld_texts:
        return "\n".join(json_ld_texts)[:8000]

    # Remove noise elements
    for tag in soup(["script", "style", "noscript", "iframe",
                     "nav", "footer", "header", "aside",
                     "[class*='sidebar']", "[id*='sidebar']",
                     "[class*='cookie']", "[class*='popup']",
                     "[class*='newsletter']", "[class*='banner']"]):
        tag.decompose()

    # Also remove by common class/id patterns
    for selector in [
        ".sidebar", "#sidebar", ".widget", ".nav", ".navbar",
        ".footer", "#footer", ".header", "#header",
        ".breadcrumb", ".breadcrumbs",
        ".pagination", ".pager",
        ".social", ".share",
        ".cookie", ".popup", ".modal",
    ]:
        for el in soup.select(selector):
            el.decompose()

    # Priority 2: Platform-specific selectors
    platform_selectors = [
        # WooCommerce
        ".woocommerce-loop-product__title",
        ".products .product",
        ".product-title",
        ".woocommerce-product-details__short-description",
        # Shopify
        ".collection-grid",
        ".product-card",
        ".grid__item",
        ".card__heading",
        # Generic ecommerce
        ".product-list",
        ".product-grid",
        ".product-item",
        ".product-name",
        ".product-title",
        "[class*='product']",
        "[class*='collection']",
        "[class*='category']",
        "h1", "h2", "h3",
    ]

    parts = []
    for sel in platform_selectors:
        for el in soup.select(sel)[:20]:
            text = el.get_text(separator=" ", strip=True)
            if text:
                parts.append(text)
    if parts:
        combined = "\n".join(parts)
        if len(combined) > 500:
            return combined[:8000]

    # Priority 3: <main> fallback
    main = soup.find("main")
    if main:
        return main.get_text(separator="\n", strip=True)[:8000]

    return soup.get_text(separator="\n", strip=True)[:8000]


def _call_claude(url: str, content: str, client: anthropic.Anthropic) -> list[str]:
    """Call Claude Sonnet to generate keywords. Returns list of keyword strings."""
    prompt = KEYWORD_EXTRACTION_PROMPT.format(
        n=KEYWORDS_PER_PAGE,
        url=url,
        content=content,
    )
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    keywords = [line.strip() for line in raw.splitlines() if line.strip()]
    return keywords


def scrape_keywords(url: str) -> list[str]:
    """
    Fetch the page at url, extract content, call Claude to generate keywords.
    Returns a list of keyword strings (~KEYWORDS_PER_PAGE items).
    On failure returns an empty list and logs a warning.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Fetch HTML
    try:
        html = _fetch_html(url)
    except Exception as exc:
        logger.warning(f"Failed to fetch {url}: {exc}")
        return []

    # Extract content
    content = _extract_content(html, url)
    if not content.strip():
        logger.warning(f"No content extracted from {url}, skipping.")
        return []

    # Call Claude (retry once on API errors)
    for attempt in range(2):
        try:
            keywords = _call_claude(url, content, client)
            if keywords:
                logger.info(f"Extracted {len(keywords)} keywords from {url}")
                return keywords
            else:
                logger.warning(f"Claude returned no keywords for {url}")
                return []
        except anthropic.APIError as exc:
            if attempt == 0:
                logger.warning(f"Claude API error for {url} (attempt 1): {exc}. Retrying...")
                time.sleep(2)
            else:
                logger.warning(f"Claude API error for {url} (attempt 2): {exc}. Skipping.")
                return []

    return []
