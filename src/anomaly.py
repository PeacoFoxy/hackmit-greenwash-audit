"""Company-level PVR / z-scores and passage-level flag-density anomalies. Deterministic, no model calls."""
import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from src.rules import flags as rule_flags

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FIGS = ROOT / "figures"

SIGNAL_KEYS = ["vagueness", "numeric", "hedge", "future", "flags", "verification", "specificity"]
# Higher composite = more suspect: vagueness, hedging, promises and rule hits count
# positive; figures, verification mentions and specificity count negative.
COMPOSITE_SIGN = {"vagueness": +1, "hedge": +1, "future": +1, "flags": +1,
                  "numeric": -1, "verification": -1, "specificity": -1}
MIN_REGION = 5
SMOOTH_WINDOW = 20
# Same set as PRECISE_FLAGS in evaluate.py: SCOPE_BOUNDARY_UNCLEAR fires far too widely
# to carry information, so it is excluded from the density.
PRECISE_FLAGS = {
    "SCOPE2_METHOD_UNSTATED", "MATCHING_LANGUAGE", "OFFSET_UNDISCLOSED", "NO_BASELINE_YEAR",
    "GRID_MISMATCH_RISK", "CHERRY_PICKED_METRIC", "WATER_ACCOUNTING_VAGUE",
    "FUTURE_PROMISE_NO_MILESTONE",
}
COLORS = {"Alphabet": "#4269d0", "Microsoft": "#efb118", "Amazon": "#ff725c"}


def load():
    rows = json.loads((DATA / "signals.json").read_text(encoding="utf-8"))
    groups = {}
    for r in rows:
        groups.setdefault(r["company"], []).append(r)
    return groups


def company_stats(groups):
    means = {c: {k: float(np.mean([r[k] for r in g])) for k in SIGNAL_KEYS}
             for c, g in groups.items()}
    companies = list(groups)

    # z-scores compare companies against each other (n=3, population standard deviation)
    z = {c: {} for c in companies}
    for k in SIGNAL_KEYS:
        vals = np.array([means[c][k] for c in companies])
        sd = vals.std()
        for c, v in zip(companies, vals):
            z[c][k] = float((v - vals.mean()) / sd) if sd > 0 else 0.0

    out = []
    for c in companies:
        g = groups[c]
        n = len(g)
        fsum = sum(r["future"] for r in g)
        vsum = sum(r["verification"] for r in g)
        future_interval = n / fsum if fsum else float("inf")
        verif_interval = n / vsum if vsum else float("inf")
        pvr = verif_interval / future_interval if future_interval else float("inf")
        out.append({
            "company": c, "sentences": n,
            "future_total": fsum, "verification_total": vsum,
            "future_interval": round(future_interval, 2),
            "verification_interval": round(verif_interval, 2),
            "pvr": round(pvr, 3),
            "means": {k: round(means[c][k], 4) for k in SIGNAL_KEYS},
            "z": {k: round(z[c][k], 3) for k in SIGNAL_KEYS},
            "composite": round(sum(COMPOSITE_SIGN[k] * z[c][k] for k in SIGNAL_KEYS), 3),
        })
    return out


def smooth(values, window=SMOOTH_WINDOW):
    """Moving average; at the edges it averages only over samples that exist."""
    v = np.asarray(values, dtype=float)
    kernel = np.ones(window) / window
    norm = np.convolve(np.ones(len(v)), kernel, mode="same")
    return np.convolve(v, kernel, mode="same") / norm


def regions(groups):
    out = []
    for c, g in groups.items():
        # Recompute density locally over high-precision flags only. signals.json is left
        # untouched, because the plots still use the full flag set.
        per_sent = [[f for f in rule_flags(r["text"]) if f in PRECISE_FLAGS] for r in g]
        vals = smooth([len(f) for f in per_sent])
        thr = float(vals.mean() + 2 * vals.std())
        hot = vals > thr
        print(f"{c}  threshold {thr:.3f} (high-precision flags only)")

        i, found = 0, 0
        while i < len(hot):
            if not hot[i]:
                i += 1
                continue
            j = i
            while j < len(hot) and hot[j]:
                j += 1
            types = Counter(f for fs in per_sent[i:j] for f in fs)
            # Smoothing lets a nearby peak bleed into a stretch with no hits at all.
            # Such a passage opens empty, so it is a false positive.
            if j - i >= MIN_REGION and types:
                seg = g[i:j]
                text = " ".join(r["text"] for r in seg)
                out.append({
                    "company": c, "threshold": round(thr, 4),
                    "start_sent_id": seg[0]["sent_id"], "end_sent_id": seg[-1]["sent_id"],
                    "n_sentences": len(seg),
                    "rel_pos": [seg[0]["rel_pos"], seg[-1]["rel_pos"]],
                    "peak": round(float(vals[i:j].max()), 4),
                    "flag_types": dict(types.most_common()),
                    "text": text[:400],
                })
                found += 1
                print(f"  [{found}] {seg[0]['sent_id']} → {seg[-1]['sent_id']}  "
                      f"{len(seg)} sent, rel {seg[0]['rel_pos']:.3f}–{seg[-1]['rel_pos']:.3f}, "
                      f"peak {out[-1]['peak']:.3f}")
                for f, n in types.most_common():
                    print(f"        {f:<30}{n}")
            i = j
        print(f"  -> {found} passages\n")
    return out


def plot_pvr(stats):
    FIGS.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    names = [s["company"] for s in stats]
    vals = [s["pvr"] for s in stats]
    bars = ax.bar(names, vals, color=[COLORS.get(n, "#888") for n in names], width=0.55)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.2f}", ha="center", va="bottom")
    ax.set_ylabel("PVR = verification interval / future interval")
    ax.set_title("Promise-to-verification ratio (higher = more promises per verification)")
    ax.set_ylim(0, max(vals) * 1.18)
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    fig.savefig(FIGS / "anomaly_pvr.png", dpi=120)
    plt.close(fig)


def main():
    groups = load()
    stats = company_stats(groups)
    (DATA / "anomaly_company.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{'company':<12}{'PVR':>8}{'future/sent':>13}{'verif/sent':>12}{'composite':>11}")
    for s in stats:
        print(f"{s['company']:<12}{s['pvr']:>8.2f}{s['future_total']:>11}"
              f"{s['verification_total']:>11}{s['composite']:>11.2f}")

    print()
    regs = regions(groups)
    (DATA / "anomaly_regions.json").write_text(
        json.dumps(regs, ensure_ascii=False, indent=1), encoding="utf-8")

    plot_pvr(stats)
    print("\n→ data/anomaly_company.json, data/anomaly_regions.json, figures/anomaly_pvr.png")


if __name__ == "__main__":
    main()
