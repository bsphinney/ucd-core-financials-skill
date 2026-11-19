import pandas as pd
from core_financials.fiscal import fiscal_year, fy_months, complete_fys


def test_fiscal_year_boundaries():
    assert fiscal_year(pd.Timestamp("2025-06-30")) == 2025
    assert fiscal_year(pd.Timestamp("2025-07-01")) == 2026


def test_complete_fys():
    dates = pd.Series(pd.date_range("2024-01-01", "2025-07-01", freq="MS"))
    assert complete_fys(dates) == [2025]
    m = fy_months(dates)
    assert m[2024] == {1, 2, 3, 4, 5, 6}
    assert m[2026] == {7}
