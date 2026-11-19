import copy

from core_financials.aggie import po_vs_gl
from core_financials.checks import run_checks, write_checks_md


def test_checks_pass_on_sample(sample):
    checks = run_checks(sample["fin"], sample["use"], po_vs_gl(sample["po"], sample["gl"]))
    failed = [c for c in checks if c.kind == "arithmetic" and not c.passed]
    assert not failed, failed
    names = {c.name for c in checks}
    assert {"income − expense = net", "Sankey in = out", "assessment matches 15% of external sales"} <= names


def test_check_fails_when_tampered(sample):
    fin = copy.deepcopy(sample["fin"])
    fin["expense_groups"][0]["amount"] -= 1.0
    checks = {c.name: c for c in run_checks(fin, sample["use"], [])}
    assert not checks["expense groups sum = expense"].passed


def test_checks_without_inputs():
    assert run_checks(None, None, []) == []


def test_write_checks_md(sample, tmp_path):
    p = write_checks_md(run_checks(sample["fin"], sample["use"], []), tmp_path / "checks.md")
    assert "PASS" in p.read_text()
