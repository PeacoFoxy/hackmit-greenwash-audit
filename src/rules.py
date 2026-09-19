"""Deterministic regex-based greenwashing flags and vagueness scoring (no LLM)."""
import json
import re
from collections import Counter
from pathlib import Path

I = re.IGNORECASE


def _rx(pattern):
    return re.compile(pattern, I)


# 100% / carbon-free / zero-carbon modifying electricity/energy/power (up to 3 words in between)
RE_CLEAN_CLAIM = _rx(
    r"(?:100\s*%|\b100\s+percent|\bcarbon[-\s]free|\bzero[-\s]carbon)"
    r"(?:\W+\w+){0,3}?\W+(?:electricity|energy|power)\b"
)
RE_SCOPE2_METHOD = _rx(r"\b(?:location|market)[-\s]based\b")
RE_MATCHING = _rx(r"\bmatched\s+by\b|\bmatch(?:ing|es)?\b|\bpurchas(?:e|es|ed|ing)\b")

RE_NEUTRAL = _rx(r"\bcarbon[-\s]neutral(?:ity)?\b|\bnet[-\s]zero\b|\bclimate[-\s]neutral(?:ity)?\b")
RE_OFFSET = _rx(r"\boffsets?\b|\boffsetting\b|\bremovals?\b|\bcredits?\b")

RE_PERCENT = _rx(r"\d+(?:\.\d+)?\s*(?:%|percent\b)")
RE_CHANGE_VERB = _rx(
    r"\b(?:reduc|decreas|increas|cut|lower|improv|declin|drop)(?:e|es|ed|ing|tion|tions|s)?\b"
)
RE_BASELINE = _rx(
    r"\bbase(?:line)?\s+year\b|\bbaseline\b|\b(?:since|from|vs\.?|versus|compared\s+(?:to|with))\s+(?:19|20)\d{2}\b"
)

RE_RESOURCE = _rx(r"\bemissions?\b|\benergy\b|\belectricity\b|\bwater\b")
RE_DIGIT = re.compile(r"\d")
RE_BOUNDARY = _rx(
    r"\bscopes?\s*[123]\b|\bfleet\b|\bportfolio\b|\bglobal(?:ly)?\b|\ball\s+(?:of\s+our\s+)?facilities\b"
)

RE_PROCUREMENT = _rx(r"\bPPAs?\b|\bRECs?\b|\bpower\s+purchase\b|\bcertificates?\b")
RE_GRID = _rx(r"\bgrids?\b|\bregion(?:s|al|ally)?\b|\bISOs?\b|\blocal(?:ly)?\b")

RE_PUE = _rx(r"\bPUE\b")
RE_PUE_SCOPE = _rx(r"\bfleet\b|\baverage[ds]?\b|\bacross\s+all\b")

RE_WATER = _rx(r"\bwater[-\s]positive\b|\bwater[-\s]neutral(?:ity)?\b|\breplenish(?:es|ed|ing|ment)?\b")

RE_FUTURE = _rx(r"\bby\s+20\d{2}\b|\bwill\b")
RE_MILESTONE = _rx(r"\binterim\b|\bmilestones?\b|\bannual(?:ly)?\b")

RE_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
RE_VERIFY = _rx(r"\bverif\w*|\bassur\w*|\baudit\w*|\bthird[-\s]party\b|\bcertif\w*")
VAGUE_TERMS = [
    r"\bcommitted\s+to\b",
    r"\bstriv(?:e|es|ing)\b",
    r"\baim(?:s|ing)?\s+to\b",
    r"\baspir(?:e|es|ing|ation)\w*",
    r"\bleading\b",
    r"\bsustainable\s+future\b",
    r"\bworking\s+toward(?:s)?\b",
    r"\bbelieve[sd]?\b",
    r"\bresponsibl(?:e|y)\b",
]
RE_VAGUE = [_rx(p) for p in VAGUE_TERMS]


def flags(text):
    t = text or ""
    out = []

    clean_claim = bool(RE_CLEAN_CLAIM.search(t))
    method_missing = not RE_SCOPE2_METHOD.search(t)
    if clean_claim and method_missing:
        out.append("SCOPE2_METHOD_UNSTATED")
        if RE_MATCHING.search(t):
            out.append("MATCHING_LANGUAGE")

    if RE_NEUTRAL.search(t) and not RE_OFFSET.search(t):
        out.append("OFFSET_UNDISCLOSED")

    if RE_PERCENT.search(t) and RE_CHANGE_VERB.search(t) and not RE_BASELINE.search(t):
        out.append("NO_BASELINE_YEAR")

    if RE_RESOURCE.search(t) and RE_DIGIT.search(t) and not RE_BOUNDARY.search(t):
        out.append("SCOPE_BOUNDARY_UNCLEAR")

    if RE_PROCUREMENT.search(t) and not RE_GRID.search(t):
        out.append("GRID_MISMATCH_RISK")

    if RE_PUE.search(t) and not RE_PUE_SCOPE.search(t):
        out.append("CHERRY_PICKED_METRIC")

    if RE_WATER.search(t):
        out.append("WATER_ACCOUNTING_VAGUE")

    if RE_FUTURE.search(t) and not RE_MILESTONE.search(t):
        out.append("FUTURE_PROMISE_NO_MILESTONE")

    return out


def vagueness(text):
    t = text or ""
    score = 0.0
    if not RE_DIGIT.search(t):
        score += 0.35
    if not RE_YEAR.search(t):
        score += 0.20
    if not RE_VERIFY.search(t):
        score += 0.15
    hits = sum(1 for rx in RE_VAGUE if rx.search(t))
    score += min(0.10 * hits, 0.30)
    return round(min(score, 1.0), 2)


def main():
    root = Path(__file__).resolve().parent.parent
    claims = json.loads((root / "data" / "claims.json").read_text(encoding="utf-8"))

    for c in claims:
        c["flags"] = flags(c.get("text", ""))
        c["vagueness"] = vagueness(c.get("text", ""))

    (root / "data" / "flagged.json").write_text(
        json.dumps(claims, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    counts = Counter(f for c in claims for f in c["flags"])
    print(f"Total claims: {len(claims)}")
    for flag, n in counts.most_common():
        print(f"  {flag:<30} {n}")
    no_flag = sum(1 for c in claims if not c["flags"])
    pct = no_flag / len(claims) * 100 if claims else 0.0
    print(f"  {'(no flags)':<30} {no_flag} ({pct:.1f}%)")


if __name__ == "__main__":
    main()
