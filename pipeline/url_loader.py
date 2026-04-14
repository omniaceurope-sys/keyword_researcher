"""Load product landing page URLs from a CSV file."""

import sys
from pathlib import Path

import pandas as pd


def load_urls(csv_path: str) -> list[str]:
    """Read a CSV file and return a deduplicated list of URLs.

    Accepts files with or without a header row. Any cell value that starts
    with 'http' is treated as a URL — all others are ignored.
    """
    p = Path(csv_path)
    if not p.exists():
        raise FileNotFoundError(f"URL file not found: {csv_path}")

    df = pd.read_csv(csv_path, header=None, dtype=str)

    _IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp", ".ico")

    urls = []
    for value in df.values.flatten():
        if isinstance(value, str):
            v = value.strip()
            if v.lower().startswith("http") and not v.lower().endswith(_IMAGE_EXTS):
                urls.append(v)

    # Deduplicate, preserve order
    unique = list(dict.fromkeys(urls))

    if not unique:
        print(f"[url_loader] no URLs found in {csv_path}", file=sys.stderr)

    return unique
