#!/usr/bin/env bash
set -euo pipefail

DSN=${ACTIVEKG_DSN:-postgresql://activekg:activekg@localhost:5432/activekg}

echo "== Index Size Metrics (bytes) =="
psql "$DSN" -Atc "\
SELECT indexname, pg_total_relation_size(indexname::regclass) AS bytes \
FROM pg_indexes \
WHERE schemaname='public' AND tablename='nodes' AND indexname LIKE 'idx_nodes_%' \
ORDER BY bytes DESC;"

echo
echo "== Table Size (nodes) =="
psql "$DSN" -Atc "SELECT pg_total_relation_size('nodes') AS bytes;"

echo "✓ DB index metrics printed"

