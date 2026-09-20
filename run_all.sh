#!/usr/bin/env bash
# Three modes:
#   ./run_all.sh          everything. Needs corpus/*.pdf and ANTHROPIC_API_KEY
#   ./run_all.sh offline  skips steps that need new model calls, still needs the PDFs
#   ./run_all.sh verify   only the steps that need no PDF; reproduces every reported number
#
# verify is for whoever clones this repository. The PDFs are not committed (published
# corporate documents), but the derived data and the model-response cache are, so the
# comparison table, ablation, sensitivity sweeps and significance tests all re-run at zero
# cost. The mode clears the API key first, so a cache miss fails immediately instead of
# quietly sending a request: reproducibility is enforced here, not asserted.
set -euo pipefail

PY=.venv/bin/python
MODE="${1:-all}"

run() {  # run <module> <description>
  echo ""
  echo "=== $1  — $2"
  $PY -m "$1"
}

if [ "$MODE" = "verify" ]; then
  export ANTHROPIC_API_KEY=""     # force the cache; a miss is a failure
  echo "verify mode: no PDFs, no network requests (API key cleared)"
fi

# ---------------------------------------------------------- Stage 1-2  ingest
# Only these two need the source PDFs or new model calls, so verify skips them; their
# outputs (data/corpus.json, data/claims.json) are committed.
if [ "$MODE" != "verify" ]; then
  run src.ingest "corpus/*.pdf                → data/corpus.json"
  if [ "$MODE" != "offline" ]; then
    run src.extract "data/corpus.json          → data/claims.json            [LLM]"
  fi
fi

# ---------------------------------------------------------- Stage 3  features
run src.rules   "data/claims.json             → data/flagged.json           390 claims, 9 rules"
run src.filter  "data/flagged.json            → data/candidates.json        390 → 89"
run src.signals "data/corpus.json             → data/signals.json           4084 sentences x 7 signals"

# ---------------------------------------------------------- Stage 4  unsupervised
run src.anomaly      "data/signals.json       → anomaly_*.json + anomaly_pvr.png   13 passages"
run src.plot_signals "data/signals.json       → figures/sig_*.png"

# ---------------------------------------------------------- Stage 5  three tracks
run src.test_tree "12 regression cases from spec sec.10, all must pass"
run src.tree      "data/flagged.json          → data/track_r.json           Track R, 0 model calls"
run src.termstats "data/signals.json          → data/term_risk.json         Track S, 0 model calls"
run src.consensus "R + D + S                  → data/consensus.json         consensus layer, 0 calls"

# ---------------------------------------------------------- Stage 6  trajectory (model)
if [ "$MODE" = "all" ]; then
  run src.trajectory "data/corpus.json         → trajectories/gaps/audit     [LLM]"
fi
run src.plot_trajectory "trajectory_gaps.json → figures/trajectory_gap.png"
run src.plot_discard    "trajectory_audit.json → figures/commitment_verifiability.png"

# ---------------------------------------------------------- Stage 7  evaluation
run src.evaluate    "data/gold.json           → metrics.json + confusion.png   [cached]"
run src.stats_tests "data/metrics.json        → data/significance.json       Friedman/McNemar"
run src.plot_stats  "data/significance.json   → figures/friedman_*.png"

# ---------------------------------------------------------- Stage 8  audit layer
run src.indicators    "prelabels + signals + audit -> four indicators and grade"
run src.ablation      "gold + flagged          → data/ablation.json          per-rule ablation"
run src.sensitivity   "parameter sweeps         -> data/sensitivity.json"
run src.experiments.rule_evidence "term_risk + flagged → data/rule_evidence.json  REJECTED experiment"
run src.cost          "cache/                  → data/cost.json              cost accounting"
run src.experiments.abstain       "metrics + tree      → data/abstain.json        REJECTED experiment"
run src.merge_expand  "blind_expand.csv        → gold_expand + expand_eval   per-rule blind verdicts"
run src.experiments.evidence_tier "gold + gold_expand  → data/evidence_tier.json  REJECTED experiment"
run src.headline      "everything              → data/headline.json          4 corpus-level percentages"

# ---------------------------------------------------------- Stage 9  full mode only
if [ "$MODE" = "all" ]; then
  run src.prelabel "data/candidates.json       → data/prelabels.json         [LLM]"
  run src.coverage "data/flagged.json          → coverage_gaps.json          [LLM]"
fi

echo ""
case "$MODE" in
  verify)  echo "verify complete: no PDF was read and no network request was sent." ;;
  offline) echo "offline complete. Skipped: extract / trajectory / prelabel / coverage (need a key)" ;;
  *)       echo "Done." ;;
esac
