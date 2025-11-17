#!/usr/bin/env python3
"""
Unit test for cron fallback behavior.

Tests that invalid cron expressions fall back to interval instead of
silently stalling refresh.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

from activekg.graph.models import Node
from activekg.graph.repository import GraphRepository


def test_cron_fallback_to_interval():
    """Test that invalid cron falls back to interval."""
    print("\n=== Test: Invalid Cron + Interval Fallback ===")

    # Mock DSN (we won't actually connect for this test)
    repo = GraphRepository("postgresql://localhost/test")

    # Create node with invalid cron + valid interval
    node = Node(
        classes=["TestDoc"],
        props={"text": "Test node"},
        embedding=np.random.rand(384).astype(np.float32),
        refresh_policy={
            "cron": "INVALID_CRON_EXPRESSION",  # Bad cron
            "interval": "5m",  # Valid interval
        },
        last_refreshed=datetime.now(timezone.utc) - timedelta(minutes=6),  # 6 min ago
        tenant_id="test",
    )

    # Test: Should fall back to interval
    is_due = repo._is_due_for_refresh(node)

    print("  Node policy: cron=INVALID, interval=5m")
    print("  Last refreshed: 6 minutes ago")
    print(f"  Is due for refresh: {is_due}")
    print("  Expected: True (falls back to interval, 6min > 5min)")

    if is_due:
        print("✅ PASS: Invalid cron correctly falls back to interval")
        return True
    else:
        print("❌ FAIL: Expected fallback to interval (should be due)")
        return False


def test_cron_fallback_without_interval():
    """Test that invalid cron without interval returns False."""
    print("\n=== Test: Invalid Cron + No Interval ===")

    repo = GraphRepository("postgresql://localhost/test")

    # Create node with only invalid cron (no interval)
    node = Node(
        classes=["TestDoc"],
        props={"text": "Test node"},
        embedding=np.random.rand(384).astype(np.float32),
        refresh_policy={
            "cron": "INVALID_CRON_EXPRESSION"  # Bad cron, no interval
        },
        last_refreshed=datetime.now(timezone.utc) - timedelta(minutes=6),
        tenant_id="test",
    )

    # Test: Should return False (no valid policy)
    is_due = repo._is_due_for_refresh(node)

    print("  Node policy: cron=INVALID, no interval")
    print("  Last refreshed: 6 minutes ago")
    print(f"  Is due for refresh: {is_due}")
    print("  Expected: False (no valid policy to fall back to)")

    if not is_due:
        print("✅ PASS: Invalid cron with no interval correctly returns False")
        return True
    else:
        print("❌ FAIL: Expected False (no valid policy)")
        return False


def test_valid_cron_no_fallback():
    """Test that valid cron does not fall back to interval."""
    print("\n=== Test: Valid Cron + Interval (No Fallback) ===")

    repo = GraphRepository("postgresql://localhost/test")

    # Create node with valid cron + interval (cron takes precedence)
    node = Node(
        classes=["TestDoc"],
        props={"text": "Test node"},
        embedding=np.random.rand(384).astype(np.float32),
        refresh_policy={
            "cron": "*/10 * * * *",  # Valid cron: every 10 minutes
            "interval": "5m",  # Interval: every 5 minutes (should be ignored)
        },
        last_refreshed=datetime.now(timezone.utc) - timedelta(minutes=7),  # 7 min ago
        tenant_id="test",
    )

    # Test: Should use cron (not due at 7min since cron is 10min)
    is_due = repo._is_due_for_refresh(node)

    print("  Node policy: cron=*/10 (10min), interval=5m")
    print("  Last refreshed: 7 minutes ago")
    print(f"  Is due for refresh: {is_due}")
    print("  Expected: False (cron precedence, 7min < 10min)")

    if not is_due:
        print("✅ PASS: Valid cron correctly takes precedence (no fallback)")
        return True
    else:
        print("❌ FAIL: Expected cron precedence (not due at 7min)")
        return False


def main():
    print("=" * 60)
    print("Cron Fallback Unit Tests")
    print("=" * 60)

    results = {}

    # Test 1: Invalid cron falls back to interval
    results["fallback_to_interval"] = test_cron_fallback_to_interval()

    # Test 2: Invalid cron without interval returns False
    results["fallback_without_interval"] = test_cron_fallback_without_interval()

    # Test 3: Valid cron does not fall back
    results["valid_cron_no_fallback"] = test_valid_cron_no_fallback()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print(
        f"Invalid cron + interval fallback:  {'✅ PASS' if results['fallback_to_interval'] else '❌ FAIL'}"
    )
    print(
        f"Invalid cron + no interval:        {'✅ PASS' if results['fallback_without_interval'] else '❌ FAIL'}"
    )
    print(
        f"Valid cron precedence (no fallback):{'✅ PASS' if results['valid_cron_no_fallback'] else '❌ FAIL'}"
    )

    total_pass = sum(results.values())
    print(f"\nTotal: {total_pass}/3 tests passed")

    if total_pass == 3:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠️  {3 - total_pass} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
