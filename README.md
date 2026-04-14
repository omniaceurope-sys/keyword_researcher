# Keyword Researcher Agent

An automated keyword research pipeline for ecommerce websites. It crawls category pages, generates search keywords using Claude AI, fetches real search volumes from Google Ads Keyword Planner, and exports a ready-to-use Excel file.

---

## Features

- **Single page mode** — research keywords for one URL in minutes
- **Full site mode** — crawl an entire ecommerce site, extract keywords per category, and get a multi-sheet Excel output
- **Claude-powered extraction** — generates ~30 realistic search queries per page (not product titles)
- **Real search volumes** — via Google Ads Keyword Planner API, with competition level
- **Smart categorization** — Claude assigns keywords to the most relevant category
- **Streamlit UI** — web interface for non-technical users
- **CLI** — scriptable for automation

---

## Project Structure

```
keyword_researcher/
├── app.py                     ← Streamlit web UI
├── main.py                    ← CLI entry point
├── requirements.txt
├── .env.example               ← credential template
├── config/
│   └── settings.py            ← env vars + constants
├── pipeline/
│   ├── site_crawler.py        ← BFS category URL discovery
│   ├── scraper.py             ← keyword extraction via Claude
│   ├── keyword_planner.py     ← Google Ads search volumes
│   ├── categorizer.py         ← keyword→category assignment via Claude
│   └── excel_writer.py        ← formatted .xlsx output
├── tests/
│   └── test_basic.py          ← unit tests (no API calls)
└── data/output/               ← generated .xlsx files
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure credentials

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Required variables:

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key from [console.anthropic.com](https://console.anthropic.com) |
| `GOOGLE_ADS_DEVELOPER_TOKEN` | From Google Ads API Center |
| `GOOGLE_ADS_CLIENT_ID` | OAuth2 client ID |
| `GOOGLE_ADS_CLIENT_SECRET` | OAuth2 client secret |
| `GOOGLE_ADS_REFRESH_TOKEN` | OAuth2 refresh token |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | MCC account ID (no dashes) |
| `GOOGLE_ADS_CUSTOMER_ID` | Client account ID (no dashes) |

---

## Usage

### Web UI (Streamlit)

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

### CLI — Single page

```bash
python main.py --url "https://example.com/collections/headphones"
```

### CLI — Full site crawl

```bash
python main.py --site "https://example.com"
```

---

## Output

Excel file saved to `data/output/{domain}_{date}.xlsx`:

- **Single page mode** — one sheet with all keywords
- **Full site mode** — one sheet per category

Each sheet contains:

| Column | Description |
|---|---|
| Keyword | Search query |
| Volume | Average monthly searches |
| Competition | LOW / MEDIUM / HIGH |

---

## Pipeline Overview

```
--url mode:
  URL → scraper (Claude) → keyword_planner (Google Ads) → excel_writer

--site mode:
  homepage → site_crawler → scraper ×N (Claude) → keyword_planner (Google Ads)
           → categorizer (Claude) → excel_writer
```

### Step details

| Step | Module | What it does |
|---|---|---|
| 1 | `site_crawler` | BFS crawl, finds category pages (max 2 levels deep) |
| 2 | `scraper` | Fetches HTML, strips noise, asks Claude for ~30 search queries |
| 3 | `keyword_planner` | Batches keywords into groups of 20, calls Keyword Planner API |
| 4 | `categorizer` | Claude assigns each keyword to the best matching category |
| 5 | `excel_writer` | Writes formatted `.xlsx` with bold headers + auto-width columns |

---

## Running Tests

```bash
python -m pytest tests/ -v
```

Tests cover URL filtering, content extraction, deduplication, and Excel writing — no API calls required.

---

## Configuration

Edit `config/settings.py` to adjust:

| Constant | Default | Description |
|---|---|---|
| `CRAWL_MAX_DEPTH` | `2` | How deep to crawl from homepage |
| `CRAWL_DELAY_SECONDS` | `1` | Delay between crawl requests |
| `KEYWORDS_PER_PAGE` | `30` | Keywords to generate per page |
| `KP_BATCH_SIZE` | `20` | Keywords per Google Ads API call |
| `KP_MIN_VOLUME` | `10` | Minimum monthly volume to keep |
