"""从语料里抽取量化承诺与其已实现值，用于比较「要求速度」与「实际速度」。

data/claims.json + data/signals.json → data/trajectories.json。[LLM]
三步：目标抽取 → 观测值抽取 → 配对（同公司同指标，保留最近两次观测）。
"""
import json
import re
from collections import defaultdict
from pathlib import Path

from src.llm import ask

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

BATCH = 10
OBS_CANDIDATES = 20        # 每个指标最多送多少条候选去抽观测值
MIN_OBSERVATIONS = 2

RE_TARGET_YEAR = re.compile(r"\b20[2-5]\d\b")
RE_QUANTITY = re.compile(r"\d")
RE_WORD = re.compile(r"[a-z][a-z0-9-]+")

STOPWORDS = {"the", "a", "an", "of", "and", "to", "in", "for", "by", "our", "we", "percentage",
             "percent", "total", "annual", "per", "with", "from", "is", "are", "was", "were"}

SYSTEM = "Output ONLY a JSON array, no prose, no markdown fences."

TARGET_PROMPT = """Extract any quantified environmental commitment.

CLAIMS:
{claims}

Output ONLY a JSON array: [{{"claim_id": "...", "metric": "short name e.g. carbon-free energy
percentage", "target_value": number, "target_unit": "% | tCO2e | MWh", "target_year": number,
"domain": "energy|emissions|water|waste"}}]. Skip claims with no numeric target or no year.
Return [] if none."""

OBS_PROMPT = """For the metric described as {metric}, extract any reported actual value.

CLAIMS:
{claims}

Output ONLY: [{{"claim_id": "...", "value": number, "unit": "...", "year": number}}].
Only include values the company reports as achieved, not targets. Return [] if none."""


def parse_json(raw):
    """整体 JSON → 首个 [...] → 放弃。解析失败打印原文前 200 字符。"""
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip(), flags=re.I).strip()
    m = re.search(r"\[.*\]", s, re.S)
    for cand in (s, m.group(0) if m else None):
        if not cand:
            continue
        try:
            out = json.loads(cand)
            if isinstance(out, list):
                return out
        except Exception:
            continue
    print(f"  [warn] parse failed, raw[:200]: {s[:200]!r}")
    return []


def num(v):
    """把 "66%"、"1,234" 之类转成 float；失败返回 None。"""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.search(r"-?\d[\d,]*(?:\.\d+)?", v)
        if m:
            return float(m.group(0).replace(",", ""))
    return None


def words(text):
    return {w for w in RE_WORD.findall(text.lower()) if w not in STOPWORDS}


def similarity(metric, text):
    """指标名与候选文本的词重叠比例。"""
    mw = words(metric)
    return len(mw & words(text)) / len(mw) if mw else 0.0


# ------------------------------------------------------------------ step 1
def extract_targets(claims):
    pool = [c for c in claims
            if RE_TARGET_YEAR.search(c["text"]) and RE_QUANTITY.search(c["text"])]
    print(f"step 1: {len(pool)} / {len(claims)} claims have a target year + quantity")

    targets = []
    by_id = {c["claim_id"]: c for c in claims}
    for i in range(0, len(pool), BATCH):
        batch = pool[i:i + BATCH]
        items = "\n".join(json.dumps({"claim_id": c["claim_id"], "text": c["text"]},
                                     ensure_ascii=False) for c in batch)
        print(f"  batch {i // BATCH + 1}/{-(-len(pool) // BATCH)}")
        for r in parse_json(ask(TARGET_PROMPT.format(claims=items), system=SYSTEM)):
            cid = r.get("claim_id") if isinstance(r, dict) else None
            tv, ty = num(r.get("target_value")), num(r.get("target_year"))
            if cid not in by_id or tv is None or ty is None or not r.get("metric"):
                continue
            targets.append({"claim_id": cid, "company": by_id[cid]["company"],
                            "metric": str(r["metric"]).strip(),
                            "target_value": tv, "target_unit": r.get("target_unit", ""),
                            "target_year": int(ty), "domain": r.get("domain", "other")})
    # 同一个承诺常被多条 claim 重复表述，按 (公司,指标,目标值,目标年) 合并
    merged = {}
    for t in targets:
        key = (t["company"], t["metric"].lower(), t["target_value"], t["target_year"])
        if key in merged:
            merged[key]["claim_ids"].append(t["claim_id"])
        else:
            t["claim_ids"] = [t.pop("claim_id")]
            merged[key] = t
    out = list(merged.values())
    print(f"step 1: {len(targets)} extracted → {len(out)} distinct targets after merge")
    return out


# ------------------------------------------------------------------ step 2
def extract_observations(metric, company, pool):
    """在同公司的候选里抽已实现值。pool 已按与 metric 的相似度排序。"""
    obs = []
    for i in range(0, len(pool), BATCH):
        batch = pool[i:i + BATCH]
        items = "\n".join(json.dumps({"claim_id": c["id"], "text": c["text"]},
                                     ensure_ascii=False) for c in batch)
        for r in parse_json(ask(OBS_PROMPT.format(metric=metric, claims=items), system=SYSTEM)):
            if not isinstance(r, dict):
                continue
            v, y = num(r.get("value")), num(r.get("year"))
            if v is None or y is None:
                continue
            obs.append({"claim_id": r.get("claim_id"), "company": company,
                        "value": v, "unit": r.get("unit", ""), "year": int(y)})
    return obs


def candidate_pool(metric, company, claims, sentences):
    """同公司候选，按指标词重叠排序。claim 级优先，不足时回落到句级。"""
    cand = [{"id": c["claim_id"], "text": c["text"], "sim": similarity(metric, c["text"])}
            for c in claims if c["company"] == company]
    cand = [c for c in cand if c["sim"] > 0]
    cand.sort(key=lambda c: -c["sim"])
    if len(cand) < OBS_CANDIDATES:
        extra = [{"id": s["sent_id"], "text": s["text"], "sim": similarity(metric, s["text"])}
                 for s in sentences if s["company"] == company]
        extra = [e for e in extra if e["sim"] >= 0.5]
        extra.sort(key=lambda e: -e["sim"])
        cand += extra[:OBS_CANDIDATES - len(cand)]
    return cand[:OBS_CANDIDATES]


# ------------------------------------------------------------------ step 3
def pair(targets, observations):
    """同公司同指标配对，保留最近两次观测；不足两次的丢弃并记原因。

    返回 (轨迹, 丢弃分组, 审计)。审计包含每一个目标的去向，不只是被丢弃的。
    """
    out, discarded, audit = [], defaultdict(list), []
    for t in targets:
        obs = observations.get((t["company"], t["metric"]), [])
        # 去重（同年取最后一次），排除目标年本身
        by_year = {}
        for o in obs:
            if o["year"] < t["target_year"]:
                by_year[o["year"]] = o
        kept = sorted(by_year.values(), key=lambda o: o["year"])[-MIN_OBSERVATIONS:]

        record = {"company": t["company"], "metric": t["metric"],
                  "target_value": t["target_value"], "target_unit": t["target_unit"],
                  "target_year": t["target_year"], "domain": t["domain"],
                  "observations_found": len(kept),
                  "observation_years": [o["year"] for o in kept],
                  "source_claim_ids": t["claim_ids"]}

        if len(kept) < MIN_OBSERVATIONS:
            reason = "no_observations" if not kept else "only_one_observation"
            discarded[reason].append({"company": t["company"], "metric": t["metric"],
                                      "found": len(kept)})
            audit.append({**record, "outcome": "discarded", "reason": reason})
            continue
        audit.append({**record, "outcome": "kept", "reason": None})

        first, last = kept[0], kept[-1]
        span_obs = last["year"] - first["year"]
        span_left = t["target_year"] - last["year"]
        observed = (last["value"] - first["value"]) / span_obs if span_obs else None
        required = (t["target_value"] - last["value"]) / span_left if span_left else None
        out.append({
            "company": t["company"], "metric": t["metric"],
            "target_value": t["target_value"], "target_year": t["target_year"],
            "unit": t["target_unit"], "domain": t["domain"],
            "observations": [{"year": o["year"], "value": o["value"]} for o in kept],
            "observed_pace_per_year": round(observed, 3) if observed is not None else None,
            "required_pace_per_year": round(required, 3) if required is not None else None,
            "on_track": (None if observed is None or required is None
                         else bool(observed >= required)),
            "source_claim_ids": t["claim_ids"] + [o["claim_id"] for o in kept],
        })
    return out, discarded, audit


# ------------------------------------------------------------------ gap 分析
def compute_gap(traj):
    """把一条轨迹换算成速度缺口。符号自适应：减排类目标（gap 为负、achieved 为负）
    的 pace_ratio 同样为正，因此用 ratio 而非 achieved 的正负来判定 MOVING_AWAY。"""
    obs = sorted(traj["observations"], key=lambda o: o["year"])
    prior, latest = obs[-2], obs[-1]
    gap = traj["target_value"] - latest["value"]
    years_left = traj["target_year"] - latest["year"]
    obs_span = latest["year"] - prior["year"]

    required = gap / years_left if years_left else None
    achieved = (latest["value"] - prior["value"]) / obs_span if obs_span else None

    ratio = None
    if required not in (None, 0) and achieved is not None:
        ratio = achieved / required

    projected = shortfall = None
    if achieved and ratio is not None and ratio > 0:
        projected = latest["year"] + gap / achieved
        shortfall = projected - traj["target_year"]

    if ratio is None:
        status = "UNDEFINED"
    elif ratio <= 0:
        status = "MOVING_AWAY"
    elif ratio >= 1.0:
        status = "ON_TRACK"
    else:
        status = "TRAJECTORY_INSUFFICIENT"

    return {**{k: traj[k] for k in ("company", "metric", "unit", "target_value",
                                    "target_year", "source_claim_ids")},
            "prior_year": prior["year"], "prior_value": prior["value"],
            "latest_year": latest["year"], "latest_value": latest["value"],
            "gap": round(gap, 3), "years_left": years_left,
            "required_pace": round(required, 3) if required is not None else None,
            "achieved_pace": round(achieved, 3) if achieved is not None else None,
            "pace_ratio": round(ratio, 3) if ratio is not None else None,
            "projected_year": round(projected, 1) if projected is not None else None,
            "shortfall_years": round(shortfall, 1) if shortfall is not None else None,
            "status": status}


def gaps():
    """读 data/trajectories.json，算缺口，写 data/trajectory_gaps.json 并打表。"""
    trajs = json.loads((DATA / "trajectories.json").read_text(encoding="utf-8"))
    rows = [compute_gap(t) for t in trajs]
    (DATA / "trajectory_gaps.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    hdr = (f"{'company':<11}{'metric':<34}{'latest':>13}{'target':>13}"
           f"{'req/yr':>9}{'ach/yr':>9}{'proj':>8}  status")
    print("\n" + hdr)
    print("-" * len(hdr))
    for r in rows:
        f = lambda v, d=2: "—" if v is None else f"{v:.{d}f}"
        print(f"{r['company'][:10]:<11}{r['metric'][:33]:<34}"
              f"{f(r['latest_value'])+' ('+str(r['latest_year'])+')':>13}"
              f"{f(r['target_value'])+' ('+str(r['target_year'])+')':>13}"
              f"{f(r['required_pace']):>9}{f(r['achieved_pace']):>9}"
              f"{f(r['projected_year'], 0):>8}  {r['status']}")
    print(f"\n{len(rows)} rows → data/trajectory_gaps.json")
    return rows


def main():
    claims = json.loads((DATA / "claims.json").read_text(encoding="utf-8"))
    sentences = json.loads((DATA / "signals.json").read_text(encoding="utf-8"))

    targets = extract_targets(claims)

    # 同公司同指标只抽一次观测值
    observations = {}
    keys = {(t["company"], t["metric"]) for t in targets}
    print(f"\nstep 2: {len(keys)} distinct (company, metric) pairs")
    for company, metric in sorted(keys):
        pool = candidate_pool(metric, company, claims, sentences)
        print(f"  {company} / {metric[:48]} — {len(pool)} candidates")
        observations[(company, metric)] = extract_observations(metric, company, pool)

    trajectories, discarded, audit = pair(targets, observations)
    (DATA / "trajectories.json").write_text(
        json.dumps(trajectories, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "trajectory_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nstep 3: {len(trajectories)} trajectories → data/trajectories.json")
    print(f"        {len(audit)} targets audited → data/trajectory_audit.json")
    for reason, items in discarded.items():
        print(f"  discarded ({reason}): {len(items)}")

    # 按公司分组的丢弃统计：可追踪性本身就是结论
    print(f"\n{'company':<12}{'targets':>8}{'kept':>6}{'1 obs':>7}{'0 obs':>7}{'untrackable':>13}")
    for co in sorted({a["company"] for a in audit}):
        rows = [a for a in audit if a["company"] == co]
        kept = sum(a["outcome"] == "kept" for a in rows)
        one = sum(a["reason"] == "only_one_observation" for a in rows)
        zero = sum(a["reason"] == "no_observations" for a in rows)
        print(f"{co:<12}{len(rows):>8}{kept:>6}{one:>7}{zero:>7}"
              f"{(len(rows) - kept) / len(rows) * 100:>12.1f}%")
    for t in trajectories:
        obs = " → ".join(f"{o['year']}:{o['value']:g}" for o in t["observations"])
        print(f"  {t['company']:<11}{t['metric'][:40]:<42}{obs}  ⇒ "
              f"{t['target_value']:g}{t['unit']} by {t['target_year']}")


if __name__ == "__main__":
    import sys
    if "gaps" in sys.argv[1:]:   # 只跑缺口分析：python -m src.trajectory gaps（零调用）
        gaps()
    else:
        main()
        gaps()
