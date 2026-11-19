"""Build dist/ucd-core-financials.zip for upload to claude.ai or Claude Desktop."""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

INCLUDE = ["SKILL.md", "README.md", "LICENSE", "run.py", "requirements.txt", "core_financials", "assets",
           "reference", "sample_data"]
SKIP_PARTS = {"__pycache__", ".git", ".pytest_cache", "out", ".DS_Store", ".superpowers"}
SKIP_NAMES = {"affiliations.csv"}


def build_zip(repo: Path, out: Path) -> Path:
    repo, out = Path(repo), Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    import subprocess
    # Only files git tracks: a real-data folder dropped into the working tree can never be packaged.
    tracked = set(subprocess.run(["git", "-C", str(repo), "ls-files"], capture_output=True, text=True,
                                 check=True).stdout.splitlines())
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for item in INCLUDE:
            p = repo / item
            files = [p] if p.is_file() else sorted(f for f in p.rglob("*") if f.is_file())
            for f in files:
                if f.relative_to(repo).as_posix() not in tracked:
                    continue
                rel = f.relative_to(repo)
                if SKIP_PARTS & set(rel.parts) or f.name in SKIP_NAMES or f.suffix == ".pyc":
                    continue
                z.write(f, Path("ucd-core-financials") / rel)
    return out


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    print(build_zip(root, Path(sys.argv[1]) if len(sys.argv) > 1 else root / "dist" / "ucd-core-financials.zip"))
