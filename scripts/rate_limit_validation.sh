#!/usr/bin/env bash
set -euo pipefail

# Validate rate limiting behavior by generating bursts and checking 429 + Retry-After

API_URL=${API_URL:-${API:-http://localhost:8000}}
TOKEN=${TOKEN:-${E2E_ADMIN_TOKEN:-}}
ENDPOINT=${ENDPOINT:-/nodes?limit=1}
ATTEMPTS=${ATTEMPTS:-60}
SLEEP_BETWEEN=${SLEEP_BETWEEN:-0.02} # 20ms between requests

if [[ -z "${TOKEN}" ]]; then
  echo "ERROR: TOKEN env var not set. Export a single-line JWT into TOKEN." >&2
  exit 1
fi

hdr_auth=( -H "Authorization: Bearer ${TOKEN}" )

echo "== Rate Limit Validation =="
echo "Target: ${API_URL}${ENDPOINT} (attempts=${ATTEMPTS})"
echo "Note: Ensure RATE_LIMIT_ENABLED=true and REDIS_URL is configured before running."

codes=()
retry_after=""

for i in $(seq 1 "$ATTEMPTS"); do
  # Capture headers and status
  out=$(mktemp)
  code=$(curl -s -D "$out" -o /dev/null -w "%{http_code}" "${API_URL}${ENDPOINT}" "${hdr_auth[@]}") || true
  codes+=("$code")

  if [[ "$code" == "429" && -z "$retry_after" ]]; then
    retry_after=$(grep -i '^Retry-After:' "$out" | awk '{print $2}' | tr -d '\r' || true)
  fi

  rm -f "$out"
  # brief pacing
  sleep "$SLEEP_BETWEEN"
done

# Summaries
total=${#codes[@]}
rc200=$(printf '%s
' "${codes[@]}" | awk '$1==200{c++} END{print c+0}')
rc429=$(printf '%s
' "${codes[@]}" | awk '$1==429{c++} END{print c+0}')
rc_other=$(printf '%s
' "${codes[@]}" | awk '$1!=200 && $1!=429{c++} END{print c+0}')

echo "Total: $total | 200: $rc200 | 429: $rc429 | other: $rc_other"

if [[ "$rc429" -gt 0 ]]; then
  echo "First Retry-After observed: ${retry_after:-unknown}s"
  if [[ -n "$retry_after" ]]; then
    echo "Sleeping ${retry_after}s and retrying a search (should be 200)"
    sleep "$retry_after"
    code2=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${API_URL}/search" \
      "${hdr_auth[@]}" -H 'Content-Type: application/json' -d '{"query":"rl test","top_k":1,"use_hybrid":false}')
    echo "POST /search after wait -> ${code2}"
  fi
else
  echo "No 429 observed. Ensure RATE_LIMIT_ENABLED=true and limits are low enough to trigger."
fi

echo "✓ Rate limit validation complete"
