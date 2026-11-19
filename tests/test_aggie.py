import json

import pandas as pd
import pytest

from conftest import (GLIDE_COLS, PNL_COLS, PO_COLS, PO_PREAMBLE, make_gl, po_row, write_sheet)
from core_financials import aggie as A


def _po(tmp_path, rows):
    return write_sheet(tmp_path / "po.xlsx", PO_COLS, rows, sheet="Sheet1", preamble=PO_PREAMBLE)


def test_po_header_row_12_and_code_parsing(tmp_path, cfg):
    p = _po(tmp_path, [po_row("ACME", "522400", "12100", 100.0, created="12-19-2023")])
    po = A.load_po([p], cfg)
    assert po.loc[0, "account"] == "522400"
    assert po.loc[0, "fund"] == "12100"
    assert po.loc[0, "fy"] == 2024


def test_po_filtered_to_funds(tmp_path, cfg):
    p = _po(tmp_path, [po_row("ACME", "522400", "12100", 100.0), po_row("ACME", "522400", "20700", 7.0)])
    assert list(A.load_po([p], cfg)["fund"]) == ["12100"]


def test_suppliers_and_concentration(tmp_path, cfg):
    p = _po(tmp_path, [po_row("ACME", "522400", "12100", 300.0), po_row("BETA", "522400", "12100", 100.0),
                       po_row("GAMMA", "530102", "12100", 100.0), po_row("PAYROLL", "500100", "12100", 900.0)])
    po = A.load_po([p], cfg)
    s = A.suppliers_by_account(po)
    assert s["522400"][2025][0] == {"supplier": "ACME", "amount": 300.0}
    c = A.supplier_concentration(po, cfg, n=2)
    assert [t["supplier"] for t in c["top"]] == ["ACME", "BETA"]
    assert c["top_n_share"] == pytest.approx(0.8)
    assert sum(t["share"] for t in c["top"]) <= 1


def test_po_vs_gl(tmp_path, cfg):
    po = A.load_po([_po(tmp_path, [po_row("ACME", "532302", "12100", 900.0)])], cfg)
    gl = make_gl([("12100", "532302", "2025-03-10", 300.0)], cfg)
    assert A.po_vs_gl(po, gl) == [{"account": "532302", "po_committed": 900.0, "gl_posted": 300.0}]


def test_balances_forward_fill_and_grand_total_dropped(tmp_path):
    rows = [dict(zip(PNL_COLS, r)) for r in [
        ["XTST001", "12100", "OTHER PROJECT", 0, 376, -376, 0],
        [None, None, "TEST CORE", 5000, -400000, 380000, -15000],
        ["XTST001", "16200", "TEST CORE", -20000, 0, 0, -20000],
        ["Grand Total", None, None, -15000, -399624, 379624, -35000]]]
    p = write_sheet(tmp_path / "pnl.xlsx", PNL_COLS, rows, sheet="Balances")
    b = A.load_balances(p)
    assert [(r["fund"], r["project"]) for r in b] == [("12100", "OTHER PROJECT"), ("12100", "TEST CORE"),
                                                     ("16200", "TEST CORE")]
    t = A.balances_total(b)
    assert t["ending"] == pytest.approx(-35000)
    assert t["beginning"] == pytest.approx(-15000)


def test_glide_drops_name_columns(tmp_path):
    rows = [{"Report Type": "GL Expense", "Accounting Date": pd.Timestamp("2025-08-01").to_pydatetime(),
             "GL Natural Account Name": "Travel - Domestic", "Debit Amount": 120.0, "Credit Amount": None,
             "udfString1": "Jane Traveler", "PPM Comment": "Jane Traveler trip"},
            {"Report Type": "GL Revenue", "Accounting Date": pd.Timestamp("2025-08-01").to_pydatetime(),
             "GL Natural Account Name": "Sales", "Debit Amount": None, "Credit Amount": 50.0}]
    p = write_sheet(tmp_path / "glide.xlsx", GLIDE_COLS, rows)
    g = A.load_glide([p])
    assert list(g.columns) == ["category", "fy", "amount"]
    cats = A.glide_by_category(g)
    assert cats == [{"category": "Travel - Domestic", "amount": 120.0, "by_fy": {2026: 120.0}}]
    assert "jane" not in json.dumps(cats).lower()
