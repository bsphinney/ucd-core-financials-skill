import json
import re

import pytest

from core_financials import aggie as A
from core_financials.checks import Check, run_checks
from core_financials.dashboard import build_dashboard_data, write_dashboard


def _aggie(s):
    return {"suppliers_by_account": A.suppliers_by_account(s["po"]), "po_vs_gl": A.po_vs_gl(s["po"], s["gl"]),
            "supplier_concentration": A.supplier_concentration(s["po"], s["cfg"]), "balances": s["balances"],
            "balances_total": A.balances_total(s["balances"]), "glide": A.glide_by_category(s["glide"])}


def _data(html):
    m = re.search(r"const DATA = (\{.*?\});\n", html, flags=re.S)
    return json.loads(m.group(1))


@pytest.fixture(scope="module")
def built(sample, tmp_path_factory):
    out = tmp_path_factory.mktemp("dash")
    s = sample
    checks = run_checks(s["fin"], s["use"], [])
    full = write_dashboard(build_dashboard_data(s["fin"], s["use"], _aggie(s), checks, s["cfg"], staff=False),
                           s["cfg"], out / "dashboard.html")
    staff = write_dashboard(build_dashboard_data(s["fin"], s["use"], _aggie(s), checks, s["cfg"], staff=True),
                            s["cfg"], out / "dashboard_STAFF.html")
    return full.read_text(), staff.read_text()


def test_dashboard_self_contained(built):
    html, _ = built
    assert "<script src=" not in html
    assert not re.search(r"<link[^>]+href=\"https?:", html)
    assert "sourceMappingURL" not in html
    assert len(html.encode()) < 3_000_000


def test_dashboard_data_roundtrip(built, sample):
    d = _data(built[0])
    assert d["fin"]["kpis"]["net"] == pytest.approx(sample["fin"]["kpis"]["net"])
    assert d["meta"]["core_name"] == "Example Imaging Core"


def test_staff_edition_has_no_personnel_accounts(built, sample):
    _, staff = built
    gl = sample["gl"]
    codes = set(gl.loc[gl["account"].str.startswith(tuple(sample["cfg"].personnel_prefixes)), "account"])
    assert codes
    for c in codes:
        assert c not in staff, c
    assert "STAFF EDITION" in staff
    d = _data(staff)
    assert d["use"]["unbilled"] is None
    sal = next(g for g in d["fin"]["expense_groups"] if g["name"] == "Salaries & Wages")
    assert sal["accounts"] == [] and sal["amount"] > 0


def test_full_edition_keeps_personnel_accounts(built):
    assert "500100" in built[0]


def test_missing_sections_show_note(sample, tmp_path):
    s = sample
    html = write_dashboard(build_dashboard_data(s["fin"], None, {}, [], s["cfg"], staff=False), s["cfg"],
                           tmp_path / "d.html").read_text()
    notes = " ".join(_data(html)["missing"].values())
    assert "Add the PO spend report" in notes
    assert "Add the PPMS Order details report" in notes
    full = _data(write_dashboard(build_dashboard_data(s["fin"], s["use"], _aggie(s), [], s["cfg"], staff=False),
                                 s["cfg"], tmp_path / "f.html").read_text())
    assert "po" not in full["missing"] and "ppms" not in full["missing"]


def test_failed_check_shows_red_banner(sample, tmp_path):
    s = sample
    bad = [Check("income − expense = net", False, "off by 1.00")]
    html = write_dashboard(build_dashboard_data(s["fin"], s["use"], {}, bad, s["cfg"], staff=False), s["cfg"],
                           tmp_path / "d.html").read_text()
    d = _data(html)
    assert d["checks"][0]["passed"] is False
    assert 'id="checks-banner"' in html
