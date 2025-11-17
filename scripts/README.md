# Scripts Catalog

All end-to-end validation and proof scripts live here and are exposed via Makefile targets.

Common variables:
- `API` (default `http://localhost:8000`)
- `TOKEN` (admin JWT for protected endpoints)
- `SECOND_TOKEN` (optional, for cross-tenant governance tests)

Core
- `live_smoke.sh` → CRUD, ANN, vector/hybrid search, ask/stream, metrics
- `live_extended.sh` → Drift, lineage, events, triggers
- `metrics_probe.sh` → Prometheus counters/histograms summary
- `proof_points_report.sh` → Builds evaluation/PROOF_POINTS_REPORT.md

Evaluation
- `seed_ground_truth.sh` → Populate evaluation/datasets/ground_truth.json
- `retrieval_quality.sh` → Vector vs hybrid vs weighted (triple mode)
- `qa_benchmark.sh` → LLM Q&A latency and accuracy
- `publish_retrieval_uplift.sh` → Expose uplift as Prom stats (Grafana)

Ops & SRE
- `db_index_metrics.sh` → Index sizes, table size
- `tco_snapshot.sh` → CPU/Mem footprints & storage snapshot
- `scheduler_sla.sh` → Inter-run intervals; first-token SSE latency
- `failure_recovery.sh` → Graceful failure modes (timeouts, DLQ, resume)
- `governance_audit.sh` / `governance_demo.sh` → RLS isolation proofs

Latency
- `search_latency_eval.sh` → p50/p95/p99 for vector/hybrid

Usage via Makefile (examples)
```bash
export API=http://localhost:8000
export TOKEN='<admin JWT>'
make live-smoke
make retrieval-quality && make publish-retrieval-uplift
make proof-report
```

