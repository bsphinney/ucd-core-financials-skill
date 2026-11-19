"""Usership metrics from the PPMS orders frame. Only revenue lines (accepted or completed) count."""
from __future__ import annotations

import pandas as pd

from .fiscal import complete_fys

FY_MONTHS = [7, 8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6]


def _rev(orders):
    return orders[orders["is_revenue"]]


def _aff(key, aff):
    return (aff.get(key) or {}).get("affiliation") or "Unknown"


def overview_by_fy(orders) -> list:
    out = []
    for fy, sub in _rev(orders).groupby("fy"):
        out.append({"fy": int(fy), "revenue": float(sub["price"].sum()), "orders": int(sub["order"].nunique()),
                    "groups": int(sub["group_key"].nunique()), "users": int(sub["user"].nunique())})
    return out


def mix_by_fy(orders, aff) -> list:
    r = _rev(orders).assign(aff=lambda d: d["group_key"].map(lambda k: _aff(k, aff)))
    out = []
    for fy, sub in r.groupby("fy"):
        total = sub["price"].sum()
        if total <= 0:
            continue
        row = {"fy": int(fy)}
        row.update({a: float(v / total) for a, v in sub.groupby("aff")["price"].sum().items()})
        out.append(row)
    return out


def concentration(orders) -> dict:
    s = _rev(orders).groupby("group_key")["price"].sum().sort_values(ascending=False)
    total = s.sum()
    share = lambda n: float(s.head(n).sum() / total) if total > 0 else None  # noqa: E731
    return {"top5": share(5), "top10": share(10), "top20": share(20), "n_groups": int(len(s))}


def new_vs_returning(orders) -> list:
    r = _rev(orders)
    if r.empty:
        return []
    first = r.groupby("group_key")["fy"].min()
    fys = sorted(r["fy"].unique())
    out = []
    for fy in fys[1:]:
        groups = set(r.loc[r["fy"] == fy, "group_key"])
        new = sum(1 for g in groups if first[g] == fy)
        out.append({"fy": int(fy), "new": new, "returning": len(groups) - new})
    return out


def turnaround(orders) -> dict:
    r = _rev(orders)
    r = r[r["accepted"].notna() & r["completed"].notna()].copy()
    r["days"] = (r["completed"] - r["accepted"]).dt.total_seconds() / 86400
    r = r[r["days"] >= 0]
    r = r.drop_duplicates(subset=["order", "service", "days"])
    r["svc"] = r["service_group"].where(r["service_group"] != "", r["service"])
    by_service = []
    for svc, sub in r.groupby("svc"):
        d = sub["days"]
        by_service.append({"service": svc, "median": float(d.median()), "p25": float(d.quantile(0.25)),
                           "p75": float(d.quantile(0.75)), "n": int(len(d))})
    by_service.sort(key=lambda x: -x["n"])
    by_quarter = []
    for q, sub in r.groupby(r["completed"].dt.to_period("Q")):
        by_quarter.append({"quarter": str(q), "median": float(sub["days"].median()), "n": int(len(sub))})
    by_fy = [{"fy": int(fy), "median": float(sub["days"].median()), "n": int(len(sub))}
             for fy, sub in r.groupby("fy")]
    return {"by_service": by_service, "by_quarter": by_quarter, "by_fy": by_fy}


def backlog_monthly(orders) -> list:
    r = _rev(orders)
    r = r[r["accepted"].notna()].groupby("order").agg(accepted=("accepted", "min"), completed=("completed", "max"))
    if r.empty:
        return []
    last = max(r["accepted"].max(), r["completed"].max() if r["completed"].notna().any() else r["accepted"].max())
    months = pd.period_range(r["accepted"].min().to_period("M"), last.to_period("M"), freq="M")
    out = []
    for m in months:
        end = m.to_timestamp(how="end")
        open_ = ((r["accepted"] <= end) & (r["completed"].isna() | (r["completed"] > end))).sum()
        out.append({"month": str(m), "open": int(open_)})
    return out


def orders_heatmap(orders) -> dict:
    r = _rev(orders).drop_duplicates(subset=["order"])
    fys = sorted(int(f) for f in r["fy"].unique())
    counts = [[int(((r["fy"] == fy) & (r["ordered"].dt.month == m)).sum()) for m in FY_MONTHS] for fy in fys]
    return {"fys": fys, "months": FY_MONTHS, "counts": counts}


def revenue_by_service(orders) -> list:
    r = _rev(orders)
    g = r.groupby("service").agg(revenue=("price", "sum"), orders=("order", "nunique")).reset_index()
    return [{"service": x.service, "revenue": float(x.revenue), "orders": int(x.orders)}
            for x in g.sort_values("revenue", ascending=False).itertuples()]


def top_groups(orders, aff, n: int = 20) -> list:
    r = _rev(orders)
    g = r.groupby("group_key").agg(group=("group", "first"), revenue=("price", "sum"),
                                   orders=("order", "nunique")).reset_index()
    g = g.sort_values("revenue", ascending=False).head(n)
    return [{"group": x.group, "affiliation": _aff(x.group_key, aff), "revenue": float(x.revenue),
             "orders": int(x.orders)} for x in g.itertuples()]


def unbilled(orders) -> dict:
    u = orders[orders["is_revenue"] & orders["completed"].notna() & ~orders["invoiced"]]
    lines = [{"order": x.order, "group": x.group, "service": x.service, "price": float(x.price),
              "completed": x.completed.strftime("%Y-%m-%d")} for x in u.itertuples()]
    return {"lines": lines, "total": float(u["price"].sum())}


def quotes(orders) -> dict:
    q = orders[~orders["is_revenue"]]
    return {"count": int(q["order"].nunique()), "total": float(q["price"].sum())}


def compute_usership(orders, aff) -> dict:
    return {
        "overview_by_fy": overview_by_fy(orders),
        "mix_by_fy": mix_by_fy(orders, aff),
        "concentration": concentration(orders),
        "new_vs_returning": new_vs_returning(orders),
        "turnaround": turnaround(orders),
        "backlog_monthly": backlog_monthly(orders),
        "orders_heatmap": orders_heatmap(orders),
        "revenue_by_service": revenue_by_service(orders),
        "top_groups": top_groups(orders, aff),
        "unbilled": unbilled(orders),
        "quotes": quotes(orders),
        "complete_fys": complete_fys(orders["ordered"]) if len(orders) else [],
        "revenue_total": float(_rev(orders)["price"].sum()),
    }
