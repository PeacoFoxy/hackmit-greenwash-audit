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
def plot_boxplot(sig):
    """折级分布箱线图：每个方法一个箱，点是单折得分；标题给 Friedman 统计量。"""
    methods = sig["methods"]
    panels = [("accuracy", "Accuracy"), ("balanced_accuracy", "Balanced accuracy"),
              ("C_f1", "F1 on technically-true claims")]
    order = np.argsort(sig["fold_level"]["balanced_accuracy"]["mean_ranks"])  # 好的在左
    labels = [SHOW.get(methods[i], methods[i]) for i in order]

    fig, axes = plt.subplots(1, len(panels), figsize=(14, 5.2), sharey=True)
    rng = np.random.default_rng(0)
    for ax, (key, title) in zip(axes, panels):
        r = sig["fold_level"][key]
        S = np.array(r["scores"])[:, order]
        bp = ax.boxplot(S, widths=0.6, showfliers=False, patch_artist=True,
                        medianprops=dict(color="#222", lw=1.6))
        for patch in bp["boxes"]:
            patch.set(facecolor="#dbe4f7", edgecolor="#4269d0", lw=1.1)
        for i in range(S.shape[1]):          # 单折得分，抖动后叠在箱上
            x = np.full(S.shape[0], i + 1) + rng.normal(0, 0.06, S.shape[0])
            ax.plot(x, S[:, i], "o", ms=3, alpha=0.35, color="#4269d0")
        ax.set_title(f"{title}\nFriedman χ² = {r['chi2']:.1f}, p = {r['p']:.1e}",
                     fontsize=10)
        ax.set_xticks(range(1, len(methods) + 1), labels, rotation=22, ha="right",
                      fontsize=8)
        ax.grid(axis="y", alpha=0.2)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    axes[0].set_ylabel("Score on a held-out fold")
    axes[0].set_ylim(-0.05, 1.05)
    fig.suptitle("Repeated stratified 5-fold resampling of the 29 gold claims "
                 f"({sig['fold_level']['accuracy']['n_folds']} folds), methods ordered by "
                 "mean rank\nFolds are redraws of the same 29 items, so the p values are "
                 "optimistic; read the overlap of the boxes, not the exponent.",
                 fontsize=10, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(FIGS / "friedman_boxplot.png", dpi=DPI)
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
    plot_boxplot(sig)
    plot_mcnemar(sig)
    print("→ figures/friedman_boxplot.png, figures/friedman_cd.png, "
          "figures/pairwise_mcnemar.png")


if __name__ == "__main__":
    main()
