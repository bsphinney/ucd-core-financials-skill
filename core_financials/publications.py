"""Papers by the core's customers that may use the core's data, and whether they name the core.

Uses Europe PMC (all of PubMed plus open-access and NIH full text, searchable by section). This is the
only part of the skill that goes online: it sends author names to a public literature search. It is
never run by `build`.
"""
from __future__ import annotations

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
API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
DEFAULTS = {"core_names": [], "other_facilities": [], "technique_terms": [], "institution": "Davis", "years_after": 3, "follow_up_years": 3}


def settings(raw: dict | None, core_name: str = "") -> dict:
    s = {**DEFAULTS, **(raw or {})}
    s["core_names"] = [str(x) for x in (s["core_names"] or ([core_name] if core_name else []))]
    s["technique_terms"] = [str(x) for x in s["technique_terms"] or []]
    s["other_facilities"] = [str(x) for x in s["other_facilities"] or []]
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


def parse_user(name: str) -> tuple[str, str]:
    """PPMS user 'Last First' -> (last, first)."""
    parts = re.sub(r"\(.*?\)", "", str(name)).split()
    if "," in str(name):
        return parse_group(name)
    return (parts[0], parts[1]) if len(parts) > 1 else ((parts or [""])[0], "")


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
    return f'{field}:"{t}"' if " " in t or "-" in t or "/" in t else f"{field}:{t}"


def _base(last, first, start, end):
    au = f"{last} {first[:1]}".strip()
    return f'AUTH:"{au}" AND FIRST_PDATE:[{start:%Y-%m-%d} TO {end:%Y-%m-%d}]'


def technique_query(last, first, start, end, s) -> str:
    terms = " OR ".join(_term(f, t) for t in s["technique_terms"] for f in ("METHODS", "ABSTRACT", "TITLE"))
    return f"{_base(last, first, start, end)} AND ({terms})"


def named_query(last, first, start, end, s, key="core_names") -> str:
    names = " OR ".join(f'"{n}"' for n in s[key])
    return f"{technique_query(last, first, start, end, s)} AND ({names})"


# ---------- matching ----------

def _authors(p):
    return (p.get("authorList") or {}).get("author") or []


def _affs(a):
    return " ".join(x.get("affiliation", "") for x in (a.get("authorAffiliationDetailsList") or {}).get(
        "authorAffiliation", []))


def _is(a, last, first):
    if (a.get("lastName") or "").casefold() != last.casefold():
        return False
    given = (a.get("firstName") or a.get("initials") or "")
    return not first or given[:1].casefold() == first[:1].casefold()


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
    others = [q for q in lab_people if q is not person]
    return any(_is(a, q["last"], q["first"]) for q in others for a in _authors(paper))


def find_papers(orders: pd.DataFrame, s: dict, client, progress=None) -> list[dict]:
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
        papers = [x for x in client.search(technique_query(*a, s)) if _keep(x, person, lab[person["group"]], s)]
        if papers:
            kept.append((person, a, papers))
    lists = [k for k in ("core_names", "other_facilities") if s[k]]
    if hasattr(client, "prefetch"):
        client.prefetch([named_query(*a, s, k) for _, a, _ in kept for k in lists])
    found = {}  # (group, paper id) -> row
    for person, a, papers in kept:
        named_ids = {x.get("id") for x in client.search(named_query(*a, s))} if s["core_names"] else set()
        other_ids = ({x.get("id") for x in client.search(named_query(*a, s, "other_facilities"))}
                     if s["other_facilities"] else set())
        for paper in papers:
            key = (person["group"], paper.get("id"))
            who = f"{person['last']} {person['first'][:1]} ({person['role']})"
            if key in found:
                if who not in found[key]["matched"]:
                    found[key]["matched"] += f"; {who}"
                if paper.get("id") in named_ids:
                    found[key]["status"] = NAMED
                continue
            status = (NAMED if paper.get("id") in named_ids else OTHER if paper.get("id") in other_ids
                      else NOT_NAMED if paper.get("inEPMC") == "Y" else CANT_CHECK)
            g = orders[(orders["group"] == person["group"]) & orders["is_revenue"]]
            pid = paper.get("pmid") or paper.get("id")
            src = paper.get("source", "MED")
            found[key] = {
                "group": person["group"], "matched": who, "date": paper.get("firstPublicationDate", ""),
                "title": re.sub(r"<[^>]+>", "", paper.get("title", "")),
                "journal": ((paper.get("journalInfo") or {}).get("journal") or {}).get("title", "")
                or ("Preprint" if src == "PPR" else ""),
                "pmid": paper.get("pmid") or "", "pmcid": paper.get("pmcid") or "",
                "link": f"https://europepmc.org/article/{src}/{pid}", "status": status,
                "lab_orders": f"{g['ordered'].min():%Y-%m-%d} → {g['ordered'].max():%Y-%m-%d}",
                "preprint": src == "PPR"}
    return sorted(found.values(), key=lambda r: (r["group"].casefold(), r["date"]))


def follow_up(orders: pd.DataFrame, rows: list[dict], s: dict, as_of=None) -> pd.DataFrame:
    o = orders[orders["is_revenue"]]
    as_of = pd.Timestamp(as_of or o["ordered"].max())
    cutoff = as_of - pd.DateOffset(years=s["follow_up_years"])
    out = []
    for group, g in o.groupby("group"):
        last = g["ordered"].max()
        if last < cutoff:
            continue
        later = [r for r in rows if r["group"] == group and str(r["date"]) >= f"{last:%Y-%m-%d}"]
        if later:
            continue
        out.append({"group": group, "submitters": "; ".join(sorted(set(g["user"]) - {""})),
                    "first_order": f"{g['ordered'].min():%Y-%m-%d}", "last_order": f"{last:%Y-%m-%d}",
                    "services": "; ".join(g["service"].value_counts().index[:4]),
                    "papers_before": sum(r["group"] == group for r in rows)})
    cols = ["group", "submitters", "first_order", "last_order", "services", "papers_before"]
    return pd.DataFrame(out, columns=cols).sort_values("last_order", ascending=False).reset_index(drop=True)


# ---------- output ----------

COLS = {"group": "Lab (PPMS group)", "matched": "Matched author", "date": "Published", "title": "Title",
        "journal": "Journal", "pmid": "PMID", "pmcid": "PMCID", "link": "Link", "status": "Status",
        "lab_orders": "Lab's orders"}


def write_workbook(rows, fu: pd.DataFrame, s: dict, path) -> None:
    df = pd.DataFrame(rows, columns=list(COLS) + ["preprint"])
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
        f"'{OTHER}': names one of {', '.join(s['other_facilities']) or '(none set)'} and not this core; the lab "
        "probably used that facility.",
        f"Follow up: labs with orders in the last {s['follow_up_years']} years of the export and no matching "
        "paper since their last order.",
        "Source: Europe PMC (europepmc.org), which includes all of PubMed. Contains lab and person names: "
        "keep inside the core.",
        f"Built {date.today():%Y-%m-%d}."]})
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        for sheet, st in [("Core not named", NOT_NAMED), ("Can't check", CANT_CHECK),
                          ("Names another facility", OTHER), ("Names the core", NAMED)]:
            df[df["status"] == st][list(COLS)].rename(columns=COLS).to_excel(xw, sheet_name=sheet, index=False)
        fu.rename(columns={"group": "Lab (PPMS group)", "submitters": "Submitters", "first_order": "First order",
                           "last_order": "Last order", "services": "Services",
                           "papers_before": "Earlier matching papers"}).to_excel(xw, sheet_name="Follow up",
                                                                                 index=False)
        about.to_excel(xw, sheet_name="About", index=False, header=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                width = min(max(len(str(c.value or "")) for c in col) + 2, 70)
                ws.column_dimensions[col[0].column_letter].width = width


# ---------- Europe PMC client ----------

def compact(r: dict) -> dict:
    """Keep only what the report reads; author lists of big consortium papers are otherwise huge."""
    out = {k: r.get(k) for k in ("id", "source", "pmid", "pmcid", "title", "firstPublicationDate", "inEPMC",
                                 "pubTypeList")}
    out["journalInfo"] = {"journal": {"title": ((r.get("journalInfo") or {}).get("journal") or {}).get("title", "")}}
    authors = []
    for a in (r.get("authorList") or {}).get("author") or []:
        c = {k: a.get(k) for k in ("lastName", "firstName", "initials")}
        affs = [x.get("affiliation", "")[:300] for x in (a.get("authorAffiliationDetailsList") or {}).get(
            "authorAffiliation", [])[:1]]
        c["authorAffiliationDetailsList"] = {"authorAffiliation": [{"affiliation": x} for x in affs]}
        authors.append(c)
    out["authorList"] = {"author": authors}
    return out


class EuropePMC:
    """Search with a JSON cache, so re-runs and interrupted runs don't repeat queries."""

    def __init__(self, cache_path=None, pause=0.1):
        self.cache_path = Path(cache_path) if cache_path else None
        self.cache = json.loads(self.cache_path.read_text()) if self.cache_path and self.cache_path.exists() else {}
        self.pause = pause

    def search(self, query: str, max_results: int = 1000) -> list[dict]:
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
            tmp.write_text(json.dumps(dict(self.cache)))
            tmp.replace(self.cache_path)
