import re

import pytest

from core_financials.aggie import supplier_concentration
from core_financials.figures import INTERNAL, SHARE, render_figures


def _svg_text(path):
    svg = path.read_text()
    chunks = re.findall(r"<text\b[^>]*>(.*?)</text>", svg, flags=re.S)
    return " ".join(re.sub(r"<[^>]+>", " ", c) for c in chunks)


@pytest.fixture(scope="module")
def rendered(sample, tmp_path_factory):
    out = tmp_path_factory.mktemp("figs")
    aggie = {"supplier_concentration": supplier_concentration(sample["po"], sample["cfg"])}
    render_figures(sample["fin"], sample["use"], sample["cfg"], out, aggie=aggie)
    return out


def test_expected_files_exist(rendered):
    assert len(SHARE) == 10 and len(INTERNAL) == 5
    for sub, names in (("share", SHARE), ("internal", INTERNAL)):
        for n in names:
            for ext in ("png", "svg"):
                assert (rendered / sub / f"{n}.{ext}").exists(), f"{sub}/{n}.{ext}"


def test_share_figures_have_no_dollars_or_names(rendered, sample):
    groups = {g.casefold() for g in sample["orders"]["group"].unique()}
    surnames = {g.split(",")[0].strip().casefold() for g in groups}
    for svg in (rendered / "share").glob("*.svg"):
        text = _svg_text(svg)
        assert text.strip(), f"{svg.name} has no searchable text (svg.fonttype must be 'none')"
        assert "$" not in text, svg.name
        low = text.casefold()
        assert not [s for s in surnames if re.search(rf"\b{re.escape(s)}\b", low)], svg.name


def test_missing_input_skips(sample, tmp_path):
    written = render_figures(None, sample["use"], sample["cfg"], tmp_path)
    assert set(written) == {"customer_mix", "concentration", "new_vs_returning", "turnaround", "backlog",
                            "orders_heatmap"}
    assert not (tmp_path / "internal").exists() or not any((tmp_path / "internal").iterdir())


def test_stale_figures_from_earlier_run_are_removed(sample, tmp_path):
    from core_financials.figures import render_figures
    (tmp_path / "share").mkdir()
    (tmp_path / "share" / "turnaround.png").write_bytes(b"old")
    (tmp_path / "share" / "notes.txt").write_text("mine")
    out = render_figures(sample["fin"], None, sample["cfg"], tmp_path)
    assert "turnaround" not in out
    assert not (tmp_path / "share" / "turnaround.png").exists()
    assert (tmp_path / "share" / "notes.txt").exists()


def test_bridge_leaves_room_above_tallest_bar(sample, tmp_path, monkeypatch):
    import matplotlib.pyplot as plt
    from core_financials import figures
    seen = {}
    real = plt.Figure.savefig

    def spy(self, *a, **k):
        for ax in self.axes:
            if "What moved" in ax.get_title("left") + ax.get_title():
                tops = [r.get_y() + r.get_height() for r in ax.patches]
                seen["ok"] = ax.get_ylim()[1] > max(tops) * 1.05
        return real(self, *a, **k)
    monkeypatch.setattr(plt.Figure, "savefig", spy)
    figures.render_figures(sample["fin"], None, sample["cfg"], tmp_path)
    assert seen["ok"]
