"""Regression tests for the final whole-branch review findings."""
import shutil
import subprocess

import pandas as pd
import pytest

from conftest import (GLIDE_COLS, PAGE_COLS, PNL_COLS, SAMPLE, make_gl, order_row, page_row, write_orders,
                      write_sheet)
from core_financials import finance as F
from core_financials import SKILL_ROOT


def _net(gl, fy):
    return next(r["net"] for r in F.series(gl, "FY") if r["key"] == f"FY{fy}")


def _pnl(beginning, net, fund="12100"):
    """A P&L row in UC signs (negative = surplus) whose activity nets to `net` (surplus-positive)."""
    return {"fund": fund, "project": "P", "beginning": beginning, "revenue": -(net + 1000.0), "expense": 1000.0,
            "ending": beginning - net}


# 1. bridge beginning balance must come from the P&L's own fiscal year
def test_bridge_from_current_year_pnl_rolls_back(small_gl, cfg):
    net25, net26 = _net(small_gl, 2025), _net(small_gl, 2026)
    fin = F.compute_finance(small_gl, cfg, None, pnl=[_pnl(-10000.0, net26)])
    assert fin["bridge"]["fy"] == 2025 and fin["bridge"]["pnl_fy"] == 2026
    steps = fin["bridge"]["steps"]
    assert steps[0]["amount"] == pytest.approx(10000.0 - net25)
    assert steps[-1]["amount"] == pytest.approx(10000.0)


def test_bridge_from_same_year_pnl_and_check(small_gl, cfg):
    from core_financials.checks import run_checks
    net25 = _net(small_gl, 2025)
    fin = F.compute_finance(small_gl, cfg, None, pnl=[_pnl(-5000.0, net25)])
    assert fin["bridge"]["pnl_fy"] == 2025
    assert fin["bridge"]["steps"][0]["amount"] == pytest.approx(5000.0)
    c = [c for c in run_checks(fin, None, []) if c.name.startswith("bridge ending")]
    assert c and c[0].passed and c[0].kind == "arithmetic"


def test_bridge_unmatched_pnl_uses_zero(small_gl, cfg):
    fin = F.compute_finance(small_gl, cfg, None, pnl=[_pnl(-5000.0, 123456.0)])
    assert fin["bridge"]["pnl_fy"] is None and fin["bridge"]["steps"][0]["amount"] == 0


def test_pipeline_uses_one_pnl_filtered_to_funds(tmp_path, cfg):
    from core_financials.pipeline import pick_balances
    a = shutil.copy(SAMPLE / "pnl_fy2026.xlsx", tmp_path / "a.xlsx")
    b = shutil.copy(SAMPLE / "pnl_fy2026.xlsx", tmp_path / "b.xlsx")
    from core_financials.aggie import load_balances
    one = [r for r in load_balances(a) if r["fund"] in cfg.funds]
    rows = pick_balances([a, b], cfg)
    assert sum(r["beginning"] for r in rows) == pytest.approx(sum(r["beginning"] for r in one))
    assert all(r["fund"] in cfg.funds for r in rows)


# 2. share Sankey percentages are of gross revenue
def test_share_sankey_denominator_is_gross_revenue():
    from core_financials.figures import _share_total
    fin = {"core_node": "C", "sankey": [
        {"from": "Internal Recharge (UCD)", "to": "C", "flow": 60.0},
        {"from": "External Sales & Services", "to": "C", "flow": 40.0},
        {"from": "Draw on reserves / deficit", "to": "C", "flow": 20.0},
        {"from": "C", "to": "Salaries & Wages", "flow": 120.0}]}
    assert _share_total(fin) == 100.0


# 3. groups missing from per_dollar_buckets fall into other operating
def test_unbucketed_group_goes_to_other(small_gl, cfg):
    from core_financials.config import load_coa
    from core_financials.gl import classify
    base = F.per_dollar(small_gl, cfg, 2025)
    end0 = F.bridge(small_gl, cfg, 2025, 0)[-1]["amount"]
    cfg.coa = load_coa({"expense_groups": [
        {"name": "Salaries & Wages", "prefixes": ["500", "501"], "personnel": True},
        {"name": "Benefits", "prefixes": ["508", "505", "506"], "personnel": True},
        {"name": "Instrument Service Contracts", "accounts": ["522400"]},
        {"name": "Other Operating", "catch_all": True}]})
    gl = classify(small_gl.drop(columns=["acct_class", "fy", "role", "group"]), cfg)
    p = F.per_dollar(gl, cfg, 2025)
    parts = p["personnel"] + p["supplies_services"] + p["other_operating"] + p["assessment"] + p["surplus"]
    assert parts == pytest.approx(1.0)
    assert p["surplus"] == pytest.approx(base["surplus"])
    assert F.bridge(gl, cfg, 2025, 0)[-1]["amount"] == pytest.approx(end0)


# 4. CSV with a parameter block above the header
def test_csv_with_parameter_block(tmp_path, cfg):
    from core_financials.gl import PAGE_SIG, read_gl_file
    from core_financials.io_util import locate
    x = write_sheet(tmp_path / "g.xlsx", PAGE_COLS, [page_row("12100", "410000", "2025-03-04", -50.0)])
    df = pd.read_excel(x, dtype=str)
    p = tmp_path / "g.csv"
    p.write_text("Report,GL listing\nRun date,2025-04-01\n\n" + df.to_csv(index=False))
    assert locate(p, PAGE_SIG) == ("csv", 3)
    assert read_gl_file(p)["amount"].sum() == -50.0


# 5. duplicate handling in GLIDE and PPMS
def test_glide_same_file_twice(tmp_path):
    from core_financials.aggie import load_glide
    row = dict.fromkeys(GLIDE_COLS, "")
    row.update({"Report Type": "GL Expense", "Accounting Date": "2025-03-04", "GL Natural Account Name": "Travel",
                "Debit Amount": 100.0, "Credit Amount": 0.0})
    a = write_sheet(tmp_path / "a.xlsx", GLIDE_COLS, [row, row])
    b = shutil.copy(a, tmp_path / "b.xlsx")
    assert load_glide([a, b])["amount"].sum() == 200.0


def test_ppms_identical_lines_kept_and_overlap_counted_once(tmp_path):
    from core_financials.ppms import load_orders
    r1 = order_row("1", "Lab A", 100.0, "2025/03/04 09:00:00", completed=None)
    r2 = order_row("2", "Lab B", 50.0, "2025/03/05 09:00:00")
    old = write_orders(tmp_path / "old.xlsx", [r1, r1, r2])
    done = dict(r1, **{"Date Completed": "2025/03/20 09:00:00"})
    new = write_orders(tmp_path / "new.xlsx", [done, done, r2])
    o = load_orders([old, new])
    assert o["price"].sum() == 250.0
    assert o.loc[o["order"] == "1", "completed"].notna().all()


# 6. staff edition carries no transaction-level detail
def test_staff_edition_has_no_transactions(sample):
    from core_financials.dashboard import build_dashboard_data
    d = build_dashboard_data(sample["fin"], sample["use"], {}, [], sample["cfg"], staff=True)
    assert all(not v["transactions"] and not v.get("subledger") for v in d["fin"]["account_details"].values())


# 7. every 50xxxx account is personnel
def test_all_50_accounts_are_personnel(cfg):
    from core_financials.dashboard import build_dashboard_data
    assert cfg.personnel_prefixes == ["50"]
    gl = make_gl([("12100", "410000", "2025-03-04", -1000), ("12100", "503100", "2025-03-04", 300)], cfg)
    assert gl.loc[gl["account"] == "503100", "group"].iloc[0] == "Other Personnel"
    fin = F.compute_finance(gl, cfg, None)
    assert F.per_dollar(gl, cfg)["personnel"] == pytest.approx(0.3)
    d = build_dashboard_data(fin, None, {}, [], cfg, staff=True)
    assert "503100" not in d["fin"]["account_details"]


# 10. unquoted override codes become text
def test_coa_override_codes_become_text():
    from core_financials.config import load_coa
    c = load_coa({"assessment_accounts": [770009], "external_sales_account": 410000})
    assert c["assessment_accounts"] == ["770009"] and c["external_sales_account"] == "410000"


# 15. zip only contains tracked files
def test_zip_ignores_untracked_files(tmp_path):
    import sys
    import zipfile
    sys.path.insert(0, str(SKILL_ROOT / "tools"))
    from build_skill_zip import build_zip
    probe = SKILL_ROOT / "sample_data" / "zz_untracked_probe"
    probe.mkdir(exist_ok=True)
    (probe / "real.csv").write_text("x")
    try:
        names = zipfile.ZipFile(build_zip(SKILL_ROOT, tmp_path / "z.zip")).namelist()
    finally:
        shutil.rmtree(probe)
    assert not any("zz_untracked_probe" in n for n in names)
    assert subprocess.run(["git", "-C", str(SKILL_ROOT), "status", "--porcelain"], capture_output=True,
                          text=True).returncode == 0
