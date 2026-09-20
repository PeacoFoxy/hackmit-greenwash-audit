"""Merge the stratified blind annotation and report it *separately* from the random gold.

`expand_gold.py` drew 20 claims to a per-terminal quota: two each from the class-C
terminals the original 29-claim gold set never exercised, plus four probes the tree calls
A or B. The sheet was filled blind -- the annotator saw claim text only, never the
terminal or the tree's label.

The one rule this module exists to enforce: **the two sets are never pooled into a single
headline number.**

  * The 29 are a random draw from the candidate pool, so accuracy on them estimates field
    accuracy.
  * The 20 are a quota sample of the rules that were previously unmeasurable, deliberately
    enriched for rules with no evidence behind them. Accuracy on them estimates nothing
    about the field; it measures those specific rules.

Averaging the two would import the quota into the estimate. They are reported side by
side instead, and only the ablation -- which asks "what does this rule contribute?", not
"how accurate is the system?" -- draws on the union.

Outputs
  data/gold_expand.json   the 20 labels, same schema as gold.json, marked stratified
  data/expand_eval.json   per-terminal verdicts and the two-set comparison
"""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
VALID = {"A", "B", "C", "D", "SKIP"}


def load_key():
    """The answer key: which terminal each sampled claim came from, and what the tree said.

    It is gitignored on purpose -- it holds the tree's predictions, and an annotator who
    reads it is no longer blind. That makes a fresh clone unable to score the sheet, so
    when the file is absent it is derived instead: expand_gold.sample() runs off a fixed
    SEED over committed data, and reproduces the same draw in the same order.

    Verified on 2026-09-20: the regenerated key matches the committed sheet claim for
    claim, including order. If the tree or the corpus changes the draw will move, and
    the mismatch check below turns that into an error rather than silent nonsense.
    """
    path = DATA / "expand_key.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")), "file"
    from src.expand_gold import sample
    picked, _, _ = sample()
    return [{"claim_id": r["claim_id"], "terminal": r["terminal"],
             "tree_label": r["label"], "pool": r["pool"]} for r in picked], "regenerated"


def load():
    rows = list(csv.DictReader((DATA / "blind_expand.csv").open(encoding="utf-8")))
    key_rows, origin = load_key()
    key = {k["claim_id"]: k for k in key_rows}

    unknown = [r["claim_id"] for r in rows if r["claim_id"] not in key]
    if unknown:
        raise SystemExit(
            f"The answer key ({origin}) does not cover {len(unknown)} claims in "
            f"blind_expand.csv, starting with {unknown[0]}.\n"
            f"A regenerated key only matches while the tree and the corpus are "
            f"unchanged. Re-draw the sample and re-annotate, or restore the key file.")
    out, missing = [], 0
    for r in rows:
        lab = (r.get("my_label") or "").strip().upper()
        if not lab:
            missing += 1
            continue
        if lab not in VALID:
            raise ValueError(f"{r['claim_id']}: unrecognised label {lab!r}")
        k = key[r["claim_id"]]
        out.append({"claim_id": r["claim_id"], "company": r["company"], "text": r["text"],
                    "gold_label": lab, "note": (r.get("note") or "").strip(),
                    "terminal": k["terminal"], "tree_label": k["tree_label"],
                    "pool": k["pool"],
                    "stratum": "negative_probe" if k["tree_label"] in ("A", "B")
                               else "untested_terminal"})
    return out, missing


def per_terminal(rows):
    by = defaultdict(list)
    for r in rows:
        by[r["terminal"]].append(r)
    out = []
    for term, rs in sorted(by.items()):
        tree = rs[0]["tree_label"]
        agree = sum(r["gold_label"] == tree for r in rs)
        labs = Counter(r["gold_label"] for r in rs)
        if tree == "C":
            verdict = ("confirmed" if agree == len(rs) else
                       "over-flags" if agree == 0 else "mixed")
        else:
            verdict = "no missed flag" if agree == len(rs) else "missed a flag"
        out.append({"terminal": term, "tree_label": tree, "n": len(rs),
                    "agree": agree, "human_labels": dict(labs),
                    "pool": rs[0]["pool"], "verdict": verdict})
    out.sort(key=lambda r: (r["tree_label"] != "C", r["agree"] / r["n"], r["terminal"]))
    return out


def run():
    rows, missing = load()
    if not rows:
        print("blind_expand.csv has no filled labels yet.")
        return None

    (DATA / "gold_expand.json").write_text(json.dumps(
        [{"claim_id": r["claim_id"], "gold_label": r["gold_label"],
          "source": "stratified_expand_2026-09-20", "terminal": r["terminal"],
          "stratum": r["stratum"], "pool": r["pool"], "note": r["note"]} for r in rows],
        ensure_ascii=False, indent=1), encoding="utf-8")

    terms = per_terminal(rows)
    agree = sum(r["gold_label"] == r["tree_label"] for r in rows)

    # C precision within this sample only. Not a field estimate -- the sample was drawn
    # to a quota over exactly the rules that had never been checked.
    flagged_c = [r for r in rows if r["tree_label"] == "C"]
    c_conf = sum(r["gold_label"] == "C" for r in flagged_c)
    probes = [r for r in rows if r["stratum"] == "negative_probe"]
    missed = [r for r in probes if r["gold_label"] in ("C", "D")]

    orig = [g for g in json.loads((DATA / "gold.json").read_text(encoding="utf-8"))
            if g["gold_label"] != "SKIP"]

    out = {"n_labelled": len(rows), "n_unlabelled": missing,
           "agreement": agree / len(rows),
           "c_precision_in_sample": c_conf / len(flagged_c) if flagged_c else None,
           "n_flagged_c": len(flagged_c), "n_confirmed_c": c_conf,
           "n_probes": len(probes), "n_missed_flags": len(missed),
           "missed_flag_ids": [r["claim_id"] for r in missed],
           "per_terminal": terms, "n_original_gold": len(orig),
           "note": ("Quota sample over previously unmeasured terminals. Agreement here is "
                    "not comparable with accuracy on the 29 random gold claims and the two "
                    "are never averaged.")}
    (DATA / "expand_eval.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                           encoding="utf-8")

    print(f"Stratified blind set: {len(rows)} labelled"
          + (f", {missing} still empty" if missing else ""))
    print(f"tree agrees with the annotator on {agree}/{len(rows)} = {agree / len(rows):.0%}\n")
    print(f"{'terminal':<28}{'tree':>5}{'n':>3}{'agree':>7}  human labels     verdict")
    for t in terms:
        labs = " ".join(f"{k}:{v}" for k, v in sorted(t["human_labels"].items()))
        print(f"{t['terminal']:<28}{t['tree_label']:>5}{t['n']:>3}{t['agree']:>7}  "
              f"{labs:<16} {t['verdict']}")

    print(f"\nOf the {len(flagged_c)} claims the tree called C, the annotator confirmed "
          f"{c_conf} ({c_conf / len(flagged_c):.0%}).")
    print("This is a quota sample of the rules that had never been checked, so that figure")
    print(f"measures those rules -- it is not comparable with the {len(orig)} random gold claims.")
    if missed:
        print(f"\n{len(missed)} of {len(probes)} negative probes were flags the tree missed: "
              + ", ".join(r["claim_id"] for r in missed))
    else:
        print(f"\nNone of the {len(probes)} negative probes turned out to be a missed flag: "
              "no counter-example to C recall was found.")
    print("\n-> data/gold_expand.json  -> data/expand_eval.json")
    return out


if __name__ == "__main__":
    run()
