#!/usr/bin/env sh
set -eu

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
WORKERS="${WORKERS:-2}"

exec uvicorn activekg.api.main:app --host "$HOST" --port "$PORT" --workers "$WORKERS"
