"""Commitment trackability: the share of quantified commitments for which the same
report does not contain two yearly observations.

data/trajectory_audit.json → figures/commitment_verifiability.png
"""
import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FIG_DIR = ROOT / "figures"
os.makedirs(FIG_DIR, exist_ok=True)

COLORS = {"Alphabet": "#4269d0", "Microsoft": "#efb118", "Amazon": "#ff725c"}
DPI = 120


def main():
    audit = json.loads((DATA / "trajectory_audit.json").read_text(encoding="utf-8"))
    companies = sorted({a["company"] for a in audit})

    stats = []
    for co in companies:
        rows = [a for a in audit if a["company"] == co]
        untrackable = sum(a["outcome"] == "discarded" for a in rows)
        stats.append({"company": co, "n": len(rows), "untrackable": untrackable,
                      "pct": untrackable / len(rows) * 100})

    fig, ax = plt.subplots(figsize=(7, 4.6))
    bars = ax.bar([s["company"] for s in stats], [s["pct"] for s in stats],
                  color=[COLORS.get(s["company"], "#888") for s in stats], width=0.55)
    for b, s in zip(bars, stats):
        ax.text(b.get_x() + b.get_width() / 2, s["pct"] + 1.5,
                f"{s['pct']:.0f}%", ha="center", va="bottom", fontweight="bold")
        ax.text(b.get_x() + b.get_width() / 2, s["pct"] / 2,
                f"{s['untrackable']} / {s['n']}", ha="center", va="center",
                color="white", fontsize=9)

    total = sum(s["untrackable"] for s in stats), sum(s["n"] for s in stats)
    ax.set_ylim(0, 108)
    ax.set_ylabel("% of quantified commitments")
    ax.set_title("Commitments with fewer than two trackable observations\n"
                 f"(all three reports: {total[0]} of {total[1]})", fontsize=11)
    ax.grid(axis="y", alpha=0.2)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "commitment_verifiability.png", dpi=DPI)
    plt.close(fig)

    for s in stats:
        print(f"{s['company']:<12}{s['untrackable']:>3} / {s['n']:<3} = {s['pct']:>5.1f}%")
    print(f"{'TOTAL':<12}{total[0]:>3} / {total[1]:<3} = {total[0] / total[1] * 100:>5.1f}%")
    print("→ figures/commitment_verifiability.png")


if __name__ == "__main__":
    main()
