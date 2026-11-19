"""PPMS (Stratocore) Order details report -> normalised orders frame."""
from __future__ import annotations

import pandas as pd

from .fiscal import fiscal_year
from .io_util import read_table

ORDERS_SIG = {"Order Number", "Group", "Fin Account", "Price", "Date Ordered"}
COLUMNS = ["order", "user", "group", "group_key", "fin_account", "service", "service_group", "unit_price", "qty",
           "price", "invoiced", "ordered", "accepted", "completed", "assigned_to", "fy", "is_revenue"]


def group_key(name) -> str:
    return " ".join(str(name or "").casefold().split())


def _dates(s):
    return pd.to_datetime(s.replace({"": None}), errors="coerce", format="mixed")


def _col(df, name, default=""):
    return df[name] if name in df.columns else pd.Series(default, index=df.index)


def load_orders(paths) -> pd.DataFrame:
    frames = []
    for p in paths:
        df = read_table(p, ORDERS_SIG)
        if df is None:
            continue
        inv_col = next((c for c in df.columns if str(c).startswith("Invoiced")), None)
        o = pd.DataFrame({
            "order": df["Order Number"].map(lambda v: str(int(v)) if isinstance(v, float) and v.is_integer()
                                            else str(v).strip()),
            "user": _col(df, "User").fillna("").astype(str).str.strip(),
            "group": df["Group"].fillna("").astype(str).str.strip(),
            "fin_account": df["Fin Account"].fillna("").astype(str).str.strip(),
            "service": _col(df, "Service Name").fillna("").astype(str).str.strip(),
            "service_group": _col(df, "Service Group").fillna("").astype(str).str.strip(),
            "unit_price": pd.to_numeric(_col(df, "Unit price", 0), errors="coerce").fillna(0.0),
            "qty": pd.to_numeric(_col(df, "Quantity ordered", 0), errors="coerce").fillna(0.0),
            "price": pd.to_numeric(df["Price"], errors="coerce").fillna(0.0),
            "invoiced": (df[inv_col].astype(str).str.strip().str.upper().str.startswith("Y") if inv_col
                         else pd.Series(True, index=df.index)),
            "ordered": _dates(df["Date Ordered"]),
            "accepted": _dates(_col(df, "Date Accepted", None)),
            "completed": _dates(_col(df, "Date Completed", None)),
            "assigned_to": _col(df, "Assigned to").fillna("").astype(str).str.strip(),
        })
        frames.append(o)
    if not frames:
        return pd.DataFrame(columns=COLUMNS)
    o = pd.concat(frames, ignore_index=True).drop_duplicates()
    o = o[o["ordered"].notna() & (o["group"] != "")].copy()
    o["group_key"] = o["group"].map(group_key)
    # one display spelling per group: the most common one
    display = o.groupby("group_key")["group"].agg(lambda s: s.value_counts().index[0])
    o["group"] = o["group_key"].map(display)
    o["fy"] = o["ordered"].map(fiscal_year).astype(int)
    o["is_revenue"] = o["accepted"].notna() | o["completed"].notna()
    return o[COLUMNS].reset_index(drop=True)
