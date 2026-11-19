"""Static figures (PNG + SVG) for slides and reports.

share/    percentages, ratios, counts and days only - safe to show other cores.
internal/ dollar amounts and supplier names - for the core and its department only.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import PathPatch, Rectangle  # noqa: E402
from matplotlib.path import Path as MPath  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

PALETTE = ["#C07F00", "#3D8FD9", "#5FAA4E", "#A96FE8", "#E86A3B", "#17A89A", "#C94F63"]
SURPLUS, DEFICIT, NEUTRAL = "#2e9e78", "#d4475a", "#8496AD"
INK, INK2, GRID, SURFACE = "#1d2533", "#5b6575", "#e6e8ec", "#fcfcfb"
AFF_ORDER = ["UC Davis", "Ext-UC", "Ext-NP", "Ext-FP", "Unknown"]
AFF_LABEL = {"UC Davis": "UC Davis", "Ext-UC": "Other UC", "Ext-NP": "External non-profit",
             "Ext-FP": "Industry", "Unknown": "Not yet classified"}

SHARE = ["cost_recovery_by_fy", "per_dollar", "assessment_per_dollar_by_fy", "sankey_share", "customer_mix",
         "concentration", "new_vs_returning", "turnaround", "backlog", "orders_heatmap"]
INTERNAL = ["balance_series", "bridge", "supplier_concentration", "forecast", "assessment_by_fy"]

plt.rcParams.update({
    "svg.fonttype": "none", "font.family": "sans-serif", "font.size": 10, "axes.edgecolor": GRID,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "axes.titlecolor": INK,
    "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.axisbelow": True, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "legend.frameon": False,
})

pct = FuncFormatter(lambda v, _: f"{v:.0%}")
money = FuncFormatter(lambda v, _: f"-${abs(v) / 1000:,.0f}k" if v < 0 else f"${v / 1000:,.0f}k")


def _fy_label(fy, complete):
    return f"FY{fy}" + ("" if fy in complete else "\n(partial)")


class _Saver:
    def __init__(self, out_dir: Path, cfg, written: dict):
        self.out, self.cfg, self.written = Path(out_dir), cfg, written

    def __call__(self, fig, name, audience, source):
        d = self.out / audience
        d.mkdir(parents=True, exist_ok=True)
        fig.text(0.01, 0.01, f"{self.cfg.core_name} · source: {source} · generated {date.today():%Y-%m-%d}",
                 fontsize=7.5, color=INK2, ha="left", va="bottom")
        paths = []
        for ext in ("png", "svg"):
            p = d / f"{name}.{ext}"
            fig.savefig(p, dpi=200 if ext == "png" else None, bbox_inches="tight")
            paths.append(p)
        plt.close(fig)
        self.written[name] = paths


def _fig(w=7.5, h=4.2):
    fig, ax = plt.subplots(figsize=(w, h))
    fig.subplots_adjust(bottom=0.16)
    return fig, ax


# ------------------------------------------------------------------ finance, share
def _cost_recovery(fin, save):
    cr = fin["cost_recovery_by_fy"]
    if not cr:
        return
    fys, comp = sorted(cr), fin["complete_fys"]
    fig, ax = _fig()
    bars = ax.bar([_fy_label(f, comp) for f in fys], [cr[f] for f in fys], color=PALETTE[1], width=0.55,
                  hatch=["" if f in comp else "//" for f in fys], edgecolor=SURFACE, linewidth=2)
    ax.axhline(1.0, color=INK, ls="--", lw=1.2)
    ax.text(0, 1.02, "Dashed line: 100% = earned revenue covers all operating expense. Hatched = partial year.",
            transform=ax.transAxes, color=INK2, fontsize=8.5)
    ax.bar_label(bars, labels=[f"{cr[f]:.0%}" for f in fys], padding=3, color=INK)
    ax.yaxis.set_major_formatter(pct)
    ax.set_ylim(0, max(1.25, max(cr.values()) * 1.25))
    ax.set_title("Cost recovery: earned revenue as a share of operating expense", pad=20)
    save(fig, "cost_recovery_by_fy", "share", "GL Transaction Listing")


def _per_dollar(fin, save):
    pd_ = fin["per_dollar"]
    rows = {f"FY{fy}": v for fy, v in pd_["by_fy"].items() if v} or ({"All data": pd_["all"]} if pd_["all"] else {})
    if not rows:
        return
    keys = [("personnel", "Personnel"), ("supplies_services", "Supplies & services"),
            ("other_operating", "Other operating"), ("assessment", "Campus assessment"),
            ("surplus", "Left over (surplus)")]
    colors = [PALETTE[1], PALETTE[2], PALETTE[5], NEUTRAL, SURPLUS]
    fig, ax = _fig(8, 1.2 + 0.7 * len(rows))
    labels = list(rows)
    right = 1.0
    for i, lab in enumerate(labels):
        left = 0.0
        for (k, name), c in zip(keys, colors):
            v = rows[lab][k]
            if k == "surplus" and v < 0:
                ax.annotate(f"deficit {abs(v) * 100:.0f}¢", (left, i), xytext=(6, 0), textcoords="offset points",
                            va="center", color=DEFICIT, fontsize=9, fontweight="bold")
                right = max(right, left)
                continue
            ax.barh(i, v, left=left, color=c, edgecolor=SURFACE, linewidth=2, height=0.6,
                    label=name if i == 0 else None)
            if v >= 0.05:
                ax.text(left + v / 2, i, f"{v * 100:.0f}¢", ha="center", va="center", color="white", fontsize=9,
                        fontweight="bold")
            left += v
    ax.set_yticks(range(len(labels)), labels)
    ax.invert_yaxis()
    ax.axvline(1.0, color=INK, lw=1, ls="--")
    ax.set_xlim(0, right + 0.16)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v * 100:.0f}¢"))
    ax.grid(axis="y", visible=False)
    ax.legend(ncol=5, loc="lower left", bbox_to_anchor=(0, 1.0), fontsize=8.5)
    ax.set_title("Where each dollar of revenue goes", pad=28)
    save(fig, "per_dollar", "share", "GL Transaction Listing")


def _gross_by_fy(fin):
    out: dict = {}
    for g in fin["revenue_groups"]:
        for fy, v in g["by_fy"].items():
            out[int(fy)] = out.get(int(fy), 0.0) + v
    return out


def _assessment_share(fin, save):
    a, gross = fin["assessment"], _gross_by_fy(fin)
    fys = [fy for fy in sorted(a["by_fy"]) if gross.get(fy)]
    if not fys:
        return
    vals = [a["by_fy"][fy] / gross[fy] * 100 for fy in fys]
    fig, ax = _fig()
    bars = ax.bar([_fy_label(f, fin["complete_fys"]) for f in fys], vals, color=NEUTRAL, width=0.55,
                  edgecolor=SURFACE, linewidth=2)
    ax.bar_label(bars, labels=[f"{v:.1f}¢" for v in vals], padding=3, color=INK)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.1f}¢"))
    ax.set_ylim(0, max(vals) * 1.2)
    ax.set_title("Campus income assessment, in cents per dollar of gross revenue", pad=20)
    m = a["match"]
    if m["months"]:
        ax.text(0, 1.02, f"It equals {a['rate']:.0%} of external sales in {m['matched']} of {m['months']} months.",
                transform=ax.transAxes, color=INK2, fontsize=8.5)
    save(fig, "assessment_per_dollar_by_fy", "share", "GL Transaction Listing")


def _band(ax, x0, y0a, y0b, x1, y1a, y1b, color):
    xm = (x0 + x1) / 2
    verts = [(x0, y0a), (xm, y0a), (xm, y1a), (x1, y1a), (x1, y1b), (xm, y1b), (xm, y0b), (x0, y0b), (x0, y0a)]
    codes = [MPath.MOVETO, MPath.CURVE4, MPath.CURVE4, MPath.CURVE4, MPath.LINETO, MPath.CURVE4, MPath.CURVE4,
             MPath.CURVE4, MPath.CLOSEPOLY]
    ax.add_patch(PathPatch(MPath(verts, codes), facecolor=color, alpha=0.45, edgecolor="none"))


def _sankey_share(fin, cfg, save):
    links = fin["sankey"]
    core = fin["core_node"]
    ins = [l for l in links if l["to"] == core]
    outs = [l for l in links if l["from"] == core]
    total = sum(l["flow"] for l in ins)
    if total <= 0:
        return
    # fold outflows under 2% into one item so labels stay legible
    small = [l for l in outs if l["flow"] / total < 0.02 and l["to"] != "Net Surplus"]
    if len(small) > 1:
        outs = [l for l in outs if l not in small] + [
            {"from": core, "to": "Smaller items", "flow": sum(l["flow"] for l in small)}]
    gap = 0.015
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.axis("off")
    ax.set_xlim(-0.6, 1.6)

    def draw(items, x, colors, side):
        scale = 1 - gap * (len(items) - 1)
        y_side, y_core = 1.0, 1.0
        for l, c in zip(items, colors):
            share = l["flow"] / total
            h = share * scale
            ax.add_patch(Rectangle((x - 0.02, y_side - h), 0.04, h, color=c))
            name = l["from"] if side == "left" else l["to"]
            ax.text(x - 0.04 if side == "left" else x + 0.04, y_side - h / 2, f"{name}  {share:.0%}",
                    ha="right" if side == "left" else "left", va="center", fontsize=8.5, color=INK)
            if side == "left":
                _band(ax, x + 0.02, y_side, y_side - h, 0.47, y_core, y_core - share, c)
            else:
                _band(ax, 0.53, y_core, y_core - share, x - 0.02, y_side, y_side - h, c)
            y_side -= h + gap
            y_core -= share

    in_colors = [PALETTE[i % len(PALETTE)] for i in range(len(ins))]
    out_colors = []
    for l in outs:
        out_colors.append(SURPLUS if l["to"] == "Net Surplus" else NEUTRAL if "Assessment" in l["to"]
                          else PALETTE[(len(out_colors) + 1) % len(PALETTE)])
    draw(ins, 0.0, in_colors, "left")
    draw(outs, 1.0, out_colors, "right")
    ax.add_patch(Rectangle((0.47, 0), 0.06, 1.0, color=cfg.brand.get("primary", "#022851")))
    ax.text(0.5, 1.03, core, ha="center", va="bottom", fontsize=10, fontweight="bold", color=INK)
    ax.set_ylim(-0.05, 1.1)
    ax.set_title("Follow the money: shares of gross revenue", loc="left")
    save(fig, "sankey_share", "share", "GL Transaction Listing")


# ------------------------------------------------------------------ usership, share
def _customer_mix(use, save):
    mix = use["mix_by_fy"]
    if not mix:
        return
    comp = use["complete_fys"]
    labels = [_fy_label(r["fy"], comp) for r in mix]
    present = [a for a in AFF_ORDER if any(r.get(a) for r in mix)]
    fig, ax = _fig()
    bottom = [0.0] * len(mix)
    for i, a in enumerate(present):
        vals = [r.get(a, 0.0) for r in mix]
        bars = ax.bar(labels, vals, bottom=bottom, color=PALETTE[i], edgecolor=SURFACE, linewidth=2, width=0.6,
                      label=AFF_LABEL[a])
        ax.bar_label(bars, labels=[f"{v:.0%}" if v >= 0.06 else "" for v in vals], label_type="center",
                     color="white", fontsize=8.5, fontweight="bold")
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.yaxis.set_major_formatter(pct)
    ax.set_ylim(0, 1)
    ax.legend(ncol=len(present), loc="lower left", bbox_to_anchor=(0, 1.0), fontsize=8.5)
    ax.set_title("Who the core serves: share of revenue by customer type", pad=28)
    save(fig, "customer_mix", "share", "PPMS Order details")


def _concentration(use, save):
    c = use["concentration"]
    if not c["n_groups"]:
        return
    fig, ax = _fig(6.5, 3.8)
    labs = ["Top 5 labs", "Top 10 labs", "Top 20 labs"]
    vals = [c["top5"], c["top10"], c["top20"]]
    bars = ax.bar(labs, vals, color=PALETTE[3], width=0.55, edgecolor=SURFACE, linewidth=2)
    ax.bar_label(bars, labels=[f"{v:.0%}" for v in vals], padding=3, color=INK)
    ax.yaxis.set_major_formatter(pct)
    ax.set_ylim(0, 1.05)
    ax.set_title(f"Customer breadth: share of revenue from the largest labs (of {c['n_groups']})")
    save(fig, "concentration", "share", "PPMS Order details")


def _new_vs_returning(use, save):
    rows = use["new_vs_returning"]
    if not rows:
        return
    comp = use["complete_fys"]
    labels = [_fy_label(r["fy"], comp) for r in rows]
    x = range(len(rows))
    fig, ax = _fig()
    b1 = ax.bar([i - 0.18 for i in x], [r["new"] for r in rows], width=0.34, color=PALETTE[2], label="New labs")
    b2 = ax.bar([i + 0.18 for i in x], [r["returning"] for r in rows], width=0.34, color=PALETTE[1],
                label="Returning labs")
    ax.bar_label(b1, padding=2, color=INK, fontsize=8.5)
    ax.bar_label(b2, padding=2, color=INK, fontsize=8.5)
    ax.set_xticks(list(x), labels)
    ax.legend(ncol=2, loc="lower left", bbox_to_anchor=(0, 1.0))
    ax.set_title("New and returning labs each fiscal year", pad=28)
    save(fig, "new_vs_returning", "share", "PPMS Order details")


def _turnaround(use, save):
    t = use["turnaround"]
    if not t.get("measurable", True) or not t["by_service"]:
        return
    svc = t["by_service"][:8]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.2), gridspec_kw={"width_ratios": [1.1, 1]})
    fig.subplots_adjust(bottom=0.18, wspace=0.45)
    y = range(len(svc))
    ax1.hlines(list(y), [s["p25"] for s in svc], [s["p75"] for s in svc], color=PALETTE[1], lw=6, alpha=0.4)
    ax1.plot([s["median"] for s in svc], list(y), "o", color=PALETTE[1], ms=8)
    for i, s in enumerate(svc):
        ax1.annotate(f"{s['median']:.0f} d", (s["p75"], i), xytext=(6, 0), textcoords="offset points",
                     va="center", fontsize=8.5, color=INK)
    ax1.set_yticks(list(y), [f"{s['service']} (n={s['n']})" for s in svc], fontsize=8.5)
    ax1.invert_yaxis()
    ax1.set_xlabel("days from accepted to completed (dot = median, bar = middle half)")
    ax1.set_title("Turnaround by service")
    q = t["by_quarter"]
    ax2.plot([r["quarter"] for r in q], [r["median"] for r in q], color=PALETTE[0], lw=2, marker="o", ms=5)
    ax2.set_ylabel("median days")
    ax2.set_title("Median turnaround by quarter")
    ax2.tick_params(axis="x", rotation=60, labelsize=7.5)
    save(fig, "turnaround", "share", "PPMS Order details")


def _backlog(use, save):
    b = use["backlog_monthly"]
    if not b:
        return
    fig, ax = _fig()
    ax.plot([r["month"] for r in b], [r["open"] for r in b], color=PALETTE[4], lw=2)
    ax.fill_between([r["month"] for r in b], [r["open"] for r in b], color=PALETTE[4], alpha=0.12)
    step = max(1, len(b) // 12)
    ax.set_xticks(range(0, len(b), step), [b[i]["month"] for i in range(0, len(b), step)], rotation=45,
                  fontsize=8)
    ax.set_ylabel("open orders at month end")
    ax.set_title("Backlog: orders accepted but not yet completed")
    save(fig, "backlog", "share", "PPMS Order details")


def _heatmap(use, save):
    h = use["orders_heatmap"]
    if not h["fys"]:
        return
    import numpy as np
    data = np.array([[np.nan if v is None else v for v in row] for row in h["counts"]], dtype=float)
    fig, ax = _fig(8, 1.6 + 0.45 * len(h["fys"]))
    im = ax.imshow(data, cmap="Blues", aspect="auto")
    names = ["Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun"]
    ax.set_xticks(range(12), names)
    ax.set_yticks(range(len(h["fys"])), [f"FY{f}" for f in h["fys"]])
    ax.grid(False)
    vmax = np.nanmax(data) or 1
    for i in range(data.shape[0]):
        for j in range(12):
            if np.isnan(data[i, j]):
                ax.text(j, i, "–", ha="center", va="center", fontsize=8, color=INK2)
                continue
            ax.text(j, i, int(data[i, j]), ha="center", va="center", fontsize=8,
                    color="white" if data[i, j] > vmax * 0.55 else INK)
    ax.text(0, -0.12, "– = outside the dates in the export", transform=ax.transAxes, fontsize=8, color=INK2,
            va="top")
    fig.colorbar(im, ax=ax, fraction=0.025, label="orders")
    ax.set_title("Busy and quiet months: orders placed")
    save(fig, "orders_heatmap", "share", "PPMS Order details")


# ------------------------------------------------------------------ internal (dollars, names)
def _balance(fin, save):
    s = fin["balance_series"]
    if not s:
        return
    fig, ax = _fig()
    xs, ys = [r["month"] for r in s], [r["cumulative_net"] for r in s]
    ax.plot(xs, ys, color=INK, lw=2)
    ax.fill_between(xs, ys, 0, where=[y >= 0 for y in ys], color=SURPLUS, alpha=0.25, interpolate=True)
    ax.fill_between(xs, ys, 0, where=[y < 0 for y in ys], color=DEFICIT, alpha=0.25, interpolate=True)
    ax.axhline(0, color=INK2, lw=0.8)
    step = max(1, len(xs) // 12)
    ax.set_xticks(range(0, len(xs), step), [xs[i] for i in range(0, len(xs), step)], rotation=45, fontsize=8)
    ax.yaxis.set_major_formatter(money)
    ax.set_title(f"Cumulative operating surplus (+) or deficit (−) since {xs[0]}")
    save(fig, "balance_series", "internal", "GL Transaction Listing")


def _bridge(fin, save):
    b = fin["bridge"]
    if not b["steps"]:
        return
    steps = b["steps"]
    fig, ax = _fig(8.5, 4.8)
    fig.subplots_adjust(bottom=0.32)
    run = 0.0
    for i, s in enumerate(steps):
        total_bar = i == 0 or s["step"].startswith("=")
        base = 0.0 if total_bar else run
        color = INK2 if total_bar else (SURPLUS if s["amount"] >= 0 else DEFICIT)
        ax.bar(i, s["amount"], bottom=base, color=color, width=0.6)
        top = max(base, base + s["amount"])
        ax.text(i, top, f"{s['amount'] / 1000:,.0f}k", ha="center", va="bottom", fontsize=8, color=INK)
        run = s["amount"] if total_bar else run + s["amount"]
    ax.set_xticks(range(len(steps)), [s["step"] for s in steps], rotation=25, ha="right", fontsize=8.5)
    ax.yaxis.set_major_formatter(money)
    ax.margins(y=0.12)
    ax.axhline(0, color=INK2, lw=0.8)
    ax.set_title(f"What moved the balance in FY{b['fy']}")
    save(fig, "bridge", "internal", "GL Transaction Listing + Department P&L")


def _suppliers(aggie, save):
    c = (aggie or {}).get("supplier_concentration")
    if not c or not c["top"]:
        return
    top = c["top"][::-1]
    fig, ax = _fig(8, 1.2 + 0.38 * len(top))
    bars = ax.barh([t["supplier"].title() for t in top], [t["share"] for t in top], color=PALETTE[3], height=0.6)
    ax.bar_label(bars, labels=[f"{t['share']:.0%}" for t in top], padding=3, color=INK, fontsize=8.5)
    ax.xaxis.set_major_formatter(pct)
    ax.tick_params(axis="y", labelsize=8)
    ax.set_title(f"Top suppliers' share of non-personnel PO spend (top {len(top)} = {c['top_n_share']:.0%})")
    save(fig, "supplier_concentration", "internal", "PO spend report")


def _forecast(fin, save):
    f = fin["forecast"]
    if not f:
        return
    nets = {int(r["key"][2:]): r["net"] for r in fin["series_fy"]}
    fys = list(f["based_on_fys"])
    fig, ax = _fig()
    labels = [f"FY{fy}\n(actual)" for fy in fys] + [f"FY{f['fy']}\nyear to date", f"FY{f['fy']}\nprojected"]
    vals = [nets[fy] for fy in fys] + [f["ytd_net"], f["projected"]]
    colors = [SURPLUS if v >= 0 else DEFICIT for v in vals]
    bars = ax.bar(labels, vals, color=colors, width=0.55, alpha=0.85,
                  hatch=[""] * len(fys) + ["", "//"], edgecolor=SURFACE)
    ax.bar_label(bars, labels=[f"{v / 1000:,.0f}k" for v in vals], padding=3, fontsize=8.5, color=INK)
    i = len(labels) - 1
    ax.errorbar(i, f["projected"], yerr=[[f["projected"] - f["low"]], [f["high"] - f["projected"]]],
                color=INK, capsize=8, lw=1.5)
    ax.text(0, 1.02, f"Projection = {f['months_seen']} months so far + the remaining months as they went in "
                     f"{', '.join('FY' + str(x) for x in fys)}. Whisker = range across those years.",
            transform=ax.transAxes, color=INK2, fontsize=8)
    ax.axhline(0, color=INK2, lw=0.8)
    ax.yaxis.set_major_formatter(money)
    ax.set_title(f"Year-end forecast for FY{f['fy']}: operating surplus or deficit", pad=20)
    save(fig, "forecast", "internal", "GL Transaction Listing")


def _assessment_dollars(fin, save):
    a = fin["assessment"]
    if not a["by_fy"]:
        return
    fys = sorted(a["by_fy"])
    fig, ax = _fig()
    bars = ax.bar([_fy_label(f, fin["complete_fys"]) for f in fys], [a["by_fy"][f] for f in fys], color=NEUTRAL,
                  width=0.55)
    ax.bar_label(bars, labels=[f"${a['by_fy'][f]:,.0f}" for f in fys], padding=3, color=INK, fontsize=8.5)
    ax.yaxis.set_major_formatter(money)
    ax.set_title("Campus income assessment by fiscal year (partial years are not comparable)")
    save(fig, "assessment_by_fy", "internal", "GL Transaction Listing")


def render_figures(fin, use, cfg, out_dir, aggie: dict | None = None) -> dict:
    written: dict = {}
    # Remove this tool's own figures from an earlier run, so a chart that no longer applies cannot linger.
    for sub, names in (("share", SHARE), ("internal", INTERNAL)):
        for name in names:
            for ext in ("png", "svg"):
                (Path(out_dir) / sub / f"{name}.{ext}").unlink(missing_ok=True)
    save = _Saver(Path(out_dir), cfg, written)
    if fin:
        _cost_recovery(fin, save)
        _per_dollar(fin, save)
        _assessment_share(fin, save)
        _sankey_share(fin, cfg, save)
        _balance(fin, save)
        _bridge(fin, save)
        _forecast(fin, save)
        _assessment_dollars(fin, save)
    if use:
        _customer_mix(use, save)
        _concentration(use, save)
        _new_vs_returning(use, save)
        _turnaround(use, save)
        _backlog(use, save)
        _heatmap(use, save)
    _suppliers(aggie, save)
    return written
