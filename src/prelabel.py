"""Annotation aid: the model pre-labels candidate claims into the four classes.

data/candidates.json -> data/prelabels.json + data/annotations.csv  [model]

The pre-labels feed the report-level indicators. They are NOT gold and cannot become
gold: if the gold set were model-generated, every accuracy comparison would be scoring
the model against its own answers.

This file used to emit a blank `gold_label` column next to `llm_label`, inviting exactly
that. It happened -- all 89 rows came back with gold_label identical to llm_label, and
13 of the 30 that overlapped the real gold set contradicted it. Warning against the
mistake was not enough, so the column is gone. Gold is collected only on a blind sheet
(data/blind30.csv, data/blind_expand.csv), where the annotator sees the claim text and
nothing else -- no model label, no rule-tree terminal, no flags.
"""
import csv, json, re
from collections import Counter
from src.llm import ask

BATCH = 10
LABELS = {"A", "B", "C", "D"}

SYSTEM = """You are an auditor classifying corporate environmental claims for greenwashing risk.
Labels:
A = Substantiated: concrete numbers, clear boundary (states scope or accounting method), independently verifiable.
B = Vague: unfalsifiable rhetoric with no checkable specifics.
C = Accounting_misleading: technically true but uses accounting choices to create a misleading impression,
    e.g. claiming 100% renewable on a market-based basis, passing off offsets as real reductions,
    reporting only a favorable boundary, or future pledges without interim milestones.
D = Contradicted: conflicts with other information in the same document or with well-known public facts.
The rule-based flags and vagueness score are hints from a regex pass; use them as evidence, not as verdicts.
Output ONLY a JSON array, no prose, no markdown fences."""

PROMPT = """Classify each claim below. All are from {company}.

FLAG MEANINGS:
- SCOPE2_METHOD_UNSTATED: 100%/carbon-free energy claim without location-/market-based method
- MATCHING_LANGUAGE: uses "matched by"/"purchase" framing for clean energy
- OFFSET_UNDISCLOSED: carbon/climate neutral or net zero without mentioning offsets/removals
- NO_BASELINE_YEAR: percentage change with no baseline year
- SCOPE_BOUNDARY_UNCLEAR: quantitative figure without scope 1/2/3 or fleet-wide boundary
- GRID_MISMATCH_RISK: PPA/REC/certificates without grid/region reference
- CHERRY_PICKED_METRIC: PUE without fleet/average qualifier
- WATER_ACCOUNTING_VAGUE: water positive/neutral/replenish language
- FUTURE_PROMISE_NO_MILESTONE: future pledge without interim milestones
vagueness is 0-1 (higher = vaguer).

CLAIMS:
{items}

Output a JSON array with exactly one item per claim:
[{{"claim_id": "...", "label": "A|B|C|D", "confidence": 0.0-1.0, "reason": "one sentence"}}]"""


def fmt(c):
    return json.dumps({"claim_id": c["claim_id"], "text": c["text"],
                       "flags": c.get("flags", []), "vagueness": c.get("vagueness")},
                      ensure_ascii=False)


def label_batch(batch):
    prompt = PROMPT.format(company=batch[0]["company"],
                           items="\n".join(fmt(c) for c in batch))
    raw = ask(prompt, system=SYSTEM)
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.M).strip()
    try:
        out = json.loads(raw)
    except Exception as e:
        print(f"  parse fail: {e}")
        return {}
    res = {}
    for r in out:
        if not isinstance(r, dict) or r.get("label") not in LABELS:
            continue
        try:
            conf = min(max(float(r.get("confidence", 0)), 0.0), 1.0)
        except (TypeError, ValueError):
            conf = 0.0
        res[r.get("claim_id")] = {"label": r["label"], "confidence": conf,
                                  "reason": str(r.get("reason", ""))}
    return res


def main():
    claims = json.load(open("data/candidates.json"))

    # Batch within a company: class D (contradicted elsewhere) needs same-company context
    by_co = {}
    for c in claims:
        by_co.setdefault(c["company"], []).append(c)
    batches = [cs[i:i+BATCH] for cs in by_co.values() for i in range(0, len(cs), BATCH)]

    results = {}
    for i, b in enumerate(batches, 1):
        print(f"batch {i}/{len(batches)} ({b[0]['company']}, {len(b)} claims)")
        results.update(label_batch(b))

    # Retry any claim that came back without a label, one at a time
    missing = [c for c in claims if c["claim_id"] not in results]
    for c in missing:
        print(f"  retry {c['claim_id']}")
        results.update(label_batch([c]))

    for c in claims:
        r = results.get(c["claim_id"], {})
        c["llm_label"] = r.get("label")
        c["llm_confidence"] = r.get("confidence")
        c["llm_reason"] = r.get("reason", "")
    json.dump(claims, open("data/prelabels.json", "w"), ensure_ascii=False, indent=1)

    # No gold_label column: see the module docstring. This sheet is for reading the
    # model's pre-labels, not for recording human ones.
    path = "data/annotations.csv"
    cols = ["claim_id", "company", "text", "flags", "vagueness",
            "llm_label", "llm_reason"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for c in claims:
            w.writerow({"claim_id": c["claim_id"], "company": c["company"],
                        "text": c["text"], "flags": ";".join(c.get("flags", [])),
                        "vagueness": c.get("vagueness"),
                        "llm_label": c["llm_label"] or "",
                        "llm_reason": c["llm_reason"]})

    dist = Counter(c["llm_label"] or "UNLABELED" for c in claims)
    print(f"\n{len(claims)} claims -> data/prelabels.json, {path}")
    for k in ["A", "B", "C", "D", "UNLABELED"]:
        if dist[k]:
            print(f"  {k}: {dist[k]} ({dist[k] / len(claims) * 100:.1f}%)")


if __name__ == "__main__":
    main()
