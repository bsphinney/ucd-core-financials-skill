"""Single-file interactive HTML dashboard (and the staff edition with personnel detail removed)."""
from __future__ import annotations

import copy
import json
import re
from datetime import date
from pathlib import Path

from . import SKILL_ROOT, __version__

TEMPLATE = SKILL_ROOT / "assets" / "dashboard_template.html"
VENDOR = [SKILL_ROOT / "assets" / "vendor" / n for n in
          ("chart.umd.min.js", "chartjs-chart-treemap.min.js", "chartjs-chart-sankey.min.js")]

MISSING = {
    "gl": "Add the GL Transaction Listing to see income, expenses, the campus assessment and the money flow.",
    "po": "Add the PO spend report to see which companies were paid for each expense account.",
    "pnl": "Add the Department P&L (Balances tab) to see official fund balances.",
    "glide": "Add the GLIDE report to see card, travel and freight spending.",
    "ppms": "Add the PPMS Order details report to see customers, turnaround, backlog and unbilled orders.",
}


def _personnel(code: str, prefixes) -> bool:
    return str(code).startswith(tuple(prefixes))


def _redact_fin(fin: dict, cfg) -> dict:
    fin = copy.deepcopy(fin)
    pre = cfg.personnel_prefixes
    pers_groups = {g["name"] for g in cfg.coa["expense_groups"] if g.get("personnel")}
    for g in fin["expense_groups"]:
        if g["name"] in pers_groups or any(_personnel(a["account"], pre) for a in g["accounts"]):
            g["accounts"] = [a for a in g["accounts"] if not _personnel(a["account"], pre)]
    fin["account_details"] = {a: d for a, d in fin["account_details"].items() if not _personnel(a, pre)}
    top = [r for r in fin["top_expense"] if not _personnel(r["account"], pre)]
    for g in fin["expense_groups"]:
        if g["name"] in pers_groups:
            top.append({"account": "", "desc": f"{g['name']} (all personnel accounts combined)",
                        "group": g["name"], "amount": g["amount"], "aggregate": True})
    fin["top_expense"] = sorted(top, key=lambda r: -r["amount"])
    return fin


def build_dashboard_data(fin, use, aggie: dict, checks, cfg, staff: bool) -> dict:
    aggie = copy.deepcopy(aggie or {})
    use = copy.deepcopy(use) if use else None
    if staff and fin:
        fin = _redact_fin(fin, cfg)
        pre = cfg.personnel_prefixes
        if "suppliers_by_account" in aggie:
            aggie["suppliers_by_account"] = {a: v for a, v in aggie["suppliers_by_account"].items()
                                             if not _personnel(a, pre)}
        if "po_vs_gl" in aggie:
            aggie["po_vs_gl"] = [r for r in aggie["po_vs_gl"] if not _personnel(r["account"], pre)]
    if staff and use:
        use["unbilled"] = None
    missing = {}
    if not fin:
        missing["gl"] = MISSING["gl"]
    if not aggie.get("suppliers_by_account"):
        missing["po"] = MISSING["po"]
    if not aggie.get("balances"):
        missing["pnl"] = MISSING["pnl"]
    if not aggie.get("glide"):
        missing["glide"] = MISSING["glide"]
    if not use:
        missing["ppms"] = MISSING["ppms"]
    return {
        "meta": {"core_name": cfg.core_name, "short_name": cfg.short_name, "generated": date.today().isoformat(),
                 "staff": staff, "version": __version__, "brand": cfg.brand,
                 "assessment_note": cfg.assessment_note,
                 "funds": {k: v.get("label", k) for k, v in cfg.funds.items()},
                 "rate": cfg.coa.get("assessment_rate")},
        "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail, "kind": c.kind} for c in checks],
        "fin": fin,
        "use": use,
        "aggie": aggie,
        "missing": missing,
    }


def _vendor_js() -> str:
    parts = []
    for p in VENDOR:
        js = re.sub(r"//# sourceMappingURL=\S+", "", p.read_text())
        parts.append(f"<script>\n{js}\n</script>")
    return "\n".join(parts)


def _json(obj) -> str:
    s = json.dumps(obj, default=str, separators=(",", ":"))
    return s.replace("</", "<\\/")


def write_dashboard(data: dict, cfg, out_path) -> Path:
    html = TEMPLATE.read_text()
    title = f"{cfg.core_name} — Financial Dashboard" + (" (Staff Edition)" if data["meta"]["staff"] else "")
    html = html.replace("__TITLE__", title.replace("<", "&lt;"))
    html = html.replace("<!--__VENDOR__-->", _vendor_js())
    html = html.replace("/*__DATA__*/", f"const DATA = {_json(data)};\n")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    return out
