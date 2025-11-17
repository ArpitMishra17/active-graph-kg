#!/usr/bin/env python3
"""Unit tests for SNS message signature verification.

Tests:
- Certificate URL validation
- Certificate fetching and caching
- Canonical string building
- Signature verification (valid/invalid)
- Timeout handling
- Error cases
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

from activekg.connectors.sns_verify import (
    build_canonical_string,
    clear_cert_cache,
    fetch_certificate,
    validate_cert_url,
    verify_signature,
    verify_sns_message,
)

# Test fixtures


@pytest.fixture
def rsa_keypair():
    """Generate RSA keypair for testing."""
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture
def test_certificate(rsa_keypair):
    """Generate test X.509 certificate."""
    private_key, public_key = rsa_keypair

    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Washington"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Seattle"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Amazon Web Services"),
            x509.NameAttribute(NameOID.COMMON_NAME, "sns.amazonaws.com"),
        ]
    )

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=365))
        .sign(private_key, hashes.SHA256(), default_backend())
    )

    return cert


@pytest.fixture
def sample_sns_notification():
    """Sample SNS Notification message."""
    return {
        "Type": "Notification",
        "MessageId": "12345678-1234-1234-1234-123456789012",
        "TopicArn": "arn:aws:sns:us-east-1:123456789012:activekg-s3-test",
        "Subject": "Amazon S3 Notification",
        "Message": json.dumps(
            {
                "Records": [
                    {
                        "eventName": "ObjectCreated:Put",
                        "s3": {
                            "bucket": {"name": "my-bucket"},
                            "object": {"key": "test.txt", "eTag": "abc123"},
                        },
                    }
                ]
            }
        ),
        "Timestamp": "2025-01-01T12:00:00.000Z",
        "SignatureVersion": "1",
    }


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear certificate cache before each test."""
    clear_cert_cache()
    yield
    clear_cert_cache()


# Test certificate URL validation


def test_validate_cert_url_valid():
    """Test that valid AWS certificate URLs pass validation."""
    valid_urls = [
        "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-abc123.pem",
        "https://sns.us-west-2.amazonaws.com/SimpleNotificationService-xyz789.pem",
        "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-test.pem",
    ]

    for url in valid_urls:
        assert validate_cert_url(url) is True, f"Valid URL rejected: {url}"


def test_validate_cert_url_not_https():
    """Test that non-HTTPS URLs are rejected."""
    assert validate_cert_url("http://sns.amazonaws.com/SimpleNotificationService-test.pem") is False


def test_validate_cert_url_not_amazonaws():
    """Test that non-amazonaws.com URLs are rejected."""
    invalid_urls = [
        "https://evil.com/SimpleNotificationService-test.pem",
        "https://sns.fakeamazonaws.com/SimpleNotificationService-test.pem",
        "https://amazonaws.com.evil.com/SimpleNotificationService-test.pem",
    ]

    for url in invalid_urls:
        assert validate_cert_url(url) is False, f"Invalid URL accepted: {url}"


def test_validate_cert_url_missing_sns_path():
    """Test that URLs without SimpleNotificationService in path are rejected."""
    assert validate_cert_url("https://sns.amazonaws.com/test.pem") is False


def test_validate_cert_url_malformed():
    """Test that malformed URLs are rejected."""
    assert validate_cert_url("not-a-url") is False
    assert validate_cert_url("") is False


# Test certificate fetching


@patch("activekg.connectors.sns_verify.requests.get")
def test_fetch_certificate_success(mock_get, test_certificate):
    """Test successful certificate fetch and caching."""
    cert_pem = test_certificate.public_bytes(serialization.Encoding.PEM)
    mock_get.return_value.content = cert_pem
    mock_get.return_value.raise_for_status = Mock()

    cert_url = "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-test.pem"

    # First fetch - should hit network
    cert = fetch_certificate(cert_url)
    assert cert is not None
    assert mock_get.call_count == 1

    # Second fetch - should hit cache
    cert2 = fetch_certificate(cert_url)
    assert cert2 is not None
    assert cert == cert2
    assert mock_get.call_count == 1  # No additional network call


@patch("activekg.connectors.sns_verify.requests.get")
def test_fetch_certificate_timeout(mock_get):
    """Test that certificate fetch timeout is handled."""
    import requests

    mock_get.side_effect = requests.exceptions.Timeout()

    cert_url = "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-test.pem"
    cert = fetch_certificate(cert_url)

    assert cert is None


@patch("activekg.connectors.sns_verify.requests.get")
def test_fetch_certificate_http_error(mock_get):
    """Test that HTTP errors are handled."""
    import requests

    mock_get.side_effect = requests.exceptions.RequestException("404 Not Found")

    cert_url = "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-test.pem"
    cert = fetch_certificate(cert_url)

    assert cert is None


@patch("activekg.connectors.sns_verify.requests.get")
def test_fetch_certificate_invalid_pem(mock_get):
    """Test that invalid PEM content is handled."""
    mock_get.return_value.content = b"not a valid PEM certificate"
    mock_get.return_value.raise_for_status = Mock()

    cert_url = "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-test.pem"
    cert = fetch_certificate(cert_url)

    assert cert is None


# Test canonical string building


def test_build_canonical_string_notification(sample_sns_notification):
    """Test canonical string building for Notification message."""
    canonical = build_canonical_string(sample_sns_notification, "Notification")

    # Should contain all required fields
    assert "Message\n" in canonical
    assert "MessageId\n" in canonical
    assert "Subject\n" in canonical
    assert "Timestamp\n" in canonical
    assert "TopicArn\n" in canonical
    assert "Type\n" in canonical

    # Should have correct format (FieldName\nFieldValue\n)
    assert canonical.startswith("Message\n")
    assert "Amazon S3 Notification" in canonical


def test_build_canonical_string_subscription_confirmation():
    """Test canonical string building for SubscriptionConfirmation message."""
    message = {
        "Type": "SubscriptionConfirmation",
        "MessageId": "test-123",
        "Token": "abc123",
        "TopicArn": "arn:aws:sns:us-east-1:123:test",
        "Message": "You have chosen to subscribe...",
        "SubscribeURL": "https://sns.amazonaws.com/?Action=ConfirmSubscription&Token=abc123",
        "Timestamp": "2025-01-01T12:00:00.000Z",
    }

    canonical = build_canonical_string(message, "SubscriptionConfirmation")

    # Should contain subscription-specific fields
    assert "Token\n" in canonical
    assert "SubscribeURL\n" in canonical
    assert "Message\n" in canonical


def test_build_canonical_string_missing_subject(sample_sns_notification):
    """Test that missing optional fields (Subject) are handled."""
    message = sample_sns_notification.copy()
    del message["Subject"]

    canonical = build_canonical_string(message, "Notification")

    # Should still work without Subject
    assert "Subject\n" not in canonical
    assert "Message\n" in canonical


# Test signature verification


@patch("activekg.connectors.sns_verify.fetch_certificate")
def test_verify_signature_valid(
    mock_fetch_cert, rsa_keypair, test_certificate, sample_sns_notification
):
    """Test valid signature verification."""
    private_key, public_key = rsa_keypair
    mock_fetch_cert.return_value = test_certificate

    # Build canonical string
    canonical = build_canonical_string(sample_sns_notification, "Notification")

    # Sign it with private key (SHA1 as per SNS spec)
    signature = private_key.sign(canonical.encode("utf-8"), padding.PKCS1v15(), hashes.SHA1())
    signature_b64 = base64.b64encode(signature).decode("utf-8")

    # Verify
    cert_url = "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-test.pem"
    result = verify_signature(sample_sns_notification, signature_b64, cert_url, "Notification")

    assert result is True


@patch("activekg.connectors.sns_verify.fetch_certificate")
def test_verify_signature_tampered_message(
    mock_fetch_cert, rsa_keypair, test_certificate, sample_sns_notification
):
    """Test that tampered messages fail verification."""
    private_key, public_key = rsa_keypair
    mock_fetch_cert.return_value = test_certificate

    # Build canonical string and sign
    canonical = build_canonical_string(sample_sns_notification, "Notification")
    signature = private_key.sign(canonical.encode("utf-8"), padding.PKCS1v15(), hashes.SHA1())
    signature_b64 = base64.b64encode(signature).decode("utf-8")

    # Tamper with message
    tampered_message = sample_sns_notification.copy()
    tampered_message["Message"] = "TAMPERED CONTENT"

    # Verify should fail
    cert_url = "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-test.pem"
    result = verify_signature(tampered_message, signature_b64, cert_url, "Notification")

    assert result is False


@patch("activekg.connectors.sns_verify.fetch_certificate")
def test_verify_signature_invalid_cert_url(mock_fetch_cert):
    """Test that invalid certificate URLs fail verification."""
    result = verify_signature(
        {"Type": "Notification"},
        "fake_signature",
        "http://evil.com/cert.pem",  # Not HTTPS, not amazonaws.com
        "Notification",
    )

    assert result is False
    assert mock_fetch_cert.call_count == 0  # Should reject before fetching


@patch("activekg.connectors.sns_verify.fetch_certificate")
def test_verify_signature_cert_fetch_fails(mock_fetch_cert, sample_sns_notification):
    """Test that certificate fetch failures are handled."""
    mock_fetch_cert.return_value = None  # Simulate fetch failure

    cert_url = "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-test.pem"
    result = verify_signature(sample_sns_notification, "fake_signature", cert_url, "Notification")

    assert result is False


@patch("activekg.connectors.sns_verify.fetch_certificate")
def test_verify_signature_invalid_base64(
    mock_fetch_cert, test_certificate, sample_sns_notification
):
    """Test that invalid base64 signatures are handled."""
    mock_fetch_cert.return_value = test_certificate

    cert_url = "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-test.pem"
    result = verify_signature(
        sample_sns_notification, "not-valid-base64!!!", cert_url, "Notification"
    )

    assert result is False


# Test verify_sns_message wrapper


@patch("activekg.connectors.sns_verify.verify_signature")
def test_verify_sns_message_valid(mock_verify_sig, sample_sns_notification):
    """Test verify_sns_message wrapper with valid message."""
    mock_verify_sig.return_value = True

    result = verify_sns_message(
        sample_sns_notification,
        "fake_signature",
        "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-test.pem",
        "1",
    )

    assert result is True
    mock_verify_sig.assert_called_once()


def test_verify_sns_message_unsupported_version(sample_sns_notification):
    """Test that unsupported signature versions are rejected."""
    result = verify_sns_message(
        sample_sns_notification,
        "fake_signature",
        "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-test.pem",
        "2",  # Unsupported version
    )

    assert result is False


# Integration-style test


@patch("activekg.connectors.sns_verify.requests.get")
def test_full_verification_flow(mock_get, rsa_keypair, test_certificate, sample_sns_notification):
    """Test full verification flow from SNS message to verified result."""
    private_key, public_key = rsa_keypair

    # Mock certificate fetch
    cert_pem = test_certificate.public_bytes(serialization.Encoding.PEM)
    mock_get.return_value.content = cert_pem
    mock_get.return_value.raise_for_status = Mock()

    # Build canonical string and sign
    canonical = build_canonical_string(sample_sns_notification, "Notification")
    signature = private_key.sign(canonical.encode("utf-8"), padding.PKCS1v15(), hashes.SHA1())
    signature_b64 = base64.b64encode(signature).decode("utf-8")

    # Verify
    cert_url = "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-test.pem"
    result = verify_sns_message(sample_sns_notification, signature_b64, cert_url, "1")

    assert result is True
