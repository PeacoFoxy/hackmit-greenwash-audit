"""无标签证据：gold 没覆盖到的规则，是否指向语料里真实的系统性缺口。

Abualigah & Khader（2017）用 MAD 作为**无监督** fitness，在没有类别标签的情况下给特征
打分。我们已经有一个等价物 —— Track S 的 lift，所以不需要再引入一个优化算法，只需要把
它当 fitness 用：

  qualifier support(claim) = 该 claim 的内容词在 lift 表里的平均 lift

lift 低 = 这些词在语料里通常**不带**它该带的限定语（方法 / 口径 / 核验方）。若某终点触
发的 claim 普遍落在低分位，说明它指向的是一个系统性缺口，而不是偶发个例 —— 这条证据不
需要任何人工标注。

它不能替代 gold：低分位只说明"这类表述在本语料里普遍缺限定语"，不说明"标注者会判它为 C"。
"""
import json
from pathlib import Path

import numpy as np

from src.termstats import RE_TOKEN, STOPWORDS
from src.tree import TERMINALS, classify

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# 机制 → 它缺的那类限定语（term_risk.json 的表名）
QUALIFIER_OF = {
    "UNDISCLOSED_METHOD": "method_stated",
    "UNDISCLOSED_BOUNDARY": "scope_stated",
    "SELECTIVE_AGGREGATION": "baseline_stated",
    "UNDEFINED_TERM": "verifier_named",
}
MIN_TOKENS = 2       # 少于这么多词命中 lift 表的 claim 不参与打分


def lift_maps(table):
    return {q: {r["term"]: r["lift"] for r in rows} for q, rows in table["terms"].items()}


def support(text, lut):
    """claim 的 qualifier support：内容词平均 lift。命中太少返回 None。"""
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
        # 参照分布：全语料在同一张 lift 表下的 support
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

    print("未标注证据：每条 C 规则触发的 claim 在语料 qualifier-support 分布中的位置\n")
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
