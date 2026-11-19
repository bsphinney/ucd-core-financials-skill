"""UC fiscal year: July 1 - June 30. FY2026 = 2025-07-01 .. 2026-06-30."""
import pandas as pd


def fiscal_year(ts) -> int:
    ts = pd.Timestamp(ts)
    return ts.year + 1 if ts.month >= 7 else ts.year


def fy_months(dates: pd.Series) -> dict:
    out: dict[int, set[int]] = {}
    for d in pd.to_datetime(pd.Series(dates)).dropna():
        out.setdefault(fiscal_year(d), set()).add(d.month)
    return out


def complete_fys(dates) -> list:
    return sorted(fy for fy, months in fy_months(dates).items() if len(months) == 12)
