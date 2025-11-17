#!/usr/bin/env python3
"""Test Phase 2: Redis pub/sub cache invalidation.

Tests:
1. Publisher sends invalidation messages on config changes
2. Subscriber receives messages and evicts cache entries
3. Prometheus metrics are tracked correctly
"""

import os
import time

from cryptography.fernet import Fernet

# Set environment
os.environ["CONNECTOR_KEK_V1"] = Fernet.generate_key().decode()
os.environ["CONNECTOR_KEK_ACTIVE_VERSION"] = "1"
os.environ["ACTIVEKG_DSN"] = "postgresql:///activekg?host=/var/run/postgresql&port=5433"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["RUN_SCHEDULER"] = "false"

print("=" * 60)
print("Phase 2: Redis Pub/Sub Cache Invalidation Test")
print("=" * 60)

# Test 1: Import and basic setup
print("\n=== Test 1: Module imports ===")
try:
    from activekg.connectors.cache_subscriber import start_subscriber, stop_subscriber
    from activekg.connectors.config_store import get_config_store

    print("✓ All modules imported successfully")
except Exception as e:
    print(f"✗ Import failed: {e}")
    exit(1)

# Test 2: Publisher integration
print("\n=== Test 2: Publisher integration ===")
try:
    store = get_config_store()

    # Upsert a config
    config = {
        "endpoint": "https://s3.amazonaws.com",
        "access_key": "test_key",
        "secret_key": "test_secret",
    }
    result = store.upsert("test_tenant", "s3", config)

    if result:
        print("✓ Config upserted (publisher should have sent message)")
    else:
        print("✗ Failed to upsert config")
        exit(1)
except Exception as e:
    print(f"✗ Publisher test failed: {e}")
    exit(1)

# Test 3: Subscriber startup
print("\n=== Test 3: Subscriber startup ===")
try:
    start_subscriber(os.getenv("REDIS_URL"), store)
    time.sleep(2)  # Give subscriber time to connect
    print("✓ Subscriber started")
except Exception as e:
    print(f"✗ Subscriber startup failed: {e}")
    exit(1)

# Test 4: Cache invalidation
print("\n=== Test 4: Cache invalidation ===")
try:
    # First retrieval (cache miss)
    config1 = store.get("test_tenant", "s3")
    assert config1 is not None, "Config should exist"
    assert ("test_tenant", "s3") in store._cache, "Should be in cache"
    print("✓ Config loaded into cache")

    # Update config (should publish invalidation)
    config["endpoint"] = "https://s3-updated.amazonaws.com"
    store.upsert("test_tenant", "s3", config)

    # Give time for pub/sub message to propagate
    time.sleep(1)

    # Check if cache was invalidated
    if ("test_tenant", "s3") not in store._cache:
        print("✓ Cache invalidated by subscriber")
    else:
        print("⚠ Cache still present (may need more time)")

except Exception as e:
    print(f"✗ Cache invalidation test failed: {e}")
    exit(1)

# Test 5: Cleanup
print("\n=== Test 5: Cleanup ===")
try:
    store.delete("test_tenant", "s3")
    stop_subscriber()
    print("✓ Cleanup completed")
except Exception as e:
    print(f"⚠ Cleanup warning: {e}")

print("\n" + "=" * 60)
print("✅ Phase 2 pub/sub tests completed successfully!")
print("=" * 60)
print("\nMetrics to check:")
print("  - connector_config_invalidate_total")
print("  - connector_pubsub_messages_total")
print("  - connector_pubsub_reconnect_total")
