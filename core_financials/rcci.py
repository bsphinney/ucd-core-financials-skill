"""Usership workbook, including RCCI Table 1 and Table 2 in the campus template layout."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

TABLE1_COLS = ["Core", "PI Affiliation", "PI College/School", "PI Department", "PI Name", "Spend", "Volume (orders)"]
AFF_ORDER = ["UC Davis", "Ext-UC", "Ext-NP", "Ext-FP", "Unknown"]
AFF_LABEL = {"UC Davis": "UC Davis", "Ext-UC": "Other UC campus", "Ext-NP": "External non-profit",
             "Ext-FP": "External for-profit", "Unknown": "Not yet classified"}
HEAD = Font(bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor="022851")


def _sheet(wb, title, header, rows, money_cols=(), pct_cols=()):
    ws = wb.create_sheet(title)
    ws.append(header)
    for c in ws[1]:
        c.font, c.fill = HEAD, HEAD_FILL
    for r in rows:
        ws.append(r)
    for i, h in enumerate(header, 1):
        ws.column_dimensions[get_column_letter(i)].width = max(12, min(45, len(str(h)) + 4))
        for row in ws.iter_rows(min_row=2, min_col=i, max_col=i):
            if h in money_cols:
                row[0].number_format = '"$"#,##0.00'
            if h in pct_cols:
                row[0].number_format = "0.0%"
    return ws


def _info(aff, key):
    return aff.get(key) or {}


def write_usership_workbook(orders, aff, use, cfg, path) -> Path:
    complete = set(use.get("complete_fys") or [])
    fy_lab = lambda fy: f"FY{fy}" + ("" if fy in complete else " (partial)")  # noqa: E731
    wb = Workbook()
    wb.remove(wb.active)
    _sheet(wb, "Overview", ["Fiscal year", "Revenue", "Orders", "Lab groups", "Users"],
           [[fy_lab(r["fy"]), r["revenue"], r["orders"], r["groups"], r["users"]] for r in use["overview_by_fy"]],
           money_cols=("Revenue",))
    rev = orders[orders["is_revenue"]].copy()
    rev["aff"] = rev["group_key"].map(lambda k: _info(aff, k).get("affiliation") or "Unknown")
    by_type = rev.groupby(["fy", "aff"]).agg(revenue=("price", "sum"), orders=("order", "nunique")).reset_index()
    _sheet(wb, "By customer type", ["Fiscal year", "Customer type", "Revenue", "Orders"],
           [[fy_lab(r.fy), AFF_LABEL.get(r.aff, r.aff), r.revenue, r.orders] for r in by_type.itertuples()],
           money_cols=("Revenue",))
    _sheet(wb, "Top PI groups", ["PI group", "Customer type", "Revenue", "Orders"],
           [[g["group"], AFF_LABEL.get(g["affiliation"], g["affiliation"]), g["revenue"], g["orders"]]
            for g in use["top_groups"]], money_cols=("Revenue",))
    _sheet(wb, "By service", ["Service", "Revenue", "Orders"],
           [[s["service"], s["revenue"], s["orders"]] for s in use["revenue_by_service"]], money_cols=("Revenue",))

    # RCCI tables
    win = rev
    if cfg.rcci_window:
        start, end = cfg.rcci_window
        win = rev[(rev["ordered"] >= pd.Timestamp(start)) & (rev["ordered"] < pd.Timestamp(end) + pd.Timedelta(days=1))]
    g = win.groupby("group_key").agg(group=("group", "first"), spend=("price", "sum"),
                                     volume=("order", "nunique")).reset_index()
    rows = []
    for r in g.itertuples():
        info = _info(aff, r.group_key)
        a = info.get("affiliation") or "Unknown"
        college = (info.get("college") or "Unassigned") if a == "UC Davis" else a
        rows.append({"Core": cfg.core_name, "PI Affiliation": AFF_LABEL["UC Davis"] if a == "UC Davis" else
                     AFF_LABEL.get(a, a), "PI College/School": college, "PI Department": info.get("department") or "",
                     "PI Name": r.group, "Spend": round(float(r.spend), 2), "Volume (orders)": int(r.volume),
                     "_rank": AFF_ORDER.index(a) if a in AFF_ORDER else 9})
    t1 = pd.DataFrame(rows, columns=TABLE1_COLS + ["_rank"]).sort_values(["_rank", "PI College/School", "PI Name"])
    _sheet(wb, "RCCI Table 1", TABLE1_COLS, t1[TABLE1_COLS].values.tolist(), money_cols=("Spend",))

    t2 = t1.groupby(["_rank", "PI College/School"])["Spend"].sum().reset_index().sort_values(["_rank",
                                                                                               "PI College/School"])
    ws2 = _sheet(wb, "RCCI Table 2", ["College/School or affiliation", "Spend", "% spend"],
                 [[r["PI College/School"], r["Spend"], None] for _, r in t2.iterrows()], money_cols=("Spend",))
    total_row = ws2.max_row + 1
    # total stored as a value so it reads correctly even where formulas are not recalculated
    ws2.append(["Grand Total", round(float(t2["Spend"].sum()), 2), f"=SUM(C2:C{total_row - 1})"])
    ws2.cell(total_row, 2).number_format = '"$"#,##0.00'
    for r in range(2, total_row + 1):
        if r < total_row:
            ws2.cell(r, 3).value = f"=B{r}/B${total_row}"
        ws2.cell(r, 3).number_format = "0.0%"
    for c in ws2[total_row]:
        c.font = Font(bold=True)

    unconf = [[i.get("group"), i.get("affiliation"), i.get("confidence"), i.get("reason")]
              for i in aff.values() if str(i.get("confirmed", "N")).upper() != "Y"]
    _sheet(wb, "Unconfirmed", ["PI group", "Guessed affiliation", "Confidence", "Why"], unconf)

    q = use["quotes"]
    win_txt = f"{cfg.rcci_window[0]} to {cfg.rcci_window[1]}" if cfg.rcci_window else "all dates in the export"
    notes = [
        ["Core", cfg.core_name],
        ["Source", "PPMS Order details report (line items). Revenue = Price of accepted or completed lines."],
        ["RCCI date window (Date Ordered)", win_txt],
        ["Fiscal year", "July 1 – June 30; partial years are labelled."],
        ["Unconverted quotes excluded", f"{q['count']} orders, ${q['total']:,.2f}"],
        ["Affiliations", "Guessed from Fin Account, confirmed by the core in affiliations.csv. "
                         f"{len(unconf)} groups are not yet confirmed (see the Unconfirmed sheet)."],
        ["Comparing with PPMS", "PPMS's own Usership Summary can differ by a few percent because it includes "
                                "credits and adjustments that are not order lines."],
    ]
    _sheet(wb, "Notes", ["Item", "Detail"], notes)
    wb["Notes"].column_dimensions["B"].width = 110
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    wb.save(p)
    return p
