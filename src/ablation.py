"""规则贡献度审计：每个终点是否值得留在树里。

借的是 wrapper feature selection 的问题形式（Abualigah & Khader 2017；Purushothaman 等
2020）：一个特征的价值 = 去掉它之后性能的变化。但**不借它们的搜索算法** —— 那些方法在
200 到 10,000 篇文档上搜上千维特征，我们只有 29 条 gold。在 29 条上搜子集等于把 gold 背
下来，正是 Abiodun 等（2021）§5.v 警告的过拟合形态。

所以这里只做单因素消融 + 配对 bootstrap 区间，报告每条规则的贡献和它的不确定度，
不做"选出最优子集"的宣称。

消融的定义：把某个 C 终点改判为 A（即"不再把这个机制当问题"），观察指标变化。
  Δ > 0  该规则有害（不判它反而更好）
  Δ = 0  该规则在 gold 上不起作用（可能是死规则，也可能只是 gold 没覆盖到）
  Δ < 0  该规则在挣它的位置
"""
import json
from pathlib import Path

import numpy as np

import src.tree as T
from src.evaluate import score

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
N_BOOT = 2000
METRIC = "C_balanced_accuracy"     # 优化目标：同时惩罚漏报与滥报


def load_gold():
    gold = {g["claim_id"]: g["gold_label"]
            for g in json.loads((DATA / "gold.json").read_text(encoding="utf-8"))
            if g["gold_label"] != "SKIP"}
    cands = {c["claim_id"]: c
             for c in json.loads((DATA / "candidates.json").read_text(encoding="utf-8"))}
    ids = [i for i in gold if i in cands]
    return ids, [gold[i] for i in ids], [cands[i]["text"] for i in ids]


def predict(texts, ids, ablate=None):
    """ablate: 终点名。该终点被改判为 A 后重新分类。"""
    saved = None
    if ablate:
        saved = T.TERMINALS[ablate]
        T.TERMINALS[ablate] = ("A", None, None)
    try:
        return [T.classify(t, i)["label"] for t, i in zip(texts, ids)]
    finally:
        if saved is not None:
            T.TERMINALS[ablate] = saved


def utilisation():
    """全量 390 条上每个终点的触发次数 —— 死规则在这里现形。"""
    claims = json.loads((DATA / "flagged.json").read_text(encoding="utf-8"))
    counts = {t: 0 for t in T.TERMINALS}
    for c in claims:
        counts[T.classify(c["text"], c["claim_id"])["terminal"]] += 1
    return counts, len(claims)


def paired_bootstrap(y, base, abl, metric=METRIC, n_boot=N_BOOT, seed=0):
    """配对 bootstrap：同一批重采样索引同时评两套预测，取差值的百分位区间。"""
    rng = np.random.default_rng(seed)
    y, base, abl = np.array(y), np.array(base), np.array(abl)
    deltas = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        if len(set(y[idx])) < 2:            # 退化重采样，跳过
            continue
        deltas.append(score(list(y[idx]), list(abl[idx]))[metric]
                      - score(list(y[idx]), list(base[idx]))[metric])
    d = np.array(deltas)
    return float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


def verdict(delta, lo, hi, fires_gold, fires_all):
    if fires_all == 0:
        return "never fires"
    if fires_gold == 0:
        return "untested by gold"
    if lo > 0:
        return "HARMFUL"
    if hi < 0:
        return "earns its place"
    return "not separable from zero"


def run(metric=METRIC):
    import warnings
    warnings.filterwarnings("ignore", message="y_pred contains classes not in y_true")

    ids, y, texts = load_gold()
    base = predict(texts, ids)
    base_score = score(y, base)
    counts, n_all = utilisation()

    terminals = [t for t, (lab, _, _) in T.TERMINALS.items() if lab == "C"]
    gold_terms = [T.classify(t, i)["terminal"] for t, i in zip(texts, ids)]

    rows = []
    for t in terminals:
        fires_gold = gold_terms.count(t)
        abl = predict(texts, ids, ablate=t) if fires_gold else base
        s = score(y, abl)
        delta = s[metric] - base_score[metric]
        lo, hi = paired_bootstrap(y, base, abl, metric) if fires_gold else (0.0, 0.0)
        rows.append({"terminal": t, "severity": T.TERMINALS[t][2],
                     "mechanism": T.TERMINALS[t][1],
                     "fires_all": counts[t], "fires_gold": fires_gold,
                     "delta": delta, "ci": [lo, hi],
                     "accuracy_after": s["accuracy"], "C_spec_after": s["C_specificity"],
                     "C_rec_after": s["C_recall"],
                     "verdict": verdict(delta, lo, hi, fires_gold, counts[t])})
    rows.sort(key=lambda r: (-r["delta"], -r["fires_all"]))

    out = {"metric": metric, "baseline": base_score[metric],
           "n_gold": len(ids), "n_all": n_all, "n_boot": N_BOOT,
           "utilisation": counts, "ablations": rows,
           "note": ("Single-factor ablation with a paired bootstrap interval. No subset "
                    "search is performed: with 29 labelled claims a wrapper search would "
                    "overfit the gold set (Abiodun et al. 2021, sec. 5.v).")}
    (DATA / "ablation.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                        encoding="utf-8")

    print(f"baseline {metric} = {base_score[metric]:.3f}   "
          f"(gold n={len(ids)}, corpus n={n_all}, {N_BOOT} bootstraps)\n")
    print(f"{'terminal':<30}{'sev':>4}{'fires':>7}{'gold':>6}{'Δ':>8}"
          f"{'95% CI':>18}  verdict")
    for r in rows:
        ci = f"[{r['ci'][0]:+.3f}, {r['ci'][1]:+.3f}]"
        print(f"{r['terminal']:<30}{r['severity']:>4}{r['fires_all']:>7}"
              f"{r['fires_gold']:>6}{r['delta']:>+8.3f}{ci:>18}  {r['verdict']}")

    dead = [t for t in terminals if counts[t] == 0]
    thin = [t for t in terminals if 0 < counts[t] <= 2]
    print(f"\n{len(dead)} C-terminals never fire on {n_all} claims: {', '.join(dead) or '—'}")
    print(f"{len(thin)} fire once or twice: {', '.join(thin) or '—'}")
    print("→ data/ablation.json")
    return out


if __name__ == "__main__":
    run()
