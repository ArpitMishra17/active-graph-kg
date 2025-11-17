SHELL := /bin/bash

.PHONY: live-smoke live-extended metrics-probe proof-report rate-limit-validate \
	trigger-effectiveness ingestion-pipeline scheduler-sla governance-audit \
	failure-recovery dx-timing demo-run open-grafana

API ?= http://localhost:8000

live-smoke:
	@API=$$API TOKEN=$$TOKEN bash scripts/live_smoke.sh

live-extended:
	@API=$$API TOKEN=$$TOKEN SECOND_TOKEN=$$SECOND_TOKEN bash scripts/live_extended.sh

metrics-probe:
	@API=$$API bash scripts/metrics_probe.sh

proof-report:
	@API=$$API TOKEN=$$TOKEN OUT=$${OUT:-evaluation/PROOF_POINTS_REPORT.md} bash scripts/proof_points_report.sh

rate-limit-validate:
	@API=$$API TOKEN=$$TOKEN bash scripts/rate_limit_validation.sh

retrieval-quality:
	@API=$$API QUERIES=$${QUERIES:-evaluation/datasets/test_queries.json} \
	GROUND=$${GROUND:-evaluation/datasets/ground_truth.json} \
	TOPK=$${TOPK:-20} OUT=$${OUT:-evaluation/weighted_search_results.json} \
	bash scripts/retrieval_quality.sh

qa-benchmark:
	@API=$$API DATASET=$${DATASET:-evaluation/datasets/qa_questions.json} \
	TIMEOUT=$${TIMEOUT:-30} OUT=$${OUT:-evaluation/llm_qa_results.json} \
	bash scripts/qa_benchmark.sh

search-latency-vector:
	@API=$$API QUERIES=$${QUERIES:-evaluation/datasets/test_queries.json} \
	REPEATS=$${REPEATS:-5} MODE=vector bash scripts/search_latency_eval.sh

search-latency-hybrid:
	@API=$$API QUERIES=$${QUERIES:-evaluation/datasets/test_queries.json} \
	REPEATS=$${REPEATS:-3} MODE=hybrid bash scripts/search_latency_eval.sh

db-index-metrics:
	@ACTIVEKG_DSN=$${ACTIVEKG_DSN:-postgresql://activekg:activekg@localhost:5432/activekg} \
	bash scripts/db_index_metrics.sh

tco-snapshot:
	@ACTIVEKG_DSN=$${ACTIVEKG_DSN:-postgresql://activekg:activekg@localhost:5432/activekg} \
	bash scripts/tco_snapshot.sh

seed-ground-truth:
	@API=$$API TOKEN=$$TOKEN QUERIES=$${QUERIES:-evaluation/datasets/test_queries.json} \
	GROUND=$${GROUND:-evaluation/datasets/ground_truth.json} \
	MODE=$${MODE:-threshold} THRESH=$${THRESH:-0.20} TOPK=$${TOPK:-10} HYBRID=$${HYBRID:-false} \
	bash scripts/seed_ground_truth.sh

trigger-effectiveness:
	@API=$$API TOKEN=$$TOKEN bash scripts/trigger_effectiveness.sh

ingestion-pipeline:
	@API=$$API TOKEN=$$TOKEN bash scripts/ingestion_pipeline.sh

scheduler-sla:
	@API=$$API TOKEN=$$TOKEN bash scripts/scheduler_sla.sh

governance-audit:
	@API=$$API TOKEN=$$TOKEN SECOND_TOKEN=$$SECOND_TOKEN bash scripts/governance_audit.sh

failure-recovery:
	@API=$$API TOKEN=$$TOKEN bash scripts/failure_recovery.sh

dx-timing:
	@API=$$API TOKEN=$$TOKEN bash scripts/dx_timing.sh

governance-demo:
	@API=$$API TOKEN=$$TOKEN SECOND_TOKEN=$$SECOND_TOKEN TOKEN_NO_ADMIN=$$TOKEN_NO_ADMIN \
	bash scripts/governance_demo.sh

publish-retrieval-uplift:
	@API=$$API TOKEN=$$TOKEN FILE=$${FILE:-evaluation/weighted_search_results.json} \
	bash scripts/publish_retrieval_uplift.sh

demo-run:
	@API=$$API TOKEN=$$TOKEN make seed-ground-truth THRESH=$${THRESH:-0.10} TOPK=$${TOPK:-20}
	@API=$$API TOKEN=$$TOKEN make retrieval-quality
	@API=$$API TOKEN=$$TOKEN make publish-retrieval-uplift
	@API=$$API TOKEN=$$TOKEN make proof-report

open-grafana:
	@URL=$${GRAFANA_URL:-http://localhost:3000/d/activekg-ops}; \
	echo "Opening $$URL"; \
	( command -v xdg-open >/dev/null 2>&1 && xdg-open "$$URL" ) || \
	( command -v wslview  >/dev/null 2>&1 && wslview  "$$URL" ) || \
	( command -v open     >/dev/null 2>&1 && open     "$$URL" ) || \
	( command -v start    >/dev/null 2>&1 && start "" "$$URL" ) || \
	echo "Please open $$URL manually."
