"""Fernet-based envelope encryption for connector secrets with KEK rotation support.

Security requirements:
- Secrets are encrypted at rest using Fernet symmetric encryption
- KEK (Key Encryption Key) loaded from environment variables with versioning
- Secrets never logged or printed
- Encryption key must be 32 URL-safe base64-encoded bytes
- Supports multiple KEK versions for zero-downtime key rotation

KEK versioning:
- CONNECTOR_KEK_ACTIVE_VERSION: Version to use for new encryptions (default: 1)
- CONNECTOR_KEK_V1, CONNECTOR_KEK_V2, ...: Versioned KEKs
- Legacy CONNECTOR_KEK: Falls back to V1 if no versioned KEKs found
"""
from __future__ import annotations

import os
import logging
from typing import Dict, Any, List, Optional

from cryptography.fernet import Fernet
from prometheus_client import Counter

logger = logging.getLogger(__name__)

# Prometheus metrics
connector_decrypt_failures_total = Counter(
    'connector_decrypt_failures_total',
    'Total connector secret decryption failures',
    ['field']
)

# Fields to encrypt in connector configs
SECRET_FIELDS = [
    "access_key_id",
    "secret_access_key",
    "api_key",
    "password",
    "token",
    "credentials"
]


def load_keks() -> Dict[int, Fernet]:
    """Load all available KEKs from environment variables.

    Returns:
        Dict mapping version number to Fernet cipher

    Raises:
        ValueError: If no KEKs found or invalid format
    """
    keks = {}

    # Try loading versioned KEKs (CONNECTOR_KEK_V1, CONNECTOR_KEK_V2, ...)
    for version in range(1, 10):  # Support up to V9
        kek_env = f"CONNECTOR_KEK_V{version}"
        kek_str = os.getenv(kek_env)
        if kek_str:
            try:
                keks[version] = Fernet(kek_str.encode())
                logger.debug(f"Loaded KEK version {version}")
            except Exception as e:
                logger.error(f"Invalid {kek_env}: {e}")
                raise ValueError(f"Invalid {kek_env}: {e}")

    # Fallback: legacy CONNECTOR_KEK → V1 if no versioned KEKs found
    if not keks:
        legacy_kek = os.getenv("CONNECTOR_KEK")
        if legacy_kek:
            try:
                keks[1] = Fernet(legacy_kek.encode())
                logger.debug("Loaded legacy CONNECTOR_KEK as V1")
            except Exception as e:
                raise ValueError(f"Invalid CONNECTOR_KEK: {e}")
        else:
            raise ValueError(
                "No KEKs found. Set CONNECTOR_KEK_V1 or legacy CONNECTOR_KEK. "
                "Generate with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )

    return keks


def get_active_version() -> int:
    """Get active KEK version for new encryptions.

    Returns:
        Active KEK version number

    Raises:
        ValueError: If CONNECTOR_KEK_ACTIVE_VERSION invalid
    """
    active_str = os.getenv("CONNECTOR_KEK_ACTIVE_VERSION", "1")
    try:
        return int(active_str)
    except ValueError:
        raise ValueError(f"CONNECTOR_KEK_ACTIVE_VERSION must be an integer, got: {active_str}")


class SecretEncryption:
    """Handles encryption/decryption of connector secrets with KEK rotation support."""

    def __init__(self, keks: Dict[int, Fernet] | None = None, active_version: int | None = None):
        """Initialize encryption handler with multi-KEK support.

        Args:
            keks: Dict of version -> Fernet cipher (loads from env if None)
            active_version: Version to use for new encryptions (loads from env if None)

        Raises:
            ValueError: If no KEKs available or active version not found
        """
        if keks is None:
            keks = load_keks()

        if active_version is None:
            active_version = get_active_version()

        if active_version not in keks:
            raise ValueError(
                f"Active KEK version {active_version} not found. "
                f"Available versions: {list(keks.keys())}"
            )

        self.keks = keks
        self.active_version = active_version
        self.active_cipher = keks[active_version]

    def encrypt_value(self, plaintext: str) -> str:
        """Encrypt a single secret value using active KEK.

        Args:
            plaintext: Plain text secret

        Returns:
            Base64-encoded ciphertext
        """
        if not plaintext:
            return plaintext

        ciphertext = self.active_cipher.encrypt(plaintext.encode())
        return ciphertext.decode()

    def decrypt_value(self, ciphertext: str, key_version: Optional[int] = None) -> str:
        """Decrypt a single secret value with KEK fallback support.

        Tries specified key_version first, then falls back to all available KEKs.

        Args:
            ciphertext: Base64-encoded ciphertext
            key_version: KEK version that encrypted this value (None = try all)

        Returns:
            Plain text secret

        Raises:
            ValueError: If decryption fails with all available KEKs
        """
        if not ciphertext:
            return ciphertext

        # Try specified version first if provided
        if key_version and key_version in self.keks:
            try:
                plaintext = self.keks[key_version].decrypt(ciphertext.encode())
                return plaintext.decode()
            except Exception:
                logger.warning(f"Failed to decrypt with specified KEK v{key_version}, trying fallback")

        # Fallback: try all available KEKs
        for version, cipher in self.keks.items():
            try:
                plaintext = cipher.decrypt(ciphertext.encode())
                if key_version and version != key_version:
                    logger.info(f"Decrypted with KEK v{version} (expected v{key_version})")
                return plaintext.decode()
            except Exception:
                continue

        # All KEKs failed
        logger.error(f"Failed to decrypt secret with any available KEK (tried versions: {list(self.keks.keys())})")
        raise ValueError("Decryption failed with all available KEKs")

    def encrypt_config(self, config: Dict[str, Any], secret_fields: List[str] | None = None) -> Dict[str, Any]:
        """Encrypt secret fields in connector config.

        Args:
            config: Connector config dict
            secret_fields: List of field names to encrypt (default: SECRET_FIELDS)

        Returns:
            Config with encrypted secret fields
        """
        if secret_fields is None:
            secret_fields = SECRET_FIELDS

        encrypted = config.copy()

        for field in secret_fields:
            if field in encrypted and encrypted[field]:
                encrypted[field] = self.encrypt_value(encrypted[field])

        return encrypted

    def decrypt_config(
        self,
        config: Dict[str, Any],
        secret_fields: List[str] | None = None,
        key_version: Optional[int] = None
    ) -> Dict[str, Any]:
        """Decrypt secret fields in connector config with KEK fallback support.

        Args:
            config: Connector config dict with encrypted secrets
            secret_fields: List of field names to decrypt (default: SECRET_FIELDS)
            key_version: KEK version that encrypted secrets (None = try all KEKs)

        Returns:
            Config with decrypted secret fields
        """
        if secret_fields is None:
            secret_fields = SECRET_FIELDS

        decrypted = config.copy()

        for field in secret_fields:
            if field in decrypted and decrypted[field]:
                try:
                    decrypted[field] = self.decrypt_value(decrypted[field], key_version=key_version)
                except Exception as e:
                    logger.error(f"Failed to decrypt field '{field}' with KEK v{key_version or 'any'}")
                    connector_decrypt_failures_total.labels(field=field).inc()
                    # Keep encrypted value, let caller handle
                    pass

        return decrypted


# Global singleton instance (lazy-loaded)
_encryption: SecretEncryption | None = None


def get_encryption() -> SecretEncryption:
    """Get global encryption instance.

    Returns:
        SecretEncryption instance

    Raises:
        ValueError: If CONNECTOR_KEK not set
    """
    global _encryption
    if _encryption is None:
        _encryption = SecretEncryption()
    return _encryption


def sanitize_config_for_logging(config: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize config for logging by redacting secret fields.

    Args:
        config: Connector config dict

    Returns:
        Config with secrets redacted as '***REDACTED***'
    """
    sanitized = config.copy()

    for field in SECRET_FIELDS:
        if field in sanitized and sanitized[field]:
            sanitized[field] = "***REDACTED***"

    return sanitized


# Example usage
if __name__ == "__main__":
    import sys

    # Generate new KEK
    if len(sys.argv) > 1 and sys.argv[1] == "generate-key":
        new_key = Fernet.generate_key()
        print("Generated KEK (save as CONNECTOR_KEK):")
        print(new_key.decode())
        sys.exit(0)

    # Test encryption/decryption
    os.environ["CONNECTOR_KEK"] = Fernet.generate_key().decode()
    enc = SecretEncryption()

    test_config = {
        "bucket": "my-bucket",
        "access_key_id": "AKIAIOSFODNN7EXAMPLE",
        "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "region": "us-east-1"
    }

    print("Original config:")
    print(sanitize_config_for_logging(test_config))

    encrypted = enc.encrypt_config(test_config)
    print("\nEncrypted config:")
    print(encrypted)

    decrypted = enc.decrypt_config(encrypted)
    print("\nDecrypted config:")
    print(sanitize_config_for_logging(decrypted))

    assert decrypted == test_config
    print("\n✓ Encryption/decryption successful!")
