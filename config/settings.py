import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

# Anthropic
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
CLAUDE_MODEL = "claude-sonnet-4-6"

# Google Ads API
GOOGLE_ADS_DEVELOPER_TOKEN = os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"]
GOOGLE_ADS_LOGIN_CUSTOMER_ID = os.environ["GOOGLE_ADS_LOGIN_CUSTOMER_ID"]
GOOGLE_ADS_CUSTOMER_ID = os.environ["GOOGLE_ADS_CUSTOMER_ID"]

# Scraper
SCRAPER_TIMEOUT = 10  # seconds
TOP_KEYWORDS_PER_URL = 30

# Keyword planner
KEYWORD_PLANNER_BATCH = 20
DEFAULT_GEO_TARGET_ID = "2705"   # Slovenia
DEFAULT_LANGUAGE_ID = "1023"     # Slovenian
MIN_SEARCH_VOLUME = 10
