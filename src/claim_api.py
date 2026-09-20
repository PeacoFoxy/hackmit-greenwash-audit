"""Single-claim classification for the interface. The prompt is fixed, so the same text
always hits the same cache file.

Warm the cache (run once online; the four presets then work offline):
    python -m src.claim_api warm
"""
import hashlib
import json
import os
import re

from src.rubric import RUBRIC
from src.llm import ask
from src.ui_text import PRESETS

MODEL = "claude-sonnet-4-6"
CACHE = "cache"

SYSTEM = ("You audit corporate environmental claims. Judge only from the wording of the claim. "
          "Output ONLY a raw JSON object, no markdown fences, no preamble.")

PROMPT = """Classify this corporate environmental claim as A, B, C, or D.

{rubric}

Judge ONLY from the wording. Do NOT fact-check against outside knowledge. The question is what
the sentence states and omits, not whether the company is actually green.

CLAIM: {claim}

Output ONLY: {{"label": "A|B|C|D", "reasoning": "one sentence naming what is stated or missing"}}"""


def build_prompt(claim):
    return PROMPT.format(rubric=RUBRIC, claim=claim.strip())


def cache_path(claim):
    key = hashlib.md5((MODEL + SYSTEM + build_prompt(claim)).encode()).hexdigest()
    return os.path.join(CACHE, f"{key}.json")


def is_cached(claim):
    """Whether a preset button will work with no network."""
    return os.path.exists(cache_path(claim))


def parse(raw):
    """Whole JSON -> first {...} -> regex for the label. Raises if all three fail."""
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip(), flags=re.I).strip()
    m = re.search(r"\{.*\}", s, re.S)
    for cand in (s, m.group(0) if m else None):
        if not cand:
            continue
        try:
            out = json.loads(cand)
            if isinstance(out, dict) and out.get("label") in {"A", "B", "C", "D"}:
                return {"label": out["label"], "reasoning": str(out.get("reasoning", "")).strip()}
        except Exception:
            continue
    lab = re.search(r'"label"\s*:\s*"([ABCD])"', s)
    if lab:
        rsn = re.search(r'"reasoning"\s*:\s*"([^"]*)"', s)
        return {"label": lab.group(1), "reasoning": rsn.group(1) if rsn else ""}
    raise ValueError(f"unparseable model output: {s[:200]!r}")


def classify_claim(claim):
    """Returns {label, reasoning, raw, cached}. Sends nothing on a cache hit."""
    cached = is_cached(claim)
    raw = ask(build_prompt(claim), system=SYSTEM, model=MODEL, max_tokens=400)
    return {**parse(raw), "raw": raw, "cached": cached}


def warm():
    """Write the four presets into the cache so the demo runs offline."""
    for p in PRESETS:
        hit = is_cached(p["claim"])
        r = classify_claim(p["claim"])
        print(f"[{'cached' if hit else 'fetched'}] {p['button']:<18} → {r['label']}  "
              f"{r['reasoning'][:80]}")


if __name__ == "__main__":
    import sys
    warm() if "warm" in sys.argv[1:] else print(__doc__)
