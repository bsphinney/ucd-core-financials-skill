import shutil

from core_financials.pipeline import run_build


def _core(tmp_path, extra=""):
    folder = tmp_path / "core"
    shutil.copytree("sample_data/example_core", folder, ignore=shutil.ignore_patterns("out"))
    with open(folder / "core-config.yaml", "a") as f:
        f.write(extra)
    return folder


def test_small_core_gets_no_staff_edition(tmp_path):
    folder = _core(tmp_path, "\npaid_staff: 2\n")
    (folder / "out").mkdir()
    (folder / "out" / "dashboard_STAFF.html").write_text("stale")
    res = run_build(folder)
    assert not (folder / "out" / "dashboard_STAFF.html").exists()
    assert any("staff edition" in s["section"] and "individual pay" in s["reason"] for s in res["skipped"])


def test_larger_core_keeps_staff_edition(tmp_path):
    res = run_build(_core(tmp_path, "\npaid_staff: 5\n"))
    from pathlib import Path
    assert (Path(res["out"]) / "dashboard_STAFF.html").exists()


def test_config_reads_paid_staff(tmp_path):
    from core_financials.config import load_config
    p = tmp_path / "c.yaml"
    p.write_text('core_name: "X"\npaid_staff: 1\n')
    assert load_config(p).paid_staff == 1
    p.write_text('core_name: "X"\n')
    assert load_config(p).paid_staff is None
