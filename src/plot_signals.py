"""三张句级信号图：趋势、累计话术强度、Microsoft 的 future vs verification 对照。"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data"
FIGSIZE, DPI = (10, 5), 120
COLORS = {"Alphabet": "#4269d0", "Microsoft": "#efb118", "Amazon": "#ff725c"}


def load():
    rows = json.loads((OUT / "signals.json").read_text(encoding="utf-8"))
    groups = {}
    for r in rows:
        groups.setdefault(r["company"], []).append(r)
    return groups


def plot_vagueness(groups):
    fig, ax = plt.subplots(figsize=FIGSIZE)
    for company, g in groups.items():
        ax.plot([r["rel_pos"] for r in g], [r["vagueness_smooth"] for r in g],
                label=company, color=COLORS.get(company), lw=1.2)
    ax.set_xlabel("Relative position in report")
    ax.set_ylabel("Vagueness (20-sentence moving average)")
    ax.set_title("Vagueness across the report")
    ax.legend()
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(OUT / "sig_vagueness.png", dpi=DPI)
    plt.close(fig)


def plot_cumulative(groups):
    fig, ax = plt.subplots(figsize=FIGSIZE)
    for company, g in groups.items():
        n = len(g)
        total, cum = 0, []
        for r in g:
            total += r["hedge"]
            cum.append(total / n)
        x = [r["rel_pos"] for r in g]
        ax.plot(x, cum, label=company, color=COLORS.get(company), lw=1.4)
        # 终点标注：斜率即单位句子的话术强度
        ax.annotate(f"{cum[-1]:.3f}", (x[-1], cum[-1]), textcoords="offset points",
                    xytext=(6, 0), va="center", color=COLORS.get(company), fontsize=9)
    ax.set_xlim(0, 1.06)
    ax.set_xlabel("Relative position in report")
    ax.set_ylabel("Cumulative hedge words per sentence")
    ax.set_title("Cumulative hedging intensity (slope = hedge words per sentence)")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(OUT / "sig_cumulative.png", dpi=DPI)
    plt.close(fig)


def plot_overlay(groups, company="Microsoft"):
    g = groups[company]
    x = [r["rel_pos"] for r in g]
    fig, ax1 = plt.subplots(figsize=FIGSIZE)

    flagged = [r["rel_pos"] for r in g if r["flags"] > 0]
    for pos in flagged:
        ax1.axvline(pos, color="#999999", ls="--", lw=0.4, alpha=0.18, zorder=0)

    ax1.plot(x, [r["future_smooth"] for r in g], color="#4269d0", lw=1.3, label="future")
    ax1.set_xlabel("Relative position in report")
    ax1.set_ylabel("Future-tense markers (smoothed)", color="#4269d0")
    ax1.tick_params(axis="y", labelcolor="#4269d0")

    ax2 = ax1.twinx()
    ax2.plot(x, [r["verification_smooth"] for r in g], color="#3ca951", lw=1.3,
             label="verification")
    ax2.set_ylabel("Verification mentions (smoothed)", color="#3ca951")
    ax2.tick_params(axis="y", labelcolor="#3ca951")

    lines = ax1.get_lines()[len(flagged):] + ax2.get_lines()
    ax1.legend(lines, [l.get_label() for l in lines], loc="upper left")
    ax1.set_title(f"{company}: promises vs verification "
                  f"(dashed lines = {len(flagged)} rule-flagged sentences)")
    fig.tight_layout()
    fig.savefig(OUT / "sig_overlay.png", dpi=DPI)
    plt.close(fig)


def main():
    groups = load()
    for company, g in groups.items():
        print(f"{company:<12}{len(g):>6} 句, flags>0: {sum(1 for r in g if r['flags'] > 0)}")
    plot_vagueness(groups)
    plot_cumulative(groups)
    plot_overlay(groups)
    print("→ data/sig_vagueness.png, data/sig_cumulative.png, data/sig_overlay.png")


if __name__ == "__main__":
    main()
