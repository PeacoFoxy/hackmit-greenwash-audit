"""三张句级信号图：趋势、累计话术强度、Microsoft 的 future vs verification 对照。"""
import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data"
FIG_DIR = ROOT / "figures"
os.makedirs(FIG_DIR, exist_ok=True)
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
    fig.savefig(FIG_DIR / "sig_vagueness.png", dpi=DPI)
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
    fig.savefig(FIG_DIR / "sig_cumulative.png", dpi=DPI)
    plt.close(fig)


OVERLAY_WINDOW = 80


def smooth(values, window=OVERLAY_WINDOW):
    """滑动平均，边界只对实际存在的样本取平均。"""
    import numpy as np
    v = np.asarray(values, dtype=float)
    kernel = np.ones(window) / window
    norm = np.convolve(np.ones(len(v)), kernel, mode="same")
    return np.convolve(v, kernel, mode="same") / norm


def plot_overlay(groups, company="Microsoft"):
    g = groups[company]
    x = [r["rel_pos"] for r in g]
    future = smooth([r["future"] for r in g])
    verif = smooth([r["verification"] for r in g])
    flag_density = smooth([r["flags"] for r in g])

    fig, ax1 = plt.subplots(figsize=FIGSIZE)
    ax1.plot(x, future, color="#4269d0", lw=1.8, alpha=0.85, label="future-tense")
    ax1.fill_between(x, future, color="#4269d0", alpha=0.15)
    ax1.set_xlabel("Relative position in report")
    ax1.set_ylabel(f"Future-tense markers ({OVERLAY_WINDOW}-sentence avg)", color="#4269d0")
    ax1.tick_params(axis="y", labelcolor="#4269d0")
    ax1.set_xlim(0, 1)
    ax1.set_ylim(0, max(future) * 1.15)

    # 底部 5% 高度的 flag 密度色带
    lo, hi = ax1.get_ylim()
    band = lo + (hi - lo) * 0.05
    ax1.imshow(flag_density.reshape(1, -1), aspect="auto", cmap="OrRd",
               extent=(0, 1, lo, band), origin="lower", zorder=3)
    ax1.axhline(band, color="white", lw=0.8, zorder=4)

    ax2 = ax1.twinx()
    ax2.plot(x, verif, color="#3ca951", lw=1.8, alpha=0.85, label="third-party verification")
    ax2.set_ylabel(f"Verification mentions ({OVERLAY_WINDOW}-sentence avg)", color="#3ca951")
    ax2.tick_params(axis="y", labelcolor="#3ca951")
    ax2.set_ylim(0, max(verif) * 1.15)

    lines = ax1.get_lines()[:1] + ax2.get_lines()
    ax1.legend(lines, [l.get_label() for l in lines] + [], loc="upper left",
               title="bottom band = rule-flag density")
    ax1.set_title(f"{company}: future-tense promises vs third-party verification")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "sig_overlay.png", dpi=DPI)
    plt.close(fig)


def pvr(g):
    """与 anomaly.py 一致：(句数/verification总和) / (句数/future总和)。"""
    n = len(g)
    fsum = sum(r["future"] for r in g)
    vsum = sum(r["verification"] for r in g)
    if not fsum or not vsum:
        return float("inf")
    return (n / vsum) / (n / fsum)


def draw_overlay(ax1, g, company, legend=False, ymax_left=None, ymax_right=None):
    """单个公司的双轴 future/verification 曲线 + 底部 flag 密度色带。"""
    x = [r["rel_pos"] for r in g]
    future = smooth([r["future"] for r in g])
    verif = smooth([r["verification"] for r in g])
    flag_density = smooth([r["flags"] for r in g])

    ax1.plot(x, future, color="#4269d0", lw=1.8, alpha=0.85, label="future-tense")
    ax1.fill_between(x, future, color="#4269d0", alpha=0.15)
    ax1.set_ylabel(f"Future-tense ({OVERLAY_WINDOW}-sent avg)", color="#4269d0")
    ax1.tick_params(axis="y", labelcolor="#4269d0")
    ax1.set_xlim(0, 1)
    ax1.set_ylim(0, ymax_left if ymax_left else max(future) * 1.15)

    lo, hi = ax1.get_ylim()
    band = lo + (hi - lo) * 0.05
    ax1.imshow(flag_density.reshape(1, -1), aspect="auto", cmap="OrRd",
               extent=(0, 1, lo, band), origin="lower", zorder=3)
    ax1.axhline(band, color="white", lw=0.8, zorder=4)

    ax2 = ax1.twinx()
    ax2.plot(x, verif, color="#3ca951", lw=1.8, alpha=0.85, label="third-party verification")
    ax2.set_ylabel(f"Verification ({OVERLAY_WINDOW}-sent avg)", color="#3ca951")
    ax2.tick_params(axis="y", labelcolor="#3ca951")
    ax2.set_ylim(0, ymax_right if ymax_right else (max(verif) * 1.15 or 1))

    ax1.set_title(f"{company} — PVR {pvr(g):.2f}")
    if legend:
        lines = ax1.get_lines()[:1] + ax2.get_lines()
        ax1.legend(lines, [l.get_label() for l in lines], loc="upper left",
                   title="bottom band = rule-flag density")
    return ax2


def plot_overlay_all(groups):
    order = [c for c in ["Alphabet", "Microsoft", "Amazon"] if c in groups]
    order += [c for c in groups if c not in order]
    # 三格共用 y 轴范围，否则跨格比较曲线高度会得出相反结论
    gmax_f = max(smooth([r["future"] for r in groups[c]]).max() for c in order)
    gmax_v = max(smooth([r["verification"] for r in groups[c]]).max() for c in order)

    fig, axes = plt.subplots(len(order), 1, figsize=(10, 10), sharex=True)
    for i, (ax, company) in enumerate(zip(axes, order)):
        draw_overlay(ax, groups[company], company, legend=(i == 0),
                     ymax_left=gmax_f * 1.05, ymax_right=gmax_v * 1.05)
    axes[-1].set_xlabel("Relative position in report")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "sig_overlay_all.png", dpi=DPI)
    plt.close(fig)


def main():
    groups = load()
    for company, g in groups.items():
        print(f"{company:<12}{len(g):>6} 句, flags>0: {sum(1 for r in g if r['flags'] > 0)}")
    plot_vagueness(groups)
    plot_cumulative(groups)
    plot_overlay(groups)
    plot_overlay_all(groups)
    print("→ figures/sig_vagueness.png, figures/sig_cumulative.png, "
          "figures/sig_overlay.png, figures/sig_overlay_all.png")


if __name__ == "__main__":
    main()
