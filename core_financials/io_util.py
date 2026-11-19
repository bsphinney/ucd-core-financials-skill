"""Reading exports whose header row may sit below a parameter block."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def norm_code(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    s = str(x).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def _clean(v) -> str:
    return str(v).strip() if v is not None else ""


def _sheets(path: Path) -> list[str]:
    if path.suffix.lower() == ".xls":
        import xlrd
        return xlrd.open_workbook(str(path), on_demand=True).sheet_names()
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True)
    names = wb.sheetnames
    wb.close()
    return names


def _head_rows(path: Path, sheet: str, max_rows: int) -> list[list[str]]:
    if path.suffix.lower() == ".xls":
        import xlrd
        sh = xlrd.open_workbook(str(path), on_demand=True).sheet_by_name(sheet)
        return [[_clean(v) for v in sh.row_values(i)] for i in range(min(max_rows, sh.nrows))]
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, header=None, nrows=max_rows, dtype=str, keep_default_na=False)
        return [[_clean(v) for v in row] for row in df.values.tolist()]
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True)
    out = []
    for i, row in enumerate(wb[sheet].iter_rows(values_only=True)):
        if i >= max_rows:
            break
        out.append([_clean(v) for v in row])
    wb.close()
    return out


def find_header_row(path, sheet, signature: set[str], max_rows: int = 60) -> int | None:
    sig = {s.strip() for s in signature}
    for i, row in enumerate(_head_rows(Path(path), sheet, max_rows)):
        if sig <= set(row):
            return i
    return None


def locate(path, signature: set[str], sheet: str | None = None) -> tuple[str, int] | None:
    """Return (sheet, header_row) of the first sheet whose header contains every signature column."""
    path = Path(path)
    sheets = [sheet] if sheet else (["csv"] if path.suffix.lower() == ".csv" else _sheets(path))
    for sh in sheets:
        try:
            row = find_header_row(path, sh, signature)
        except Exception:
            continue
        if row is not None:
            return sh, row
    return None


def read_table(path, signature: set[str], sheet: str | None = None) -> pd.DataFrame | None:
    path = Path(path)
    found = locate(path, signature, sheet)
    if found is None:
        return None
    sh, row = found
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, header=row, dtype=object)
    else:
        engine = "xlrd" if path.suffix.lower() == ".xls" else "openpyxl"
        df = pd.read_excel(path, sheet_name=sh, header=row, dtype=object, engine=engine)
    df.columns = [str(c).strip() for c in df.columns]
    return df.dropna(how="all")
