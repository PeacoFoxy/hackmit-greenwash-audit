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


# ============================================================ FRONTEND_V2 用语
# §4.2 四个指标：标签、tooltip（含公式）、格式化
INDICATORS = [
    {"key": "claims_needing_review", "label": "Claims needing review",
     "help": "Share of quantified claims that are technically true but incomplete. "
             "Formula: C claims / (A claims + C claims) × 100.",
     "fmt": lambda v: f"{v:.0f}%"},
    {"key": "promises_per_verification", "label": "Promises per verification",
     "help": "Forward-looking statements per mention of third-party assurance. "
             "Formula: sum(future markers) / sum(verification mentions).",
     "fmt": lambda v: f"{v:.2f}"},
    {"key": "verification_density", "label": "Verification density",
     "help": "Sentences between assurance mentions. "
             "Formula: sentences / sum(verification mentions).",
     "fmt": lambda v: f"1 in {v:.0f}"},
    {"key": "commitments_trackable", "label": "Commitments trackable",
     "help": "Targets with two or more observations of the same metric in the same report. "
             "Formula: targets with ≥ 2 observations / targets × 100.",
     "fmt": lambda v: f"{v:.0f}%"},
]

# §3.2 评级读数
GRADE_READINGS = {
    "A": "Figures are scoped and verifiable",
    "B": "Mostly scoped, some gaps",
    "C": "Technically true, materially thin",
    "D": "Claims contradict available figures",
}
GRADE_BADGE_COLOR = {"A": "green", "B": "blue", "C": "orange", "D": "red"}
GRADE_TOOLTIP = ("Measures how completely this report discloses the basis for its own figures. "
                 "It is not a judgment of environmental performance or of the company.")
# §5 必须逐字出现在展开块里
GRADE_DISCLAIMER = (
    "The thresholds in this grade were chosen by the author, not fitted to outcome data. "
    "There is no dataset of \"correctly graded\" reports to calibrate against. The grade is a "
    "transparent, reproducible summary of three measured quantities — not a validated rating.")

# §3.4 阶段名（不是模块名）
STAGES = [
    ("Reading the PDF", "{sentences:,} sentences"),
    ("Checking disclosures", "9 rules, {regions} passages flagged"),
    ("Measuring language", "7 signals"),
    ("Classifying claims", "{claims} claims"),
    ("Extracting commitments", "{commitments} targets"),
]

# §4.1 关键术语词表：没有 term_risk.json 时的回落（不带 lift 着色）
KEY_TERMS = ["matched", "carbon-free", "market-based", "location-based", "diverted",
             "inset", "replenished", "net zero", "carbon neutral", "offset", "REC", "PPA",
             "PUE", "water positive", "renewable energy", "intensity"]

KEY_TERM_QUALIFIER = {          # 每个术语用哪一类限定语判断 lift
    "matched": "method_stated", "carbon-free": "method_stated",
    "market-based": "method_stated", "location-based": "method_stated",
    "renewable energy": "method_stated", "REC": "method_stated", "PPA": "method_stated",
    "net zero": "scope_stated", "carbon neutral": "scope_stated", "offset": "scope_stated",
    "intensity": "scope_stated", "diverted": "verifier_named", "inset": "verifier_named",
    "replenished": "verifier_named", "PUE": "verifier_named",
    "water positive": "verifier_named",
}


def term_pill(term, lift=None, count=None):
    """§4.1 术语药丸：lift < 1 用警示色，其余中性；无 lift 时一律中性。"""
    if lift is None:
        return f":gray-badge[{term}]"
    color = "orange" if lift < 1 else "gray"
    return f":{color}-badge[{term}]"


def term_hover(term, lift, count, cooc):
    if lift is None:
        return f"{term}: appears {count} times"
    share = f"{100 * cooc / count:.0f}%" if count else "0%"
    return f"{term}: appears {count} times, qualifier present in {share}"


# ---------------------------------------------- 段落分析面板（右栏，粘贴原文）
PASSAGE_PANEL = {
    "title": "Analyse a passage",
    "hint": "Paste a sentence or short passage from any report. Ctrl+Enter to run.",
    "placeholder": "e.g. We matched 100% of our electricity consumption with renewable "
                   "energy purchases in 2024.",
    "empty": "Nothing analysed yet.",
    "rule_only": "Rule layer only — the one-line reading needs a network call, which is "
                 "not available right now.",
    "no_terms": "No accounting terms from the vocabulary appear in this passage.",
}


def say_span(span):
    """终点命中的原文片段，用引号包起来给用户看。"""
    return f"“{span}”" if span else None


# ------------------------------------------------- 工作树（“跑到哪一步”的可视化）
# 每个阶段：(标题, 子项, 与 pipeline stage 名的对应)
WORK_TREE = [
    ("Read the document",
     ["Pull text out of the PDF", "Repair line breaks, drop contents pages and tables"],
     "Reading the PDF"),
    ("Check the disclosures",
     ["Nine accounting rules per sentence", "Method, boundary, baseline, offsets, water, waste"],
     "Checking disclosures"),
    ("Measure the language",
     ["Seven signals per sentence", "Vagueness, hedging, promises, verification"],
     "Measuring language"),
    ("Find passages to review",
     ["Flag density against the report's own baseline", "Runs of five sentences or more"],
     "Finding passages"),
    ("Classify the claims",
     ["Atomic claims from the first 150 qualifying sentences",
      "Decision tree: method, coverage, aggregation, undefined term"],
     "Classifying claims"),
    ("Summarise",
     ["Four indicators", "Disclosure grade from three measured quantities"],
     "Extracting commitments"),
]

TREE_MARKS = {"done": ":green[●]", "running": ":orange[◐]", "pending": ":gray[○]",
              "failed": ":red[✕]"}

HISTORY_PANEL = {
    "title": "Analysed documents",
    "empty": "Nothing analysed yet. Upload a PDF above and it will be listed here.",
    "hint": "Every document analysed in this browser, newest first. Pick one to load its "
            "result without re-running the pipeline.",
    "partial": "partial — classification did not run",
}


# ------------------------------------- 评级脆弱度与子分说明（敏感性分析的界面出口）
def say_margin(m, n_subscores=3):
    """把 band_margin 的结果写成一句给人看的话。

    总分是三个子分的平均，所以总分要动 margin 分，单个子分得动 margin × 3 分 ——
    直接写总分差距会让评级显得比实际更脆。
    """
    verb = "below" if m["direction"] == "up" else "above"
    need = m["margin"] * n_subscores
    return (f"{m['margin']:.0f} points {verb} the {m['would_become']} boundary: "
            f"a {need:.0f}-point move in any single sub-score flips the letter.")


GRADE_FRAGILITY_NOTE = (
    "The letter is not robust. Moving all three band edges by up to 12 points flips two "
    "of the three reports; the ranking between them never changes. Read the ordering, "
    "not the letter.")

# 惰性子分：扫描区间内不影响任何公司的字母，必须在展开块里说明，不能默认它在起作用
INERT_SUBSCORE_NOTE = (
    "Promise balance does not discriminate here: sweeping its ceiling from 3 to 8 leaves "
    "every letter on this corpus unchanged. It is kept because a report with a very high "
    "promise-to-verification ratio should still be penalised, but on these three reports "
    "it contributes no separation.")


# ------------------------------------------------------------- 文档来源描述
def say_source(src):
    """来源行。只说文件里可核实的东西：标题、文件名、PDF 创建日期。

    出版日期我们没有核实过，所以不声称。PDF 创建日期取自文件元数据，通常接近但不等于
    出版日期，措辞上必须区分 —— 之前这里写的是编造的 published 2025-01-01。
    """
    bits = [src.get("title") or src["company"]]
    from pathlib import Path
    bits.append(Path(src["file"]).name)
    if src.get("pdf_created"):
        bits.append(f"PDF created {src['pdf_created']}")
    return "Source: " + " · ".join(bits)


# ------------------------------------------- 建议动作：机制 → 分析师下一步要什么
# 每条都必须是「可以发给 IR 的一句具体请求」，不是「需要进一步调查」这种空话。
ACTION_BY_MECHANISM = {
    "UNDISCLOSED_METHOD":
        "Ask which accounting method produced the figure, and request the other one: "
        "market-based and location-based emissions differ, and only one is usually shown.",
    "UNDISCLOSED_BOUNDARY":
        "Ask which entities the figure covers — owned sites, leased sites, the value "
        "chain — and whether that boundary is the same one used last year.",
    "SELECTIVE_AGGREGATION":
        "Request the absolute figure alongside the per-unit one, on the same boundary. "
        "Intensity can fall while the absolute total rises.",
    "UNDEFINED_TERM":
        "Ask for the definition the company applies to the term and who verified it "
        "against that definition.",
}

# 少数终点有更具体的请求，覆盖机制默认值
ACTION_BY_TERMINAL = {
    "INTENSITY_NO_ABSOLUTE":
        "Request the absolute tonnage for the same period and boundary. A 39% fall per "
        "unit is compatible with a rise in total emissions if volume grew.",
    "NO_BASELINE_YEAR":
        "Ask which baseline year the reduction is measured against, and whether the "
        "baseline has been restated since it was set.",
    "FUTURE_PROMISE_NO_MILESTONE":
        "Ask for the interim milestones between now and the target year, and what was "
        "achieved against last year's milestone.",
    "MARKET_BASED_IMPLIED":
        "Ask whether the match is hourly or annual, and in which grids the certificates "
        "were retired. An annual national match can coexist with fossil-powered hours.",
    "PROPRIETARY_METRIC":
        "Ask for the formula behind the metric and whether any third party has audited "
        "it. A company-defined index cannot be compared across issuers.",
}


def recommended_action(mechanism=None, terminal=None):
    """给分析师的下一步。没有对应机制时返回 None，界面就不显示这一块。"""
    if terminal and terminal in ACTION_BY_TERMINAL:
        return ACTION_BY_TERMINAL[terminal]
    return ACTION_BY_MECHANISM.get(mechanism)
