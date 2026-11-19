import re

import yaml

from core_financials import SKILL_ROOT

SKILL = SKILL_ROOT / "SKILL.md"


def _front():
    text = SKILL.read_text()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "SKILL.md needs YAML frontmatter"
    return yaml.safe_load(m.group(1)), text


def test_frontmatter():
    fm, text = _front()
    assert fm["name"] == "ucd-core-financials"
    assert len(fm["description"]) < 1024
    for word in ["PPMS", "Aggie Enterprise", "assessment", "RCCI"]:
        assert word in fm["description"]
    assert len(text.splitlines()) < 300


def test_linked_reference_files_exist():
    _, text = _front()
    links = set(re.findall(r"\((reference/[^)]+\.md)\)", text))
    assert {"reference/pulling-reports.md", "reference/calculations.md", "reference/config.md",
            "reference/figures.md"} <= links
    for link in links:
        assert (SKILL_ROOT / link).exists(), link


def test_commands_named_exist():
    from core_financials.cli import COMMANDS
    _, text = _front()
    named = set(re.findall(r"run\.py (\w+)", text))
    assert named and named <= set(COMMANDS), named - set(COMMANDS)
    assert set(COMMANDS) <= named


def test_pull_guide_covers_every_report_with_placeholders():
    g = (SKILL_ROOT / "reference" / "pulling-reports.md").read_text()
    for heading in ["GL Transaction Listing", "GL and Subledger Detail", "PO spend report", "Department P&L",
                    "GLIDE", "PPMS Order details"]:
        assert heading in g, heading
    assert "{DEPT}" in g and "KB0010829" in g


def test_readme_credit_and_install():
    r = (SKILL_ROOT / "README.md").read_text()
    assert "Built by the UC Davis Proteomics Core (Brett Phinney)." in r
    assert "~/.claude/skills/ucd-core-financials" in r and "ucd-core-financials.zip" in r
