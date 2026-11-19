"""Full text for flagged papers, cut down to the parts that say where the mass spec was done.

Sources, in order: Europe PMC full-text XML, NCBI PubMed Central (efetch), the PMC web page, then free
copies listed by OpenAlex (preprints, repositories, author manuscripts). Publisher sites behind bot checks
are not used. Claude reads the excerpts and records a verdict per paper (reference/paper-review.md).
"""
from __future__ import annotations

import html
import io
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

MS = re.compile(r"mass spectromet|LC-MS|LC–MS|nanoLC|Orbitrap|timsTOF|Q Exactive|Q-Exactive|Lumos|Exploris|"
                r"proteomic|tryptic|trypsin|DIA-NN|MaxQuant|Spectronaut|FragPipe|Proteome Discoverer|S-Trap|"
                r"confocal|microscop|sequenc|flow cytometr", re.I)
WHERE = re.compile(r"core|facility|facilities|center|centre|service|inc\.|ltd|company|performed (by|at)|"
                   r"in-house|our laborator|our lab", re.I)
INSTR = re.compile(r"timsTOF[\w ]{0,8}|Orbitrap (Fusion )?Lumos|Fusion Lumos|Q[ -]Exactive[\w ]{0,8}|Exploris \d+|"
                   r"Orbitrap (Eclipse|Astral|Elite|Velos|Fusion)|Synapt|TripleTOF|QTRAP|Xevo|Agilent 6\d{3}", re.I)
UA = {"User-Agent": "Mozilla/5.0 (compatible; ucd-core-financials)"}
VERDICTS = ["likely_core", "credits_core", "other_facility", "in_house", "no_new_proteomics", "unclear"]
_lock = threading.Lock()
_last = [0.0]


def _text(x: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip()


def _common(alltext: str, institution: str, core_words: list[str]) -> dict:
    words = "|".join(re.escape(w) for w in [institution, *core_words] if w) or "Davis"
    sents = re.split(r"(?<=[.;])\s", alltext)
    return {"instruments": sorted({m.group(0).strip() for m in INSTR.finditer(alltext)})[:8],
            "facility_sentences": [s[:400] for s in sents
                                   if re.search(rf"{words}|(core|facility|center)\b", s, re.I)
                                   and MS.search(s)][:6]}


def terms_regex(terms) -> re.Pattern:
    """A core's technique terms (config) as one pattern; '*' is a prefix wildcard."""
    parts = [re.escape(str(t).rstrip("*")) for t in terms if str(t).strip("*")]
    return re.compile("|".join(parts), re.I) if parts else MS


def excerpts_from_xml(x: str, institution: str = "Davis", core_words=(), ms=MS) -> dict:
    body = x.split("<body", 1)[1] if "<body" in x else x
    body = body.split("</body>", 1)[0]
    paras = [_text(p) for p in re.findall(r"<p[ >].*?</p>", body, re.S)]
    ms_paras = sorted((p for p in paras if ms.search(p)),
                key=lambda p: -(2 * bool(WHERE.search(p)) + bool(INSTR.search(p))))
    contrib = [_text(f) for f in re.findall(
        r"<(?:fn|sec)[^>]*>(?:(?!</(?:fn|sec)>).)*?(?:contribution|CRediT)(?:(?!</(?:fn|sec)>).)*?</(?:fn|sec)>",
        x, re.S | re.I)]
    return {"ms_paragraphs": [p[:900] for p in ms_paras[:5]], "n_ms_paragraphs": len(ms_paras),
            "acknowledgments": _text(" ".join(re.findall(r"<ack.*?</ack>", x, re.S)))[:1500],
            "funding": _text(" ".join(re.findall(r"<funding-group.*?</funding-group>", x, re.S)))[:400],
            "author_contributions": " ".join(contrib)[:700],
            **_common(_text(body), institution, list(core_words))}


def excerpts_from_text(t: str, institution: str = "Davis", core_words=(), ms=MS) -> dict:
    t = re.sub(r"\s+", " ", t)
    windows, last = [], -10_000
    for m in ms.finditer(t):
        if m.start() - last > 700:
            windows.append(t[max(0, m.start() - 300):m.start() + 600])
            last = m.start()
    windows.sort(key=lambda w: -bool(WHERE.search(w)))
    acks = list(re.finditer(r"acknowledg(e)?ments?", t, re.I))
    return {"ms_paragraphs": windows[:5], "n_ms_paragraphs": len(windows),
            "acknowledgments": t[acks[-1].start():acks[-1].start() + 1500] if acks else "",
            "funding": "", "author_contributions": "", **_common(t, institution, list(core_words))}


def _get(url: str) -> str:
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60)
    b = r.read()
    if "pdf" in r.headers.get("Content-Type", "") or b[:4] == b"%PDF":
        from pypdf import PdfReader
        return " ".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(b)).pages)
    return b.decode("utf-8", "ignore")


def _ncbi_wait(pause):
    with _lock:  # NCBI allows 3 requests a second without a key
        wait = pause - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()


def fetch_fulltext(pmcid: str, getter=_get, pause: float = 0.4) -> tuple[str, str]:
    """(text, source) for a PMC article; XML when possible. Raises if no source has the body."""
    for _ in range(2):
        try:
            return getter(f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"), "europepmc"
        except Exception:
            time.sleep(pause)
    _ncbi_wait(pause)
    try:
        x = getter("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&tool=ucd-core-financials&id="
                   + pmcid.replace("PMC", ""))
        if "<body" in x:
            return x, "ncbi"
    except Exception:
        pass
    _ncbi_wait(pause)
    page = getter(f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/")
    body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page.split("<main", 1)[-1], flags=re.S)
    if len(body) < 5000:
        raise RuntimeError("no full text")
    return body, "pmc web"


def free_copies(doi: str, getter=_get) -> list[str]:
    """Open-access copies OpenAlex knows of: repositories and preprints first, publisher pages last."""
    w = json.loads(getter("https://api.openalex.org/works/doi:" + urllib.parse.quote(doi)))
    locs = [loc for loc in w.get("locations", []) if loc.get("is_oa")]

    def rank(loc):
        s = json.dumps(loc.get("source") or {}) + (loc.get("landing_page_url") or "")
        return (0 if "PubMed Central" in s else 2 if re.search(r"sciencedirect|elsevier|wiley|acs\.org|springer", s, re.I)
                else 1)
    urls = []
    for loc in sorted(locs, key=rank):
        urls += [u for u in (loc.get("pdf_url"), loc.get("landing_page_url")) if u]
    return list(dict.fromkeys(urls))


def excerpts_for(paper: dict, institution="Davis", core_words=(), getter=_get, ms=MS) -> dict:
    """Excerpts for one paper row (keys pmcid, doi). Adds 'source' or 'error'."""
    rec = dict(paper)
    if paper.get("pmcid"):
        try:
            x, src = fetch_fulltext(paper["pmcid"], getter=getter)
            ex = excerpts_from_xml(x, institution, core_words, ms) if src != "pmc web" else \
                excerpts_from_text(_text(x), institution, core_words, ms)
            return {**rec, **ex, "source": src}
        except Exception:
            pass
    if paper.get("doi"):
        try:
            for url in free_copies(paper["doi"], getter=getter):
                try:
                    t = getter(url)
                except Exception:
                    continue
                t = _text(re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S))
                if len(t) > 8000 and ms.search(t) and not re.search(r"verify you are human|just a moment", t[:3000], re.I):
                    return {**rec, **excerpts_from_text(t, institution, core_words, ms), "source": url}
        except Exception:
            pass
    return {**rec, "error": "no free full text: read it through the library"}


def write_batches(records: list[dict], folder, size: int = 45) -> list[Path]:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("batch*.json"):
        old.unlink()
    paths = []
    for i in range(0, len(records), size):
        p = folder / f"batch{i // size + 1}.json"
        p.write_text(json.dumps(records[i:i + size], ensure_ascii=False, indent=1))
        paths.append(p)
    return paths


def load_verdicts(folder) -> dict:
    out = {}
    for p in sorted(Path(folder).glob("verdict*.json")):
        for v in json.loads(p.read_text()):
            if v.get("verdict") in VERDICTS:
                out[int(v["n"])] = v
    return out
