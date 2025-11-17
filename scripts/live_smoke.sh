#!/usr/bin/env bash
set -euo pipefail

# Live end-to-end smoke for Active Graph KG
# - Verifies health, DB info, ANN indexes
# - Exercises CRUD, search (vector+hybrid), and ask streaming
# - Emits traffic to populate Prometheus metrics

API_URL=${API_URL:-${API:-http://localhost:8000}}
TOKEN=${TOKEN:-${E2E_ADMIN_TOKEN:-}}

if [[ -z "${TOKEN}" ]]; then
  echo "ERROR: TOKEN env var not set. Export a single-line JWT into TOKEN." >&2
  exit 1
fi

json() { jq -r "$1" 2>/dev/null || true; }

hdr_auth=( -H "Authorization: Bearer ${TOKEN}" )

echo "== Health =="
curl -sS "${API_URL}/health" | jq . || true

echo "== DB Info =="
curl -sS "${API_URL}/debug/dbinfo" "${hdr_auth[@]}" | jq . || true

echo "== ANN Indexes (list) =="
curl -sS -X POST "${API_URL}/admin/indexes" \
  "${hdr_auth[@]}" -H 'Content-Type: application/json' \
  -d '{"action":"list"}' | jq . || true

echo "== ANN Indexes (ensure) =="
curl -sS -X POST "${API_URL}/admin/indexes" \
  "${hdr_auth[@]}" -H 'Content-Type: application/json' \
  -d '{"action":"ensure"}' | jq . || true

echo "== Embed Info (also updates Prometheus gauges) =="
curl -sS "${API_URL}/debug/embed_info" "${hdr_auth[@]}" | jq . || true

echo "== Nodes (list, limit=20) =="
curl -sS "${API_URL}/nodes?limit=20" "${hdr_auth[@]}" | jq . | wc -l >/dev/null || true
curl -sS "${API_URL}/nodes?limit=20" "${hdr_auth[@]}" | jq 'length'

echo "== Create Node =="
CREATE_RES=$(curl -sS -X POST "${API_URL}/nodes" \
  "${hdr_auth[@]}" -H 'Content-Type: application/json' \
  -d '{"classes":["TestDoc"],"props":{"title":"Live Smoke","text":"This node was created by live_smoke.sh"}}')
NODE_ID=$(echo "$CREATE_RES" | json .id)
echo "Created node: ${NODE_ID}"

echo "== Refresh Node (compute embedding + history) =="
curl -sS -X POST "${API_URL}/nodes/${NODE_ID}/refresh" "${hdr_auth[@]}" | jq . || true

echo "== Search (vector) =="
curl -sS -X POST "${API_URL}/search" \
  "${hdr_auth[@]}" -H 'Content-Type: application/json' \
  -d '{"query":"machine learning","top_k":5,"use_hybrid":false}' | jq '.results | length'

echo "== Search Explain (vector) =="
curl -sS -X POST "${API_URL}/debug/search_explain" \
  "${hdr_auth[@]}" -H 'Content-Type: application/json' \
  -d '{"query":"machine learning","use_hybrid":false,"top_k":5}' | jq '.ann_config'

echo "== Search (hybrid) =="
curl -sS -X POST "${API_URL}/search" \
  "${hdr_auth[@]}" -H 'Content-Type: application/json' \
  -d '{"query":"machine learning","top_k":5,"use_hybrid":true}' | jq '.results | length'

echo "== Ask (stream) =="
# Stream a few lines, then stop (timeout guards long streams)
curl -N -m 20 -X POST "${API_URL}/ask/stream" \
  "${hdr_auth[@]}" -H 'Accept: text/event-stream' -H 'Content-Type: application/json' \
  --data '{"question":"What is machine learning?","stream":true}' | head -n 10 || true

echo "== Hard Delete Node =="
curl -sS -X DELETE "${API_URL}/nodes/${NODE_ID}?hard=true" "${hdr_auth[@]}" | jq . || true

echo "== Burst Searches (populate histograms) =="
for i in $(seq 1 30); do
  curl -sS -X POST "${API_URL}/search" \
    "${hdr_auth[@]}" -H 'Content-Type: application/json' \
    -d '{"query":"ml jobs","top_k":5,"use_hybrid":false}' >/dev/null || true
done

echo "== Prometheus scrape (key lines) =="
curl -sS "${API_URL}/prometheus" | grep -E 'activekg_(ask|search|gating|embedding|rejections|cited|latency)' || true

echo "✓ Live smoke complete"
