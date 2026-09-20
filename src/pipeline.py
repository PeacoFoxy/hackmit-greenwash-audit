"""上传 PDF 的实时管线：解析 → 句级信号 → 异常区间 → claim 抽取 → 规则树分类。

预加载路径不走这里（那条路直接读 data/*.json）。
claim 抽取需要 LLM；其余全部零调用，断网时仍能产出前四个阶段。
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

MAX_CLAIM_SENTENCES = 150     # 抽取上限，保证上传流程可在约 90 秒内完成
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
    """句子 → 七标量 + 相对位置，形状与 data/signals.json 一致。"""
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
    """对前 MAX_CLAIM_SENTENCES 条带环境信号的句子做 claim 抽取。需要 LLM。"""
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


def analyse(pdf_bytes, filename, company=None, on_stage=None, extract=True):
    """完整上传管线。on_stage(name, detail) 用于界面进度显示。"""
    def stage(name, detail):
        if on_stage:
            on_stage(name, detail)

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
    stage("Reading the PDF", f"{len(rows):,} sentences found")

    n_flagged = sum(1 for r in rows if rule_flags(r["text"]))
    stage("Checking accounting disclosures",
          f"9 rules applied, {n_flagged} sentences hit at least one")
    stage("Measuring language patterns", "7 signals computed per sentence")

    groups = {company: rows}
    regions = find_regions(groups)
    stage("Finding passages to review", f"{len(regions)} regions flagged")

    stats = company_stats(groups)

    claims, n_pool, extract_error = [], 0, None
    if extract:
        try:
            claims, n_pool = extract_claims(rows, company)
        except Exception as exc:
            extract_error = f"{type(exc).__name__}: {exc}"

    labelled = [{**c, **{k: v for k, v in tree_classify(c["text"], c["claim_id"]).items()
                         if k != "claim_id"}} for c in claims]
    detail = (f"{len(labelled)} claims labelled from the first {n_pool} qualifying sentences"
              if labelled else "extraction unavailable — rule layers above still apply")
    stage("Classifying claims", detail)

    commitments = [r for r in rows
                   if RE_TARGET_YEAR.search(r["text"]) and RE_DIGIT.search(r["text"])]

    return {"company": company, "source_id": source_id, "filename": filename,
            "n_sentences": len(rows), "rows": rows, "regions": regions,
            "company_stats": stats, "claims": labelled, "n_claim_pool": n_pool,
            "n_commitments": len(commitments), "extract_error": extract_error,
            "max_claim_sentences": MAX_CLAIM_SENTENCES}
