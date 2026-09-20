"""单条 claim 的分类接口（界面用）。prompt 固定，因此同一条文本永远命中同一个缓存文件。

预热缓存（联网跑一次，之后四条预设离线可用）：
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
    """预设按钮在无网络时是否可用。"""
    return os.path.exists(cache_path(claim))


def parse(raw):
    """整体 JSON → 首个 {...} → 正则抓 label。全失败抛异常，由调用方兜住。"""
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
    """返回 {label, reasoning, raw, cached}。缓存命中时不发请求。"""
    cached = is_cached(claim)
    raw = ask(build_prompt(claim), system=SYSTEM, model=MODEL, max_tokens=400)
    return {**parse(raw), "raw": raw, "cached": cached}


def warm():
    """把四条预设写进缓存，供离线 demo 使用。"""
    for p in PRESETS:
        hit = is_cached(p["claim"])
        r = classify_claim(p["claim"])
        print(f"[{'cached' if hit else 'fetched'}] {p['button']:<18} → {r['label']}  "
              f"{r['reasoning'][:80]}")


if __name__ == "__main__":
    import sys
    warm() if "warm" in sys.argv[1:] else print(__doc__)
