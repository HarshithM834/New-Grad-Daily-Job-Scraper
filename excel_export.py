"""Portable Excel snapshot for CareerOps output destinations.

Optional dependency: artifact_tool. Values are exported as literals; spreadsheet
formulas from untrusted job text are escaped before writing.
"""
from __future__ import annotations

from pathlib import Path

COLUMNS = ["Company", "Role", "Link", "Location", "Stage", "To-do", "Notes"]


def safe_excel_text(value) -> str:
    text = str(value or "").strip()
    return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text


def make_xlsx(jobs: list[dict[str, str]], path: Path) -> dict:
    """Create one legible XLSX workbook with frozen column names and no macros."""
    try:
        from artifact_tool import Workbook, SpreadsheetFile
    except ImportError as exc:
        raise RuntimeError("Excel export requires the optional artifact_tool package") from exc
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook.create()
    sheet = wb.worksheets.add("Jobs")
    sheet.get_range("A1:G1").values = [COLUMNS]
    # Use chunked writes so very large curated feeds do not require a giant payload.
    for start in range(0, len(jobs), 200):
        batch = jobs[start:start + 200]
        rows = [[safe_excel_text(row.get(k, "")) for k in COLUMNS] for row in batch]
        sheet.get_range_by_indexes(start + 1, 0, len(rows), len(COLUMNS)).values = rows
    sheet.get_range("A1:G1").format = {
        "fill": "#172033", "font": {"bold": True, "color": "#FFFFFF"},
        "row_height": 26, "vertical_alignment": "center",
    }
    for column, width in zip("ABCDEFG", (23, 41, 56, 27, 22, 13, 37)):
        sheet.get_range(f"{column}:{column}").format.column_width = width
    sheet.freeze_panes.freeze_rows(1)
    SpreadsheetFile.export_xlsx(wb).save(str(path))
    return {"rows": len(jobs), "file": path.name}