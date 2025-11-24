"""Tests for security limits, error counters, and Pydantic validation.

These tests can run without a database connection by setting ACTIVEKG_TEST_NO_DB=true.
For integration tests with real DB, unset the flag or set it to false.
"""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Enable test mode to avoid DB connection during import
os.environ["ACTIVEKG_TEST_NO_DB"] = "true"
os.environ["JWT_ENABLED"] = "false"  # Disable JWT for easier testing

from activekg.api.main import app, get_route_name
from activekg.connectors.config_store import validate_connector_config


class TestSecurityLimitsEndpoint:
    """Test /_admin/security/limits endpoint."""

    def test_security_limits_default_config(self):
        """Test security limits with default configuration."""
        client = TestClient(app)

        # Test without JWT (dev mode)
        with patch.dict(os.environ, {"JWT_ENABLED": "false"}, clear=False):
            response = client.get("/_admin/security/limits")

        assert response.status_code == 200
        data = response.json()

        # Verify SSRF protection structure
        assert "ssrf_protection" in data
        assert data["ssrf_protection"]["enabled"] is True
        assert data["ssrf_protection"]["max_fetch_bytes"] == 10485760  # 10MB default
        assert data["ssrf_protection"]["max_fetch_mb"] == 10.0
        assert data["ssrf_protection"]["fetch_timeout_seconds"] == 10.0
        assert "text/*" in data["ssrf_protection"]["allowed_content_types"]
        assert "application/json" in data["ssrf_protection"]["allowed_content_types"]

        # Verify blocked IP ranges
        blocked_ranges = data["ssrf_protection"]["blocked_ip_ranges"]
        assert any("127.0.0.0/8" in r for r in blocked_ranges)
        assert any("169.254.0.0/16" in r for r in blocked_ranges)

        # Verify file access protection
        assert "file_access" in data
        assert data["file_access"]["enabled"] is True
        assert data["file_access"]["symlinks_blocked"] is True
        assert data["file_access"]["max_file_bytes"] == 1048576  # 1MB default
        assert data["file_access"]["max_file_mb"] == 1.0

        # Verify request limits
        assert "request_limits" in data
        assert data["request_limits"]["max_request_body_bytes"] == 10485760
        assert data["request_limits"]["max_request_body_mb"] == 10.0
        assert "Content-Length header" in data["request_limits"]["enforced_for"]
        assert "chunked transfers" in data["request_limits"]["enforced_for"]

    def test_security_limits_with_allowlist(self):
        """Test security limits with URL allowlist configured."""
        client = TestClient(app)

        with patch.dict(
            os.environ,
            {
                "JWT_ENABLED": "false",
                "ACTIVEKG_URL_ALLOWLIST": "example.com,trusted-api.com",
            },
            clear=False,
        ):
            response = client.get("/_admin/security/limits")

        assert response.status_code == 200
        data = response.json()

        allowlist = data["ssrf_protection"]["url_allowlist"]
        assert "example.com" in allowlist
        assert "trusted-api.com" in allowlist

    def test_security_limits_with_custom_file_basedirs(self):
        """Test security limits with custom file basedirs."""
        client = TestClient(app)

        with patch.dict(
            os.environ,
            {
                "JWT_ENABLED": "false",
                "ACTIVEKG_FILE_BASEDIRS": "/opt/data,/mnt/uploads",
            },
            clear=False,
        ):
            response = client.get("/_admin/security/limits")

        assert response.status_code == 200
        data = response.json()

        basedirs = data["file_access"]["allowed_base_directories"]
        assert "/opt/data" in basedirs
        assert "/mnt/uploads" in basedirs


class TestRouteNameExtraction:
    """Test route name extraction for metrics."""

    def test_get_route_name_with_path_params(self):
        """Test that route name uses template, not actual values."""

        # Create a mock request with route info
        class MockRoute:
            path = "/nodes/{node_id}"

        class MockScope:
            def __getitem__(self, key):
                if key == "route":
                    return MockRoute()
                return {}

        class MockRequest:
            scope = {"route": MockRoute()}
            url = type("URL", (), {"path": "/nodes/abc-123"})()
            app = app

        request = MockRequest()
        route_name = get_route_name(request)

        # Should return template, not actual ID
        assert route_name == "/nodes/{node_id}"

    def test_get_route_name_fallback(self):
        """Test route name fallback to raw path when template not available."""

        class MockRequest:
            scope = {}
            url = type("URL", (), {"path": "/custom/path"})()
            app = app

        request = MockRequest()
        route_name = get_route_name(request)

        # Should fallback to raw path
        assert route_name == "/custom/path"


class TestPydanticValidation:
    """Test Pydantic validation for connector configs."""

    def test_s3_config_validation_valid(self):
        """Test valid S3 config passes validation."""
        config = {
            "bucket": "my-bucket",
            "prefix": "data/",
            "region": "us-west-2",
            "access_key_id": "AKIA1234567890ABCDEF",
            "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        }

        validated = validate_connector_config("s3", config)

        assert validated["bucket"] == "my-bucket"
        assert validated["region"] == "us-west-2"
        assert validated["access_key_id"] == "AKIA1234567890ABCDEF"

    def test_s3_config_validation_invalid_access_key(self):
        """Test invalid S3 config (access key too short) raises error."""
        config = {
            "bucket": "my-bucket",
            "access_key_id": "SHORT",  # Too short (min 16 chars)
            "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        }

        with pytest.raises(ValueError, match="Invalid s3 config"):
            validate_connector_config("s3", config)

    def test_s3_config_validation_invalid_secret_key(self):
        """Test invalid S3 config (secret key too short) raises error."""
        config = {
            "bucket": "my-bucket",
            "access_key_id": "AKIA1234567890ABCDEF",
            "secret_access_key": "TOO_SHORT",  # Too short (min 32 chars)
        }

        with pytest.raises(ValueError, match="Invalid s3 config"):
            validate_connector_config("s3", config)

    def test_gcs_config_validation_valid(self):
        """Test valid GCS config passes validation."""
        config = {
            "bucket": "my-gcs-bucket",
            "prefix": "data/",
            "service_account_json_path": "/path/to/service-account.json",
        }

        validated = validate_connector_config("gcs", config)

        assert validated["bucket"] == "my-gcs-bucket"
        assert validated["service_account_json_path"] == "/path/to/service-account.json"

    def test_drive_config_validation_valid(self):
        """Test valid Drive config passes validation."""
        config = {
            "folder_id": "1a2b3c4d5e6f",
            "service_account_json_path": "/path/to/service-account.json",
        }

        validated = validate_connector_config("drive", config)

        assert validated["folder_id"] == "1a2b3c4d5e6f"

    def test_unknown_provider_skips_validation(self):
        """Test unknown provider skips validation but returns config."""
        config = {"custom_field": "value"}

        validated = validate_connector_config("unknown_provider", config)

        # Should return config unchanged
        assert validated == config

    def test_poll_interval_validation(self):
        """Test poll_interval is validated (must be >= 60 and <= 3600)."""
        # Valid: within range
        config = {
            "bucket": "my-bucket",
            "access_key_id": "AKIA1234567890ABCDEF",
            "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "poll_interval_seconds": 600,
        }
        validated = validate_connector_config("s3", config)
        assert validated["poll_interval_seconds"] == 600

        # Invalid: too small
        config_too_small = {
            "bucket": "my-bucket",
            "access_key_id": "AKIA1234567890ABCDEF",
            "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "poll_interval_seconds": 30,  # Less than 60
        }
        with pytest.raises(ValueError):
            validate_connector_config("s3", config_too_small)

        # Invalid: too large
        config_too_large = {
            "bucket": "my-bucket",
            "access_key_id": "AKIA1234567890ABCDEF",
            "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "poll_interval_seconds": 7200,  # More than 3600
        }
        with pytest.raises(ValueError):
            validate_connector_config("s3", config_too_large)


class TestErrorMetrics:
    """Test error metrics with route names and error types."""

    def test_error_metrics_track_route_template(self):
        """Test that error metrics use route templates, not raw paths."""
        from activekg.observability.metrics import api_errors_total, record_api_error

        # Record an error with route template
        before_count = api_errors_total.labels(
            endpoint="/nodes/{node_id}", status="404", error_type="not_found"
        )._value.get()

        record_api_error("/nodes/{node_id}", 404, "not_found")

        after_count = api_errors_total.labels(
            endpoint="/nodes/{node_id}", status="404", error_type="not_found"
        )._value.get()

        assert after_count == before_count + 1

    def test_error_metrics_with_error_types(self):
        """Test that error metrics track error types."""
        from activekg.observability.metrics import api_errors_total, record_api_error

        # Test different error types
        before_validation = api_errors_total.labels(
            endpoint="/nodes", status="422", error_type="validation_error"
        )._value.get()

        record_api_error("/nodes", 422, "validation_error")

        after_validation = api_errors_total.labels(
            endpoint="/nodes", status="422", error_type="validation_error"
        )._value.get()

        assert after_validation == before_validation + 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
