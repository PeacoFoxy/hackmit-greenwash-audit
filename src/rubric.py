"""The four-class rubric. evaluate.py and the interface share this exact text, so any
edit changes the cache keys on both sides."""

RUBRIC = """Label definitions:
A = Substantiated: concrete numbers AND states the scope or accounting method; independently verifiable.
B = Vague: unfalsifiable rhetoric with no checkable content.
C = Accounting_misleading: literally true but uses accounting choices to mislead, e.g. market-based
    "matched" wording, reporting only intensity metrics without absolute amounts, no baseline year,
    future pledges without interim milestones, or unstated coverage boundary.
D = Contradicted: conflicts with other information."""

SHORT_RUBRIC = """Label definitions:
A = specific and verifiable.
B = vague and unfalsifiable.
C = literally true but misleading through accounting choices.
D = contradicts other information."""
