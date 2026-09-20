#!/usr/bin/env bash
# 三种模式：
#   ./run_all.sh          全部。需要 corpus/*.pdf 和 ANTHROPIC_API_KEY
#   ./run_all.sh offline  跳过需要新 LLM 调用的步骤，但仍需 PDF（从 ingest 开始）
#   ./run_all.sh verify   只跑不依赖 PDF 的步骤，复现所有已报告的数字
#
# verify 是给拿到这个仓库的人用的：PDF 因版权不入库，但派生数据和 LLM 响应缓存都在，
# 所以对照表、消融、敏感性、统计检验全都能零成本重跑。该模式会主动清空 API key —
# 任何缓存未命中都立刻失败，而不是静默发请求。这样"零成本可复现"是被强制的，不是声称的。
set -euo pipefail

PY=.venv/bin/python
MODE="${1:-all}"

run() {  # run <module> <说明>
  echo ""
  echo "=== $1  — $2"
  $PY -m "$1"
}

if [ "$MODE" = "verify" ]; then
  export ANTHROPIC_API_KEY=""     # 强制走缓存；未命中即失败
  echo "verify 模式：不使用 PDF，不发任何网络请求（API key 已清空）"
fi

# ---------------------------------------------------------- Stage 1-2 摄入
# 仅这两步需要原始 PDF / 新 LLM 调用，verify 模式跳过（产物 data/corpus.json
# 与 data/claims.json 已入库）。
if [ "$MODE" != "verify" ]; then
  run src.ingest "corpus/*.pdf                → data/corpus.json"
  if [ "$MODE" != "offline" ]; then
    run src.extract "data/corpus.json          → data/claims.json            [LLM]"
  fi
fi

# ---------------------------------------------------------- Stage 3 特征与候选
run src.rules   "data/claims.json             → data/flagged.json           390 条，9 条规则"
run src.filter  "data/flagged.json            → data/candidates.json        390 → 89"
run src.signals "data/corpus.json             → data/signals.json           4084 句 × 7 标量"

# ---------------------------------------------------------- Stage 4 无监督分析
run src.anomaly      "data/signals.json       → anomaly_*.json + anomaly_pvr.png   13 个段落"
run src.plot_signals "data/signals.json       → figures/sig_*.png"

# ---------------------------------------------------------- Stage 5 分类三轨
run src.test_tree "§10 回归集 12 条，必须全过"
run src.tree      "data/flagged.json          → data/track_r.json           Track R, 0 调用"
run src.termstats "data/signals.json          → data/term_risk.json         Track S, 0 调用"
run src.consensus "R + D + S                  → data/consensus.json         共识层, 0 调用"

# ---------------------------------------------------------- Stage 6 轨迹（需 LLM）
if [ "$MODE" = "all" ]; then
  run src.trajectory "data/corpus.json         → trajectories/gaps/audit     [LLM]"
fi
run src.plot_trajectory "trajectory_gaps.json → figures/trajectory_gap.png"
run src.plot_discard    "trajectory_audit.json → figures/commitment_verifiability.png"

# ---------------------------------------------------------- Stage 7 评测与统计
run src.evaluate    "data/gold.json           → metrics.json + confusion.png   [缓存]"
run src.stats_tests "data/metrics.json        → data/significance.json       Friedman/McNemar"
run src.plot_stats  "data/significance.json   → figures/friedman_*.png"

# ---------------------------------------------------------- Stage 8 审计层
run src.indicators    "prelabels + signals + audit → 四指标与评级"
run src.ablation      "gold + flagged          → data/ablation.json          逐规则消融"
run src.sensitivity   "参数扫描                 → data/sensitivity.json"
run src.rule_evidence "term_risk + flagged     → data/rule_evidence.json     无监督证据"
run src.cost          "cache/                  → data/cost.json              成本核算"
run src.abstain       "metrics + tree          → data/abstain.json           弃答曲线"

# ---------------------------------------------------------- Stage 9 仅完整模式
if [ "$MODE" = "all" ]; then
  run src.prelabel "data/candidates.json       → data/prelabels.json         [LLM]"
  run src.coverage "data/flagged.json          → coverage_gaps.json          [LLM]"
fi

echo ""
case "$MODE" in
  verify)  echo "verify 完成：以上全部未使用 PDF、未发网络请求。" ;;
  offline) echo "offline 完成。跳过: extract / trajectory / prelabel / coverage（需 API key）" ;;
  *)       echo "完成。" ;;
esac
