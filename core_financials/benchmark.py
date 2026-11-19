"""Share-safe benchmark file (percentages, ratios, counts, days) and a cross-core comparison."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

UNITS = {"ratio", "fraction", "days", "count"}


def _fy(fy, complete):
    return f"{fy}" if int(fy) in set(int(c) for c in complete) else f"{fy}-partial"


def write_benchmark(fin, use, cfg, path) -> Path:
    rows = []
    add = lambda fy, metric, value, unit: rows.append(  # noqa: E731
        {"core": cfg.core_name, "fy": fy, "metric": metric, "value": round(float(value), 4), "unit": unit})
    if fin:
        comp = fin["complete_fys"]
        for fy, v in fin["cost_recovery_by_fy"].items():
            add(_fy(fy, comp), "cost_recovery", v, "ratio")
        gross: dict = {}
        for g in fin["revenue_groups"]:
            for fy, v in g["by_fy"].items():
                gross[int(fy)] = gross.get(int(fy), 0.0) + v
        for fy, v in fin["assessment"]["by_fy"].items():
            if gross.get(int(fy)):
                add(_fy(fy, comp), "assessment_per_dollar", v / gross[int(fy)], "fraction")
        names = {"personnel": "per_dollar_personnel", "supplies_services": "per_dollar_supplies_services",
                 "other_operating": "per_dollar_other", "surplus": "per_dollar_surplus"}
        for fy, pdict in fin["per_dollar"]["by_fy"].items():
            if pdict:
                for k, m in names.items():
                    add(_fy(fy, comp), m, pdict[k], "fraction")
    if use:
        comp = use["complete_fys"]
        for r in use["mix_by_fy"]:
            for k, v in r.items():
                if k != "fy":
                    add(_fy(r["fy"], comp), f"mix_{k.replace(' ', '_')}", v, "fraction")
        if use["concentration"]["top10"] is not None:
            add("all", "top10_share", use["concentration"]["top10"], "fraction")
        for r in use["new_vs_returning"]:
            tot = r["new"] + r["returning"]
            if tot:
                add(_fy(r["fy"], comp), "new_group_share", r["new"] / tot, "fraction")
        for r in use["turnaround"].get("by_fy", []):
            add(_fy(r["fy"], comp), "median_turnaround_days", r["median"], "days")
        for r in use["overview_by_fy"]:
            add(_fy(r["fy"], comp), "orders", r["orders"], "count")
            add(_fy(r["fy"], comp), "groups", r["groups"], "count")
    p = Path(path)
    pd.DataFrame(rows, columns=["core", "fy", "metric", "value", "unit"]).to_csv(p, index=False)
    return p


def combine_benchmarks(paths, out_xlsx, out_png) -> None:
    df = pd.concat([pd.read_csv(p, dtype={"fy": str}) for p in paths], ignore_index=True)
    cores = df["core"].unique().tolist()
    full = df[~df["fy"].str.endswith("-partial") & (df["fy"] != "all")]
    common = None
    for c in cores:
        fys = set(full.loc[full["core"] == c, "fy"])
        common = fys if common is None else common & fys
    fy = max(common) if common else None
    pick = df[(df["fy"] == fy) | (df["fy"] == "all")] if fy else df[df["fy"] == "all"]
    wide = pick.pivot_table(index=["metric", "unit"], columns="core", values="value", aggfunc="first").reset_index()
    wide.insert(0, "fy", fy or "all")
    with pd.ExcelWriter(out_xlsx) as xw:
        wide.to_excel(xw, sheet_name="Comparison", index=False)
        df.to_excel(xw, sheet_name="All rows", index=False)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .figures import PALETTE
    metrics = wide["metric"].tolist()[:12]
    n = len(metrics)
    cols = 3
    rows = max(1, (n + cols - 1) // cols)
    fig, axs = plt.subplots(rows, cols, figsize=(12, 2.6 * rows), squeeze=False)
    for ax in axs.flat:
        ax.axis("off")
    for ax, m in zip(axs.flat, metrics):
        ax.axis("on")
        r = wide[wide["metric"] == m].iloc[0]
        vals = [r.get(c) for c in cores]
        ax.barh(cores, [v if pd.notna(v) else 0 for v in vals], color=PALETTE[: len(cores)])
        unit = r["unit"]
        ax.set_title(m.replace("_", " ") + (f" (FY{fy})" if fy else ""), fontsize=9, loc="left")
        for i, v in enumerate(vals):
            if pd.notna(v):
                ax.text(v, i, f" {v:.0%}" if unit in ("fraction", "ratio") else f" {v:,.0f}", va="center",
                        fontsize=8)
        ax.tick_params(labelsize=8)
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
