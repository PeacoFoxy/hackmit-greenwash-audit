"""弃答曲线：允许系统说"我不确定"之后，已作答部分的准确率能升到多少。

想法来自这批论文里反复出现的 FCM（模糊 c-means）——输出隶属度而非硬标签
（Purushothaman 等 2020；Gopal & Brunda 2019；Majhi 2019）。我们的树输出硬标签，
但它在设计时就给每个节点标了 CLOSED / OPEN：CLOSED 表示概念有固定术语表，正则未命中
基本等于概念缺失；OPEN 表示说法多样，未命中只是弱证据。这个标注一直没被用过。

检验五个置信度代理，看哪个能真正把错例排到后面：
  closed_frac  路径上 CLOSED 节点占比
  decided_by   做出最终判定的那个节点是否 CLOSED
  severity     终点的严重度 1-3（A/B 记为 0）
  agree_1      树与 baseline2 是否一致
  agree_n      三个 LLM 方法中与树一致的个数

只有跑赢随机弃答，代理才算有信息量 —— 任何弃答都会因为样本变小而抬高准确率，
所以必须和"随机扔掉同样多条"对照。
"""
import json
import warnings
from pathlib import Path

import numpy as np

from src.tree import classify

warnings.filterwarnings("ignore", message="y_pred contains classes not in y_true")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
N_RANDOM = 2000
LLM_METHODS = ("baseline2", "pipeline", "pipeline_allflags")


def load():
    met = json.loads((DATA / "metrics.json").read_text(encoding="utf-8"))
    preds = met["predictions"]
    cands = {c["claim_id"]: c
             for c in json.loads((DATA / "candidates.json").read_text(encoding="utf-8"))}
    rows = []
    for p in preds:
        r = classify(cands[p["claim_id"]]["text"], p["claim_id"])
        path = r["path"]
        closed = sum(1 for s in path if s["reliability"] == "CLOSED")
        rows.append({
            "id": p["claim_id"], "gold": p["gold"], "pred": r["label"],
            "correct": int(r["label"] == p["gold"]),
            "closed_frac": closed / len(path),
            "decided_by": int(path[-1]["reliability"] == "CLOSED"),
            "severity": r["severity"] or 0,
            "agree_1": int(p["baseline2"] == r["label"]),
            "agree_n": sum(int(p[m] == r["label"]) for m in LLM_METHODS),
        })
    return rows


def curve(rows, key):
    """按置信度阈值逐级弃答。返回 (coverage, accuracy_on_answered) 列表。"""
    vals = sorted({r[key] for r in rows}, reverse=True)
    out = []
    for t in vals:
        kept = [r for r in rows if r[key] >= t]
        out.append({"threshold": t, "coverage": len(kept) / len(rows),
                    "n_answered": len(kept),
                    "accuracy": sum(r["correct"] for r in kept) / len(kept)})
    return out


def random_baseline(rows, n_answered, n=N_RANDOM, seed=0):
    """随机扔掉同样多条时的准确率分布 —— 代理必须跑赢它才算有信息量。"""
    rng = np.random.default_rng(seed)
    corr = np.array([r["correct"] for r in rows])
    accs = [corr[rng.choice(len(corr), n_answered, replace=False)].mean() for _ in range(n)]
    return float(np.mean(accs)), float(np.percentile(accs, 95))


def run():
    rows = load()
    base = sum(r["correct"] for r in rows) / len(rows)
    print(f"全作答 accuracy = {base:.3f}（{len(rows)} 条）")
    print("随机弃答是对照：任何弃答都会抬高准确率，代理必须跑赢随机才有信息量。\n")

    out = {"n": len(rows), "baseline_accuracy": base, "proxies": {}}
    for key in ("closed_frac", "decided_by", "severity", "agree_1", "agree_n"):
        pts = curve(rows, key)
        print(f"{key}")
        print(f"  {'阈值':>8}{'覆盖率':>9}{'已答':>6}{'准确率':>9}"
              f"{'随机均值':>10}{'随机95%':>9}  ")
        beats = 0
        for p in pts:
            rm, r95 = random_baseline(rows, p["n_answered"])
            p["random_mean"], p["random_p95"] = rm, r95
            p["beats_random"] = p["accuracy"] > r95
            beats += p["beats_random"]
            mark = "  ✓ 跑赢随机" if p["beats_random"] else ""
            print(f"  {p['threshold']:>8.2f}{p['coverage']:>9.0%}{p['n_answered']:>6}"
                  f"{p['accuracy']:>9.3f}{rm:>10.3f}{r95:>9.3f}{mark}")
        out["proxies"][key] = {"points": pts, "n_beating_random": beats}
        print()

    (DATA / "abstain.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    winners = [k for k, v in out["proxies"].items() if v["n_beating_random"]]
    print("跑赢随机的代理：" + (", ".join(winners) if winners else "一个都没有"))
    print("→ data/abstain.json")
    return out


if __name__ == "__main__":
    run()
