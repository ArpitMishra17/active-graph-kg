#!/usr/bin/env bash
set -euo pipefail

DSN=${ACTIVEKG_DSN:-${DATABASE_URL:-}}
if [[ -z "${DSN}" ]]; then
  echo "ERROR: ACTIVEKG_DSN or DATABASE_URL must be set" >&2
  exit 1
fi

echo "Using DSN: ${DSN}"

echo "Ensuring pgvector extension..."
psql "${DSN}" -c "CREATE EXTENSION IF NOT EXISTS vector;" || true

echo "Applying base schema..."
psql "${DSN}" -f db/init.sql

if [[ -f db/migrations/add_text_search.sql ]]; then
  echo "Applying optional text search migration..."
  psql "${DSN}" -f db/migrations/add_text_search.sql || true
fi

echo "Applying RLS policies..."
psql "${DSN}" -f enable_rls_policies.sql

echo "Bootstrap complete."

