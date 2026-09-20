"""参数敏感性分析：结论对阈值的依赖程度。

做法取自 Mosa（2020）§5.4「Effects of parameters」与 Lu 等（2015）的参数表：报告整条
曲线，而不是只报最优点。阈值是作者选的而非拟合的（FRONTEND_V2 §5 已声明），因此唯一
诚实的辩护不是"阈值对"，而是"结论在阈值附近是否稳定"。

四条扫描：
  1. 评级带边界整体平移
  2. PVR 上限（promise_balance 的 clamp 右端）
  3. 核验目标（每 100 句的第三方核验提及数）
  4. 异常检测的 z 倍数（段落数量如何随之变化）
零 LLM 调用。
"""
import json
from pathlib import Path

import numpy as np

from src.indicators import (GRADE_BANDS, cached_bundle, grade_components,
                            promises_per_verification)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def grade_of(bundle, **kw):
    g = grade_components(bundle["claims"], bundle["sentences"], **kw)
    return g["letter"], g["score"]


def sweep_bands(bundles, shifts=np.arange(-12, 12.1, 2)):
    """整体平移 75/55/35 三条带边界。"""
    rows = []
    for d in shifts:
        bands = [(cut + d, g) for cut, g in GRADE_BANDS]
        rows.append({"shift": float(d),
                     **{co: grade_of(b, bands=bands)[0] for co, b in bundles.items()}})
    return rows


def sweep_pvr_ceil(bundles, ceils=np.arange(3.0, 8.01, 0.5)):
    rows = []
    for c in ceils:
        rows.append({"pvr_ceil": float(c),
                     **{co: grade_of(b, pvr_ceil=float(c))[0] for co, b in bundles.items()}})
    return rows


def sweep_verif_target(bundles, targets=np.arange(2.0, 10.01, 0.5)):
    rows = []
    for t in targets:
        rows.append({"verif_target": float(t),
                     **{co: grade_of(b, verif_target=float(t))[0]
                        for co, b in bundles.items()}})
    return rows


def sweep_anomaly(bundles, ks=np.arange(1.0, 3.51, 0.25)):
    """异常段落的 z 倍数：阈值 = mean + k·std。段落数随 k 的变化。"""
    from collections import Counter

    from src.anomaly import MIN_REGION, PRECISE_FLAGS, smooth
    from src.rules import flags as rule_flags

    per_company = {}
    for co, b in bundles.items():
        per_sent = [[f for f in rule_flags(r["text"]) if f in PRECISE_FLAGS]
                    for r in b["sentences"]]
        per_company[co] = (per_sent, smooth([len(f) for f in per_sent]))

    rows = []
    for k in ks:
        row = {"k": float(k)}
        for co, (per_sent, vals) in per_company.items():
            thr = vals.mean() + k * vals.std()
            hot, i, n = vals > thr, 0, 0
            while i < len(hot):
                if not hot[i]:
                    i += 1
                    continue
                j = i
                while j < len(hot) and hot[j]:
                    j += 1
                if j - i >= MIN_REGION and Counter(f for fs in per_sent[i:j] for f in fs):
                    n += 1
                i = j
            row[co] = n
        rows.append(row)
    return rows


def margins(bundles):
    """每家离最近一条带边界还有多少分 —— 评级的脆弱程度。"""
    out = []
    for co, b in bundles.items():
        letter, s = grade_of(b)
        edges = [cut for cut, _ in GRADE_BANDS]
        nearest = min(edges, key=lambda e: abs(e - s))
        out.append({"company": co, "score": s, "grade": letter,
                    "nearest_edge": nearest, "margin": abs(s - nearest),
                    "pvr": promises_per_verification(b["sentences"])})
    return sorted(out, key=lambda r: r["margin"])


def stability(rows, companies):
    """一条扫描里每家公司出现过几种评级；1 = 完全稳定。"""
    return {co: sorted({r[co] for r in rows}) for co in companies}


def main():
    bundles = cached_bundle()
    companies = list(bundles)

    sweeps = {
        "band_shift": sweep_bands(bundles),
        "pvr_ceil": sweep_pvr_ceil(bundles),
        "verif_target": sweep_verif_target(bundles),
        "anomaly_k": sweep_anomaly(bundles),
    }
    marg = margins(bundles)

    out = {"defaults": {"bands": GRADE_BANDS, "pvr_floor": 1.0, "pvr_ceil": 5.0,
                        "verif_target": 5.0, "anomaly_k": 2.0},
           "margins": marg, "sweeps": sweeps,
           "note": ("Whole curves are reported, not the argmax. The thresholds were chosen "
                    "by the author; this analysis shows how far a conclusion survives when "
                    "they move, it does not justify the specific values.")}
    (DATA / "sensitivity.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                           encoding="utf-8")

    print("评级离最近带边界的距离（越小越脆弱）")
    print(f"{'company':<11}{'score':>7}{'grade':>7}{'edge':>7}{'margin':>8}")
    for m in marg:
        print(f"{m['company']:<11}{m['score']:>7.1f}{m['grade']:>7}"
              f"{m['nearest_edge']:>7}{m['margin']:>8.1f}")

    for name, key, unit in [("评级带整体平移", "band_shift", "shift"),
                            ("PVR 上限", "pvr_ceil", "pvr_ceil"),
                            ("核验目标（每 100 句）", "verif_target", "verif_target")]:
        rows = sweeps[key]
        st = stability(rows, companies)
        lo, hi = rows[0][unit], rows[-1][unit]
        print(f"\n{name}  扫描 {lo:g} → {hi:g}")
        for co in companies:
            seq = "".join(r[co] for r in rows)
            flips = sum(1 for a, b in zip(seq, seq[1:]) if a != b)
            print(f"  {co:<11}{seq}   评级集合 {st[co]}  翻转 {flips} 次")

    print("\n异常段落的 z 倍数 k  扫描 1.0 → 3.5")
    print("  " + "k".ljust(9) + "".join(f"{co[:9]:>11}" for co in companies))
    for r in sweeps["anomaly_k"]:
        print(f"  {r['k']:<9.2f}" + "".join(f"{r[co]:>11}" for co in companies))
    print("\n→ data/sensitivity.json")
    return out


if __name__ == "__main__":
    main()
