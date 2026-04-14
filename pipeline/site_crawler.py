"""Crawl a website to discover product and category pages."""

import sys
from collections import deque, defaultdict
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from config.settings import SCRAPER_TIMEOUT

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# Path segments that clearly indicate non-product pages — always skip
_SKIP_SEGMENTS = {
    "cart", "checkout", "login", "logout", "register", "sign-in", "sign-up",
    "account", "my-account", "profile", "orders", "wishlist", "compare",
    "blog", "news", "articles", "posts", "press", "media",
    "about", "about-us", "contact", "contact-us", "faq", "help", "support",
    "privacy", "terms", "cookies", "legal", "policy", "sitemap",
    "search", "404", "error", "cdn", "static", "assets",
    "recipes", "recipe", "recept", "recepti",  # blog/recipe pages
}

# Path segments that signal a product or category page
_PRODUCT_SIGNALS = {
    "product", "products",
    "shop", "store",
    "collections", "collection",
    "category", "categories", "cat",
    "catalog", "catalogue",
    "item", "items",
    "buy", "p",
    # Slovenian / other common European e-commerce terms
    "izdelek", "izdelki", "trgovina", "produkt", "produit", "prodotto",
    "producto", "artikel", "produkte",
}

# Path segments that identify a category/listing page (not a leaf product)
_CATEGORY_SIGNALS = {
    "product-category", "category", "categories", "cat",
    "collections", "collection",
    "shop", "store", "catalog", "catalogue",
    "trgovina",  # Slovenian for "store"
}

_SKIP_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg",
    ".bmp", ".ico", ".pdf", ".zip", ".xml", ".json",
)

# Ordered list of CSS selectors for product grids across platforms.
# Tried in order; first that yields links wins.
_PRODUCT_GRID_SELECTORS = [
    ("ul", "products"),               # WooCommerce standard
    ("div", "products"),              # WooCommerce
    ("ul", "collection-grid__list"),  # Shopify
    ("div", "collection-grid"),       # Shopify
    ("div", "product-grid"),          # Shopify / generic
    ("ol", "products"),               # Magento 2
    ("div", "products-grid"),         # Magento
    ("ul", "product-list"),           # Generic
    ("div", "product-list"),          # Generic
    ("div", "product-listing"),       # Generic
    ("div", "items-grid"),            # Various
    ("ul", "items-grid"),             # Various
]


def _normalize(url: str) -> str:
    """Normalize a URL: remove fragment, query string, trailing slash, fix double slashes in path."""
    p = urlparse(url)
    path = p.path.rstrip("/")
    # Collapse double slashes in path (e.g. //trgovina → /trgovina)
    while "//" in path:
        path = path.replace("//", "/")
    return urlunparse((p.scheme, p.netloc, path, "", "", ""))


def _base_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _same_domain(base: str, url: str) -> bool:
    return urlparse(url).netloc == urlparse(base).netloc


def _is_product_like(url: str) -> bool:
    """Return True if the URL looks like a product or category page."""
    path = urlparse(url).path.lower().strip("/")

    if not path:
        return False

    if any(url.lower().endswith(ext) for ext in _SKIP_EXTENSIONS):
        return False

    segments = path.split("/")
    segment_set = set(segments)

    if segment_set & _SKIP_SEGMENTS:
        return False

    if segment_set & _PRODUCT_SIGNALS:
        return True

    # Deep paths (2+ segments) found on category pages are likely products
    if len(segments) >= 2:
        return True

    return False


def _is_category_url(url: str) -> bool:
    """Return True if the URL looks like a category/listing page."""
    segments = set(urlparse(url).path.lower().strip("/").split("/"))
    return bool(segments & _CATEGORY_SIGNALS)


def _links_from_grid_selectors(soup: BeautifulSoup, base: str) -> list[str]:
    """Try known product grid CSS selectors across platforms. Returns links or []."""
    for tag, cls in _PRODUCT_GRID_SELECTORS:
        grid = soup.find(tag, class_=cls)
        if not grid:
            continue
        links = []
        for a in grid.find_all("a", href=True):
            full = _normalize(urljoin(base, a["href"]))
            if _same_domain(base, full) and full != base and _is_product_like(full):
                links.append(full)
        links = list(dict.fromkeys(links))
        if links:
            return links
    return []


def _links_from_density(soup: BeautifulSoup, base: str) -> list[str]:
    """Fallback: find the page container with the densest cluster of product links.

    Groups all product-like internal <a> links by their grandparent element,
    then returns the links from the container with the most unique product URLs.
    This works for custom themes and unknown platforms.
    """
    container_links: dict[int, list[str]] = defaultdict(list)

    for a in soup.find_all("a", href=True):
        full = _normalize(urljoin(base, a["href"]))
        if not _same_domain(base, full) or full == base:
            continue
        if not _is_product_like(full):
            continue

        # Walk up 3 levels to find a stable container
        parent = a
        for _ in range(3):
            if parent.parent:
                parent = parent.parent
            else:
                break
        container_links[id(parent)].append(full)

    if not container_links:
        return []

    best = max(container_links, key=lambda k: len(container_links[k]))
    return list(dict.fromkeys(container_links[best]))


def _find_pagination_links(soup: BeautifulSoup, url: str, base: str) -> list[str]:
    """Find ?page=N pagination links on a listing page."""
    import re
    seen = set()
    pages = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full = urljoin(base, href)
        # Keep only same-domain links with ?page= query param
        if not _same_domain(base, full):
            continue
        if re.search(r"[?&]page=\d+", full) and full not in seen:
            seen.add(full)
            pages.append(full)
    return pages


def _fetch_links(url: str, base: str, products_only: bool = False) -> list[str]:
    """Fetch a page and return all unique internal links.

    If products_only=True (used on category pages), tries platform-specific
    product grid selectors first, then falls back to density analysis.
    This avoids picking up sidebar/footer/related-product links.
    """
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=SCRAPER_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        print(f"[crawler] failed to fetch {url}: {exc}", file=sys.stderr)
        return []

    soup = BeautifulSoup(resp.text, "lxml")

    if products_only:
        # 1. Try known platform selectors
        links = _links_from_grid_selectors(soup, base)
        if links:
            return links
        # 2. Density fallback
        links = _links_from_density(soup, base)
        if links:
            return links
        print(f"[crawler] could not isolate product grid on {url}, using full scan", file=sys.stderr)

    # Full page scan (used on homepage and as last resort)
    links = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        full = _normalize(urljoin(base, href))
        if _same_domain(base, full) and full != base:
            links.append(full)

    return list(dict.fromkeys(links))


def crawl(homepage: str) -> list[str]:
    """BFS crawl from homepage up to 2 levels deep.

    Level 0: homepage      → discovers category/shop pages
    Level 1: category page → discovers individual product pages (grid-only scan)
    Level 2: product page  → leaf node, not crawled further

    Returns a deduplicated list of all product/category URLs found.
    Works across WooCommerce, Shopify, Magento, and custom platforms.
    """
    base = _base_url(homepage)
    visited = {homepage.rstrip("/")}
    product_pages: list[str] = []

    queue: deque[tuple[str, int]] = deque([(homepage, 0)])

    print(f"[crawler] starting crawl from {homepage}")

    while queue:
        url, depth = queue.popleft()

        if depth >= 2:
            continue

        try:
            resp = __import__("requests").get(url, headers=_HEADERS, timeout=SCRAPER_TIMEOUT)
            resp.raise_for_status()
            soup = __import__("bs4").BeautifulSoup(resp.text, "lxml")
        except Exception as exc:
            print(f"[crawler] failed to fetch {url}: {exc}", file=sys.stderr)
            continue

        is_category = _is_category_url(url)

        # Extract product links (grid-aware on category pages)
        if is_category:
            links = _links_from_grid_selectors(soup, base)
            if not links:
                links = _links_from_density(soup, base)
            if not links:
                links = [
                    _normalize(urljoin(base, a["href"]))
                    for a in soup.find_all("a", href=True)
                    if _same_domain(base, urljoin(base, a["href"]))
                ]
            # Also pick up sub-category links from navigation (not just product grid)
            sub_cats = [
                _normalize(urljoin(base, a["href"]))
                for a in soup.find_all("a", href=True)
                if _same_domain(base, urljoin(base, a["href"]))
                and _is_category_url(_normalize(urljoin(base, a["href"])))
            ]
            links = list(dict.fromkeys(links + sub_cats))
            # Follow pagination on listing pages
            for page_url in _find_pagination_links(soup, url, base):
                if page_url not in visited:
                    visited.add(page_url)
                    queue.append((page_url, depth))  # same depth — still a listing page
        else:
            links = [
                _normalize(urljoin(base, a["href"]))
                for a in soup.find_all("a", href=True)
                if a.get("href", "").strip() and
                not a["href"].strip().startswith(("#", "mailto:", "tel:", "javascript:")) and
                _same_domain(base, urljoin(base, a["href"]))
            ]

        for link in links:
            normalized = link.rstrip("/")
            if normalized in visited:
                continue
            visited.add(normalized)

            if _is_product_like(normalized):
                product_pages.append(normalized)
                if _is_category_url(normalized):
                    queue.append((normalized, depth + 1))

    print(f"[crawler] discovered {len(product_pages)} product/category pages")
    return product_pages
