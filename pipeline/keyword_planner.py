"""Fetch average monthly search volumes from Google Ads Keyword Planner."""

import json
import os
import sys
from math import ceil
from pathlib import Path

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from config.settings import (
    GOOGLE_ADS_CUSTOMER_ID,
    GOOGLE_ADS_LOGIN_CUSTOMER_ID,
    KEYWORD_PLANNER_BATCH,
    DEFAULT_GEO_TARGET_ID,
    DEFAULT_LANGUAGE_ID,
)

_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "cache" / "volumes_cache.json"


def _load_cache() -> dict:
    if _CACHE_PATH.exists():
        try:
            return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"[keyword_planner] Could not save cache: {exc}", file=sys.stderr)


def _build_client() -> GoogleAdsClient:
    # load_from_env() raises if use_proto_plus is absent — provide a safe default.
    os.environ.setdefault("GOOGLE_ADS_USE_PROTO_PLUS", "True")
    return GoogleAdsClient.load_from_env()


def _fetch_batch(
    client: GoogleAdsClient,
    keywords: list[str],
    customer_id: str,
    language_id: str,
    geo_target_id: str,
) -> dict[str, int]:
    keyword_plan_idea_service = client.get_service("KeywordPlanIdeaService")
    request = client.get_type("GenerateKeywordIdeasRequest")

    request.customer_id = customer_id
    request.language = client.get_service("GoogleAdsService").language_constant_path(
        language_id
    )
    request.geo_target_constants.append(
        client.get_service("GoogleAdsService").geo_target_constant_path(geo_target_id)
    )
    request.include_adult_keywords = False
    request.keyword_seed.keywords.extend(keywords)

    results = {}
    response = keyword_plan_idea_service.generate_keyword_ideas(request=request)
    for idea in response:
        kw = idea.text.lower().strip()
        volume = idea.keyword_idea_metrics.avg_monthly_searches
        results[kw] = int(volume) if volume else 0
    return results


def get_search_volumes(
    keywords: list[str],
    geo_target_id: str = DEFAULT_GEO_TARGET_ID,
    language_id: str = DEFAULT_LANGUAGE_ID,
) -> dict[str, int]:
    """Return {keyword: avg_monthly_searches} for every keyword in the list.

    Results are cached in data/cache/volumes_cache.json keyed by geo+language,
    so repeated runs skip the API for already-known keywords.
    Automatically batches requests to stay within the 100-keyword API limit.
    """
    if not keywords:
        return {}

    unique = list(dict.fromkeys(k.lower().strip() for k in keywords))

    # Load cache and check which keywords are already known for this geo/lang combo
    cache = _load_cache()
    cache_key = f"{geo_target_id}_{language_id}"
    cached_volumes: dict[str, int] = cache.get(cache_key, {})

    missing = [kw for kw in unique if kw not in cached_volumes]

    if missing:
        client = _build_client()
        customer_id = GOOGLE_ADS_CUSTOMER_ID.replace("-", "")
        n_batches = ceil(len(missing) / KEYWORD_PLANNER_BATCH)

        for i in range(n_batches):
            batch = missing[i * KEYWORD_PLANNER_BATCH : (i + 1) * KEYWORD_PLANNER_BATCH]
            batch_result = _fetch_batch(client, batch, customer_id, language_id, geo_target_id)
            cached_volumes.update(batch_result)

        # Default 0 for anything the API didn't return
        for kw in missing:
            cached_volumes.setdefault(kw, 0)

        cache[cache_key] = cached_volumes
        _save_cache(cache)

    return {kw: cached_volumes.get(kw, 0) for kw in unique}
