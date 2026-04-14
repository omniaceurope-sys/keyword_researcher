"""
Loads environment variables and defines constants.
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Claude API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = "claude-sonnet-4-6"

# Google Ads API
GOOGLE_ADS_DEVELOPER_TOKEN = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN")
GOOGLE_ADS_CLIENT_ID = os.getenv("GOOGLE_ADS_CLIENT_ID")
GOOGLE_ADS_CLIENT_SECRET = os.getenv("GOOGLE_ADS_CLIENT_SECRET")
GOOGLE_ADS_REFRESH_TOKEN = os.getenv("GOOGLE_ADS_REFRESH_TOKEN")
GOOGLE_ADS_LOGIN_CUSTOMER_ID = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
GOOGLE_ADS_CUSTOMER_ID = os.getenv("GOOGLE_ADS_CUSTOMER_ID")

# Crawler settings
CRAWL_MAX_DEPTH = 2
CRAWL_DELAY_SECONDS = 1

# Scraper settings
KEYWORDS_PER_PAGE = 30

# Keyword Planner settings
KP_BATCH_SIZE = 20
KP_MIN_VOLUME = 10

# Output
OUTPUT_DIR = "data/output"


def validate_env(require_google_ads: bool = True):
    """Fail fast if required environment variables are missing."""
    missing = []

    if not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")

    if require_google_ads:
        google_ads_vars = [
            "GOOGLE_ADS_DEVELOPER_TOKEN",
            "GOOGLE_ADS_CLIENT_ID",
            "GOOGLE_ADS_CLIENT_SECRET",
            "GOOGLE_ADS_REFRESH_TOKEN",
            "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
            "GOOGLE_ADS_CUSTOMER_ID",
        ]
        for var in google_ads_vars:
            if not os.getenv(var):
                missing.append(var)

    if missing:
        print("ERROR: Missing required environment variables:")
        for var in missing:
            print(f"  - {var}")
        print("\nCreate a .env file in the project root with these variables.")
        sys.exit(1)
