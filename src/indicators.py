"""The four indicators from FRONTEND_V2 sec. 6 and the disclosure grade from sec. 5.
The preloaded path and the upload path share this one implementation.

Inputs are plain dicts in the shape of data/*.json, not objects; the formulas follow
sec. 6 to the letter.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

GRADE_BANDS = [(75, "A"), (55, "B"), (35, "C")]   # below 35 is D


# ------------------------------------------------------------ sec. 6 indicators
def claims_needing_review(claims):
    """% of quantified claims that are technically true but incomplete."""
    scored = [c for c in claims if c.get("label") in ("A", "C")]
    return 100 * sum(c.get("label") == "C" for c in scored) / max(len(scored), 1)


def promises_per_verification(sentences):
    """Forward-looking markers per assurance mention."""
    f = sum(s["future"] for s in sentences)
    v = sum(s["verification"] for s in sentences)
    return f / max(v, 1)


def verification_density(sentences):
    """Sentences between assurance mentions. Returned as N for '1 in N'."""
    v = sum(s["verification"] for s in sentences)
    return len(sentences) / max(v, 1)


def commitments_trackable(audit):
    """% of extracted targets with >= 2 observations of the same metric."""
    n_two = sum(a["outcome"] == "kept" for a in audit)
    return 100 * n_two / max(len(audit), 1)


# --------------------------------------------------------- sec. 5 disclosure grade
def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


# Tunable parameters of the three sub-scores. The defaults are the published set from
# FRONTEND_V2 sec. 5; src/sensitivity.py sweeps them.
PVR_FLOOR, PVR_CEIL = 1.0, 5.0     # PVR <= floor scores 100, >= ceil scores 0
VERIF_TARGET = 5.0                 # assurance mentions per 100 sentences that score 100


def band_margin(score, bands=None):
    """Distance to the nearest band edge, and which letter crossing it would produce.

    The sweeps show that moving the band edges by ±12 points already flips reports (see
    src/sensitivity.py), so the letter must never be shown without its fragility.
    """
    bands = bands or GRADE_BANDS
    below = {bands[i][0]: (bands[i + 1][1] if i + 1 < len(bands) else "D")
             for i in range(len(bands))}
    edge = min((cut for cut, _ in bands), key=lambda e: abs(e - score))
    letter_at = dict((cut, g) for cut, g in bands)
    return {"edge": edge, "margin": abs(score - edge),
            "would_become": letter_at[edge] if score < edge else below[edge],
            "direction": "up" if score < edge else "down"}


def grade_components(claims, sentences, pvr_floor=PVR_FLOOR, pvr_ceil=PVR_CEIL,
                     verif_target=VERIF_TARGET, bands=None):
    """The three sub-scores (0-100 each) and their inputs, all inspectable in the UI.

    Parameters can be overridden so src/sensitivity.py can sweep them; the defaults are
    exactly what the interface displays.
    """
    scored = [c for c in claims if c.get("label") in ("A", "C")]
    n_c = sum(c.get("label") == "C" for c in scored)
    c_rate = n_c / max(len(scored), 1)
    completeness = (1 - c_rate) * 100

    pvr = promises_per_verification(sentences)
    promise_balance = clamp((pvr_ceil - pvr) / (pvr_ceil - pvr_floor)) * 100

    v = sum(s["verification"] for s in sentences)
    verif_per_100 = 100 * v / max(len(sentences), 1)
    verification = clamp(verif_per_100 / verif_target) * 100

    score = (completeness + promise_balance + verification) / 3
    letter = next((g for cut, g in (bands or GRADE_BANDS) if score >= cut), "D")
    return {
        "completeness": completeness, "promise_balance": promise_balance,
        "verification": verification, "score": score, "letter": letter,
        "inputs": {"quantified_claims": len(scored), "C_claims": n_c,
                   "C_rate": c_rate, "pvr": pvr, "verification_mentions": v,
                   "sentences": len(sentences), "verif_per_100_sentences": verif_per_100},
    }


# ------------------------------------------------------------------- data loading
def load_json(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def cached_bundle():
    """Preloaded path: claims / sentences / audit split by company."""
    claims = [{**c, "label": c.get("llm_label")} for c in load_json("prelabels.json")]
    sentences = load_json("signals.json")
    audit = load_json("trajectory_audit.json")
    companies = sorted({s["company"] for s in sentences})
    return {co: {"claims": [c for c in claims if c["company"] == co],
                 "sentences": [s for s in sentences if s["company"] == co],
                 "audit": [a for a in audit if a["company"] == co]}
            for co in companies}


def indicators_for(bundle):
    """The four indicators, packaged for st.metric."""
    return {
        "claims_needing_review": claims_needing_review(bundle["claims"]),
        "promises_per_verification": promises_per_verification(bundle["sentences"]),
        "verification_density": verification_density(bundle["sentences"]),
        "commitments_trackable": commitments_trackable(bundle["audit"]),
    }


def main():
    bundles = cached_bundle()
    print(f"{'company':<12}{'review %':>10}{'PVR':>8}{'1 in N':>9}{'trackable %':>13}{'grade':>7}")
    for co, b in bundles.items():
        i = indicators_for(b)
        g = grade_components(b["claims"], b["sentences"])
        print(f"{co:<12}{i['claims_needing_review']:>9.1f}%{i['promises_per_verification']:>8.2f}"
              f"{i['verification_density']:>9.1f}{i['commitments_trackable']:>12.1f}%"
              f"{g['letter']:>7}  ({g['score']:.1f})")


if __name__ == "__main__":
    main()
