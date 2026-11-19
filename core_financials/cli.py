"""Command line: python run.py {init,inventory,affiliations,build,combine} ..."""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

COMMANDS = ["init", "inventory", "affiliations", "build", "combine"]


def _init(folder: Path) -> int:
    from .config import write_config_template
    from .gl import PAGE_SIG, WIDE_SIG
    from .io_util import norm_code, read_table
    target = folder / "core-config.yaml"
    if target.exists():
        print(f"{target} already exists; leaving it unchanged. Edit it directly.")
        return 0
    funds, depts, projects = {}, Counter(), Counter()
    for p in sorted(folder.iterdir()):
        if p.suffix.lower() not in (".xlsx", ".xls", ".csv"):
            continue
        for sig in (PAGE_SIG, WIDE_SIG):
            try:
                df = read_table(p, sig)
            except Exception:
                df = None
            if df is None:
                continue
            for f, d in zip(df["Fund"].map(norm_code), df.get("Fund Description", df["Fund"])):
                if f:
                    funds.setdefault(f, str(d))
            if "Financial Department" in df:
                depts.update(df["Financial Department"].dropna().astype(str))
            if "Project" in df:
                projects.update(df["Project"].dropna().astype(str))
            break
    dept = depts.most_common(1)[0][0] if depts else ""
    project = projects.most_common(1)[0][0] if projects else ""
    write_config_template(target, funds or None, dept=dept, project=project)
    print(f"Wrote {target}.")
    if funds:
        print("Funds found in the ledger (confirm which to keep):")
        for f, d in funds.items():
            print(f"  {f}  {d}")
    else:
        print("No GL export found yet: fund 12100 was filled in as a placeholder.")
    return 0


def _inventory(folder: Path) -> int:
    from .config import Config, load_config
    from .inventory import NAMES, reports_needed_md, scan
    inv = scan(folder)
    cfg_path = folder / "core-config.yaml"
    cfg = load_config(cfg_path) if cfg_path.exists() else Config(core_name=folder.name)
    print(f"{'File':45} {'Report':55} Covers")
    for r in inv:
        cover = f"{r['start']} → {r['end']}" if r["start"] else ""
        print(f"{r['file'][:45]:45} {NAMES.get(r['kind'], 'not recognised')[:55]:55} {cover}")
    out = folder / "out"
    out.mkdir(exist_ok=True)
    (out / "reports-needed.md").write_text(reports_needed_md(inv, cfg))
    print(f"\nWrote {out / 'reports-needed.md'}")
    return 0


def _affiliations(folder: Path) -> int:
    from .affiliation import build_or_update
    from .config import load_config, load_coa
    from .inventory import scan
    from .ppms import load_orders
    files = [Path(r["path"]) for r in scan(folder) if r["kind"] == "ppms_orders"]
    if not files:
        print("No PPMS Order details report found.")
        return 2
    cfg_path = folder / "core-config.yaml"
    coa = load_config(cfg_path).coa if cfg_path.exists() else load_coa()
    df = build_or_update(load_orders(files), folder / "affiliations.csv", coa)
    unconf = df[df["confirmed"].str.upper() != "Y"]
    print(f"{folder / 'affiliations.csv'}: {len(df)} groups, {len(unconf)} unconfirmed")
    for conf, n in unconf["confidence"].value_counts().items():
        print(f"  {conf}: {n}")
    print("By guessed affiliation:", dict(df["affiliation"].value_counts()))
    return 0


def _build(folder: Path) -> int:
    from .pipeline import BuildError, run_build
    try:
        res = run_build(folder)
    except BuildError as e:
        print(f"ERROR: {e}")
        return 2
    print(f"Outputs in {res['out']}:")
    for p in res["outputs"]:
        if not p.endswith(".svg"):
            print("  " + str(Path(p).relative_to(res["out"])))
    if res["skipped"]:
        print("\nSkipped (add the report to include it):")
        for s in res["skipped"]:
            print(f"  - {s['section']}: {s['reason']}")
    failed = [c for c in res["checks"] if c["kind"] == "arithmetic" and not c["passed"]]
    if failed:
        print("\nFAILED CHECKS — figures may be wrong:")
        for c in failed:
            print(f"  ✗ {c['name']}: {c['detail']}")
    else:
        print(f"\nAll {sum(c['kind'] == 'arithmetic' for c in res['checks'])} reconciliation checks passed.")
    print("\nshare/ is safe to show other cores. internal/, dashboard*.html and usership.xlsx contain dollar "
          "amounts and lab names.")
    return 0


def _combine(paths, out: Path) -> int:
    from .benchmark import combine_benchmarks
    out.mkdir(parents=True, exist_ok=True)
    combine_benchmarks(paths, out / "benchmark_comparison.xlsx", out / "benchmark_comparison.png")
    print(f"Wrote {out / 'benchmark_comparison.xlsx'} and {out / 'benchmark_comparison.png'}")
    return 0


def main(argv=None) -> int:
    from ._deps import ensure
    ensure(["pandas", "openpyxl", "xlrd", "matplotlib", "yaml"])
    ap = argparse.ArgumentParser(prog="run.py", description="UC Davis core financial and usership reports")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, help_ in [("init", "write core-config.yaml, proposing funds from the GL export"),
                        ("inventory", "list the reports found and write out/reports-needed.md"),
                        ("affiliations", "guess customer affiliations into affiliations.csv"),
                        ("build", "build every output into <folder>/out")]:
        p = sub.add_parser(name, help=help_)
        p.add_argument("folder", type=Path)
    c = sub.add_parser("combine", help="compare several cores' benchmark.csv files")
    c.add_argument("files", nargs="+", type=Path)
    c.add_argument("--out", type=Path, default=Path("benchmark_comparison"))
    args = ap.parse_args(argv)
    if args.cmd == "combine":
        return _combine(args.files, args.out)
    folder = args.folder.expanduser().resolve()
    if not folder.is_dir():
        print(f"ERROR: {folder} is not a folder")
        return 2
    return {"init": _init, "inventory": _inventory, "affiliations": _affiliations, "build": _build}[args.cmd](folder)


if __name__ == "__main__":
    sys.exit(main())
