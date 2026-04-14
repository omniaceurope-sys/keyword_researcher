"""Extract candidate keywords from a product landing page using AI."""

import json
import sys

import anthropic
import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config.settings import SCRAPER_TIMEOUT, ANTHROPIC_API_KEY, CLAUDE_MODEL, TOP_KEYWORDS_PER_URL

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# Platform-specific CSS selectors for the main product content area.
# Tried in order; first match with non-empty text wins.
_PRODUCT_CONTENT_SELECTORS = [
    ("div", "summary"),                                         # WooCommerce
    ("div", "woocommerce-product-details__short-description"),  # WooCommerce short desc
    ("div", "product__description"),                            # Shopify
    ("div", "product-single__description"),                     # Shopify (legacy)
    ("div", "product-description"),                             # Magento / generic
    ("div", "pdp-description"),                                 # Various
    ("div", "product-detail__description"),                     # Various
    ("section", "product-description"),                         # Various
    ("div", "product__info-container"),                         # Shopify Dawn theme
    ("div", "product-info__description"),                       # Various
]

_NOISE_TAGS = ["script", "style", "nav", "footer", "header", "aside"]

_claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_SYSTEM_PROMPT = """\
You are a Google Ads keyword research specialist.

Your job is to generate search keywords that real customers type into Google \
when looking for the products shown on a page.

Rules:
- Generate keywords in the SAME LANGUAGE as the product page.
- USE THE URL to understand the page's main topic. Only generate keywords \
  relevant to that topic — ignore unrelated products that may appear in \
  navigation, footers, or related product sections.
- IMPORTANT: Product pages often use creative, branded, or poetic product names. \
  Do NOT use these as keywords. Instead, identify what the product IS or DOES \
  and generate the functional search queries customers actually use.
  Example: "ProGlow X3 Serum" → "face serum", "anti-aging serum" — NOT "proglow x3"
  Example: "Mountain Breeze Bundle" → "hiking gear", "outdoor equipment" — NOT "mountain breeze bundle"
- KEYWORD LENGTH — this is the most important rule:
  * At least HALF of your keywords must be 1-2 words (generic, high-volume terms).
    Start with the single-word category itself, then add simple modifiers.
    Examples: "t-shirts", "men t-shirts", "fitted t-shirt", "gym t-shirt"
  * The rest may be 3 words maximum.
  * NEVER generate keywords longer than 3 words.
- Cover the full search funnel: single generic category word first, then \
  2-word terms with one modifier, then 3-word terms with fit/material/use-case.
- Do NOT include brand names, model names, prices, or promotional language.
- Respond ONLY with a valid JSON array of strings. No markdown, no explanation.
- Example output: ["men t-shirts", "fitted t-shirt", "crew neck tee", \
  "slim fit t-shirt", "gym t-shirt men", "cotton t-shirt men"]
"""


def _parse_jsonld_product(soup: BeautifulSoup) -> dict | None:
    """Parse schema.org Product JSON-LD and return a dict with all available fields."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            raw = script.string or ""
            data = json.loads(raw)
            candidates = data if isinstance(data, list) else [data]
            expanded = []
            for item in candidates:
                if isinstance(item, dict):
                    expanded.append(item)
                    expanded.extend(item.get("@graph", []))

            for item in expanded:
                if not isinstance(item, dict):
                    continue
                type_ = item.get("@type", "")
                if type_ == "Product" or (isinstance(type_, list) and "Product" in type_):
                    brand = item.get("brand", {})
                    brand_name = (
                        brand.get("name") if isinstance(brand, dict)
                        else str(brand) if brand else None
                    )
                    return {
                        "name": item.get("name"),
                        "brand": brand_name,
                        "description": item.get("description"),
                        "category": item.get("category"),
                    }
        except (json.JSONDecodeError, AttributeError, TypeError):
            continue
    return None


def _extract_from_jsonld(soup: BeautifulSoup) -> str | None:
    """Extract product text content from schema.org JSON-LD."""
    product = _parse_jsonld_product(soup)
    if not product:
        return None
    parts = [v for k, v in product.items() if v and k != "brand"]
    return " ".join(parts) if parts else None


def _extract_brand_from_soup(soup: BeautifulSoup) -> str:
    """Try to extract the site/brand name from meta tags and common HTML patterns."""
    # og:site_name (most reliable non-schema source)
    og = soup.find("meta", property="og:site_name")
    if og and og.get("content", "").strip():
        return og["content"].strip()

    # Twitter site name
    tw = soup.find("meta", attrs={"name": "twitter:site"})
    if tw and tw.get("content", "").strip():
        val = tw["content"].strip().lstrip("@")
        if val:
            return val

    # application-name
    app = soup.find("meta", attrs={"name": "application-name"})
    if app and app.get("content", "").strip():
        return app["content"].strip()

    return ""


def get_product_info(url: str) -> dict:
    """Return {name, brand} for a product page.

    Extraction priority:
    1. schema.org JSON-LD Product (name + brand)
    2. og:site_name / twitter:site / application-name meta tags (brand only)
    3. Page <title> stripped of common suffixes (name only)
    """
    try:
        html = _fetch(url)
    except Exception:
        return {"name": "", "brand": ""}

    soup = BeautifulSoup(html, "lxml")
    product = _parse_jsonld_product(soup)

    if product:
        brand = product.get("brand") or _extract_brand_from_soup(soup)
        return {
            "name": product.get("name") or "",
            "brand": brand,
        }

    # No JSON-LD product — try meta tags for brand, page title for name
    brand = _extract_brand_from_soup(soup)
    title_tag = soup.find("title")
    name = title_tag.get_text().strip() if title_tag else ""
    # Strip common " | Brand" or " - Brand" suffixes from title
    for sep in (" | ", " - ", " – ", " — "):
        if sep in name:
            name = name.split(sep)[0].strip()
            break

    return {"name": name, "brand": brand}


def _extract_from_selectors(soup: BeautifulSoup) -> str | None:
    """Try known platform-specific CSS selectors for the product content area."""
    for tag, cls in _PRODUCT_CONTENT_SELECTORS:
        el = soup.find(tag, class_=cls)
        if el:
            text = el.get_text(separator=" ").strip()
            if len(text) > 50:
                return text
    return None


def _extract_from_main(soup: BeautifulSoup) -> str | None:
    """Fallback: use the <main> tag, stripped of noise."""
    main = soup.find("main")
    if main:
        for tag in main(_NOISE_TAGS):
            tag.decompose()
        return main.get_text(separator=" ")
    return None


def _get_page_text(html: str) -> str:
    """Extract the most relevant product text from a page HTML."""
    soup = BeautifulSoup(html, "lxml")

    text = _extract_from_jsonld(soup)
    if text:
        return text

    text = _extract_from_selectors(soup)
    if text:
        return text

    text = _extract_from_main(soup)
    if text:
        return text

    for tag in soup(_NOISE_TAGS):
        tag.decompose()
    return soup.get_text(separator=" ")


@retry(
    retry=retry_if_exception_type(requests.RequestException),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
def _fetch(url: str) -> str:
    resp = requests.get(url, headers=_HEADERS, timeout=SCRAPER_TIMEOUT)
    resp.raise_for_status()
    return resp.text


@retry(
    retry=retry_if_exception_type(anthropic.APIError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    reraise=True,
)
def _ask_claude(page_text: str, top_n: int, url: str = "") -> list[str]:
    """Ask Claude to extract meaningful search keywords from the product text."""
    message = _claude.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        system=_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"URL: {url}\n\n"
                f"Extract up to {top_n} search keywords from this product page. "
                f"Only include keywords relevant to the URL's main topic:\n\n"
                f"{page_text[:3000]}"
            ),
        }],
    )
    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


def extract_keywords(url: str, top_n: int = TOP_KEYWORDS_PER_URL) -> list[str]:
    """Fetch a product page and use Claude to extract meaningful search keywords.

    Returns an empty list on failure.
    """
    if not url:
        return []

    try:
        html = _fetch(url)
    except Exception as exc:
        print(f"[scraper] failed to fetch {url}: {exc}", file=sys.stderr)
        return []

    page_text = _get_page_text(html)

    try:
        keywords = _ask_claude(page_text, top_n, url=url)
        if not isinstance(keywords, list):
            raise ValueError("Claude did not return a list")
        return [str(kw).strip() for kw in keywords if kw]
    except Exception as exc:
        print(f"[scraper] Claude keyword extraction failed for {url}: {exc}", file=sys.stderr)
        return []
