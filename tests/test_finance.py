import pytest

from conftest import make_gl
from core_financials import finance as F


def test_kpis_identity(small_gl):
    k = F.kpis(small_gl)
    assert k["income"] == pytest.approx(45000 - 2250 - 40 - 25)
    assert k["expense"] == pytest.approx(12 * 2300 + 3 * 2600)
    assert k["net"] == pytest.approx(k["income"] - k["expense"])


def test_assessment_excludes_contra(small_gl, cfg):
    a = F.assessment(small_gl, cfg)
    assert a["total"] == pytest.approx(2250)
    assert a["contra_total"] == pytest.approx(40)
    assert a["by_fy"] == {2025: pytest.approx(1800), 2026: pytest.approx(450)}
    assert a["per_dollar_external"] == pytest.approx(0.15)


def test_assessment_match_rate(cfg):
    rows = []
    for i, assess in enumerate([150, 150, 149]):
        d = f"2025-0{i + 1}-10"
        rows += [("12100", "410000", d, -1000), ("12100", "775004", d, assess)]
    m = F.assessment(make_gl(rows, cfg), cfg)["match"]
    assert (m["months"], m["matched"]) == (3, 2)
    assert m["rate"] == pytest.approx(2 / 3)


def _flows(links, node):
    inflow = sum(l["flow"] for l in links if l["to"] == node)
    outflow = sum(l["flow"] for l in links if l["from"] == node)
    return inflow, outflow


def test_sankey_balances_surplus(small_gl, cfg):
    links = F.sankey(small_gl, cfg)
    i, o = _flows(links, cfg.short_name)
    assert i == pytest.approx(o, abs=0.01)
    assert any(l["to"] == "Net Surplus" for l in links)
    assert any(l["to"] == "Bad debt write-offs" for l in links)


def test_sankey_balances_deficit(cfg):
    gl = make_gl([("12100", "410000", "2025-01-10", -1000), ("12100", "500100", "2025-01-10", 1500)], cfg)
    links = F.sankey(gl, cfg)
    i, o = _flows(links, cfg.short_name)
    assert i == pytest.approx(o, abs=0.01)
    assert any(l["from"] == "Draw on reserves / deficit" for l in links)


def test_per_dollar_sums_to_one(small_gl, cfg):
    p = F.per_dollar(small_gl, cfg)
    assert sum(p.values()) == pytest.approx(1.0, abs=1e-9)
    assert p["personnel"] == pytest.approx(27900 / 45000)
    assert p["assessment"] == pytest.approx(2250 / 45000)


def test_per_dollar_deficit(cfg):
    gl = make_gl([("12100", "410000", "2025-01-10", -1000), ("12100", "500100", "2025-01-10", 1500)], cfg)
    assert F.per_dollar(gl, cfg)["surplus"] == pytest.approx(-0.5)


def test_deduction_account_is_outflow(small_gl, cfg):
    assert [d["account"] for d in F.deductions(small_gl, cfg)] == ["770006"]
    assert "770006" not in [a["account"] for g in F.revenue_groups(small_gl, cfg) for a in g["accounts"]]


def test_cost_recovery(small_gl, cfg):
    cr = F.cost_recovery_by_fy(small_gl, cfg)
    assert cr[2025] == pytest.approx(36000 / 27600)


def test_forecast(small_gl, cfg):
    f = F.forecast(small_gl, cfg)
    assert f["ytd_net"] == pytest.approx(750)
    assert f["projected"] == pytest.approx(750 + 9 * 550 - 65)
    assert f["low"] == f["high"] == pytest.approx(f["projected"])
    assert f["based_on_fys"] == [2025]
    assert f["months_seen"] == 3


def test_forecast_none_without_prior_complete_fy(cfg):
    gl = make_gl([("12100", "410000", "2025-08-10", -1000)], cfg)
    assert F.forecast(gl, cfg) is None


def test_bridge_ends_at_computed_balance(small_gl, cfg):
    steps = F.bridge(small_gl, cfg, 2025, beginning=1000)
    assert steps[0] == {"step": "Beginning balance", "amount": 1000}
    assert steps[-1]["step"] == "= Ending balance"
    assert steps[-1]["amount"] == pytest.approx(1000 + 12 * 550 - 65)
    assert steps[-1]["amount"] == pytest.approx(sum(s["amount"] for s in steps[:-1]))


def test_series_and_fund_summary(small_gl, cfg):
    fy = F.series(small_gl, "FY")
    assert [r["key"] for r in fy] == ["FY2025", "FY2026"]
    assert len(F.series(small_gl, "M")) == 15
    assert F.carryforward(small_gl) == [{"fund": "12100", "fy": 2025, "amount": -5000.0}]


def test_compute_finance_keys(small_gl, cfg):
    out = F.compute_finance(small_gl, cfg, balances_beginning=None)
    for k in ["kpis", "revenue_groups", "expense_groups", "deductions", "assessment", "sankey", "per_dollar",
              "cost_recovery_by_fy", "series_fy", "series_month", "series_by_fund", "fund_summary", "carryforward",
              "balance_series", "bridge", "forecast", "top_revenue", "top_expense", "account_details",
              "complete_fys", "all_fys", "gross_total", "deductions_total", "contra_total"]:
        assert k in out, k
    assert out["complete_fys"] == [2025]


def test_account_detail_includes_subledger_lines(small_gl, cfg):
    import pandas as pd
    sub = pd.DataFrame([{"account": "522400", "date": pd.Timestamp("2025-01-10"), "supplier": "ACME",
                         "line_desc": "tips", "amount": 120.0, "fund": "12100"}])
    out = F.compute_finance(small_gl, cfg, balances_beginning=None, subledger=sub)
    lines = out["account_details"]["522400"]["subledger"]
    assert lines == [{"date": "2025-01-10", "supplier": "ACME", "line": "tips", "amount": 120.0}]
    assert out["account_details"]["500100"]["subledger"] == []


def test_assessment_match_uses_month_named_in_journal_and_skips_unposted(cfg):
    """Real AE: February's assessment posts on 31 March, named 'Campus Income Assessment - February 2024'."""
    from conftest import make_gl
    gl = make_gl([("12100", "410000", "2024-02-10", -1000), ("12100", "410000", "2024-03-10", -2000),
                  ("12100", "770009", "2024-03-31", 150), ("12100", "770009", "2024-03-31", 300),
                  ("12100", "410000", "2024-04-10", -500)], cfg)
    gl.loc[gl["account"] == "770009", "journal_name"] = ["Campus Income Assessment - February 2024 X",
                                                         "Campus Income Assessment - March 2024 X"]
    m = F.assessment(gl, cfg)["match"]
    assert (m["months"], m["matched"]) == (2, 2)
    assert m["not_yet_posted"] == ["2024-04"]


def test_forecast_needs_three_months(small_gl, cfg):
    two = small_gl[small_gl["date"] < "2025-09-01"]
    assert F.forecast(two, cfg) is None
    assert F.forecast(small_gl, cfg)["months_seen"] == 3
