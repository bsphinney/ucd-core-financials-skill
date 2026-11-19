import json

import pandas as pd

from core_financials import fulltext as T

XML = """<article><front><article-meta><title-group><article-title>T</article-title></title-group></article-meta></front>
<body><sec><title>Methods</title>
<p>Cells were grown in DMEM.</p>
<p>Digested peptides were analysed on a Q Exactive mass spectrometer at the Example Proteomics Facility.</p>
</sec></body><back><ack><p>We thank the Example Proteomics Facility.</p></ack>
<funding-group><award-group>NIH R01</award-group></funding-group></back></article>"""


def test_excerpts_from_xml_pick_methods_ack_and_instruments():
    ex = T.excerpts_from_xml(XML)
    assert len(ex["ms_paragraphs"]) == 1 and "Q Exactive" in ex["ms_paragraphs"][0]
    assert "thank" in ex["acknowledgments"] and "R01" in ex["funding"]
    assert any("Q Exactive" in i for i in ex["instruments"])


def test_excerpts_from_text_find_acknowledgments():
    t = "Intro. " * 50 + "Samples were run by LC-MS/MS on an Orbitrap Fusion Lumos. " + "More. " * 50 + \
        "Acknowledgments We thank the core."
    ex = T.excerpts_from_text(t)
    assert ex["ms_paragraphs"] and ex["acknowledgments"].startswith("Acknowledgments")
    assert any("Lumos" in i for i in ex["instruments"])


def test_fetch_falls_back_in_order():
    calls = []

    def getter(url):
        calls.append(url)
        if "ebi.ac.uk" in url:
            raise OSError("500")
        return "<article><body><p>mass spectrometry</p></body></article>"
    text, src = T.fetch_fulltext("PMC123", getter=getter, pause=0)
    assert src == "ncbi" and "mass spectrometry" in text and "ebi.ac.uk" in calls[0]


def test_batches_and_review_merge(tmp_path):
    recs = [{"n": i, "title": f"P{i}", "status": "Core not named"} for i in range(1, 8)]
    paths = T.write_batches(recs, tmp_path, size=3)
    assert [len(json.loads(p.read_text())) for p in paths] == [3, 3, 1]
    (tmp_path / "verdict1.json").write_text(json.dumps([{"n": 1, "verdict": "likely_core", "confidence": "high",
                                                         "where": "this core", "evidence": "x",
                                                         "action": "Ask the lab to credit the core"}]))
    rv = T.load_verdicts(tmp_path)
    assert rv[1]["verdict"] == "likely_core" and 2 not in rv


def test_review_prompt_reference_exists():
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "reference" / "paper-review.md"
    text = p.read_text()
    for v in ("likely_core", "credits_core", "other_facility", "in_house", "no_new_proteomics", "unclear"):
        assert v in text
