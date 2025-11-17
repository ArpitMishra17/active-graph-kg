#!/usr/bin/env bash
set -euo pipefail

API_URL=${API_URL:-${API:-http://localhost:8000}}
TOKEN=${TOKEN:-}
SECOND_TOKEN=${SECOND_TOKEN:-}

if [[ -z "${TOKEN}" || -z "${SECOND_TOKEN}" ]]; then
  echo "ERROR: TOKEN and SECOND_TOKEN must be set for cross-tenant audit." >&2
  exit 1
fi

HDR1=( -H "Authorization: Bearer ${TOKEN}" )
HDR2=( -H "Authorization: Bearer ${SECOND_TOKEN}" )

echo "== Create node under tenant-1 =="
ID=$(curl -sS -X POST "${API_URL}/nodes" "${HDR1[@]}" -H 'Content-Type: application/json' \
  -d '{"classes":["TestDoc"],"props":{"title":"Governance","text":"RLS governance audit"}}' | jq -r .id)

echo "== Read node with SECOND_TOKEN (expect 404) =="
code=$(curl -s -o /dev/null -w "%{http_code}" "${API_URL}/nodes/${ID}" "${HDR2[@]}")
echo "GET /nodes/${ID} with SECOND_TOKEN -> ${code}"

if [[ "$code" != "404" ]]; then
  echo "✗ Governance boundary failed (expected 404)." >&2
  exit 2
fi

echo "✓ Governance audit passed"

