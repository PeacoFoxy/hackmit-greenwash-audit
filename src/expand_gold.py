"""按终点分层抽样，补齐 gold 从未检验过的规则。

为什么要分层：消融显示 19 个 C 终点里 10 个从未被 gold 覆盖，它们的贡献度无法测量
（Abiodun 等 2021 §4.4.3「dataset issue」、§4.4.4「established benchmarks」）。

两个必须守住的边界：
1. **分层集不是随机样本**。它按终点配额抽取，因此它上面的总准确率不是现场准确率的估计。
   原 29 条随机 gold 的指标独立保留，两者永不合并成一个"总分"。
2. **来源池不同**。4 个终点在 89 条候选里为零，只能从 390 条全量抽，这些条目在
   filter.py 下不会进入候选池。每条都记 pool 字段，便于分开统计。

另外抽 4 条树判为 A 的条目：当前 C recall = 1.000，只有在树说"没问题"的条目里
才可能找到反例。不抽这一层，recall 就永远是自证的。
"""
import csv
import json
import random
from collections import Counter
from pathlib import Path

from src.tree import TERMINALS, classify

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PER_TERMINAL = 2          # 每个未检验终点的配额
N_NEGATIVE_PROBE = 4      # 树判 A 的探针，用于检验 C recall 是否真是 1.0
SEED = 20260920


def pools():
    flagged = json.loads((DATA / "flagged.json").read_text(encoding="utf-8"))
    cand_ids = {c["claim_id"]
                for c in json.loads((DATA / "candidates.json").read_text(encoding="utf-8"))}
    gold_ids = {g["claim_id"]
                for g in json.loads((DATA / "gold.json").read_text(encoding="utf-8"))}
    rows = []
    for c in flagged:
        r = classify(c["text"], c["claim_id"])
        rows.append({"claim_id": c["claim_id"], "company": c["company"],
                     "text": c["text"], "terminal": r["terminal"], "label": r["label"],
                     "pool": "candidates" if c["claim_id"] in cand_ids else "flagged_only",
                     "in_gold": c["claim_id"] in gold_ids})
    return rows, gold_ids


def untested(rows, gold_ids):
    """gold 覆盖为 0、但在语料上确实触发的 C 终点。"""
    covered = Counter(r["terminal"] for r in rows if r["in_gold"])
    fires = Counter(r["terminal"] for r in rows)
    return [t for t, (lab, _, _) in TERMINALS.items()
            if lab == "C" and fires[t] > 0 and covered[t] == 0]


def sample():
    rng = random.Random(SEED)
    rows, gold_ids = pools()
    targets = untested(rows, gold_ids)

    picked, by_terminal = [], {}
    for t in sorted(targets):
        avail = [r for r in rows if r["terminal"] == t and not r["in_gold"]]
        take = rng.sample(avail, min(PER_TERMINAL, len(avail)))
        by_terminal[t] = len(take)
        picked += take

    # 探针层：树判 A/B 的条目，用来寻找漏报
    probe_pool = [r for r in rows if r["label"] in ("A", "B") and not r["in_gold"]]
    probes = rng.sample(probe_pool, min(N_NEGATIVE_PROBE, len(probe_pool)))
    for p in probes:
        by_terminal.setdefault("(negative probe)", 0)
        by_terminal["(negative probe)"] += 1
    picked += probes

    rng.shuffle(picked)          # 打乱，标注者看不出分层结构
    return picked, by_terminal, targets


def write(picked):
    """盲标 CSV 不含 terminal / 树标签；答案键单独存，合并时才用。"""
    blind = DATA / "blind_expand.csv"
    with blind.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["claim_id", "company", "text", "my_label", "note"])
        for r in picked:
            w.writerow([r["claim_id"], r["company"], r["text"], "", ""])

    # 答案键不进仓库（.gitignore）：它含树的预测，看到就不盲了。
    # 需要时用固定种子 SEED 重跑本模块即可完全复现。
    key = DATA / "expand_key.json"
    key.write_text(json.dumps(
        [{"claim_id": r["claim_id"], "terminal": r["terminal"],
          "tree_label": r["label"], "pool": r["pool"]} for r in picked],
        ensure_ascii=False, indent=1), encoding="utf-8")
    return blind, key


def main():
    picked, by_terminal, targets = sample()
    blind, key = write(picked)

    print(f"{len(targets)} 个 C 终点在 gold 上从未被检验，抽样配额如下：\n")
    print(f"{'stratum':<32}{'sampled':>8}")
    for t, n in sorted(by_terminal.items()):
        print(f"{t:<32}{n:>8}")
    print(f"{'total':<32}{len(picked):>8}")

    pool_mix = Counter(r["pool"] for r in picked)
    print(f"\n来源池：candidates {pool_mix['candidates']} 条 · "
          f"flagged_only {pool_mix['flagged_only']} 条")
    print("flagged_only 的条目在 filter.py 下不会进入候选池，统计时要分开。")
    print(f"\n→ {blind.name}（盲标，填 my_label 列：A / B / C / D / SKIP）")
    print(f"→ {key.name}（答案键，合并前不要看）")


if __name__ == "__main__":
    main()
