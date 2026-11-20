"""Command line: python run.py {init,inventory,affiliations,build,combine} ..."""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

COMMANDS = ["init", "inventory", "affiliations", "build", "publications", "combine"]


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
    if any(Path(p).name == "dashboard_STAFF.html" for p in res["outputs"]):
        print("\ndashboard_STAFF.html hides individual salary accounts and transactions, but still shows "
              "yearly personnel totals. With few staff, those can reveal someone's pay.")
    print("\nshare/ is safe to show other cores. internal/, dashboard*.html and usership.xlsx contain dollar "
          "amounts and lab names.")
    return 0


def _publications(folder: Path, limit=None, excerpts=False, methods_check=False) -> int:
    from . import publications as P
    from .config import load_config
    from .inventory import scan
    from .ppms import load_orders
    files = [Path(r["path"]) for r in scan(folder) if r["kind"] == "ppms_orders"]
    if not files:
        print("No PPMS Order details report found. It holds the lab and submitter names to search.")
        return 2
    s = load_config(folder / "core-config.yaml").publications
    if not s["technique_terms"]:
        print("Add technique_terms under publications: in core-config.yaml first: words a methods section "
              "uses when your service was used (e.g. \"mass spectrometry\", \"confocal\").")
        return 2
    orders = load_orders(files)
    if limit:
        keep = orders[orders["is_revenue"]].groupby("group")["ordered"].max().nlargest(limit).index
        orders = orders[orders["group"].isin(keep)]
    out = folder / "out" / "internal"
    client = P.EuropePMC(out / "publications_cache.json.gz")
    print("Searching Europe PMC (includes all of PubMed) and Crossref (journals PubMed doesn't index). "
          "Author names are sent to europepmc.org and api.crossref.org.")

    def progress(i, n, person):
        if i % 50 == 0:
            print(f"  {i}/{n} people searched", flush=True)
    failed = []
    try:
        rows = P.find_papers(orders, s, client, progress, failed)
        cr = P.Crossref(out / "crossref_cache.json")
        if hasattr(cr, "prefetch"):
            cr.prefetch(P.crossref_pairs(orders, s))
        journals = {(((x.get("journalInfo") or {}).get("journal") or {}).get("title") or "")
                    for hits in getattr(client, "cache", {}).values() for x in hits}
        rows += P.find_outside_pubmed(orders, s, cr, client, rows, failed=failed, indexed_journals=journals - {""})
    finally:
        for c in (client, locals().get("cr")):
            if hasattr(c, "save"):
                c.save()
    fu = P.follow_up(orders, rows, s)
    review_dir = out / "paper_review"
    if excerpts:
        _write_excerpts(P, rows, s, client, review_dir)
    verdicts = P.load_review(review_dir)
    mc_path = review_dir / "methods_check.json"
    if methods_check:
        _methods_check(P, rows, s, client, verdicts, mc_path)
    methods = None
    if mc_path.exists():
        import json
        reviews = P.load_methods_reviews(review_dir)
        verdicts = P.verdicts_from_reviews(reviews, verdicts)
        methods = P.classify_methods(list(json.loads(mc_path.read_text()).values()), reviews)
    path = out / "publications.xlsx"
    P.write_workbook(rows, fu, s, path, verdicts=verdicts or None, methods=methods)
    n = {st: sum(r["status"] == st for r in rows) for st in (P.NAMED, P.NOT_NAMED, P.CANT_CHECK, P.OTHER, P.OUTSIDE)}
    checkable = n[P.NAMED] + n[P.NOT_NAMED]
    print(f"\n{len(rows) - n[P.OUTSIDE]} papers may use the core's data:")
    print(f"  {n[P.NAMED]} name the core, {n[P.NOT_NAMED]} don't, {n[P.CANT_CHECK]} can't be checked (no free full text), "
          f"{n[P.OTHER]} name another facility")
    if checkable:
        print(f"  Of the papers that could be checked, {n[P.NAMED] / checkable:.0%} name the core.")
    if n[P.OUTSIDE]:
        print(f"  Plus {n[P.OUTSIDE]} papers by customer labs that PubMed doesn't have (sheet 'Not in PubMed'); "
              "their methods can't be searched, so run --excerpts to read them.")
    print(f"  Follow up: {len(fu)} labs with recent orders and no paper yet.")
    if failed:
        print(f"  {len(failed)} people could not be searched; run again to retry them (results are cached).")
    if getattr(client, "truncated", None):
        print(f"  {len(client.truncated)} searches had more than 1,000 results and were cut off (very common "
              "names); add a technique_also list to narrow them.")
    if verdicts:
        ask = {k for k, v in verdicts.items() if str(v.get("action", "")).startswith("Ask")}
        print(f"  Full-text review: {len(verdicts)} papers reviewed; {len(ask)} to raise with the lab "
              "(sheet 'Ask the lab').")
    cred = {P.row_key(r): r for r in P.credited(rows, verdicts)}
    if s["core_staff"]:
        print(f"  {sum(not r.get('staff') for r in cred.values())} of {len(cred)} papers that credit the core have no "
              "core staff author (sheet 'Credited, no staff author').")
    if methods:
        flagged = [k for k, v in methods.items() if k in cred and v["methods"] in (P.MC_NOT, P.MC_VAGUE)]
        print(f"  Methods check: {len(flagged)} of {len(cred)} credited papers have methods that are probably "
              "not the core's (sheet \"Methods not the core's\").")
    print(f"\nWrote {path} (internal: lab names).")
    return 0


def _find_doi(client, r) -> str:
    import re
    ppr = re.search(r"/PPR/(PPR\d+)", r.get("link", ""))
    if r.get("doi") or not ((r.get("pmid") and not r.get("pmcid")) or ppr):
        return r.get("doi") or ""
    hit = client.search(f"EXT_ID:{ppr.group(1)} AND SRC:PPR" if ppr else f"EXT_ID:{r['pmid']} AND SRC:MED")
    return (hit[0].get("doi") if hit else "") or ""


def _methods_check(P, rows, s, client, verdicts, path: Path) -> None:
    """Read the full text of every paper that credits the core and record its instruments and grant lines.
    Papers checked on an earlier run are kept and not fetched again."""
    import json
    from concurrent.futures import ThreadPoolExecutor
    from . import fulltext as T
    if not s["core_grants"]:
        print("Add core_grants under publications: in core-config.yaml first (each grant-funded instrument and "
              "the words of its acknowledgment); without them the methods can't be judged.")
        return
    done = json.loads(path.read_text()) if path.exists() else {}
    recs = {}
    for r in P.credited(rows, verdicts):
        k = P.row_key(r)
        if k not in done and k not in recs:
            recs[k] = {"key": k, "date": r["date"], "pmid": r.get("pmid", ""), "pmcid": r.get("pmcid", ""),
                       "doi": r.get("doi", ""), "link": r.get("link", ""), "title": r["title"]}
    for r in recs.values():
        r["doi"] = _find_doi(client, r)
    ms = T.terms_regex(s["technique_terms"] + s.get("technique_also", []))
    print(f"\nMethods check: reading {len(recs)} papers that credit the core ({len(done)} checked earlier)...", flush=True)
    with ThreadPoolExecutor(4) as ex:
        got = list(ex.map(lambda r: T.excerpts_for(r, s["institution"], s["core_names"], ms=ms,
                                                   grants=s["core_grants"]), recs.values()))
    keep = ("key", "date", "title", "link", "error", "grant_instruments", "grant_lines", "instruments",
            "n_ms_paragraphs", "ms_paragraphs", "facility_sentences", "acknowledgments", "source")
    for g in got:
        done[g["key"]] = {k: (g[k][:2] if k == "ms_paragraphs" else g[k]) for k in keep if k in g}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(done, ensure_ascii=False, indent=1))


def _write_excerpts(P, rows, s, client, review_dir: Path) -> None:
    import json
    from concurrent.futures import ThreadPoolExecutor
    from . import fulltext as T
    import re
    reviewed = P.keep_review(review_dir)  # earlier rounds' verdicts are kept; only new papers are read
    recs = [r for r in P.review_records(rows) if r["key"] not in reviewed]
    for i, r in enumerate(recs, 1):
        r["n"] = i
        r["doi"] = _find_doi(client, r)  # look the DOI up once
    ms = T.terms_regex(s["technique_terms"] + s.get("technique_also", []))
    print(f"\nReading the full text of {len(recs)} papers not reviewed yet (flagged, other facility, can't check, "
          f"not in PubMed); {len(reviewed)} reviewed earlier are kept...", flush=True)
    with ThreadPoolExecutor(4) as ex:
        done = list(ex.map(lambda r: T.excerpts_for(r, s["institution"], s["core_names"], ms=ms), recs))
    auto = {r["key"]: {"verdict": "no_new_proteomics", "confidence": "medium", "where": "-",
                       "evidence": "Full text found; it never mentions the core's techniques.", "action": "No action"}
            for r in done if r["status"] == P.OUTSIDE and "error" not in r and not r.get("n_ms_paragraphs")}
    readable = [r for r in done if "error" not in r and r["key"] not in auto]
    library = [r for r in done if "error" in r]
    review_dir.mkdir(parents=True, exist_ok=True)
    for old in review_dir.glob("verdict*.json"):
        old.unlink()
    P.keep_review(review_dir, auto)
    (review_dir / "index.json").unlink(missing_ok=True)
    paths = T.write_batches(readable, review_dir)
    (review_dir / "index.json").write_text(json.dumps({r["n"]: r["key"] for r in done}))
    (review_dir / "read_in_library.json").write_text(json.dumps(library, ensure_ascii=False, indent=1))
    print(f"  {len(readable)} to review, in {len(paths)} batch files in {review_dir}")
    if auto:
        print(f"  {len(auto)} papers outside PubMed never mention the core's techniques: closed automatically")
    print(f"  {len(library)} have no free full text: listed in read_in_library.json for someone with library access")
    print("  Next: review each batch (reference/paper-review.md), then run this command again without --excerpts.")


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
    pp = sub.add_parser("publications", help="find customers' papers and check they name the core (online)")
    pp.add_argument("folder", type=Path)
    pp.add_argument("--limit", type=int, help="only the N labs with the most recent orders (for a quick test)")
    pp.add_argument("--excerpts", action="store_true",
                    help="also read flagged papers' full text and write excerpts for review")
    pp.add_argument("--methods-check", action="store_true",
                    help="read the full text of papers that credit the core and check their methods carry "
                         "the core's instrument-grant lines")
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
    if args.cmd == "publications":
        return _publications(folder, args.limit, args.excerpts, args.methods_check)
    return {"init": _init, "inventory": _inventory, "affiliations": _affiliations, "build": _build}[args.cmd](folder)


if __name__ == "__main__":
    sys.exit(main())
