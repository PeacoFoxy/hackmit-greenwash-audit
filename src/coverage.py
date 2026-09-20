"""Rule coverage gaps: find claims that carry quantitative signal but fire no rule, and
ask the model which vocabulary the rule layer does not recognise."""
import json
import re
from collections import Counter, defaultdict

from src.llm import ask

BATCH = 15

RE_DIGIT = re.compile(r"\d")
RE_FUTURE = re.compile(
    r"\bwill\b|\bby\s+20\d{2}\b|\bplan(?:s|ning)?\s+to\b|\btarget(?:s|ing|ed)?\b|"
    r"\bexpect(?:s|ed|ing)?\b|\baim(?:s|ing)?\s+to\b|\bcommit(?:s|ted|ment|ments)?\b",
    re.I,
)
RE_PERCENT = re.compile(r"\d+(?:\.\d+)?\s*(?:%|percent\b)", re.I)
RE_UNIT = re.compile(
    r"\btCO2e?\b|\bMtCO2e?\b|\bMWh?\b|\bGWh?\b|\bGW\b|\bMW\b|\bkWh\b|\bTWh\b|"
    r"\bliters?\b|\blitres?\b|\bgallons?\b|\bm3\b|\btonnes?\b|\btons?\b|\bmetric\s+tons?\b",
    re.I,
)

SYSTEM = "Output ONLY a JSON array, no prose, no markdown fences."

PROMPT = """These are corporate environmental claims that our carbon-accounting rule set did not flag.
For each, identify any technical term, metric, or accounting concept that could hide a scoping or
boundary problem but is not covered by these nine existing rules: market-based vs location-based
Scope 2, REC/PPA grid matching, carbon neutral offsets, missing baseline year, missing scope
boundary, cherry-picked PUE, water accounting, future promises without milestones, matching
language.

CLAIMS:
{claims}

Output ONLY a JSON array: [{{"term": "...", "why_it_matters": "one sentence",
"example_claim_id": "..."}}]. Return [] if nothing new."""


MECHANISMS = ["UNDISCLOSED_BOUNDARY", "UNDISCLOSED_METHOD",
              "SELECTIVE_AGGREGATION", "UNDEFINED_TERM"]

CONSOLIDATE_PROMPT = """These are candidate gaps in a carbon-accounting rule set. Group them into a
small number of reusable rules — aim for 5 to 8. Each rule must generalize beyond one company and
one metric. Classify each into exactly one mechanism: UNDISCLOSED_BOUNDARY, UNDISCLOSED_METHOD,
SELECTIVE_AGGREGATION, or UNDEFINED_TERM. Discard any candidate that is not a measurement or
accounting concept.

CANDIDATES:
{candidates}

Output JSON: [{{"rule_name": "...", "mechanism": "...", "detects": "one sentence",
"trigger_terms": [...], "absorbed_candidates": [...]}}]"""


def residual(claims):
    out = []
    for c in claims:
        t = c.get("text", "")
        if c.get("flags"):
            continue
        if not RE_DIGIT.search(t):
            continue
        if RE_FUTURE.search(t) or RE_PERCENT.search(t) or RE_UNIT.search(t):
            out.append(c)
    return out


def parse_json(raw):
    """Three-tier parse: whole JSON -> first [...] -> per-item regex. Returns [] if all fail."""
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip(), flags=re.I).strip()
    try:
        out = json.loads(s)
        if isinstance(out, list):
            return out
    except Exception:
        pass
    m = re.search(r"\[.*\]", s, flags=re.S)
    if m:
        try:
            out = json.loads(m.group(0))
            if isinstance(out, list):
                return out
        except Exception:
            pass
    pairs = re.findall(r'"term"\s*:\s*"([^"]+)"', s)
    if pairs:
        return [{"term": t} for t in pairs]
    print(f"  [warn] parse failed, raw[:200]: {s[:200]!r}")
    return []


def consolidate():
    """Stage two: consolidate candidate terms into 5-8 reusable rules, one mechanism each."""
    gaps = json.load(open("data/coverage_gaps.json"))["gaps"]
    terms = [g["term"] for g in gaps]
    print(f"\nConsolidating {len(terms)} candidate terms ...")

    raw = ask(CONSOLIDATE_PROMPT.format(candidates="\n".join(f"- {t}" for t in terms)),
              system=SYSTEM, max_tokens=4000)
    rules = [r for r in parse_json(raw) if isinstance(r, dict) and r.get("rule_name")]
    for r in rules:
        if r.get("mechanism") not in MECHANISMS:
            print(f"  [warn] unknown mechanism: {r.get('mechanism')!r} ({r['rule_name']})")

    absorbed = {c for r in rules for c in r.get("absorbed_candidates", [])}
    json.dump({"n_candidates": len(terms), "n_rules": len(rules),
               "discarded": [t for t in terms if t not in absorbed], "rules": rules},
              open("data/proposed_rules.json", "w"), ensure_ascii=False, indent=1)

    print(f"\n{len(rules)} rules -> data/proposed_rules.json\n")
    for r in rules:
        print(f"[{r.get('mechanism', '?')}] {r['rule_name']}")
        print(f"    {r.get('detects', '')}")
        print(f"    triggers: {', '.join(r.get('trigger_terms', [])[:8])}")
        print(f"    absorbs {len(r.get('absorbed_candidates', []))} candidates\n")
    print(f"candidates not absorbed: {len(terms) - len(absorbed & set(terms))}")
    return rules


def main():
    claims = json.load(open("data/flagged.json"))
    res = residual(claims)
    print(f"residual set: {len(res)} / {len(claims)} claims "
          f"({len(res) / len(claims) * 100:.1f}%) -- has figures, fires no flag")

    counts = Counter()
    details = defaultdict(lambda: {"why": [], "examples": []})
    for i in range(0, len(res), BATCH):
        batch = res[i:i+BATCH]
        items = "\n".join(
            json.dumps({"claim_id": c["claim_id"], "text": c["text"]}, ensure_ascii=False)
            for c in batch)
        print(f"batch {i // BATCH + 1}/{-(-len(res) // BATCH)} ({len(batch)} claims)")
        for r in parse_json(ask(PROMPT.format(claims=items), system=SYSTEM)):
            if not isinstance(r, dict) or not r.get("term"):
                continue
            key = str(r["term"]).strip().lower()
            counts[key] += 1
            d = details[key]
            if r.get("why_it_matters"):
                d["why"].append(str(r["why_it_matters"]))
            if r.get("example_claim_id"):
                d["examples"].append(str(r["example_claim_id"]))

    gaps = [{"term": t, "count": n,
             "why_it_matters": details[t]["why"][0] if details[t]["why"] else "",
             "example_claim_ids": details[t]["examples"][:5]}
            for t, n in counts.most_common()]
    json.dump({"residual_n": len(res), "total_claims": len(claims), "gaps": gaps},
              open("data/coverage_gaps.json", "w"), ensure_ascii=False, indent=1)

    by_id = {c["claim_id"]: c for c in claims}
    print(f"\n{len(gaps)} candidate terms -> data/coverage_gaps.json\n")
    print(f"{'term':<38}{'n':>4}  example")
    for g in gaps[:15]:
        ex = g["example_claim_ids"][0] if g["example_claim_ids"] else ""
        text = by_id[ex]["text"][:70] if ex in by_id else ""
        print(f"{g['term'][:37]:<38}{g['count']:>4}  {ex} {text}")


if __name__ == "__main__":
    import sys
    if "consolidate" not in sys.argv[1:]:  # stage two only: python -m src.coverage consolidate
        main()
    consolidate()
