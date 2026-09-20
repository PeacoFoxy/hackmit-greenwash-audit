"""规则层 v2：有序决策树，替代 v1 的扁平 flag 集合。

每条 claim 走到唯一终点，终点带 label / mechanism / severity，root 到 leaf 的路径即解释。
所有节点测试都是纯正则，语义判断留给下游 LLM。
"""
import json
import re

I = re.IGNORECASE

# ---------------------------------------------------------------- 终点定义
# name: (label, mechanism, severity)
TERMINALS = {
    "SKIP": ("SKIP", None, None),
    "VAGUE_NO_QUANTITY": ("B", None, None),

    # T3 目标分支
    "FUTURE_PROMISE_NO_MILESTONE": ("C", "UNDISCLOSED_BOUNDARY", 2),
    "TARGET_SCOPE_UNSTATED": ("C", "UNDISCLOSED_BOUNDARY", 2),
    "SUBSTANTIATED_TARGET": ("A", None, None),

    # T5 能源与电力
    "MARKET_BASED_IMPLIED": ("C", "UNDISCLOSED_METHOD", 3),
    "INSTRUMENT_NO_METHOD": ("C", "UNDISCLOSED_METHOD", 3),
    "METHOD_UNSTATED": ("C", "UNDISCLOSED_METHOD", 2),
    "GRID_MISMATCH_RISK": ("C", "UNDISCLOSED_BOUNDARY", 2),
    "COVERAGE_UNSTATED": ("C", "UNDISCLOSED_BOUNDARY", 1),
    "SUBSTANTIATED_ENERGY": ("A", None, None),

    # T6 排放
    "INTENSITY_NO_ABSOLUTE": ("C", "SELECTIVE_AGGREGATION", 3),
    "OFFSET_UNDISCLOSED": ("C", "UNDISCLOSED_METHOD", 3),
    "SCOPE_UNSTATED": ("C", "UNDISCLOSED_BOUNDARY", 2),
    "NO_BASELINE_YEAR": ("C", "UNDISCLOSED_BOUNDARY", 2),
    "SUBSTANTIATED_EMISSIONS": ("A", None, None),

    # T7 水
    "WATER_TERM_UNDEFINED": ("C", "UNDEFINED_TERM", 3),
    "WATER_BOUNDARY_UNSTATED": ("C", "UNDISCLOSED_BOUNDARY", 2),
    "SUBSTANTIATED_WATER": ("A", None, None),

    # T8 废弃物
    "DIVERSION_UNDEFINED": ("C", "UNDEFINED_TERM", 3),
    "WASTE_BOUNDARY_UNSTATED": ("C", "UNDISCLOSED_BOUNDARY", 2),
    "SUBSTANTIATED_WASTE": ("A", None, None),

    # T9 效率与复合指标
    "PROPRIETARY_METRIC": ("C", "UNDEFINED_TERM", 3),
    "REGIONAL_ONLY": ("C", "SELECTIVE_AGGREGATION", 2),
    "CHERRY_PICKED_METRIC": ("C", "SELECTIVE_AGGREGATION", 3),
    "SUBSTANTIATED_METRIC": ("A", None, None),

    # T10 其他
    "UNSCOPED_FIGURE": ("C", "UNDISCLOSED_BOUNDARY", 1),
    "SUBSTANTIATED_OTHER": ("A", None, None),
}


def rx(pattern):
    return re.compile(pattern, I)


# ---------------------------------------------------------------- 节点正则
RE_SELF = rx(r"\b(?:we|we'?re|our|us|microsoft|alphabet|google|amazon|aws)\b")
RE_ASSERT = rx(r"\b(?:reduc|achiev|deliver|match|power|offset|remov|eliminat|will|commit|"
               r"reach|maintain|operat|invest|contract|sourc|replenish|recycl|divert|avoid|"
               r"sign|run|ran|cut|increas|decreas|divert)\w*")

RE_COPULA = rx(r"\b(?:was|were|is|are)\b|\breach(?:ed|es)\b|\btotal(?:ed|led|s)\b|"
               r"\bstood\s+at\b|\brepresents?\b|\bremains?\b")
RE_QUANTITY = rx(r"\d|\ball\b|\bevery\b|\bnone\b|\b100\s*%")
RE_FUTURE = rx(r"\bwill\b|\bby\s+20\d{2}\b|\baim(?:s|ing)?\s+to\b|\btarget(?:s|ing|ed)?\b|"
               r"\bplan(?:s|ning)?\s+to\b|\bexpect(?:s|ed|ing)?\b")
RE_MILESTONE = rx(r"\binterim\b|\bannual(?:ly)?\b|\beach\s+year\b|\bevery\s+year\b|"
                  r"\bmilestones?\b|\bthird[-\s]party\s+validated\b|\bSBTi\b")
RE_TWO_DATES = rx(r"\bby\s+20\d{2}\b.*\bby\s+20\d{2}\b")

RE_SCOPE = rx(r"\bscopes?\s*[123]\b|\bscope\s*1\s*(?:and|&|,)\s*2\b|\bdirect\s+operations\b|"
              r"\bvalue\s+chain\b|\bindirect\s+emissions\b")
RE_BASELINE = rx(r"\bbase(?:line)?\s+year\b|\bbaseline\b|"
                 r"\b(?:since|from|vs\.?|versus|compared\s+(?:to|with)|against|relative\s+to)\s+"
                 r"(?:our\s+|the\s+)?(?:19|20)\d{2}\b")
RE_PERCENT_CHANGE = rx(r"\d+(?:\.\d+)?\s*(?:%|percent)")
RE_CHANGE_VERB = rx(r"\b(?:reduc|decreas|increas|cut|lower|declin|drop|grew|grow)\w*")
RE_INTENSITY = rx(r"\bper\s+(?:unit|shipped|item|employee|dollar|customer|package|"
                  r"kwh|mwh|user|capita|\$)|\bintensity\b|\bnormalized\b|\bper\s+\w+\s+unit\b")
RE_ABSOLUTE = rx(r"\b\d[\d,.]*\s*(?:mt|kt|t|tonnes?|tons?|metric\s+tons?)\s*(?:co2e?)?\b|"
                 r"\b\d[\d,.]*\s*(?:mt|mmt)?co2e\b|\babsolute\b")
RE_NEUTRAL = rx(r"\bcarbon[-\s]neutral(?:ity)?\b|\bnet[-\s]zero\b|\bclimate[-\s]neutral(?:ity)?\b")
RE_OFFSET_DISCLOSED = rx(r"\boffsets?\b|\boffsetting\b|\bremovals?\b|\bcredits?\b|"
                         r"\bwithout\s+offsets?\b")

RE_METHOD = rx(r"\b(?:market|location)[-\s]based\b|\bgrid[-\s]supplied\b|\bon[-\s]site\s+generation\b")
RE_MATCHING = rx(r"\bmatch(?:ed|ing|es)?\b|\bpurchas\w+[^.]{0,40}\bequivalent\b|\boffset\s+by\b")
RE_INSTRUMENT = rx(r"\bPPAs?\b|\bRECs?\b|\bpower\s+purchase\b|\bcertificates?\b|"
                   r"\benergy\s+attribute\b")
RE_GRID = rx(r"\bgrids?\b|\bregion(?:s|al|ally)?\b|\bISOs?\b|\bsame\s+market\b|\blocal(?:ly)?\b|"
             r"\b(?:north|south|latin)\s+america\b|\basia\s+pacific\b|\beurope\b|\bEMEA\b|"
             r"\bAPAC\b|\bPJM\b|\bERCOT\b|\bMISO\b")
RE_COVERAGE = rx(r"\bglobal(?:ly)?\b|\bfleet[-\s]?wide\b|\bfleet\b|\ball\s+(?:of\s+our\s+)?"
                 r"(?:facilities|sites|offices|data\s?centers?)\b|\bportfolio\b|\bworldwide\b|"
                 r"\bcompany[-\s]wide\b|\bacross\s+all\b|\bevery\s+(?:facility|site)\b")

RE_WATER_TERM = rx(r"\bwater[-\s]positive\b|\bwater[-\s]neutral(?:ity)?\b|\breplenish\w*|"
                   r"\brestor(?:e|ed|ing|ation)\b")
RE_WATER_METHOD = rx(r"\bmethodolog\w*|\bverif\w*|\bassur\w*|\bthird[-\s]party\b|"
                     r"\bVolumetric\s+Water\s+Benefit\b|\bWRI\b|\bcertif\w*")
RE_WATERSHED = rx(r"\bwatersheds?\b|\bbasins?\b|\bcatchments?\b|\bwater[-\s]stressed\s+"
                  r"(?:regions?|areas?)\b")

RE_WASTE_TERM = rx(r"\bdivert(?:ed|s|ing)?\b|\bdiversion\b|\bcircular(?:ity)?\b|"
                   r"\brecover(?:ed|y)\b|\brecycled\s+content\b")
RE_PATHWAY = rx(r"\bcompost\w*|\brecycl\w*|\bincinerat\w*|\benergy\s+recovery\b|\blandfill\b|"
                r"\banaerobic\s+digestion\b|\bdonation\w*|\breuse\b")
RE_WASTE_STREAM = rx(r"\b(?:food|plastic|packaging|construction|electronic|hazardous|municipal|"
                     r"office|organic|paper|textile)\s+waste\b|\be-?waste\b|"
                     r"\bwaste\s+from\s+\w+")

RE_EFFICIENCY = rx(r"\bPUE\b|\bWUE\b|\bCUE\b|\bCFE\b|\bcarbon[-\s]free\s+energy\s+(?:score|"
                   r"percentage|percent)\b|\befficiency\s+(?:metric|index|ratio)\b")
STANDARD_METRICS = rx(r"\bPUE\b|\bWUE\b|\bCUE\b")
RE_METRIC_DEFINED = rx(r"\bdefined\s+as\b|\bmeasures?\b|\bcalculated\s+as\b|\bratio\s+of\b|"
                       r"\bmethodolog\w*|\bsee\s+(?:appendix|definition)\b")
RE_REGIONAL_SLICE = rx(r"\bin\s+(?:asia\s+pacific|north\s+america|latin\s+america|europe|EMEA|"
                       r"APAC)\b|\bregional\s+average\b|\bby\s+region\b|\bper[-\s]site\b|"
                       r"\bat\s+our\s+\w+\s+(?:facility|site|campus)\b")

RE_VERIFIER = rx(r"\bthird[-\s]party\b|\bassur\w*|\bverif\w*|\baudit\w*|\bcertif\w*|"
                 r"\bvalidated\s+by\b|\bSBTi\b|\bCDP\b")
RE_PERIOD = rx(r"\bin\s+(?:19|20)\d{2}\b|\bfiscal\s+year\b|\bFY\s?\d{2,4}\b|"
               r"\b(?:19|20)\d{2}\s+(?:report|data)\b|\bas\s+of\s+(?:19|20)\d{2}\b")

RE_DOMAIN_WATER = rx(r"\bwater\b|\bwatersheds?\b|\breplenish\w*")
RE_DOMAIN_WASTE = rx(r"\bwaste\b|\brecycl\w*|\blandfill\b|\bdivert\w*|\bpackaging\b|"
                     r"\bcircular(?:ity)?\b")
RE_DOMAIN_EMISSIONS = rx(r"\bemissions?\b|\bcarbon\s+footprint\b|\bGHG\b|\bgreenhouse\s+gas\b|"
                         r"\bCO2e?\b|\bnet[-\s]zero\b|\bcarbon[-\s]neutral\w*")
RE_DOMAIN_ENERGY = rx(r"\belectricity\b|\benergy\b|\bpower(?:ed|ing)?\b|\brenewables?\b|"
                      r"\bclean\s+power\b")
# 只报装机容量（GW/MW）而非用电量，属于采购/建设事实，不是 Scope 2 核算口径问题
RE_CAPACITY_ONLY = rx(r"\d[\d,.]*\s*(?:GW|MW)\b(?!h)")
RE_ENERGY_USE = rx(r"\bconsum\w*|\bused?\b|\busage\b|\bpowered\s+by\b|\bran\s+on\b|\bruns?\s+on\b|"
                   r"\bmatch\w*|\bMWh\b|\bGWh\b|\bTWh\b|\bkWh\b|\bsourced\b|\bprocure\w*")


# ---------------------------------------------------------------- 节点测试
def t0_self(t):
    """自指 + 主张动词；报数句（"our X was 12%"）用系动词 + 数量同样算自述业绩。"""
    m = RE_SELF.search(t)
    if not m:
        return None
    if RE_ASSERT.search(t):
        return m
    if RE_COPULA.search(t) and RE_QUANTITY.search(t):
        return m
    return None


def t1_quantity(t):
    return RE_QUANTITY.search(t)


def t2_future(t):
    return RE_FUTURE.search(t)


def t3_milestone(t):
    return RE_MILESTONE.search(t) or RE_TWO_DATES.search(t)


def t3a_scope_or_baseline(t):
    return RE_SCOPE.search(t) or RE_BASELINE.search(t) or RE_COVERAGE.search(t)


def t5_method(t):
    return RE_METHOD.search(t)


def t5a_matching(t):
    return RE_MATCHING.search(t)


def t5b_instrument(t):
    return RE_INSTRUMENT.search(t)


def t5c_grid(t):
    return RE_GRID.search(t)


def t5d_coverage(t):
    return RE_COVERAGE.search(t)


def t6_intensity(t):
    return RE_INTENSITY.search(t)


def t6_absolute(t):
    return RE_ABSOLUTE.search(t)


def t6_neutral(t):
    return RE_NEUTRAL.search(t)


def t6_offset_disclosed(t):
    return RE_OFFSET_DISCLOSED.search(t)


def t6_scope(t):
    return RE_SCOPE.search(t)


def t6b_percent_change(t):
    return RE_PERCENT_CHANGE.search(t) if RE_CHANGE_VERB.search(t) else None


def t6b_baseline(t):
    return RE_BASELINE.search(t)


def t7_water_term(t):
    return RE_WATER_TERM.search(t)


def t7_water_method(t):
    return RE_WATER_METHOD.search(t)


def t7a_watershed(t):
    return RE_WATERSHED.search(t) or RE_COVERAGE.search(t)


def t8_waste_term(t):
    return RE_WASTE_TERM.search(t)


def t8_pathway(t):
    return RE_PATHWAY.search(t)


def t8a_stream(t):
    return RE_WASTE_STREAM.search(t) or RE_COVERAGE.search(t)


def t9_proprietary(t):
    m = RE_EFFICIENCY.search(t)
    return m if (m and not STANDARD_METRICS.search(t)) else None


def t9_defined(t):
    return RE_METRIC_DEFINED.search(t)


def t9a_fleetwide(t):
    return RE_COVERAGE.search(t)


def t9a_regional(t):
    return RE_REGIONAL_SLICE.search(t)


def t10_verifier(t):
    return RE_VERIFIER.search(t)


def t10a_boundary(t):
    return RE_COVERAGE.search(t) or RE_PERIOD.search(t) or RE_GRID.search(t)


def domain(t):
    """T4 域路由，按判定优先级排序（同一句可能多词共现）。"""
    if RE_DOMAIN_WATER.search(t) and not RE_DOMAIN_WASTE.search(t):
        return "T7", "water"
    if RE_DOMAIN_WASTE.search(t):
        return "T8", "waste"
    if RE_EFFICIENCY.search(t):
        return "T9", "efficiency"
    if RE_DOMAIN_EMISSIONS.search(t):
        return "T6", "emissions"
    if RE_DOMAIN_ENERGY.search(t):
        # 只有装机容量、没有用电量口径 → 不是 Scope 2 核算问题，走 T10
        if RE_CAPACITY_ONLY.search(t) and not RE_ENERGY_USE.search(t):
            return "T10", "other_capacity"
        return "T5", "energy"
    return "T10", "other"


# node_id: (test_fn, (yes_tag, yes_target), (no_tag, no_target))
NODES = {
    "T0": (t0_self, ("self", "T1"), ("not_self", "SKIP")),
    "T1": (t1_quantity, ("quantity", "T2"), ("no_quantity", "VAGUE_NO_QUANTITY")),
    "T2": (t2_future, ("forward_looking", "T3"), ("historical", "T4")),

    "T3": (t3_milestone, ("milestone", "T3a"), ("no_milestone", "FUTURE_PROMISE_NO_MILESTONE")),
    "T3a": (t3a_scope_or_baseline, ("scope_stated", "SUBSTANTIATED_TARGET"),
            ("scope_absent", "TARGET_SCOPE_UNSTATED")),

    "T5": (t5_method, ("method_stated", "T5c"), ("method_absent", "T5a")),
    "T5a": (t5a_matching, ("matching_language", "MARKET_BASED_IMPLIED"),
            ("no_matching", "T5b")),
    "T5b": (t5b_instrument, ("instrument_cited", "INSTRUMENT_NO_METHOD"),
            ("no_instrument", "METHOD_UNSTATED")),
    "T5c": (t5c_grid, ("grid_stated", "T5d"), ("grid_absent", "GRID_MISMATCH_RISK")),
    "T5d": (t5d_coverage, ("coverage_stated", "SUBSTANTIATED_ENERGY"),
            ("coverage_absent", "COVERAGE_UNSTATED")),

    # 按严重度排序：INTENSITY(3) → OFFSET(3) → SCOPE(2) → BASELINE(2)
    "T6": (t6_intensity, ("intensity", "T6i"), ("not_intensity", "T6n")),
    "T6i": (t6_absolute, ("absolute_given", "T6n"), ("absolute_absent", "INTENSITY_NO_ABSOLUTE")),
    "T6n": (t6_neutral, ("neutrality_claim", "T6o"), ("no_neutrality", "T6s")),
    "T6o": (t6_offset_disclosed, ("offsets_disclosed", "T6s"),
            ("offsets_undisclosed", "OFFSET_UNDISCLOSED")),
    "T6s": (t6_scope, ("scope_stated", "T6b"), ("scope_absent", "SCOPE_UNSTATED")),
    "T6b": (t6b_percent_change, ("percent_change", "T6c"),
            ("no_percent_change", "SUBSTANTIATED_EMISSIONS")),
    "T6c": (t6b_baseline, ("baseline_stated", "SUBSTANTIATED_EMISSIONS"),
            ("baseline_absent", "NO_BASELINE_YEAR")),

    "T7": (t7_water_term, ("composite_term", "T7m"), ("no_composite_term", "T7a")),
    "T7m": (t7_water_method, ("method_named", "SUBSTANTIATED_WATER"),
            ("method_absent", "WATER_TERM_UNDEFINED")),
    "T7a": (t7a_watershed, ("watershed_stated", "SUBSTANTIATED_WATER"),
            ("watershed_absent", "WATER_BOUNDARY_UNSTATED")),

    "T8": (t8_waste_term, ("diversion_term", "T8p"), ("no_diversion_term", "T8a")),
    "T8p": (t8_pathway, ("pathway_named", "T8a"), ("pathway_absent", "DIVERSION_UNDEFINED")),
    "T8a": (t8a_stream, ("stream_stated", "SUBSTANTIATED_WASTE"),
            ("stream_absent", "WASTE_BOUNDARY_UNSTATED")),

    "T9": (t9_proprietary, ("issuer_defined", "T9d"), ("industry_standard", "T9a")),
    "T9d": (t9_defined, ("definition_given", "T9a"), ("definition_absent", "PROPRIETARY_METRIC")),
    "T9a": (t9a_fleetwide, ("fleet_wide", "SUBSTANTIATED_METRIC"), ("not_fleet_wide", "T9r")),
    "T9r": (t9a_regional, ("regional_breakdown", "REGIONAL_ONLY"),
            ("no_breakdown", "CHERRY_PICKED_METRIC")),

    "T10": (t10_verifier, ("verifier_named", "SUBSTANTIATED_OTHER"), ("no_verifier", "T10a")),
    "T10a": (t10a_boundary, ("boundary_stated", "SUBSTANTIATED_OTHER"),
             ("boundary_absent", "UNSCOPED_FIGURE")),
}


def classify(text, claim_id=None):
    """从 T0 遍历到终点，返回输出契约里的 dict。"""
    path, span, node = [], None, "T0"
    while node not in TERMINALS:
        test, (yes_tag, yes_next), (no_tag, no_next) = NODES[node]
        m = test(text)
        if m is not None and m is not False:
            path.append(f"{node}:{yes_tag}")
            if hasattr(m, "group"):
                span = m.group(0)
            node = yes_next
        else:
            path.append(f"{node}:{no_tag}")
            node = no_next
        if node == "T4":  # 域路由不是二元节点，单独处理
            node, tag = domain(text)
            path.append(f"T4:{tag}")

    label, mechanism, severity = TERMINALS[node]
    return {"claim_id": claim_id, "label": label, "terminal": node,
            "mechanism": mechanism, "severity": severity,
            "path": path, "evidence_span": span}


def main():
    claims = json.load(open("data/flagged.json"))
    out = [classify(c["text"], c["claim_id"]) for c in claims]
    json.dump(out, open("data/tree_labels.json", "w"), ensure_ascii=False, indent=1)

    from collections import Counter
    labels = Counter(r["label"] for r in out)
    terms = Counter(r["terminal"] for r in out)
    mechs = Counter(r["mechanism"] for r in out if r["mechanism"])
    print(f"{len(out)} claims → data/tree_labels.json")
    print("\nlabel:", dict(labels))
    print("mechanism:", dict(mechs))
    print("\nterminal:")
    for t, n in terms.most_common():
        print(f"  {t:<32}{n}")


if __name__ == "__main__":
    main()
