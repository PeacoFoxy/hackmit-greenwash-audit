"""FRONTEND_V2 §6 的四个指标 + §5 的披露评级。缓存路径与上传路径共用同一份实现。

输入是 dict（data/*.json 的原始结构），不是对象；公式与 §6 逐字一致。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

GRADE_BANDS = [(75, "A"), (55, "B"), (35, "C")]   # 低于 35 为 D


# ------------------------------------------------------------------ §6 指标
def claims_needing_review(claims):
    """% of quantified claims that are technically true but incomplete."""
    scored = [c for c in claims if c.get("label") in ("A", "C")]
    return 100 * sum(c.get("label") == "C" for c in scored) / max(len(scored), 1)


def promises_per_verification(sentences):
    """Forward-looking markers per assurance mention."""
    f = sum(s["future"] for s in sentences)
    v = sum(s["verification"] for s in sentences)
    return f / max(v, 1)


def verification_density(sentences):
    """Sentences between assurance mentions. Returned as N for '1 in N'."""
    v = sum(s["verification"] for s in sentences)
    return len(sentences) / max(v, 1)


def commitments_trackable(audit):
    """% of extracted targets with >= 2 observations of the same metric."""
    n_two = sum(a["outcome"] == "kept" for a in audit)
    return 100 * n_two / max(len(audit), 1)


# ------------------------------------------------------------- §5 披露评级
def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def grade_components(claims, sentences):
    """三个子分（各 0-100）及其输入，全部可在界面展开核对。"""
    scored = [c for c in claims if c.get("label") in ("A", "C")]
    n_c = sum(c.get("label") == "C" for c in scored)
    c_rate = n_c / max(len(scored), 1)
    completeness = (1 - c_rate) * 100

    pvr = promises_per_verification(sentences)
    promise_balance = clamp((5 - pvr) / 4) * 100

    v = sum(s["verification"] for s in sentences)
    verif_per_100 = 100 * v / max(len(sentences), 1)
    verification = clamp(verif_per_100 / 5) * 100

    score = (completeness + promise_balance + verification) / 3
    letter = next((g for cut, g in GRADE_BANDS if score >= cut), "D")
    return {
        "completeness": completeness, "promise_balance": promise_balance,
        "verification": verification, "score": score, "letter": letter,
        "inputs": {"quantified_claims": len(scored), "C_claims": n_c,
                   "C_rate": c_rate, "pvr": pvr, "verification_mentions": v,
                   "sentences": len(sentences), "verif_per_100_sentences": verif_per_100},
    }


# ----------------------------------------------------------------- 数据装载
def load_json(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def cached_bundle():
    """预加载路径：按公司切好 claims / sentences / audit。"""
    claims = [{**c, "label": c.get("llm_label")} for c in load_json("prelabels.json")]
    sentences = load_json("signals.json")
    audit = load_json("trajectory_audit.json")
    companies = sorted({s["company"] for s in sentences})
    return {co: {"claims": [c for c in claims if c["company"] == co],
                 "sentences": [s for s in sentences if s["company"] == co],
                 "audit": [a for a in audit if a["company"] == co]}
            for co in companies}


def indicators_for(bundle):
    """四个指标打包，供 st.metric 直接使用。"""
    return {
        "claims_needing_review": claims_needing_review(bundle["claims"]),
        "promises_per_verification": promises_per_verification(bundle["sentences"]),
        "verification_density": verification_density(bundle["sentences"]),
        "commitments_trackable": commitments_trackable(bundle["audit"]),
    }


def main():
    bundles = cached_bundle()
    print(f"{'company':<12}{'review %':>10}{'PVR':>8}{'1 in N':>9}{'trackable %':>13}{'grade':>7}")
    for co, b in bundles.items():
        i = indicators_for(b)
        g = grade_components(b["claims"], b["sentences"])
        print(f"{co:<12}{i['claims_needing_review']:>9.1f}%{i['promises_per_verification']:>8.2f}"
              f"{i['verification_density']:>9.1f}{i['commitments_trackable']:>12.1f}%"
              f"{g['letter']:>7}  ({g['score']:.1f})")


if __name__ == "__main__":
    main()
