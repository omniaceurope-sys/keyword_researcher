"""Keyword Researcher — main entry point."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tqdm import tqdm

from config.settings import TOP_KEYWORDS_PER_URL, DEFAULT_GEO_TARGET_ID, DEFAULT_LANGUAGE_ID, MIN_SEARCH_VOLUME
from pipeline.scraper import extract_keywords
from pipeline.keyword_planner import get_search_volumes
from pipeline.categorizer import assign_keywords_to_categories
from pipeline.excel_writer import write_excel
from pipeline.site_crawler import crawl, _is_category_url
from pipeline.url_loader import load_urls


def run_single(
    url: str,
    output_path: str,
    geo_target_id: str = DEFAULT_GEO_TARGET_ID,
    language_id: str = DEFAULT_LANGUAGE_ID,
) -> None:
    print(f"Scraping: {url}")
    candidates = extract_keywords(url, top_n=TOP_KEYWORDS_PER_URL)
    print(f"  {len(candidates)} candidate keywords extracted")

    if not candidates:
        print("[error] no keywords extracted — check the URL and try again", file=sys.stderr)
        return

    print(f"Fetching search volumes for {len(candidates)} candidates...")
    volumes = get_search_volumes(candidates, geo_target_id=geo_target_id, language_id=language_id)

    kw_list = sorted(
        [{"kw": kw, "volume": volumes.get(kw, 0)} for kw in candidates if volumes.get(kw, 0) > MIN_SEARCH_VOLUME],
        key=lambda x: x["volume"],
        reverse=True,
    )

    if not kw_list:
        print("[error] no keywords with sufficient search volume", file=sys.stderr)
        return

    print(f"  {len(kw_list)} keywords with volume > {MIN_SEARCH_VOLUME}")
    write_excel([{"url": url, "keywords": kw_list}], output_path)


def run_site(
    homepage: str,
    output_path: str,
    geo_target_id: str = DEFAULT_GEO_TARGET_ID,
    language_id: str = DEFAULT_LANGUAGE_ID,
) -> None:
    # 1. Crawl — keep only category/listing pages, deduplicate by last path segment
    all_urls = crawl(homepage)
    _SKIP_SLUGS = {
        "shop", "store", "trgovina", "boutique", "tienda", "negozio", "winkel",
        "sale", "deals", "offers", "akcija", "aktualne-ugodnosti", "ugodnosti",
        "promotions", "rabais", "offerte", "angebote",
        "gift-cards", "gift-vouchers", "darilni-boni", "boni", "vouchers",
        "uncategorized", "neuvrsceni", "neuvrsteno", "brez-kategorije",
        "page",
    }
    seen_slugs: set[str] = set()
    urls = []
    for u in all_urls:
        if not _is_category_url(u):
            continue
        segments = [s for s in u.rstrip("/").split("/") if s]
        slug = segments[-1]
        if slug.isdigit() or slug in _SKIP_SLUGS or "page" in segments:
            continue
        if slug not in seen_slugs:
            seen_slugs.add(slug)
            urls.append(u)
    print(f"  {len(urls)} category pages (filtered from {len(all_urls)} total)")
    if not urls:
        print("[error] no category pages found", file=sys.stderr)
        return

    # Category names derived from URL slugs (used for Claude categorization)
    category_names = [
        u.rstrip("/").split("/")[-1].replace("-", " ").replace("_", " ").title()
        for u in urls
    ]
    print(f"  Categories: {', '.join(category_names)}")

    # 2. Scrape all pages — pool all candidate keywords
    print(f"\nScraping {len(urls)} pages...")
    all_candidates: list[str] = []
    for url in tqdm(urls, desc="  scraping"):
        kws = extract_keywords(url, top_n=TOP_KEYWORDS_PER_URL)
        all_candidates.extend(kws)

    # Deduplicate while preserving order
    all_candidates = list(dict.fromkeys(all_candidates))
    print(f"  {len(all_candidates)} unique candidate keywords across all pages")

    if not all_candidates:
        print("[error] no keywords extracted from any page", file=sys.stderr)
        return

    # 3. Fetch search volumes for all candidates at once
    print(f"Fetching search volumes for {len(all_candidates)} candidates...")
    volumes = get_search_volumes(all_candidates, geo_target_id=geo_target_id, language_id=language_id)

    # Filter by minimum volume
    kw_volumes = {
        kw: volumes.get(kw, 0)
        for kw in all_candidates
        if volumes.get(kw, 0) > MIN_SEARCH_VOLUME
    }
    print(f"  {len(kw_volumes)} keywords with volume > {MIN_SEARCH_VOLUME}")

    if not kw_volumes:
        print("[error] no keywords with sufficient search volume", file=sys.stderr)
        return

    # 4. Claude assigns each keyword to its most relevant category
    print(f"Assigning {len(kw_volumes)} keywords to {len(category_names)} categories (Claude)...")
    categorized = assign_keywords_to_categories(kw_volumes, category_names)

    # 5. Build results — one entry per category
    results = [
        {"url": url, "category": cat, "keywords": kws}
        for url, cat, kws in zip(urls, category_names, [categorized.get(c, []) for c in category_names])
        if categorized.get(cat)
    ]
    print(f"  {len(results)} categories with keywords")
    write_excel(results, output_path)


def run_csv(
    csv_path: str,
    output_path: str,
    geo_target_id: str = DEFAULT_GEO_TARGET_ID,
    language_id: str = DEFAULT_LANGUAGE_ID,
    limit: int | None = None,
) -> None:
    print(f"Loading URLs: {csv_path}")
    urls = load_urls(csv_path)
    if limit:
        urls = urls[:limit]
    print(f"  {len(urls)} URLs loaded")

    if not urls:
        print("[error] no URLs found in file", file=sys.stderr)
        return

    # Scrape all pages and collect candidates per URL
    print(f"\nScraping {len(urls)} landing pages...")
    url_candidates: list[tuple[str, list[str]]] = []
    for url in tqdm(urls, desc="  scraping"):
        kws = extract_keywords(url, top_n=TOP_KEYWORDS_PER_URL)
        url_candidates.append((url, kws))

    # Pool all unique candidates for a single batch volume lookup
    all_candidates = list(dict.fromkeys(kw for _, kws in url_candidates for kw in kws))
    print(f"  {len(all_candidates)} unique candidate keywords")

    if not all_candidates:
        print("[error] no keywords extracted from any URL", file=sys.stderr)
        return

    print(f"\nFetching search volumes for {len(all_candidates)} candidates...")
    volumes = get_search_volumes(all_candidates, geo_target_id=geo_target_id, language_id=language_id)

    # Build one result entry per URL
    results = []
    skipped = 0
    for url, candidates in url_candidates:
        kw_list = sorted(
            [{"kw": kw, "volume": volumes.get(kw, 0)} for kw in candidates if volumes.get(kw, 0) > MIN_SEARCH_VOLUME],
            key=lambda x: x["volume"],
            reverse=True,
        )
        if kw_list:
            results.append({"url": url, "keywords": kw_list})
        else:
            skipped += 1

    print(f"  {len(results)} URLs with results, {skipped} skipped (no volume)")

    if not results:
        print("[error] no keywords with sufficient search volume", file=sys.stderr)
        return

    write_excel(results, output_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Keyword research tool — extracts keywords and search volumes."
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--url", help="Single product/category page URL to research")
    mode.add_argument("--site", help="Homepage URL — crawls the entire site automatically")
    mode.add_argument("--csv", metavar="FILE", help="CSV file of URLs — one sheet per URL in output")

    parser.add_argument("--output", default="data/output/keyword_research.xlsx", help="Output Excel workbook path")
    parser.add_argument("--geo", default=DEFAULT_GEO_TARGET_ID, help="Google Ads geo target constant ID")
    parser.add_argument("--language", default=DEFAULT_LANGUAGE_ID, help="Google Ads language constant ID")
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N URLs (CSV mode)")
    args = parser.parse_args()

    if args.url:
        run_single(args.url, args.output, geo_target_id=args.geo, language_id=args.language)
    elif args.site:
        run_site(args.site, args.output, geo_target_id=args.geo, language_id=args.language)
    else:
        run_csv(args.csv, args.output, geo_target_id=args.geo, language_id=args.language, limit=args.limit)


if __name__ == "__main__":
    main()
