"""Live pipeline for an uploaded PDF: parse -> sentence signals -> passages ->
claim extraction -> rule-tree classification.

The preloaded path does not come through here; it reads data/*.json directly.
Only claim extraction needs the model. Everything else is deterministic, so the first
four stages still produce output with no network.
"""
import json
import re
import tempfile
from pathlib import Path

from src.anomaly import company_stats, regions as find_regions
from src.extract import SIGNALS
from src.ingest import load as load_pdf
from src.llm import ask
from src.rules import flags as rule_flags
from src.signals import is_prose, sentences, signals
from src.tree import classify as tree_classify

MAX_CLAIM_SENTENCES = 150     # extraction cap, keeping an upload inside ~90 seconds
EXTRACT_BATCH = 10

RE_TARGET_YEAR = re.compile(r"\b20[2-5]\d\b")
RE_DIGIT = re.compile(r"\d")

EXTRACT_SYSTEM = """You extract atomic environmental claims from corporate reports.
An atomic claim is ONE assertion that can be independently checked for evidence.
Skip narrative, headers and page furniture.
Output ONLY a JSON array, no prose, no markdown fences."""

EXTRACT_PROMPT = """Extract atomic environmental claims from these sentences.

COMPANY: {company}
SENTENCES:
{chunk}

Output JSON array, each item: {{"text": "the claim, lightly cleaned",
"topic": "energy|emissions|water|waste|other"}}. Return [] if none."""


def _parse_array(raw):
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip(), flags=re.I).strip()
    m = re.search(r"\[.*\]", s, re.S)
    for cand in (s, m.group(0) if m else None):
        if not cand:
            continue
        try:
            out = json.loads(cand)
            if isinstance(out, list):
                return out
        except Exception:
            continue
    return []


def build_rows(text, company, source_id):
    """Sentence -> 7 signals + relative position, shaped like data/signals.json."""
    kept = [s for s in sentences(text) if is_prose(s)]
    rows = []
    for i, s in enumerate(kept):
        rows.append({"sent_id": f"{source_id}_{i:05d}", "company": company,
                     "source_id": source_id, "text": s, **signals(s)})
    n = len(rows)
    for i, r in enumerate(rows):
        r["rel_pos"] = round(i / (n - 1), 4) if n > 1 else 0.0
    return rows


def extract_claims(rows, company, progress=None):
    """Extract claims from the first MAX_CLAIM_SENTENCES qualifying sentences. Needs the model."""
    pool = [r for r in rows if SIGNALS.search(r["text"])][:MAX_CLAIM_SENTENCES]
    claims, n_batches = [], -(-len(pool) // EXTRACT_BATCH)
    for i in range(0, len(pool), EXTRACT_BATCH):
        batch = pool[i:i + EXTRACT_BATCH]
        chunk = "\n".join(r["text"] for r in batch)
        if progress:
            progress(i // EXTRACT_BATCH + 1, n_batches)
        raw = ask(EXTRACT_PROMPT.format(company=company, chunk=chunk), system=EXTRACT_SYSTEM)
        for c in _parse_array(raw):
            if isinstance(c, dict) and c.get("text"):
                claims.append({"claim_id": f"up_{len(claims):03d}", "company": company,
                               "text": str(c["text"]).strip(),
                               "topic": c.get("topic", "other")})
    return claims, len(pool)


def analyse(pdf_bytes, filename, company=None, on_stage=None, extract=True, on_partial=None):
    """The full upload pipeline.

    on_stage(name, detail) updates the progress line. on_partial(dict) hands out the
    accumulated result as each stage completes, so the caller can render progressively:
    when a later stage fails, the earlier results are not lost.
    """
    partial = {}

    def stage(name, detail, **fields):
        partial.update(fields)
        if on_stage:
            on_stage(name, detail)
        if on_partial:
            on_partial(dict(partial))

    company = company or Path(filename).stem
    source_id = re.sub(r"\W+", "_", Path(filename).stem).lower()[:24] or "upload"

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
        fh.write(pdf_bytes)
        tmp = fh.name
    try:
        text = load_pdf(tmp)
    finally:
        Path(tmp).unlink(missing_ok=True)

    rows = build_rows(text, company, source_id)
    stage("Reading the PDF", f"{len(rows):,} sentences",
          company=company, source_id=source_id, filename=filename,
          rows=rows, n_sentences=len(rows))

    n_flagged = sum(1 for r in rows if rule_flags(r["text"]))
    stage("Checking disclosures", f"9 rules, {n_flagged} sentences hit at least one",
          n_flagged=n_flagged)
    stage("Measuring language", "7 signals per sentence")

    groups = {company: rows}
    regions = find_regions(groups)
    stage("Finding passages", f"{len(regions)} passages flagged", regions=regions)

    stats = company_stats(groups)
    partial["company_stats"] = stats

    claims, n_pool, extract_error = [], 0, None
    if extract:
        try:
            claims, n_pool = extract_claims(rows, company)
        except Exception as exc:
            extract_error = f"{type(exc).__name__}: {exc}"

    labelled = [{**c, **{k: v for k, v in tree_classify(c["text"], c["claim_id"]).items()
                         if k != "claim_id"}} for c in claims]
    detail = (f"{len(labelled)} claims from the first {n_pool} qualifying sentences "
              f"(cap {MAX_CLAIM_SENTENCES})"
              if labelled else "extraction unavailable — the rule stages above still apply")
    stage("Classifying claims", detail, claims=labelled, n_claim_pool=n_pool,
          extract_error=extract_error)

    commitments = [r for r in rows
                   if RE_TARGET_YEAR.search(r["text"]) and RE_DIGIT.search(r["text"])]
    stage("Extracting commitments", f"{len(commitments)} targets",
          n_commitments=len(commitments))

    return {**partial, "max_claim_sentences": MAX_CLAIM_SENTENCES}
