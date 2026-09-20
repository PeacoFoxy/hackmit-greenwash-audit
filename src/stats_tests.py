"""Are the methods actually different? Friedman + Nemenyi critical difference +
pairwise McNemar with Holm correction.

block = one gold claim, treatment = one of the five methods, observation = whether that
method got that claim right. On binary observations Friedman is equivalent to Cochran's Q.
Results are reported as p-values and a critical difference, never as a point ranking.
"""
import json
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy.stats import binomtest, friedmanchisquare, rankdata

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# Critical q values for the Nemenyi test (alpha=0.05), indexed by the number of methods k
Q_ALPHA_05 = {2: 1.960, 3: 2.344, 4: 2.569, 5: 2.728, 6: 2.850, 7: 2.949,
              8: 3.031, 9: 3.102, 10: 3.164}


def correctness_matrix(predictions, methods):
    """An n_claims x k_methods matrix of 0/1 correctness."""
    return np.array([[1 if p[m] == p["gold"] else 0 for m in methods] for p in predictions])


def friedman(M):
    stat, p = friedmanchisquare(*[M[:, i] for i in range(M.shape[1])])
    ranks = np.array([rankdata(-row, method="average") for row in M])  # 1 = best
    return {"chi2": float(stat), "p": float(p),
            "mean_ranks": ranks.mean(axis=0).tolist(),
            "n_blocks": int(M.shape[0]), "k_methods": int(M.shape[1]),
            "unanimous_blocks": int(((M.sum(1) == 0) | (M.sum(1) == M.shape[1])).sum())}


def critical_difference(k, n, alpha_q=None):
    """Nemenyi CD = q * sqrt(k(k+1) / (6n)). Two methods whose mean ranks differ by less
    than CD are indistinguishable."""
    q = alpha_q or Q_ALPHA_05.get(k, 3.164)
    return float(q * np.sqrt(k * (k + 1) / (6 * n)))


def mcnemar_exact(a_correct, b_correct):
    """Exact pairwise McNemar: only the claims where the two methods disagree (b01 / b10)."""
    b01 = int(np.sum((a_correct == 1) & (b_correct == 0)))
    b10 = int(np.sum((a_correct == 0) & (b_correct == 1)))
    n = b01 + b10
    p = 1.0 if n == 0 else binomtest(b01, n, 0.5).pvalue
    return {"b01": b01, "b10": b10, "discordant": n, "p": float(p)}


def holm(pairs):
    """Holm-Bonferroni correction; returns adjusted p-values in the original order."""
    order = sorted(range(len(pairs)), key=lambda i: pairs[i]["p"])
    m, out, running = len(pairs), [None] * len(pairs), 0.0
    for rank, idx in enumerate(order):
        adj = min(1.0, (m - rank) * pairs[idx]["p"])
        running = max(running, adj)          # keep the sequence monotone
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
           "per_dataset_ranks": {m: per_dataset_ranks(preds, methods, metric=m)
                                 for m in ("balanced_accuracy", "C_balanced_accuracy")},
           "fold_level": {m: fold_friedman(preds, methods, metric=m)
                          for m in ("accuracy", "balanced_accuracy", "C_f1")},
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


# ------------------------------------- fold-level distribution (box plot and Friedman)
def fold_scores(predictions, methods, metric="balanced_accuracy", k=5, repeats=10, seed=0):
    """Repeated stratified k-fold: score every method once per fold, giving a
    distribution that can be drawn as a box plot.

    No method is trained here -- the predictions are already fixed -- so the folds are
    purely a resampling device. The same claims are split over and over, so the folds are
    not independent and the p-value below is optimistic. Read the box overlap, not the p.
    """
    import warnings
    from src.evaluate import score
    warnings.filterwarnings("ignore", message="y_pred contains classes not in y_true")
    rng = np.random.default_rng(seed)
    y = np.array([p["gold"] for p in predictions])
    idx_by_label = {lab: np.where(y == lab)[0] for lab in set(y)}

    blocks = []
    for _ in range(repeats):
        folds = [[] for _ in range(k)]
        for lab, idx in idx_by_label.items():          # stratify: keep class ratios per fold
            order = rng.permutation(idx)
            for i, j in enumerate(order):
                folds[i % k].append(j)
        for f in folds:
            if len(f) < 2:
                continue
            row = []
            for m in methods:
                yt = [predictions[i]["gold"] for i in f]
                yp = [predictions[i][m] for i in f]
                row.append(score(yt, yp)[metric])
            blocks.append(row)
    return np.array(blocks)


def fold_friedman(predictions, methods, metric="balanced_accuracy", **kw):
    S = fold_scores(predictions, methods, metric=metric, **kw)
    stat, p = friedmanchisquare(*[S[:, i] for i in range(S.shape[1])])
    ranks = np.array([rankdata(-row, method="average") for row in S])
    return {"metric": metric, "scores": S.tolist(), "chi2": float(stat), "p": float(p),
            "n_folds": int(S.shape[0]), "mean_ranks": ranks.mean(0).tolist(),
            "median": np.median(S, axis=0).tolist(),
            "critical_difference": critical_difference(len(methods), S.shape[0])}


def print_folds(out):
    print(f"\nFold-level distribution (stratified 5-fold x 10 repeats = "
          f"{out['fold_level']['accuracy']['n_folds']} folds)")
    for metric, r in out["fold_level"].items():
        print(f"  {metric:<18} chi2={r['chi2']:7.2f}  p={r['p']:.2e}  "
              f"CD={r['critical_difference']:.3f}")
        print(f"    median: " + "  ".join(f"{m}={v:.3f}"
              for m, v in zip(out["methods"], r["median"])))




# ----------------------------------- per-dataset mean rank (Abualigah tables 4 and 5)
def per_dataset_ranks(predictions, methods, metric="balanced_accuracy"):
    """Treat each company as a dataset and lay out per-column ranks, sums, means and an
    overall rank, in the format Abualigah et al. use.

    They have 7-8 datasets; we have 3, about 10 claims each, so individual ranks are
    noisy. The table is here to show **whether the ranking is consistent across
    companies**, not to claim a winner -- consistency is stronger evidence than any
    single score.
    """
    import warnings

    from src.evaluate import score
    warnings.filterwarnings("ignore", message="y_pred contains classes not in y_true")

    groups = {}
    for p in predictions:
        groups.setdefault(p["claim_id"].split("_")[0], []).append(p)

    per_ds, scores = {}, {}
    for ds, rows in sorted(groups.items()):
        s = [score([r["gold"] for r in rows], [r[m] for r in rows])[metric] for m in methods]
        scores[ds] = s
        per_ds[ds] = rankdata([-v for v in s], method="average").tolist()  # 1 = best

    summation = [sum(per_ds[ds][i] for ds in per_ds) for i in range(len(methods))]
    mean_rank = [v / len(per_ds) for v in summation]
    final = rankdata(mean_rank, method="min").tolist()
    return {"metric": metric, "datasets": sorted(groups),
            "n_per_dataset": {ds: len(r) for ds, r in groups.items()},
            "scores": scores, "ranks": per_ds, "summation": summation,
            "mean_rank": mean_rank, "final_ranking": final,
            "unanimous": len({tuple(per_ds[ds]) for ds in per_ds}) == 1}


def print_ranks(r, methods):
    ds = r["datasets"]
    print(f"\nPer-dataset mean rank (metric = {r['metric']}, n per company = "
          + ", ".join(f"{d}:{r['n_per_dataset'][d]}" for d in ds) + ")")
    print(f"{'method':<20}" + "".join(f"{d[:8]:>10}" for d in ds)
          + f"{'sum':>7}{'mean':>7}{'rank':>6}")
    for i, m in enumerate(methods):
        print(f"{m:<20}"
              + "".join(f"{r['ranks'][d][i]:>10.1f}" for d in ds)
              + f"{r['summation'][i]:>7.1f}{r['mean_rank'][i]:>7.2f}"
              + f"{r['final_ranking'][i]:>6}")
    print("  Rank vectors across companies are "
          + ("identical" if r["unanimous"] else "not identical"))


if __name__ == "__main__":
    _out = run()
    for _m in _out["per_dataset_ranks"].values():
        print_ranks(_m, _out["methods"])
    print_folds(_out)
