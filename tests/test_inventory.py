import shutil

import pandas as pd
from openpyxl import load_workbook

from conftest import SAMPLE
from core_financials.config import load_config
from core_financials.inventory import detect, reports_needed_md, scan

EXPECTED = {"gl_page_2024-01_to_2026-09.xlsx": "gl_page", "gl_wide_2025-03.xlsx": "gl_wide",
            "po_spend_2023-12_to_2026-04.xlsx": "po_spend", "pnl_fy2026.xlsx": "pnl_balances",
            "glide_fy2026.xlsx": "glide", "ppms_order_details.xlsx": "ppms_orders"}


def test_detect_each_sample_file():
    for name, kind in EXPECTED.items():
        assert detect(SAMPLE / name) == kind, name


def test_scan_reports_coverage():
    inv = {r["kind"]: r for r in scan(SAMPLE)}
    assert inv["gl_page"]["start"] == "2024-01-02" or inv["gl_page"]["start"].startswith("2024-01")
    assert inv["gl_page"]["end"].startswith("2026-09")
    assert inv["ppms_orders"]["rows"] > 100


def _drop_month(src, dst, year, month):
    wb = load_workbook(src)
    ws = wb["page"]
    header = [c.value for c in ws[1]]
    col = header.index("Journal Accounting Date") + 1
    for row in range(ws.max_row, 1, -1):
        v = ws.cell(row, col).value
        if v is not None and v.year == year and v.month == month:
            ws.delete_rows(row)
    wb.save(dst)


def test_reports_needed_lists_missing_po_and_gl_gap(tmp_path):
    for f in SAMPLE.iterdir():
        if f.name not in ("po_spend_2023-12_to_2026-04.xlsx", "gl_page_2024-01_to_2026-09.xlsx"):
            shutil.copy(f, tmp_path / f.name)
    _drop_month(SAMPLE / "gl_page_2024-01_to_2026-09.xlsx", tmp_path / "gl.xlsx", 2025, 3)
    cfg = load_config(tmp_path / "core-config.yaml")
    text = reports_needed_md(scan(tmp_path), cfg)
    assert "PO spend report" in text
    assert "Mar-2025" in text
    assert "XIMG001" in text


def test_reports_needed_none_missing(tmp_path):
    cfg = load_config(SAMPLE / "core-config.yaml")
    text = reports_needed_md(scan(SAMPLE), cfg)
    assert "All six report types are present" in text
