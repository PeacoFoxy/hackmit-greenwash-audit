"""Filter flagged claims down to self-referential, assertive, suspicious candidates."""
import json
import re
from collections import Counter
from pathlib import Path

RE_SELF = re.compile(
    r"\b(?:we|our|us|microsoft|alphabet|google|amazon|aws)\b", re.IGNORECASE
)
RE_ASSERT = re.compile(
    r"\b(?:reduc|achiev|deliver|match|power|offset|remov|eliminat|will|commit|reach|"
    r"maintain|operat|invest|contract|sourc|replenish|recycl|divert|avoid)\w*",
    re.IGNORECASE,
)
MIN_LEN, MAX_LEN = 40, 400
VAGUE_THRESHOLD = 0.5


def keep(claim):
    t = claim.get("text", "") or ""
    if not (MIN_LEN <= len(t) <= MAX_LEN):
        return False
    if not RE_SELF.search(t) or not RE_ASSERT.search(t):
        return False
    return bool(claim.get("flags")) or claim.get("vagueness", 0) >= VAGUE_THRESHOLD


def main():
    root = Path(__file__).resolve().parent.parent
    claims = json.loads((root / "data" / "flagged.json").read_text(encoding="utf-8"))
    kept = [c for c in claims if keep(c)]

    (root / "data" / "candidates.json").write_text(
        json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print(f"Kept: {len(kept)} / {len(claims)}")
    for company, n in Counter(c.get("company") for c in kept).most_common():
        print(f"  {company:<15} {n}")
    print(f"With flags: {sum(1 for c in kept if c['flags'])}")
    print(f"High vagueness (>= {VAGUE_THRESHOLD}): "
          f"{sum(1 for c in kept if c['vagueness'] >= VAGUE_THRESHOLD)}")


if __name__ == "__main__":
    main()
