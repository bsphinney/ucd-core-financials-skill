from core_financials.checks import run_checks
from core_financials.inventory import scan
from core_financials.summary import build_facts
from conftest import SAMPLE


def test_facts_have_sources(sample):
    facts = build_facts(sample["fin"], sample["use"], run_checks(sample["fin"], sample["use"], []), scan(SAMPLE),
                        sample["cfg"])
    assert facts["core"] == "Example Imaging Core"
    assert len(facts["facts"]) >= 12
    for f in facts["facts"]:
        assert f["source"], f
        assert {"id", "label", "value", "unit"} <= set(f)


def test_facts_without_gl(sample):
    facts = build_facts(None, sample["use"], [], [], sample["cfg"])
    assert all(not f["id"].startswith("fin.") for f in facts["facts"])
