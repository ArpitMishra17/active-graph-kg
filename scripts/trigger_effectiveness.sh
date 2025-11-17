#!/usr/bin/env bash
set -euo pipefail

# Measure trigger engine effectiveness: ingest -> trigger -> refresh

API_URL=${API_URL:-${API:-http://localhost:8000}}
TOKEN=${TOKEN:-${E2E_ADMIN_TOKEN:-}}

if [[ -z "${TOKEN}" ]]; then
  echo "ERROR: TOKEN env var not set (admin JWT)." >&2
  exit 1
fi

HDR=( -H "Authorization: Bearer ${TOKEN}" )
name="trg_live_$RANDOM"

echo "== Register trigger pattern: $name =="
curl -sS -X POST "${API_URL}/triggers" "${HDR[@]}" -H 'Content-Type: application/json' \
  -d "{\"name\":\"$name\",\"example_text\":\"Alpha Beta Gamma\",\"description\":\"Trigger test\"}" | jq .

echo "== Create node with triggers referencing $name =="
RES=$(curl -sS -X POST "${API_URL}/nodes" "${HDR[@]}" -H 'Content-Type: application/json' \
  -d "{\"classes\":[\"TestDoc\"],\"props\":{\"title\":\"Trig Node\",\"text\":\"Alpha Beta Gamma matches\"},\"triggers\":[{\"name\":\"$name\",\"threshold\":0.80}]}")
NODE_ID=$(echo "$RES" | jq -r .id)
if [[ -z "$NODE_ID" || "$NODE_ID" == "null" ]]; then
  echo "ERROR: Node creation failed. Response: $RES" >&2
  exit 2
fi
echo "Node: $NODE_ID"

echo "== Manual refresh to compute embedding and post-refresh trigger check =="
curl -sS -X POST "${API_URL}/nodes/${NODE_ID}/refresh" "${HDR[@]}" | jq .

echo "== Wait for trigger_fired event (poll 10s) =="
fired=0
for i in {1..10}; do
  ev=$(curl -sS "${API_URL}/events?node_id=${NODE_ID}&event_type=trigger_fired&limit=1" "${HDR[@]}" | jq -r '.events|length')
  if [[ "$ev" != "0" ]]; then fired=1; break; fi
  sleep 1
done

if [[ "$fired" == "1" ]]; then
  echo "✓ Trigger fired for node ${NODE_ID}"
else
  echo "✗ Trigger did not fire (check scheduler or thresholds)"
fi

echo "== Cleanup pattern =="
curl -sS -X DELETE "${API_URL}/triggers/${name}" "${HDR[@]}" | jq .

echo "✓ Trigger effectiveness test done"
