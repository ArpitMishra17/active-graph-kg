#!/usr/bin/env bash
set -euo pipefail

API_URL=${API_URL:-${API:-http://localhost:8000}}
QUERIES=${QUERIES:-evaluation/datasets/test_queries.json}
REPEATS=${REPEATS:-5}
MODE=${MODE:-vector} # vector|hybrid

queries=()
if [[ -f "$QUERIES" ]]; then
  # Extract simple list of query texts
  queries=($(jq -r '.[] | if type=="object" then .text else . end' "$QUERIES"))
else
  queries=("machine learning" "graph rag" "postgres vector search")
fi

lat=()
for q in "${queries[@]}"; do
  for i in $(seq 1 "$REPEATS"); do
    t0=$(date +%s%3N)
    if [[ "$MODE" == "hybrid" ]]; then
      curl -sS -X POST "$API_URL/search" -H 'Content-Type: application/json' \
        -d "{\"query\":\"$q\",\"top_k\":5,\"use_hybrid\":true}" >/dev/null
    else
      curl -sS -X POST "$API_URL/search" -H 'Content-Type: application/json' \
        -d "{\"query\":\"$q\",\"top_k\":5,\"use_hybrid\":false}" >/dev/null
    fi
    t1=$(date +%s%3N)
    lat+=( $((t1 - t0)) )
  done
done

# Compute percentiles
sorted=($(printf '%s\n' "${lat[@]}" | sort -n))
n=${#sorted[@]}
if [[ "$n" -eq 0 ]]; then
  echo "No latency samples collected"
  exit 1
fi

idx_p() { # percentile in ms
  local p=$1
  local pos=$(python3 - <<PY
import math
n=$n
p=$p
print(int(max(0, min(n-1, round((p/100.0)*(n-1))))))
PY
)
  echo ${sorted[$pos]}
}

p50=$(idx_p 50)
p95=$(idx_p 95)
p99=$(idx_p 99)

echo "Mode: $MODE | Samples: $n"
echo "p50: ${p50}ms"
echo "p95: ${p95}ms"
echo "p99: ${p99}ms"

