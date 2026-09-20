"""Rule contribution audit: is each terminal earning its place in the tree?

The question form is borrowed from wrapper feature selection (Abualigah & Khader 2017;
Purushothaman et al. 2020): a feature is worth what performance loses without it. Their
search algorithms are deliberately NOT borrowed. Those run over thousands of features on
200-10,000 documents; we have 29 labelled claims. Searching subsets on 29 items memorises
the gold set, which is the exact failure Abiodun et al. (2021) sec. 5.v warns about.

So this module does single-factor ablation with a paired bootstrap interval only. It
reports each rule's contribution together with its uncertainty, and never claims to have
found an optimal subset.

Ablation means relabelling one C terminal as A -- that is, no longer treating the
mechanism as a problem -- and observing the change:
  delta > 0  the rule is harmful (not flagging is better)
  delta = 0  the rule does nothing on the gold set (dead, or simply never exercised)
  delta < 0  the rule earns its place
"""
import json
from pathlib import Path

import numpy as np

import src.tree as T
from src.evaluate import score

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
N_BOOT = 2000
METRIC = "C_balanced_accuracy"     # target: penalises missed flags and over-flagging alike


def load_gold(include_expand=False):
    """include_expand adds the 20 stratified claims.

    Ablation is the one analysis where pooling the two sets is defensible, because the
    question is "what does this rule contribute?" and not "how accurate is the system?".
    Ten class-C terminals had no gold coverage at all, so their contribution was not
    merely uncertain -- it was unmeasurable. The quota that makes the pooled set useless
    as an accuracy estimate is exactly what gives those rules any evidence.

    The cost is that a rule's delta is now measured on a sample enriched for that rule,
    so the magnitudes are not comparable with the random-only run. Run both.
    """
    gold = {g["claim_id"]: g["gold_label"]
            for g in json.loads((DATA / "gold.json").read_text(encoding="utf-8"))
            if g["gold_label"] != "SKIP"}
    cands = {c["claim_id"]: c
             for c in json.loads((DATA / "candidates.json").read_text(encoding="utf-8"))}
    ids = [i for i in gold if i in cands]
    texts = [cands[i]["text"] for i in ids]

    if include_expand:
        path = DATA / "gold_expand.json"
        if path.exists():
            flagged = {c["claim_id"]: c
                       for c in json.loads((DATA / "flagged.json").read_text(encoding="utf-8"))}
            for g in json.loads(path.read_text(encoding="utf-8")):
                if g["gold_label"] == "SKIP" or g["claim_id"] in gold:
                    continue
                gold[g["claim_id"]] = g["gold_label"]
                ids.append(g["claim_id"])
                texts.append(flagged[g["claim_id"]]["text"])

    return ids, [gold[i] for i in ids], texts


def predict(texts, ids, ablate=None):
    """ablate: terminal name. That terminal is relabelled A and everything reclassified."""
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
    """Firing count per terminal over all 390 claims. Dead rules show up here."""
    claims = json.loads((DATA / "flagged.json").read_text(encoding="utf-8"))
    counts = {t: 0 for t in T.TERMINALS}
    for c in claims:
        counts[T.classify(c["text"], c["claim_id"])["terminal"]] += 1
    return counts, len(claims)


def paired_bootstrap(y, base, abl, metric=METRIC, n_boot=N_BOOT, seed=0):
    """Paired bootstrap: one resample index scores both predictions; percentile CI of the difference."""
    rng = np.random.default_rng(seed)
    y, base, abl = np.array(y), np.array(base), np.array(abl)
    deltas = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        if len(set(y[idx])) < 2:            # degenerate resample, skip
            continue
        deltas.append(score(list(y[idx]), list(abl[idx]))[metric]
                      - score(list(y[idx]), list(base[idx]))[metric])
    d = np.array(deltas)
    # Direction shares matter as much as the interval here: with this few claims a delta
    # is discrete, so a percentile can sit exactly on 0 while no resample ever favours
    # keeping the rule. p_harmful / p_helpful say which of those two cases it is.
    return (float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5)),
            float((d > 0).mean()), float((d < 0).mean()))


def verdict(delta, lo, hi, fires_gold, fires_all, p_harm=0.0, p_help=0.0):
    if fires_all == 0:
        return "never fires"
    if fires_gold == 0:
        return "untested by gold"
    if lo > 0:
        return "HARMFUL"
    if hi < 0:
        return "earns its place"
    # A rule no resample ever favours keeping. The interval touches zero, so this is not
    # a significance claim -- but it is not the same as a two-sided tie either.
    if p_help == 0.0 and p_harm > 0:
        return "no resample favours keeping it"
    if p_harm == 0.0 and p_help > 0:
        return "no resample favours dropping it"
    return "not separable from zero"


def run(metric=METRIC, include_expand=False, out_name=None):
    import warnings
    warnings.filterwarnings("ignore", message="y_pred contains classes not in y_true")

    ids, y, texts = load_gold(include_expand)
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
        lo, hi, p_harm, p_help = (paired_bootstrap(y, base, abl, metric) if fires_gold
                                  else (0.0, 0.0, 0.0, 0.0))
        rows.append({"terminal": t, "severity": T.TERMINALS[t][2],
                     "mechanism": T.TERMINALS[t][1],
                     "fires_all": counts[t], "fires_gold": fires_gold,
                     "delta": delta, "ci": [lo, hi],
                     "p_harmful": p_harm, "p_helpful": p_help,
                     "accuracy_after": s["accuracy"], "C_spec_after": s["C_specificity"],
                     "C_rec_after": s["C_recall"],
                     "verdict": verdict(delta, lo, hi, fires_gold, counts[t],
                                        p_harm, p_help)})
    rows.sort(key=lambda r: (-r["delta"], -r["fires_all"]))

    out = {"metric": metric, "baseline": base_score[metric],
           "n_gold": len(ids), "n_all": n_all, "n_boot": N_BOOT,
           "utilisation": counts, "ablations": rows,
           "note": ("Single-factor ablation with a paired bootstrap interval. No subset "
                    "search is performed: with this few labelled claims a wrapper search "
                    "would overfit the gold set (Abiodun et al. 2021, sec. 5.v).") ,
           "gold_source": "random29 + stratified20" if include_expand else "random29",
           "caveat": ("Pooled run: the stratified claims were drawn to a per-terminal "
                      "quota, so a rule's delta is measured on a sample enriched for that "
                      "rule. Magnitudes are not comparable with the random-only run; the "
                      "point of this run is that ten terminals have any evidence at all."
                      ) if include_expand else None}
    (DATA / (out_name or "ablation.json")).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                        encoding="utf-8")

    print(f"baseline {metric} = {base_score[metric]:.3f}   "
          f"(gold n={len(ids)}, corpus n={n_all}, {N_BOOT} bootstraps)\n")
    print(f"{'terminal':<30}{'sev':>4}{'fires':>7}{'gold':>6}{'Δ':>8}"
          f"{'95% CI':>18}{'p(help)':>9}  verdict")
    for r in rows:
        ci = f"[{r['ci'][0]:+.3f}, {r['ci'][1]:+.3f}]"
        print(f"{r['terminal']:<30}{r['severity']:>4}{r['fires_all']:>7}"
              f"{r['fires_gold']:>6}{r['delta']:>+8.3f}{ci:>18}"
              f"{r['p_helpful']:>9.3f}  {r['verdict']}")

    dead = [t for t in terminals if counts[t] == 0]
    thin = [t for t in terminals if 0 < counts[t] <= 2]
    print(f"\n{len(dead)} C-terminals never fire on {n_all} claims: {', '.join(dead) or '—'}")
    print(f"{len(thin)} fire once or twice: {', '.join(thin) or '—'}")
    print(f"→ data/{out_name or 'ablation.json'}")
    return out


if __name__ == "__main__":
    import sys
    if "expand" in sys.argv[1:]:
        run(include_expand=True, out_name="ablation_expanded.json")
    else:
        run()
