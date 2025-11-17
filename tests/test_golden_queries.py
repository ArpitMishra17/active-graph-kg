"""
Test golden queries - critical queries that must work correctly in both RRF and cosine modes.

These tests validate core system behavior on a curated set of queries that represent
typical usage patterns. They ensure that:
1. Score types are correct for the active mode
2. Scores fall within expected ranges for each mode
3. Citation quality meets minimum thresholds
4. Rejection behavior is appropriate

Usage:
    # RRF mode
    export HYBRID_RRF_ENABLED=true
    pytest tests/test_golden_queries.py -v

    # Cosine mode
    export HYBRID_RRF_ENABLED=false
    pytest tests/test_golden_queries.py -v
"""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """Test client that inherits environment configuration."""
    from activekg.api.main import app

    return TestClient(app)


@pytest.fixture(scope="module")
def golden_queries():
    """Load golden queries from JSON file."""
    golden_queries_path = (
        Path(__file__).parent.parent / "evaluation" / "datasets" / "golden_queries.json"
    )
    with open(golden_queries_path) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def mode():
    """Determine active scoring mode from environment."""
    rrf_enabled = os.getenv("HYBRID_RRF_ENABLED", "true").lower() == "true"
    return "rrf" if rrf_enabled else "cosine"


class TestGoldenQueries:
    """Test critical queries against expected behavior."""

    def test_golden_query_score_types(self, client, golden_queries, mode):
        """Test that all golden queries return correct score type for active mode."""
        failures = []

        for query_spec in golden_queries:
            query_id = query_spec["id"]
            query_text = query_spec["query"]
            expected_config = query_spec[mode]
            expected_score_type = expected_config["expected_score_type"]

            response = client.post("/ask", json={"question": query_text})
            assert response.status_code == 200, (
                f"Query {query_id} failed with status {response.status_code}"
            )

            data = response.json()
            metadata = data.get("metadata", {})
            actual_score_type = metadata.get("gating_score_type")

            if actual_score_type != expected_score_type:
                failures.append(
                    f"Query '{query_id}': expected score_type={expected_score_type}, "
                    f"got {actual_score_type}"
                )

        assert not failures, "Score type mismatches:\n" + "\n".join(failures)

    def test_golden_query_score_ranges(self, client, golden_queries, mode):
        """Test that gating scores fall within expected ranges for active mode."""
        failures = []

        for query_spec in golden_queries:
            query_id = query_spec["id"]
            query_text = query_spec["query"]
            expected_config = query_spec[mode]
            min_score = expected_config["min_gating_score"]
            max_score = expected_config["max_gating_score"]

            response = client.post("/ask", json={"question": query_text})
            assert response.status_code == 200

            data = response.json()
            metadata = data.get("metadata", {})
            gating_score = metadata.get("gating_score", 0)

            # Allow some tolerance for edge cases
            tolerance = 0.005 if mode == "rrf" else 0.05
            if not (min_score - tolerance <= gating_score <= max_score + tolerance):
                failures.append(
                    f"Query '{query_id}': gating_score={gating_score:.4f} "
                    f"outside expected range [{min_score}, {max_score}]"
                )

        assert not failures, "Score range violations:\n" + "\n".join(failures)

    def test_golden_query_citation_quality(self, client, golden_queries, mode):
        """Test that queries with expected results return minimum cited nodes."""
        failures = []

        for query_spec in golden_queries:
            query_id = query_spec["id"]
            query_text = query_spec["query"]
            min_cited = query_spec.get("min_cited_nodes", 0)
            expected_config = query_spec[mode]
            expect_rejection = expected_config.get("expect_rejection", False)

            response = client.post("/ask", json={"question": query_text})
            assert response.status_code == 200

            data = response.json()
            metadata = data.get("metadata", {})
            cited_nodes = metadata.get("cited_nodes", 0)

            # Skip citation check if rejection is expected
            if expect_rejection:
                continue

            if min_cited > 0 and cited_nodes < min_cited:
                failures.append(
                    f"Query '{query_id}': cited_nodes={cited_nodes} below minimum {min_cited}"
                )

        assert not failures, "Citation quality failures:\n" + "\n".join(failures)

    def test_golden_query_rejection_behavior(self, client, golden_queries, mode):
        """Test that irrelevant queries are appropriately handled."""
        for query_spec in golden_queries:
            query_id = query_spec["id"]
            query_text = query_spec["query"]
            expected_config = query_spec[mode]
            expect_rejection = expected_config.get("expect_rejection", False)

            # Only test queries that should be rejected
            if not expect_rejection:
                continue

            response = client.post("/ask", json={"question": query_text})
            assert response.status_code == 200

            data = response.json()
            metadata = data.get("metadata", {})
            cited_nodes = metadata.get("cited_nodes", 0)
            reason = metadata.get("reason", "")

            # Should either be rejected or return no citations
            assert cited_nodes == 0 or "extremely_low_similarity" in reason, (
                f"Query '{query_id}' should be rejected or return no results, "
                f"but got cited_nodes={cited_nodes}, reason={reason}"
            )

    def test_golden_query_consistency(self, client, golden_queries, mode):
        """Test that repeated queries return consistent results."""
        # Pick a representative query
        query_spec = golden_queries[0]
        query_text = query_spec["query"]

        results = []
        for _ in range(3):
            response = client.post("/ask", json={"question": query_text})
            assert response.status_code == 200

            data = response.json()
            metadata = data.get("metadata", {})
            results.append(
                {
                    "gating_score": metadata.get("gating_score", 0),
                    "gating_score_type": metadata.get("gating_score_type"),
                    "cited_nodes": metadata.get("cited_nodes", 0),
                }
            )

        # Check score type consistency
        score_types = [r["gating_score_type"] for r in results]
        assert len(set(score_types)) == 1, f"Inconsistent score types: {score_types}"

        # Check score stability (allow some variation due to randomness in LLM/ranking)
        scores = [r["gating_score"] for r in results]
        score_variance = max(scores) - min(scores)
        max_variance = 0.01 if mode == "rrf" else 0.1
        assert score_variance <= max_variance, (
            f"Score variance too high: {score_variance:.4f} > {max_variance}"
        )


class TestGoldenQueriesPerformance:
    """Test performance characteristics of golden queries."""

    @pytest.mark.timeout(5)
    def test_golden_query_latency(self, client, golden_queries):
        """Test that golden queries complete within acceptable time."""
        import time

        # Test first 3 queries for speed
        for query_spec in golden_queries[:3]:
            query_text = query_spec["query"]

            start = time.time()
            response = client.post("/ask", json={"question": query_text})
            latency = time.time() - start

            assert response.status_code == 200
            assert latency < 5.0, f"Query '{query_spec['id']}' took {latency:.2f}s (> 5s)"

    def test_golden_query_debug_metadata(self, client, golden_queries, mode):
        """Test that debug endpoints provide correct metadata for golden queries."""
        # Test first query with debug endpoint
        query_spec = golden_queries[0]
        query_text = query_spec["query"]
        expected_config = query_spec[mode]
        expected_score_type = expected_config["expected_score_type"]

        response = client.post(
            "/debug/search_explain", json={"query": query_text, "use_hybrid": True, "top_k": 5}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify score_type
        assert data.get("score_type") == expected_score_type

        # Verify scoring_notes present
        scoring_notes = data.get("scoring_notes", {})
        assert len(scoring_notes) >= 3, "Should have notes for all scoring modes"
        assert expected_score_type in scoring_notes


def pytest_collection_modifyitems(config, items):
    """Add custom markers based on test names."""
    for item in items:
        # Mark tests that should be run in CI
        if "golden" in item.nodeid:
            item.add_marker(pytest.mark.golden)

        # Mark performance tests
        if "performance" in item.nodeid.lower() or "latency" in item.nodeid.lower():
            item.add_marker(pytest.mark.performance)
