"""Does "has this rule ever been checked?" predict whether the rule is right?

`abstain.py` tested five confidence proxies -- path composition, node reliability,
severity, cross-method agreement -- and none of them beat random abstention. This module
tests a sixth, which the stratified annotation made available for the first time.

The tier is not a property of the claim. It is a property of the *rule*: a terminal is
`evidence_backed` if at least one of the 29 random gold claims exercised it, and
`unvalidated` otherwise. That assignment was fixed before the 20 stratified claims were
labelled -- `expand_gold.py` used it to choose what to sample -- so the tier is a genuine
prior prediction here, not a label fitted after the fact.

What makes this testable at all is that the strata were drawn blind: the annotator saw
claim text only, never the terminal and never the tree's answer.

Two limits that the numbers below cannot escape:

1. The pooled set of 49 mixes a random sample (29) with a quota sample (20) enriched for
   unvalidated rules. Accuracy on the pool estimates nothing about the field. Random
   abstention is drawn from the same pooled set, so the comparison still answers "does
   the tier sort errors" -- but the coverage axis is not a field coverage.
2. Per-terminal counts are 1-2. The tier is one bit over all ten rules, which is why it
   is reported as one bit and not as ten per-rule decisions.
"""
import json
import warnings
from pathlib import Path

import numpy as np

from src.tree import classify

warnings.filterwarnings("ignore", message="y_pred contains classes not in y_true")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
N_RANDOM = 5000
SEED = 0


def pooled():
    """The 29 random gold claims plus the 20 stratified ones, each tagged with its source."""
    cands = {c["claim_id"]: c
             for c in json.loads((DATA / "candidates.json").read_text(encoding="utf-8"))}
    flagged = {c["claim_id"]: c
               for c in json.loads((DATA / "flagged.json").read_text(encoding="utf-8"))}

    rows = []
    for g in json.loads((DATA / "gold.json").read_text(encoding="utf-8")):
        if g["gold_label"] == "SKIP" or g["claim_id"] not in cands:
            continue
        rows.append({"claim_id": g["claim_id"], "gold": g["gold_label"],
                     "text": cands[g["claim_id"]]["text"], "source": "random29"})
    for g in json.loads((DATA / "gold_expand.json").read_text(encoding="utf-8")):
        if g["gold_label"] == "SKIP":
            continue
        rows.append({"claim_id": g["claim_id"], "gold": g["gold_label"],
                     "text": flagged[g["claim_id"]]["text"], "source": "stratified20"})

    # Terminals the original 29 exercised. Fixed before the 20 were labelled.
    backed = {classify(r["text"], r["claim_id"])["terminal"]
              for r in rows if r["source"] == "random29"}

    for r in rows:
        c = classify(r["text"], r["claim_id"])
        r["terminal"], r["pred"] = c["terminal"], c["label"]
        r["correct"] = int(c["label"] == r["gold"])
        r["tier"] = "evidence_backed" if c["terminal"] in backed else "unvalidated"
    return rows, sorted(backed)


def random_control(rows, n_answered, n=N_RANDOM, seed=SEED):
    """Accuracy when the same number of claims is dropped at random from the same pool."""
    rng = np.random.default_rng(seed)
    corr = np.array([r["correct"] for r in rows])
    accs = [corr[rng.choice(len(corr), n_answered, replace=False)].mean() for _ in range(n)]
    return float(np.mean(accs)), float(np.percentile(accs, 95))


def stratified_control(rows, kept, n=N_RANDOM, seed=SEED):
    """The control the naive one gets wrong.

    Sampling at random from the pooled set lets the control draw a different mix of
    random29 and stratified20 than the kept set has. Because the two sources have very
    different accuracies *by design*, any subset weighted towards random29 wins, whether
    or not the tier means anything. This control resamples within each source, holding
    the source composition of the kept set fixed, so only the tier can move the number.
    """
    rng = np.random.default_rng(seed)
    by_src = {}
    for r in rows:
        by_src.setdefault(r["source"], []).append(r["correct"])
    quota = {}
    for r in kept:
        quota[r["source"]] = quota.get(r["source"], 0) + 1

    accs = []
    for _ in range(n):
        got = []
        for src, k in quota.items():
            pool = np.array(by_src[src])
            got += list(pool[rng.choice(len(pool), k, replace=False)])
        accs.append(float(np.mean(got)))
    return float(np.mean(accs)), float(np.percentile(accs, 95)), quota


def confound(rows):
    """tier x source cross-tab, and how much freedom the stratified control actually has."""
    tab = {}
    for r in rows:
        tab.setdefault(r["tier"], {}).setdefault(r["source"], 0)
        tab[r["tier"]][r["source"]] += 1
    totals = {}
    for r in rows:
        totals[r["source"]] = totals.get(r["source"], 0) + 1
    # Share of each source that the kept set consumes. At 1.0 there is nothing left to
    # resample and the control is forced to reproduce the observed value.
    kept = tab.get("evidence_backed", {})
    consumed = {s: kept.get(s, 0) / totals[s] for s in totals}
    return tab, totals, consumed


def run():
    rows, backed = pooled()
    kept = [r for r in rows if r["tier"] == "evidence_backed"]
    drop = [r for r in rows if r["tier"] == "unvalidated"]

    acc_all = sum(r["correct"] for r in rows) / len(rows)
    acc_kept = sum(r["correct"] for r in kept) / len(kept)
    acc_drop = sum(r["correct"] for r in drop) / len(drop)
    rm, r95 = random_control(rows, len(kept))
    sm, s95, quota = stratified_control(rows, kept)
    tab, totals, consumed = confound(rows)
    worst = max(consumed.values())
    testable = worst < 0.9
    beats_naive = acc_kept > r95
    beats = bool(testable and acc_kept > s95)

    by_source = {}
    for s in ("random29", "stratified20"):
        sub = [r for r in rows if r["source"] == s]
        by_source[s] = {
            "n": len(sub),
            "accuracy": sum(r["correct"] for r in sub) / len(sub),
            "n_unvalidated": sum(r["tier"] == "unvalidated" for r in sub)}

    out = {"n_pooled": len(rows), "n_evidence_backed": len(kept), "n_unvalidated": len(drop),
           "accuracy_pooled": acc_all, "accuracy_evidence_backed": acc_kept,
           "accuracy_unvalidated": acc_drop,
           "coverage": len(kept) / len(rows),
           "naive_random_mean": rm, "naive_random_p95": r95,
           "beats_naive_control": bool(beats_naive),
           "stratified_control_mean": sm, "stratified_control_p95": s95,
           "kept_source_quota": quota, "tier_by_source": tab,
           "source_consumed_by_kept": consumed, "testable": bool(testable),
           "beats_random": beats,
           "backed_terminals": backed, "by_source": by_source,
           "note": ("Tier is a property of the rule, assigned from gold coverage before "
                    "the stratified claims were labelled, so it is a genuine prior "
                    "prediction. It is nonetheless untestable on this data: the tier is "
                    "almost perfectly collinear with which sample a claim came from, and "
                    "the two samples differ in accuracy by construction. The naive "
                    "pooled-random control does not separate the two and reports a false "
                    "win; the source-stratified control has almost no freedom left to "
                    "resample. Testing this needs unvalidated-rule claims inside a random "
                    "sample, which means more random annotation, not more strata.")}
    (DATA / "evidence_tier.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                             encoding="utf-8")

    print(f"Pooled set: {len(rows)} claims "
          f"({by_source['random29']['n']} random + {by_source['stratified20']['n']} stratified)")
    print(f"{len(backed)} terminals were exercised by the original gold; the rest were not.\n")
    print(f"{'tier':<20}{'n':>4}{'accuracy':>10}")
    print(f"{'evidence_backed':<20}{len(kept):>4}{acc_kept:>10.3f}")
    print(f"{'unvalidated':<20}{len(drop):>4}{acc_drop:>10.3f}")
    print(f"{'pooled':<20}{len(rows):>4}{acc_all:>10.3f}")
    print(f"\nAnswer only on evidence_backed rules: coverage {len(kept) / len(rows):.0%}, "
          f"accuracy {acc_kept:.3f}")
    print(f"  naive control (resample the pool):       mean {rm:.3f}, p95 {r95:.3f}"
          f"  -> {'beats it' if beats_naive else 'does not beat it'}")
    print(f"  source-stratified control:               mean {sm:.3f}, p95 {s95:.3f}"
          f"  -> {'beats it' if acc_kept > s95 else 'does not beat it'}")

    print("\nWhy the naive control is wrong here -- tier x source:")
    print(f"  {'tier':<18}" + "".join(f"{s:>16}" for s in totals))
    for t in ("evidence_backed", "unvalidated"):
        print(f"  {t:<18}" + "".join(f"{tab.get(t, {}).get(s, 0):>16}" for s in totals))
    print("  " + ", ".join(f"the kept set takes {v:.0%} of {s}" for s, v in consumed.items()))
    if not testable:
        print("\n  The tier is collinear with the sample a claim came from, and the two "
              "samples\n  differ in accuracy by design. The stratified control has almost "
              "nothing left to\n  resample, so this data cannot test the tier either way. "
              "Reported as untestable,\n  not as a win.")

    print("\nPer source (these two are never averaged into one headline):")
    for s, v in by_source.items():
        print(f"  {s:<14} n={v['n']:<3} accuracy {v['accuracy']:.3f}   "
              f"{v['n_unvalidated']} on unvalidated rules")
    print("\n-> data/evidence_tier.json")
    return out


if __name__ == "__main__":
    run()
