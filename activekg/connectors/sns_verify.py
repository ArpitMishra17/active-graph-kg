"""SNS message signature verification with certificate validation.

Security features:
- Certificate URL validation (HTTPS only, amazonaws.com)
- Certificate caching with TTL
- RSA signature verification using AWS public key
- Canonical string building per SNS spec

References:
- https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html
"""

from __future__ import annotations

import base64
import logging
import os
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import requests
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

logger = logging.getLogger(__name__)

# Certificate cache TTL (seconds)
CERT_CACHE_TTL = int(os.getenv("WEBHOOK_CERT_CACHE_TTL", "3600"))  # 1 hour default
CERT_HTTP_TIMEOUT = int(os.getenv("WEBHOOK_HTTP_TIMEOUT", "3"))  # 3 seconds

# Certificate cache: URL -> (cert, expiry_time)
_cert_cache: dict[str, tuple[x509.Certificate, datetime]] = {}


def validate_cert_url(cert_url: str) -> bool:
    """Validate that certificate URL is from AWS.

    Args:
        cert_url: Certificate URL from SNS message

    Returns:
        True if valid, False otherwise
    """
    try:
        parsed = urlparse(cert_url)

        # Must be HTTPS
        if parsed.scheme != "https":
            logger.error(f"Certificate URL not HTTPS: {cert_url}")
            return False

        # Must be from amazonaws.com
        if not parsed.hostname or not parsed.hostname.endswith(".amazonaws.com"):
            logger.error(f"Certificate URL not from amazonaws.com: {cert_url}")
            return False

        # Must contain SimpleNotificationService in path
        if "SimpleNotificationService" not in parsed.path:
            logger.error(f"Certificate URL path invalid: {cert_url}")
            return False

        return True

    except Exception as e:
        logger.error(f"Failed to parse certificate URL: {e}")
        return False


def fetch_certificate(cert_url: str) -> x509.Certificate | None:
    """Fetch and parse SNS certificate from URL.

    Implements caching with TTL to avoid repeated fetches.

    Args:
        cert_url: Certificate URL from SNS message

    Returns:
        Parsed certificate or None if fetch/parse fails
    """
    # Check cache first
    if cert_url in _cert_cache:
        cert, expiry = _cert_cache[cert_url]
        if datetime.utcnow() < expiry:
            logger.debug(f"Certificate cache hit: {cert_url}")
            return cert
        else:
            # Expired
            del _cert_cache[cert_url]
            logger.debug(f"Certificate cache expired: {cert_url}")

    # Fetch certificate
    try:
        logger.info(f"Fetching SNS certificate: {cert_url}")
        resp = requests.get(cert_url, timeout=CERT_HTTP_TIMEOUT)
        resp.raise_for_status()

        # Parse PEM certificate
        cert = x509.load_pem_x509_certificate(resp.content, default_backend())

        # Cache it
        expiry = datetime.utcnow() + timedelta(seconds=CERT_CACHE_TTL)
        _cert_cache[cert_url] = (cert, expiry)

        logger.info(f"Certificate fetched and cached: {cert_url}")
        return cert

    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching certificate: {cert_url}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch certificate: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to parse certificate: {e}")
        return None


def build_canonical_string(message: dict[str, Any], message_type: str) -> str:
    """Build canonical string for signature verification.

    Order matters: Message, MessageId, Subject (if present), Timestamp, TopicArn, Type

    Args:
        message: SNS message dict
        message_type: Type of SNS message (Notification, SubscriptionConfirmation, etc.)

    Returns:
        Canonical string for verification
    """
    # For Notifications, use these fields
    if message_type == "Notification":
        fields = ["Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"]
    # For SubscriptionConfirmation, use these fields
    elif message_type == "SubscriptionConfirmation":
        fields = ["Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"]
    # For UnsubscribeConfirmation
    elif message_type == "UnsubscribeConfirmation":
        fields = ["Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"]
    else:
        logger.warning(f"Unknown message type for signing: {message_type}")
        fields = ["Message", "MessageId", "Timestamp", "TopicArn", "Type"]

    # Build canonical string
    parts = []
    for field in fields:
        if field in message:
            # Each field is: "FieldName\nFieldValue\n"
            parts.append(f"{field}\n{message[field]}\n")

    canonical = "".join(parts)
    logger.debug(f"Canonical string length: {len(canonical)}")
    return canonical


def verify_signature(
    message: dict[str, Any], signature_b64: str, cert_url: str, message_type: str
) -> bool:
    """Verify SNS message signature.

    Args:
        message: SNS message dict
        signature_b64: Base64-encoded signature
        cert_url: Certificate URL
        message_type: Type of SNS message

    Returns:
        True if signature valid, False otherwise
    """
    try:
        # 1. Validate certificate URL
        if not validate_cert_url(cert_url):
            return False

        # 2. Fetch certificate
        cert = fetch_certificate(cert_url)
        if not cert:
            return False

        # 3. Build canonical string
        canonical = build_canonical_string(message, message_type)

        # 4. Decode signature
        try:
            signature = base64.b64decode(signature_b64)
        except Exception as e:
            logger.error(f"Failed to decode signature: {e}")
            return False

        # 5. Verify signature
        try:
            public_key = cert.public_key()

            # SNS uses SHA1 with RSA (PKCS1v15 padding)
            public_key.verify(
                signature, canonical.encode("utf-8"), padding.PKCS1v15(), hashes.SHA1()
            )

            logger.info("SNS signature verified successfully")
            return True

        except InvalidSignature:
            logger.error("SNS signature verification failed: invalid signature")
            return False

    except Exception as e:
        logger.error(f"SNS signature verification error: {e}")
        return False


def verify_sns_message(
    message: dict[str, Any], signature: str, cert_url: str, signature_version: str = "1"
) -> bool:
    """Verify SNS message signature (wrapper for webhook use).

    Args:
        message: SNS message dict
        signature: Base64-encoded signature
        cert_url: Certificate URL
        signature_version: Signature version (should be "1")

    Returns:
        True if signature valid, False otherwise
    """
    # Check signature version
    if signature_version != "1":
        logger.error(f"Unsupported signature version: {signature_version}")
        return False

    # Get message type
    message_type = message.get("Type", "Notification")

    # Verify
    return verify_signature(message, signature, cert_url, message_type)


# Metrics helper
def clear_cert_cache():
    """Clear certificate cache (for testing or forced refresh)."""
    global _cert_cache
    _cert_cache.clear()
    logger.info("Certificate cache cleared")
