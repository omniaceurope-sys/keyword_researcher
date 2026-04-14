# Keyword Researcher

A CLI tool that crawls ecommerce websites, extracts search keywords using Claude AI, fetches real search volumes from Google Ads Keyword Planner, and outputs a structured Excel workbook ready for Google Ads campaign planning.

## Features

- Three input modes: single URL, full-site crawl, or CSV list
- Keyword extraction via Claude Sonnet (functional queries, not brand names)
- Real search volumes from Google Ads Keyword Planner with local caching
- AI-powered keyword categorization across site sections
- Excel output — one sheet per category, sorted by volume

## Requirements

- Python 3.12+
- Google Ads account with Keyword Planner access and a developer token
- Anthropic API key

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure credentials

```bash
cp .env.example .env
```

Fill in `.env`:

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic Console → API Keys |
| `GOOGLE_ADS_DEVELOPER_TOKEN` | Google Ads → Tools → API Center |
| `GOOGLE_ADS_CLIENT_ID` | Google Cloud Console → OAuth 2.0 Client ID |
| `GOOGLE_ADS_CLIENT_SECRET` | Google Cloud Console → OAuth 2.0 Client Secret |
| `GOOGLE_ADS_REFRESH_TOKEN` | Generated via OAuth flow |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | MCC account ID (no dashes) |
| `GOOGLE_ADS_CUSTOMER_ID` | Target account ID (no dashes) |

## Streamlit UI

A web interface is available for running the tool without the CLI:

```bash
streamlit run app.py
```

This opens a browser UI with three tabs matching the three CLI modes. On **Streamlit Cloud**, add all credentials from `.env.example` to the app's **Secrets** panel (`Settings → Secrets`) — the app injects them into the environment automatically before any pipeline code runs.

---

## CLI Usage

### Single page

Research keywords for one product or category URL:

```bash
python main.py --url "https://example.com/collections/headphones"
```

### Full site crawl

Crawl an entire site, discover category pages, and output one sheet per category:

```bash
python main.py --site "https://example.com"
```

### CSV list

Research keywords for a list of URLs from a CSV file (one sheet per URL):

```bash
python main.py --csv data/input/urls.csv
```

CSV format — one URL per line, no header required:

```
https://example.com/products/product-a
https://example.com/products/product-b
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--output` | `data/output/keyword_research.xlsx` | Output file path |
| `--geo` | `2705` (Slovenia) | Google Ads geo target constant ID |
| `--language` | `1023` (Slovenian) | Google Ads language constant ID |
| `--limit` | none | Process only the first N URLs (CSV mode) |

## Output

Each run produces an `.xlsx` file in `data/output/`. Each sheet contains:

- Source URL in the header row
- `Keyword` and `Avg Monthly Volume` columns
- Keywords sorted by volume descending
- Only keywords with > 10 avg monthly searches

## Project Structure

```
keyword_researcher/
├── main.py                  — entry point
├── requirements.txt
├── .env.example
├── MANUAL.md                — end-user guide
├── config/
│   └── settings.py          — env vars and constants
├── pipeline/
│   ├── url_loader.py        — reads URL CSV files
│   ├── site_crawler.py      — BFS site crawler
│   ├── scraper.py           — Claude-powered keyword extraction
│   ├── keyword_planner.py   — Google Ads volume lookup (cached)
│   ├── categorizer.py       — Claude-powered keyword categorization
│   └── excel_writer.py      — Excel output writer
└── data/
    ├── input/               — place your urls.csv files here
    ├── output/              — generated .xlsx files
    └── cache/               — volumes_cache.json (auto-generated)
```

## Caching

Search volumes are cached in `data/cache/volumes_cache.json` keyed by geo+language. Repeated runs skip the API for already-known keywords, saving quota and time.

## Notes

- Keywords are generated in the same language as the page content
- Brand names and model names are excluded from keyword output
- The Google Ads API batches requests in groups of 20 to stay within API limits
- The site crawler follows internal links up to 2 levels deep
