#!/usr/bin/env bash
set -euo pipefail

# Developer Experience timing: time to first searchable answer (approx)

API_URL=${API_URL:-${API:-http://localhost:8000}}
TOKEN=${TOKEN:-${E2E_ADMIN_TOKEN:-}}

if [[ -z "${TOKEN}" ]]; then
  echo "ERROR: TOKEN env var not set (admin JWT)." >&2
  exit 1
fi

HDR=( -H "Authorization: Bearer ${TOKEN}" )

echo "== Health check =="
t0=$(date +%s)
curl -sS "${API_URL}/health" | jq . >/dev/null

echo "== Create node and refresh =="
RES=$(curl -sS -X POST "${API_URL}/nodes" "${HDR[@]}" -H 'Content-Type: application/json' \
  -d '{"classes":["DX"],"props":{"title":"DX timing","text":"Time to first answer"}}')
ID=$(echo "$RES" | jq -r .id)
curl -sS -X POST "${API_URL}/nodes/${ID}/refresh" "${HDR[@]}" >/dev/null

echo "== Search until result appears =="
for i in {1..10}; do
  hits=$(curl -sS -X POST "${API_URL}/search" "${HDR[@]}" -H 'Content-Type: application/json' \
    -d '{"query":"DX timing","top_k":3,"use_hybrid":false}' | jq -r '.results|length')
  if [[ "$hits" != "0" ]]; then break; fi
  sleep 1
done
t1=$(date +%s)
echo "Time to first searchable answer: $((t1 - t0))s"

echo "✓ DX timing probe complete"

