"""成本与耗时对比：每 100 条 claim 的 API 调用数、token、美元、墙钟时间。

这批论文都会报 execution time / memory（Purushothaman 等 2020 Table 4；Abualigah &
Khader 2017 Table 7），因为在同等效果下资源消耗本身就是结论的一部分。我们的对照更极端：
规则树是 0 次调用。

token 由缓存里的真实 prompt / response 字符数估算（约 4 字符 ≈ 1 token），不是猜的；
但它是估算，不是计费口径，表里标明。
"""
import hashlib
import json
import os
import time
from pathlib import Path

from src.evaluate import BATCH, METHODS, SYSTEM, build_prompt
from src.tree import classify as tree_classify

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = ROOT / "cache"

MODEL = "claude-sonnet-4-6"
PRICE_IN, PRICE_OUT = 3.0, 15.0        # 美元 / 百万 token（Sonnet 公布价）
CHARS_PER_TOKEN = 4.0


def cache_lookup(prompt, system=SYSTEM, model=MODEL):
    key = hashlib.md5((model + system + prompt).encode()).hexdigest()
    path = CACHE / f"{key}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def measure_llm(method, claims):
    """重建 evaluate.py 会发的每一条 prompt，从缓存里读真实字符数。"""
    calls = in_chars = out_chars = missing = 0
    for i in range(0, len(claims), BATCH):
        prompt = build_prompt(method, claims[i:i + BATCH])
        hit = cache_lookup(prompt)
        calls += 1
        if hit is None:
            missing += 1
            continue
        in_chars += len(hit["prompt"]) + len(hit.get("system", ""))
        out_chars += len(hit["text"])
    return calls, in_chars, out_chars, missing


def measure_tree(claims, repeats=5):
    """规则树的墙钟时间，取多轮最小值（排除调度噪声）。"""
    best = float("inf")
    for _ in range(repeats):
        t0 = time.perf_counter()
        for c in claims:
            tree_classify(c["text"], c["claim_id"])
        best = min(best, time.perf_counter() - t0)
    return best


def run():
    # 批次内容必须与 evaluate.py 逐字一致，否则缓存键对不上：它按 gold.json 的顺序组批
    cands = {c["claim_id"]: c
             for c in json.loads((DATA / "candidates.json").read_text(encoding="utf-8"))}
    gold = [g for g in json.loads((DATA / "gold.json").read_text(encoding="utf-8"))
            if g["gold_label"] != "SKIP" and g["claim_id"] in cands]
    evaluated = [cands[g["claim_id"]] for g in gold]
    n = len(evaluated)

    tree_sec = measure_tree(evaluated)
    rows = []
    for m in METHODS:
        if m == "tree_only":
            rows.append({"method": m, "calls": 0, "in_tok": 0, "out_tok": 0,
                         "usd": 0.0, "sec": tree_sec, "missing": 0})
            continue
        calls, ic, oc, miss = measure_llm(m, evaluated)
        it, ot = ic / CHARS_PER_TOKEN, oc / CHARS_PER_TOKEN
        rows.append({"method": m, "calls": calls, "in_tok": it, "out_tok": ot,
                     "usd": it / 1e6 * PRICE_IN + ot / 1e6 * PRICE_OUT,
                     "sec": None, "missing": miss})

    scale = 100 / n
    out = {"n_claims": n, "batch": BATCH, "model": MODEL,
           "price_per_mtok": {"input": PRICE_IN, "output": PRICE_OUT},
           "chars_per_token": CHARS_PER_TOKEN,
           "tree_seconds_for_n": tree_sec, "per_100": [
               {**r, "calls_per_100": r["calls"] * scale,
                "in_tok_per_100": r["in_tok"] * scale,
                "out_tok_per_100": r["out_tok"] * scale,
                "usd_per_100": r["usd"] * scale,
                "sec_per_100": (r["sec"] * scale if r["sec"] is not None else None)}
               for r in rows],
           "note": ("Token counts are estimated from the real cached prompt and response "
                    "text at ~4 characters per token; they are not billing figures. "
                    "Wall-clock is reported only for the deterministic path, where it is "
                    "reproducible; LLM latency depends on the network and is not compared.")}
    (DATA / "cost.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                    encoding="utf-8")

    print(f"按 {n} 条 gold 实测，折算到每 100 条 claim（{MODEL}，batch={BATCH}）\n")
    print(f"{'method':<20}{'calls':>7}{'in tok':>10}{'out tok':>9}{'USD':>9}{'wall':>10}")
    for r in out["per_100"]:
        wall = f"{r['sec_per_100']*1000:.0f} ms" if r["sec_per_100"] is not None else "network"
        print(f"{r['method']:<20}{r['calls_per_100']:>7.0f}{r['in_tok_per_100']:>10,.0f}"
              f"{r['out_tok_per_100']:>9,.0f}{r['usd_per_100']:>9.4f}{wall:>10}")
    miss = sum(r["missing"] for r in rows)
    if miss:
        print(f"\n{miss} 个批次不在缓存里，其 token 记为 0，上表偏低。")
    print("\ntoken 由缓存中真实 prompt/response 字符数估算（约 4 字符 ≈ 1 token），非计费口径。")
    print("→ data/cost.json")
    return out


if __name__ == "__main__":
    run()
