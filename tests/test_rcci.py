from datetime import date

import pandas as pd
import pytest
from openpyxl import load_workbook

from core_financials.rcci import TABLE1_COLS, write_usership_workbook


@pytest.fixture(scope="module")
def wb(sample, tmp_path_factory):
    p = tmp_path_factory.mktemp("rcci") / "usership.xlsx"
    write_usership_workbook(sample["orders"], sample["aff"], sample["use"], sample["cfg"], p)
    return p


def _table(path, sheet):
    return pd.read_excel(path, sheet_name=sheet)


def test_sheets_present(wb):
    names = load_workbook(wb).sheetnames
    for s in ["Overview", "By customer type", "Top PI groups", "By service", "RCCI Table 1", "RCCI Table 2",
              "Unconfirmed", "Notes"]:
        assert s in names


def test_rcci_table1_columns_and_order(wb):
    t1 = _table(wb, "RCCI Table 1")
    assert list(t1.columns) == TABLE1_COLS
    order = {"UC Davis": 0, "Ext-UC": 1, "Ext-NP": 2, "Ext-FP": 3, "Unknown": 4}
    ranks = [order[a] for a in t1["PI College/School"].where(t1["PI Affiliation"] != "UC Davis", t1["PI Affiliation"])
             .map(lambda x: x if x in order else "UC Davis")]
    assert ranks == sorted(ranks)


def test_rcci_window_filters(sample, tmp_path):
    cfg = sample["cfg"]
    old = cfg.rcci_window
    cfg.rcci_window = (date(2024, 7, 1), date(2025, 6, 30))
    try:
        p = write_usership_workbook(sample["orders"], sample["aff"], sample["use"], cfg, tmp_path / "u.xlsx")
    finally:
        cfg.rcci_window = old
    t1 = _table(p, "RCCI Table 1")
    o = sample["orders"]
    expect = o[o["is_revenue"] & (o["fy"] == 2025)]["price"].sum()
    assert t1["Spend"].sum() == pytest.approx(expect)


def test_rcci_table2_total_equals_table1_sum(wb):
    t1 = _table(wb, "RCCI Table 1")
    t2 = _table(wb, "RCCI Table 2")
    total = t2.loc[t2.iloc[:, 0] == "Grand Total", "Spend"].iloc[0]
    assert total == pytest.approx(t1["Spend"].sum())
    ws = load_workbook(wb)["RCCI Table 2"]
    assert str(ws["C2"].value).startswith("=")
