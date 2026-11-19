"""Guess each PPMS group's affiliation from its Fin Account; the user confirms in affiliations.csv."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

AFFILIATIONS = ["UC Davis", "Ext-UC", "Ext-NP", "Ext-FP", "Unknown"]
CSV_COLS = ["group", "affiliation", "college", "department", "confidence", "reason", "confirmed"]
_CONF_RANK = {"high": 3, "medium": 2, "low": 1}


def _domain_match(domain: str, d: str) -> bool:
    return domain == d or domain.endswith("." + d)


def guess(fin_account: str, coa) -> tuple:
    s = str(fin_account or "").strip()
    if s.upper().startswith("EXTERNAL"):
        m = re.search(r"@([A-Za-z0-9.\-]+)", s)
        domain = m.group(1).lower().rstrip(".") if m else ""
        if not domain:
            return "Unknown", "low", "external, no email domain"
        if _domain_match(domain, "ucdavis.edu"):
            return "UC Davis", "low", "external billing with UCD email"
        if any(_domain_match(domain, d) for d in coa.get("uc_domains", []) if d != "ucdavis.edu"):
            return "Ext-UC", "high", f"UC email domain {domain}"
        if domain.endswith((".edu", ".org", ".gov")) or ".ac." in domain or ".edu." in domain:
            return "Ext-NP", "medium", f"academic/non-profit domain {domain}"
        if domain.endswith((".com", ".bio", ".io")):
            return "Ext-FP", "medium", f"company domain {domain}"
        return "Unknown", "low", f"external domain {domain}"
    if re.fullmatch(r"\d+", s):
        return "Unknown", "low", "looks like a PO number"
    if re.match(r"^\d-[A-Z0-9]+", s) or re.match(r"^[A-Z0-9]{5,}-[A-Z0-9]+", s):
        return "UC Davis", "medium", "UC Davis chartstring"
    return "Unknown", "low", "unrecognised account"


def _vote(fins, coa) -> tuple:
    guesses = [guess(f, coa) for f in fins]
    counts: dict = {}
    for aff, conf, reason in guesses:
        c = counts.setdefault(aff, [0, 0, reason, conf])
        c[0] += 1
        if _CONF_RANK[conf] > c[1]:
            c[1], c[2], c[3] = _CONF_RANK[conf], reason, conf
    # most orders wins; Unknown only if nothing else
    ranked = sorted(counts.items(), key=lambda kv: (kv[0] != "Unknown", kv[1][0], kv[1][1]), reverse=True)
    aff, (_, _, reason, conf) = ranked[0]
    return aff, conf, reason


def _read_csv(path: Path) -> pd.DataFrame:
    if Path(path).exists():
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        for c in CSV_COLS:
            if c not in df.columns:
                df[c] = ""
        return df[CSV_COLS]
    return pd.DataFrame(columns=CSV_COLS)


def build_or_update(orders, path, coa) -> pd.DataFrame:
    from .ppms import group_key
    existing = _read_csv(path)
    have = set(existing["group"].map(group_key))
    new_rows = []
    for key, sub in orders.groupby("group_key"):
        if key in have:
            continue
        aff, conf, reason = _vote(sub["fin_account"].tolist(), coa)
        new_rows.append({"group": sub["group"].iloc[0], "affiliation": aff, "college": "", "department": "",
                         "confidence": conf, "reason": reason, "confirmed": "N"})
    df = pd.concat([existing, pd.DataFrame(new_rows, columns=CSV_COLS)], ignore_index=True)
    df.to_csv(path, index=False)
    return df


def load_affiliations(path) -> dict:
    from .ppms import group_key
    df = _read_csv(path)
    return {group_key(r["group"]): {k: r[k] for k in CSV_COLS} for _, r in df.iterrows()}
