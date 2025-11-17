#!/usr/bin/env bash
set -euo pipefail

API_URL=${API_URL:-${API:-http://localhost:8000}}
DATASET=${DATASET:-evaluation/datasets/qa_questions.json}
TIMEOUT=${TIMEOUT:-30}
OUT=${OUT:-evaluation/llm_qa_results.json}

echo "== LLM Q&A Benchmark (Accuracy, Citations, Latency) =="
if [[ -n "${TOKEN:-}" ]]; then
  python3 evaluation/llm_qa_eval.py \
    --api-url "$API_URL" \
    --dataset "$DATASET" \
    --timeout "$TIMEOUT" \
    --output "$OUT" \
    --token "$TOKEN"
else
  python3 evaluation/llm_qa_eval.py \
    --api-url "$API_URL" \
    --dataset "$DATASET" \
    --timeout "$TIMEOUT" \
    --output "$OUT"
fi

echo "✓ Wrote $OUT"
