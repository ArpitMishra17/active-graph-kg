#!/usr/bin/env bash
set -euo pipefail

API_URL=${API_URL:-${API:-http://localhost:8000}}
TOKEN=${TOKEN:-${E2E_ADMIN_TOKEN:-}}

if [[ -z "${TOKEN}" ]]; then
  echo "ERROR: TOKEN env var not set (admin JWT)." >&2
  exit 1
fi

HDR=( -H "Authorization: Bearer ${TOKEN}" )

echo "== Scheduler metrics summary =="
curl -sS "${API_URL}/_admin/metrics_summary" "${HDR[@]}" | jq .

echo "Note: Inter-run intervals and run counts are visible via Prometheus series:"
echo " - activekg_schedule_runs_total"
echo " - activekg_schedule_inter_run_seconds_bucket"
echo " - activekg_node_refresh_latency_seconds_bucket"

echo
echo "Suggested SLA Targets (dev):"
echo " - Refresh jitter: ±10s for minute-scale intervals"
echo " - Due→refreshed latency: 99% under 1.5× configured interval"
echo " - Trigger cycle: completes within < 2s for small corpora"

echo "✓ Scheduler SLA probe complete"
