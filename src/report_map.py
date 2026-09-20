"""报告地图与段落详情的渲染件，供 app_v2 使用（app.py 保持原样不动）。"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from src.ui_text import MECHANISM_COLORS, mechanism_of_region, say_mechanism

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MIN_MARK_PX = 8


def load_regions(companies=None):
    regions = json.loads((DATA / "anomaly_regions.json").read_text(encoding="utf-8"))
    for r in regions:
        r["mechanism"] = mechanism_of_region(r.get("flag_types", {}))
    if companies:
        regions = [r for r in regions if r["company"] in companies]
    regions.sort(key=lambda r: (r["company"], r["rel_pos"][0]))
    return regions


def render_map(regions, counts):
    """每家一条 0→1 的横条，命中区间画成色块。窄区间加宽到 8px 以便点选。"""
    companies = list(counts)
    fig, ax = plt.subplots(figsize=(10, 0.85 * len(companies) + 1.0))
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.6, len(companies) - 0.4)

    fig.canvas.draw()   # 先布局再量轴宽，才能把 8px 换算成数据单位
    ax_px = ax.get_window_extent(fig.canvas.get_renderer()).width
    min_w = MIN_MARK_PX / ax_px if ax_px else 0.006

    for y, company in enumerate(companies):
        ax.barh(y, 1.0, height=0.34, color="#e9ecef", zorder=1)
        for r in regions:
            if r["company"] != company:
                continue
            start, end = r["rel_pos"]
            ax.barh(y, max(end - start, min_w), left=start, height=0.34, zorder=2,
                    color=MECHANISM_COLORS.get(r["mechanism"], "#9498a0"))

    ax.set_yticks(range(len(companies)), companies)
    ax.invert_yaxis()
    ax.set_xticks([0, 1], ["start of report", "end"])
    ax.tick_params(axis="x", length=0)
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)

    seen = [m for m in MECHANISM_COLORS if any(r["mechanism"] == m for r in regions)]
    ax.legend([Line2D([0], [0], color=MECHANISM_COLORS[m], lw=7) for m in seen],
              [say_mechanism(m) for m in seen], loc="upper center",
              bbox_to_anchor=(0.5, -0.12), ncol=len(seen) or 1, frameon=False, fontsize=9)
    fig.tight_layout()
    return fig


def region_option(r):
    return (f"{r['company']} · {round(r['rel_pos'][0] * 100)}% into report · "
            f"{say_mechanism(r['mechanism'])}")


def span_caption(regions):
    spans = [(r["rel_pos"][1] - r["rel_pos"][0]) * 100 for r in regions]
    return (f"Each block marks a run of sentences where accounting-disclosure flags cluster. "
            f"True spans run from {min(spans):.1f}% to {max(spans):.1f}% of a report "
            f"({min(r['n_sentences'] for r in regions)}–"
            f"{max(r['n_sentences'] for r in regions)} sentences); narrow blocks are widened "
            f"to {MIN_MARK_PX}px so they stay visible.")
