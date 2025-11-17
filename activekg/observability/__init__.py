"""
Observability package for Active Graph KG.

Provides Prometheus metrics and monitoring utilities.
"""

from activekg.observability.metrics import (
    get_metrics_handler,
    track_ask_request,
    track_embedding_health,
    track_refresh,
    track_search_request,
)

__all__ = [
    "track_ask_request",
    "track_search_request",
    "track_embedding_health",
    "track_refresh",
    "get_metrics_handler",
]
