"""Run everything for one core folder."""
from __future__ import annotations

import json
from pathlib import Path

from . import aggie, finance, usership
from .affiliation import build_or_update, load_affiliations
from .checks import run_checks, write_checks_md
from .config import load_config
from .dashboard import build_dashboard_data, write_dashboard
from .figures import render_figures
from .gl import classify, load_gl, load_subledger
from .inventory import reports_needed_md, scan
from .ppms import load_orders


class BuildError(Exception):
    pass


def run_build(folder, out=None) -> dict:
    folder = Path(folder)
    out = Path(out) if out else folder / "out"
    inv = scan(folder)
    by_kind: dict = {}
    for r in inv:
        if r["kind"]:
            by_kind.setdefault(r["kind"], []).append(Path(r["path"]))
    if not by_kind:
        raise BuildError(f"No recognised Aggie Enterprise or PPMS exports found in {folder}.")
    cfg_path = folder / "core-config.yaml"
    if not cfg_path.exists():
        raise BuildError(f"No core-config.yaml in {folder}. Run `python run.py init {folder}` first.")
    cfg = load_config(cfg_path)
    out.mkdir(parents=True, exist_ok=True)
    outputs, skipped = [], []

    gl_files = by_kind.get("gl_page", []) + by_kind.get("gl_wide", [])
    gl = classify(load_gl(gl_files, cfg), cfg) if gl_files else None
    if gl is not None and gl.empty:
        skipped.append({"section": "finance", "reason": "GL files had no rows in the configured funds"})
        gl = None
    balances = []
    for p in by_kind.get("pnl_balances", []):
        balances += aggie.load_balances(p)
    beginning = -aggie.balances_total(balances)["beginning"] if balances else None
    sub = load_subledger(gl_files, cfg) if gl_files else None
    fin = finance.compute_finance(gl, cfg, beginning, subledger=sub) if gl is not None else None
    if fin is None:
        skipped.append({"section": "finance (dashboard money sections, finance figures)",
                        "reason": "no GL Transaction Listing"})

    po = aggie.load_po(by_kind.get("po_spend", []), cfg) if by_kind.get("po_spend") else None
    glide = aggie.load_glide(by_kind.get("glide", [])) if by_kind.get("glide") else None
    ag: dict = {}
    if po is not None and len(po):
        ag["suppliers_by_account"] = aggie.suppliers_by_account(po)
        ag["supplier_concentration"] = aggie.supplier_concentration(po, cfg)
        ag["po_vs_gl"] = aggie.po_vs_gl(po, gl) if gl is not None else []
    else:
        skipped.append({"section": "companies paid / supplier concentration", "reason": "no PO spend report"})
    if balances:
        ag["balances"], ag["balances_total"] = balances, aggie.balances_total(balances)
    else:
        skipped.append({"section": "official fund balances", "reason": "no Department P&L"})
    if glide is not None and len(glide):
        ag["glide"] = aggie.glide_by_category(glide)
    else:
        skipped.append({"section": "card, travel and freight", "reason": "no GLIDE report"})

    use = orders = aff = None
    if by_kind.get("ppms_orders"):
        orders = load_orders(by_kind["ppms_orders"])
        build_or_update(orders, folder / "affiliations.csv", cfg.coa)
        aff = load_affiliations(folder / "affiliations.csv")
        use = usership.compute_usership(orders, aff)
    else:
        skipped.append({"section": "usership, RCCI tables, unbilled check", "reason": "no PPMS Order details"})

    checks = run_checks(fin, use, ag.get("po_vs_gl"))
    outputs.append(write_checks_md(checks, out / "checks.md"))
    for staff, name in ((False, "dashboard.html"), (True, "dashboard_STAFF.html")):
        outputs.append(write_dashboard(build_dashboard_data(fin, use, ag, checks, cfg, staff), cfg, out / name))
    figs = render_figures(fin, use, cfg, out, aggie=ag)
    outputs += [p for paths in figs.values() for p in paths]
    if use:
        from .rcci import write_usership_workbook
        outputs.append(write_usership_workbook(orders, aff, use, cfg, out / "usership.xlsx"))
    from .benchmark import write_benchmark
    from .summary import build_facts
    outputs.append(write_benchmark(fin, use, cfg, out / "benchmark.csv"))
    facts = build_facts(fin, use, checks, inv, cfg)
    (out / "facts.json").write_text(json.dumps(facts, indent=2, default=str))
    outputs.append(out / "facts.json")
    (out / "reports-needed.md").write_text(reports_needed_md(inv, cfg))
    outputs.append(out / "reports-needed.md")
    return {"outputs": [str(p) for p in outputs], "skipped": skipped,
            "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail, "kind": c.kind} for c in checks],
            "out": str(out)}
