"""Find which reports are in a folder, what dates they cover, and what is still needed."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import aggie, gl as glmod, ppms
from .io_util import locate

KINDS = {
    "gl_page": (glmod.PAGE_SIG, None),
    "gl_wide": (glmod.WIDE_SIG, None),
    "po_spend": (aggie.PO_SIG, None),
    "pnl_balances": (aggie.PNL_SIG, "Balances"),
    "glide": (aggie.GLIDE_SIG, None),
    "ppms_orders": (ppms.ORDERS_SIG, None),
}
NAMES = {
    "gl_page": "GL Transaction Listing (standard export)",
    "gl_wide": "GL and Subledger Detail (wide export with suppliers)",
    "po_spend": "PO spend report (UCD Comprehensive Spend Report)",
    "pnl_balances": "Department P&L with Balances tab",
    "glide": "GLIDE report",
    "ppms_orders": "PPMS Order details report",
}
ADDS = {
    "gl": "the whole financial dashboard: income and expense, campus assessment, Sankey, per-$1 split, "
          "cost recovery, fund balance, forecast",
    "po_spend": "which companies were paid, for each expense account, and supplier concentration",
    "pnl_balances": "the official fund balances table and the bridge chart's beginning balance",
    "glide": "card, travel and freight spending by category",
    "ppms_orders": "every usership figure, the RCCI tables, turnaround, backlog and the unbilled-orders check",
}
DATA_EXT = {".xlsx", ".xls", ".csv"}


def detect(path) -> str | None:
    path = Path(path)
    if path.suffix.lower() not in DATA_EXT or path.name.startswith(("~$", ".")):
        return None
    for kind, (sig, sheet) in KINDS.items():
        try:
            if locate(path, sig, sheet) is not None:
                return kind
        except Exception:
            continue
    return None


def _coverage(path, kind):
    if kind in ("gl_page", "gl_wide"):
        df = glmod.read_gl_file(path)
        dates = df["date"] if df is not None else pd.Series(dtype="datetime64[ns]")
    elif kind == "po_spend":
        df = aggie.read_table(path, aggie.PO_SIG)
        dates = pd.to_datetime(df["PO Creation Date"], errors="coerce", format="mixed")
    elif kind == "glide":
        df = aggie.read_table(path, aggie.GLIDE_SIG)
        dates = pd.to_datetime(df["Accounting Date"], errors="coerce")
    elif kind == "ppms_orders":
        df = ppms.load_orders([path])
        dates = df["ordered"]
    else:
        return None, None, len(aggie.load_balances(path)), []
    dates = pd.to_datetime(dates, errors="coerce").dropna()
    if dates.empty:
        return None, None, 0, []
    months = sorted({d.strftime("%Y-%m") for d in dates})
    return dates.min().strftime("%Y-%m-%d"), dates.max().strftime("%Y-%m-%d"), int(len(dates)), months


def scan(folder) -> list:
    out = []
    for p in sorted(Path(folder).iterdir()):
        if not p.is_file() or p.suffix.lower() not in DATA_EXT or p.name == "affiliations.csv":
            continue
        kind = detect(p)
        rec = {"path": str(p), "file": p.name, "kind": kind, "start": None, "end": None, "rows": 0, "months": []}
        if kind:
            rec["start"], rec["end"], rec["rows"], rec["months"] = _coverage(p, kind)
        out.append(rec)
    return out


def _label(ym: str) -> str:
    return pd.Period(ym, "M").strftime("%b-%Y")


def reports_needed_md(inv, cfg) -> str:
    kinds = {r["kind"] for r in inv if r["kind"]}
    dept = cfg.financial_department or "<your Financial Department code>"
    funds = ", ".join(cfg.funds) or "<your funds>"
    lines = [f"# Reports still needed — {cfg.core_name}", ""]
    lines += ["## What is in the folder", "", "| File | Report | Covers | Rows |", "|---|---|---|---|"]
    for r in inv:
        name = NAMES.get(r["kind"], "not recognised")
        cover = f"{r['start']} → {r['end']}" if r["start"] else "—"
        lines.append(f"| {r['file']} | {name} | {cover} | {r['rows']} |")
    lines.append("")
    todo = []
    has_gl = bool(kinds & {"gl_page", "gl_wide"})
    if not has_gl:
        todo.append(("GL Transaction Listing", ADDS["gl"]))
    for k in ["po_spend", "pnl_balances", "glide", "ppms_orders"]:
        if k not in kinds:
            todo.append((NAMES[k], ADDS[k]))
    gaps = []
    if has_gl:
        gl_kind = "gl_page" if "gl_page" in kinds else "gl_wide"
        months = sorted({m for r in inv if r["kind"] == gl_kind for m in r["months"]})
        if months:
            full = pd.period_range(months[0], months[-1], freq="M").strftime("%Y-%m")
            missing = [m for m in full if m not in set(months)]
            if missing:
                gaps.append("GL Transaction Listing is missing these months: "
                            + ", ".join(_label(m) for m in missing) + ". Pull them so totals are complete.")
        gl_end = max(pd.Timestamp(r["end"]) for r in inv if r["kind"] in ("gl_page", "gl_wide") and r["end"])
        for r in inv:
            if r["kind"] == "po_spend" and r["end"] and (gl_end - pd.Timestamp(r["end"])).days > 60:
                gaps.append(f"PO spend report ends {r['end']} but the ledger runs to {gl_end:%Y-%m-%d}: "
                            "re-run it through today so supplier detail covers the same period.")
    lines.append("## Still needed")
    lines.append("")
    if not todo and not gaps:
        lines.append("All six report types are present and their dates line up. Nothing else to pull.")
    else:
        if not todo:
            lines.append("All six report types are present.")
        for name, adds in todo:
            lines.append(f"- **{name}** — adds {adds}.")
        for g in gaps:
            lines.append(f"- {g}")
        lines += ["", "## Request you can send to your finance staff", "",
                  f"> For **Financial Department {dept}**, funds **{funds}**, could you please export:"]
        for name, _ in todo:
            lines.append(f"> - the {name}")
        for g in gaps:
            lines.append(f"> - {g}")
        lines.append("> as Excel files? Thank you.")
    lines += ["", "Step-by-step instructions for each report are in `reference/pulling-reports.md`."]
    return "\n".join(lines) + "\n"
