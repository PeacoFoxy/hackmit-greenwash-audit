"""Parameter sensitivity: how much does the conclusion depend on the thresholds?

The form is taken from Mosa (2020) sec. 5.4 "Effects of parameters" and the parameter
tables in Lu et al. (2015): report the whole curve, not just the best point. The
thresholds here were chosen by the author rather than fitted (FRONTEND_V2 sec. 5 says so),
so the only honest defence is not "the threshold is right" but "the conclusion holds in a
neighbourhood of it".

Four sweeps:
  1. shifting all three grade-band edges together
  2. the PVR ceiling (the right end of the promise_balance clamp)
  3. the verification target (third-party verification mentions per 100 sentences)
  4. the z multiplier in anomaly detection (how the passage count moves with it)
Zero LLM calls.
"""
import json
from pathlib import Path

import numpy as np

from src.indicators import (GRADE_BANDS, cached_bundle, grade_components,
                            promises_per_verification)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def grade_of(bundle, **kw):
    g = grade_components(bundle["claims"], bundle["sentences"], **kw)
    return g["letter"], g["score"]


def sweep_bands(bundles, shifts=np.arange(-12, 12.1, 2)):
    """Shift all three band edges (75/55/35) by the same amount."""
    rows = []
    for d in shifts:
        bands = [(cut + d, g) for cut, g in GRADE_BANDS]
        rows.append({"shift": float(d),
                     **{co: grade_of(b, bands=bands)[0] for co, b in bundles.items()}})
    return rows


def sweep_pvr_ceil(bundles, ceils=np.arange(3.0, 8.01, 0.5)):
    rows = []
    for c in ceils:
        rows.append({"pvr_ceil": float(c),
                     **{co: grade_of(b, pvr_ceil=float(c))[0] for co, b in bundles.items()}})
    return rows


def sweep_verif_target(bundles, targets=np.arange(2.0, 10.01, 0.5)):
    rows = []
    for t in targets:
        rows.append({"verif_target": float(t),
                     **{co: grade_of(b, verif_target=float(t))[0]
                        for co, b in bundles.items()}})
    return rows


def sweep_anomaly(bundles, ks=np.arange(1.0, 3.51, 0.25)):
    """z multiplier for anomalous passages: threshold = mean + k*std. Passage count vs k."""
    from collections import Counter

    from src.anomaly import MIN_REGION, PRECISE_FLAGS, smooth
    from src.rules import flags as rule_flags

    per_company = {}
    for co, b in bundles.items():
        per_sent = [[f for f in rule_flags(r["text"]) if f in PRECISE_FLAGS]
                    for r in b["sentences"]]
        per_company[co] = (per_sent, smooth([len(f) for f in per_sent]))

    rows = []
    for k in ks:
        row = {"k": float(k)}
        for co, (per_sent, vals) in per_company.items():
            thr = vals.mean() + k * vals.std()
            hot, i, n = vals > thr, 0, 0
            while i < len(hot):
                if not hot[i]:
                    i += 1
                    continue
                j = i
                while j < len(hot) and hot[j]:
                    j += 1
                if j - i >= MIN_REGION and Counter(f for fs in per_sent[i:j] for f in fs):
                    n += 1
                i = j
            row[co] = n
        rows.append(row)
    return rows


def margins(bundles):
    """Points from each company to its nearest band edge -- how fragile the grade is."""
    out = []
    for co, b in bundles.items():
        letter, s = grade_of(b)
        edges = [cut for cut, _ in GRADE_BANDS]
        nearest = min(edges, key=lambda e: abs(e - s))
        out.append({"company": co, "score": s, "grade": letter,
                    "nearest_edge": nearest, "margin": abs(s - nearest),
                    "pvr": promises_per_verification(b["sentences"])})
    return sorted(out, key=lambda r: r["margin"])


def stability(rows, companies):
    """How many distinct grades each company takes across a sweep; 1 = fully stable."""
    return {co: sorted({r[co] for r in rows}) for co in companies}


def main():
    bundles = cached_bundle()
    companies = list(bundles)

    sweeps = {
        "band_shift": sweep_bands(bundles),
        "pvr_ceil": sweep_pvr_ceil(bundles),
        "verif_target": sweep_verif_target(bundles),
        "anomaly_k": sweep_anomaly(bundles),
    }
    marg = margins(bundles)

    out = {"defaults": {"bands": GRADE_BANDS, "pvr_floor": 1.0, "pvr_ceil": 5.0,
                        "verif_target": 5.0, "anomaly_k": 2.0},
           "margins": marg, "sweeps": sweeps,
           "note": ("Whole curves are reported, not the argmax. The thresholds were chosen "
                    "by the author; this analysis shows how far a conclusion survives when "
                    "they move, it does not justify the specific values.")}
    (DATA / "sensitivity.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                           encoding="utf-8")

    print("Distance from each grade to its nearest band edge (smaller = more fragile)")
    print(f"{'company':<11}{'score':>7}{'grade':>7}{'edge':>7}{'margin':>8}")
    for m in marg:
        print(f"{m['company']:<11}{m['score']:>7.1f}{m['grade']:>7}"
              f"{m['nearest_edge']:>7}{m['margin']:>8.1f}")

    for name, key, unit in [("grade bands shifted together", "band_shift", "shift"),
                            ("PVR ceiling", "pvr_ceil", "pvr_ceil"),
                            ("verification target (per 100 sentences)", "verif_target",
                             "verif_target")]:
        rows = sweeps[key]
        st = stability(rows, companies)
        lo, hi = rows[0][unit], rows[-1][unit]
        print(f"\n{name}  sweep {lo:g} -> {hi:g}")
        for co in companies:
            seq = "".join(r[co] for r in rows)
            flips = sum(1 for a, b in zip(seq, seq[1:]) if a != b)
            print(f"  {co:<11}{seq}   grades seen {st[co]}  {flips} flips")

    print("\nz multiplier k for anomalous passages  sweep 1.0 -> 3.5")
    print("  " + "k".ljust(9) + "".join(f"{co[:9]:>11}" for co in companies))
    for r in sweeps["anomaly_k"]:
        print(f"  {r['k']:<9.2f}" + "".join(f"{r[co]:>11}" for co in companies))
    print("\n→ data/sensitivity.json")
    return out


if __name__ == "__main__":
    main()
