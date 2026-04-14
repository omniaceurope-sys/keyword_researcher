"""
Loads credentials from st.secrets (Streamlit Cloud) or .env (local).
Priority: st.secrets > environment variables > .env file
"""
import os
import sys
import tempfile

from dotenv import load_dotenv

load_dotenv()


def _get(key: str) -> str | None:
    """Read a secret from st.secrets first, then fall back to env vars."""
    try:
        import streamlit as st
        val = st.secrets.get(key)
        if val:
            return str(val)
    except Exception:
        pass
    return os.getenv(key)


# Claude API
ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY")
CLAUDE_MODEL = "claude-sonnet-4-6"

# Google Ads API
GOOGLE_ADS_DEVELOPER_TOKEN = _get("GOOGLE_ADS_DEVELOPER_TOKEN")
GOOGLE_ADS_CLIENT_ID = _get("GOOGLE_ADS_CLIENT_ID")
GOOGLE_ADS_CLIENT_SECRET = _get("GOOGLE_ADS_CLIENT_SECRET")
GOOGLE_ADS_REFRESH_TOKEN = _get("GOOGLE_ADS_REFRESH_TOKEN")
GOOGLE_ADS_LOGIN_CUSTOMER_ID = _get("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
GOOGLE_ADS_CUSTOMER_ID = _get("GOOGLE_ADS_CUSTOMER_ID")

# Crawler settings
CRAWL_MAX_DEPTH = 2
CRAWL_DELAY_SECONDS = 1

# Scraper settings
KEYWORDS_PER_PAGE = 30

# Keyword Planner settings
KP_BATCH_SIZE = 20
KP_MIN_VOLUME = 10

# Output — use system temp dir so it works on Streamlit Cloud (ephemeral FS)
OUTPUT_DIR = os.path.join(tempfile.gettempdir(), "keyword_researcher_output")


def validate_env(require_google_ads: bool = True):
    """Fail fast if required credentials are missing."""
    missing = []

    if not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")

    if require_google_ads:
        google_ads_vars = {
            "GOOGLE_ADS_DEVELOPER_TOKEN": GOOGLE_ADS_DEVELOPER_TOKEN,
            "GOOGLE_ADS_CLIENT_ID": GOOGLE_ADS_CLIENT_ID,
            "GOOGLE_ADS_CLIENT_SECRET": GOOGLE_ADS_CLIENT_SECRET,
            "GOOGLE_ADS_REFRESH_TOKEN": GOOGLE_ADS_REFRESH_TOKEN,
            "GOOGLE_ADS_LOGIN_CUSTOMER_ID": GOOGLE_ADS_LOGIN_CUSTOMER_ID,
            "GOOGLE_ADS_CUSTOMER_ID": GOOGLE_ADS_CUSTOMER_ID,
        }
        for var, val in google_ads_vars.items():
            if not val:
                missing.append(var)

    if missing:
        print("ERROR: Missing required credentials:")
        for var in missing:
            print(f"  - {var}")
        print("\nAdd them to .env (local) or the Streamlit Cloud secrets dashboard.")
        sys.exit(1)
