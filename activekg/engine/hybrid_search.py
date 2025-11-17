from __future__ import annotations

from typing import Any

import numpy as np

from activekg.common.logger import get_enhanced_logger


class HybridSearch:
    """Placeholder hybrid search that will combine vector similarity + filters.

    Start with pgvector-only for MVP; add FAISS/HNSW later if needed.
    """

    def __init__(self):
        self.logger = get_enhanced_logger(__name__)

    def search(
        self, query_vector: np.ndarray, filters: dict[str, Any] | None = None, k: int = 10
    ) -> list[dict[str, Any]]:
        # Wire to Postgres pgvector query in graph.repository later
        self.logger.info(
            "HybridSearch.search called", extra_fields={"k": k, "has_filters": bool(filters)}
        )
        return []
