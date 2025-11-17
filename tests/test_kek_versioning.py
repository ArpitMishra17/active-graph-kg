#!/usr/bin/env python3
"""Test KEK versioning implementation for zero-downtime key rotation.

Tests:
1. Multi-KEK loading from environment
2. Encryption with active KEK
3. Decryption with key_version fallback
4. Config store integration
"""

import os
import sys

from cryptography.fernet import Fernet

# Set up test environment
os.environ["CONNECTOR_KEK_V1"] = Fernet.generate_key().decode()
os.environ["CONNECTOR_KEK_V2"] = Fernet.generate_key().decode()
os.environ["CONNECTOR_KEK_ACTIVE_VERSION"] = "2"  # Use V2 for new encryptions
os.environ["ACTIVEKG_DSN"] = "postgresql:///activekg?host=/var/run/postgresql&port=5433"

from activekg.connectors.config_store import ConnectorConfigStore
from activekg.connectors.encryption import (
    SecretEncryption,
    get_active_version,
    load_keks,
)


def test_load_keks():
    """Test loading multiple KEK versions from environment."""
    print("Test 1: Loading KEKs from environment")
    keks = load_keks()

    assert 1 in keks, "KEK V1 should be loaded"
    assert 2 in keks, "KEK V2 should be loaded"
    assert len(keks) == 2, "Should have exactly 2 KEKs"
    print("✓ Loaded 2 KEK versions successfully")


def test_get_active_version():
    """Test reading active KEK version."""
    print("\nTest 2: Get active KEK version")
    active = get_active_version()

    assert active == 2, "Active version should be 2"
    print(f"✓ Active KEK version: {active}")


def test_encryption_decryption():
    """Test encryption with active KEK and decryption with fallback."""
    print("\nTest 3: Encryption/decryption with KEK versioning")
    enc = SecretEncryption()

    # Test that active version is V2
    assert enc.active_version == 2, "Active version should be 2"
    print(f"✓ Using active KEK version: {enc.active_version}")

    # Encrypt a secret
    plaintext = "my-secret-api-key-12345"
    ciphertext = enc.encrypt_value(plaintext)
    print(f"✓ Encrypted secret (length: {len(ciphertext)})")

    # Decrypt with correct version
    decrypted = enc.decrypt_value(ciphertext, key_version=2)
    assert decrypted == plaintext, "Decryption with V2 should work"
    print("✓ Decrypted with correct key version (V2)")

    # Decrypt without specifying version (should try all KEKs)
    decrypted2 = enc.decrypt_value(ciphertext)
    assert decrypted2 == plaintext, "Decryption without version should work"
    print("✓ Decrypted with automatic fallback")


def test_config_encryption():
    """Test config dict encryption/decryption."""
    print("\nTest 4: Config encryption/decryption")
    enc = SecretEncryption()

    test_config = {
        "bucket": "my-bucket",
        "access_key_id": "AKIAIOSFODNN7EXAMPLE",
        "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "region": "us-east-1",
    }

    # Encrypt
    encrypted = enc.encrypt_config(test_config)
    print("✓ Encrypted config dict")

    # Verify secrets are encrypted
    assert encrypted["access_key_id"] != test_config["access_key_id"], (
        "access_key_id should be encrypted"
    )
    assert encrypted["secret_access_key"] != test_config["secret_access_key"], (
        "secret_access_key should be encrypted"
    )
    assert encrypted["bucket"] == test_config["bucket"], "Non-secret fields should not be encrypted"
    print("✓ Verified only secret fields are encrypted")

    # Decrypt with key version
    decrypted = enc.decrypt_config(encrypted, key_version=2)
    assert decrypted["access_key_id"] == test_config["access_key_id"], (
        "Decryption should restore original"
    )
    assert decrypted["secret_access_key"] == test_config["secret_access_key"], (
        "Decryption should restore original"
    )
    print("✓ Decrypted config with key version")

    # Decrypt without key version (fallback)
    decrypted2 = enc.decrypt_config(encrypted)
    assert decrypted2 == test_config, "Fallback decryption should work"
    print("✓ Decrypted config with fallback")


def test_config_store_integration():
    """Test config store with KEK versioning."""
    print("\nTest 5: Config store integration")

    store = ConnectorConfigStore(os.environ["ACTIVEKG_DSN"])

    test_config = {
        "bucket": "test-bucket",
        "access_key_id": "AKIATEST123",
        "secret_access_key": "SECRET123",
        "region": "us-west-2",
    }

    # Upsert config (should use active KEK V2)
    success = store.upsert("test-tenant", "s3", test_config, enabled=True)
    assert success, "Upsert should succeed"
    print("✓ Upserted config to database")

    # Verify key_version was written correctly
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(os.environ["ACTIVEKG_DSN"], row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT key_version FROM connector_configs WHERE tenant_id = %s AND provider = %s",
                ("test-tenant", "s3"),
            )
            row = cur.fetchone()
            assert row is not None, "Row should exist"
            assert row["key_version"] == 2, "key_version should be 2 (active version)"
            print(f"✓ Verified key_version={row['key_version']} in database")

    # Retrieve config (should decrypt with stored key_version)
    retrieved = store.get("test-tenant", "s3")
    assert retrieved is not None, "Config should be retrieved"
    assert retrieved["access_key_id"] == test_config["access_key_id"], "Secrets should be decrypted"
    assert retrieved["secret_access_key"] == test_config["secret_access_key"], (
        "Secrets should be decrypted"
    )
    print("✓ Retrieved and decrypted config from database")

    # Clean up
    store.delete("test-tenant", "s3")
    print("✓ Cleaned up test data")


def test_fallback_decryption():
    """Test decryption fallback when key_version is wrong."""
    print("\nTest 6: Fallback decryption when key_version mismatches")

    enc = SecretEncryption()

    # Encrypt with V2 (active)
    plaintext = "fallback-test-secret"
    ciphertext = enc.encrypt_value(plaintext)
    print("✓ Encrypted with active KEK (V2)")

    # Try to decrypt with wrong version (V1) - should fallback to V2
    decrypted = enc.decrypt_value(ciphertext, key_version=1)
    assert decrypted == plaintext, "Should fallback to correct KEK"
    print("✓ Fallback decryption worked (tried V1, succeeded with V2)")


def main():
    """Run all tests."""
    print("=" * 60)
    print("KEK Versioning Tests - Phase 1 Implementation")
    print("=" * 60)

    try:
        test_load_keks()
        test_get_active_version()
        test_encryption_decryption()
        test_config_encryption()
        test_config_store_integration()
        test_fallback_decryption()

        print("\n" + "=" * 60)
        print("✅ All tests passed! Phase 1 implementation complete.")
        print("=" * 60)
        print("\nPhase 1 Summary:")
        print("  ✓ Multi-KEK loading from environment")
        print("  ✓ Active version selection")
        print("  ✓ Encryption with active KEK")
        print("  ✓ Decryption with version fallback")
        print("  ✓ Config store integration")
        print("  ✓ Database key_version tracking")
        print("\nNext Steps (Phase 2):")
        print("  - Redis pub/sub cache invalidation")
        print("  - Worker subscriber for config changes")
        print("\nNext Steps (Phase 3):")
        print("  - Admin endpoint for key rotation")
        print("  - Batch re-encryption logic")
        return 0
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
