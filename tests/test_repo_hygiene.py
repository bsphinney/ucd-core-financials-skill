"""No real Proteomics Core codes, names or figures may appear anywhere in the repo.

The forbidden values are stored only as SHA-256 digests (tests/forbidden_sha256.txt),
so this file does not reveal them either.
"""
import hashlib
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = set((ROOT / "tests" / "forbidden_sha256.txt").read_text().split())
SKIP_DIRS = {".git", "dist", "__pycache__", ".pytest_cache", ".superpowers", "out", "node_modules"}
TEXT_EXT = {".py", ".md", ".txt", ".yaml", ".yml", ".html", ".csv", ".json", ".svg", ".ini", ".cfg", ""}


def _tokens(text):
    text = re.sub(r"(?<=\d),(?=\d)", "", text.lower())
    toks = re.findall(r"[a-z0-9]+", text)
    yield from toks
    for a, b in zip(toks, toks[1:]):
        yield f"{a} {b}"


def _files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            p = Path(dirpath) / f
            if p.suffix.lower() in TEXT_EXT and p.name != "forbidden_sha256.txt":
                yield p


def test_no_real_core_data_in_repo():
    hits = []
    for p in _files():
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        for t in _tokens(text):
            if hashlib.sha256(t.encode()).hexdigest() in FORBIDDEN:
                hits.append(str(p.relative_to(ROOT)))
                break
    assert not hits, f"real-data tokens found in: {hits}"
