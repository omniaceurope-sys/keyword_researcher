"""
site_crawler.py — Discovers category URLs via BFS crawl (--site mode only).
"""
import logging
import time
from collections import deque
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config.settings import CRAWL_MAX_DEPTH, CRAWL_DELAY_SECONDS

logger = logging.getLogger(__name__)

# URL path patterns that indicate a category page
CATEGORY_PATTERNS = [
    "/product-category/",
    "/collections/",
    "/category/",
    "/c/",
]

# /shop/ subpages (not root /shop)
SHOP_SUBPAGE_PREFIX = "/shop/"

# Patterns that disqualify a URL
EXCLUDE_PATTERNS = [
    "/deals", "/sale", "/clearance",
    "/uncategorized",
    "/gift-card", "/gift-cards",
    "?page=", "/page/",
    "/account", "/cart", "/checkout", "/login", "/register", "/my-account",
    "/blog", "/about", "/contact", "/faq", "/help", "/support",
    "/news", "/press", "/careers",
    "/search",
    "/wishlist",
    "/compare",
]

# Exact root paths to exclude
EXCLUDE_EXACT = {"/shop", "/shop/", "/store", "/store/"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


@retry(
    retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _fetch(url: str, timeout: int = 15) -> requests.Response:
    return requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)


def _is_category_url(parsed: urlparse, base_domain: str) -> bool:
    """Return True if this URL looks like an ecommerce category page."""
    path = parsed.path.rstrip("/") or "/"

    # Must be same domain
    if parsed.netloc and parsed.netloc != base_domain:
        return False

    # Exclude exact root shop/store paths
    if path in EXCLUDE_EXACT or path + "/" in EXCLUDE_EXACT:
        return False

    # Exclude disqualifying patterns
    full = (parsed.path + ("?" + parsed.query if parsed.query else "")).lower()
    if any(excl in full for excl in EXCLUDE_PATTERNS):
        return False

    # Must match a known category pattern
    p = parsed.path.lower()
    if any(pat in p for pat in CATEGORY_PATTERNS):
        return True

    # /shop/ subpages (path starts with /shop/ and has more segments)
    if p.startswith(SHOP_SUBPAGE_PREFIX) and len(p) > len(SHOP_SUBPAGE_PREFIX):
        return True

    return False


def _slug(url: str) -> str:
    """Normalised last-segment key for deduplication."""
    path = urlparse(url).path.rstrip("/")
    return path.lower()


def crawl(start_url: str) -> list[str]:
    """
    BFS-crawl starting from start_url up to CRAWL_MAX_DEPTH levels.
    Returns a deduplicated list of category URLs.
    """
    parsed_start = urlparse(start_url)
    base_domain = parsed_start.netloc

    visited_pages: set[str] = set()      # pages we've fetched (normalised)
    found_categories: dict[str, str] = {}  # slug → full URL

    # Queue items: (url, depth)
    queue: deque[tuple[str, int]] = deque()
    queue.append((start_url, 0))
    visited_pages.add(_slug(start_url))

    while queue:
        url, depth = queue.popleft()

        if depth > CRAWL_MAX_DEPTH:
            continue

        logger.info(f"Crawling depth={depth}: {url}")

        try:
            resp = _fetch(url)
            resp.raise_for_status()
        except Exception as exc:
            logger.warning(f"Failed to fetch {url}: {exc}")
            time.sleep(CRAWL_DELAY_SECONDS)
            continue

        soup = BeautifulSoup(resp.text, "lxml")

        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()
            if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
                continue

            full_url = urljoin(url, href)
            parsed = urlparse(full_url)

            # Strip fragment
            full_url = parsed._replace(fragment="").geturl()
            parsed = urlparse(full_url)

            # Same domain only
            if parsed.netloc != base_domain:
                continue

            slug = _slug(full_url)

            # Check if it's a category
            if _is_category_url(parsed, base_domain):
                if slug not in found_categories:
                    found_categories[slug] = full_url
                    logger.debug(f"Found category: {full_url}")

            # Enqueue for further crawling if not visited and within depth
            if slug not in visited_pages and depth < CRAWL_MAX_DEPTH:
                visited_pages.add(slug)
                queue.append((full_url, depth + 1))

        time.sleep(CRAWL_DELAY_SECONDS)

    categories = list(found_categories.values())
    logger.info(f"Crawl complete. Found {len(categories)} category pages.")
    return categories
