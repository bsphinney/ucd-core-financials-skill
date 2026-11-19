import pandas as pd
import pytest

from conftest import order_row, write_orders
from core_financials import usership as U
from core_financials.ppms import load_orders


@pytest.fixture
def orders(tmp_path):
    rows = [
        order_row(1, "Alpha", 600, "2024/03/01 09:00:00", completed="2024/03/11 09:00:00", fin="3-AAA1"),
        order_row(2, "Beta", 300, "2024/09/01 09:00:00", completed="2024/09/21 09:00:00"),
        order_row(3, "Alpha", 100, "2024/10/01 09:00:00", completed="2024/10/06 09:00:00", fin="3-AAA1"),
        order_row(4, "Gamma", 100, "2025/01/05 09:00:00", completed=None, fin="EXTERNAL - x@acmebio.com"),
        order_row(5, "Delta", 900, "2025/02/01 09:00:00", accepted=None, completed=None),  # quote
        order_row(6, "Beta", 200, "2025/08/01 09:00:00", completed="2025/08/03 09:00:00", invoiced="N"),
    ]
    return load_orders([write_orders(tmp_path / "o.xlsx", rows)])


AFF = {"alpha": {"affiliation": "UC Davis", "college": "CBS", "department": "MCB"},
       "beta": {"affiliation": "Ext-UC"}, "gamma": {"affiliation": "Ext-FP"}}


def test_overview(orders):
    ov = {r["fy"]: r for r in U.overview_by_fy(orders)}
    assert ov[2024]["revenue"] == 600 and ov[2025]["revenue"] == 500 and ov[2026]["revenue"] == 200
    assert ov[2025]["groups"] == 3


def test_mix_sums_to_one(orders):
    for r in U.mix_by_fy(orders, AFF):
        assert sum(v for k, v in r.items() if k != "fy") == pytest.approx(1.0)


def test_concentration_monotonic(orders):
    c = U.concentration(orders)
    assert c["top5"] <= c["top10"] <= c["top20"] <= 1
    assert c["n_groups"] == 3


def test_new_vs_returning_hand_example(orders):
    assert U.new_vs_returning(orders) == [{"fy": 2025, "new": 2, "returning": 1},
                                          {"fy": 2026, "new": 0, "returning": 1}]


def test_turnaround(orders):
    t = U.turnaround(orders)
    svc = t["by_service"][0]
    assert svc["service"] == "Service A" and svc["n"] == 4 and svc["median"] == pytest.approx(7.5)


def test_backlog_counts_open_orders(orders):
    b = {r["month"]: r["open"] for r in U.backlog_monthly(orders)}
    assert b["2025-01"] == 1 and b["2025-06"] == 1 and b["2024-03"] == 0


def test_heatmap(orders):
    h = U.orders_heatmap(orders)
    assert h["months"] == [7, 8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6]
    assert h["counts"][h["fys"].index(2025)][h["months"].index(9)] == 1


def test_unbilled_only_completed_not_invoiced(orders):
    u = U.unbilled(orders)
    assert [l["order"] for l in u["lines"]] == ["6"] and u["total"] == 200


def test_quotes(orders):
    assert U.quotes(orders) == {"count": 1, "total": 900.0}


def test_compute_usership_keys(orders):
    out = U.compute_usership(orders, AFF)
    for k in ["overview_by_fy", "mix_by_fy", "concentration", "new_vs_returning", "turnaround", "backlog_monthly",
              "orders_heatmap", "revenue_by_service", "top_groups", "unbilled", "quotes", "complete_fys"]:
        assert k in out, k


def test_turnaround_by_fy(orders):
    t = {r["fy"]: r for r in U.turnaround(orders)["by_fy"]}
    assert t[2024]["median"] == pytest.approx(10) and t[2025]["n"] == 2


def test_turnaround_flags_orders_entered_at_billing(orders):
    assert U.turnaround(orders)["measurable"] is True
    same = orders.copy()
    same["accepted"] = same["ordered"] + pd.Timedelta(seconds=14)
    same["completed"] = same["ordered"] + pd.Timedelta(seconds=30)
    t = U.turnaround(same)
    assert t["measurable"] is False and t["same_moment_share"] == 1.0
    assert U.compute_usership(same, {})["backlog_monthly"] == []


def test_turnaround_figure_skipped_when_not_measurable(orders, cfg, tmp_path):
    from core_financials.figures import render_figures
    same = orders.copy()
    same["accepted"] = same["ordered"] + pd.Timedelta(seconds=14)
    same["completed"] = same["ordered"] + pd.Timedelta(seconds=30)
    out = render_figures(None, U.compute_usership(same, {}), cfg, tmp_path)
    assert "turnaround" not in out and "backlog" not in out
