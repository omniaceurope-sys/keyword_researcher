"""
keyword_planner.py — Fetches search volumes via Google Ads Keyword Plan Idea API.
"""
import logging
import time
from typing import Any

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from config.settings import (
    GOOGLE_ADS_DEVELOPER_TOKEN,
    GOOGLE_ADS_CLIENT_ID,
    GOOGLE_ADS_CLIENT_SECRET,
    GOOGLE_ADS_REFRESH_TOKEN,
    GOOGLE_ADS_LOGIN_CUSTOMER_ID,
    GOOGLE_ADS_CUSTOMER_ID,
    KP_BATCH_SIZE,
    KP_MIN_VOLUME,
)

logger = logging.getLogger(__name__)

# Map language code to Google Ads language constant resource name
# Extend as needed
LANGUAGE_CONSTANTS = {
    "en": "languageConstants/1000",
    "de": "languageConstants/1001",
    "fr": "languageConstants/1002",
    "es": "languageConstants/1003",
    "it": "languageConstants/1004",
    "nl": "languageConstants/1010",
    "pl": "languageConstants/1030",
    "pt": "languageConstants/1014",
    "sl": "languageConstants/1039",
}

COMPETITION_MAP = {
    0: "UNKNOWN",
    1: "LOW",
    2: "MEDIUM",
    3: "HIGH",
}


def _build_client() -> GoogleAdsClient:
    config = {
        "developer_token": GOOGLE_ADS_DEVELOPER_TOKEN,
        "client_id": GOOGLE_ADS_CLIENT_ID,
        "client_secret": GOOGLE_ADS_CLIENT_SECRET,
        "refresh_token": GOOGLE_ADS_REFRESH_TOKEN,
        "login_customer_id": GOOGLE_ADS_LOGIN_CUSTOMER_ID,
        "use_proto_plus": True,
    }
    return GoogleAdsClient.load_from_dict(config)


def _competition_label(value: Any) -> str:
    """Convert competition enum value to human-readable string."""
    if hasattr(value, "name"):
        return value.name  # proto-plus enum
    return COMPETITION_MAP.get(int(value), "UNKNOWN")


@retry(
    retry=retry_if_exception_type(GoogleAdsException),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=5, max=60),
    reraise=True,
)
def _fetch_batch(
    client: GoogleAdsClient,
    customer_id: str,
    keyword_batch: list[str],
    language_constant: str,
) -> dict[str, dict]:
    """Fetch keyword ideas for one batch. Returns {keyword: {volume, competition}}."""
    keyword_plan_idea_service = client.get_service("KeywordPlanIdeaService")

    request = client.get_type("GenerateKeywordIdeasRequest")
    request.customer_id = customer_id
    request.language = language_constant
    request.keyword_plan_network = (
        client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH
    )
    request.keyword_seed.keywords.extend(keyword_batch)

    results = {}
    try:
        response = keyword_plan_idea_service.generate_keyword_ideas(request=request)
        for idea in response:
            kw = idea.text.lower().strip()
            metrics = idea.keyword_idea_metrics
            volume = metrics.avg_monthly_searches
            competition = _competition_label(metrics.competition)
            results[kw] = {"volume": volume, "competition": competition}
    except GoogleAdsException as exc:
        logger.warning(f"GoogleAdsException on batch: {exc}")
        raise

    return results


def get_search_volumes(
    keywords: list[str],
    language: str = "en",
) -> dict[str, dict]:
    """
    Given a list of keyword strings, fetch avg monthly volume + competition
    from Google Ads Keyword Planner.

    Returns dict: {keyword: {"volume": int, "competition": str}}
    Only includes keywords with volume > KP_MIN_VOLUME.
    """
    if not keywords:
        return {}

    # Deduplicate
    unique_keywords = list(dict.fromkeys(kw.lower().strip() for kw in keywords if kw.strip()))
    logger.info(f"Fetching volumes for {len(unique_keywords)} unique keywords...")

    language_constant = LANGUAGE_CONSTANTS.get(language, LANGUAGE_CONSTANTS["en"])
    customer_id = GOOGLE_ADS_CUSTOMER_ID
    client = _build_client()

    all_results: dict[str, dict] = {}

    # Process in batches
    for i in range(0, len(unique_keywords), KP_BATCH_SIZE):
        batch = unique_keywords[i: i + KP_BATCH_SIZE]
        batch_num = i // KP_BATCH_SIZE + 1
        total_batches = (len(unique_keywords) + KP_BATCH_SIZE - 1) // KP_BATCH_SIZE
        logger.info(f"  Batch {batch_num}/{total_batches} ({len(batch)} keywords)...")

        try:
            batch_results = _fetch_batch(client, customer_id, batch, language_constant)
            all_results.update(batch_results)
        except GoogleAdsException as exc:
            logger.error(f"Failed to fetch batch {batch_num} after retries: {exc}")

        # Rate limit courtesy delay
        if i + KP_BATCH_SIZE < len(unique_keywords):
            time.sleep(1)

    # Filter low-volume keywords
    filtered = {
        kw: data
        for kw, data in all_results.items()
        if data["volume"] > KP_MIN_VOLUME
    }

    logger.info(
        f"Volume fetch complete. {len(filtered)}/{len(unique_keywords)} keywords "
        f"passed volume filter (>{KP_MIN_VOLUME}/mo)."
    )
    return filtered
