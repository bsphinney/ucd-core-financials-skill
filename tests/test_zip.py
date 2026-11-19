import subprocess
import sys
import zipfile

from core_financials import SKILL_ROOT


def test_zip_contents(tmp_path):
    sys.path.insert(0, str(SKILL_ROOT / "tools"))
    from build_skill_zip import build_zip
    z = build_zip(SKILL_ROOT, tmp_path / "ucd-core-financials.zip")
    names = zipfile.ZipFile(z).namelist()
    top = "ucd-core-financials/"
    for need in ["SKILL.md", "run.py", "requirements.txt", "core_financials/cli.py", "assets/dashboard_template.html",
                 "reference/pulling-reports.md", "sample_data/example_core/core-config.yaml"]:
        assert top + need in names, need
    for bad in ["tests/", "docs/", "tools/", "__pycache__", ".git/", "/out/", ".superpowers", "affiliations.csv"]:
        assert not any(bad in n for n in names), bad
    assert z.stat().st_size < 10 * 1024 * 1024


def test_unzipped_skill_builds_sample(tmp_path):
    sys.path.insert(0, str(SKILL_ROOT / "tools"))
    from build_skill_zip import build_zip
    z = build_zip(SKILL_ROOT, tmp_path / "s.zip")
    zipfile.ZipFile(z).extractall(tmp_path / "x")
    root = tmp_path / "x" / "ucd-core-financials"
    r = subprocess.run([sys.executable, str(root / "run.py"), "build", str(root / "sample_data" / "example_core")],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (root / "sample_data" / "example_core" / "out" / "dashboard.html").exists()
