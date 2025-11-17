#!/usr/bin/env python3
"""
test_soft_delete_purger.py - Comprehensive test suite for soft-delete purger functionality.

Tests:
- Creating parent+chunk nodes with 'Deleted' class and past grace period
- Dry-run mode (counts candidates without purging)
- Actual purge (removes nodes permanently)
- Tenant isolation (nodes from different tenants remain separate)
- Post-purge verification (confirms removal)

Usage:
    python3 test_soft_delete_purger.py
"""

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

# Configuration
BASE_URL = os.getenv("ACTIVEKG_BASE_URL", "http://localhost:8000")
DSN = os.getenv("ACTIVEKG_DSN", "postgresql:///activekg?host=/var/run/postgresql&port=5433")


def print_header(msg: str) -> None:
    """Print a formatted test section header."""
    print(f"\n{'=' * 70}")
    print(f"  {msg}")
    print(f"{'=' * 70}")


def print_step(msg: str) -> None:
    """Print a formatted test step."""
    print(f"\n→ {msg}")


def print_success(msg: str) -> None:
    """Print a success message."""
    print(f"  ✓ {msg}")


def print_error(msg: str) -> None:
    """Print an error message."""
    print(f"  ✗ {msg}")


def create_node(props: dict[str, Any], classes: list[str], tenant_id: str = "default") -> str:
    """Create a node via API."""
    payload = {"classes": classes, "props": props, "tenant_id": tenant_id}

    resp = requests.post(f"{BASE_URL}/nodes", json=payload)
    if resp.status_code != 200:
        raise Exception(f"Failed to create node: {resp.status_code} - {resp.text}")

    node_id = resp.json().get("node_id")
    print_success(f"Created node {node_id} with classes {classes}")
    return node_id


def count_nodes_by_class(class_name: str, tenant_id: str = "default") -> int:
    """Count nodes with a specific class via SQL."""
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(DSN, min_size=1, max_size=2)
    conn = pool.getconn()

    try:
        with conn:
            with conn.cursor() as cur:
                # Set tenant context for RLS
                from psycopg import sql

                cur.execute(
                    sql.SQL("SET LOCAL app.current_tenant_id = {}").format(sql.Literal(tenant_id))
                )

                # Count nodes with class
                cur.execute("SELECT COUNT(*) FROM nodes WHERE %s = ANY(classes)", (class_name,))
                count = cur.fetchone()[0]
                return count
    finally:
        pool.putconn(conn)
        pool.close()


def mark_node_deleted(node_id: str, grace_hours: int = -1, tenant_id: str = "default") -> None:
    """Mark a node as Deleted with grace period via SQL."""
    from psycopg_pool import ConnectionPool

    # Calculate grace period timestamp
    grace_until = datetime.now(UTC) + timedelta(hours=grace_hours)
    grace_until_str = grace_until.isoformat()

    pool = ConnectionPool(DSN, min_size=1, max_size=2)
    conn = pool.getconn()

    try:
        with conn:
            with conn.cursor() as cur:
                # Set tenant context for RLS
                from psycopg import sql

                cur.execute(
                    sql.SQL("SET LOCAL app.current_tenant_id = {}").format(sql.Literal(tenant_id))
                )

                # Update node: add Deleted class and set grace period
                cur.execute(
                    """
                    UPDATE nodes
                    SET classes = array_append(classes, 'Deleted'),
                        props = props || jsonb_build_object('deletion_grace_until', %s::text)
                    WHERE id = %s
                    """,
                    (grace_until_str, node_id),
                )

                print_success(
                    f"Marked node {node_id} as Deleted (grace_until={grace_until_str[:19]})"
                )
    finally:
        pool.putconn(conn)
        pool.close()


def call_purge_api(
    tenant_id: str = None, batch_size: int = 500, dry_run: bool = False
) -> dict[str, Any]:
    """Call the purge endpoint via API."""
    payload = {"tenant_id": tenant_id, "batch_size": batch_size, "dry_run": dry_run}

    resp = requests.post(f"{BASE_URL}/_admin/connectors/purge_deleted", json=payload)
    if resp.status_code != 200:
        raise Exception(f"Purge API failed: {resp.status_code} - {resp.text}")

    return resp.json()


def main():
    """Run soft-delete purger tests."""
    print_header("Soft-Delete Purger Test Suite")

    # Test 1: Create parent and chunks
    print_header("Test 1: Create Parent + Chunks")

    print_step("Creating parent document for tenant 'default'")
    parent_id = create_node(
        props={
            "external_id": "test-parent-1",
            "title": "Test Document",
            "text": "This is a test document that will be soft-deleted and purged.",
        },
        classes=["Document"],
        tenant_id="default",
    )

    print_step("Creating 3 chunks for parent document")
    chunk_ids = []
    for i in range(3):
        chunk_id = create_node(
            props={
                "parent_id": "test-parent-1",
                "text": f"Chunk {i + 1} of test document",
                "chunk_index": i,
            },
            classes=["Chunk"],
            tenant_id="default",
        )
        chunk_ids.append(chunk_id)

    print_success(f"Created parent {parent_id} with {len(chunk_ids)} chunks")

    # Test 2: Mark as deleted with past grace period
    print_header("Test 2: Mark as Deleted (past grace)")

    print_step("Marking parent as Deleted with grace_until -1 hour (past)")
    mark_node_deleted(parent_id, grace_hours=-1, tenant_id="default")

    # Verify counts before purge
    deleted_count = count_nodes_by_class("Deleted", tenant_id="default")
    chunk_count = count_nodes_by_class("Chunk", tenant_id="default")
    print_success(f"Nodes before purge: {deleted_count} Deleted, {chunk_count} Chunks")

    # Test 3: Dry-run mode
    print_header("Test 3: Dry-Run Mode")

    print_step("Calling purge API in dry-run mode")
    dry_result = call_purge_api(tenant_id="default", batch_size=500, dry_run=True)

    print_success(f"Dry-run result: {json.dumps(dry_result, indent=2)}")

    if not dry_result.get("dry_run"):
        print_error("Expected dry_run=true in response")
        sys.exit(1)

    if dry_result.get("purged_parents") != 1:
        print_error(f"Expected 1 parent candidate, got {dry_result.get('purged_parents')}")
        sys.exit(1)

    if dry_result.get("purged_chunks") != 3:
        print_error(f"Expected 3 chunk candidates, got {dry_result.get('purged_chunks')}")
        sys.exit(1)

    # Verify counts after dry-run (should be unchanged)
    deleted_count_after_dry = count_nodes_by_class("Deleted", tenant_id="default")
    chunk_count_after_dry = count_nodes_by_class("Chunk", tenant_id="default")

    if deleted_count != deleted_count_after_dry or chunk_count != chunk_count_after_dry:
        print_error("Dry-run mode modified data! Expected no changes.")
        sys.exit(1)

    print_success("Dry-run completed without modifying data")

    # Test 4: Actual purge
    print_header("Test 4: Actual Purge")

    print_step("Calling purge API in actual mode")
    purge_result = call_purge_api(tenant_id="default", batch_size=500, dry_run=False)

    print_success(f"Purge result: {json.dumps(purge_result, indent=2)}")

    if purge_result.get("dry_run"):
        print_error("Expected dry_run=false in response")
        sys.exit(1)

    if purge_result.get("purged_parents") != 1:
        print_error(f"Expected 1 parent purged, got {purge_result.get('purged_parents')}")
        sys.exit(1)

    if purge_result.get("purged_chunks") != 3:
        print_error(f"Expected 3 chunks purged, got {purge_result.get('purged_chunks')}")
        sys.exit(1)

    # Test 5: Verify removal
    print_header("Test 5: Verify Removal")

    print_step("Counting nodes after purge")
    deleted_count_after = count_nodes_by_class("Deleted", tenant_id="default")
    chunk_count_after = count_nodes_by_class("Chunk", tenant_id="default")

    print_success(f"Nodes after purge: {deleted_count_after} Deleted, {chunk_count_after} Chunks")

    if deleted_count_after != 0:
        print_error(f"Expected 0 Deleted nodes, found {deleted_count_after}")
        sys.exit(1)

    if chunk_count_after != 0:
        print_error(f"Expected 0 Chunk nodes, found {chunk_count_after}")
        sys.exit(1)

    print_success("All soft-deleted nodes were purged successfully")

    # Test 6: Tenant isolation
    print_header("Test 6: Tenant Isolation")

    print_step("Creating nodes for tenant 'tenant-a'")
    parent_a = create_node(
        props={"external_id": "test-parent-a", "title": "Tenant A Doc"},
        classes=["Document"],
        tenant_id="tenant-a",
    )
    mark_node_deleted(parent_a, grace_hours=-1, tenant_id="tenant-a")

    print_step("Creating nodes for tenant 'tenant-b'")
    parent_b = create_node(
        props={"external_id": "test-parent-b", "title": "Tenant B Doc"},
        classes=["Document"],
        tenant_id="tenant-b",
    )
    mark_node_deleted(parent_b, grace_hours=-1, tenant_id="tenant-b")

    print_step("Purging only tenant-a")
    purge_a = call_purge_api(tenant_id="tenant-a", dry_run=False)
    print_success(f"Tenant-a purge: {json.dumps(purge_a, indent=2)}")

    # Verify tenant-a purged, tenant-b intact
    count_a = count_nodes_by_class("Deleted", tenant_id="tenant-a")
    count_b = count_nodes_by_class("Deleted", tenant_id="tenant-b")

    print_success(f"After tenant-a purge: tenant-a={count_a}, tenant-b={count_b}")

    if count_a != 0:
        print_error(f"Expected tenant-a to have 0 Deleted nodes, found {count_a}")
        sys.exit(1)

    if count_b != 1:
        print_error(f"Expected tenant-b to have 1 Deleted node, found {count_b}")
        sys.exit(1)

    print_success("Tenant isolation verified: tenant-a purged, tenant-b intact")

    # Cleanup tenant-b
    print_step("Cleaning up tenant-b")
    call_purge_api(tenant_id="tenant-b", dry_run=False)

    # Final summary
    print_header("ALL TESTS PASSED ✓")
    print("\nSoft-delete purger functionality verified:")
    print("  ✓ Parent + chunks creation")
    print("  ✓ Soft-delete marking with past grace period")
    print("  ✓ Dry-run mode (preview without changes)")
    print("  ✓ Actual purge (permanent deletion)")
    print("  ✓ Post-purge verification (confirms removal)")
    print("  ✓ Tenant isolation (RLS enforcement)")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"Test failed with error: {str(e)}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
