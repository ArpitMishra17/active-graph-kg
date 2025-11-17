"""
Prometheus metrics for Active Graph KG.

Tracks key metrics for observability:
- Gating scores by mode (RRF vs cosine)
- Citation counts
- Rejection reasons
- Search latency
- Embedding health

Usage:
    from activekg.observability.metrics import (
        track_ask_request,
        track_search_request,
        get_metrics_handler
    )

    # In /ask endpoint
    track_ask_request(
        gating_score=0.033,
        gating_score_type="rrf_fused",
        cited_nodes=3,
        latency_ms=450,
        rejected=False,
        rejection_reason=None
    )

    # Expose metrics endpoint
    app.add_route("/metrics", get_metrics_handler())
"""

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.responses import Response

# Request counters
ask_requests_total = Counter(
    "activekg_ask_requests_total", "Total number of /ask requests", ["score_type", "rejected"]
)

search_requests_total = Counter(
    "activekg_search_requests_total", "Total number of search requests", ["mode", "score_type"]
)

# Gating score metrics
gating_score_histogram = Histogram(
    "activekg_gating_score",
    "Distribution of gating scores",
    ["score_type"],
    buckets=(
        0.005,
        0.01,
        0.015,
        0.02,
        0.03,
        0.04,
        0.05,
        0.10,
        0.15,
        0.20,
        0.30,
        0.50,
        0.70,
        0.90,
        1.0,
    ),
)

# Citation metrics
cited_nodes_histogram = Histogram(
    "activekg_cited_nodes",
    "Distribution of cited node counts",
    ["score_type"],
    buckets=(0, 1, 2, 3, 5, 10, 15, 20, 30, 50),
)

zero_citation_counter = Counter(
    "activekg_zero_citations_total", "Total requests with zero citations", ["score_type", "reason"]
)

# Rejection metrics
rejection_counter = Counter(
    "activekg_rejections_total", "Total number of rejected queries", ["reason", "score_type"]
)

# Latency metrics
ask_latency_histogram = Histogram(
    "activekg_ask_latency_seconds",
    "Latency of /ask requests",
    ["score_type", "reranked"],
    buckets=(0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0),
)

search_latency_histogram = Histogram(
    "activekg_search_latency_seconds",
    "Latency of search requests",
    ["mode", "score_type", "reranked"],
    buckets=(0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0),
)

# Embedding health gauges
embedding_coverage_gauge = Gauge(
    "activekg_embedding_coverage_ratio", "Ratio of nodes with embeddings", ["tenant_id"]
)

embedding_staleness_gauge = Gauge(
    "activekg_embedding_max_staleness_seconds", "Maximum time since last refresh", ["tenant_id"]
)

# System health
last_refresh_timestamp_gauge = Gauge(
    "activekg_last_refresh_timestamp",
    "Timestamp of last successful refresh",
    ["class_name", "tenant_id"],
)


def track_ask_request(
    gating_score: float,
    gating_score_type: str,
    cited_nodes: int,
    latency_ms: float,
    rejected: bool = False,
    rejection_reason: str | None = None,
    reranked: bool = False,
) -> None:
    """
    Track metrics for an /ask request.

    Args:
        gating_score: The gating similarity score used for decision
        gating_score_type: Type of score ("rrf_fused" or "cosine")
        cited_nodes: Number of nodes cited in response
        latency_ms: Request latency in milliseconds
        rejected: Whether the query was rejected
        rejection_reason: Reason for rejection (if rejected)
        reranked: Whether reranking was applied
    """
    # Convert milliseconds to seconds
    latency_s = latency_ms / 1000.0

    # Track request count
    ask_requests_total.labels(score_type=gating_score_type, rejected=str(rejected).lower()).inc()

    # Track gating score distribution
    gating_score_histogram.labels(score_type=gating_score_type).observe(gating_score)

    # Track citation metrics
    if not rejected:
        cited_nodes_histogram.labels(score_type=gating_score_type).observe(cited_nodes)

        if cited_nodes == 0:
            reason = rejection_reason or "no_results"
            zero_citation_counter.labels(score_type=gating_score_type, reason=reason).inc()

    # Track rejections
    if rejected and rejection_reason:
        rejection_counter.labels(reason=rejection_reason, score_type=gating_score_type).inc()

    # Track latency
    ask_latency_histogram.labels(
        score_type=gating_score_type, reranked=str(reranked).lower()
    ).observe(latency_s)


def track_search_request(
    mode: str, score_type: str, latency_ms: float, result_count: int, reranked: bool = False
) -> None:
    """
    Track metrics for a search request.

    Args:
        mode: Search mode ("hybrid", "vector", "text")
        score_type: Score type ("rrf_fused", "weighted_fusion", "cosine")
        latency_ms: Request latency in milliseconds
        result_count: Number of results returned
        reranked: Whether reranking was applied
    """
    # Convert milliseconds to seconds
    latency_s = latency_ms / 1000.0

    # Track request count
    search_requests_total.labels(mode=mode, score_type=score_type).inc()

    # Track latency
    search_latency_histogram.labels(
        mode=mode, score_type=score_type, reranked=str(reranked).lower()
    ).observe(latency_s)


def track_embedding_health(
    coverage_ratio: float, max_staleness_seconds: float, tenant_id: str = "default"
) -> None:
    """
    Track embedding health metrics.

    Args:
        coverage_ratio: Ratio of nodes with embeddings (0.0-1.0)
        max_staleness_seconds: Maximum age of embeddings in seconds
        tenant_id: Tenant ID for multi-tenant setups
    """
    embedding_coverage_gauge.labels(tenant_id=tenant_id).set(coverage_ratio)
    embedding_staleness_gauge.labels(tenant_id=tenant_id).set(max_staleness_seconds)


def track_refresh(class_name: str, timestamp: float, tenant_id: str = "default") -> None:
    """
    Track successful refresh operation.

    Args:
        class_name: Name of the class refreshed
        timestamp: Unix timestamp of refresh
        tenant_id: Tenant ID
    """
    last_refresh_timestamp_gauge.labels(class_name=class_name, tenant_id=tenant_id).set(timestamp)


def get_metrics_handler():
    """
    Get a handler for the /metrics endpoint.

    Returns:
        Async handler function for Starlette/FastAPI
    """

    async def metrics_endpoint():
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return metrics_endpoint


# Convenience exports
__all__ = [
    "track_ask_request",
    "track_search_request",
    "track_embedding_health",
    "track_refresh",
    "get_metrics_handler",
    "track_trigger_run",
    "track_trigger_fired",
    "track_schedule_run",
    "track_node_refresh_latency",
    "track_index_build",
    "track_ask_first_chunk_latency",
    "track_nodes_refreshed",
    "track_refresh_cycle_nodes",
    "access_violations_total",
    "set_retrieval_uplift",
]

# -----------------------------
# Trigger engine & scheduler metrics
# -----------------------------

triggers_fired_total = Counter(
    "activekg_triggers_fired_total", "Total triggers fired", ["pattern", "mode"]
)

trigger_run_latency_seconds = Histogram(
    "activekg_trigger_run_latency_seconds",
    "Duration of trigger engine runs",
    ["mode"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)

schedule_runs_total = Counter(
    "activekg_schedule_runs_total", "Total scheduled job runs", ["job_id", "kind"]
)

schedule_inter_run_seconds = Histogram(
    "activekg_schedule_inter_run_seconds",
    "Observed inter-run intervals per job",
    ["job_id"],
    buckets=(5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
)

node_refresh_latency_seconds = Histogram(
    "activekg_node_refresh_latency_seconds",
    "Per-node refresh processing time in scheduler",
    ["result"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)
nodes_refreshed_total = Counter(
    "activekg_nodes_refreshed_total", "Total nodes refreshed by scheduler", ["result"]
)
refresh_cycle_nodes = Histogram(
    "activekg_refresh_cycle_nodes",
    "Number of nodes refreshed per scheduler cycle",
    [],
    buckets=(0, 1, 2, 5, 10, 20, 50, 100, 200),
)

# Governance / Access control counters
access_violations_total = Counter(
    "activekg_access_violations_total",
    "Access control violations (missing token, scope denied, cross-tenant attempts)",
    ["type"],
)

# Retrieval uplift gauges (percent vs vector baseline)
retrieval_uplift_mrr_percent = Gauge(
    "activekg_retrieval_uplift_mrr_percent",
    "MRR uplift vs vector baseline (percent)",
    ["mode"],
)


def set_retrieval_uplift(mode: str, value_percent: float) -> None:
    """Set MRR uplift gauge for a retrieval mode (e.g., hybrid, weighted)."""
    retrieval_uplift_mrr_percent.labels(mode=mode).set(float(value_percent))


# Index build timing
vector_index_build_seconds = Histogram(
    "activekg_vector_index_build_seconds",
    "Vector index build duration in seconds",
    ["type", "metric", "result"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0),
)

# Streaming ask: first token latency
ask_first_chunk_latency_seconds = Histogram(
    "activekg_ask_first_chunk_latency_seconds",
    "Time from request to first streamed token for /ask/stream",
    [],
    buckets=(0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0),
)


def track_trigger_run(latency_s: float, mode: str, fired_count: int) -> None:
    trigger_run_latency_seconds.labels(mode=mode).observe(latency_s)


def track_trigger_fired(pattern: str, mode: str) -> None:
    triggers_fired_total.labels(pattern=pattern, mode=mode).inc()


def track_schedule_run(job_id: str, kind: str, inter_run_s: float | None = None) -> None:
    schedule_runs_total.labels(job_id=job_id, kind=kind).inc()
    if inter_run_s is not None and inter_run_s >= 0:
        schedule_inter_run_seconds.labels(job_id=job_id).observe(inter_run_s)


def track_node_refresh_latency(latency_s: float, result: str = "ok") -> None:
    node_refresh_latency_seconds.labels(result=result).observe(latency_s)


def track_index_build(latency_s: float, type_: str, metric: str, result: str) -> None:
    vector_index_build_seconds.labels(type=type_, metric=metric, result=result).observe(latency_s)


def track_ask_first_chunk_latency(latency_s: float) -> None:
    ask_first_chunk_latency_seconds.observe(latency_s)


def track_nodes_refreshed(result: str = "ok", count: int = 1) -> None:
    nodes_refreshed_total.labels(result=result).inc(count)


def track_refresh_cycle_nodes(count: int) -> None:
    try:
        refresh_cycle_nodes.observe(float(count))
    except Exception:
        pass
