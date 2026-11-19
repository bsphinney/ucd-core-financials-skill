import copy

import pandas as pd

from core_financials.benchmark import UNITS, combine_benchmarks, write_benchmark


def test_benchmark_no_dollars_no_names(sample, tmp_path):
    p = write_benchmark(sample["fin"], sample["use"], sample["cfg"], tmp_path / "benchmark.csv")
    df = pd.read_csv(p, dtype=str)
    assert list(df.columns) == ["core", "fy", "metric", "value", "unit"]
    assert set(df["unit"]) <= UNITS
    assert not df["value"].str.contains(r"\$").any()
    text = p.read_text().casefold()
    for g in sample["orders"]["group"].unique():
        assert g.split(",")[0].casefold() not in text
    assert {"cost_recovery", "top10_share", "median_turnaround_days"} <= set(df["metric"])
    assert df["fy"].str.endswith("-partial").any()


def test_combine_two_cores(sample, tmp_path):
    a = write_benchmark(sample["fin"], sample["use"], sample["cfg"], tmp_path / "a.csv")
    cfg2 = copy.copy(sample["cfg"])
    cfg2.core_name = "Second Example Core"
    b = write_benchmark(sample["fin"], sample["use"], cfg2, tmp_path / "b.csv")
    combine_benchmarks([a, b], tmp_path / "compare.xlsx", tmp_path / "compare.png")
    wide = pd.read_excel(tmp_path / "compare.xlsx")
    assert {"Example Imaging Core", "Second Example Core"} <= set(wide.columns)
    assert (tmp_path / "compare.png").exists()
