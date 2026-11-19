"""facts.json: every number the one-page summary may quote, each with its source."""
from __future__ import annotations

GL = "GL Transaction Listing"
PPMS = "PPMS Order details report"


def build_facts(fin, use, checks, inv, cfg) -> dict:
    facts = []
    add = lambda id_, label, value, unit, source, fy=None: facts.append(  # noqa: E731
        {"id": id_, "label": label, "value": value, "unit": unit, "fy": fy, "source": source})
    if fin:
        k = fin["kpis"]
        span = f"FY{fin['all_fys'][0]}–FY{fin['all_fys'][-1]}" if fin["all_fys"] else ""
        add("fin.income", f"Operating income, {span}", round(k["income"], 2), "usd", GL)
        add("fin.expense", f"Operating expense, {span}", round(k["expense"], 2), "usd", GL)
        add("fin.net", f"Operating net, {span}", round(k["net"], 2), "usd", GL)
        for r in fin["series_fy"]:
            fy = int(r["key"][2:])
            if fy in fin["complete_fys"]:
                add(f"fin.net.{fy}", f"Operating net FY{fy}", round(r["net"], 2), "usd", GL, fy)
        for fy, v in fin["cost_recovery_by_fy"].items():
            tag = "" if fy in fin["complete_fys"] else " (partial year)"
            add(f"fin.cost_recovery.{fy}", f"Cost recovery FY{fy}{tag}", round(v, 4), "ratio", GL, fy)
        a = fin["assessment"]
        add("fin.assessment.total", "Campus income assessment, whole ledger", round(a["total"], 2), "usd", GL)
        if a["per_dollar_external"] is not None:
            add("fin.assessment.per_external", "Assessment per $1 of external sales",
                round(a["per_dollar_external"], 4), "fraction", GL)
        if a["match"]["months"]:
            add("fin.assessment.match", f"Months where assessment = {a['rate']:.0%} of external sales",
                f"{a['match']['matched']} of {a['match']['months']}", "text", GL)
        if fin["complete_fys"]:
            fy = fin["complete_fys"][-1]
            p = fin["per_dollar"]["by_fy"].get(fy)
            if p:
                for key, v in p.items():
                    add(f"fin.per_dollar.{key}.{fy}", f"Per $1 of gross revenue FY{fy}: {key.replace('_', ' ')}",
                        round(v, 4), "fraction", GL, fy)
        f = fin["forecast"]
        if f:
            add("fin.forecast", f"Projected FY{f['fy']} year-end operating net (projection)",
                {"projected": round(f["projected"], 2), "low": round(f["low"], 2), "high": round(f["high"], 2),
                 "months_seen": f["months_seen"]}, "usd", GL, f["fy"])
    if use:
        comp = use["complete_fys"]
        for r in use["overview_by_fy"]:
            tag = "" if r["fy"] in comp else " (partial year)"
            add(f"use.orders.{r['fy']}", f"Orders FY{r['fy']}{tag}", r["orders"], "count", PPMS, r["fy"])
            add(f"use.groups.{r['fy']}", f"Lab groups served FY{r['fy']}{tag}", r["groups"], "count", PPMS, r["fy"])
        if use["mix_by_fy"]:
            last = use["mix_by_fy"][-1]
            add("use.mix.latest", f"Customer mix FY{last['fy']} (share of revenue)",
                {k: round(v, 4) for k, v in last.items() if k != "fy"}, "fraction", PPMS, last["fy"])
        c = use["concentration"]
        if c["top10"] is not None:
            add("use.top10", f"Share of revenue from the top 10 of {c['n_groups']} lab groups", round(c["top10"], 4),
                "fraction", PPMS)
        for r in use["new_vs_returning"][-2:]:
            add(f"use.new.{r['fy']}", f"New lab groups FY{r['fy']}", r["new"], "count", PPMS, r["fy"])
        for r in use["turnaround"].get("by_fy", [])[-2:]:
            add(f"use.turnaround.{r['fy']}", f"Median turnaround FY{r['fy']} (days)", round(r["median"], 1), "days",
                PPMS, r["fy"])
        if use["backlog_monthly"]:
            b = use["backlog_monthly"][-1]
            add("use.backlog.latest", f"Open orders at end of {b['month']}", b["open"], "count", PPMS)
        if use.get("unbilled"):
            add("use.unbilled", "Completed order lines not marked invoiced",
                {"lines": len(use["unbilled"]["lines"]), "total": round(use["unbilled"]["total"], 2)}, "usd", PPMS)
        add("use.quotes", "Unconverted quotes excluded",
            {"count": use["quotes"]["count"], "total": round(use["quotes"]["total"], 2)}, "usd", PPMS)
    failed = [c.name for c in checks if c.kind == "arithmetic" and not c.passed]
    add("checks.failed", "Reconciliation checks that failed", failed, "list", "checks.md")
    kinds = {r["kind"] for r in inv if r.get("kind")}
    add("inputs.present", "Report types found in the folder", sorted(kinds), "list", "reports-needed.md")
    return {"core": cfg.core_name, "facts": facts,
            "rules": ["Quote only numbers in this file.", "Say 'projection' for the forecast.",
                      "Label partial fiscal years.", "Shareable text must not include dollar amounts or lab names."]}
