#!/usr/bin/env bash
# 完整管线，按依赖顺序。标 [LLM] 的步骤命中缓存时不发请求（cache/ 里有 40 个调用）。
# 用法:  ./run_all.sh          跑全部
#        ./run_all.sh offline  跳过需要新调用的步骤，只跑确定性层
set -euo pipefail

PY=.venv/bin/python
MODE="${1:-all}"

run() {  # run <module> <说明>
  echo ""
  echo "=== $1  — $2"
  $PY -m "$1"
}

# ---------------------------------------------------------- Stage 1-2 摄入
run src.ingest   "corpus/*.pdf                 → data/corpus.json"

# ---------------------------------------------------------- Stage 3 特征与候选
if [ "$MODE" != "offline" ]; then
  run src.extract "data/corpus.json             → data/claims.json            [LLM]"
fi
run src.rules    "data/claims.json              → data/flagged.json           (v1 flags)"
run src.filter   "data/flagged.json             → data/candidates.json        390 → 89"
run src.signals  "data/corpus.json              → data/signals.json           4084 句 × 7 标量"

# ---------------------------------------------------------- Stage 4 无监督分析
run src.anomaly      "data/signals.json         → data/anomaly_*.json + figures/anomaly_pvr.png"
run src.plot_signals "data/signals.json         → figures/sig_*.png"

# ---------------------------------------------------------- Stage 5 分类层（三条 track）
run src.test_tree "§10 回归集 12 条，必须全过"
run src.tree      "data/flagged.json            → data/track_r.json           Track R, 0 调用"
run src.termstats "data/signals.json            → data/term_risk.json         Track S, 0 调用"
run src.consensus "R + D + S                    → data/consensus.json         共识层, 0 调用"

# ---------------------------------------------------------- Stage 6 评测与缺口
if [ "$MODE" != "offline" ]; then
  run src.evaluate "data/gold.json              → data/metrics.json + figures/confusion.png  [LLM]"
  run src.coverage "data/flagged.json           → data/coverage_gaps.json + proposed_rules.json  [LLM]"
fi

echo ""
echo "完成。离线模式跳过的步骤: extract / evaluate / coverage（需要 ANTHROPIC_API_KEY）"
