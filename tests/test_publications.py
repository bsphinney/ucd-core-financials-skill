from datetime import datetime

import pandas as pd
import pytest

from core_financials import publications as P


def _orders(rows):
    df = pd.DataFrame(rows, columns=["order", "user", "group", "service", "ordered", "accepted", "completed"])
    for c in ("ordered", "accepted", "completed"):
        df[c] = pd.to_datetime(df[c])
    df["is_revenue"] = df["accepted"].notna() | df["completed"].notna()
    return df


ORDERS = _orders([
    ("1", "Lindqvist Mira", "Okafor, Grace", "LC-MSMS", "2025-06-10", "2025-06-10", "2025-06-10"),
    ("2", "Ngata Ann", "Ngata, Ann (Vet Med)", "LC-MSMS", "2021-03-01", "2021-03-02", "2021-04-01"),
    ("3", "Quote Only", "Nobody, Nora", "LC-MSMS", "2022-01-01", None, None),
])
CFG = {"core_names": ["Proteomics Core", "Genome Center Proteomics"], "other_facilities": ["Metabolomics Center"], "technique_terms": ["mass spectrometry", "proteom*"],
       "institution": "Davis", "years_after": 3, "follow_up_years": 3}


def _author(last, first, aff=""):
    a = {"lastName": last, "firstName": first, "initials": first[0], "fullName": f"{last} {first[0]}"}
    if aff:
        a["authorAffiliationDetailsList"] = {"authorAffiliation": [{"affiliation": aff}]}
    return a


def _paper(pid, authors, date="2026-01-05", in_epmc="Y", pubtypes=("research-article",), title="A study"):
    return {"id": pid, "pmid": pid, "pmcid": f"PMC{pid}" if in_epmc == "Y" else None, "source": "MED",
            "title": title, "firstPublicationDate": date, "inEPMC": in_epmc,
            "authorList": {"author": authors}, "pubTypeList": {"pubType": list(pubtypes)},
            "journalInfo": {"journal": {"title": "J Test"}}}


class FakeClient:
    def __init__(self, technique=None, named=None, other=None):
        self.technique, self.named, self.other, self.queries = technique or {}, named or {}, other or {}, []

    def search(self, query):
        self.queries.append(query)
        key = query.split('"')[1]  # the AUTH:"Last F" name
        table = (self.named if "Proteomics Core" in query else self.other if "Metabolomics Center" in query
                 else self.technique)
        return table.get(key, [])


def test_name_parsing():
    assert P.parse_group("Okafor, Grace") == ("Okafor", "Grace")
    assert P.parse_group("Ngata, Ann (Vet Med)") == ("Ngata", "Ann")
    assert P.parse_user("Lindqvist Mira") == ("Lindqvist", "Mira")


def test_people_cover_pi_and_submitter_with_windows():
    people = P.people_from_orders(ORDERS, CFG)
    keys = {(p["last"], p["role"]) for p in people}
    assert ("Okafor", "PI") in keys and ("Lindqvist", "submitter") in keys
    assert not any(p["group"] == "Nobody, Nora" for p in people)          # quote never accepted
    assert not any(p["last"] == "Ngata" and p["role"] == "submitter" for p in people)  # submitter is the PI
    r = next(p for p in people if p["last"] == "Lindqvist")
    assert r["start"] == datetime(2025, 6, 10).date() and r["end"].year == 2028 or r["end"] <= datetime.now().date()


def test_query_uses_author_window_and_sections():
    q = P.technique_query("Lindqvist", "Mira", datetime(2025, 6, 10).date(), datetime(2028, 6, 10).date(), CFG)
    assert 'AUTH:"Lindqvist M"' in q and "FIRST_PDATE:[2025-06-10 TO 2028-06-10]" in q
    assert 'METHODS:"mass spectrometry"' in q and "ABSTRACT:proteom*" in q


def test_same_name_researcher_elsewhere_is_not_matched():
    elsewhere = _paper("1", [_author("Other", "Ola", "Faraway University"), _author("Lindqvist", "Mats", "Faraway University")])
    rows = P.find_papers(ORDERS, CFG, FakeClient(technique={"Lindqvist M": [elsewhere]}))
    assert rows == []


def test_submitter_matched_through_pi_coauthor_without_davis_affiliation():
    paper = _paper("2", [_author("Lindqvist", "Mira", "Nordic University"), _author("Okafor", "Grace")])
    rows = P.find_papers(ORDERS, CFG, FakeClient(technique={"Lindqvist M": [paper], "Okafor G": [paper]}))
    assert len(rows) == 1 and rows[0]["group"] == "Okafor, Grace"
    assert "Lindqvist" in rows[0]["matched"] and "Okafor" in rows[0]["matched"]


def test_reviews_are_excluded():
    rev = _paper("3", [_author("Okafor", "Grace", "UC Davis")], pubtypes=("Review", "review-article"))
    assert P.find_papers(ORDERS, CFG, FakeClient(technique={"Okafor G": [rev]})) == []


def test_status_named_not_named_and_cant_check():
    davis = lambda pid, **k: _paper(pid, [_author("Okafor", "Grace", "UC Davis School of Medicine")], **k)
    a, b, c = davis("10"), davis("11"), davis("12", in_epmc="N")
    rows = P.find_papers(ORDERS, CFG, FakeClient(technique={"Okafor G": [a, b, c]}, named={"Okafor G": [a]}))
    status = {r["pmid"]: r["status"] for r in rows}
    assert status == {"10": P.NAMED, "11": P.NOT_NAMED, "12": P.CANT_CHECK}


def test_outside_window_is_dropped():
    old = _paper("13", [_author("Okafor", "Grace", "UC Davis")], date="2024-01-01")
    assert P.find_papers(ORDERS, CFG, FakeClient(technique={"Okafor G": [old]})) == []


def test_follow_up_lists_recent_labs_without_a_later_paper():
    fu = P.follow_up(ORDERS, [], CFG, as_of=datetime(2026, 4, 1))
    assert list(fu["group"]) == ["Okafor, Grace"]          # Ngata 2021 order is older than 3 years
    assert "Lindqvist Mira" in fu.iloc[0]["submitters"]
    paper = {"group": "Okafor, Grace", "date": "2026-01-05", "status": P.NOT_NAMED}
    assert P.follow_up(ORDERS, [paper], CFG, as_of=datetime(2026, 4, 1)).empty


def test_workbook_sheets(tmp_path):
    rows = [{"group": "Okafor, Grace", "matched": "Lindqvist M (submitter)", "date": "2026-01-05", "title": "T",
             "journal": "J", "pmid": "1", "pmcid": "PMC1", "link": "https://europepmc.org/article/MED/1",
             "status": P.NOT_NAMED, "lab_orders": "2025-06-10 → 2025-06-10", "preprint": False}]
    path = tmp_path / "publications.xlsx"
    P.write_workbook(rows, P.follow_up(ORDERS, [], CFG, as_of=datetime(2026, 4, 1)), CFG, path)
    xl = pd.ExcelFile(path)
    assert xl.sheet_names == ["Core not named", "Can't check", "Names another facility", "Names the core",
                              "Not in PubMed", "Follow up", "About"]
    assert pd.read_excel(path, "Core not named").iloc[0]["Title"] == "T"


def test_build_never_queries_the_internet():
    import inspect
    from core_financials import pipeline
    assert "publications" not in inspect.getsource(pipeline)


def test_config_reads_publications_block(tmp_path):
    from core_financials.config import load_config
    p = tmp_path / "core-config.yaml"
    p.write_text('core_name: "X Core"\npublications:\n  core_names: ["X Core"]\n  technique_terms: ["confocal"]\n')
    pub = load_config(p).publications
    assert pub["core_names"] == ["X Core"] and pub["institution"] == "Davis" and pub["years_after"] == 3


def test_cli_publications_needs_ppms_and_terms(tmp_path, capsys):
    from core_financials.cli import main
    (tmp_path / "core-config.yaml").write_text('core_name: "X Core"\n')
    assert main(["publications", str(tmp_path)]) == 2
    assert "PPMS" in capsys.readouterr().out


def test_cli_publications_runs_with_offline_client(tmp_path, monkeypatch, capsys, sample):
    import shutil
    from core_financials import cli
    folder = tmp_path / "core"
    shutil.copytree("sample_data/example_core", folder, ignore=shutil.ignore_patterns("out"))
    monkeypatch.setattr(P, "EuropePMC", lambda *a, **k: FakeClient())
    assert cli.main(["publications", str(folder), "--limit", "5"]) == 0
    assert (folder / "out" / "internal" / "publications.xlsx").exists()
    assert "Follow up" in capsys.readouterr().out


def test_paper_naming_another_facility_is_not_flagged():
    davis = lambda pid: _paper(pid, [_author("Okafor", "Grace", "UC Davis")])
    a, b = davis("20"), davis("21")
    rows = P.find_papers(ORDERS, CFG, FakeClient(technique={"Okafor G": [a, b]}, named={"Okafor G": [b]},
                                                 other={"Okafor G": [a, b]}))
    assert {r["pmid"]: r["status"] for r in rows} == {"20": P.OTHER, "21": P.NAMED}


def test_client_keeps_only_needed_author_fields():
    raw = {"id": "1", "authorList": {"author": [{"lastName": "Okafor", "firstName": "Grace", "initials": "G",
           "fullName": "Okafor G", "authorId": {"type": "ORCID"}, "authorAffiliationDetailsList": {
               "authorAffiliation": [{"affiliation": "UC Davis " + "x" * 500}, {"affiliation": "Other"}]}}]}}
    a = P.compact(raw)["authorList"]["author"][0]
    assert set(a) == {"lastName", "firstName", "initials", "authorAffiliationDetailsList"}
    assert "Davis" in P._affs(a) and "Other" in P._affs(a) and len(P._affs(a)) < 400


def test_find_papers_prefetches_all_queries_in_two_batches():
    class Batching(FakeClient):
        batches = []
        def prefetch(self, queries):
            self.batches.append(len(queries))
    paper = _paper("2", [_author("Lindqvist", "Mira", "Nordic University"), _author("Okafor", "Grace")])
    c = Batching(technique={"Lindqvist M": [paper], "Okafor G": [paper]})
    P.find_papers(ORDERS, CFG, c)
    assert c.batches == [3, 4]   # 3 people; then named + other queries for the 2 people with papers


def test_full_first_name_must_agree_when_given():
    other = _paper("30", [_author("Lindqvist", "Mats", "UC Davis"), _author("Okafor", "Gordon", "UC Davis")])
    assert P.find_papers(ORDERS, CFG, FakeClient(technique={"Lindqvist M": [other], "Okafor G": [other]})) == []
    initials_only = _paper("31", [{"lastName": "Okafor", "initials": "G", "authorAffiliationDetailsList": {
        "authorAffiliation": [{"affiliation": "UC Davis"}]}}])
    assert len(P.find_papers(ORDERS, CFG, FakeClient(technique={"Okafor G": [initials_only]}))) == 1


def test_technique_also_terms_are_required_together():
    s = {**CFG, "technique_also": ["trypsin", "peptide*"]}
    q = P.technique_query("Okafor", "Grace", datetime(2025, 6, 10).date(), datetime(2028, 6, 10).date(), s)
    assert q.count(" AND (") == 2 and "METHODS:trypsin" in q


# ---- review fixes ----

def test_compact_keeps_every_affiliation():
    raw = {"id": "1", "authorList": {"author": [{"lastName": "Okafor", "firstName": "Grace", "authorAffiliationDetailsList": {
        "authorAffiliation": [{"affiliation": "Shriners Hospital, Sacramento"}, {"affiliation": "University of California Davis"}]}}]}}
    assert "Davis" in P._affs(P.compact(raw)["authorList"]["author"][0])


def test_a_failing_search_is_reported_not_fatal():
    class Flaky(FakeClient):
        def search(self, query):
            if "Lindqvist" in query:
                raise OSError("HTTP 500")
            return super().search(query)
    failed = []
    P.find_papers(ORDERS, CFG, Flaky(), failed=failed)
    assert any("Lindqvist" in f for f in failed)


@pytest.mark.parametrize("term,expected", [("Q:Exactive", 'METHODS:"Q:Exactive"'), ("peptide*", "METHODS:peptide*"),
                                           ('say "hi"', 'METHODS:"say hi"'), ("LC-MS/MS", 'METHODS:"LC-MS/MS"')])
def test_terms_are_quoted_safely(term, expected):
    assert P._term("METHODS", term) == expected


def test_multi_word_surnames_in_user_names():
    assert P.parse_user("Van Der Berg Anna") == ("Van Der Berg", "Anna")
    assert P.parse_user("de la Cruz Maria") == ("de la Cruz", "Maria")
    assert P.parse_user("Lindqvist Mira") == ("Lindqvist", "Mira")


def test_accented_given_names_match():
    assert P._is({"lastName": "Okafor", "firstName": "Élodie"}, "Okafor", "Elodie")


def test_coauthor_rule_needs_the_pi_and_two_different_authors():
    orders = _orders([("1", "Wang Dan", "Okafor, Grace", "LC-MSMS", "2025-06-10", "2025-06-10", "2025-06-10"),
                      ("2", "Cheng Yu", "Okafor, Grace", "LC-MSMS", "2025-06-11", "2025-06-11", "2025-06-11")])
    two_submitters = _paper("40", [_author("Wang", "Dan", "Elsewhere"), _author("Cheng", "Yu", "Elsewhere")])
    assert P.find_papers(orders, CFG, FakeClient(technique={"Wang D": [two_submitters], "Cheng Y": [two_submitters]})) == []


def _row(pmid, status=None, group="Okafor, Grace"):
    return {"group": group, "matched": "Okafor G (PI)", "date": "2026-01-05", "title": f"T{pmid}", "journal": "J",
            "pmid": pmid, "pmcid": f"PMC{pmid}", "doi": "", "link": "l", "status": status or P.NOT_NAMED,
            "lab_orders": "x", "preprint": False}


def test_review_records_cover_flagged_other_and_cant_check():
    rows = [_row("1"), _row("2", P.NAMED), _row("3", P.OTHER), _row("4", P.CANT_CHECK)]
    recs = P.review_records(rows)
    assert [r["pmid"] for r in recs] == ["1", "3", "4"] and [r["n"] for r in recs] == [1, 2, 3]
    assert recs[0]["key"] == P.row_key(rows[0])


def test_workbook_adds_verdicts_and_ask_sheet(tmp_path):
    rows = [_row("1"), _row("3", P.OTHER)]
    verdicts = {P.row_key(rows[0]): {"verdict": "likely_core", "confidence": "high", "where": "this core",
                                     "evidence": "run on the core's timsTOF", "action": "Ask the lab to credit the core"},
                P.row_key(rows[1]): {"verdict": "other_facility", "confidence": "high", "where": "Other Center",
                                     "evidence": "e", "action": "No action"}}
    path = tmp_path / "p.xlsx"
    P.write_workbook(rows, P.follow_up(ORDERS, [], CFG, as_of=datetime(2026, 4, 1)), CFG, path, verdicts=verdicts)
    xl = pd.ExcelFile(path)
    assert xl.sheet_names[0] == "Ask the lab"
    ask = pd.read_excel(path, "Ask the lab")
    assert list(ask["Title"]) == ["T1"] and ask.iloc[0]["Evidence"] == "run on the core's timsTOF"
    assert pd.read_excel(path, "Names another facility").iloc[0]["Review"] == "other_facility"


def test_cli_excerpts_writes_batches(tmp_path, monkeypatch, sample):
    import shutil, json
    from core_financials import cli, fulltext
    folder = tmp_path / "core"
    shutil.copytree("sample_data/example_core", folder, ignore=shutil.ignore_patterns("out"))
    paper = _paper("50", [_author("Okafor", "Grace", "UC Davis")])
    monkeypatch.setattr(P, "EuropePMC", lambda *a, **k: FakeClient())
    monkeypatch.setattr(P, "find_papers", lambda *a, **k: [_row("50")])
    monkeypatch.setattr(P, "Crossref", lambda *a, **k: FakeCrossref({}))
    monkeypatch.setattr(fulltext, "excerpts_for", lambda paper, *a, **k: {**paper, "ms_paragraphs": ["x"], "source": "test"})
    assert cli.main(["publications", str(folder), "--excerpts"]) == 0
    b = json.loads((folder / "out" / "internal" / "paper_review" / "batch1.json").read_text())
    assert b[0]["pmid"] == "50" and b[0]["ms_paragraphs"] == ["x"]


# ---------- papers outside PubMed (Crossref) ----------

def _cr_item(doi, authors, date=(2026, 2, 1), title="Hydrogel wound study", aff=None, kind="journal-article"):
    return {"DOI": doi, "type": kind, "title": [title], "container-title": ["Smart Mater Med"],
            "issued": {"date-parts": [list(date)]},
            "author": [{"family": f, "given": g, "affiliation": [{"name": aff}] if aff else []} for f, g in authors]}


def test_crossref_item_becomes_a_paper_record():
    p = P.crossref_paper(_cr_item("10.1/X", [("Okafor", "Grace"), ("Lindqvist", "Mira")], aff="UC Davis"))
    assert p["doi"] == "10.1/X" and p["firstPublicationDate"] == "2026-02-01" and p["source"] == "CR"
    assert P._is(p["authorList"]["author"][0], "Okafor", "Grace")
    assert "Davis" in P._affs(p["authorList"]["author"][0])


class FakeCrossref:
    def __init__(self, items):
        self.items, self.queries = items, []

    def search(self, names, start, end):
        self.queries.append(tuple(names))
        return [P.crossref_paper(i) for i in self.items.get(names[0][0], [])]


class FakeEPMC:
    def __init__(self, known):
        self.known = known

    def search(self, query):
        return [{"doi": d} for d in self.known if d.casefold() in query.casefold()]


def test_papers_outside_pubmed_are_added_for_review():
    items = {"Okafor": [
        _cr_item("10.1/both", [("Okafor", "Grace"), ("Lindqvist", "Mira")]),       # PI + submitter: kept
        _cr_item("10.1/pi-only", [("Okafor", "Grace"), ("Smith", "Jo")]),          # PI alone, no Davis: dropped
        _cr_item("10.1/in-pubmed", [("Okafor", "Grace"), ("Lindqvist", "Mira")]),  # Europe PMC has it: dropped
        _cr_item("10.1/old", [("Okafor", "Grace"), ("Lindqvist", "Mira")], date=(2019, 1, 1)),  # before orders
    ]}
    cr = FakeCrossref(items)
    rows = P.find_outside_pubmed(ORDERS, P.settings(CFG), cr, FakeEPMC(["10.1/in-pubmed"]), [])
    assert [r["doi"] for r in rows] == ["10.1/both"]
    assert ("Okafor", "Grace") in cr.queries[0] and ("Lindqvist", "Mira") in cr.queries[0]  # PI with submitter
    assert rows[0]["status"] == P.OUTSIDE and rows[0]["link"] == "https://doi.org/10.1/both"
    assert P.review_records(rows)[0]["doi"] == "10.1/both"


def test_papers_already_found_are_not_repeated():
    items = {"Okafor": [_cr_item("10.1/both", [("Okafor", "Grace"), ("Lindqvist", "Mira")])]}
    found = [{"group": "Okafor, Grace", "doi": "10.1/BOTH", "title": "x"}]
    assert P.find_outside_pubmed(ORDERS, P.settings(CFG), FakeCrossref(items), FakeEPMC([]), found) == []


def test_workbook_has_outside_pubmed_sheet(tmp_path):
    rows = [{"group": "Okafor, Grace", "matched": "Okafor G (PI)", "date": "2026-02-01", "title": "T", "journal": "J",
             "pmid": "", "pmcid": "", "doi": "10.1/a", "link": "https://doi.org/10.1/a", "status": P.OUTSIDE,
             "lab_orders": "x", "preprint": False}]
    path = tmp_path / "p.xlsx"
    P.write_workbook(rows, P.follow_up(ORDERS, rows, P.settings(CFG)), P.settings(CFG), path)
    assert len(pd.read_excel(path, "Not in PubMed")) == 1


def test_cli_excerpts_keeps_earlier_verdicts(tmp_path, monkeypatch, sample):
    import shutil, json
    from core_financials import cli, fulltext
    folder = tmp_path / "core"
    shutil.copytree("sample_data/example_core", folder, ignore=shutil.ignore_patterns("out"))
    monkeypatch.setattr(P, "EuropePMC", lambda *a, **k: FakeClient())
    monkeypatch.setattr(P, "Crossref", lambda *a, **k: FakeCrossref({}))
    monkeypatch.setattr(fulltext, "excerpts_for", lambda paper, *a, **k: {**paper, "ms_paragraphs": ["x"],
                                                                          "n_ms_paragraphs": 1, "source": "t"})
    rows = [_row("50")]
    monkeypatch.setattr(P, "find_papers", lambda *a, **k: list(rows))
    assert cli.main(["publications", str(folder), "--excerpts"]) == 0
    rd = folder / "out" / "internal" / "paper_review"
    (rd / "verdict1.json").write_text(json.dumps([{"n": 1, "verdict": "likely_core", "confidence": "high",
                                                   "where": "w", "evidence": "e", "action": "Ask the lab"}]))
    rows.append(_row("51"))  # a new paper turns up on the next run
    assert cli.main(["publications", str(folder), "--excerpts"]) == 0
    assert [r["pmid"] for r in json.loads((rd / "batch1.json").read_text())] == ["51"]  # only the new one
    assert P.load_review(rd)["50"]["verdict"] == "likely_core"  # the earlier verdict survives


def test_outside_pubmed_paper_without_technique_words_is_closed_automatically(tmp_path, monkeypatch, sample):
    import shutil
    from core_financials import cli, fulltext
    folder = tmp_path / "core"
    shutil.copytree("sample_data/example_core", folder, ignore=shutil.ignore_patterns("out"))
    out = {**_row("x"), "pmid": "", "pmcid": "", "doi": "10.1/none", "status": P.OUTSIDE}
    monkeypatch.setattr(P, "EuropePMC", lambda *a, **k: FakeClient())
    monkeypatch.setattr(P, "find_papers", lambda *a, **k: [])
    monkeypatch.setattr(P, "Crossref", lambda *a, **k: FakeCrossref({}))
    monkeypatch.setattr(P, "find_outside_pubmed", lambda *a, **k: [out])
    monkeypatch.setattr(fulltext, "excerpts_for", lambda paper, *a, **k: {**paper, "ms_paragraphs": [],
                                                                          "n_ms_paragraphs": 0, "source": "t"})
    assert cli.main(["publications", str(folder), "--excerpts"]) == 0
    v = P.load_review(folder / "out" / "internal" / "paper_review")
    assert v["10.1/none"]["verdict"] == "no_new_proteomics"


def test_meeting_abstracts_in_indexed_journals_are_skipped():
    items = {"Okafor": [
        _cr_item("10.1/abs", [("Okafor", "Grace"), ("Lindqvist", "Mira")], date=(2025, 9, 1)),
        _cr_item("10.1/new", [("Okafor", "Grace"), ("Lindqvist", "Mira")], date=(2026, 11, 1)),
    ]}
    rows = P.find_outside_pubmed(ORDERS, P.settings(CFG), FakeCrossref(items), FakeEPMC([]), [],
                                 indexed_journals={"smart mater med"}, today=datetime(2026, 11, 19).date())
    assert [r["doi"] for r in rows] == ["10.1/new"]  # an old item in an indexed journal is a meeting abstract


def test_journal_names_match_across_spellings():
    k = P._journal_key
    assert k("The Journal of biological chemistry") == k("Journal of Biological Chemistry")
    assert k("Journal of the American Society of Nephrology : JASN") == k("Journal of the American Society of Nephrology")
    assert k("Alzheimer's &amp; Dementia") == k("Alzheimer's & dementia : the journal of the Alzheimer's Association")


def test_unchecked_outside_papers_do_not_take_a_lab_off_follow_up():
    out = {**_row("x"), "date": "2026-03-01", "status": P.OUTSIDE}
    fu = P.follow_up(ORDERS, [out], P.settings(CFG), as_of=datetime(2026, 4, 1))
    assert "Okafor, Grace" in set(fu["group"])
