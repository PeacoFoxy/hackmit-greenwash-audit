"""Stage 6：在 gold 集上对比五种方法，输出指标表与混淆矩阵。

data/gold.json + data/candidates.json → data/metrics.json + figures/confusion.png。
tree_only 零调用，其余四种走 LLM（命中缓存则不发请求）。
"""
import json, os, re
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
from src.llm import ask
from src.rubric import RUBRIC, SHORT_RUBRIC
from src.tree import classify as tree_classify

FIG_DIR = "figures"
os.makedirs(FIG_DIR, exist_ok=True)

BATCH = 5
LABELS = ["A", "B", "C", "D"]


FLAG_NOTE = """Each claim also carries rule-based hints from a regex pass: "flags" (triggered risk patterns)
and "vagueness" (0-1, higher = vaguer).
These flags are heuristic signals, not conclusions. A flag suggests where to look; it does not
by itself make a claim misleading. If the claim states its scope or method clearly despite a
flag, label it A."""

# SCOPE_BOUNDARY_UNCLEAR 误报率太高，不喂给模型
PRECISE_FLAGS = {
    "SCOPE2_METHOD_UNSTATED", "MATCHING_LANGUAGE", "OFFSET_UNDISCLOSED", "NO_BASELINE_YEAR",
    "GRID_MISMATCH_RISK", "CHERRY_PICKED_METRIC", "WATER_ACCOUNTING_VAGUE",
    "FUTURE_PROMISE_NO_MILESTONE",
}

SYSTEM = "Output ONLY a JSON array, no prose, no markdown fences."

CONSTRAINTS = """Judge ONLY from the wording of each claim. Do NOT fact-check against outside
knowledge. The question is what the sentence states and omits, not whether
the company is actually green.

Output ONLY a raw JSON array. No markdown fences, no analysis, no preamble.
Format: [{"claim_id":"...","label":"A"}]"""


METHODS = ["tree_only", "baseline1", "baseline2", "pipeline", "pipeline_allflags"]


def item(c, hint_mode):
    """hint_mode: None 不给提示 / 'precise' 只给高精度 flag / 'all' 给全部 flag。"""
    d = {"claim_id": c["claim_id"], "text": c["text"]}
    if hint_mode:
        d["flags"] = (c["flags"] if hint_mode == "all"
                      else [f for f in c["flags"] if f in PRECISE_FLAGS])
        d["vagueness"] = c["vagueness"]
    return json.dumps(d, ensure_ascii=False)


def build_prompt(method, batch):
    hint_mode = {"pipeline": "precise", "pipeline_allflags": "all"}.get(method)
    hints = hint_mode is not None
    claims = "\n".join(item(c, hint_mode) for c in batch)
    rubric = SHORT_RUBRIC if method == "baseline1" else RUBRIC
    head = "Classify each corporate environmental claim below as A, B, C, or D.\n\n" + rubric
    if hints:
        head += "\n\n" + FLAG_NOTE
    return f"{head}\n\nCLAIMS:\n{claims}\n\n{CONSTRAINTS}"


def parse_json(raw):
    """逐级降级解析：整体 JSON → 首个 [...] → 逐条正则抓取。全失败返回 []。"""
    s = (raw or "").strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.I).strip()
    try:
        out = json.loads(s)
        if isinstance(out, list):
            return out
    except Exception:
        pass
    m = re.search(r"\[.*\]", s, flags=re.S)
    if m:
        try:
            out = json.loads(m.group(0))
            if isinstance(out, list):
                return out
        except Exception:
            pass
    pairs = re.findall(r'"claim_id"\s*:\s*"([^"]+)"[^}]*?"label"\s*:\s*"([ABCD])"', s)
    if pairs:
        return [{"claim_id": cid, "label": lab} for cid, lab in pairs]
    print(f"  [warn] parse_json failed, raw[:200]: {s[:200]!r}")
    return []


def classify(method, claims):
    if method == "tree_only":  # 纯规则树，零 LLM 调用
        return [tree_classify(c["text"], c["claim_id"])["label"] for c in claims]

    preds = {}
    for i in range(0, len(claims), BATCH):
        batch = claims[i:i+BATCH]
        raw = ask(build_prompt(method, batch), system=SYSTEM)
        for r in parse_json(raw):
            if isinstance(r, dict) and r.get("label") in LABELS:
                preds[r.get("claim_id")] = r["label"]
    out = []
    for c in claims:
        if c["claim_id"] not in preds:
            print(f"  [warn] {method}: no valid label for {c['claim_id']} -> UNKNOWN")
        out.append(preds.get(c["claim_id"], "UNKNOWN"))
    return out


def score(y_true, y_pred):
    present = sorted(set(y_true))  # macro F1 只对 gold 中出现的类别取平均
    p, r, f, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=["C"], average=None, zero_division=0)
    return {"accuracy": accuracy_score(y_true, y_pred),
            "macro_f1": f1_score(y_true, y_pred, labels=present, average="macro", zero_division=0),
            "C_precision": float(p[0]), "C_recall": float(r[0]), "C_f1": float(f[0])}


def plot_confusion(y_true, y_pred, path):
    labels = LABELS + (["UNKNOWN"] if "UNKNOWN" in y_pred else [])
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    fig, ax = plt.subplots(figsize=(5, 4.5))
    ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(labels)), labels)
    ax.set_yticks(range(len(labels)), labels)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Gold")
    ax.set_title("Pipeline confusion matrix")
    vmax = cm.max() or 1
    for i in range(len(labels)):
        for j in range(len(labels)):
            ax.text(j, i, cm[i, j], ha="center", va="center",
                    color="white" if cm[i, j] > vmax / 2 else "black")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return labels, cm.tolist()


def main():
    gold = [g for g in json.load(open("data/gold.json")) if g["gold_label"] != "SKIP"]
    cands = {c["claim_id"]: c for c in json.load(open("data/candidates.json"))}
    missing = [g["claim_id"] for g in gold if g["claim_id"] not in cands]
    if missing:
        print(f"[warn] {len(missing)} gold ids not in candidates.json, skipped: {missing}")
    gold = [g for g in gold if g["claim_id"] in cands]
    claims = [cands[g["claim_id"]] for g in gold]
    y_true = [g["gold_label"] for g in gold]
    print(f"Evaluating on {len(gold)} claims")

    metrics, preds = {}, {}
    for m in METHODS:
        print(f"running {m} ...")
        preds[m] = classify(m, claims)
        metrics[m] = score(y_true, preds[m])

    cols = ["accuracy", "macro_f1", "C_precision", "C_recall", "C_f1"]
    print("\n" + f"{'method':<19}" + "".join(f"{c:>13}" for c in cols))
    for m, s in metrics.items():
        print(f"{m:<19}" + "".join(f"{s[c]:>13.3f}" for c in cols))

    labels, cm = plot_confusion(y_true, preds["pipeline"], os.path.join(FIG_DIR, "confusion.png"))
    json.dump({"n": len(gold), "metrics": metrics,
               "pipeline_confusion": {"labels": labels, "matrix": cm},
               "predictions": [{"claim_id": g["claim_id"], "gold": g["gold_label"],
                                **{m: preds[m][i] for m in preds}} for i, g in enumerate(gold)]},
              open("data/metrics.json", "w"), ensure_ascii=False, indent=1)
    print("\n→ data/metrics.json, figures/confusion.png")


if __name__ == "__main__":
    main()
