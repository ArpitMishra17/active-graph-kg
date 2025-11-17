#!/usr/bin/env bash
set -euo pipefail

# Lightweight TCO snapshot: CPU/mem for API, PG sizes

DSN=${ACTIVEKG_DSN:-postgresql://activekg:activekg@localhost:5432/activekg}
API_PID=$(pgrep -f 'uvicorn activekg.api.main:app' || true)

echo "== API Process (uvicorn) =="
if [[ -n "$API_PID" ]]; then
  ps -o pid,%cpu,%mem,rss,etime,cmd -p "$API_PID"
else
  echo "API process not found"
fi

echo
echo "== Postgres table/index sizes (bytes) =="
psql "$DSN" -Atc "\
SELECT 'nodes' AS rel, pg_total_relation_size('nodes') AS bytes \
UNION ALL \
SELECT indexname, pg_total_relation_size(indexname::regclass) \
FROM pg_indexes WHERE schemaname='public' AND tablename='nodes' \
ORDER BY bytes DESC;"

echo
echo "(Estimate storage $/GB by applying your infra rates to the above sizes)"
echo "✓ TCO snapshot complete"

