"""界面用词表：内部机制名 / 终点名 / 标签 → 用户可读措辞，以及四条预设 claim。

FRONTEND.md §2 的铁律：内部代号不上屏，只出现在「技术细节」折叠块里。
"""

# §2 机制（四类）
MECHANISM_LABELS = {
    "UNDISCLOSED_METHOD": "Method not stated",
    "UNDISCLOSED_BOUNDARY": "Coverage not stated",
    "SELECTIVE_AGGREGATION": "Partial figure only",
    "UNDEFINED_TERM": "Term undefined",
}

# §2 列出的终点（其余终点回落到所属机制的措辞）
TERMINAL_LABELS = {
    "MARKET_BASED_IMPLIED": "Purchased, not consumed",
    "INTENSITY_NO_ABSOLUTE": "Per-unit figure only",
    "NO_BASELINE_YEAR": "No baseline year",
    "FUTURE_PROMISE_NO_MILESTONE": "No interim milestone",
    "PROPRIETARY_METRIC": "Company-defined metric",
    "DIVERSION_UNDEFINED": "Disposal route unstated",
}

# §2 四类标签
LABEL_NAMES = {
    "A": "Substantiated",
    "B": "Unverifiable",
    "C": "Technically true, incomplete",
    "D": "Contradicted",
}

# 四类机制的配色（报告地图的色块、图例共用）
MECHANISM_COLORS = {
    "UNDISCLOSED_METHOD": "#4269d0",
    "UNDISCLOSED_BOUNDARY": "#efb118",
    "SELECTIVE_AGGREGATION": "#ff725c",
    "UNDEFINED_TERM": "#3ca951",
}

# v1 flag（异常区间用的就是它）→ 机制。区间按出现最多的 flag 归类。
FLAG_MECHANISM = {
    "SCOPE2_METHOD_UNSTATED": "UNDISCLOSED_METHOD",
    "MATCHING_LANGUAGE": "UNDISCLOSED_METHOD",
    "OFFSET_UNDISCLOSED": "UNDISCLOSED_METHOD",
    "NO_BASELINE_YEAR": "UNDISCLOSED_BOUNDARY",
    "GRID_MISMATCH_RISK": "UNDISCLOSED_BOUNDARY",
    "FUTURE_PROMISE_NO_MILESTONE": "UNDISCLOSED_BOUNDARY",
    "CHERRY_PICKED_METRIC": "SELECTIVE_AGGREGATION",
    "WATER_ACCOUNTING_VAGUE": "UNDEFINED_TERM",
}


# 每个 v1 flag 的名词短语说明。用名词短语而非动词，计数为 1 时也不会出现主谓不一致。
FLAG_WHY = {
    "SCOPE2_METHOD_UNSTATED": "clean-electricity figures with no accounting method stated "
                              "(market-based or location-based)",
    "MATCHING_LANGUAGE": "electricity described as matched or purchased rather than consumed",
    "OFFSET_UNDISCLOSED": "neutrality claims with no role stated for offsets",
    "NO_BASELINE_YEAR": "percentage changes with no baseline year",
    "GRID_MISMATCH_RISK": "purchase instruments with no grid or region named",
    "FUTURE_PROMISE_NO_MILESTONE": "future targets with no interim milestone",
    "CHERRY_PICKED_METRIC": "efficiency metrics not stated as fleet averages",
    "WATER_ACCOUNTING_VAGUE": "water-positive or replenishment wording with no method named",
}


def why_flagged(flag_types, n_sentences):
    """把区间的 flag 计数写成一段用户读得懂的解释。"""
    if not flag_types:
        return (f"These {n_sentences} sentences sit above this report's flag density, "
                f"but no single pattern dominates.")
    parts = [f"{n} × {FLAG_WHY.get(f, f.lower())}"
             for f, n in sorted(flag_types.items(), key=lambda kv: (-kv[1], kv[0]))]
    return f"Within this passage of {n_sentences} sentences — " + "; ".join(parts) + "."


def mechanism_of_region(flag_types):
    """区间里命中最多的 flag 决定它的机制；并列时取字母序，保证渲染稳定。"""
    if not flag_types:
        return None
    top = max(sorted(flag_types), key=lambda f: flag_types[f])
    return FLAG_MECHANISM.get(top)


# Streamlit 原生 badge 的颜色名（:green-badge[...]），不是 CSS 色值
LABEL_BADGE_COLOR = {"A": "green", "B": "gray", "C": "orange", "D": "red"}
MECHANISM_BADGE_COLOR = {
    "UNDISCLOSED_METHOD": "blue",
    "UNDISCLOSED_BOUNDARY": "orange",
    "SELECTIVE_AGGREGATION": "red",
    "UNDEFINED_TERM": "green",
}




def say_mechanism(mechanism):
    """机制代号 → 用户措辞。未知代号返回原样，便于发现遗漏。"""
    return MECHANISM_LABELS.get(mechanism, mechanism or "—")


def say_terminal(terminal, mechanism=None):
    """终点代号 → 用户措辞。未列入 §2 的终点回落到机制措辞。"""
    if terminal in TERMINAL_LABELS:
        return TERMINAL_LABELS[terminal]
    return say_mechanism(mechanism) if mechanism else (terminal or "—")


def say_label(label):
    return LABEL_NAMES.get(label, label or "—")


# §3 四条预设 claim。第三条是 demo 高潮：highlight 指出要高亮的术语。
PRESETS = [
    {"button": "Substantiated", "expected": "A", "highlight": "Scope 1 and 2",
     "claim": "Our Scope 1 and 2 emissions decreased by 30% from the 2020 base year"},
    {"button": "Unverifiable", "expected": "B", "highlight": None,
     "claim": "Nature-based design solutions are reducing our environmental footprint"},
    {"button": "Technically true", "expected": "C", "highlight": "matched",
     "claim": "Amazon matched 100% of the electricity consumed by its global operations "
              "with renewable energy"},
    {"button": "Per-unit only", "expected": "C", "highlight": "per shipped unit",
     "claim": "We reduced emissions per shipped unit by 39% compared to 2019"},
]

def label_badge(label):
    return f":{LABEL_BADGE_COLOR.get(label, 'gray')}-badge[{say_label(label)}]"


def mechanism_badge(mechanism):
    color = MECHANISM_BADGE_COLOR.get(mechanism, "gray")
    return f":{color}-badge[{say_mechanism(mechanism)}]"
