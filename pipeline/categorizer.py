"""Assign keywords to product categories using Claude."""

import json
import sys

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config.settings import ANTHROPIC_API_KEY, CLAUDE_MODEL

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_SYSTEM_PROMPT = """\
You are a Google Ads keyword strategist. Your job is to assign each keyword \
to the most relevant product category.

Rules:
- Assign EVERY keyword to exactly one category.
- Base your decision on the search intent behind the keyword, not just word matching.
  Example: "odstranjevanje vodnega kamna" → "kopalnica" (bathroom limescale removal)
  Example: "čiščenje žara" → "kuhinja" or "ciscenje" (grill cleaning)
  Example: "mikro krpa za tla" → "tla" (floor microfiber cloth)
- If a keyword fits multiple categories, pick the most specific one.
- If a keyword doesn't fit any category well, assign it to the most general one.
- Respond ONLY with a valid JSON object mapping keyword → category name.
  No markdown, no explanation.
- Example: {"čistilo za kopalnico": "Kopalnica", "čiščenje oken": "Steklo"}
"""


@retry(
    retry=retry_if_exception_type(anthropic.APIError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    reraise=True,
)
def _call_claude(user_message: str) -> str:
    message = _client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=8096,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    return message.content[0].text


def assign_keywords_to_categories(
    keyword_volumes: dict[str, int],
    categories: list[str],
) -> dict[str, list[dict]]:
    """Assign keywords to categories using Claude.

    Args:
        keyword_volumes: {keyword: volume} — all keywords with their volumes
        categories: list of category names (e.g. ["Kopalnica", "Steklo", "Kuhinja"])

    Returns:
        {category_name: [{"kw": str, "volume": int}]} sorted by volume desc
    """
    if not keyword_volumes or not categories:
        return {}

    kw_list = "\n".join(
        f"{kw} (volume: {vol})"
        for kw, vol in sorted(keyword_volumes.items(), key=lambda x: x[1], reverse=True)
    )
    user_message = (
        f"Categories: {', '.join(categories)}\n\n"
        f"Assign each keyword to its most relevant category:\n{kw_list}"
    )

    try:
        raw = _call_claude(user_message).strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        assignments: dict[str, str] = json.loads(raw)
    except (anthropic.APIError, json.JSONDecodeError) as exc:
        print(f"[categorizer] failed: {exc}", file=sys.stderr)
        # Fallback: assign all to first category
        assignments = {kw: categories[0] for kw in keyword_volumes}

    # Group by category, sorted by volume
    result: dict[str, list[dict]] = {cat: [] for cat in categories}
    for kw, cat in assignments.items():
        if cat not in result:
            # Claude returned an unknown category — find closest match
            cat = next((c for c in categories if c.lower() in cat.lower() or cat.lower() in c.lower()), categories[0])
        vol = keyword_volumes.get(kw, 0)
        result[cat].append({"kw": kw, "volume": vol})

    # Sort each category by volume desc, remove empty
    return {
        cat: sorted(kws, key=lambda x: x["volume"], reverse=True)
        for cat, kws in result.items()
        if kws
    }
