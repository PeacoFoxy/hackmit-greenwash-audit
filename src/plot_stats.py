"""Friedman 检验的三张图：临界差图、指标点图、成对 McNemar 热图。

data/significance.json + data/metrics.json → figures/。matplotlib only, dpi 120。
"""
import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FIGS = ROOT / "figures"
os.makedirs(FIGS, exist_ok=True)
DPI = 120

SHOW = {"tree_only": "Rule tree (no LLM)", "baseline1": "LLM, short rubric",
        "baseline2": "LLM, full rubric", "pipeline": "LLM + precise flags",
        "pipeline_allflags": "LLM + all flags"}
ACCENT = "#4269d0"


def load():
    sig = json.loads((DATA / "significance.json").read_text(encoding="utf-8"))
    met = json.loads((DATA / "metrics.json").read_text(encoding="utf-8"))
    return sig, met


# ------------------------------------------------------------------ 图 1
def plot_cd(sig):
    """Friedman + Nemenyi 临界差图：秩越小越好（左侧），粗线内的方法不可区分。"""
    methods = sig["methods"]
    ranks = np.array(sig["friedman"]["mean_ranks"])
    cd = sig["critical_difference"]
    order = list(np.argsort(ranks))          # 最好的在前
    k = len(methods)

    lo, hi = ranks.min() - 0.18, ranks.max() + 0.18
    fig, ax = plt.subplots(figsize=(9.5, 3.4))
    ax.set_xlim(lo - 0.55, hi + 0.55)
    ax.set_ylim(-(k // 2 + 1) - 0.9, 1.9)

    # 秩轴
    ax.hlines(0, lo, hi, color="#333", lw=1.4)
    for t in np.arange(np.ceil(lo * 10) / 10, hi + 1e-9, 0.1):
        tall = abs(round(t, 2) * 100 % 20) < 1e-6
        ax.vlines(t, -0.09 if tall else -0.05, 0, color="#333", lw=1)
        if tall:                      # 刻度标签放轴下方，给上方的集团线让位
            ax.text(t, -0.13, f"{t:.1f}", ha="center", va="top", fontsize=8)
    ax.text(lo, -0.42, "better", ha="left", va="top", fontsize=8, color="#666")
    ax.text(hi, -0.42, "worse", ha="right", va="top", fontsize=8, color="#666")

    # 方法：前一半标在左，后一半标在右，避免引线交叉
    left, right = order[:(k + 1) // 2], order[(k + 1) // 2:]
    for i, idx in enumerate(left):
        y = -(i + 1)
        ax.plot([ranks[idx], ranks[idx], lo - 0.5], [0, y, y], color=ACCENT, lw=1.2)
        ax.text(lo - 0.55, y, f"{SHOW.get(methods[idx], methods[idx])} ({ranks[idx]:.2f})",
                va="center", ha="right", fontsize=9)
    for i, idx in enumerate(right):
        y = -(i + 1)
        ax.plot([ranks[idx], ranks[idx], hi + 0.5], [0, y, y], color=ACCENT, lw=1.2)
        ax.text(hi + 0.55, y, f"({ranks[idx]:.2f}) {SHOW.get(methods[idx], methods[idx])}",
                va="center", ha="left", fontsize=9)

    # 不可区分的集团：秩差 <= CD 的方法用一条粗线连起来
    groups, used = [], set()
    for a in order:
        if a in used:
            continue
        clique = [b for b in order if abs(ranks[b] - ranks[a]) <= cd]
        if len(clique) > 1:
            groups.append(clique)
            used.update(clique)
    for g_i, g in enumerate(groups):
        y = 0.22 + 0.26 * g_i
        ax.plot([min(ranks[g]) - 0.02, max(ranks[g]) + 0.02], [y, y],
                color="#333", lw=5, solid_capstyle="butt")

    # CD 标尺
    ax.plot([lo, lo + cd], [1.35, 1.35], color="#ff725c", lw=3, solid_capstyle="butt")
    ax.vlines([lo, lo + cd], 1.28, 1.42, color="#ff725c", lw=1.5)
    ax.text(lo + cd / 2, 1.46, f"critical difference {cd:.2f}", ha="center", va="bottom",
            fontsize=9, color="#ff725c")

    ax.axis("off")
    fr = sig["friedman"]
    ax.set_title("No method separates from another\n"
                 f"Friedman χ² = {fr['chi2']:.2f}, p = {fr['p']:.2f} · "
                 f"{fr['n_blocks']} claims × {fr['k_methods']} methods · "
                 f"{fr['unanimous_blocks']} claims where all five agree\n"
                 "The whole field fits inside one critical difference.",
                 fontsize=10, loc="left")
    fig.tight_layout()
    fig.savefig(FIGS / "friedman_cd.png", dpi=DPI)
    plt.close(fig)


# ------------------------------------------------------------------ 图 2
def bootstrap_ci(correct, n_boot=2000, seed=0):
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(correct), size=(n_boot, len(correct)))
    means = correct[idx].mean(axis=1)
    return np.percentile(means, [2.5, 97.5])


def plot_metric_dots(sig, met):
    """每个方法四个指标各一个点 + accuracy 的 bootstrap 区间。"""
    methods = sig["methods"]
    preds = met["predictions"]
    corr = {m: np.array([1 if p[m] == p["gold"] else 0 for p in preds]) for m in methods}
    keys = [("accuracy", "Accuracy"), ("balanced_accuracy", "Balanced accuracy"),
            ("macro_f1", "Macro F1"), ("C_f1", "F1 on technically-true claims")]
    marks = ["o", "s", "^", "D"]

    fig, ax = plt.subplots(figsize=(9, 4.8))
    x = np.arange(len(methods))
    for (k, label), mk in zip(keys, marks):
        ax.plot(x, [met["metrics"][m][k] for m in methods], mk, label=label,
                markersize=7, alpha=0.85, linestyle="none")

    for i, m in enumerate(methods):          # accuracy 的 95% bootstrap 区间
        lo, hi = bootstrap_ci(corr[m])
        ax.vlines(i, lo, hi, color=ACCENT, alpha=0.35, lw=6, zorder=0)

    ax.set_xticks(x, [SHOW.get(m, m) for m in methods], rotation=18, ha="right")
    ax.set_ylim(0, 1)
    ax.set_ylabel("Score")
    ax.grid(axis="y", alpha=0.2)
    ax.legend(loc="lower right", fontsize=8, frameon=False)
    ax.set_title("Four metrics per method; the band is a 95% bootstrap interval on accuracy\n"
                 "The intervals overlap everywhere — consistent with the Friedman result.",
                 fontsize=10, loc="left")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIGS / "method_metrics_dots.png", dpi=DPI)
    plt.close(fig)


# ------------------------------------------------------------------ 图 3
def plot_mcnemar(sig):
    """成对 McNemar 热图：下三角原始 p，上三角 Holm 校正后 p。"""
    methods = sig["methods"]
    n = len(methods)
    grid = np.full((n, n), np.nan)
    ann = [["" for _ in range(n)] for _ in range(n)]
    for r in sig["pairwise_mcnemar"]:
        i, j = methods.index(r["a"]), methods.index(r["b"])
        grid[max(i, j), min(i, j)] = r["p"]          # 下三角：原始 p
        grid[min(i, j), max(i, j)] = r["p_holm"]     # 上三角：Holm
        ann[max(i, j)][min(i, j)] = f"{r['p']:.2f}\n{r['b01']}v{r['b10']}"
        ann[min(i, j)][max(i, j)] = f"{r['p_holm']:.2f}"

    fig, ax = plt.subplots(figsize=(7.4, 6.2))
    # 中性单色：红绿会让 p=0.12 看起来像“显著”。显著的格子另加星号标出。
    im = ax.imshow(grid, cmap="Blues_r", vmin=0, vmax=1)
    ax.set_xticks(range(n), [SHOW.get(m, m) for m in methods], rotation=25, ha="right",
                  fontsize=8)
    ax.set_yticks(range(n), [SHOW.get(m, m) for m in methods], fontsize=8)
    for i in range(n):
        for j in range(n):
            if i == j:
                ax.text(j, i, "—", ha="center", va="center", color="#999")
            else:
                star = "*" if (grid[i, j] < 0.05) else ""
                ax.text(j, i, ann[i][j] + star, ha="center", va="center", fontsize=7.5,
                        color="white" if grid[i, j] < 0.35 else "#222")
    fig.colorbar(im, ax=ax, shrink=0.75, label="p value")
    n_sig = int(np.nansum(grid < 0.05))
    ax.set_title("Pairwise McNemar: no pair differs\n"
                 "lower triangle raw p with discordant counts (b01 v b10), "
                 "upper triangle Holm-adjusted\n"
                 f"{n_sig} of {n * (n - 1)} cells reach p < 0.05 (marked *)",
                 fontsize=10, loc="left")
    fig.tight_layout()
    fig.savefig(FIGS / "pairwise_mcnemar.png", dpi=DPI)
    plt.close(fig)


def main():
    sig, met = load()
    plot_cd(sig)
    plot_metric_dots(sig, met)
    plot_mcnemar(sig)
    print("→ figures/friedman_cd.png, figures/method_metrics_dots.png, "
          "figures/pairwise_mcnemar.png")


if __name__ == "__main__":
    main()
