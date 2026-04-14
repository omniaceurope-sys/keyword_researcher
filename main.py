"""
Keyword Researcher Agent — Entry Point

Usage:
  python main.py --url "https://example.com/collections/headphones"
  python main.py --site "https://example.com"
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

    # Step 1: Extract keywords
    print("Step 1/3  Extracting keywords from page...")
    keywords = scrape_keywords(url)
    if not keywords:
        print("ERROR: No keywords could be extracted from the page.")
        sys.exit(1)
    print(f"  → {len(keywords)} candidate keywords extracted.")

    # Step 2: Fetch search volumes
    print("Step 2/3  Fetching search volumes from Google Ads Keyword Planner...")
    keyword_volumes = get_search_volumes(keywords)
    if not keyword_volumes:
        print("WARNING: No keywords passed the volume filter. The Excel may be empty.")

    # Step 3: Write Excel
    print("Step 3/3  Writing Excel output...")
    output_path = write_single_page(url, keyword_volumes)

    print(f"\nDone! Output saved to:\n  {output_path}")
    print(f"\nSummary:")
    print(f"  Candidate keywords : {len(keywords)}")
    print(f"  After volume filter: {len(keyword_volumes)}")


def run_full_site(site_url: str) -> None:
    from pipeline.site_crawler import crawl
    from pipeline.categorizer import categorize_keywords

    print(f"\n=== Full Site Mode ===")
    print(f"Site: {site_url}\n")

    # Step 1: Crawl
    print("Step 1/5  Crawling site for category pages...")
    category_urls = crawl(site_url)

    if not category_urls:
        print("ERROR: No category pages found on this site.")
        sys.exit(1)

    print(f"\nFound {len(category_urls)} category pages:")
    for i, url in enumerate(category_urls, 1):
        print(f"  {i:3}. {url}")

    # Confirmation
    print()
    try:
        answer = input(f"Proceed with scraping all {len(category_urls)} pages? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(0)

    if answer not in ("y", "yes"):
        print("Aborted.")
        sys.exit(0)

    # Step 2: Scrape keywords
    print(f"\nStep 2/5  Extracting keywords from {len(category_urls)} pages...")
    all_keywords: list[str] = []
    page_keyword_map: dict[str, list[str]] = {}

    for url in tqdm(category_urls, desc="Scraping", unit="page"):
        kws = scrape_keywords(url)
        page_keyword_map[url] = kws
        all_keywords.extend(kws)

    # Deduplicate globally
    unique_keywords = list(dict.fromkeys(kw.lower().strip() for kw in all_keywords if kw.strip()))
    print(f"  → {len(unique_keywords)} unique candidate keywords across all pages.")

    if not unique_keywords:
        print("ERROR: No keywords could be extracted from any page.")
        sys.exit(1)

    # Step 3: Fetch volumes
    print(f"\nStep 3/5  Fetching search volumes for {len(unique_keywords)} keywords...")
    keyword_volumes = get_search_volumes(unique_keywords)
    print(f"  → {len(keyword_volumes)} keywords passed the volume filter.")

    if not keyword_volumes:
        print("WARNING: No keywords passed the volume filter.")

    # Step 4: Categorize
    print(f"\nStep 4/5  Categorizing keywords...")
    categorized = categorize_keywords(keyword_volumes, category_urls)
    print(f"  → Assigned keywords to {len(categorized)} categories.")

    # Step 5: Write Excel
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

    args = parser.parse_args()

    # Validate environment variables
    validate_env(require_google_ads=True)

    if args.url:
        url = validate_url(args.url)
        run_single_page(url)
    else:
        site_url = validate_url(args.site)
        run_full_site(site_url)


if __name__ == "__main__":
    main()
