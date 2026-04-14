# Keyword Researcher — User Manual

## What does this tool do?

This tool automatically researches keywords for your product landing pages and generates complete Google Ads Responsive Search Ad (RSA) copy, ready to paste directly into Google Ads.

For each product URL you provide, it:
1. Visits the product landing page and extracts candidate keywords
2. Checks how often those keywords are searched on Google (via Keyword Planner)
3. Uses AI (Claude) to group keywords into thematic ad group categories
4. Generates 15 headlines and 5 descriptions per category following Google Ads RSA rules
5. Outputs everything in a structured Excel workbook — one sheet per product URL

---

## Requirements

Before using this tool, make sure you have:
- **Python 3.12** installed — download at https://www.python.org/downloads
- **VS Code** installed — download at https://code.visualstudio.com
- A `.env` file inside the `keyword_researcher/` folder with all credentials filled in (see Setup below)
- Dependencies installed (see Setup below)

---

## Credentials

This tool requires a `.env` file placed inside the `keyword_researcher/` folder.

Copy `.env.example` to `.env` and fill in your credentials:

| Credential | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys |
| `GOOGLE_ADS_DEVELOPER_TOKEN` | Google Ads → Tools → API Center |
| `GOOGLE_ADS_CLIENT_ID` + `CLIENT_SECRET` | console.cloud.google.com → Credentials → OAuth 2.0 Client |
| `GOOGLE_ADS_REFRESH_TOKEN` | Generate with the OAuth script (see merchant_optimizer MANUAL.md) |
| `GOOGLE_ADS_CUSTOMER_ID` | Your Google Ads account ID (no dashes) |

---

## First-Time Setup

### Step 1 — Open the project in VS Code

1. Open VS Code
2. Click **File → Open Folder**
3. Navigate to the `Omniac_AI` folder and click **Select Folder**

### Step 2 — Open the terminal

Press **Ctrl + `** (backtick key, top-left of keyboard under Esc)

### Step 3 — Set up your `.env` file

```
cp .env.example .env
```

Then open `.env` and fill in all credentials.

### Step 4 — Install dependencies (only needed once)

```
pip install -r requirements.txt
```

---

## Running the Tool

### Step 1 — Prepare your URL input file

Create a CSV file with one product URL per line and place it in:
```
keyword_researcher/data/input/
```

Example file (`urls.csv`):
```
https://yourstore.com/products/product-a
https://yourstore.com/products/product-b
https://yourstore.com/products/product-c
```

No header row needed — just URLs, one per line.

### Step 2 — Open the terminal in VS Code

Press **Ctrl + `**

### Step 3 — Navigate to the keyword_researcher folder

```
cd keyword_researcher
```

### Step 4 — Run the tool

```
python main.py --input data/input/urls.csv --output data/output/keyword_research.xlsx
```

Replace `urls.csv` with your actual filename.

### Step 5 — Wait for it to finish

The tool will show progress through three stages:
```
Loading URLs: data/input/urls.csv
  3 URLs loaded

Scraping landing pages...
  scraping: 100%|██████████| 3/3

Fetching search volumes for 85 unique candidates...

Categorizing keywords and generating ad copy...
  generating: 100%|██████████| 3/3
  3 URLs processed, 0 skipped

[excel_writer] wrote 3 sheets -> data/output/keyword_research.xlsx
```

### Step 6 — Open the output file

Your results are saved at:
```
keyword_researcher/data/output/keyword_research.xlsx
```

---

## Testing Before a Full Run

Add `--limit 2` to process only the first 2 URLs:

```
python main.py --input data/input/urls.csv --output data/output/keyword_research.xlsx --limit 2
```

---

## Understanding the Excel Output

Each product URL gets its own sheet. Within each sheet, categories are stacked vertically.

**For each category you will see:**

1. **Category name** — a thematic ad group name (e.g. "Thermogenesis Support")
2. **Keyword table** — keywords discovered from the page with average monthly search volumes
3. **Headlines table** — 15 headlines with a live character count column (must be ≤ 30 chars)
4. **Descriptions table** — 5 descriptions with a live character count column (must be ≤ 90 chars)

**Red highlighted cells** indicate a character limit was exceeded — this should not normally happen as limits are enforced automatically, but serves as a visual safety check if you manually edit copy in the sheet.

The character count column uses a live Excel formula (`=LEN()`), so if you edit any headline or description directly in the sheet, the count updates automatically.

---

## Uploading to Google Ads

1. Log in to **Google Ads** at https://ads.google.com
2. Go to **Campaigns → Ad groups → Ads**
3. Click **+ New Ad → Responsive search ad**
4. Copy headlines and descriptions from the Excel sheet into the ad builder
5. Google Ads will automatically test combinations

Each category in the Excel output corresponds to one **ad group** in Google Ads.

---

## Troubleshooting

### "No URLs found in file"
Make sure your CSV file contains full URLs starting with `https://`. Check there are no extra spaces or blank lines at the top.

### "0 URLs loaded"
The file may be empty or contain only header text. Check the file has actual URLs starting with `http`.

### Categories are empty or missing
This happens when the Claude API call fails — usually due to insufficient API credits. Check your balance at https://console.anthropic.com/settings/billing

### Search volumes are all 0
Your Google Ads developer token may not have Basic access yet. Apply at Google Ads → Tools → API Center. The tool still runs and generates ad copy — it just won't have volume data to inform categorization.

### "Module not found" error
Run `pip install -r requirements.txt` from inside the `keyword_researcher/` folder.

### Character count shows red in Excel
A headline exceeded 30 characters or a description exceeded 90. Edit the text in the cell to bring it within the limit — the count will update automatically.

---

## File Structure Reference

```
keyword_researcher/
├── main.py                      ← the program you run
├── requirements.txt             ← list of dependencies
├── MANUAL.md                    ← this file
├── config/
│   └── settings.py              ← configuration (model, limits)
├── pipeline/
│   ├── url_loader.py            ← reads your URL CSV
│   ├── scraper.py               ← visits landing pages
│   ├── keyword_planner.py       ← fetches Google search volumes
│   ├── categorizer.py           ← Claude groups keywords into themes
│   ├── ad_copy_writer.py        ← Claude writes RSA headlines + descriptions
│   └── excel_writer.py          ← writes the output Excel file
└── data/
    ├── input/                   ← put your urls.csv here
    └── output/                  ← keyword_research.xlsx appears here
```

---

## Support

For questions or issues, contact the developer (habjanicluk@gmail.com) or open an issue on GitHub at:
https://github.com/omniaceurope-sys/OMNIAC_AI
