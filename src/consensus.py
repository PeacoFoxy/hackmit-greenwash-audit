"""Consensus layer: merge the three tracks, assign a state, rank. No model calls
(track D reads predictions that already exist).

No weighting and no confidence-based winner (spec sec. 4): both readings are reported,
and disagreements are ranked first.
"""
import json
from collections import Counter
from pathlib import Path

from src.termstats import build_table, risk
from src.tree import classify as tree_classify

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# "High" threshold for risk_S. The spec does not fix one, so a constant is used and
# recorded in the output so a reviewer can check it.
HIGH_RISK = 0.70


def load_track_d():
    """Track D is baseline2 from evaluate.py. Only the 29 gold claims have predictions."""
    m = json.loads((DATA / "metrics.json").read_text(encoding="utf-8"))
    return {p["claim_id"]: p.get("baseline2") for p in m["predictions"] if p.get("baseline2")}


def state_of(r, d, risk_s):
    """State machine from spec sec. 4. Special cases are checked before general disagreement."""
    if d is None:
        return "NO_TRACK_D", r["label"]
    if r["label"] == d:
        return "CONFIRMED", d
    if r["severity"] == 3 and r["decided_by"] == "CLOSED" and d == "A":
        return "RULE_ONLY", "C"          # terminology fact; the tree is not overruled
    if r["label"] == "A" and d == "C" and risk_s is not None and risk_s >= HIGH_RISK:
        return "NOVEL", "C"              # no tree branch + model suspects + corpus agrees
    return "CONTESTED", None             # report both labels, synthesise neither


def main():
    claims = {c["claim_id"]: c for c in json.loads(
        (DATA / "candidates.json").read_text(encoding="utf-8"))}
    sentences = [r["text"] for r in json.loads(
        (DATA / "signals.json").read_text(encoding="utf-8"))]
    table, _, _ = build_table(sentences)
    track_d = load_track_d()

    out = []
    for cid, c in claims.items():
        r = tree_classify(c["text"], cid)
        s = risk(c["text"], table, r["domain"])
        d = track_d.get(cid)
        st, final = state_of(r, d, s["risk"])
        out.append({
            "claim_id": cid, "company": c["company"], "text": c["text"],
            "track_R": {k: r[k] for k in
                        ("label", "terminal", "mechanism", "severity", "path")},
            "track_D": {"label": d, "confidence": None, "reasoning": None},
            "track_S": s,
            "consensus": {"state": st, "label": final,
                          "labels_reported": [r["label"], d] if st == "CONTESTED" else None},
        })

    # Disagreement first, then severity, then risk
    prio = {"CONTESTED": 0, "RULE_ONLY": 0, "NOVEL": 0, "CONFIRMED": 1, "NO_TRACK_D": 2}
    out.sort(key=lambda o: (prio[o["consensus"]["state"]],
                            -(o["track_R"]["severity"] or 0),
                            -(o["track_S"]["risk"] or 0)))
    for i, o in enumerate(out, 1):
        o["consensus"]["triage_rank"] = i

    (DATA / "consensus.json").write_text(json.dumps(
        {"high_risk_threshold": HIGH_RISK, "claims": out}, ensure_ascii=False, indent=1),
        encoding="utf-8")

    novel = [o for o in out if o["consensus"]["state"] == "NOVEL"]
    (DATA / "candidate_rules.json").write_text(json.dumps(
        [{"claim_id": o["claim_id"], "text": o["text"],
          "tree_terminal": o["track_R"]["terminal"], "risk": o["track_S"]["risk"],
          "terms": o["track_S"]["contributing_terms"]} for o in novel],
        ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{len(out)} claims → data/consensus.json")
    print("state:", dict(Counter(o["consensus"]["state"] for o in out)))

    # Breakdown from spec sec. 4; only gold claims have ground truth
    gold = {g["claim_id"]: g["gold_label"] for g in json.loads(
        (DATA / "gold.json").read_text(encoding="utf-8")) if g["gold_label"] != "SKIP"}
    scored = [o for o in out if o["claim_id"] in gold and o["track_D"]["label"]]
    def acc(rows, pick):
        if not rows:
            return None
        return sum(pick(o) == gold[o["claim_id"]] for o in rows) / len(rows)

    print(f"\n{'state':<12}{'n':>4}{'acc_R':>8}{'acc_D':>8}{'n(no B)':>9}{'acc_R':>8}{'acc_D':>8}")
    for st in ["CONFIRMED", "CONTESTED", "RULE_ONLY", "NOVEL"]:
        grp = [o for o in scored if o["consensus"]["state"] == st]
        nb = [o for o in grp if gold[o["claim_id"]] != "B"]
        if not grp:
            print(f"{st:<12}{0:>4}{'—':>8}{'—':>8}{0:>9}{'—':>8}{'—':>8}")
            continue
        f = lambda v: f"{v:.3f}" if v is not None else "—"
        r_ = lambda o: o["track_R"]["label"]
        d_ = lambda o: o["track_D"]["label"]
        print(f"{st:<12}{len(grp):>4}{f(acc(grp, r_)):>8}{f(acc(grp, d_)):>8}"
              f"{len(nb):>9}{f(acc(nb, r_)):>8}{f(acc(nb, d_)):>8}")
    print("\nBoth tracks are reported separately on the same basis; under CONFIRMED they agree by definition.")
    print(f"NOVEL -> data/candidate_rules.json ({len(novel)} claims)")


if __name__ == "__main__":
    main()
