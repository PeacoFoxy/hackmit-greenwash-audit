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

LABEL_COLORS = {
    "A": "#3ca951",
    "B": "#9498a0",
    "C": "#efb118",
    "D": "#ff725c",
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
