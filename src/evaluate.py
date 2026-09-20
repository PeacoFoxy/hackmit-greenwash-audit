"""Stage 6：在 gold 集上对比五种方法，输出指标表与混淆矩阵。

data/gold.json + data/candidates.json → data/metrics.json + figures/confusion.png。
tree_only 零调用，其余四种走 LLM（命中缓存则不发请求）。
"""
import json, os, re
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, confusion_matrix,
                             f1_score, fbeta_score, multilabel_confusion_matrix,
                             precision_recall_fscore_support)
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


def per_class(y_true, y_pred, label):
    """单类的 TP/FP/FN/TN 及其派生指标（定义取自 Hicks 等，PMC11404377）。

    precision = TP/(TP+FP)          recall = TP/(TP+FN)
    specificity = TN/(TN+FP)        F_b = (1+b²)·P·R / (b²·P + R)
    """
    labels = sorted(set(y_true) | set(y_pred))
    if label not in labels:
        return None
    m = multilabel_confusion_matrix(y_true, y_pred, labels=labels)[labels.index(label)]
    tn, fp, fn, tp = int(m[0, 0]), int(m[0, 1]), int(m[1, 0]), int(m[1, 1])
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    spec = tn / (tn + fp) if tn + fp else 0.0

    def fb(b):
        denom = b * b * p + r
        return (1 + b * b) * p * r / denom if denom else 0.0

    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": p, "recall": r, "specificity": spec,
            "balanced_accuracy": (r + spec) / 2,
            "f1": fb(1.0), "f0.5": fb(0.5), "f2": fb(2.0)}


def score(y_true, y_pred):
    present = sorted(set(y_true))  # macro 只对 gold 中出现的类别取平均
    c = per_class(y_true, y_pred, "C") or {k: 0.0 for k in
                                           ("precision", "recall", "specificity", "f1",
                                            "f0.5", "f2", "balanced_accuracy")}
    out = {"accuracy": accuracy_score(y_true, y_pred),
           # 多类 BA = 各类 recall 的宏平均，对类别不均衡更公允
           "balanced_accuracy": balanced_accuracy_score(y_true, y_pred),
           "macro_f1": f1_score(y_true, y_pred, labels=present, average="macro",
                                zero_division=0),
           "macro_f0.5": fbeta_score(y_true, y_pred, beta=0.5, labels=present,
                                     average="macro", zero_division=0),
           "macro_f2": fbeta_score(y_true, y_pred, beta=2.0, labels=present,
                                   average="macro", zero_division=0),
           "C_precision": c["precision"], "C_recall": c["recall"],
           "C_specificity": c["specificity"], "C_f1": c["f1"],
           "C_f0.5": c["f0.5"], "C_f2": c["f2"],
           "C_balanced_accuracy": c["balanced_accuracy"]}
    out["per_class"] = {lab: per_class(y_true, y_pred, lab) for lab in present}
    return out


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

    cols = ["accuracy", "balanced_accuracy", "macro_f1",
            "C_precision", "C_recall", "C_specificity", "C_f1", "C_f2"]
    head = {"accuracy": "acc", "balanced_accuracy": "BA", "macro_f1": "macroF1",
            "C_precision": "C_prec", "C_recall": "C_rec", "C_specificity": "C_spec",
            "C_f1": "C_F1", "C_f2": "C_F2"}
    print("\n" + f"{'method':<19}" + "".join(f"{head[c]:>9}" for c in cols))
    for m, s in metrics.items():
        print(f"{m:<19}" + "".join(f"{s[c]:>9.3f}" for c in cols))

    labels, cm = plot_confusion(y_true, preds["pipeline"], os.path.join(FIG_DIR, "confusion.png"))
    json.dump({"n": len(gold), "metrics": metrics,
               "pipeline_confusion": {"labels": labels, "matrix": cm},
               "predictions": [{"claim_id": g["claim_id"], "gold": g["gold_label"],
                                **{m: preds[m][i] for m in preds}} for i, g in enumerate(gold)]},
              open("data/metrics.json", "w"), ensure_ascii=False, indent=1)
    print("\n→ data/metrics.json, figures/confusion.png")


if __name__ == "__main__":
    main()
