"""Track R — 规则决策树。零 LLM 调用。

每个节点标注 CLOSED / OPEN：CLOSED 表示概念有固定的术语表，正则未命中基本等于概念缺失；
OPEN 表示说法多样，未命中只是弱证据。标注本身预测该节点在哪里会与 track D 分歧。
"""
import json
import re
from collections import Counter, namedtuple

I = re.IGNORECASE
Node = namedtuple("Node", "reliability test yes no")

# terminal: (label, mechanism, severity)
TERMINALS = {
    "SKIP": ("SKIP", None, None),
    "VAGUE_NO_QUANTITY": ("B", None, None),

    "FUTURE_PROMISE_NO_MILESTONE": ("C", "UNDISCLOSED_BOUNDARY", 2),
    "TARGET_SCOPE_UNSTATED": ("C", "UNDISCLOSED_BOUNDARY", 2),
    "SUBSTANTIATED_TARGET": ("A", None, None),

    "MARKET_BASED_IMPLIED": ("C", "UNDISCLOSED_METHOD", 3),
    "INSTRUMENT_NO_METHOD": ("C", "UNDISCLOSED_METHOD", 3),
    "METHOD_UNSTATED": ("C", "UNDISCLOSED_METHOD", 2),
    "GRID_MISMATCH_RISK": ("C", "UNDISCLOSED_BOUNDARY", 2),
    "COVERAGE_UNSTATED": ("C", "UNDISCLOSED_BOUNDARY", 1),
    "SUBSTANTIATED_ENERGY": ("A", None, None),

    "SCOPE_UNSTATED": ("C", "UNDISCLOSED_BOUNDARY", 2),
    "INTENSITY_NO_ABSOLUTE": ("C", "SELECTIVE_AGGREGATION", 3),
    "NO_BASELINE_YEAR": ("C", "UNDISCLOSED_BOUNDARY", 2),
    "OFFSET_UNDISCLOSED": ("C", "UNDISCLOSED_METHOD", 3),
    "SUBSTANTIATED_EMISSIONS": ("A", None, None),

    "WATER_TERM_UNDEFINED": ("C", "UNDEFINED_TERM", 3),
    "WATER_BOUNDARY_UNSTATED": ("C", "UNDISCLOSED_BOUNDARY", 2),
    "SUBSTANTIATED_WATER": ("A", None, None),

    "DIVERSION_UNDEFINED": ("C", "UNDEFINED_TERM", 3),
    "WASTE_BOUNDARY_UNSTATED": ("C", "UNDISCLOSED_BOUNDARY", 2),
    "SUBSTANTIATED_WASTE": ("A", None, None),

    "PROPRIETARY_METRIC": ("C", "UNDEFINED_TERM", 3),
    "REGIONAL_ONLY": ("C", "SELECTIVE_AGGREGATION", 2),
    "CHERRY_PICKED_METRIC": ("C", "SELECTIVE_AGGREGATION", 3),
    "SUBSTANTIATED_METRIC": ("A", None, None),

    "UNSCOPED_FIGURE": ("C", "UNDISCLOSED_BOUNDARY", 1),
    "SUBSTANTIATED_OTHER": ("A", None, None),
}


def rx(p):
    return re.compile(p, I)


# --------------------------------------------------------------- 节点正则
RE_SELF = rx(r"\b(?:we|we'?re|our|us|microsoft|alphabet|google|amazon|aws)\b")
RE_ASSERT = rx(r"\b(?:reduc|achiev|deliver|match|power|offset|remov|eliminat|will|commit|"
               r"reach|maintain|operat|invest|contract|sourc|replenish|recycl|divert|avoid|"
               r"sign|run|ran|cut|increas|decreas)\w*")
# 报数句（"our X was 12%"）没有主张动词，但仍是自述业绩
RE_COPULA = rx(r"\b(?:was|were|is|are)\b|\breach(?:ed|es)\b|\btotal(?:ed|led|s)\b|"
               r"\bstood\s+at\b|\brepresents?\b|\bremains?\b")

RE_QUANTITY = rx(r"\d|\ball\b|\bevery\b|\bnone\b|\b100\s*%")
RE_FUTURE = rx(r"\bwill\b|\bby\s+20\d{2}\b|\baim(?:s|ing)?\s+to\b|\btarget(?:s|ing|ed)?\b|"
               r"\bplan(?:s|ning)?\s+to\b|\bexpect(?:s|ed|ing)?\b|\bcommit(?:s|ted|ting)?\s+to\b")
RE_MILESTONE = rx(r"\binterim\b|\bannual(?:ly)?\b|\beach\s+year\b|\bevery\s+year\b|"
                  r"\bmilestones?\b|\bthird[-\s]party\s+validated\b|\bSBTi\b")
RE_TWO_DATES = rx(r"\bby\s+20\d{2}\b.*\bby\s+20\d{2}\b")

# scope 既可以用 GHG Protocol 术语表达，也可以用一个明确命名的设施/业务边界表达
# （"data center emissions"、"our fleet"、"global operations"）。后者同样是可核对的口径，
# 只认前者会把 goog_sr_016 这类已说明边界的 claim 误判为 C。
RE_SCOPE = rx(r"\bscopes?\s*[123]\b|\bscope\s*1\s*(?:and|&|,)\s*2\b|\bdirect\s+operations\b|"
              r"\bvalue\s+chain\b|\bindirect\s+emissions\b|"
              r"\bdata\s?cent(?:er|re)s?\b|\bfleet[-\s]?wide\b|\bour\s+fleet\b|"
              r"\b(?:global|worldwide|company[-\s]wide)\s+operations\b|"
              r"\bowned\s+and\s+operated\b|\boperational\s+control\b")
RE_BASELINE = rx(r"\bbase(?:line)?\s+year\b|\bbaseline\b|"
                 r"\b(?:since|from|vs\.?|versus|compared\s+(?:to|with)|against|relative\s+to)\s+"
                 r"(?:our\s+|the\s+)?(?:19|20)\d{2}\b")
RE_PERCENT = rx(r"\d+(?:\.\d+)?\s*(?:%|percent)")
RE_CHANGE_VERB = rx(r"\b(?:reduc|decreas|increas|cut|lower|declin|drop|grew|grow)\w*")
RE_INTENSITY = rx(r"\bper\s+(?:unit|shipped|item|employee|dollar|customer|package|kwh|mwh|"
                  r"user|capita|\$)|\bintensity\b|\bnormalized\b")
RE_ABSOLUTE = rx(r"\b\d[\d,.]*\s*(?:mt|kt|t|tonnes?|tons?|metric\s+tons?)\s*(?:co2e?)?\b|"
                 r"\b\d[\d,.]*\s*(?:mt|mmt)?co2e\b|\babsolute\b")
RE_NEUTRAL = rx(r"\bcarbon[-\s]neutral(?:ity)?\b|\bnet[-\s]zero\b|\bclimate[-\s]neutral(?:ity)?\b")
RE_OFFSET = rx(r"\boffsets?\b|\boffsetting\b|\bremovals?\b|\bcredits?\b")

RE_METHOD = rx(r"\b(?:market|location)[-\s]based\b|\bgrid[-\s]supplied\b|"
               r"\bon[-\s]site\s+generation\b")
RE_MATCHING = rx(r"\bmatch(?:ed|ing|es)?\b|\bequivalent\s+to\b|\boffset\s+by\b")
RE_INSTRUMENT = rx(r"\bPPAs?\b|\bRECs?\b|\bpower\s+purchase\b|\bcertificates?\b|"
                   r"\benergy\s+attribute\b")
RE_GRID = rx(r"\bgrids?\b|\bregion(?:s|al|ally)?\b|\bISOs?\b|\bsame\s+market\b|\blocal(?:ly)?\b|"
             r"\b(?:north|south|latin)\s+america\b|\basia\s+pacific\b|\beurope\b|\bEMEA\b|"
             r"\bAPAC\b|\bPJM\b|\bERCOT\b|\bMISO\b")
RE_COVERAGE = rx(r"\bglobal(?:ly)?\b|\bfleet[-\s]?wide\b|\bfleet\b|\bportfolio\b|\bworldwide\b|"
                 r"\bcompany[-\s]wide\b|\bacross\s+all\b|\ball\s+(?:of\s+our\s+)?"
                 r"(?:facilities|sites|offices|data\s?centers?)\b|\bevery\s+(?:facility|site)\b")

RE_WATER_TERM = rx(r"\bwater[-\s]positive\b|\bwater[-\s]neutral(?:ity)?\b|\breplenish\w*|"
                   r"\brestor(?:e|ed|ing|ation)\b")
RE_WATER_METHOD = rx(r"\bmethodolog\w*|\bverif\w*|\bassur\w*|\bthird[-\s]party\b|\bcertif\w*|"
                     r"\bvolumetric\s+water\s+benefit\b|\bWRI\b")
RE_WATERSHED = rx(r"\bwatersheds?\b|\bbasins?\b|\bcatchments?\b|"
                  r"\bwater[-\s]stressed\s+(?:regions?|areas?)\b")

RE_WASTE_TERM = rx(r"\bdivert(?:ed|s|ing)?\b|\bdiversion\b|\bcircular(?:ity)?\b|"
                   r"\brecover(?:ed|y)\b|\brecycled\s+content\b")
RE_PATHWAY = rx(r"\bcompost\w*|\brecycl\w*|\bincinerat\w*|\benergy\s+recovery\b|\blandfill\b|"
                r"\banaerobic\s+digestion\b|\bdonation\w*|\breuse\b")
RE_WASTE_STREAM = rx(r"\b(?:food|plastic|packaging|construction|electronic|hazardous|municipal|"
                     r"office|organic|paper|textile)\s+waste\b|\be-?waste\b|\bwaste\s+from\s+\w+")

RE_EFFICIENCY = rx(r"\bPUE\b|\bWUE\b|\bCUE\b|\bCFE\b|\bcarbon[-\s]free\s+energy\s+"
                   r"(?:score|percentage|percent)\b|\befficiency\s+(?:metric|index|ratio)\b|"
                   r"\bindex\b")
RE_STANDARD_METRIC = rx(r"\bPUE\b|\bWUE\b|\bCUE\b")
RE_METRIC_DEFINED = rx(r"\bdefined\s+as\b|\bcalculated\s+as\b|\bratio\s+of\b|\bmethodolog\w*|"
                       r"\bsee\s+(?:appendix|definition)\b|\bmeasures?\s+the\b")
RE_REGIONAL = rx(r"\bin\s+(?:asia\s+pacific|north\s+america|latin\s+america|europe|EMEA|APAC)\b|"
                 r"\bregional\s+average\b|\bby\s+region\b|\bper[-\s]site\b|"
                 r"\bat\s+our\s+\w+\s+(?:facility|site|campus)\b")

RE_VERIFIER = rx(r"\bthird[-\s]party\b|\bassur\w*|\bverif\w*|\baudit\w*|\bcertif\w*|"
                 r"\bvalidated\s+by\b|\bSBTi\b|\bCDP\b")
RE_PERIOD = rx(r"\bin\s+(?:19|20)\d{2}\b|\bfiscal\s+year\b|\bFY\s?\d{2,4}\b|"
               r"\bas\s+of\s+(?:19|20)\d{2}\b")

RE_D_EFFICIENCY = RE_EFFICIENCY
RE_D_WASTE = rx(r"\bwaste\b|\brecycl\w*|\blandfill\b|\bdivert\w*|\bcircular(?:ity)?\b|"
                r"\bpackaging\b")
RE_D_WATER = rx(r"\bwater\b|\bwatersheds?\b|\breplenish\w*")
RE_D_EMISSIONS = rx(r"\bemissions?\b|\bcarbon\b|\bCO2e?\b|\bGHG\b|\bgreenhouse\s+gas\b|"
                    r"\bnet[-\s]zero\b")
RE_D_ENERGY = rx(r"\belectricity\b|\benergy\b|\bpower(?:ed|ing)?\b|\brenewables?\b")
# 只报装机容量（GW/MW，非 Wh）而无用电口径 → 采购事实，不是 Scope 2 核算问题
RE_CAPACITY_ONLY = rx(r"\d[\d,.]*\s*(?:GW|MW)\b(?!h)")
RE_ENERGY_USE = rx(r"\bconsum\w*|\bused?\b|\busage\b|\bpowered\s+by\b|\bran\s+on\b|"
                   r"\bruns?\s+on\b|\bmatch\w*|\b(?:M|G|T|k)Wh\b|\bsourced\b|\bprocure\w*")


# --------------------------------------------------------------- 节点测试
def t0(t):
    m = RE_SELF.search(t)
    if not m:
        return None
    if RE_ASSERT.search(t):
        return m
    return m if (RE_COPULA.search(t) and RE_QUANTITY.search(t)) else None


def t6b_percent_no_baseline(t):
    """T6b: 给了百分比变化却没有基准年 → yes 走 NO_BASELINE_YEAR。"""
    if RE_PERCENT.search(t) and RE_CHANGE_VERB.search(t):
        return None if RE_BASELINE.search(t) else RE_PERCENT.search(t)
    return None


NODES = {
    "T0":   Node("OPEN",   t0, "T1", "SKIP"),
    "T1":   Node("CLOSED", RE_QUANTITY.search, "T2", "VAGUE_NO_QUANTITY"),
    "T2":   Node("CLOSED", RE_FUTURE.search, "T3", "T4"),

    "T3":   Node("OPEN",   lambda t: RE_MILESTONE.search(t) or RE_TWO_DATES.search(t),
                 "T3a", "FUTURE_PROMISE_NO_MILESTONE"),
    "T3a":  Node("OPEN",   lambda t: RE_SCOPE.search(t) or RE_BASELINE.search(t)
                 or RE_COVERAGE.search(t), "SUBSTANTIATED_TARGET", "TARGET_SCOPE_UNSTATED"),

    "T5":   Node("CLOSED", RE_METHOD.search, "T5c", "T5a"),
    "T5a":  Node("CLOSED", RE_MATCHING.search, "MARKET_BASED_IMPLIED", "T5b"),
    "T5b":  Node("CLOSED", RE_INSTRUMENT.search, "INSTRUMENT_NO_METHOD", "METHOD_UNSTATED"),
    "T5c":  Node("OPEN",   RE_GRID.search, "T5d", "GRID_MISMATCH_RISK"),
    "T5d":  Node("OPEN",   RE_COVERAGE.search, "SUBSTANTIATED_ENERGY", "COVERAGE_UNSTATED"),

    # 按严重度排序（§7）：INTENSITY(3) 在 SCOPE(2) 之前，否则 §10 第 5 条用例无法通过
    "T6":   Node("CLOSED", RE_INTENSITY.search, "T6a2", "T6s"),
    "T6a2": Node("OPEN",   RE_ABSOLUTE.search, "T6s", "INTENSITY_NO_ABSOLUTE"),
    "T6s":  Node("CLOSED", RE_SCOPE.search, "T6b", "SCOPE_UNSTATED"),
    "T6b":  Node("OPEN",   t6b_percent_no_baseline, "NO_BASELINE_YEAR", "T6c"),
    "T6c":  Node("CLOSED", RE_NEUTRAL.search, "T6c2", "SUBSTANTIATED_EMISSIONS"),
    "T6c2": Node("OPEN",   RE_OFFSET.search, "SUBSTANTIATED_EMISSIONS", "OFFSET_UNDISCLOSED"),

    "T7":   Node("CLOSED", RE_WATER_TERM.search, "T7m", "T7a"),
    "T7m":  Node("OPEN",   RE_WATER_METHOD.search, "SUBSTANTIATED_WATER", "WATER_TERM_UNDEFINED"),
    "T7a":  Node("OPEN",   lambda t: RE_WATERSHED.search(t) or RE_COVERAGE.search(t),
                 "SUBSTANTIATED_WATER", "WATER_BOUNDARY_UNSTATED"),

    "T8":   Node("CLOSED", RE_WASTE_TERM.search, "T8a", "T8b"),
    "T8a":  Node("CLOSED", RE_PATHWAY.search, "T8b", "DIVERSION_UNDEFINED"),
    "T8b":  Node("OPEN",   lambda t: RE_WASTE_STREAM.search(t) or RE_COVERAGE.search(t),
                 "SUBSTANTIATED_WASTE", "WASTE_BOUNDARY_UNSTATED"),

    "T9":   Node("OPEN",   lambda t: (RE_EFFICIENCY.search(t)
                                      if not RE_STANDARD_METRIC.search(t) else None),
                 "T9d", "T9a"),
    "T9d":  Node("OPEN",   RE_METRIC_DEFINED.search, "T9a", "PROPRIETARY_METRIC"),
    "T9a":  Node("OPEN",   RE_COVERAGE.search, "SUBSTANTIATED_METRIC", "T9b"),
    "T9b":  Node("OPEN",   RE_REGIONAL.search, "REGIONAL_ONLY", "CHERRY_PICKED_METRIC"),

    "T10":  Node("OPEN",   RE_VERIFIER.search, "SUBSTANTIATED_OTHER", "T10a"),
    "T10a": Node("OPEN",   lambda t: RE_COVERAGE.search(t) or RE_PERIOD.search(t)
                 or RE_GRID.search(t), "SUBSTANTIATED_OTHER", "UNSCOPED_FIGURE"),
}


def route_domain(t):
    """T4 [CLOSED] 域路由。优先级处理同句多域共现：
    efficiency 先于 energy（§6 明确），waste/water 先于 energy（"energy recovery"），
    emissions 先于 energy（"energy emissions" 的口径问题是 scope，不是 method）。"""
    if RE_D_EFFICIENCY.search(t):
        return "T9", "efficiency"
    if RE_D_WASTE.search(t):
        return "T8", "waste"
    if RE_D_WATER.search(t):
        return "T7", "water"
    if RE_D_EMISSIONS.search(t):
        return "T6", "emissions"
    if RE_D_ENERGY.search(t):
        if RE_CAPACITY_ONLY.search(t) and not RE_ENERGY_USE.search(t):
            return "T10", "other_capacity"  # 装机容量，不是用电核算
        return "T5", "energy"
    return "T10", "other"


DOMAIN_OF_NODE = {"T5": "energy", "T6": "emissions", "T7": "water",
                  "T8": "waste", "T9": "efficiency", "T10": "other"}


# ------------------------------------------------- 交叉核查（cross-check）
# 结构借自 Hicks 等（PMC11404377）：模型先标，再由负责该类别的一方逐条核查并修正。
# 这里的"负责人"是每个机制自己的独立检查器：树说某项披露缺失，检查器反过来问
# "这项披露真的不在句子里吗"。命中就撤销 C，并把撤销理由记进路径。
RE_METHOD_ANY = rx(r"\b(?:market|location)[-\s]based\b|\bgrid[-\s]supplied\b|"
                   r"\bon[-\s]site\s+(?:solar|wind|generation)\b|"
                   r"\bretired\s+(?:RECs?|certificates?)\b|\bhourly\s+match\w*|"
                   r"\b24/7\s+carbon[-\s]free\b")
RE_BOUNDARY_ANY = rx(r"\bscopes?\s*[123]\b|\bdata\s?cent(?:er|re)s?\b|\bfleet\b|"
                     r"\bportfolio\b|\bglobal(?:ly)?\b|\bworldwide\b|"
                     r"\ball\s+(?:of\s+our\s+)?(?:facilities|sites|operations)\b|"
                     r"\bdirect\s+operations\b|\bvalue\s+chain\b|"
                     r"\bowned\s+and\s+operated\b|\boperational\s+control\b")
RE_ABSOLUTE_ANY = rx(r"\b\d[\d,.]*\s*(?:mt|kt|t|tonnes?|tons?|metric\s+tons?|MWh|GWh|"
                     r"TWh|liters?|litres?|gallons?)\b|\babsolute\b|"
                     r"\btotal\s+\w*\s?emissions\b")
RE_DEFINITION_ANY = rx(r"\bdefined\s+as\b|\bcalculated\s+as\b|\bmethodolog\w*|"
                       r"\bratio\s+of\b|\bmeasures?\s+the\b|\bGHG\s+Protocol\b|"
                       r"\bin\s+line\s+with\s+\w+\s+guidance\b")

CROSS_CHECKS = {
    "UNDISCLOSED_METHOD": ("method is stated in other words", RE_METHOD_ANY),
    "UNDISCLOSED_BOUNDARY": ("coverage is stated in other words", RE_BOUNDARY_ANY),
    "SELECTIVE_AGGREGATION": ("an absolute or fleet-wide figure is present", RE_ABSOLUTE_ANY),
    "UNDEFINED_TERM": ("the term is defined or a methodology is referenced",
                       RE_DEFINITION_ANY),
}

# sev 3 的终点是术语事实（matched / 只报强度），不接受撤销；只核查 sev 1-2。
CROSS_CHECK_MAX_SEVERITY = 2

# 默认关闭。2026-09-20 在 29 条 gold 上实测（窗口 ±1/±3/±5）：
#   关闭    acc 0.793  C_spec 0.737  C_rec 1.000  C_BA 0.868
#   ±1 句   acc 0.724  C_spec 0.842  C_rec 0.800  C_BA 0.821   撤销 4 条，0 条正确
#   ±5 句   acc 0.655  C_spec 0.895  C_rec 0.500  C_BA 0.697   撤销 8 条，1 条正确
# specificity 上升但 recall 掉得更快。原因：报告里 global / data centers / our operations
# 这类口径词每隔几句就出现一次，"出现在附近"不等于"绑定到这个数字" —— 而这正是 C 类
# 要抓的误导形态。保留实现与数据，供扩大语料后复测。
CROSS_CHECK_ENABLED = False


def cross_check(text, terminal, context=None):
    """返回 (是否撤销, 理由, 命中片段)。只对 C 且 severity <= 2 的终点生效。

    核查的输入必须与树不同，否则只是换一组同义词重读同一句（实测 390 条里 0 次触发）。
    这里用的是**文档上下文**：句级的树看不到前后文，但读者看得到 —— 如果被指缺失的口径
    就写在邻近句子里，那它并没有缺失。context 为空时退化为不撤销。
    """
    label, mechanism, severity = TERMINALS[terminal]
    if label != "C" or severity is None or severity > CROSS_CHECK_MAX_SEVERITY:
        return False, None, None
    if not context or not CROSS_CHECK_ENABLED:
        return False, None, None
    reason, rx_check = CROSS_CHECKS.get(mechanism, (None, None))
    if not rx_check:
        return False, None, None
    m = rx_check.search(context)
    return (bool(m), reason, m.group(0) if m else None)


def classify(text, claim_id=None, context=None):
    """从 T0 遍历到终点，返回 §8 的 track_R 结构。

    context 是这句话在原文里的邻近段落（前后各若干句）。给了就启用交叉核查。
    """
    path, node, domain = [], "T0", None
    while node not in TERMINALS:
        n = NODES[node]
        m = n.test(text)
        hit = bool(m)
        step = {"node": node, "reliability": n.reliability, "answer": "yes" if hit else "no"}
        if hit and hasattr(m, "group"):
            step["span"] = m.group(0)
        path.append(step)
        node = n.yes if hit else n.no
        if node == "T4":
            node, domain = route_domain(text)
            path.append({"node": "T4", "reliability": "CLOSED", "answer": domain})

    label, mechanism, severity = TERMINALS[node]

    cleared, reason, span = cross_check(text, node, context)
    if cleared:
        path.append({"node": "XC", "reliability": "OPEN", "answer": "cleared",
                     "span": span, "reason": reason})
        label = "A"

    return {"claim_id": claim_id, "label": label, "terminal": node,
            "cross_checked": cleared, "cross_check_reason": reason,
            "mechanism": mechanism, "severity": severity,
            "domain": domain or DOMAIN_OF_NODE.get(path[-1]["node"][:2]),
            "decided_by": path[-1]["reliability"], "path": path}


def main():
    claims = json.load(open("data/flagged.json"))
    out = [classify(c["text"], c["claim_id"]) for c in claims]
    json.dump(out, open("data/track_r.json", "w"), ensure_ascii=False, indent=1)

    print(f"{len(out)} claims → data/track_r.json")
    print("\nlabel:", dict(Counter(r["label"] for r in out)))
    print("mechanism:", dict(Counter(r["mechanism"] for r in out if r["mechanism"])))
    print("\nterminal:")
    for t, n in Counter(r["terminal"] for r in out).most_common():
        lab, mech, sev = TERMINALS[t]
        print(f"  {t:<30}{n:>4}  {lab}  sev {sev if sev else '-'}  {mech or ''}")


if __name__ == "__main__":
    main()
