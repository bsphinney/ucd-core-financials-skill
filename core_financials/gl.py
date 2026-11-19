"""Aggie Enterprise GL Transaction Listing: load (34-col 'page' or 58-col wide) and classify."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .fiscal import fiscal_year
from .io_util import norm_code, read_table

PAGE_SIG = {"Fund", "Account", "Journal Accounting Date", "Actuals"}
WIDE_SIG = {"Fund", "Account", "JE Accounting Date", "Accounted Net"}

PAGE_MAP = {"Fund": "fund", "Fund Description": "fund_desc", "Account": "account",
            "Account Description": "account_desc", "Journal Category": "journal_category",
            "Journal Name": "journal_name", "Accounting Period": "period", "Journal Accounting Date": "date",
            "Actuals": "amount", "Journal Line Description": "line_desc"}
WIDE_MAP = {"Fund": "fund", "Fund Description": "fund_desc", "Account": "account",
            "Account Description": "account_desc", "JE Category": "journal_category", "JE Name": "journal_name",
            "JE Accounting Period": "period", "JE Accounting Date": "date", "Accounted Net": "amount",
            "Supplier/Customer Name": "supplier", "Transaction Line Description": "line_desc"}
COLUMNS = ["fund", "fund_desc", "account", "account_desc", "journal_category", "journal_name", "period", "date",
           "amount", "supplier", "line_desc", "source_file", "layout"]
DEDUPE_KEY = ["fund", "account", "date", "amt_c", "journal_name"]


def _normalise(df: pd.DataFrame, mapping: dict, layout: str, source: str) -> pd.DataFrame:
    out = pd.DataFrame({new: df[old] if old in df.columns else "" for old, new in mapping.items()})
    for col in COLUMNS:
        if col not in out.columns:
            out[col] = ""
    out["fund"] = out["fund"].map(norm_code)
    out["account"] = out["account"].map(norm_code)
    for col in ["fund_desc", "account_desc", "journal_category", "journal_name", "period", "supplier", "line_desc"]:
        out[col] = out[col].fillna("").astype(str).str.strip()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["amount"] = pd.to_numeric(out["amount"], errors="coerce").fillna(0.0).astype(float)
    out["source_file"] = source
    out["layout"] = layout
    return out[COLUMNS]


def read_gl_file(path) -> pd.DataFrame | None:
    path = Path(path)
    df = read_table(path, PAGE_SIG)
    if df is not None:
        return _normalise(df, PAGE_MAP, "page", path.name)
    df = read_table(path, WIDE_SIG)
    if df is not None:
        return _normalise(df, WIDE_MAP, "wide", path.name)
    return None


def load_gl(paths, cfg) -> pd.DataFrame:
    frames = [f for f in (read_gl_file(p) for p in paths) if f is not None]
    if not frames:
        return pd.DataFrame(columns=COLUMNS)
    gl = pd.concat(frames, ignore_index=True)
    gl = gl[gl["date"].notna()]
    if cfg.funds:
        gl = gl[gl["fund"].isin(set(cfg.funds))]
    # The same rows pulled in two files are counted once, but genuinely repeated lines inside one
    # file are kept: number each repeat within its file, then de-duplicate on (row, repeat number).
    gl = gl.assign(amt_c=gl["amount"].round(2), _rank=(gl["layout"] != "wide").astype(int))
    full = [c for c in COLUMNS if c not in ("source_file", "amount")] + ["amt_c"]
    gl["_occ"] = gl.groupby(full + ["source_file"], dropna=False).cumcount()
    gl = gl.drop_duplicates(subset=full + ["_occ"])
    # The same transaction in both layouts: keep the wide row (it carries the supplier).
    gl["_kocc"] = gl.groupby(DEDUPE_KEY + ["layout"], dropna=False).cumcount()
    gl = gl.sort_values("_rank", kind="stable").drop_duplicates(subset=DEDUPE_KEY + ["_kocc"])
    gl = gl.drop(columns=["amt_c", "_rank", "_occ", "_kocc"]).sort_values(["date", "account"], kind="stable")
    return gl.reset_index(drop=True)


def _match_group(account: str, groups: list) -> str:
    for g in groups:
        if account in g.get("accounts", []) or any(account.startswith(p) for p in g.get("prefixes", [])):
            return g["name"]
    for g in groups:
        if g.get("catch_all"):
            return g["name"]
    return ""


def classify(gl: pd.DataFrame, cfg) -> pd.DataFrame:
    coa = cfg.coa
    gl = gl.copy()
    gl["acct_class"] = gl["account"].str[:1]
    gl["fy"] = gl["date"].map(fiscal_year).astype(int) if len(gl) else pd.Series(dtype=int)

    def role(row):
        a, c = row["account"], row["acct_class"]
        if a in coa["carryforward_accounts"]:
            return "carryforward"
        if a in coa["assessment_accounts"]:
            return "assessment"
        if a in coa["contra_accounts"]:
            return "contra"
        if c in ("4", "7"):
            return "income"
        if c == "5":
            return "expense"
        return "other"

    gl["role"] = gl.apply(role, axis=1) if len(gl) else pd.Series(dtype=str)
    rev, exp = coa["revenue_groups"], coa["expense_groups"]
    gl["group"] = [
        _match_group(a, rev) if r == "income" else _match_group(a, exp) if r == "expense" else ""
        for a, r in zip(gl["account"], gl["role"])
    ]
    return gl
