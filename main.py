"""
Keyword Researcher Agent — Entry Point

Usage:
  python main.py --url "https://example.com/collections/headphones"
  python main.py --site "https://example.com"
  python main.py --csv urls.csv
"""
import argparse
import logging
import sys
from urllib.parse import urlparse

from tqdm import tqdm

from config.settings import validate_env
from pipeline.scraper import scrape_keywords
from pipeline.keyword_planner import get_search_volumes
from pipeline.excel_writer import write_single_page, write_multi_category

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        print(f"ERROR: Invalid URL: {url}")
        sys.exit(1)
    return url.rstrip("/")


def run_single_page(url: str) -> None:
    print(f"\n=== Single Page Mode ===")
    print(f"URL: {url}\n")

    print("Step 1/3  Extracting keywords from page...")
    keywords = scrape_keywords(url)
    if not keywords:
        print("ERROR: No keywords could be extracted from the page.")
        sys.exit(1)
    print(f"  → {len(keywords)} candidate keywords extracted.")

    print("Step 2/3  Fetching search volumes from Google Ads Keyword Planner...")
    keyword_volumes = get_search_volumes(keywords)
    if not keyword_volumes:
        print("WARNING: No keywords passed the volume filter. The Excel may be empty.")

    print("Step 3/3  Writing Excel output...")
    output_path = write_single_page(url, keyword_volumes)

    print(f"\nDone! Output saved to:\n  {output_path}")
    print(f"\nSummary:")
    print(f"  Candidate keywords : {len(keywords)}")
    print(f"  After volume filter: {len(keyword_volumes)}")


def run_csv(csv_path: str) -> None:
    from pipeline.url_loader import load_urls
    from pipeline.categorizer import categorize_keywords

    print(f"\n=== CSV Mode ===")
    print(f"File: {csv_path}\n")

    # Step 1: Load URLs
    print("Step 1/4  Loading URLs from CSV...")
    urls = load_urls(csv_path)
    if not urls:
        print("ERROR: No URLs found in the CSV file.")
        sys.exit(1)
    print(f"  → {len(urls)} URLs loaded.")
    for i, u in enumerate(urls, 1):
        print(f"  {i:3}. {u}")

    # Step 2: Scrape keywords
    print(f"\nStep 2/4  Extracting keywords from {len(urls)} pages...")
    all_keywords: list[str] = []
    page_keyword_map: dict[str, list[str]] = {}

    for url in tqdm(urls, desc="Scraping", unit="page"):
        kws = scrape_keywords(url)
        page_keyword_map[url] = kws
        all_keywords.extend(kws)

    unique_keywords = list(dict.fromkeys(kw.lower().strip() for kw in all_keywords if kw.strip()))
    print(f"  → {len(unique_keywords)} unique candidate keywords across all pages.")

    if not unique_keywords:
        print("ERROR: No keywords could be extracted from any page.")
        sys.exit(1)

    # Step 3: Fetch volumes
    print(f"\nStep 3/4  Fetching search volumes for {len(unique_keywords)} keywords...")
    keyword_volumes = get_search_volumes(unique_keywords)
    print(f"  → {len(keyword_volumes)} keywords passed the volume filter.")

    if not keyword_volumes:
        print("WARNING: No keywords passed the volume filter.")

    # Step 4: Write Excel — one sheet per URL (using last path segment as sheet name)
    print(f"\nStep 4/4  Writing Excel output...")

    def _sheet_name(url: str) -> str:
        path = urlparse(url).path.rstrip("/")
        slug = path.split("/")[-1] if "/" in path else urlparse(url).netloc
        return slug.replace("-", " ").replace("_", " ").title()

    # Build per-URL keyword dicts filtered to volumes we got back
    categorized: dict[str, list[dict]] = {}
    for url in urls:
        page_kws = page_keyword_map.get(url, [])
        sheet = _sheet_name(url)
        entries = []
        for kw in page_kws:
            kw_lower = kw.lower().strip()
            if kw_lower in keyword_volumes:
                data = keyword_volumes[kw_lower]
                entries.append({
                    "keyword": kw_lower,
                    "volume": data["volume"],
                    "competition": data["competition"],
                })
        entries.sort(key=lambda x: -x["volume"])
        if entries:
            # Handle duplicate sheet names
            base = sheet
            idx = 2
            while sheet in categorized:
                sheet = f"{base} {idx}"
                idx += 1
            categorized[sheet] = entries

    # Use the domain of the first URL as the file name base
    first_domain = urlparse(urls[0]).netloc
    output_path = write_multi_category(f"https://{first_domain}", categorized)

    print(f"\nDone! Output saved to:\n  {output_path}")
    print(f"\nSummary:")
    print(f"  URLs processed         : {len(urls)}")
    print(f"  Candidate keywords     : {len(unique_keywords)}")
    print(f"  After volume filter    : {len(keyword_volumes)}")
    print(f"  Sheets in output file  : {len(categorized)}")


def run_full_site(site_url: str) -> None:
    from pipeline.site_crawler import crawl
    from pipeline.categorizer import categorize_keywords

    print(f"\n=== Full Site Mode ===")
    print(f"Site: {site_url}\n")

    print("Step 1/5  Crawling site for category pages...")
    category_urls = crawl(site_url)

    if not category_urls:
        print("ERROR: No category pages found on this site.")
        sys.exit(1)

    print(f"\nFound {len(category_urls)} category pages:")
    for i, url in enumerate(category_urls, 1):
        print(f"  {i:3}. {url}")

    print()
    try:
        answer = input(f"Proceed with scraping all {len(category_urls)} pages? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(0)

    if answer not in ("y", "yes"):
        print("Aborted.")
        sys.exit(0)

    print(f"\nStep 2/5  Extracting keywords from {len(category_urls)} pages...")
    all_keywords: list[str] = []
    page_keyword_map: dict[str, list[str]] = {}

    for url in tqdm(category_urls, desc="Scraping", unit="page"):
        kws = scrape_keywords(url)
        page_keyword_map[url] = kws
        all_keywords.extend(kws)

    unique_keywords = list(dict.fromkeys(kw.lower().strip() for kw in all_keywords if kw.strip()))
    print(f"  → {len(unique_keywords)} unique candidate keywords across all pages.")

    if not unique_keywords:
        print("ERROR: No keywords could be extracted from any page.")
        sys.exit(1)

    print(f"\nStep 3/5  Fetching search volumes for {len(unique_keywords)} keywords...")
    keyword_volumes = get_search_volumes(unique_keywords)
    print(f"  → {len(keyword_volumes)} keywords passed the volume filter.")

    if not keyword_volumes:
        print("WARNING: No keywords passed the volume filter.")

    print(f"\nStep 4/5  Categorizing keywords...")
    categorized = categorize_keywords(keyword_volumes, category_urls)
    print(f"  → Assigned keywords to {len(categorized)} categories.")

    print(f"\nStep 5/5  Writing Excel output...")
    output_path = write_multi_category(site_url, categorized)

    print(f"\nDone! Output saved to:\n  {output_path}")
    print(f"\nSummary:")
    print(f"  Category pages crawled : {len(category_urls)}")
    print(f"  Candidate keywords     : {len(unique_keywords)}")
    print(f"  After volume filter    : {len(keyword_volumes)}")
    print(f"  Categories with data   : {len(categorized)}")
    total_assigned = sum(len(v) for v in categorized.values())
    print(f"  Total keywords in file : {total_assigned}")


def main():
    parser = argparse.ArgumentParser(
        description="Keyword Researcher Agent — crawl ecommerce sites and extract SEO keywords.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", metavar="URL", help="Single category/product page URL")
    group.add_argument("--site", metavar="URL", help="Full site URL to crawl")
    group.add_argument("--csv", metavar="FILE", help="CSV file containing a list of URLs")

    args = parser.parse_args()

    validate_env(require_google_ads=True)

    if args.url:
        run_single_page(validate_url(args.url))
    elif args.site:
        run_full_site(validate_url(args.site))
    else:
        run_csv(args.csv)


if __name__ == "__main__":
    main()
