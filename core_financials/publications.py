"""Papers by the core's customers that may use the core's data, and whether they name the core.

Uses Europe PMC (all of PubMed plus open-access and NIH full text, searchable by section). This is the
only part of the skill that goes online: it sends author names to a public literature search. It is
never run by `build`.
"""
from __future__ import annotations

import html
import gzip
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

NAMED = "Names the core"
NOT_NAMED = "Core not named"
CANT_CHECK = "Can't check: no free full text"
OTHER = "Names another facility"
OUTSIDE = "Not in PubMed: check the methods"
API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
DEFAULTS = {"core_names": [], "other_facilities": [], "technique_terms": [], "technique_also": [], "institution": "Davis", "years_after": 3, "follow_up_years": 3, "core_staff": [], "core_grants": []}


def settings(raw: dict | None, core_name: str = "") -> dict:
    s = {**DEFAULTS, **(raw or {})}
    s["core_names"] = [str(x) for x in (s["core_names"] or ([core_name] if core_name else []))]
    s["technique_terms"] = [str(x) for x in s["technique_terms"] or []]
    s["other_facilities"] = [str(x) for x in s["other_facilities"] or []]
    s["technique_also"] = [str(x) for x in s["technique_also"] or []]
    s["core_staff"] = [str(x) for x in s["core_staff"] or []]
    s["core_grants"] = [g for g in s["core_grants"] or [] if isinstance(g, dict) and g.get("instrument")]
    return s


# ---------- people ----------

def parse_group(name: str) -> tuple[str, str]:
    """PPMS group 'Last, First Middle (note)' -> (last, first)."""
    name = re.sub(r"\(.*?\)", "", str(name)).strip()
    if "," in name:
        last, first = [x.strip() for x in name.split(",", 1)]
    else:
        parts = name.split()
        last, first = (parts[-1], " ".join(parts[:-1])) if len(parts) > 1 else (name, "")
    return last, (first.split() or [""])[0].strip(".")


PARTICLES = {"van", "der", "den", "de", "la", "le", "del", "della", "da", "di", "dos", "das", "du", "von", "ter", "st"}


def parse_user(name: str) -> tuple[str, str]:
    """PPMS user 'Last First' -> (last, first); leading particles stay with the surname (Van Der Berg)."""
    if "," in str(name):
        return parse_group(name)
    parts = re.sub(r"\(.*?\)", "", str(name)).split()
    if len(parts) < 2:
        return ((parts or [""])[0], "")
    i = 0
    while i < len(parts) - 2 and parts[i].casefold() in PARTICLES:
        i += 1
    return " ".join(parts[:i + 1]), parts[i + 1]


def _window(ords, years_after):
    start = ords["ordered"].min().date()
    end = min(ords["ordered"].max().date() + timedelta(days=round(365.25 * years_after)), date.today())
    return start, end


def people_from_orders(orders: pd.DataFrame, s: dict) -> list[dict]:
    o = orders[orders["is_revenue"]]
    people = []
    for group, g in o.groupby("group"):
        last, first = parse_group(group)
        start, end = _window(g, s["years_after"])
        people.append({"last": last, "first": first, "role": "PI", "group": group, "start": start, "end": end})
        for user, u in g.groupby("user"):
            ul, uf = parse_user(user)
            if not ul or (ul.casefold() == last.casefold() and uf[:1].casefold() == first[:1].casefold()):
                continue
            us, ue = _window(u, s["years_after"])
            people.append({"last": ul, "first": uf, "role": "submitter", "group": group, "start": us, "end": ue,
                           "user": user})
    return people


# ---------- queries ----------

def _term(field, t):
    t = str(t).replace('"', "")
    return f"{field}:{t}" if re.fullmatch(r"[A-Za-z0-9*]+", t) else f'{field}:"{t}"'


def _base(last, first, start, end):
    au = f"{last} {first[:1]}".strip().replace('"', "")
    return f'AUTH:"{au}" AND FIRST_PDATE:[{start:%Y-%m-%d} TO {end:%Y-%m-%d}]'


def _any(terms):
    return " OR ".join(_term(f, t) for t in terms for f in ("METHODS", "ABSTRACT", "TITLE"))


def technique_query(last, first, start, end, s) -> str:
    q = f"{_base(last, first, start, end)} AND ({_any(s['technique_terms'])})"
    if s.get("technique_also"):
        q += f" AND ({_any(s['technique_also'])})"
    return q


def named_query(last, first, start, end, s, key="core_names") -> str:
    names = " OR ".join('"' + str(n).replace('"', "") + '"' for n in s[key])
    return f"{technique_query(last, first, start, end, s)} AND ({names})"


# ---------- matching ----------

def _authors(p):
    return (p.get("authorList") or {}).get("author") or []


def _affs(a):
    return " ".join(x.get("affiliation", "") for x in (a.get("authorAffiliationDetailsList") or {}).get(
        "authorAffiliation", []))


def _given(name):
    import unicodedata
    plain = "".join(c for c in unicodedata.normalize("NFKD", str(name)) if not unicodedata.combining(c))
    return re.sub(r"[^a-z]", "", (plain.split() or [""])[0].casefold())


def _is(a, last, first):
    if (a.get("lastName") or "").casefold() != last.casefold():
        return False
    if not first:
        return True
    full, mine = _given(a.get("firstName") or ""), _given(first)
    if len(full) > 1 and len(mine) > 1:  # both full names: one must start with the other (Chris/Christopher)
        return full.startswith(mine) or mine.startswith(full)
    return _given(a.get("firstName") or a.get("initials") or "")[:1] == _given(first)[:1]


def _is_review(p):
    return any("review" in str(t).casefold() for t in (p.get("pubTypeList") or {}).get("pubType", []))


def _keep(paper, person, lab_people, s):
    pub = str(paper.get("firstPublicationDate") or "")
    if _is_review(paper) or not (f"{person['start']:%Y-%m-%d}" <= pub <= f"{person['end']:%Y-%m-%d}"):
        return False
    me = [a for a in _authors(paper) if _is(a, person["last"], person["first"])]
    if not me:
        return False
    if any(s["institution"].casefold() in _affs(a).casefold() for a in me):
        return True
    # otherwise the PI and a submitter from the lab must both be authors, as two different author records
    others = [q for q in lab_people if q is not person and (person["role"] == "PI" or q["role"] == "PI")]
    return any(_is(a, q["last"], q["first"]) for q in others for a in _authors(paper) if not any(a is m for m in me))


RANK = {NAMED: 3, OTHER: 2, NOT_NAMED: 1, CANT_CHECK: 0, OUTSIDE: -1}


def staff_authors(paper: dict, s: dict) -> list[str]:
    """Core staff (core_staff surnames) among the authors, counted only when the author is at the
    institution or has no affiliation listed, so a namesake elsewhere doesn't count."""
    staff = {x.casefold(): x for x in s.get("core_staff") or []}
    inst = str(s.get("institution", "")).casefold()
    out = []
    for a in _authors(paper):
        name = staff.get(str(a.get("lastName") or "").casefold())
        affs = _affs(a).casefold()
        if name and (not affs or inst in affs) and name not in out:
            out.append(name)
    return out


def _safe(client, query, who, failed):
    try:
        return client.search(query)
    except Exception as e:  # one bad search must not stop the report
        if failed is not None and who not in failed:
            failed.append(who)
        print(f"  search failed for {who}: {str(e)[:80]}", flush=True)
        return []


def find_papers(orders: pd.DataFrame, s: dict, client, progress=None, failed=None) -> list[dict]:
    people = people_from_orders(orders, s)
    lab = {}
    for p in people:
        lab.setdefault(p["group"], []).append(p)
    args = [(p["last"], p["first"], p["start"], p["end"]) for p in people]
    if hasattr(client, "prefetch"):
        client.prefetch([technique_query(*a, s) for a in args])
    kept = []  # (person, args, papers)
    for i, (person, a) in enumerate(zip(people, args)):
        if progress:
            progress(i, len(people), person)
        who = f"{person['last']} {person['first']} ({person['group']})"
        papers = [x for x in _safe(client, technique_query(*a, s), who, failed)
                  if _keep(x, person, lab[person["group"]], s)]
        if papers:
            kept.append((person, a, papers))
    lists = [k for k in ("core_names", "other_facilities") if s[k]]
    if hasattr(client, "prefetch"):
        client.prefetch([named_query(*a, s, k) for _, a, _ in kept for k in lists])
    found = {}  # (group, paper id) -> row
    for person, a, papers in kept:
        who = f"{person['last']} {person['first']} ({person['group']})"
        named_ids = ({x.get("id") for x in _safe(client, named_query(*a, s), who, failed)}
                     if s["core_names"] else set())
        other_ids = ({x.get("id") for x in _safe(client, named_query(*a, s, "other_facilities"), who, failed)}
                     if s["other_facilities"] else set())
        for paper in papers:
            key = (person["group"], paper.get("id"))
            who = f"{person['last']} {person['first'][:1]} ({person['role']})"
            status = (NAMED if paper.get("id") in named_ids else OTHER if paper.get("id") in other_ids
                      else NOT_NAMED if paper.get("inEPMC") == "Y" else CANT_CHECK)
            if key in found:
                if who not in found[key]["matched"]:
                    found[key]["matched"] += f"; {who}"
                if RANK[status] > RANK[found[key]["status"]]:
                    found[key]["status"] = status
                continue
            g = orders[(orders["group"] == person["group"]) & orders["is_revenue"]]
            pid = paper.get("pmid") or paper.get("id")
            src = paper.get("source", "MED")
            found[key] = {
                "group": person["group"], "matched": who, "date": paper.get("firstPublicationDate", ""),
                "title": re.sub(r"<[^>]+>", "", html.unescape(paper.get("title", ""))),
                "journal": ((paper.get("journalInfo") or {}).get("journal") or {}).get("title", "")
                or ("Preprint" if src == "PPR" else ""),
                "pmid": paper.get("pmid") or "", "pmcid": paper.get("pmcid") or "", "doi": paper.get("doi") or "",
                "link": f"https://europepmc.org/article/{src}/{pid}", "status": status,
                "lab_orders": f"{g['ordered'].min():%Y-%m-%d} → {g['ordered'].max():%Y-%m-%d}",
                "preprint": src == "PPR", "staff": "; ".join(staff_authors(paper, s))}
    return sorted(found.values(), key=lambda r: (r["group"].casefold(), r["date"]))


# ---------- papers outside PubMed (Crossref) ----------

def crossref_paper(item: dict) -> dict:
    """A Crossref work in the shape the matching code reads (Europe PMC's)."""
    parts = ((item.get("issued") or item.get("published") or {}).get("date-parts") or [[]])[0] or []
    when = "-".join(f"{int(x):02d}" for x in (list(parts) + [1, 1])[:3]) if parts else ""
    authors = [{"lastName": a.get("family", ""), "firstName": a.get("given", ""),
                "initials": (a.get("given") or " ")[0],
                "authorAffiliationDetailsList": {"authorAffiliation": [
                    {"affiliation": str(x.get("name", ""))[:300]} for x in (a.get("affiliation") or [])[:6]]}}
               for a in item.get("author") or []]
    kind = str(item.get("type", ""))
    return {"id": item.get("DOI", ""), "source": "CR", "doi": item.get("DOI", ""),
            "title": re.sub(r"<[^>]+>", "", " ".join(item.get("title") or [])), "firstPublicationDate": when,
            "inEPMC": "N", "pubTypeList": {"pubType": ["review" if "review" in kind else kind]},
            "journalInfo": {"journal": {"title": " ".join(item.get("container-title") or [])}},
            "authorList": {"author": authors}}


SKIP_TYPES = {"peer-review", "component", "dataset", "posted-content", "grant", "book", "book-set"}


def crossref_pairs(orders: pd.DataFrame, s: dict) -> list[tuple[dict, dict]]:
    """(PI, submitter) for every submitter: Crossref's author search is fuzzy, so both names go in one query
    and only papers with both as authors are kept."""
    people = people_from_orders(orders, s)
    pi = {p["group"]: p for p in people if p["role"] == "PI"}
    return [(pi[p["group"]], p) for p in people if p["role"] == "submitter" and p["group"] in pi]


def _journal_key(t):
    """Journal names as Crossref and Europe PMC both spell them: no leading 'The', nothing after ':'."""
    t = html.unescape(str(t)).split(":")[0]
    t = re.sub(r"\W+", " ", t).strip().casefold()
    return re.sub(r"^the ", "", t)


def find_outside_pubmed(orders: pd.DataFrame, s: dict, crossref, epmc, found: list[dict], progress=None,
                        failed=None, indexed_journals=(), today=None) -> list[dict]:
    """Papers by a lab's PI and a submitter together that Europe PMC doesn't have: journals PubMed doesn't
    index, and papers too new to be indexed. Their methods can't be searched, so they go to the full-text
    step. Items in journals Europe PMC does index, older than 90 days, are meeting abstracts: left out."""
    people = people_from_orders(orders, s)
    lab = {}
    for p in people:
        lab.setdefault(p["group"], []).append(p)
    indexed = {_journal_key(j) for j in indexed_journals}
    recent = f"{(today or date.today()) - timedelta(days=90):%Y-%m-%d}"
    seen = {str(r.get("doi") or "").casefold() for r in found if r.get("doi")}
    cands = {}  # doi -> (person, paper)
    pairs = crossref_pairs(orders, s)
    for i, (pi, sub) in enumerate(pairs):
        if progress:
            progress(i, len(pairs), sub)
        try:
            papers = crossref.search([(pi["last"], pi["first"]), (sub["last"], sub["first"])], sub["start"], sub["end"])
        except Exception as e:
            if failed is not None:
                failed.append(f"{sub['last']} {sub['first']} (Crossref)")
            print(f"  Crossref search failed for {sub['group']}: {str(e)[:80]}", flush=True)
            continue
        for paper in papers:
            doi = str(paper.get("doi") or "").casefold()
            kind = (paper.get("pubTypeList") or {}).get("pubType", [""])[0]
            if not doi or doi in seen or doi in cands or kind in SKIP_TYPES:
                continue
            if _journal_key(paper["journalInfo"]["journal"]["title"]) in indexed and \
                    paper["firstPublicationDate"] < recent:
                continue
            if _keep(paper, sub, lab[sub["group"]], s):
                cands[doi] = (sub, paper)
    known = set()  # DOIs Europe PMC has: the technique search already judged them
    dois = list(cands)
    for i in range(0, len(dois), 20):
        q = " OR ".join(f'DOI:"{d}"' for d in dois[i:i + 20])
        try:
            known |= {str(x.get("doi") or "").casefold() for x in epmc.search(q)}
        except Exception:
            known |= set(dois[i:i + 20])  # unsure: leave them out rather than list papers twice
    rows = []
    for doi, (person, paper) in cands.items():
        if doi in known:
            continue
        g = orders[(orders["group"] == person["group"]) & orders["is_revenue"]]
        rows.append({"group": person["group"], "matched": f"{person['last']} {person['first'][:1]} (submitter, with PI)",
                     "date": paper["firstPublicationDate"], "title": paper["title"],
                     "journal": paper["journalInfo"]["journal"]["title"], "pmid": "", "pmcid": "",
                     "doi": paper["doi"], "link": f"https://doi.org/{paper['doi']}", "status": OUTSIDE,
                     "lab_orders": f"{g['ordered'].min():%Y-%m-%d} → {g['ordered'].max():%Y-%m-%d}",
                     "preprint": False, "staff": "; ".join(staff_authors(paper, s))})
    return sorted(rows, key=lambda r: (r["group"].casefold(), r["date"]))


def follow_up(orders: pd.DataFrame, rows: list[dict], s: dict, as_of=None) -> pd.DataFrame:
    o = orders[orders["is_revenue"]]
    as_of = pd.Timestamp(as_of or o["ordered"].max())
    cutoff = as_of - pd.DateOffset(years=s["follow_up_years"])
    out = []
    for group, g in o.groupby("group"):
        last = g["ordered"].max()
        if last < cutoff:
            continue
        later = [r for r in rows if r["group"] == group and str(r["date"]) >= f"{last:%Y-%m-%d}"
                 and r["status"] != OUTSIDE]  # unchecked papers outside PubMed don't count until read
        if later:
            continue
        out.append({"group": group, "submitters": "; ".join(sorted(set(g["user"]) - {""})),
                    "first_order": f"{g['ordered'].min():%Y-%m-%d}", "last_order": f"{last:%Y-%m-%d}",
                    "services": "; ".join(g["service"].value_counts().index[:4]),
                    "papers_before": sum(r["group"] == group and r["status"] != OUTSIDE for r in rows)})
    cols = ["group", "submitters", "first_order", "last_order", "services", "papers_before"]
    return pd.DataFrame(out, columns=cols).sort_values("last_order", ascending=False).reset_index(drop=True)


# ---------- full-text review ----------

REVIEW_STATUSES = (NOT_NAMED, OTHER, CANT_CHECK, OUTSIDE)
REVIEW_COLS = {"verdict": "Review", "confidence": "Confidence", "where": "Where the work was done",
               "evidence": "Evidence", "action": "Action"}


def row_key(r: dict) -> str:
    """One key per paper, shared by every lab it was found under."""
    return str(r.get("pmid") or r.get("pmcid") or str(r.get("doi") or "").casefold() or re.sub(r"\W+", " ", str(r.get("title", ""))).strip().casefold())


def review_records(rows: list[dict]) -> list[dict]:
    """Papers to read in full: flagged, naming another facility, or not checkable. One record per paper."""
    recs = {}
    for r in rows:
        if r["status"] not in REVIEW_STATUSES:
            continue
        k = row_key(r)
        if k in recs:
            if r["group"] not in recs[k]["lab"]:
                recs[k]["lab"] += f"; {r['group']}"
            continue
        recs[k] = {"key": k, "lab": r["group"], "matched": r["matched"], "date": r["date"], "title": r["title"],
                   "journal": r["journal"], "pmid": r.get("pmid", ""), "pmcid": r.get("pmcid", ""),
                   "doi": r.get("doi", ""), "link": r.get("link", ""), "lab_orders": r["lab_orders"],
                   "status": r["status"]}
    out = list(recs.values())
    for i, r in enumerate(out, 1):
        r["n"] = i
    return out


def load_review(folder) -> dict:
    """Verdicts keyed by paper: earlier rounds (reviewed.json) plus the current round's verdict*.json files,
    numbered through index.json."""
    from .fulltext import load_verdicts
    folder = Path(folder)
    out = json.loads((folder / "reviewed.json").read_text()) if (folder / "reviewed.json").exists() else {}
    idx = folder / "index.json"
    if idx.exists():
        keys = {int(k): v for k, v in json.loads(idx.read_text()).items()}
        out.update({keys[n]: v for n, v in load_verdicts(folder).items() if n in keys})
    return out


def keep_review(folder, extra: dict | None = None) -> dict:
    """Fold the current round's verdicts (and any extra ones) into reviewed.json, so a new round of
    --excerpts never loses them. Returns everything reviewed so far."""
    folder = Path(folder)
    done = {**load_review(folder), **(extra or {})}
    if done:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "reviewed.json").write_text(json.dumps(done, ensure_ascii=False, indent=1))
    return done


# ---------- were the methods the core's? ----------

MC_CORE = "Grant line present: the core's methods"
MC_NOT = "No grant line: methods probably not the core's"
MC_VAGUE = "No instrument named: methods probably not the core's"
MC_CANT = "Can't tell"


def credited(rows: list[dict], verdicts: dict | None) -> list[dict]:
    """Rows that credit the core: a full-text review found they credit it, or (not reviewed) they name it."""
    v = verdicts or {}
    out = []
    for r in rows:
        verdict = (v.get(row_key(r)) or {}).get("verdict")
        if verdict == "credits_core" or (not verdict and r["status"] == NAMED):
            out.append(r)
    return out


def load_methods_reviews(folder) -> dict:
    """Reviewers' answers from paper_review/methods_review*.json: key -> {our_core, methods, confidence, evidence}."""
    out = {}
    for p in sorted(Path(folder).glob("methods_review*.json")):
        for r in json.loads(p.read_text()):
            if r.get("key"):
                out[str(r["key"])] = r
    return out


def verdicts_from_reviews(reviews: dict, verdicts: dict) -> dict:
    """A paper a reviewer found credits another institution's facility (a generic name like "Proteomics Core"
    matched) gets an other_facility verdict, unless it already has a full-text verdict."""
    out = dict(verdicts or {})
    for k, r in (reviews or {}).items():
        if r.get("our_core") == "no" and k not in out:
            out[k] = {"verdict": "other_facility", "confidence": r.get("confidence", ""), "where": "",
                      "evidence": f"Credits another institution's facility: {r.get('evidence', '')}",
                      "action": "No action"}
    return out


def classify_methods(recs: list[dict], reviews: dict | None = None) -> dict:
    """Judge each credited paper's methods by the core's instrument-grant lines (core_grants).

    Only a paper that names a grant-funded instrument, dated on or after the first paper in this set that
    carries that instrument's grant line, is judged. Other instruments, earlier papers and papers without
    free full text are "Can't tell": a missing line there says nothing about who wrote the methods."""
    since = {}
    for r in recs:
        for i in r.get("grant_lines") or []:
            since[i] = min(since.get(i, "9999"), str(r.get("date", "")))
    out = {}
    for r in recs:
        d, gi, gl = str(r.get("date", "")), r.get("grant_instruments") or [], r.get("grant_lines") or []
        if r.get("error"):
            res = (f"{MC_CANT}: no free full text", "")
        elif gl:
            res = (MC_CORE, ", ".join(gl))
        elif gi:
            judged = [i for i in gi if i in since and d >= since[i]]
            res = ((MC_NOT, "; ".join(f"{i} named, no grant line (the core's papers carry it since "
                                      f"{since[i][:7]})" for i in judged)) if judged else
                   (f"{MC_CANT}: before the grant line appears in these papers", ", ".join(gi)))
        elif r.get("n_ms_paragraphs") and not r.get("instruments"):
            res = (MC_VAGUE, "Mass spec described without naming any instrument")
        elif not r.get("n_ms_paragraphs"):
            res = (f"{MC_CANT}: no mass spec methods found", "")
        else:
            res = (f"{MC_CANT}: instrument has no grant line", ", ".join(r.get("instruments") or []))
        rv = (reviews or {}).get(r["key"]) or {}
        read = {"core_written": MC_CORE, "not_core_written": MC_NOT, "unclear": f"{MC_CANT}: read, unclear",
                "no_ms": f"{MC_CANT}: the core's work wasn't mass spec"}.get(rv.get("methods"))
        if read:
            res = (read, f"Read: {rv.get('evidence', '')}")
        out[r["key"]] = {"methods": res[0], "methods_detail": res[1]}
    return out


# ---------- output ----------

COLS = {"group": "Lab (PPMS group)", "matched": "Matched author", "date": "Published", "title": "Title",
        "journal": "Journal", "pmid": "PMID", "pmcid": "PMCID", "link": "Link", "status": "Status",
        "lab_orders": "Lab's orders"}


def write_workbook(rows, fu: pd.DataFrame, s: dict, path, verdicts: dict | None = None,
                   methods: dict | None = None) -> None:
    s = settings(s)
    df = pd.DataFrame(rows, columns=list(COLS) + ["preprint", "staff"])
    df["staff"] = df["staff"].fillna("")
    cols = dict(COLS)
    if s["core_staff"]:
        cols["staff"] = "Core staff authors"
    keys_all = [row_key(r) for r in rows]
    if methods:
        for k in ("methods", "methods_detail"):
            df[k] = [str((methods.get(key) or {}).get(k, "")) for key in keys_all]
        cols.update({"methods": "Methods", "methods_detail": "Methods detail"})
    if verdicts:
        keys = [row_key(r) for r in rows]
        for k in REVIEW_COLS:
            df[k] = [str((verdicts.get(key) or {}).get(k, "")) for key in keys]
        cols.update(REVIEW_COLS)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    about = pd.DataFrame({"": [
        "Papers by the core's customers that may use the core's data. A paper is listed when a lab's PI or "
        "a submitter from the lab is an author, it was published between the lab's first order and "
        f"{s['years_after']} years after its last, it is not a review, its methods, abstract or title mention "
        f"one of: {', '.join(s['technique_terms'])}, and the author is at {s['institution']} or the PI and "
        "a submitter are both authors.",
        f"'{NAMED}': the record or full text contains one of: {', '.join(s['core_names'])}.",
        f"'{NOT_NAMED}': the full text is in Europe PMC and contains none of those names. The lab may have "
        "used another facility; check before contacting them.",
        f"'{CANT_CHECK}': only the abstract is free to search. Read the paper.",
        f"'{OUTSIDE}': a paper by the lab's PI and a submitter (or at {s['institution']}) in a journal "
        "PubMed doesn't index, or too new to be indexed, found through Crossref. Its methods can't be searched, "
        "so it may have nothing to do with the core: read it.",
        f"'{OTHER}': names one of {', '.join(s['other_facilities']) or '(none set)'} and not this core; the lab "
        "probably used that facility.",
        f"Follow up: labs with orders in the last {s['follow_up_years']} years of the export and no matching "
        "paper since their last order.",
        "Credited, no staff author: papers that name or credit the core with none of "
        f"{', '.join(s['core_staff']) or '(core_staff not set)'} among the authors.",
        "Methods not the core's (from --methods-check): credited papers that name a grant-funded instrument "
        "without its acknowledgment, or describe mass spec without naming an instrument. Only judged for "
        "grant-funded instruments and dates on or after the first paper carrying that grant line; read the "
        "methods before contacting the lab.",
        "Sources: Europe PMC (europepmc.org), which includes all of PubMed, and Crossref (crossref.org). Contains lab and person names: "
        "keep inside the core.",
        f"Built {date.today():%Y-%m-%d}."]})
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        if verdicts:
            ask = df[df["action"].str.startswith("Ask")].drop_duplicates("title")
            ask[list(cols)].rename(columns=cols).to_excel(xw, sheet_name="Ask the lab", index=False)
        for sheet, st in [("Core not named", NOT_NAMED), ("Can't check", CANT_CHECK),
                          ("Names another facility", OTHER), ("Names the core", NAMED),
                          ("Not in PubMed", OUTSIDE)]:
            df[df["status"] == st][list(cols)].rename(columns=cols).to_excel(xw, sheet_name=sheet, index=False)
        cred = {id(r) for r in credited(rows, verdicts)}
        is_cred = pd.Series([id(r) in cred for r in rows], index=df.index, dtype=bool)
        if s["core_staff"]:
            df[is_cred & (df["staff"] == "")].drop_duplicates("title")[list(cols)].rename(columns=cols).to_excel(
                xw, sheet_name="Credited, no staff author", index=False)
        if methods:
            flag = df["methods"].isin([MC_NOT, MC_VAGUE])
            df[is_cred & flag].drop_duplicates("title")[list(cols)].rename(columns=cols).to_excel(
                xw, sheet_name="Methods not the core's", index=False)
        fu.rename(columns={"group": "Lab (PPMS group)", "submitters": "Submitters", "first_order": "First order",
                           "last_order": "Last order", "services": "Services",
                           "papers_before": "Earlier matching papers"}).to_excel(xw, sheet_name="Follow up",
                                                                                 index=False)
        about.to_excel(xw, sheet_name="About", index=False, header=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                width = min(max(len(str(c.value or "")) for c in col) + 2, 70)
                ws.column_dimensions[col[0].column_letter].width = width


# ---------- Crossref client ----------

class Crossref:
    """Crossref works by author name and publication window, with a JSON cache. No key needed."""
    API = "https://api.crossref.org/works"

    def __init__(self, cache_path=None, pause=0.2):
        self.cache_path = Path(cache_path) if cache_path else None
        self.cache = json.loads(self.cache_path.read_text()) if self.cache_path and self.cache_path.exists() else {}
        self.pause = pause

    @staticmethod
    def key(names, start, end):
        return " + ".join(f"{f} {l}".strip() for l, f in names) + f"|{start:%Y-%m-%d}|{end:%Y-%m-%d}"

    def search(self, names, start, end, rows=100) -> list[dict]:
        """Works with every one of names [(last, first), ...] as an author, published in [start, end]."""
        key = self.key(names, start, end)
        if key not in self.cache:
            params = {"query.author": " ".join(f"{f} {l}".strip() for l, f in names), "rows": rows,
                      "filter": f"from-pub-date:{start:%Y-%m-%d},until-pub-date:{end:%Y-%m-%d}",
                      "select": "DOI,type,title,container-title,issued,author"}
            req = urllib.request.Request(f"{self.API}?{urllib.parse.urlencode(params)}",
                                         headers={"User-Agent": "ucd-core-financials"})
            for attempt in range(4):
                try:
                    d = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
                    break
                except Exception:
                    if attempt == 3:
                        raise
                    time.sleep(2 ** attempt * 3)
            want = {l.casefold() for l, _ in names}
            self.cache[key] = [crossref_paper(i) for i in d.get("message", {}).get("items", [])
                               if want <= {(a.get("family") or "").casefold() for a in i.get("author") or []}]
            time.sleep(self.pause)
        return self.cache[key]

    def prefetch(self, pairs, workers=2):
        from concurrent.futures import ThreadPoolExecutor
        jobs = [([(a["last"], a["first"]), (b["last"], b["first"])], b["start"], b["end"]) for a, b in pairs]
        todo = list({self.key(*j): j for j in jobs if self.key(*j) not in self.cache}.values())

        def one(j):
            try:
                self.search(*j)
            except Exception as e:
                print(f"  Crossref search failed, will retry on the next run: {str(e)[:80]}", flush=True)
        with ThreadPoolExecutor(workers) as ex:
            for n, _ in enumerate(ex.map(one, todo), 1):
                if n % 100 == 0:
                    print(f"  {n}/{len(todo)} Crossref searches", flush=True)
                    self.save()
        self.save()

    def save(self):
        if self.cache_path:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.cache))
            tmp.replace(self.cache_path)


# ---------- Europe PMC client ----------

def compact(r: dict) -> dict:
    """Keep only what the report reads; author lists of big consortium papers are otherwise huge."""
    out = {k: r.get(k) for k in ("id", "source", "pmid", "pmcid", "doi", "title", "firstPublicationDate", "inEPMC",
                                 "pubTypeList")}
    out["journalInfo"] = {"journal": {"title": ((r.get("journalInfo") or {}).get("journal") or {}).get("title", "")}}
    authors = []
    for a in (r.get("authorList") or {}).get("author") or []:
        c = {k: a.get(k) for k in ("lastName", "firstName", "initials")}
        affs = [x.get("affiliation", "")[:300] for x in (a.get("authorAffiliationDetailsList") or {}).get(
            "authorAffiliation", [])[:6]]
        c["authorAffiliationDetailsList"] = {"authorAffiliation": [{"affiliation": x} for x in affs]}
        authors.append(c)
    out["authorList"] = {"author": authors}
    return out


def _read_cache(path) -> dict:
    """A JSON cache, gzipped when the name ends in .gz; a .gz cache not written yet starts from the old
    uncompressed file of the same name, if there is one."""
    if not path:
        return {}
    if path.exists():
        b = path.read_bytes()
        return json.loads(gzip.decompress(b) if path.suffix == ".gz" else b)
    plain = path.with_suffix("") if path.suffix == ".gz" else None
    return json.loads(plain.read_text()) if plain and plain.exists() else {}


class EuropePMC:
    """Search with a JSON cache, so re-runs and interrupted runs don't repeat queries."""

    def __init__(self, cache_path=None, pause=0.1):
        self.cache_path = Path(cache_path) if cache_path else None
        self.cache = _read_cache(self.cache_path)
        self.pause, self.truncated = pause, []
        self.used = set()  # only searches this run used are saved, so old date windows don't pile up

    def search(self, query: str, max_results: int = 1000) -> list[dict]:
        self.used.add(query)
        if query in self.cache:
            return self.cache[query]
        results, cursor = [], "*"
        while True:
            params = {"query": query, "format": "json", "resultType": "core", "pageSize": 1000, "cursorMark": cursor}
            req = urllib.request.Request(f"{API}?{urllib.parse.urlencode(params)}",
                                         headers={"User-Agent": "ucd-core-financials"})
            for attempt in range(4):
                try:
                    d = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
                    break
                except Exception:
                    if attempt == 3:
                        raise
                    time.sleep(2 ** attempt)
            page = d.get("resultList", {}).get("result", [])
            results += [compact(r) for r in page]
            if int(d.get("hitCount") or 0) > max_results and query not in self.truncated:
                self.truncated.append(query)
            nxt = d.get("nextCursorMark")
            if not page or not nxt or nxt == cursor or len(results) >= max_results:
                break
            cursor = nxt
            time.sleep(self.pause)
        self.cache[query] = results
        time.sleep(self.pause)
        return results

    def prefetch(self, queries, workers=6):
        """Run uncached queries in parallel, then save the cache."""
        from concurrent.futures import ThreadPoolExecutor
        queries = list(queries)
        self.used.update(queries)
        todo = list(dict.fromkeys(q for q in queries if q not in self.cache))
        done = 0
        with ThreadPoolExecutor(workers) as ex:
            for _ in ex.map(self._fetch_into_cache, todo):
                done += 1
                if done % 100 == 0:
                    print(f"  {done}/{len(todo)} searches", flush=True)
                    self.save()
        self.save()

    def _fetch_into_cache(self, q):
        try:
            self.search(q)
        except Exception as e:  # one failed search must not stop the run; it is retried next time
            print(f"  search failed, will retry on the next run: {str(e)[:80]}", flush=True)

    def save(self):
        if self.cache_path:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_path.with_suffix(".tmp")
            keep = {k: v for k, v in dict(self.cache).items() if k in self.used} if self.used else dict(self.cache)
            data = json.dumps(keep).encode()
            tmp.write_bytes(gzip.compress(data, 6) if self.cache_path.suffix == ".gz" else data)
            tmp.replace(self.cache_path)
            if self.cache_path.suffix == ".gz":
                self.cache_path.with_suffix("").unlink(missing_ok=True)  # the old uncompressed cache
