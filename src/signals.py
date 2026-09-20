"""句级标量信号：把每份报告切成句子，对每句算七个可解释的标量。纯确定性，不调 LLM。"""
import json
import random
import re
import string
from collections import Counter
from pathlib import Path

from src.rules import flags as rule_flags
from src.rules import vagueness

I = re.IGNORECASE
SPLIT = re.compile(r'(?<=[.!?])\s+(?=[A-Z"])')
MIN_LEN, MAX_LEN = 40, 600

FUNCTION_WORDS = re.compile(r"\b(?:the|of|and|to|in|we|our|is|are|that)\b", I)
PUNCT = set(string.punctuation) | {"—", "–", "•", "’", "“", "”"}

RE_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
RE_WORD = re.compile(r"\S+")
RE_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
RE_SCOPE = re.compile(r"\bscopes?\s*[123]\b", I)

RE_HEDGE = re.compile(
    r"\bcommitted\s+to\b|\bstriv(?:e|es|ing)\b|\baim(?:s|ing)?\s+to\b|\baspir\w*|"
    r"\bhelp(?:s|ed|ing)?\b|\bworking\s+toward(?:s)?\b|\bbelieve[sd]?\b|"
    r"\bresponsibl(?:e|y)\b|\bleading\b",
    I,
)
RE_FUTURE = re.compile(
    r"\bwill\b|\bby\s+20\d{2}\b|\bplan(?:s|ning)?\s+to\b|\btarget(?:s|ing|ed)?\b|"
    r"\bexpect(?:s|ed|ing)?\b",
    I,
)
RE_VERIFY = re.compile(
    r"\bassur\w*|\bverif\w*|\baudit\w*|\bthird[-\s]party\b|\bcertif\w*", I
)


def is_prose(s):
    """判断是否为正常英文散句，用于滤掉目录、标题、页眉和表格残留。"""
    return drop_reason(s) is None


def drop_reason(s):
    """返回丢弃原因；None 表示保留。"""
    if len(s) < MIN_LEN:
        return "too_short"
    if len(s) > MAX_LEN:
        return "too_long"
    if sum(c.islower() for c in s) / len(s) < 0.5:
        return "low_lowercase"
    if sum(c.isdigit() or c in PUNCT for c in s) / len(s) > 0.4:
        return "digits_punct"
    if not FUNCTION_WORDS.search(s):
        return "no_function_word"

    words = s.split()
    if not words:
        return "too_short"
    if len(RE_NUMBER.findall(s)) / len(words) > 0.30:
        return "numeric_dense"

    # 有句末标点且够长的句子视为散文，不再用大写词比例判死
    if not (s.rstrip()[-1:] in ".!?" and len(words) >= 8):
        cap = [bool(w[:1].isupper()) for w in words[1:]]  # 句首本就该大写，排除
        run, in_run = 0, 0
        for c in cap + [False]:  # 末尾补一个 False 以结算最后一段
            if c:
                run += 1
            else:
                in_run += run if run >= 2 else 0
                run = 0
        if cap and in_run / len(cap) > 0.7:
            return "cap_runs"
    return None


def sentences(text):
    t = text or ""
    t = re.sub(r"(?<=[a-z])\n(?=[a-z])", " ", t)  # 先合并断行，再归一化空白
    t = re.sub(r"\s+", " ", t)
    return [s.strip() for s in SPLIT.split(t)]


def signals(sentence):
    s = sentence
    words = len(RE_WORD.findall(s)) or 1
    hedge = len(RE_HEDGE.findall(s))
    has_num = bool(RE_NUMBER.search(s))

    spec = (1.0 if has_num else 0.0)
    spec += 1.0 if RE_YEAR.search(s) else 0.0
    spec += 1.0 if RE_SCOPE.search(s) else 0.0
    spec -= 0.5 * hedge

    return {
        "vagueness": vagueness(s),
        "numeric": round(len(RE_NUMBER.findall(s)) / words * 100, 2),
        "hedge": hedge,
        "future": len(RE_FUTURE.findall(s)),
        "flags": len(rule_flags(s)),
        "verification": len(RE_VERIFY.findall(s)),
        "specificity": round(spec, 2),
    }


def main():
    root = Path(__file__).resolve().parent.parent
    docs = json.loads((root / "data" / "corpus.json").read_text(encoding="utf-8"))

    rows, dropped, raw_total = [], [], 0
    for d in docs:
        sents = sentences(d["text"])
        kept, reasons = [], []
        for s in sents:
            r = drop_reason(s)
            (reasons if r else kept).append((s, r) if r else s)
        dropped += reasons
        raw_total += len(sents)
        print(f"{d['id']}: {len(sents)} 句 → 保留 {len(kept)}")
        for i, s in enumerate(kept):
            rows.append({"sent_id": f"{d['id']}_{i:05d}", "company": d["company"],
                         "source_id": d["id"], "text": s, **signals(s)})

    print(f"\n原始 {raw_total} 句，保留 {len(rows)} 句，丢弃 {len(dropped)} 句 "
          f"({len(dropped) / raw_total * 100:.1f}%)")
    print("丢弃分布:")
    for reason, n in Counter(r for _, r in dropped).most_common():
        print(f"  {reason:<18}{n}")

    rnd = random.Random(0)  # 固定种子，抽样可复现
    pools = [("保留样例", [r["text"] for r in rows]),
             ("丢弃样例", [s for s, _ in dropped]),
             ("cap_runs 丢弃样例", [s for s, r in dropped if r == "cap_runs"])]
    for title, pool in pools:
        print(f"\n--- {title} ({len(pool)}) ---")
        for s in rnd.sample(pool, min(5, len(pool))):
            print(f"  {s[:140]}")

    (root / "data" / "signals.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    keys = ["vagueness", "numeric", "hedge", "future", "flags", "verification", "specificity"]
    print(f"\n共 {len(rows)} 句 → data/signals.json")
    print(f"{'signal':<14}{'mean':>9}{'min':>8}{'max':>8}")
    for k in keys:
        vals = [r[k] for r in rows]
        print(f"{k:<14}{sum(vals) / len(vals):>9.2f}{min(vals):>8.2f}{max(vals):>8.2f}")


SIGNAL_KEYS = ["vagueness", "numeric", "hedge", "future", "flags", "verification", "specificity"]
WINDOW = 20


def add_smoothing(window=WINDOW):
    """按公司分组（保持原顺序），对七条信号各算窗口滑动平均，并加相对位置字段。"""
    import numpy as np

    root = Path(__file__).resolve().parent.parent
    path = root / "data" / "signals.json"
    rows = json.loads(path.read_text(encoding="utf-8"))

    groups = {}
    for r in rows:
        groups.setdefault(r["company"], []).append(r)

    kernel = np.ones(window) / window
    for company, g in groups.items():
        n = len(g)
        for i, r in enumerate(g):
            r["rel_pos"] = round(i / (n - 1), 4) if n > 1 else 0.0
        norm = np.convolve(np.ones(n), kernel, mode="same")  # 边界只对实际存在的样本取平均
        for k in SIGNAL_KEYS:
            sm = np.convolve(np.array([r[k] for r in g], dtype=float), kernel, mode="same") / norm
            for r, v in zip(g, sm):
                r[f"{k}_smooth"] = round(float(v), 4)

    path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n滑动平均窗口 {window} → data/signals.json")
    print(f"{'company':<12}{'句数':>8}{'rel_pos 范围':>22}")
    for company, g in groups.items():
        lo, hi = min(r["rel_pos"] for r in g), max(r["rel_pos"] for r in g)
        print(f"{company:<12}{len(g):>8}{f'{lo:.4f} – {hi:.4f}':>20}")


if __name__ == "__main__":
    import sys
    if "smooth" not in sys.argv[1:]:
        main()
    add_smoothing()
