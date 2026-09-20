"""Label-free evidence: do the rules the gold set misses point at a real systematic gap?

Abualigah & Khader (2017) use MAD as an *unsupervised* fitness, scoring features without
any class labels. We already have an equivalent in Track S lift, so no new optimisation
algorithm is needed; the lift table is simply used as the fitness:

  qualifier support(claim) = mean lift of the claim's content words

Low lift means those words usually appear in this corpus *without* the qualifier they
need (method, boundary, verifier). If the claims a terminal fires on sit in a low
percentile, the rule is pointing at a systematic gap rather than an isolated case, and
that evidence costs no annotation.

It does not replace gold. A low percentile says this phrasing usually lacks its
qualifier here; it does not say an annotator would label those claims C.
"""
import json
from pathlib import Path

import numpy as np

from src.termstats import RE_TOKEN, STOPWORDS
from src.tree import TERMINALS, classify

ROOT = Path(__file__).resolve().parents[2]   # repo root: src/experiments/ -> .
DATA = ROOT / "data"

# mechanism -> the qualifier it is missing (table name in term_risk.json)
QUALIFIER_OF = {
    "UNDISCLOSED_METHOD": "method_stated",
    "UNDISCLOSED_BOUNDARY": "scope_stated",
    "SELECTIVE_AGGREGATION": "baseline_stated",
    "UNDEFINED_TERM": "verifier_named",
}
MIN_TOKENS = 2       # claims matching fewer words than this are not scored


def lift_maps(table):
    return {q: {r["term"]: r["lift"] for r in rows} for q, rows in table["terms"].items()}


def support(text, lut):
    """Qualifier support: mean lift over content words. None when too few words match."""
    hits = [lut[t] for t in {w for w in RE_TOKEN.findall(text.lower())
                             if w not in STOPWORDS} if t in lut]
    return float(np.mean(hits)) if len(hits) >= MIN_TOKENS else None


def run():
    table = json.loads((DATA / "term_risk.json").read_text(encoding="utf-8"))
    luts = lift_maps(table)
    claims = json.loads((DATA / "flagged.json").read_text(encoding="utf-8"))
    gold_ids = {g["claim_id"]
                for g in json.loads((DATA / "gold.json").read_text(encoding="utf-8"))}

    rows = []
    for c in claims:
        r = classify(c["text"], c["claim_id"])
        rows.append({**c, "terminal": r["terminal"], "mechanism": r["mechanism"],
                     "in_gold": c["claim_id"] in gold_ids})

    out = []
    for term, (lab, mech, sev) in TERMINALS.items():
        if lab != "C" or mech not in QUALIFIER_OF:
            continue
        q = QUALIFIER_OF[mech]
        lut = luts[q]
        # Reference distribution: the whole corpus scored against the same lift table
        allv = [v for v in (support(r["text"], lut) for r in rows) if v is not None]
        mine = [v for v in (support(r["text"], lut) for r in rows
                            if r["terminal"] == term) if v is not None]
        if not mine:
            out.append({"terminal": term, "mechanism": mech, "qualifier": q,
                        "n": 0, "median_support": None, "percentile": None,
                        "gold_covered": any(r["in_gold"] for r in rows
                                            if r["terminal"] == term),
                        "reading": "never fires"})
            continue
        med = float(np.median(mine))
        pct = float((np.array(allv) < med).mean() * 100)
        covered = any(r["in_gold"] and r["terminal"] == term for r in rows)
        reading = ("gap is systematic" if pct <= 25 else
                   "indistinguishable from corpus" if pct <= 75 else
                   "vocabulary is usually qualified")
        out.append({"terminal": term, "mechanism": mech, "qualifier": q,
                    "n": len(mine), "median_support": med, "percentile": pct,
                    "gold_covered": covered, "reading": reading})

    out.sort(key=lambda r: (r["percentile"] is None, r["percentile"]))
    payload = {"min_tokens": MIN_TOKENS, "qualifier_of": QUALIFIER_OF, "rules": out,
               "note": ("Unsupervised evidence only. A low percentile says the vocabulary a "
                        "rule keys on usually appears without its qualifier in this corpus; "
                        "it does not say a human annotator would label those claims C.")}
    (DATA / "rule_evidence.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                             encoding="utf-8")

    print("Label-free evidence: where each C rule's claims sit in the corpus distribution\n")
    print(f"{'terminal':<30}{'qualifier':<17}{'n':>4}{'median':>9}{'pctile':>8}"
          f"{'gold':>6}  reading")
    for r in out:
        if r["n"] == 0:
            print(f"{r['terminal']:<30}{r['qualifier']:<17}{0:>4}{'—':>9}{'—':>8}"
                  f"{'no':>6}  never fires")
            continue
        print(f"{r['terminal']:<30}{r['qualifier']:<17}{r['n']:>4}"
              f"{r['median_support']:>9.3f}{r['percentile']:>7.0f}%"
              f"{('yes' if r['gold_covered'] else 'no'):>6}  {r['reading']}")
    print("\n→ data/rule_evidence.json")
    return payload


if __name__ == "__main__":
    run()
