"""Other Aggie Enterprise exports: PO spend report, Department P&L (Balances), GLIDE."""
from __future__ import annotations

import re

import pandas as pd

from .fiscal import fiscal_year
from .io_util import norm_code, read_table

PO_SIG = {"Supplier Name", "Charge Account", "PO Line Distribution Amount", "PO Creation Date"}
GLIDE_SIG = {"Report Type", "GL Natural Account Name", "Debit Amount", "Credit Amount", "Accounting Date"}
PNL_SIG = {"Fund", "Project Description"}


def _code(v) -> str:
    """'522400 - Lab Supplies' -> '522400'."""
    s = norm_code(v)
    m = re.match(r"^\s*([0-9A-Za-z]+)\s*-", s)
    return m.group(1) if m else s


# ---------------------------------------------------------------- PO spend report
def load_po(paths, cfg) -> pd.DataFrame:
    frames = []
    for p in paths:
        df = read_table(p, PO_SIG)
        if df is None:
            continue
        out = pd.DataFrame({
            "supplier": df["Supplier Name"].fillna("").astype(str).str.strip(),
            "item": df.get("Item Description", pd.Series("", index=df.index)).fillna("").astype(str),
            "account": df["Charge Account"].map(_code),
            "fund": df["Charge Fund"].map(_code) if "Charge Fund" in df else "",
            "amount": pd.to_numeric(df["PO Line Distribution Amount"], errors="coerce").fillna(0.0),
            "created": pd.to_datetime(df["PO Creation Date"], errors="coerce", format="mixed"),
        })
        frames.append(out)
    if not frames:
        return pd.DataFrame(columns=["supplier", "item", "account", "fund", "amount", "created", "fy"])
    po = pd.concat(frames, ignore_index=True).drop_duplicates()
    po = po[po["created"].notna() & (po["account"] != "")]
    if cfg.funds:
        po = po[po["fund"].isin(set(cfg.funds))]
    po["fy"] = po["created"].map(fiscal_year).astype(int)
    return po.reset_index(drop=True)


def suppliers_by_account(po) -> dict:
    out: dict = {}
    for (acct, fy), sub in po.groupby(["account", "fy"]):
        s = sub.groupby("supplier")["amount"].sum().sort_values(ascending=False)
        out.setdefault(acct, {})[int(fy)] = [{"supplier": k, "amount": float(v)} for k, v in s.items()]
    return out


def supplier_concentration(po, cfg, n: int = 10) -> dict:
    nonpers = po[~po["account"].str.startswith(tuple(cfg.personnel_prefixes))]
    s = nonpers.groupby("supplier")["amount"].sum().sort_values(ascending=False)
    total = float(s.sum())
    if total <= 0:
        return {"top": [], "top_n_share": None, "n_suppliers": 0}
    top = [{"supplier": k, "share": float(v) / total} for k, v in s.head(n).items()]
    return {"top": top, "top_n_share": sum(t["share"] for t in top), "n_suppliers": int(len(s))}


def po_vs_gl(po, gl) -> list:
    posted = gl[gl["role"] == "expense"].groupby("account")["amount"].sum()
    committed = po.groupby("account")["amount"].sum()
    return [{"account": a, "po_committed": float(committed[a]), "gl_posted": float(posted[a])}
            for a in sorted(set(committed.index) & set(posted.index))]


# ---------------------------------------------------------------- Department P&L, Balances sheet
def _find(cols, prefix):
    for c in cols:
        if str(c).startswith(prefix):
            return c
    return None


def load_balances(path) -> list:
    df = read_table(path, PNL_SIG, sheet="Balances")
    if df is None:
        return []
    cols = {k: _find(df.columns, p) for k, p in
            [("beginning", "Sum of 3"), ("revenue", "Sum of 4"), ("expense", "Sum of 5"), ("ending", "Sum of Ending")]}
    if None in cols.values():
        return []
    dept = df.columns[0]
    df = df[~df[dept].astype(str).str.strip().str.lower().eq("grand total")].copy()
    df["Fund"] = df["Fund"].ffill().map(norm_code)
    rows = []
    for r in df.itertuples(index=False):
        rec = dict(zip(df.columns, r))
        rows.append({"fund": rec["Fund"], "project": str(rec.get("Project Description") or "").strip(),
                     **{k: float(pd.to_numeric(rec[c], errors="coerce") or 0.0) for k, c in cols.items()}})
    return rows


def balances_total(rows) -> dict:
    keys = ["beginning", "revenue", "expense", "ending"]
    return {k: float(sum(r[k] for r in rows)) for k in keys}


# ---------------------------------------------------------------- GLIDE (card / travel / freight)
def load_glide(paths) -> pd.DataFrame:
    """Only category, fiscal year and amount are kept; person-name columns are never read into the result."""
    frames = []
    for p in paths:
        df = read_table(p, GLIDE_SIG)
        if df is None:
            continue
        df = df[df["Report Type"].astype(str).str.strip() == "GL Expense"]
        amt = pd.to_numeric(df["Debit Amount"], errors="coerce").fillna(0.0) \
            - pd.to_numeric(df["Credit Amount"], errors="coerce").fillna(0.0)
        dates = pd.to_datetime(df["Accounting Date"], errors="coerce")
        frames.append(pd.DataFrame({
            "category": df["GL Natural Account Name"].fillna("Uncategorised").astype(str).str.strip(),
            "fy": dates.map(lambda d: fiscal_year(d) if pd.notna(d) else None),
            "amount": amt.astype(float),
        }).dropna(subset=["fy"]))
    if not frames:
        return pd.DataFrame(columns=["category", "fy", "amount"])
    g = pd.concat(frames, ignore_index=True)
    g["fy"] = g["fy"].astype(int)
    return g


def glide_by_category(glide) -> list:
    out = []
    for cat, sub in glide.groupby("category"):
        out.append({"category": cat, "amount": float(sub["amount"].sum()),
                    "by_fy": {int(k): float(v) for k, v in sub.groupby("fy")["amount"].sum().items()}})
    return sorted(out, key=lambda r: -r["amount"])
