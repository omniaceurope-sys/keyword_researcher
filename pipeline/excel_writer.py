"""Write keyword research results to an Excel workbook — one sheet per URL."""

from pathlib import Path
from urllib.parse import urlparse

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

_URL_FILL = PatternFill("solid", fgColor="1F4E79")
_URL_FONT = Font(bold=True, color="FFFFFF", size=12)
_HEADER_FONT = Font(bold=True)
_CENTER = Alignment(horizontal="center", vertical="center")


def _sheet_name(url: str, index: int, used: set) -> str:
    # Extract last non-empty path segment as the sheet name
    path_segments = [s for s in urlparse(url).path.split("/") if s]
    raw = path_segments[-1] if path_segments else f"Sheet_{index}"
    # Replace hyphens/underscores with spaces and capitalize
    name = raw.replace("-", " ").replace("_", " ").title()[:28].strip()
    if not name:
        name = f"Sheet_{index}"
    candidate, suffix = name, 2
    while candidate in used:
        candidate = f"{name[:25]} {suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def write_excel(results: list[dict], output_path: str) -> None:
    """Write one sheet per category with keywords sorted by search volume.

    Each item in results:
        {"url": str, "category": str (optional), "keywords": [{"kw": str, "volume": int}]}
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    wb.remove(wb.active)

    used_names: set = set()

    for idx, result in enumerate(results):
        url = result.get("url", f"URL_{idx}")
        # Use explicit category name if provided, else derive from URL
        if result.get("category"):
            raw = result["category"][:28].strip()
            candidate, suffix = raw, 2
            while candidate in used_names:
                candidate = f"{raw[:25]} {suffix}"
                suffix += 1
            used_names.add(candidate)
            sheet_name = candidate
        else:
            sheet_name = _sheet_name(url, idx, used_names)
        ws = wb.create_sheet(title=sheet_name)

        ws.column_dimensions["A"].width = 45
        ws.column_dimensions["B"].width = 22

        # URL header
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=2)
        cell = ws.cell(row=1, column=1, value=url)
        cell.font = _URL_FONT
        cell.fill = _URL_FILL
        cell.alignment = _CENTER
        ws.row_dimensions[1].height = 20

        # Column headers
        ws.cell(row=3, column=1, value="Keyword").font = _HEADER_FONT
        ws.cell(row=3, column=2, value="Avg Monthly Volume").font = _HEADER_FONT

        # Keywords sorted by volume (already sorted in main.py)
        for row_idx, kw_item in enumerate(result.get("keywords", []), start=4):
            ws.cell(row=row_idx, column=1, value=kw_item.get("kw", ""))
            ws.cell(row=row_idx, column=2, value=kw_item.get("volume", 0))

    if not wb.sheetnames:
        ws = wb.create_sheet(title="No Results")
        ws["A1"] = "No keywords found. Check the log for details."

    wb.save(output_path)
    print(f"[excel_writer] wrote {len(results)} sheets -> {output_path}")
