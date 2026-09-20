"""Track S -- the statistical layer. Learns term x qualifier lift from the 4,084-sentence
corpus. Zero LLM calls.

lift(t, Q) = P(Q | t) / P(Q). A lift below 1 means that when this term appears, the
qualifier is systematically absent. That is a statistical property of the corpus, not a
rule anyone wrote.
"""
import json
import re
from collections import Counter
from pathlib import Path

from src.tree import (RE_BASELINE, RE_METHOD, RE_SCOPE, RE_VERIFIER, route_domain)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

MIN_COUNT = 5        # minimum occurrences to enter the lift table
REPORT_COUNT = 10    # minimum occurrences before printing or drawing a conclusion
MAX_N = 3

QUALIFIERS = {
    "method_stated": RE_METHOD,
    "baseline_stated": RE_BASELINE,
    "scope_stated": RE_SCOPE,
    "verifier_named": RE_VERIFIER,
}

# Each qualifier class is scored only within the sub-corpus on its own topic. Otherwise
# the base rate is tiny (method_stated is just 0.83%), every word unrelated to the topic
# lands at lift=0 automatically, and the ranking measures "does not discuss this topic"
# rather than "lacks the qualifier".
TOPIC = {
    "method_stated": re.compile(
        r"\belectricity\b|\benergy\b|\bpower\b|\brenewable\w*|\bclean\s+power\b", re.I),
    "baseline_stated": re.compile(
        r"\d+(?:\.\d+)?\s*(?:%|percent)|\breduc\w*|\bdecreas\w*|\bincreas\w*", re.I),
    "scope_stated": re.compile(
        r"\bemissions?\b|\bcarbon\b|\bCO2e?\b|\bGHG\b|\bgreenhouse\s+gas\b", re.I),
    "verifier_named": re.compile(r"\d", re.I),
}

# Qualifier classes relevant to each domain (sec. 5, per-claim risk)
DOMAIN_QUALIFIERS = {
    "energy": ["method_stated"],
    "emissions": ["scope_stated", "baseline_stated"],
    "water": ["verifier_named"],
    "waste": ["scope_stated"],
    "efficiency": ["scope_stated", "verifier_named"],
    "other": ["verifier_named"],
    "other_capacity": ["verifier_named"],
}

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "at", "for", "with", "by",
    "from", "as", "is", "are", "was", "were", "be", "been", "being", "we", "our", "us", "it",
    "its", "this", "that", "these", "those", "their", "they", "them", "has", "have", "had",
    "will", "would", "can", "could", "may", "might", "also", "more", "than", "which", "when",
    "while", "all", "each", "other", "such", "into", "over", "about", "through", "s",
}

RE_TOKEN = re.compile(r"[a-z][a-z0-9-]+")
RE_HAS_DIGIT = re.compile(r"\d")


def tokens(text):
    return RE_TOKEN.findall(text.lower())


def ngrams(toks, n):
    """n-grams whose first and last word are not stopwords (keeps out things like 'of the')."""
    for i in range(len(toks) - n + 1):
        g = toks[i:i + n]
        if g[0] in STOPWORDS or g[-1] in STOPWORDS:
            continue
        if n == 1 and g[0] in STOPWORDS:
            continue
        yield " ".join(g)


def build_table(sentences):
    """Returns {term: {count, lift/cooc/in_topic: {Q: ...}}}; each qualifier class is
    computed inside its own topic sub-corpus."""
    term_sents = {}
    for i, s in enumerate(sentences):
        toks = tokens(s)
        seen = set()
        for n in range(1, MAX_N + 1):
            seen.update(ngrams(toks, n))
        # sorted(), not the set itself: Python randomises string hashing per process,
        # so iterating `seen` would give term_sents a different insertion order on every
        # run, and that order leaks into any downstream tie-break.
        for t in sorted(seen):
            term_sents.setdefault(t, []).append(i)

    base, table = {}, {}
    for q, qrx in QUALIFIERS.items():
        # The sub-corpus also requires a number: a qualifier is only expected when a
        # figure is being reported, so narrative sentences should not enter the denominator
        topic = [i for i, s in enumerate(sentences)
                 if TOPIC[q].search(s) and RE_HAS_DIGIT.search(s)]
        tset = set(topic)
        hits = {i: bool(qrx.search(sentences[i])) for i in topic}
        base[q] = (sum(hits.values()) / len(topic)) if topic else 0.0

        for t, idxs in term_sents.items():
            inside = [i for i in idxs if i in tset]
            if len(inside) < MIN_COUNT:
                continue
            row = table.setdefault(t, {"count": len(idxs), "lift": {}, "cooc": {},
                                       "in_topic": {}})
            c = sum(hits[i] for i in inside)
            row["cooc"][q] = c
            row["in_topic"][q] = len(inside)
            row["lift"][q] = round((c / len(inside)) / base[q], 4) if base[q] else None
    return table, base, len(sentences)


def risk(text, table, domain=None):
    """Per-claim risk (sec. 5): mean of (1 - min(lift, 1)) over the claim's terms, across
    the qualifiers relevant to its domain."""
    if domain is None:
        domain = route_domain(text)[1]
    qs = DOMAIN_QUALIFIERS.get(domain, ["verifier_named"])

    toks = tokens(text)
    present = set()
    for n in range(1, MAX_N + 1):
        present.update(g for g in ngrams(toks, n) if g in table)

    contrib, scores = [], []
    for t in sorted(present):
        for q in qs:
            lift = table[t]["lift"].get(q)
            if lift is None:
                continue
            scores.append(1 - min(lift, 1))
            contrib.append({"term": t, "lift": lift, "count": table[t]["count"], "qualifier": q})
    if not scores:
        return {"risk": None, "contributing_terms": []}
    contrib.sort(key=lambda c: c["lift"])
    return {"risk": round(sum(scores) / len(scores), 4),
            "contributing_terms": contrib[:5]}


def main():
    rows = json.loads((DATA / "signals.json").read_text(encoding="utf-8"))
    sentences = [r["text"] for r in rows]
    table, base, total = build_table(sentences)

    out = {"n_sentences": total, "min_count": MIN_COUNT,
           "base_rates": {q: round(b, 4) for q, b in base.items()},
           "terms": {}}
    for q in QUALIFIERS:
        # The term is the final key so the order is total. Without it, two terms tying
        # on both lift and in_topic kept dict order, which was hash-randomised, and the
        # file differed between runs on identical input.
        ranked = sorted(((t, r) for t, r in table.items() if r["lift"].get(q) is not None),
                        key=lambda kv: (kv[1]["lift"][q], -kv[1]["in_topic"][q], kv[0]))
        out["terms"][q] = [{"term": t, "lift": r["lift"][q], "count": r["count"],
                            "in_topic": r["in_topic"][q], "cooc": r["cooc"][q]}
                           for t, r in ranked]
    (DATA / "term_risk.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                         encoding="utf-8")

    print(f"{total} sentences, {len(table)} terms with count >= {MIN_COUNT}")
    print("base rates:", {q: round(b, 4) for q, b in base.items()})
    for q in QUALIFIERS:
        ranked = [r for r in out["terms"][q] if r["in_topic"] >= REPORT_COUNT][:20]
        print(f"\n--- lowest lift vs {q} (count >= {REPORT_COUNT}) ---")
        print(f"{'term':<34}{'lift':>7}{'in_topic':>10}{'cooc':>6}")
        for r in ranked:
            print(f"{r['term'][:33]:<34}{r['lift']:>7.2f}{r['in_topic']:>10}{r['cooc']:>6}")
    print("\n→ data/term_risk.json")


if __name__ == "__main__":
    main()
