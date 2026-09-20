"""Interface wording: internal mechanism / terminal / label codes mapped to readable
phrasing, plus the four preset claims.

The hard rule from FRONTEND.md sec. 2: internal codes never appear on screen. They live
only inside the "technical detail" expander.
"""

# sec. 2 mechanisms (four of them)
MECHANISM_LABELS = {
    "UNDISCLOSED_METHOD": "Method not stated",
    "UNDISCLOSED_BOUNDARY": "Coverage not stated",
    "SELECTIVE_AGGREGATION": "Partial figure only",
    "UNDEFINED_TERM": "Term undefined",
}

# The terminals sec. 2 names. Anything else falls back to its mechanism's wording.
TERMINAL_LABELS = {
    "MARKET_BASED_IMPLIED": "Purchased, not consumed",
    "INTENSITY_NO_ABSOLUTE": "Per-unit figure only",
    "NO_BASELINE_YEAR": "No baseline year",
    "FUTURE_PROMISE_NO_MILESTONE": "No interim milestone",
    "PROPRIETARY_METRIC": "Company-defined metric",
    "DIVERSION_UNDEFINED": "Disposal route unstated",
}

# sec. 2 labels (four of them)
LABEL_NAMES = {
    "A": "Substantiated",
    "B": "Unverifiable",
    "C": "Technically true, incomplete",
    "D": "Contradicted",
}

# Colours for the four mechanisms, shared by the report-map blocks and the legend
MECHANISM_COLORS = {
    "UNDISCLOSED_METHOD": "#4269d0",
    "UNDISCLOSED_BOUNDARY": "#efb118",
    "SELECTIVE_AGGREGATION": "#ff725c",
    "UNDEFINED_TERM": "#3ca951",
}

# v1 flag (what the anomalous passages are built from) -> mechanism. A passage is
# assigned the mechanism of its most frequent flag.
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


# A noun phrase per v1 flag. Noun phrases rather than verbs, so a count of 1 does not
# produce subject-verb disagreement.
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
    """Turn a passage's flag counts into an explanation a reader can follow."""
    if not flag_types:
        return (f"These {n_sentences} sentences sit above this report's flag density, "
                f"but no single pattern dominates.")
    parts = [f"{n} × {FLAG_WHY.get(f, f.lower())}"
             for f, n in sorted(flag_types.items(), key=lambda kv: (-kv[1], kv[0]))]
    return f"Within this passage of {n_sentences} sentences — " + "; ".join(parts) + "."


def mechanism_of_region(flag_types):
    """The most frequent flag in the passage decides its mechanism; ties break
    alphabetically so rendering stays stable."""
    if not flag_types:
        return None
    top = max(sorted(flag_types), key=lambda f: flag_types[f])
    return FLAG_MECHANISM.get(top)


# Streamlit's own badge colour names (:green-badge[...]), not CSS colour values
LABEL_BADGE_COLOR = {"A": "green", "B": "gray", "C": "orange", "D": "red"}
MECHANISM_BADGE_COLOR = {
    "UNDISCLOSED_METHOD": "blue",
    "UNDISCLOSED_BOUNDARY": "orange",
    "SELECTIVE_AGGREGATION": "red",
    "UNDEFINED_TERM": "green",
}




def say_mechanism(mechanism):
    """Mechanism code -> readable wording. An unknown code is returned unchanged, so gaps
    are visible rather than silent."""
    return MECHANISM_LABELS.get(mechanism, mechanism or "—")


def say_terminal(terminal, mechanism=None):
    """Terminal code -> readable wording. Terminals sec. 2 does not name fall back to their
    mechanism's wording."""
    if terminal in TERMINAL_LABELS:
        return TERMINAL_LABELS[terminal]
    return say_mechanism(mechanism) if mechanism else (terminal or "—")


def say_label(label):
    return LABEL_NAMES.get(label, label or "—")


# sec. 3, the four preset claims. The third is the demo's punchline; highlight names the
# term to pick out.
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


# ========================================================= FRONTEND_V2 wording
# sec. 4.2, the four indicators: label, tooltip (with the formula), formatting
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

# sec. 3.2, grade readings
GRADE_READINGS = {
    "A": "Figures are scoped and verifiable",
    "B": "Mostly scoped, some gaps",
    "C": "Technically true, materially thin",
    "D": "Claims contradict available figures",
}
GRADE_BADGE_COLOR = {"A": "green", "B": "blue", "C": "orange", "D": "red"}
GRADE_TOOLTIP = ("Measures how completely this report discloses the basis for its own figures. "
                 "It is not a judgment of environmental performance or of the company.")
# sec. 5 requires this verbatim inside the expander
GRADE_DISCLAIMER = (
    "The thresholds in this grade were chosen by the author, not fitted to outcome data. "
    "There is no dataset of \"correctly graded\" reports to calibrate against. The grade is a "
    "transparent, reproducible summary of three measured quantities — not a validated rating.")

# sec. 3.4, stage names (not module names)
STAGES = [
    ("Reading the PDF", "{sentences:,} sentences"),
    ("Checking disclosures", "9 rules, {regions} passages flagged"),
    ("Measuring language", "7 signals"),
    ("Classifying claims", "{claims} claims"),
    ("Extracting commitments", "{commitments} targets"),
]

# sec. 4.1, key-term vocabulary: the fallback when term_risk.json is absent (no lift colouring)
KEY_TERMS = ["matched", "carbon-free", "market-based", "location-based", "diverted",
             "inset", "replenished", "net zero", "carbon neutral", "offset", "REC", "PPA",
             "PUE", "water positive", "renewable energy", "intensity"]

KEY_TERM_QUALIFIER = {          # which qualifier class each term's lift is read against
    "matched": "method_stated", "carbon-free": "method_stated",
    "market-based": "method_stated", "location-based": "method_stated",
    "renewable energy": "method_stated", "REC": "method_stated", "PPA": "method_stated",
    "net zero": "scope_stated", "carbon neutral": "scope_stated", "offset": "scope_stated",
    "intensity": "scope_stated", "diverted": "verifier_named", "inset": "verifier_named",
    "replenished": "verifier_named", "PUE": "verifier_named",
    "water positive": "verifier_named",
}


def term_pill(term, lift=None, count=None):
    """sec. 4.1 term pills: lift below 1 gets the warning colour, everything else is
    neutral; with no lift available, everything is neutral."""
    if lift is None:
        return f":gray-badge[{term}]"
    color = "orange" if lift < 1 else "gray"
    return f":{color}-badge[{term}]"


def term_hover(term, lift, count, cooc):
    if lift is None:
        return f"{term}: appears {count} times"
    share = f"{100 * cooc / count:.0f}%" if count else "0%"
    return f"{term}: appears {count} times, qualifier present in {share}"


# ------------------------------- passage analysis panel (right column, pasted text)
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
    """The span of source text the terminal matched, quoted for display."""
    return f"“{span}”" if span else None


# --------------------------------- the work tree ("where has it got to" visualisation)
# Per stage: (title, sub-items, the pipeline stage name it corresponds to)
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


# --------------- grade fragility and sub-score notes (the sensitivity analysis on screen)
def say_margin(m, n_subscores=3):
    """Turn a band_margin result into one readable sentence.

    The overall score is the mean of three sub-scores, so while the overall score has to
    move by `margin` to flip the letter, any single sub-score has to move by margin x 3.
    Quoting the overall gap alone makes the grade look more fragile than it is.
    """
    verb = "below" if m["direction"] == "up" else "above"
    need = m["margin"] * n_subscores
    return (f"{m['margin']:.0f} points {verb} the {m['would_become']} boundary: "
            f"a {need:.0f}-point move in any single sub-score flips the letter.")


GRADE_FRAGILITY_NOTE = (
    "The letter is not robust. Moving all three band edges by up to 12 points flips two "
    "of the three reports; the ranking between them never changes. Read the ordering, "
    "not the letter.")

# An inert sub-score: across the whole sweep it changes no company's letter. That has to
# be stated in the expander rather than left to the assumption that it is doing work.
INERT_SUBSCORE_NOTE = (
    "Promise balance does not discriminate here: sweeping its ceiling from 3 to 8 leaves "
    "every letter on this corpus unchanged. It is kept because a report with a very high "
    "promise-to-verification ratio should still be penalised, but on these three reports "
    "it contributes no separation.")


# ------------------------------------------------------------ document source line
def say_source(src):
    """The source line. States only what can be checked in the file itself: title,
    filename, PDF creation date.

    The publication date was never verified, so it is not claimed. The PDF creation date
    comes from file metadata; it is usually close to, but not the same as, the
    publication date, and the wording has to keep them apart -- this line previously
    carried a fabricated "published 2025-01-01".
    """
    bits = [src.get("title") or src["company"]]
    from pathlib import Path
    bits.append(Path(src["file"]).name)
    if src.get("pdf_created"):
        bits.append(f"PDF created {src['pdf_created']}")
    return "Source: " + " · ".join(bits)


# ------------------------- recommended action: mechanism -> what the analyst asks next
# Every entry has to be one concrete request that could be sent to investor relations,
# not filler like "warrants further investigation".
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

# A few terminals have a more specific request that overrides the mechanism default
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
    """The analyst's next step. Returns None when the mechanism has no entry, and the
    interface then omits the block."""
    if terminal and terminal in ACTION_BY_TERMINAL:
        return ACTION_BY_TERMINAL[terminal]
    return ACTION_BY_MECHANISM.get(mechanism)


# ------------------------------------- corpus-level headline strip (src/headline.py)
# Four ratios shown above the per-report panels. Each tooltip carries the formula, so a
# viewer can check the arithmetic without leaving the page. The fourth is deliberately a
# range: it is the only one of the four that depends on the classifier being right.
HEADLINE_STRIP = {
    "title": "Across every report analysed",
    "hint": "Four ratios, one formula each. Reproduce them with `python -m src.headline`.",
    "screening": {
        "label": "Needs no analyst attention",
        "help": "1 − claims surfaced / sentences. Where the system points, not a "
                "guarantee that the rest is clean.",
    },
    "unverifiable": {
        "label": "Commitments not progress-checkable",
        "help": "Targets with fewer than two observations of the same metric, over all "
                "targets extracted. A matter of fact, not of judgment.",
    },
    "agreement": {
        "label": "Rule tree agrees with the model",
        "help": "CONFIRMED / (CONFIRMED + CONTESTED), over the claims both tracks "
                "actually labelled.",
    },
    "incomplete": {
        "label": "True but missing their basis",
        "help": "C / (A + C). The raw count is 80.9%, but class-C precision is 0.667 on "
                "validated rules and 0.250 on the ten a blind test exposed, so each C is "
                "weighted by the measured precision of the rule behind it. The only one "
                "of the four that depends on the classifier being right.",
    },
}
