"""Abstention curves: how high does accuracy go once the system may say "not sure"?

The idea comes from the fuzzy c-means work that recurs in this literature -- membership
degrees instead of hard labels (Purushothaman et al. 2020; Gopal & Brunda 2019; Majhi
2019). Our tree emits hard labels, but every node was annotated CLOSED or OPEN at design
time: CLOSED means the concept has a fixed vocabulary, so a regex miss is close to proof
of absence; OPEN means the phrasing varies and a miss is weak evidence. That annotation
had never been used for anything.

Five confidence proxies are tested for whether they actually sort errors to the back:
  closed_frac  fraction of CLOSED nodes on the path
  decided_by   whether the deciding node was CLOSED
  severity     terminal severity 1-3 (A/B counted as 0)
  agree_1      does the tree agree with baseline2
  agree_n      how many of the three model methods agree with the tree

A proxy only carries information if it beats random abstention. Dropping any claims
raises accuracy simply by shrinking the sample, so the control is "discard the same
number at random".
"""
import json
import warnings
from pathlib import Path

import numpy as np

from src.tree import classify

warnings.filterwarnings("ignore", message="y_pred contains classes not in y_true")

ROOT = Path(__file__).resolve().parents[2]   # repo root: src/experiments/ -> .
DATA = ROOT / "data"
N_RANDOM = 2000
LLM_METHODS = ("baseline2", "pipeline", "pipeline_allflags")


def load():
    met = json.loads((DATA / "metrics.json").read_text(encoding="utf-8"))
    preds = met["predictions"]
    cands = {c["claim_id"]: c
             for c in json.loads((DATA / "candidates.json").read_text(encoding="utf-8"))}
    rows = []
    for p in preds:
        r = classify(cands[p["claim_id"]]["text"], p["claim_id"])
        path = r["path"]
        closed = sum(1 for s in path if s["reliability"] == "CLOSED")
        rows.append({
            "id": p["claim_id"], "gold": p["gold"], "pred": r["label"],
            "correct": int(r["label"] == p["gold"]),
            "closed_frac": closed / len(path),
            "decided_by": int(path[-1]["reliability"] == "CLOSED"),
            "severity": r["severity"] or 0,
            "agree_1": int(p["baseline2"] == r["label"]),
            "agree_n": sum(int(p[m] == r["label"]) for m in LLM_METHODS),
        })
    return rows


def curve(rows, key):
    """Abstain by descending confidence threshold. Returns (coverage, accuracy) points."""
    vals = sorted({r[key] for r in rows}, reverse=True)
    out = []
    for t in vals:
        kept = [r for r in rows if r[key] >= t]
        out.append({"threshold": t, "coverage": len(kept) / len(rows),
                    "n_answered": len(kept),
                    "accuracy": sum(r["correct"] for r in kept) / len(kept)})
    return out


def random_baseline(rows, n_answered, n=N_RANDOM, seed=0):
    """Accuracy when the same number of claims is dropped at random: the control."""
    rng = np.random.default_rng(seed)
    corr = np.array([r["correct"] for r in rows])
    accs = [corr[rng.choice(len(corr), n_answered, replace=False)].mean() for _ in range(n)]
    return float(np.mean(accs)), float(np.percentile(accs, 95))


def run():
    rows = load()
    base = sum(r["correct"] for r in rows) / len(rows)
    print(f"accuracy answering everything = {base:.3f} ({len(rows)} claims)")
    print("Random abstention is the control: dropping claims raises accuracy by itself.\n")

    out = {"n": len(rows), "baseline_accuracy": base, "proxies": {}}
    for key in ("closed_frac", "decided_by", "severity", "agree_1", "agree_n"):
        pts = curve(rows, key)
        print(f"{key}")
        print(f"  {'thresh':>8}{'coverage':>9}{'n':>6}{'accuracy':>9}"
              f"{'rand mean':>10}{'rand p95':>9}  ")
        beats = 0
        for p in pts:
            rm, r95 = random_baseline(rows, p["n_answered"])
            p["random_mean"], p["random_p95"] = rm, r95
            p["beats_random"] = p["accuracy"] > r95
            beats += p["beats_random"]
            mark = "  beats random" if p["beats_random"] else ""
            print(f"  {p['threshold']:>8.2f}{p['coverage']:>9.0%}{p['n_answered']:>6}"
                  f"{p['accuracy']:>9.3f}{rm:>10.3f}{r95:>9.3f}{mark}")
        out["proxies"][key] = {"points": pts, "n_beating_random": beats}
        print()

    (DATA / "abstain.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    winners = [k for k, v in out["proxies"].items() if v["n_beating_random"]]
    print("Proxies that beat random: " + (", ".join(winners) if winners else "none"))
    print("→ data/abstain.json")
    return out


if __name__ == "__main__":
    run()
