import pandas as pd

from conftest import order_row, write_orders
from core_financials.ppms import load_orders


def test_dates_parsed_from_strings_and_blanks(tmp_path):
    p = write_orders(tmp_path / "o.xlsx", [order_row(1, "Kim Lab", 100, "2022/09/27 09:41:18", completed=None)])
    o = load_orders([p])
    assert o.loc[0, "ordered"] == pd.Timestamp("2022-09-27 09:41:18")
    assert pd.isna(o.loc[0, "completed"])
    assert o.loc[0, "fy"] == 2023


def test_is_revenue_rule(tmp_path):
    p = write_orders(tmp_path / "o.xlsx", [
        order_row(1, "A", 100, "2025/01/02 10:00:00"),
        order_row(2, "A", 50, "2025/01/02 10:00:00", accepted=None, completed=None),
        order_row(3, "A", 70, "2025/01/02 10:00:00", accepted=None, completed="2025/01/09 10:00:00")])
    assert list(load_orders([p])["is_revenue"]) == [True, False, True]


def test_group_key_casefold(tmp_path):
    p = write_orders(tmp_path / "o.xlsx", [order_row(1, "Kim Lab", 1, "2025/01/02 10:00:00"),
                                           order_row(2, "kim lab ", 1, "2025/01/02 10:00:00")])
    assert load_orders([p])["group_key"].nunique() == 1


def test_invoiced_parsed(tmp_path):
    p = write_orders(tmp_path / "o.xlsx", [order_row(1, "A", 1, "2025/01/02 10:00:00", invoiced="N")])
    assert list(load_orders([p])["invoiced"]) == [False]
