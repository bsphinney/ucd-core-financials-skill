"""Financial metrics from the classified GL frame (debit-positive `amount`).

Income = -amount for roles income/assessment/contra; expense = amount for role expense.
Carry-forward (class 3) and other classes never enter operating figures.
"""
from __future__ import annotations

import re

import pandas as pd

from .fiscal import complete_fys

OPERATING = ("income", "assessment", "contra", "expense")
DEFICIT_NODE = "Draw on reserves / deficit"
SURPLUS_NODE = "Net Surplus"
ASSESS_NODE = "Campus Assessment"
CONTRA_NODE = "Bad debt write-offs"
DEDUCT_NODE = "Recharges & deductions"


def _op(gl):
    return gl[gl["role"].isin(OPERATING)]


def _income(gl):
    return float(-gl.loc[gl["role"].isin(["income", "assessment", "contra"]), "amount"].sum())


def _expense(gl):
    return float(gl.loc[gl["role"] == "expense", "amount"].sum())


def kpis(gl) -> dict:
    inc, exp = _income(gl), _expense(gl)
    return {"income": inc, "expense": exp, "net": inc - exp}


def _accounts(gl, role, sign):
    sub = gl[gl["role"] == role]
    if sub.empty:
        return pd.DataFrame(columns=["account", "desc", "group", "amount"])
    agg = sub.groupby("account").agg(desc=("account_desc", "first"), group=("group", "first"),
                                     amount=("amount", "sum")).reset_index()
    agg["amount"] = sign * agg["amount"]
    return agg


def _by_fy(sub, sign):
    return {int(k): float(sign * v) for k, v in sub.groupby("fy")["amount"].sum().items()}


def _group_list(gl, accts, role, sign, order):
    out = []
    for name in order:
        rows = accts[accts["group"] == name]
        if rows.empty:
            continue
        sub = gl[(gl["role"] == role) & gl["account"].isin(rows["account"])]
        out.append({
            "name": name,
            "amount": float(rows["amount"].sum()),
            "accounts": [{"account": r.account, "desc": r.desc, "amount": float(r.amount)}
                         for r in rows.sort_values("amount", ascending=False).itertuples()],
            "by_fy": _by_fy(sub, sign),
        })
    return out


def revenue_groups(gl, cfg) -> list:
    accts = _accounts(gl, "income", -1)
    accts = accts[accts["amount"] > 0]
    return _group_list(gl, accts, "income", -1, [g["name"] for g in cfg.coa["revenue_groups"]])


def deductions(gl, cfg) -> list:
    accts = _accounts(gl, "income", -1)
    accts = accts[accts["amount"] < 0]
    return [{"account": r.account, "desc": r.desc, "amount": float(-r.amount)}
            for r in accts.sort_values("amount").itertuples()]


def expense_groups(gl, cfg) -> list:
    accts = _accounts(gl, "expense", 1)
    return _group_list(gl, accts, "expense", 1, [g["name"] for g in cfg.coa["expense_groups"]])


def _earned(gl, cfg):
    return float(-gl.loc[gl["account"].isin(cfg.coa["earned_revenue_accounts"]), "amount"].sum())


_MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                        "september", "october", "november", "december"], 1)}
_NAMED = re.compile(r"(january|february|march|april|may|june|july|august|september|october|november|december)"
                    r"\s+(20\d\d)", re.I)


def _service_month(a) -> pd.Series:
    """The month an assessment is FOR: named in the journal ('... - February 2024'), else the posting month."""
    def one(name, date):
        m = _NAMED.search(str(name))
        return pd.Period(year=int(m.group(2)), month=_MONTHS[m.group(1).lower()], freq="M") if m \
            else date.to_period("M")
    return pd.Series([one(n, d) for n, d in zip(a["journal_name"], a["date"])], index=a.index, dtype="period[M]")


def assessment(gl, cfg) -> dict:
    coa = cfg.coa
    a = gl[gl["role"] == "assessment"]
    total = float(a["amount"].sum())
    contra = float(gl.loc[gl["role"] == "contra", "amount"].sum())
    gross = sum(g["amount"] for g in revenue_groups(gl, cfg))
    earned = _earned(gl, cfg)
    ext = gl[gl["account"] == coa["external_sales_account"]]
    ext_income = float(-ext["amount"].sum())
    ext_m = (-ext["amount"]).groupby(ext["date"].dt.to_period("M")).sum()
    a_m = a["amount"].groupby(_service_month(a)).sum()
    last = max(a_m.index) if len(a_m) else None
    months = [m for m, v in ext_m.items() if abs(v) > 0.005 and last is not None and m <= last]
    unposted = [str(m) for m, v in ext_m.items() if abs(v) > 0.005 and (last is None or m > last)]
    matched = sum(1 for m in months if abs(a_m.get(m, 0.0) - coa["assessment_rate"] * ext_m[m]) <= 0.01)
    return {
        "total": total,
        "contra_total": contra,
        "by_fy": _by_fy(a, 1),
        "pct_gross": total / gross if gross else None,
        "pct_earned": total / earned if earned else None,
        "per_dollar_external": total / ext_income if ext_income else None,
        "rate": coa["assessment_rate"],
        "match": {"months": len(months), "matched": matched, "rate": matched / len(months) if months else None,
                  "not_yet_posted": unposted},
    }


def _outflows(gl, cfg):
    """(label, amount) items leaving the core, in display order."""
    items = [(g["name"], g["amount"]) for g in expense_groups(gl, cfg)]
    items.append((ASSESS_NODE, float(gl.loc[gl["role"] == "assessment", "amount"].sum())))
    items.append((CONTRA_NODE, float(gl.loc[gl["role"] == "contra", "amount"].sum())))
    items.append((DEDUCT_NODE, sum(d["amount"] for d in deductions(gl, cfg))))
    return items


def sankey(gl, cfg) -> list:
    core = cfg.short_name
    links = [{"from": g["name"], "to": core, "flow": g["amount"]} for g in revenue_groups(gl, cfg)]
    for label, amt in _outflows(gl, cfg):
        if amt > 0.005:
            links.append({"from": core, "to": label, "flow": amt})
        elif amt < -0.005:  # net credits (refunds) flow in
            links.append({"from": f"{label} (net credit)", "to": core, "flow": -amt})
    inflow = sum(l["flow"] for l in links if l["to"] == core)
    outflow = sum(l["flow"] for l in links if l["from"] == core)
    diff = inflow - outflow
    if diff > 0.005:
        links.append({"from": core, "to": SURPLUS_NODE, "flow": diff})
    elif diff < -0.005:
        links.append({"from": DEFICIT_NODE, "to": core, "flow": -diff})
    for l in links:
        l["flow"] = round(l["flow"], 2)
    return links


def _buckets(gl, cfg) -> tuple:
    """(personnel, supplies & services, everything else). Groups not named in a bucket count as other."""
    groups = expense_groups(gl, cfg)
    b = cfg.coa["per_dollar_buckets"]
    pers_names = set(b.get("personnel", [])) | {g["name"] for g in cfg.coa["expense_groups"] if g.get("personnel")}
    pers = sum(g["amount"] for g in groups if g["name"] in pers_names)
    sup = sum(g["amount"] for g in groups if g["name"] in set(b.get("supplies_services", [])) - pers_names)
    return pers, sup, sum(g["amount"] for g in groups) - pers - sup


def per_dollar(gl, cfg, fy: int | None = None) -> dict | None:
    if fy is not None:
        gl = gl[gl["fy"] == fy]
    gross = sum(g["amount"] for g in revenue_groups(gl, cfg))
    if gross <= 0:
        return None
    pers, sup, other_exp = _buckets(gl, cfg)
    other = other_exp + sum(d["amount"] for d in deductions(gl, cfg)) \
        + float(gl.loc[gl["role"] == "contra", "amount"].sum())
    out = {
        "personnel": pers / gross,
        "supplies_services": sup / gross,
        "other_operating": other / gross,
        "assessment": float(gl.loc[gl["role"] == "assessment", "amount"].sum()) / gross,
    }
    out["surplus"] = 1.0 - sum(out.values())
    return out


def cost_recovery_by_fy(gl, cfg) -> dict:
    out = {}
    for fy, sub in gl.groupby("fy"):
        exp = _expense(sub)
        if exp > 0:
            out[int(fy)] = _earned(sub, cfg) / exp
    return out


def series(gl, freq: str, fund: str | None = None) -> list:
    g = _op(gl)
    if fund:
        g = g[g["fund"] == fund]
    key = g["fy"].map(lambda f: f"FY{f}") if freq == "FY" else g["date"].dt.strftime("%Y-%m")
    out = []
    for k, sub in g.groupby(key):
        inc, exp = _income(sub), _expense(sub)
        out.append({"key": k, "income": inc, "expense": exp, "net": inc - exp})
    return out


def fund_summary(gl, cfg) -> list:
    out = []
    for (fund, fy), sub in _op(gl).groupby(["fund", "fy"]):
        inc, exp = _income(sub), _expense(sub)
        label = cfg.funds.get(fund, {}).get("label", fund)
        out.append({"fund": fund, "label": label, "fy": int(fy), "income": inc, "expense": exp, "net": inc - exp})
    return out


def carryforward(gl) -> list:
    cf = gl[gl["role"] == "carryforward"]
    return [{"fund": f, "fy": int(fy), "amount": float(v)}
            for (f, fy), v in cf.groupby(["fund", "fy"])["amount"].sum().items()]


def _monthly_net(gl) -> pd.Series:
    g = _op(gl)
    # net = income - expense = -(sum of all operating amounts), since amounts are debit-positive
    return (-g["amount"]).groupby(g["date"].dt.to_period("M")).sum().sort_index()


def balance_series(gl) -> list:
    cum = _monthly_net(gl).cumsum()
    return [{"month": str(m), "cumulative_net": float(v)} for m, v in cum.items()]


def bridge(gl, cfg, fy: int, beginning: float | None) -> list:
    sub = gl[gl["fy"] == fy]
    pers, sup, other_exp = _buckets(sub, cfg)
    gross = sum(g["amount"] for g in revenue_groups(sub, cfg))
    other = other_exp + sum(d["amount"] for d in deductions(sub, cfg)) \
        + float(sub.loc[sub["role"] == "contra", "amount"].sum())
    steps = [
        {"step": "Beginning balance", "amount": beginning or 0},
        {"step": "+ Revenue (gross)", "amount": gross},
        {"step": "− Personnel", "amount": -pers},
        {"step": "− Supplies & services", "amount": -sup},
        {"step": "− Other operating", "amount": -other},
        {"step": "− Campus assessment", "amount": -float(sub.loc[sub["role"] == "assessment", "amount"].sum())},
    ]
    steps.append({"step": "= Ending balance", "amount": sum(s["amount"] for s in steps)})
    return steps


MIN_FORECAST_MONTHS = 3


def forecast(gl, cfg) -> dict | None:
    g = _op(gl)
    if g.empty:
        return None
    latest = int(g["fy"].max())
    complete = complete_fys(g["date"])
    if latest in complete:
        return None
    prior = [fy for fy in complete if fy < latest]
    if not prior:
        return None
    seen = set(g.loc[g["fy"] == latest, "date"].dt.month)
    if len(seen) < MIN_FORECAST_MONTHS:  # one or two (often partial) months say little about the year
        return None
    net_of = lambda sub: _income(sub) - _expense(sub)  # noqa: E731
    ytd = net_of(g[g["fy"] == latest])
    rest = [net_of(g[(g["fy"] == fy) & ~g["date"].dt.month.isin(seen)]) for fy in prior]
    return {"fy": latest, "ytd_net": ytd, "months_seen": len(seen), "based_on_fys": prior,
            "projected": ytd + sum(rest) / len(rest), "low": ytd + min(rest), "high": ytd + max(rest)}


def top_accounts(gl, role: str, n: int = 15) -> list:
    sign = -1 if role == "income" else 1
    accts = _accounts(gl, role, sign).sort_values("amount", ascending=False).head(n)
    return [{"account": r.account, "desc": r.desc, "group": r.group, "amount": float(r.amount)}
            for r in accts.itertuples()]


def account_detail(gl, account: str, subledger=None) -> dict:
    sub = gl[gl["account"] == account]
    sign = 1 if (sub["role"] == "expense").any() or (sub["role"] == "assessment").any() else -1
    tx = [{"date": r.date.strftime("%Y-%m-%d"), "period": r.period, "fund": r.fund,
           "category": r.journal_category, "journal": r.journal_name, "amount": float(r.amount),
           "supplier": r.supplier, "line": r.line_desc} for r in sub.itertuples()]
    lines = []
    if subledger is not None and len(subledger):
        sl = subledger[subledger["account"] == account]
        lines = [{"date": r.date.strftime("%Y-%m-%d"), "supplier": r.supplier, "line": r.line_desc,
                  "amount": float(r.amount)} for r in sl.itertuples()]
    return {"desc": sub["account_desc"].iloc[0] if len(sub) else "", "by_fy": _by_fy(sub, sign),
            "transactions": tx, "subledger": lines}


def pnl_beginning(gl, pnl: list, fy: int) -> tuple:
    """Beginning balance (surplus-positive) of fiscal year `fy`, from a Department P&L.

    The P&L's own year is found by matching its activity (revenue + expense) to the GL operating net
    of each fiscal year; the balance is then rolled forward or back with the GL nets. Returns
    (beginning, pnl_fy, pnl_ending) or (None, None, None) when no year matches.
    """
    if not pnl:
        return None, None, None
    nets = {int(r["key"][2:]): r["net"] for r in series(gl, "FY")}
    activity = -sum(r["revenue"] + r["expense"] for r in pnl)
    begin = -sum(r["beginning"] for r in pnl)
    match = [y for y, n in nets.items() if abs(n - activity) <= max(1.0, 0.005 * abs(n))]
    if not match:
        return None, None, None
    p = max(match)
    if fy <= p:
        b = begin - sum(nets.get(y, 0.0) for y in range(fy, p))
    else:
        b = begin + sum(nets.get(y, 0.0) for y in range(p, fy))
    return b, p, -sum(r["ending"] for r in pnl)


def _bridge_block(gl, cfg, fy, beginning, pnl) -> dict:
    if not fy:
        return {"fy": None, "steps": [], "pnl_fy": None, "pnl_ending": None}
    pnl_fy = pnl_end = None
    if pnl is not None:
        beginning, pnl_fy, pnl_end = pnl_beginning(gl, pnl, fy)
    return {"fy": fy, "steps": bridge(gl, cfg, fy, beginning), "pnl_fy": pnl_fy, "pnl_ending": pnl_end}


def compute_finance(gl, cfg, balances_beginning: float | None = None, subledger=None, pnl=None) -> dict:
    op = _op(gl)
    fys = sorted(int(f) for f in op["fy"].unique()) if len(op) else []
    complete = complete_fys(op["date"]) if len(op) else []
    rev, exp, ded = revenue_groups(gl, cfg), expense_groups(gl, cfg), deductions(gl, cfg)
    latest_complete = complete[-1] if complete else None
    return {
        "core_node": cfg.short_name,
        "kpis": kpis(gl),
        "revenue_groups": rev,
        "expense_groups": exp,
        "deductions": ded,
        "assessment": assessment(gl, cfg),
        "sankey": sankey(gl, cfg),
        "per_dollar": {"all": per_dollar(gl, cfg), "by_fy": {fy: per_dollar(gl, cfg, fy) for fy in complete}},
        "cost_recovery_by_fy": cost_recovery_by_fy(gl, cfg),
        "series_fy": series(gl, "FY"),
        "series_month": series(gl, "M"),
        "series_by_fund": {f: {"fy": series(gl, "FY", f), "month": series(gl, "M", f)}
                           for f in sorted(op["fund"].unique())},
        "fund_summary": fund_summary(gl, cfg),
        "carryforward": carryforward(gl),
        "balance_series": balance_series(gl),
        "bridge": _bridge_block(gl, cfg, latest_complete, balances_beginning, pnl),
        "forecast": forecast(gl, cfg),
        "top_revenue": top_accounts(gl, "income"),
        "top_expense": top_accounts(gl, "expense"),
        "account_details": {a: account_detail(gl, a, subledger) for a in sorted(op["account"].unique())},
        "complete_fys": complete,
        "all_fys": fys,
        "gross_total": sum(g["amount"] for g in rev),
        "deductions_total": sum(d["amount"] for d in ded),
        "contra_total": float(gl.loc[gl["role"] == "contra", "amount"].sum()),
        "assessment_total": float(gl.loc[gl["role"] == "assessment", "amount"].sum()),
        "expense_total": _expense(gl),
    }
