"""Track S — 统计层。从 4,084 句语料学 term × qualifier 的 lift。零 LLM 调用。

lift(t, Q) = P(Q | t) / P(Q)。lift < 1 表示该词出现时，限定语系统性地不在场。
这是语料的统计属性，不是谁写的规则。
"""
import json
import re
from collections import Counter
from pathlib import Path

from src.tree import (RE_BASELINE, RE_METHOD, RE_SCOPE, RE_VERIFIER, route_domain)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

MIN_COUNT = 5        # 进入 lift 表的最低出现次数
REPORT_COUNT = 10    # 打印/下结论的最低出现次数
MAX_N = 3

QUALIFIERS = {
    "method_stated": RE_METHOD,
    "baseline_stated": RE_BASELINE,
    "scope_stated": RE_SCOPE,
    "verifier_named": RE_VERIFIER,
}

# 每类限定语只在相关话题的子语料里算 lift。否则基准率极低（method_stated 仅 0.83%），
# 任何与该话题无关的词都自动 lift=0，排名反映的是"不谈这个话题"而不是"缺少限定语"。
TOPIC = {
    "method_stated": re.compile(
        r"\belectricity\b|\benergy\b|\bpower\b|\brenewable\w*|\bclean\s+power\b", re.I),
    "baseline_stated": re.compile(
        r"\d+(?:\.\d+)?\s*(?:%|percent)|\breduc\w*|\bdecreas\w*|\bincreas\w*", re.I),
    "scope_stated": re.compile(
        r"\bemissions?\b|\bcarbon\b|\bCO2e?\b|\bGHG\b|\bgreenhouse\s+gas\b", re.I),
    "verifier_named": re.compile(r"\d", re.I),
}

# 各域相关的限定语类（§5 per-claim risk）
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
    """n-gram，首尾词不得为停用词（避免 'of the' 这类）。"""
    for i in range(len(toks) - n + 1):
        g = toks[i:i + n]
        if g[0] in STOPWORDS or g[-1] in STOPWORDS:
            continue
        if n == 1 and g[0] in STOPWORDS:
            continue
        yield " ".join(g)


def build_table(sentences):
    """返回 {term: {count, lift/cooc/in_topic: {Q: ...}}}，每类限定语在其话题子语料内计算。"""
    term_sents = {}
    for i, s in enumerate(sentences):
        toks = tokens(s)
        seen = set()
        for n in range(1, MAX_N + 1):
            seen.update(ngrams(toks, n))
        for t in seen:
            term_sents.setdefault(t, []).append(i)

    base, table = {}, {}
    for q, qrx in QUALIFIERS.items():
        # 子语料再要求含数字：限定语只在报数时才被期待，叙述句不该进分母
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
    """§5 per-claim risk：claim 中出现的词，在相关限定语上 (1 - min(lift,1)) 的均值。"""
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
        ranked = sorted(((t, r) for t, r in table.items() if r["lift"].get(q) is not None),
                        key=lambda kv: (kv[1]["lift"][q], -kv[1]["in_topic"][q]))
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
