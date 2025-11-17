#!/usr/bin/env bash
set -euo pipefail

# Simulate ingestion -> graph -> embeddings -> searchable path

API_URL=${API_URL:-${API:-http://localhost:8000}}
TOKEN=${TOKEN:-${E2E_ADMIN_TOKEN:-}}

if [[ -z "${TOKEN}" ]]; then
  echo "ERROR: TOKEN env var not set (admin JWT)." >&2
  exit 1
fi

HDR=( -H "Authorization: Bearer ${TOKEN}" )

echo "== Baseline embed info =="
curl -sS "${API_URL}/_admin/embed_info" "${HDR[@]}" | jq '.counts'

echo "== Create a document (ingestion stand-in) =="
t0=$(date +%s)
RES=$(curl -sS -X POST "${API_URL}/nodes" "${HDR[@]}" -H 'Content-Type: application/json' \
  -d '{"classes":["Document"],"props":{"title":"Ingest Doc","text":"This is a pipeline integrity test."}}')
ID=$(echo "$RES" | jq -r .id)

echo "== Force refresh to embed =="
curl -sS -X POST "${API_URL}/nodes/${ID}/refresh" "${HDR[@]}" >/dev/null

echo "== Wait until searchable (search hits >=1) =="
for i in {1..10}; do
  hits=$(curl -sS -X POST "${API_URL}/search" "${HDR[@]}" -H 'Content-Type: application/json' \
    -d '{"query":"pipeline integrity test","top_k":3,"use_hybrid":false}' | jq -r '.results|length')
  if [[ "$hits" != "0" ]]; then break; fi
  sleep 1
done
t1=$(date +%s)
echo "End-to-end latency: $((t1 - t0))s"

echo "✓ Ingestion pipeline integrity test complete"

