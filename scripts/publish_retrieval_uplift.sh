#!/usr/bin/env bash
set -euo pipefail

# Publish retrieval MRR uplift (%) from evaluation/weighted_search_results.json to the API gauge.

API_URL=${API_URL:-${API:-http://localhost:8000}}
TOKEN=${TOKEN:-${E2E_ADMIN_TOKEN:-}}
FILE=${FILE:-evaluation/weighted_search_results.json}

if [[ -z "$TOKEN" ]]; then
  echo "ERROR: TOKEN env var not set (admin JWT)." >&2
  exit 1
fi

if [[ ! -f "$FILE" ]]; then
  echo "ERROR: results file not found: $FILE" >&2
  exit 2
fi

echo "== Publish retrieval uplift from $FILE =="

# Compute uplifts from triple-run if present, else baseline vs weighted
if jq -e '.vector and .hybrid and .weighted' "$FILE" >/dev/null 2>&1; then
  HYB=$(jq -r '((.hybrid.metrics.mrr - .vector.metrics.mrr) / (.vector.metrics.mrr + 1e-9) * 100.0)' "$FILE")
  WTD=$(jq -r '((.weighted.metrics.mrr - .vector.metrics.mrr) / (.vector.metrics.mrr + 1e-9) * 100.0)' "$FILE")
  body=$(jq -nc --argjson h "$HYB" --argjson w "$WTD" '{values: {hybrid: $h, weighted: $w}}')
else
  WTD=$(jq -r '((.weighted.mrr - .baseline.mrr) / (.baseline.mrr + 1e-9) * 100.0)' "$FILE")
  body=$(jq -nc --argjson w "$WTD" '{values: {weighted: $w}}')
fi

curl -sS -X POST "$API_URL/_admin/metrics/retrieval_uplift" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "$body" | jq .

echo "✓ Published retrieval uplift"

