"""方法间差异的统计检验：Friedman + Nemenyi 临界差 + 成对 McNemar（Holm 校正）。

block = 单条 gold claim，treatment = 五种方法，观测值 = 该方法在该条上是否判对。
二元观测下 Friedman 等价于 Cochran's Q；结论以 p 值与临界差呈现，不做单点排名宣称。
"""
import json
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy.stats import binomtest, friedmanchisquare, rankdata

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# Nemenyi 检验的 q 临界值（alpha=0.05），索引为方法数 k
Q_ALPHA_05 = {2: 1.960, 3: 2.344, 4: 2.569, 5: 2.728, 6: 2.850, 7: 2.949,
              8: 3.031, 9: 3.102, 10: 3.164}


def correctness_matrix(predictions, methods):
    """n_claims × k_methods 的 0/1 矩阵。"""
    return np.array([[1 if p[m] == p["gold"] else 0 for m in methods] for p in predictions])


def friedman(M):
    stat, p = friedmanchisquare(*[M[:, i] for i in range(M.shape[1])])
    ranks = np.array([rankdata(-row, method="average") for row in M])  # 1 = 最好
    return {"chi2": float(stat), "p": float(p),
            "mean_ranks": ranks.mean(axis=0).tolist(),
            "n_blocks": int(M.shape[0]), "k_methods": int(M.shape[1]),
            "unanimous_blocks": int(((M.sum(1) == 0) | (M.sum(1) == M.shape[1])).sum())}


def critical_difference(k, n, alpha_q=None):
    """Nemenyi CD = q · sqrt(k(k+1) / (6n))。两方法平均秩之差小于 CD 即不可区分。"""
    q = alpha_q or Q_ALPHA_05.get(k, 3.164)
    return float(q * np.sqrt(k * (k + 1) / (6 * n)))


def mcnemar_exact(a_correct, b_correct):
    """成对精确 McNemar：只看两方法判定不一致的条目（b01 / b10）。"""
    b01 = int(np.sum((a_correct == 1) & (b_correct == 0)))
    b10 = int(np.sum((a_correct == 0) & (b_correct == 1)))
    n = b01 + b10
    p = 1.0 if n == 0 else binomtest(b01, n, 0.5).pvalue
    return {"b01": b01, "b10": b10, "discordant": n, "p": float(p)}


def holm(pairs):
    """Holm-Bonferroni 校正，返回按原顺序排列的校正后 p 值。"""
    order = sorted(range(len(pairs)), key=lambda i: pairs[i]["p"])
    m, out, running = len(pairs), [None] * len(pairs), 0.0
    for rank, idx in enumerate(order):
        adj = min(1.0, (m - rank) * pairs[idx]["p"])
        running = max(running, adj)          # 保持单调
        out[idx] = running
    return out


def run():
    metrics = json.loads((DATA / "metrics.json").read_text(encoding="utf-8"))
    preds = metrics["predictions"]
    methods = [k for k in preds[0] if k not in ("claim_id", "gold")]
    M = correctness_matrix(preds, methods)

    fr = friedman(M)
    cd = critical_difference(fr["k_methods"], fr["n_blocks"])

    pairs = []
    for i, j in combinations(range(len(methods)), 2):
        r = mcnemar_exact(M[:, i], M[:, j])
        r.update({"a": methods[i], "b": methods[j],
                  "rank_gap": abs(fr["mean_ranks"][i] - fr["mean_ranks"][j])})
        pairs.append(r)
    for r, p_adj in zip(pairs, holm(pairs)):
        r["p_holm"] = p_adj

    out = {"methods": methods, "correct_counts": M.sum(0).tolist(),
           "accuracy": (M.mean(0)).tolist(), "friedman": fr,
           "critical_difference": cd, "pairwise_mcnemar": pairs,
           "note": ("Blocks are the individual gold claims; the observation is whether a "
                    "method labelled that claim correctly. With binary observations the "
                    "Friedman test coincides with Cochran's Q.")}
    (DATA / "significance.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                            encoding="utf-8")

    print(f"Friedman chi2 = {fr['chi2']:.3f}, p = {fr['p']:.4f} "
          f"(n={fr['n_blocks']} blocks, k={fr['k_methods']} methods, "
          f"{fr['unanimous_blocks']} unanimous)")
    print(f"Nemenyi critical difference (alpha 0.05) = {cd:.3f} mean-rank units\n")
    print(f"{'method':<19}{'correct':>8}{'acc':>7}{'mean rank':>11}")
    for m, c, a, r in zip(methods, M.sum(0), M.mean(0), fr["mean_ranks"]):
        print(f"{m:<19}{c:>8}{a:>7.3f}{r:>11.3f}")
    print(f"\n{'pair':<42}{'b01':>5}{'b10':>5}{'p':>8}{'p_holm':>9}")
    for r in sorted(pairs, key=lambda x: x["p"]):
        print(f"{r['a'] + ' vs ' + r['b']:<42}{r['b01']:>5}{r['b10']:>5}"
              f"{r['p']:>8.3f}{r['p_holm']:>9.3f}")
    print("\n→ data/significance.json")
    return out


if __name__ == "__main__":
    run()
