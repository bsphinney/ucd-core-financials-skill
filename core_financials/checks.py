"""Reconciliation checks. Failures never stop output; they are reported loudly."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

TOL = 0.01


@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    kind: str = "arithmetic"  # arithmetic | info


def _money(x):
    return f"{x:,.2f}"


def _eq(name, a, b, la, lb):
    ok = abs(a - b) <= TOL
    return Check(name, ok, f"{la} {_money(a)} vs {lb} {_money(b)}" + ("" if ok else f" (off by {_money(a - b)})"))


def run_checks(fin: dict | None, use: dict | None, po_gl: list | None = None) -> list:
    out: list[Check] = []
    if fin:
        k = fin["kpis"]
        out.append(_eq("income − expense = net", k["income"] - k["expense"], k["net"], "income − expense", "net"))
        net_rev = fin["gross_total"] - fin["assessment_total"] - fin["contra_total"] - fin["deductions_total"]
        out.append(_eq("gross − assessment − contra − deductions = income", net_rev, k["income"],
                       "net revenue", "operating income"))
        core_name = fin.get("core_node")
        if core_name:
            inflow = sum(l["flow"] for l in fin["sankey"] if l["to"] == core_name)
            outflow = sum(l["flow"] for l in fin["sankey"] if l["from"] == core_name)
            out.append(_eq("Sankey in = out", inflow, outflow, "in", "out"))
        out.append(_eq("expense groups sum = expense", sum(g["amount"] for g in fin["expense_groups"]),
                       fin["expense_total"], "groups", "expense"))
        bad = [g["name"] for g in fin["expense_groups"] + fin["revenue_groups"]
               if abs(sum(a["amount"] for a in g["accounts"]) - g["amount"]) > TOL]
        out.append(Check("each group = sum of its accounts", not bad, "mismatched: " + ", ".join(bad) if bad
                         else "all groups match their account lists"))
        m = fin["assessment"]["match"]
        if m["months"]:
            rate = fin["assessment"]["rate"]
            out.append(Check(f"assessment matches {rate:.0%} of external sales", True,
                             f"{m['matched']} of {m['months']} months match to the cent"
                             + (f"; not yet charged: {', '.join(m.get('not_yet_posted') or [])}"
                                if m.get("not_yet_posted") else ""), "info"))
    for row in po_gl or []:
        out.append(Check(f"PO committed vs GL posted, {row['account']}", True,
                         f"PO {_money(row['po_committed'])} vs GL {_money(row['gl_posted'])}", "info"))
    if use:
        out.append(_eq("usership revenue by FY = total revenue lines",
                       sum(r["revenue"] for r in use["overview_by_fy"]), use["revenue_total"], "by FY", "total"))
    return out


def write_checks_md(checks, path) -> Path:
    lines = ["# Reconciliation checks", ""]
    failed = [c for c in checks if c.kind == "arithmetic" and not c.passed]
    lines.append(f"**{len(failed)} failed** of {sum(c.kind == 'arithmetic' for c in checks)} arithmetic checks."
                 if failed else "All arithmetic checks passed.")
    lines += ["", "| Result | Check | Detail |", "|---|---|---|"]
    for c in checks:
        res = "INFO" if c.kind == "info" else ("PASS" if c.passed else "**FAIL**")
        lines.append(f"| {res} | {c.name} | {c.detail} |")
    p = Path(path)
    p.write_text("\n".join(lines) + "\n")
    return p
