import importlib.util
from pathlib import Path

import pytest

from core_financials import aggie, finance
from core_financials.config import load_config
from core_financials.gl import classify, load_gl
from core_financials.ppms import load_orders

ROOT = Path(__file__).resolve().parents[1]


def _gen():
    spec = importlib.util.spec_from_file_location("generate", ROOT / "sample_data" / "generate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.generate


def _load(folder):
    cfg = load_config(folder / "core-config.yaml")
    files = sorted(folder.glob("*.xlsx"))
    gl = classify(load_gl(files, cfg), cfg)
    return cfg, {
        "gl": gl,
        "po": aggie.load_po(files, cfg),
        "glide": aggie.load_glide(files),
        "orders": load_orders(files),
        "balances": aggie.load_balances(folder / "pnl_fy2026.xlsx"),
    }


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    a, b = tmp_path_factory.mktemp("a"), tmp_path_factory.mktemp("b")
    _gen()(a)
    _gen()(b)
    return a, b


def test_generate_is_deterministic(generated):
    (_, da), (_, db) = _load(generated[0]), _load(generated[1])
    for k in ["gl", "po", "glide", "orders"]:
        assert da[k].drop(columns=["source_file"], errors="ignore").to_csv() == \
            db[k].drop(columns=["source_file"], errors="ignore").to_csv(), k
    assert da["balances"] == db["balances"]


def test_sample_loads(generated):
    cfg, d = _load(generated[0])
    for k in ["gl", "po", "glide", "orders"]:
        assert len(d[k]) > 0, k
    assert len(d["balances"]) >= 3
    assert set(d["gl"]["layout"]) == {"page"}
    assert d["gl"]["fy"].min() == 2024 and d["gl"]["fy"].max() == 2027
    assert set(cfg.funds) == {"12100", "16200", "13U00"}


def test_sample_has_assessment_mismatch_month(generated):
    cfg, d = _load(generated[0])
    m = finance.assessment(d["gl"], cfg)["match"]
    assert 0.9 < m["rate"] < 1


def test_committed_sample_matches_generator(generated):
    _, fresh = _load(generated[0])
    _, committed = _load(ROOT / "sample_data" / "example_core")
    assert fresh["gl"]["amount"].sum() == pytest.approx(committed["gl"]["amount"].sum())
    assert len(fresh["orders"]) == len(committed["orders"])


def test_sample_pnl_reconciles_with_sample_ledger(sample):
    from core_financials import finance as F
    from core_financials.checks import run_checks
    fin = F.compute_finance(sample["gl"], sample["cfg"], None, pnl=sample["balances"])
    assert fin["bridge"]["pnl_fy"] == 2026
    c = [c for c in run_checks(fin, None, []) if c.name.startswith("bridge ending")]
    assert c and c[0].passed
