import json
import shutil

import pytest

from conftest import SAMPLE
from core_financials.cli import main
from core_financials.config import load_config

OUTPUTS = ["dashboard.html", "dashboard_STAFF.html", "usership.xlsx", "benchmark.csv", "facts.json", "checks.md",
           "reports-needed.md", "share/per_dollar.png", "internal/bridge.png"]


def _copy(tmp_path, names):
    for n in names:
        shutil.copy(SAMPLE / n, tmp_path / n)
    return tmp_path


def test_build_sample_end_to_end(tmp_path, capsys):
    folder = _copy(tmp_path, [p.name for p in SAMPLE.iterdir() if p.is_file()])
    assert main(["build", str(folder)]) == 0
    for o in OUTPUTS:
        assert (folder / "out" / o).exists(), o
    assert "FAIL" not in (folder / "out" / "checks.md").read_text().replace("failed", "")
    assert (folder / "affiliations.csv").exists()
    out = capsys.readouterr().out
    assert "dashboard.html" in out


def test_build_ppms_only(tmp_path):
    folder = _copy(tmp_path, ["core-config.yaml", "ppms_order_details.xlsx"])
    assert main(["build", str(folder)]) == 0
    assert (folder / "out" / "dashboard.html").exists()
    assert (folder / "out" / "usership.xlsx").exists()
    facts = json.loads((folder / "out" / "facts.json").read_text())
    assert not [f for f in facts["facts"] if f["id"].startswith("fin.")]
    assert "GL Transaction Listing" in (folder / "out" / "reports-needed.md").read_text()


def test_build_gl_only(tmp_path):
    folder = _copy(tmp_path, ["core-config.yaml", "gl_page_2024-01_to_2026-09.xlsx"])
    assert main(["build", str(folder)]) == 0
    assert (folder / "out" / "dashboard.html").exists()
    assert not (folder / "out" / "usership.xlsx").exists()
    assert "PPMS Order details" in (folder / "out" / "reports-needed.md").read_text()


def test_build_empty_folder_exit_2(tmp_path):
    assert main(["build", str(tmp_path)]) == 2


def test_build_without_config_exit_2(tmp_path):
    _copy(tmp_path, ["ppms_order_details.xlsx"])
    assert main(["build", str(tmp_path)]) == 2


def test_init_proposes_funds_from_gl(tmp_path):
    folder = _copy(tmp_path, ["gl_page_2024-01_to_2026-09.xlsx"])
    assert main(["init", str(folder)]) == 0
    cfg = load_config(folder / "core-config.yaml")
    assert {"12100", "16200", "13U00"} <= set(cfg.funds)
    assert cfg.financial_department == "XIMG001"
    assert main(["init", str(folder)]) == 0  # second run must not overwrite
    assert load_config(folder / "core-config.yaml").financial_department == "XIMG001"


def test_inventory_and_affiliations_commands(tmp_path, capsys):
    folder = _copy(tmp_path, [p.name for p in SAMPLE.iterdir() if p.is_file()])
    assert main(["inventory", str(folder)]) == 0
    assert (folder / "out" / "reports-needed.md").exists()
    assert main(["affiliations", str(folder)]) == 0
    assert "unconfirmed" in capsys.readouterr().out.lower()


def test_combine_command(tmp_path):
    folder = _copy(tmp_path, [p.name for p in SAMPLE.iterdir() if p.is_file()])
    main(["build", str(folder)])
    b = folder / "out" / "benchmark.csv"
    assert main(["combine", str(b), str(b), "--out", str(tmp_path / "cmp")]) == 0
    assert (tmp_path / "cmp" / "benchmark_comparison.xlsx").exists()
