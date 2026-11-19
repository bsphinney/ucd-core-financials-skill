import yaml
from core_financials.config import load_config, write_config_template, load_coa


def _write(path, data):
    path.write_text(yaml.safe_dump(data))
    return path


def test_load_coa_defaults():
    coa = load_coa()
    assert coa["assessment_accounts"] == ["770009", "775004"]
    assert coa["contra_accounts"] == ["445100"]
    assert coa["assessment_rate"] == 0.15


def test_load_config_merges_overrides(tmp_path):
    p = _write(tmp_path / "c.yaml", {"core_name": "X", "funds": {"12100": {"label": "Rev", "role": "operating"}},
                                     "coa_overrides": {"assessment_rate": 0.12}})
    cfg = load_config(p)
    assert cfg.coa["assessment_rate"] == 0.12
    assert cfg.coa["contra_accounts"] == ["445100"]


def test_fund_codes_are_strings(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("core_name: X\nfunds:\n  12100: {label: Rev, role: operating}\n")
    cfg = load_config(p)
    assert list(cfg.funds) == ["12100"]


def test_write_config_template_roundtrip(tmp_path):
    p = tmp_path / "core-config.yaml"
    write_config_template(p, {"12100": "Sales and Services Rate Based"})
    cfg = load_config(p)
    assert cfg.funds["12100"]["role"] == "operating"
    assert cfg.personnel_prefixes == ["500", "501", "505", "506", "508"]
