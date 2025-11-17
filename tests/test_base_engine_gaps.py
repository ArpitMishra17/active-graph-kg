#!/usr/bin/env python3
"""
Test script for Base Engine Gap implementations:
1. Auto-enable vector index
2. Recency/drift weighting in search
3. Cron expression support

Run with: python test_base_engine_gaps.py
"""

import os
import sys
from datetime import UTC, datetime, timedelta

import numpy as np

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from activekg.graph.models import Node
from activekg.graph.repository import GraphRepository

DSN = os.getenv("ACTIVEKG_DSN", "postgresql://activekg:activekg@localhost:5432/activekg")


def test_vector_index_auto_creation():
    """Test 1: Vector index auto-creation on startup"""
    print("\n=== Test 1: Vector Index Auto-Creation ===")

    repo = GraphRepository(DSN)

    # This should check and create index if needed
    repo.ensure_vector_index()

    # Verify index exists
    import psycopg
    from pgvector.psycopg import register_vector

    conn = psycopg.connect(DSN)
    register_vector(conn)

    with conn.cursor() as cur:
        cur.execute("""
            SELECT indexname
            FROM pg_indexes
            WHERE tablename = 'nodes'
            AND indexname LIKE 'idx_nodes_embedding%'
        """)
        indexes = cur.fetchall()

    conn.close()

    if indexes:
        print(f"✅ Vector index exists: {[idx[0] for idx in indexes]}")
        return True
    else:
        print("❌ Vector index not found")
        return False


def test_weighted_search():
    """Test 2: Recency/drift weighting in search"""
    print("\n=== Test 2: Recency/Drift Weighted Search ===")

    repo = GraphRepository(DSN)

    # Create test nodes with different ages and drift scores
    old_node = Node(
        classes=["TestDoc"],
        props={"text": "Old stale document with high drift"},
        embedding=np.random.rand(384).astype(np.float32),
        last_refreshed=datetime.now(UTC) - timedelta(days=30),  # 30 days old
        drift_score=0.5,  # High drift
        tenant_id="test_weighted",
    )

    fresh_node = Node(
        classes=["TestDoc"],
        props={"text": "Fresh recent document with low drift"},
        embedding=old_node.embedding
        + np.random.rand(384).astype(np.float32) * 0.01,  # Very similar
        last_refreshed=datetime.now(UTC) - timedelta(hours=1),  # 1 hour old
        drift_score=0.05,  # Low drift
        tenant_id="test_weighted",
    )

    try:
        repo.create_node(old_node)
        repo.create_node(fresh_node)

        # Test 1: Normal search (no weighting) - should be similar scores
        print("\nTest 2a: Normal search (no weighting)")
        results_normal = repo.vector_search(
            query_embedding=old_node.embedding,
            top_k=10,
            tenant_id="test_weighted",
            use_weighted_score=False,
        )

        print(f"  Normal search results: {len(results_normal)} nodes")
        for node, score in results_normal[:2]:
            print(
                f"    {node.id[:8]}... score={score:.4f}, age={_age_str(node.last_refreshed)}, drift={node.drift_score}"
            )

        # Test 2: Weighted search - fresh node should rank higher
        print("\nTest 2b: Weighted search (with recency/drift)")
        results_weighted = repo.vector_search(
            query_embedding=old_node.embedding,
            top_k=10,
            tenant_id="test_weighted",
            use_weighted_score=True,
            decay_lambda=0.01,  # Age penalty
            drift_beta=0.1,  # Drift penalty
        )

        print(f"  Weighted search results: {len(results_weighted)} nodes")
        for node, score in results_weighted[:2]:
            print(
                f"    {node.id[:8]}... score={score:.4f}, age={_age_str(node.last_refreshed)}, drift={node.drift_score}"
            )

        # Verification: In weighted search, fresh node should rank higher
        if len(results_weighted) >= 2:
            top_node = results_weighted[0][0]
            if top_node.id == fresh_node.id:
                print("✅ Weighted search correctly prioritizes fresh node")
                success = True
            else:
                print("⚠️  Expected fresh node to rank first in weighted search")
                success = False
        else:
            print("⚠️  Not enough results to verify")
            success = False

        # Cleanup
        _cleanup_test_nodes(repo, "test_weighted")
        return success

    except Exception as e:
        print(f"❌ Test failed: {e}")
        _cleanup_test_nodes(repo, "test_weighted")
        return False


def test_cron_expression():
    """Test 3: Cron expression support"""
    print("\n=== Test 3: Cron Expression Support ===")

    repo = GraphRepository(DSN)

    # Test 3a: Cron every 5 minutes
    print("\nTest 3a: Cron every 5 minutes (*/5 * * * *)")

    # Create node with cron policy
    node_cron = Node(
        classes=["TestDoc"],
        props={"text": "Node with cron policy"},
        embedding=np.random.rand(384).astype(np.float32),
        refresh_policy={"cron": "*/5 * * * *"},
        last_refreshed=datetime.now(UTC) - timedelta(minutes=6),  # 6 min ago - DUE
        tenant_id="test_cron",
    )

    try:
        _ = repo.create_node(node_cron)

        # Check if node is due for refresh
        is_due = repo._is_due_for_refresh(node_cron)
        print("  Node last refreshed: 6 minutes ago")
        print("  Cron schedule: Every 5 minutes")
        print(f"  Is due for refresh: {is_due}")

        if is_due:
            print("✅ Cron correctly identifies node is due (6min > 5min)")
            cron_test1 = True
        else:
            print("❌ Cron should identify node as due")
            cron_test1 = False

        # Test 3b: Cron not due yet
        print("\nTest 3b: Cron not due yet")
        node_cron.last_refreshed = datetime.now(UTC) - timedelta(minutes=2)  # 2 min ago - NOT DUE
        is_due = repo._is_due_for_refresh(node_cron)
        print("  Node last refreshed: 2 minutes ago")
        print("  Cron schedule: Every 5 minutes")
        print(f"  Is due for refresh: {is_due}")

        if not is_due:
            print("✅ Cron correctly identifies node is NOT due (2min < 5min)")
            cron_test2 = True
        else:
            print("❌ Cron should NOT identify node as due")
            cron_test2 = False

        # Test 3c: Cron precedence over interval
        print("\nTest 3c: Cron precedence over interval")
        node_both = Node(
            classes=["TestDoc"],
            props={"text": "Node with both cron and interval"},
            embedding=np.random.rand(384).astype(np.float32),
            refresh_policy={
                "cron": "*/10 * * * *",  # Every 10 minutes
                "interval": "5m",  # Every 5 minutes (should be ignored)
            },
            last_refreshed=datetime.now(UTC) - timedelta(minutes=7),  # 7 min ago
            tenant_id="test_cron",
        )

        is_due = repo._is_due_for_refresh(node_both)
        print("  Policy: cron=*/10 (every 10min), interval=5m (every 5min)")
        print("  Last refreshed: 7 minutes ago")
        print(f"  Is due for refresh: {is_due}")
        print("  Expected: False (cron takes precedence, 7min < 10min)")

        if not is_due:
            print("✅ Cron correctly takes precedence over interval")
            cron_test3 = True
        else:
            print("❌ Expected cron to take precedence (not due at 7min)")
            cron_test3 = False

        # Cleanup
        _cleanup_test_nodes(repo, "test_cron")

        return cron_test1 and cron_test2 and cron_test3

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        _cleanup_test_nodes(repo, "test_cron")
        return False


def _age_str(last_refreshed):
    """Helper to format age"""
    if not last_refreshed:
        return "never"
    age = datetime.now(UTC) - last_refreshed
    if age.days > 0:
        return f"{age.days}d"
    hours = age.seconds // 3600
    if hours > 0:
        return f"{hours}h"
    minutes = age.seconds // 60
    return f"{minutes}m"


def _cleanup_test_nodes(repo, tenant_id):
    """Helper to cleanup test nodes"""
    import psycopg
    from pgvector.psycopg import register_vector

    conn = psycopg.connect(repo.dsn)
    register_vector(conn)

    with conn.cursor() as cur:
        cur.execute("DELETE FROM nodes WHERE tenant_id = %s", (tenant_id,))

    conn.commit()
    conn.close()


def main():
    print("=" * 60)
    print("Base Engine Gap Tests - Acceptance Criteria Verification")
    print("=" * 60)

    results = {}

    # Test 1: Vector index
    results["vector_index"] = test_vector_index_auto_creation()

    # Test 2: Weighted search
    results["weighted_search"] = test_weighted_search()

    # Test 3: Cron support
    results["cron_support"] = test_cron_expression()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print(f"Vector Index Auto-Creation:  {'✅ PASS' if results['vector_index'] else '❌ FAIL'}")
    print(f"Weighted Search (Recency):   {'✅ PASS' if results['weighted_search'] else '❌ FAIL'}")
    print(f"Cron Expression Support:     {'✅ PASS' if results['cron_support'] else '❌ FAIL'}")

    total_pass = sum(results.values())
    print(f"\nTotal: {total_pass}/3 tests passed")

    if total_pass == 3:
        print("\n🎉 ALL ACCEPTANCE CRITERIA MET!")
        return 0
    else:
        print(f"\n⚠️  {3 - total_pass} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
