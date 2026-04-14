"""
categorizer.py — Assigns keywords to categories using Claude Sonnet (--site mode only).
"""
import json
import logging
import time

import anthropic

from config.settings import ANTHROPIC_API_KEY, CLAUDE_MODEL

logger = logging.getLogger(__name__)

CATEGORIZATION_PROMPT = """\
You are a keyword categorization expert. Given a list of keywords with search volumes and a list of category names from an ecommerce store, assign each keyword to the single most relevant category.

Rules:
- Every keyword must be assigned to exactly one category
- Match by search intent: what would someone searching this keyword be looking to buy?
- If a keyword doesn't fit any category well, assign it to the closest match
- Return JSON format: {{"category_name": [{{"keyword": "...", "volume": N}}, ...]}}
- Sort keywords within each category by volume descending
- Return ONLY the JSON, no explanation or markdown

Categories:
{category_names}

Keywords:
{keywords_with_volumes}"""


def categorize_keywords(
    keyword_volumes: dict[str, dict],
    category_urls: list[str],
) -> dict[str, list[dict]]:
    """
    Assign keywords to the most relevant category using Claude Sonnet.

    Args:
        keyword_volumes: {keyword: {"volume": int, "competition": str}}
        category_urls: list of category page URLs (used to derive category names)

    Returns:
        {category_name: [{"keyword": str, "volume": int, "competition": str}, ...]}
    """
    if not keyword_volumes or not category_urls:
        return {}

    # Derive human-readable category names from URLs
    from urllib.parse import urlparse

    def url_to_name(url: str) -> str:
        path = urlparse(url).path.rstrip("/")
        slug = path.split("/")[-1] if "/" in path else path
        return slug.replace("-", " ").replace("_", " ").title()

    category_names = [url_to_name(u) for u in category_urls]
    # Deduplicate while preserving order
    seen = set()
    unique_category_names = []
    for name in category_names:
        if name not in seen:
            seen.add(name)
            unique_category_names.append(name)

    # Build the keywords list for the prompt
    kw_lines = []
    for kw, data in sorted(keyword_volumes.items(), key=lambda x: -x[1]["volume"]):
        kw_lines.append(f"{kw} (volume: {data['volume']})")

    # Claude has a ~200k token context but categorizing thousands of keywords
    # at once can produce unreliable JSON. Chunk if needed.
    CHUNK_SIZE = 300

    kw_items = list(keyword_volumes.items())
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    merged: dict[str, list[dict]] = {name: [] for name in unique_category_names}

    for chunk_start in range(0, len(kw_items), CHUNK_SIZE):
        chunk = kw_items[chunk_start: chunk_start + CHUNK_SIZE]
        chunk_lines = [
            f"{kw} (volume: {data['volume']})"
            for kw, data in sorted(chunk, key=lambda x: -x[1]["volume"])
        ]

        prompt = CATEGORIZATION_PROMPT.format(
            category_names="\n".join(f"- {n}" for n in unique_category_names),
            keywords_with_volumes="\n".join(chunk_lines),
        )

        for attempt in range(2):
            try:
                message = client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw = message.content[0].text.strip()

                # Strip markdown code fences if present
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                    raw = raw.strip()

                data = json.loads(raw)

                # Merge into accumulated results
                for cat_name, kw_list in data.items():
                    # Fuzzy-match category name (case-insensitive)
                    matched = cat_name
                    for name in unique_category_names:
                        if name.lower() == cat_name.lower():
                            matched = name
                            break

                    if matched not in merged:
                        merged[matched] = []

                    for entry in kw_list:
                        kw = entry.get("keyword", "")
                        vol = entry.get("volume", 0)
                        # Look up competition from original data
                        competition = keyword_volumes.get(kw.lower(), {}).get("competition", "UNKNOWN")
                        merged[matched].append({
                            "keyword": kw,
                            "volume": vol,
                            "competition": competition,
                        })
                break  # success

            except (json.JSONDecodeError, anthropic.APIError) as exc:
                if attempt == 0:
                    logger.warning(f"Categorization error (attempt 1): {exc}. Retrying...")
                    time.sleep(2)
                else:
                    logger.error(f"Categorization failed after 2 attempts: {exc}")

    # Sort each category's keywords by volume descending
    for name in merged:
        merged[name].sort(key=lambda x: -x.get("volume", 0))

    # Remove empty categories
    result = {k: v for k, v in merged.items() if v}

    logger.info(
        f"Categorized {sum(len(v) for v in result.values())} keywords "
        f"across {len(result)} categories."
    )
    return result
