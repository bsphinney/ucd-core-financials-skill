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
                              "Follow up", "About"]
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
    assert "Davis" in P._affs(a) and len(P._affs(a)) < 400


def test_find_papers_prefetches_all_queries_in_two_batches():
    class Batching(FakeClient):
        batches = []
        def prefetch(self, queries):
            self.batches.append(len(queries))
    paper = _paper("2", [_author("Lindqvist", "Mira", "Nordic University"), _author("Okafor", "Grace")])
    c = Batching(technique={"Lindqvist M": [paper], "Okafor G": [paper]})
    P.find_papers(ORDERS, CFG, c)
    assert c.batches == [3, 4]   # 3 people; then named + other queries for the 2 people with papers
