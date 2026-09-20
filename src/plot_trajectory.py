"""承诺进度缺口图：每条轨迹一个横向面板。data/trajectory_gaps.json → figures/trajectory_gap.png。"""
import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FIG_DIR = ROOT / "figures"
os.makedirs(FIG_DIR, exist_ok=True)
DPI = 120

STATUS_COLOR = {
    "ON_TRACK": "#3ca951",
    "TRAJECTORY_INSUFFICIENT": "#efb118",
    "MOVING_AWAY": "#ff725c",
    "UNDEFINED": "#9498a0",
}


def draw(ax, r):
    color = STATUS_COLOR.get(r["status"], "#9498a0")
    latest, target = r["latest_value"], r["target_value"]

    # 已达成部分
    ax.barh([0], [latest], height=0.42, color=color, alpha=0.85, zorder=2)
    ax.text(latest, -0.30, f"{latest:g}{r['unit']} ({r['latest_year']})",
            va="top", ha="left", fontsize=8, color=color)

    # 目标竖线
    ax.axvline(target, color="#333", lw=1.6, zorder=3)
    ax.text(target, -0.42, f"target {target:g}{r['unit']} by {r['target_year']}",
            va="top", ha="right", fontsize=8, color="#333")

    # 按已实现速度外推到目标位置，标注预计达成年份
    proj = r["projected_year"]
    ax.plot([latest, target], [0, 0], ls=":", lw=1.6, color=color, zorder=4)
    if proj is None:
        note = "never at current pace" if r["status"] == "MOVING_AWAY" else "pace undefined"
    else:
        note = f"reaches target ≈ {proj:.0f}"
        if r["shortfall_years"] and r["shortfall_years"] > 0:
            note += f"  (+{r['shortfall_years']:.0f} yr late)"
    # 减排类目标（target < latest）的外推段落在柱子内部，标注上移避免被柱体盖住
    note_y = 0.30 if target < latest else 0.02
    ax.text((latest + target) / 2, note_y, note, va="bottom", ha="center",
            fontsize=8, color=color, style="italic",
            bbox=dict(fc="white", ec="none", alpha=0.75, pad=1.2))

    lo = min(0, latest, target)
    hi = max(latest, target)
    ax.set_xlim(lo, hi + (hi - lo) * 0.18 or 1)
    ax.set_ylim(-0.8, 0.8)
    ax.set_yticks([])
    ax.set_title(f"{r['company']} — {r['metric']}   "
                 f"[required {r['required_pace']:g}/yr vs achieved {r['achieved_pace']:g}/yr]"
                 if r["required_pace"] is not None and r["achieved_pace"] is not None
                 else f"{r['company']} — {r['metric']}",
                 fontsize=9, loc="left")
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="x", alpha=0.15)


def main():
    rows = json.loads((DATA / "trajectory_gaps.json").read_text(encoding="utf-8"))
    if not rows:
        print("trajectory_gaps.json 为空，无可绘制内容")
        return

    fig, axes = plt.subplots(len(rows), 1, figsize=(10, 1.5 * len(rows) + 1.2))
    for ax, r in zip([axes] if len(rows) == 1 else axes, rows):
        draw(ax, r)

    seen = [s for s in STATUS_COLOR if any(r["status"] == s for r in rows)]
    fig.legend([Line2D([0], [0], color=STATUS_COLOR[s], lw=6) for s in seen],
               [s.replace("_", " ").title() for s in seen],
               loc="lower center", ncol=len(seen), frameon=False, fontsize=8)
    fig.suptitle("Commitment pace: achieved vs required", fontsize=11)
    fig.tight_layout(rect=(0, 0.06, 1, 0.97))
    fig.savefig(FIG_DIR / "trajectory_gap.png", dpi=DPI)
    plt.close(fig)
    print(f"{len(rows)} panels → figures/trajectory_gap.png")


if __name__ == "__main__":
    main()
