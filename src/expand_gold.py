"""Stratified sampling by terminal, to cover rules the gold set has never exercised.

Why stratify: the ablation shows 10 of 19 class-C terminals are never covered by a gold
label, so their contribution cannot be measured at all (Abiodun et al. 2021, sec. 4.4.3
"dataset issue" and sec. 4.4.4 "established benchmarks").

Two boundaries this module must not cross:
1. **A stratified set is not a random sample.** It is drawn to a per-terminal quota, so
   overall accuracy on it does not estimate field accuracy. The original 29 random gold
   claims keep their own metrics, and the two are never merged into one score.
2. **The source pools differ.** Four terminals appear in none of the 89 candidates and can
   only be drawn from the full 390, where filter.py would have excluded them. Every row
   records a pool field so the two can be counted separately.

Four claims the tree labels A are also drawn. C recall is currently 1.000, and a
counter-example can only exist among claims the tree calls clean. Without this stratum
recall stays self-confirming.
"""
import csv
import json
import random
from collections import Counter
from pathlib import Path

from src.tree import TERMINALS, classify

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PER_TERMINAL = 2          # quota per untested terminal
N_NEGATIVE_PROBE = 4      # probes the tree calls A, to test whether C recall is really 1.0
SEED = 20260920


def pools():
    flagged = json.loads((DATA / "flagged.json").read_text(encoding="utf-8"))
    cand_ids = {c["claim_id"]
                for c in json.loads((DATA / "candidates.json").read_text(encoding="utf-8"))}
    gold_ids = {g["claim_id"]
                for g in json.loads((DATA / "gold.json").read_text(encoding="utf-8"))}
    rows = []
    for c in flagged:
        r = classify(c["text"], c["claim_id"])
        rows.append({"claim_id": c["claim_id"], "company": c["company"],
                     "text": c["text"], "terminal": r["terminal"], "label": r["label"],
                     "pool": "candidates" if c["claim_id"] in cand_ids else "flagged_only",
                     "in_gold": c["claim_id"] in gold_ids})
    return rows, gold_ids


def untested(rows, gold_ids):
    """Class-C terminals with zero gold coverage that do fire on the corpus."""
    covered = Counter(r["terminal"] for r in rows if r["in_gold"])
    fires = Counter(r["terminal"] for r in rows)
    return [t for t, (lab, _, _) in TERMINALS.items()
            if lab == "C" and fires[t] > 0 and covered[t] == 0]


def sample():
    rng = random.Random(SEED)
    rows, gold_ids = pools()
    targets = untested(rows, gold_ids)

    picked, by_terminal = [], {}
    for t in sorted(targets):
        avail = [r for r in rows if r["terminal"] == t and not r["in_gold"]]
        take = rng.sample(avail, min(PER_TERMINAL, len(avail)))
        by_terminal[t] = len(take)
        picked += take

    # Probe stratum: claims the tree calls A or B, to look for missed flags
    probe_pool = [r for r in rows if r["label"] in ("A", "B") and not r["in_gold"]]
    probes = rng.sample(probe_pool, min(N_NEGATIVE_PROBE, len(probe_pool)))
    for p in probes:
        by_terminal.setdefault("(negative probe)", 0)
        by_terminal["(negative probe)"] += 1
    picked += probes

    rng.shuffle(picked)          # shuffle so the annotator cannot see the strata
    return picked, by_terminal, targets


def already_annotated(path):
    """Filled labels in an existing sheet. Overwriting these would destroy annotation."""
    if not path.exists():
        return 0
    with path.open(newline="", encoding="utf-8") as fh:
        return sum(1 for r in csv.DictReader(fh) if (r.get("my_label") or "").strip())


def write(picked, force=False):
    """The blind CSV carries no terminal or tree label; the key is stored separately.

    The sheet is written in place, so re-running this module would silently wipe work
    that cannot be recovered: the annotation is a person reading 20 claims, and the
    answer key is gitignored. Refuse instead, unless the caller says otherwise.
    """
    blind = DATA / "blind_expand.csv"
    filled = already_annotated(blind)
    if filled and not force:
        raise SystemExit(
            f"{blind.name} already holds {filled} filled labels and would be overwritten.\n"
            f"Those labels are the stratified blind test; regenerating discards them.\n"
            f"Run `python -m src.merge_expand` to score the sheet you have, or pass "
            f"--force to draw a new sample anyway.")
    with blind.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["claim_id", "company", "text", "my_label", "note"])
        for r in picked:
            w.writerow([r["claim_id"], r["company"], r["text"], "", ""])

    # The key is excluded from the repository (.gitignore): it holds the tree predictions,
    # and seeing them breaks the blindness. Re-running this module with the fixed SEED
    # reproduces it exactly.
    key = DATA / "expand_key.json"
    key.write_text(json.dumps(
        [{"claim_id": r["claim_id"], "terminal": r["terminal"],
          "tree_label": r["label"], "pool": r["pool"]} for r in picked],
        ensure_ascii=False, indent=1), encoding="utf-8")
    return blind, key


def main():
    import sys
    picked, by_terminal, targets = sample()
    blind, key = write(picked, force="--force" in sys.argv[1:])

    print(f"{len(targets)} class-C terminals have never been tested by gold. Quota:\n")
    print(f"{'stratum':<32}{'sampled':>8}")
    for t, n in sorted(by_terminal.items()):
        print(f"{t:<32}{n:>8}")
    print(f"{'total':<32}{len(picked):>8}")

    pool_mix = Counter(r["pool"] for r in picked)
    print(f"\nSource pools: candidates {pool_mix['candidates']} · "
          f"flagged_only {pool_mix['flagged_only']}")
    print("flagged_only rows would not pass filter.py, so count them separately.")
    print(f"\n-> {blind.name}  (blind sheet; fill my_label with A / B / C / D / SKIP)")
    print(f"-> {key.name}  (answer key; do not open before merging)")


if __name__ == "__main__":
    main()
