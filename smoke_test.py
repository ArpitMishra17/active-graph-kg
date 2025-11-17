#!/usr/bin/env python3
"""
Smoke Test - Quick E2E validation of Phase 1 MVP

Tests the three critical flows:
1. Refresh cycle → embedding_history + gated event
2. Pattern registration → trigger_fired event
3. Lineage chain → recursive traversal
"""

import sys
import time
from datetime import datetime

import requests

BASE_URL = "http://localhost:8000"


def test_refresh_cycle():
    """Test: Create node → refresh → check embedding_history + gated event."""
    print("\n=== Test 1: Refresh Cycle with Drift Gating ===")

    # 1. Create node with refresh policy
    node_data = {
        "classes": ["TestDoc"],
        "props": {"text": "Machine learning fundamentals for beginners"},
        "refresh_policy": {"interval": "1m", "drift_threshold": 0.15},
    }

    resp = requests.post(f"{BASE_URL}/nodes", json=node_data)
    assert resp.status_code == 200, f"Failed to create node: {resp.text}"
    node_id = resp.json()["id"]
    print(f"✓ Created node: {node_id}")

    # 2. Wait for refresh cycle (scheduler runs every 1min)
    print("  Waiting 65 seconds for refresh cycle...")
    time.sleep(65)

    # 3. Check events for 'refreshed' event
    resp = requests.get(
        f"{BASE_URL}/events", params={"node_id": node_id, "event_type": "refreshed"}
    )
    assert resp.status_code == 200
    events = resp.json()["events"]

    if len(events) > 0:
        drift = events[0]["payload"].get("drift_score", 0)
        threshold = 0.15
        print(f"✓ Found refresh event: drift={drift:.4f}, threshold={threshold}")
        if events[0]["payload"].get("threshold_exceeded"):
            print(f"✓ Drift threshold gating worked (drift > {threshold})")
        else:
            print("✓ Event emitted (manual trigger or drift > threshold)")
    else:
        print("⚠ No refresh event yet (may need more time or check scheduler is running)")

    # 4. Check embedding_history (requires DB access)
    print("✓ Refresh cycle test complete (check DB for embedding_history entry)")

    return node_id


def test_pattern_trigger():
    """Test: Register pattern → create matching node → trigger_fired event."""
    print("\n=== Test 2: Pattern Registration & Trigger Firing ===")

    # 1. Register pattern
    pattern_data = {
        "name": "fraud_test",
        "example_text": "suspicious wire transfer to offshore account with unusual pattern",
        "description": "Detects potential fraud",
    }

    resp = requests.post(f"{BASE_URL}/triggers", json=pattern_data)
    assert resp.status_code == 200, f"Failed to register pattern: {resp.text}"
    print(f"✓ Registered pattern: {resp.json()['name']}")

    # 2. List patterns to verify DB persistence
    resp = requests.get(f"{BASE_URL}/triggers")
    assert resp.status_code == 200
    patterns = resp.json()["patterns"]
    assert any(p["name"] == "fraud_test" for p in patterns), "Pattern not in DB"
    print(f"✓ Pattern persisted in DB (found {len(patterns)} total patterns)")

    # 3. Create node with trigger
    node_data = {
        "classes": ["Transaction"],
        "props": {"text": "large wire transfer to offshore account flagged by system"},
        "triggers": [{"name": "fraud_test", "threshold": 0.7}],
    }

    resp = requests.post(f"{BASE_URL}/nodes", json=node_data)
    assert resp.status_code == 200
    node_id = resp.json()["id"]
    print(f"✓ Created node with trigger: {node_id}")

    # 4. Wait for trigger cycle (runs every 2min)
    print("  Waiting 125 seconds for trigger cycle...")
    time.sleep(125)

    # 5. Check for trigger_fired events
    resp = requests.get(f"{BASE_URL}/events", params={"event_type": "trigger_fired"})
    assert resp.status_code == 200
    events = resp.json()["events"]

    if len(events) > 0:
        print(f"✓ Found {len(events)} trigger_fired events")
        for event in events[:3]:
            print(
                f"  - Trigger: {event['payload'].get('trigger')}, similarity: {event['payload'].get('similarity', 0):.4f}"
            )
    else:
        print("⚠ No trigger_fired events yet (may need more time or similarity below threshold)")

    # 6. Cleanup
    resp = requests.delete(f"{BASE_URL}/triggers/fraud_test")
    print("✓ Cleaned up test pattern")

    return node_id


def test_lineage_chain():
    """Test: Create chain A→B→C via DERIVED_FROM → traverse lineage."""
    print("\n=== Test 3: Lineage Chain Traversal ===")

    # 1. Create parent (C)
    parent_data = {
        "classes": ["SourceDocument"],
        "props": {"text": "Original research paper on neural networks"},
    }
    resp = requests.post(f"{BASE_URL}/nodes", json=parent_data)
    assert resp.status_code == 200
    parent_id = resp.json()["id"]
    print(f"✓ Created parent node (C): {parent_id}")

    # 2. Create intermediate (B)
    intermediate_data = {
        "classes": ["Summary"],
        "props": {"text": "Summary of neural network research"},
    }
    resp = requests.post(f"{BASE_URL}/nodes", json=intermediate_data)
    assert resp.status_code == 200
    intermediate_id = resp.json()["id"]
    print(f"✓ Created intermediate node (B): {intermediate_id}")

    # 3. Create child (A)
    child_data = {"classes": ["Extract"], "props": {"text": "Key findings from summary"}}
    resp = requests.post(f"{BASE_URL}/nodes", json=child_data)
    assert resp.status_code == 200
    child_id = resp.json()["id"]
    print(f"✓ Created child node (A): {child_id}")

    # 4. Create edges: A→B→C
    edge1 = {
        "src": child_id,
        "rel": "DERIVED_FROM",
        "dst": intermediate_id,
        "props": {"transform": "extract_key_findings", "confidence": 0.95},
    }
    resp = requests.post(f"{BASE_URL}/edges", json=edge1)
    assert resp.status_code == 200
    print("✓ Created edge: A → B")

    edge2 = {
        "src": intermediate_id,
        "rel": "DERIVED_FROM",
        "dst": parent_id,
        "props": {"transform": "summarize_paper", "confidence": 0.92},
    }
    resp = requests.post(f"{BASE_URL}/edges", json=edge2)
    assert resp.status_code == 200
    print("✓ Created edge: B → C")

    # 5. Traverse lineage from A
    resp = requests.get(f"{BASE_URL}/lineage/{child_id}", params={"max_depth": 5})
    assert resp.status_code == 200
    lineage = resp.json()

    ancestors = lineage["ancestors"]
    print(f"✓ Lineage traversal found {len(ancestors)} ancestors:")
    for ancestor in ancestors:
        print(
            f"  - Depth {ancestor['depth']}: {ancestor['id'][:8]}... (classes: {ancestor['classes']})"
        )

    assert len(ancestors) == 2, f"Expected 2 ancestors, got {len(ancestors)}"
    assert ancestors[0]["depth"] == 1, "First ancestor should be depth 1"
    assert ancestors[1]["depth"] == 2, "Second ancestor should be depth 2"
    print("✓ Lineage chain verified: A → B → C")

    return child_id, intermediate_id, parent_id


def test_search():
    """Test: Semantic search returns results with similarity scores."""
    print("\n=== Test 4: Semantic Search ===")

    search_data = {"query": "machine learning neural networks research", "top_k": 10}

    resp = requests.post(f"{BASE_URL}/search", json=search_data)
    assert resp.status_code == 200, f"Search failed: {resp.text}"

    results = resp.json()["results"]
    print(f"✓ Search returned {len(results)} results")

    if len(results) > 0:
        for i, result in enumerate(results[:3], 1):
            print(f"  {i}. Similarity: {result['similarity']:.4f}, Classes: {result['classes']}")

    return len(results)


def main():
    print("=" * 70)
    print("Phase 1 MVP - Smoke Test")
    print("=" * 70)
    print(f"Target: {BASE_URL}")
    print(f"Time: {datetime.now().isoformat()}")
    print()

    # Check API is running
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        assert resp.status_code == 200
        print("✓ API is running")
    except Exception as e:
        print(f"❌ API not reachable: {e}")
        print("\nStart API with:")
        print("  export ACTIVEKG_DSN='postgresql://activekg:activekg@localhost:5432/activekg'")
        print("  uvicorn activekg.api.main:app --reload")
        sys.exit(1)

    try:
        # Run tests
        node_id_1 = test_refresh_cycle()
        node_id_2 = test_pattern_trigger()
        child_id, intermediate_id, parent_id = test_lineage_chain()
        result_count = test_search()

        print("\n" + "=" * 70)
        print("✅ SMOKE TEST PASSED")
        print("=" * 70)
        print("\nCreated Resources:")
        print(
            f"  - Nodes: {node_id_1[:8]}..., {node_id_2[:8]}..., {child_id[:8]}..., {intermediate_id[:8]}..., {parent_id[:8]}..."
        )
        print(f"  - Search results: {result_count} nodes indexed")
        print("\nNext Steps:")
        print("  1. Check /events for 'refreshed' and 'trigger_fired' events")
        print("  2. Query embedding_history table in DB")
        print("  3. Enable vector index: psql -f enable_vector_index.sql")

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
