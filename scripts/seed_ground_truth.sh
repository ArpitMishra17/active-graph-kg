#!/usr/bin/env bash
set -euo pipefail

# Seed evaluation/datasets/ground_truth.json from current corpus by querying /search
# Modes:
#  - threshold (default): include all result IDs with similarity >= THRESH
#  - topk: include top K results regardless of similarity

API_URL=${API_URL:-${API:-http://localhost:8000}}
TOKEN=${TOKEN:-}
QUERIES=${QUERIES:-evaluation/datasets/test_queries.json}
GROUND=${GROUND:-evaluation/datasets/ground_truth.json}
MODE=${MODE:-threshold}        # threshold|topk
THRESH=${THRESH:-0.20}         # similarity cutoff (0..1)
TOPK=${TOPK:-10}
HYBRID=${HYBRID:-false}

echo "== Seeding ground truth from queries in $QUERIES =="

if [[ ! -f "$QUERIES" ]]; then
  echo "ERROR: Queries file not found: $QUERIES" >&2
  exit 1
fi

tmp=$(mktemp)
echo "{}" > "$tmp"

len=$(jq 'length' "$QUERIES")
for idx in $(seq 0 $((len-1))); do
  q=$(jq -r ".[$idx] | if type==\"object\" then .text else . end" "$QUERIES")
  echo "-- Query: $q"
  body=$(jq -nc --arg q "$q" --argjson uh "$HYBRID" --argjson tk "$TOPK" '{query:$q, top_k: ($tk|tonumber), use_hybrid: ($uh|tostring | test("true";"i")) }')
  if [[ -n "$TOKEN" ]]; then
    resp=$(curl -sS -X POST "$API_URL/search" -H 'Content-Type: application/json' -H "Authorization: Bearer $TOKEN" -d "$body")
  else
    resp=$(curl -sS -X POST "$API_URL/search" -H 'Content-Type: application/json' -d "$body")
  fi
  count=$(echo "$resp" | jq -r '.results|length')
  echo "   results: $count"
  ids=()
  if [[ "$MODE" == "topk" ]]; then
    ids_json=$(echo "$resp" | jq -c --argjson k "$TOPK" '.results[:$k] | map(.id)')
  else
    ids_json=$(echo "$resp" | jq -c --argjson t "$THRESH" '.results | map(select(.similarity >= ($t|tonumber)) | .id)')
  fi
  # Merge into ground truth map
  jq --arg q "$q" --argjson ids "$ids_json" '. + {($q): $ids}' "$tmp" > "$tmp.new" && mv "$tmp.new" "$tmp"
done

mkdir -p "$(dirname "$GROUND")"
mv "$tmp" "$GROUND"
echo "✓ Wrote $GROUND"

# Optional: seed QA relevant_node_ids by searching with the question text
QA_FILE=${QA_FILE:-evaluation/datasets/qa_questions.json}
if [[ -f "$QA_FILE" ]]; then
  echo "== Updating QA relevant_node_ids in $QA_FILE (threshold=$THRESH, hybrid=$HYBRID) =="
  qa_tmp=$(mktemp)
  cp "$QA_FILE" "$qa_tmp"
  qa_len=$(jq 'length' "$qa_tmp")
  for idx in $(seq 0 $((qa_len-1))); do
    q=$(jq -r ".[$idx].question" "$qa_tmp")
    body=$(jq -nc --arg q "$q" --argjson uh "$HYBRID" --argjson tk "$TOPK" '{query:$q, top_k: ($tk|tonumber), use_hybrid: ($uh|tostring | test("true";"i")) }')
    if [[ -n "$TOKEN" ]]; then
      resp=$(curl -sS -X POST "$API_URL/search" -H 'Content-Type: application/json' -H "Authorization: Bearer $TOKEN" -d "$body")
    else
      resp=$(curl -sS -X POST "$API_URL/search" -H 'Content-Type: application/json' -d "$body")
    fi
    ids_json=$(echo "$resp" | jq -c --argjson t "$THRESH" '.results | map(select(.similarity >= ($t|tonumber)) | .id)')
    jq --argjson ids_var "$ids_json" ".[$idx].relevant_node_ids = \$ids_var" "$qa_tmp" > "$qa_tmp.new" && mv "$qa_tmp.new" "$qa_tmp"
  done
  mv "$qa_tmp" "$QA_FILE"
  echo "✓ Updated $QA_FILE"
fi

