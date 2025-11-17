#!/usr/bin/env bash
set -euo pipefail

API_URL=${API_URL:-${API:-http://localhost:8000}}
QUERIES=${QUERIES:-evaluation/datasets/test_queries.json}
GROUND=${GROUND:-evaluation/datasets/ground_truth.json}
TOPK=${TOPK:-20}
OUT=${OUT:-evaluation/weighted_search_results.json}

echo "== Retrieval Quality (Recall@k, MRR, NDCG) =="
if [[ -n "${TOKEN:-}" ]]; then
  python3 evaluation/weighted_search_eval.py \
    --api-url "$API_URL" \
    --queries "$QUERIES" \
    --ground-truth "$GROUND" \
    --top-k "$TOPK" \
    --output "$OUT" \
    --token "$TOKEN" \
    --triple
else
  python3 evaluation/weighted_search_eval.py \
    --api-url "$API_URL" \
    --queries "$QUERIES" \
    --ground-truth "$GROUND" \
    --top-k "$TOPK" \
    --output "$OUT" \
    --triple
fi

echo "✓ Wrote $OUT"
