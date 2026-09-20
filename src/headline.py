"""Four corpus-level percentages, one formula each.

The four indicators in `indicators.py` describe one report and are what the interface
shows per company. These four describe what the system did across everything, which is
the question a reader asks first. Each is a single ratio, each is a percentage, and each
is computed from committed data, so `./run_all.sh verify` reproduces all of them with no
network access.

One of them is deliberately reported as a range rather than a point:

The incomplete-disclosure rate counts claims the tree labels C. The stratified blind test
(`merge_expand.py`) measured ten terminals at 0.250 class-C precision against 0.667 for
the rest, and those ten produce a quarter of the C labels on the screened set. Quoting
the raw count would carry that error straight into the headline. So the rate is reported
twice: the raw count as an upper bound, and a discounted figure that keeps each C at the
measured precision of the rule that produced it. The truth is somewhere in the interval,
and the interval is narrow enough to still be a finding.
"""
import json
from collections import Counter
from pathlib import Path

from src.tree import classify

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# Measured on blind annotations. See data/expand_eval.json and data/metrics.json.
PRECISION_VALIDATED = 0.667
PRECISION_UNVALIDATED = 0.250


def load(name):
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def validated_terminals():
    """Terminals at least one of the 29 random gold claims exercised."""
    flagged = load("flagged")
    gold_ids = {g["claim_id"] for g in load("gold")}
    return {classify(c["text"], c["claim_id"])["terminal"]
            for c in flagged if c["claim_id"] in gold_ids}


# ------------------------------------------------------------------- the four
def screening_reduction(sentences, candidates, passages):
    """How much of the document the system asks a human to look at.

        attention = claims needing review / sentences

    This describes where the system points, not a guarantee about the rest. Nothing here
    establishes that the unsurfaced text is clean; the four negative probes in the blind
    set are the only evidence in that direction and four is not many.
    """
    n_s = len(sentences)
    return {"sentences": n_s, "claims_surfaced": len(candidates),
            "attention_pct": 100 * len(candidates) / n_s,
            "reduction_pct": 100 * (1 - len(candidates) / n_s),
            "passages": len(passages),
            "passage_sentences": sum(p["n_sentences"] for p in passages),
            "passage_pct": 100 * sum(p["n_sentences"] for p in passages) / n_s}


def incomplete_rate(candidates, backed):
    """Share of quantified claims that are technically true but missing their basis.

        raw rate = C / (A + C)

    B claims are excluded from the denominator on purpose: a claim with no quantity in it
    cannot be incomplete about its accounting basis, so including them would dilute the
    rate with sentences the question does not apply to.

    This is the one number here that depends on the classifier being right, and the
    classifier is measurably not always right. So the raw count is an upper bound only,
    and a corrected estimate is computed from the measured precisions:

        true C  ~=  C_validated x 0.667  +  C_unvalidated x 0.250

    The denominator needs a decision too. A false C is usually really an A, which stays
    in A + C; in the blind set 9 of 12 went that way and 3 went to B, which leaves. Both
    treatments are computed, and the pair is reported as an interval rather than a point,
    because with 49 labels an interval is the honest shape of this answer.
    """
    res = [classify(c["text"], c["claim_id"]) for c in candidates]
    lab = Counter(r["label"] for r in res)
    denom = lab["A"] + lab["C"]
    unval = sum(1 for r in res if r["label"] == "C" and r["terminal"] not in backed)
    val = lab["C"] - unval

    true_c = val * PRECISION_VALIDATED + unval * PRECISION_UNVALIDATED
    false_c = lab["C"] - true_c
    # Blind set: of 12 false C labels, 9 were really A (stay) and 3 really B (leave).
    b_share = 3 / 12
    lo = 100 * true_c / denom                              # every false C was really A
    hi = 100 * true_c / (denom - false_c * b_share)        # some were really B

    return {"A": lab["A"], "B": lab["B"], "C": lab["C"], "denominator": denom,
            "raw_pct": 100 * lab["C"] / denom,
            "from_validated_rules": val, "from_unvalidated_rules": unval,
            "corrected_lo_pct": lo, "corrected_hi_pct": hi,
            "note": (f"Raw count is an upper bound. Correcting each C by the measured "
                     f"precision of the rule behind it ({val} at {PRECISION_VALIDATED}, "
                     f"{unval} at {PRECISION_UNVALIDATED}) gives {lo:.0f}-{hi:.0f}%.")}


def unverifiable_commitments(audit):
    """Quantified commitments that cannot be progress-checked from the report making them.

        rate = targets with fewer than 2 observations / targets extracted

    This one needs no accuracy claim at all. Whether a second observation of the same
    metric exists in the document is a matter of fact, not of judgment.
    """
    out = Counter(a["outcome"] for a in audit)
    return {"targets": len(audit), "trackable": out["kept"],
            "unverifiable": out["discarded"],
            "pct": 100 * out["discarded"] / len(audit)}


def track_agreement(consensus):
    """How often the rule tree and the language model reach the same label.

        agreement = CONFIRMED / (CONFIRMED + CONTESTED)

    Restricted to claims both tracks actually labelled. Track D only ran on the gold
    subset, so the denominator is 28, not 89 -- stating the rate over all 89 would count
    60 claims the model never saw as agreement.
    """
    st = Counter(r["consensus"]["state"] for r in consensus["claims"])
    both = st["CONFIRMED"] + st["CONTESTED"]
    return {"both_labelled": both, "agree": st["CONFIRMED"], "disagree": st["CONTESTED"],
            "pct": 100 * st["CONFIRMED"] / both, "states": dict(st)}


def run():
    sentences, candidates = load("signals"), load("candidates")
    passages, audit = load("anomaly_regions"), load("trajectory_audit")
    consensus, backed = load("consensus"), validated_terminals()

    scr = screening_reduction(sentences, candidates, passages)
    inc = incomplete_rate(candidates, backed)
    unv = unverifiable_commitments(audit)
    agr = track_agreement(consensus)

    out = {"screening": scr, "incomplete": inc, "unverifiable": unv, "agreement": agr}
    (DATA / "headline.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                        encoding="utf-8")

    print("Four numbers, one formula each\n")
    print(f"1.  {scr['reduction_pct']:.1f}%  of the document needs no analyst attention")
    print(f"      1 - {scr['claims_surfaced']} claims surfaced / {scr['sentences']} sentences")
    print(f"      {scr['passages']} anomalous passages cover {scr['passage_sentences']} "
          f"sentences ({scr['passage_pct']:.1f}%)")

    print(f"\n2.  {inc['corrected_lo_pct']:.0f}-{inc['corrected_hi_pct']:.0f}%  of quantified "
          f"claims are technically true but missing their basis")
    print(f"      C / (A + C) = {inc['C']} / {inc['denominator']} = {inc['raw_pct']:.1f}%, "
          f"which is an upper bound, not the answer")
    print(f"      correcting each C by the measured precision of its rule "
          f"({inc['from_validated_rules']} at {PRECISION_VALIDATED}, "
          f"{inc['from_unvalidated_rules']} at {PRECISION_UNVALIDATED})")
    print(f"      gives {inc['corrected_lo_pct']:.0f}-{inc['corrected_hi_pct']:.0f}%. This is "
          f"the only one of the four that depends on the classifier being right.")

    print(f"\n3.  {unv['pct']:.1f}%  of quantified commitments cannot be progress-checked")
    print(f"      {unv['unverifiable']} / {unv['targets']} targets have fewer than two "
          f"observations of the same metric")

    print(f"\n4.  {agr['pct']:.1f}%  agreement between the rule tree and the language model")
    print(f"      {agr['agree']} / {agr['both_labelled']} claims both tracks labelled "
          f"({agr['disagree']} contested)")

    print("\n-> data/headline.json")
    return out


if __name__ == "__main__":
    run()
