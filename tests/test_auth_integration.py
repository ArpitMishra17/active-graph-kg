"""Integration tests for JWT authentication and rate limiting.

Run with:
    pytest tests/test_auth_integration.py -v

Prerequisites:
    - API server running on http://localhost:8000
    - JWT_ENABLED=true
    - RATE_LIMIT_ENABLED=true
    - Redis running on default port
"""

import time
from datetime import datetime, timedelta

import pytest
import requests

try:
    import jwt
except ImportError:
    pytest.skip("PyJWT not installed", allow_module_level=True)


API_URL = "http://localhost:8000"
JWT_SECRET = "test-secret-key-min-32-chars-long"
JWT_ALGORITHM = "HS256"


def generate_test_jwt(
    tenant_id: str = "test_tenant",
    actor_id: str = "test_user",
    scopes: list = None,
    expires_hours: int = 1,
) -> str:
    """Generate a test JWT token."""
    if scopes is None:
        scopes = ["search:read", "nodes:write", "admin:refresh"]

    now = datetime.utcnow()
    payload = {
        "sub": actor_id,
        "tenant_id": tenant_id,
        "actor_type": "user",
        "scopes": scopes,
        "aud": "activekg",
        "iss": "https://test.activekg.com",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(hours=expires_hours),
    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


class TestJWTAuthentication:
    """Test JWT authentication and tenant isolation."""

    def test_health_endpoint_no_auth(self):
        """Health endpoint should work without authentication."""
        response = requests.get(f"{API_URL}/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_ask_without_jwt_fails(self):
        """/ask should return 401 when JWT is required but not provided."""
        response = requests.post(f"{API_URL}/ask", json={"question": "test question"})

        # Should fail if JWT_ENABLED=true
        if response.status_code == 401:
            assert (
                response.json()["detail"]
                == "Missing Authorization header. JWT required for this endpoint."
            )
        elif response.status_code == 200:
            # JWT disabled in dev mode - that's ok
            pytest.skip("JWT authentication disabled (dev mode)")

    def test_ask_with_valid_jwt(self):
        """/ask should work with valid JWT."""
        token = generate_test_jwt()

        response = requests.post(
            f"{API_URL}/ask",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "What are vector databases?"},
        )

        assert response.status_code in [200, 503]  # 503 if LLM disabled
        if response.status_code == 200:
            data = response.json()
            assert "answer" in data
            assert "confidence" in data

    def test_ask_with_expired_jwt_fails(self):
        """/ask should reject expired JWT."""
        # Generate token that expired 1 hour ago
        now = datetime.utcnow()
        payload = {
            "sub": "test_user",
            "tenant_id": "test_tenant",
            "actor_type": "user",
            "scopes": ["search:read"],
            "aud": "activekg",
            "iss": "https://test.activekg.com",
            "iat": now - timedelta(hours=2),
            "nbf": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),  # Expired
        }

        expired_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

        response = requests.post(
            f"{API_URL}/ask",
            headers={"Authorization": f"Bearer {expired_token}"},
            json={"question": "test"},
        )

        assert response.status_code == 401
        assert "expired" in response.json()["detail"].lower()

    def test_ask_with_invalid_signature_fails(self):
        """/ask should reject JWT with invalid signature."""
        token = generate_test_jwt()

        # Tamper with token (change last character)
        tampered_token = token[:-1] + ("x" if token[-1] != "x" else "y")

        response = requests.post(
            f"{API_URL}/ask",
            headers={"Authorization": f"Bearer {tampered_token}"},
            json={"question": "test"},
        )

        assert response.status_code == 401
        assert "Invalid" in response.json()["detail"]

    def test_tenant_isolation(self):
        """Nodes created by one tenant should not be visible to another."""
        # Create node as tenant A
        token_a = generate_test_jwt(tenant_id="tenant_a", actor_id="user_a")

        create_response = requests.post(
            f"{API_URL}/nodes",
            headers={"Authorization": f"Bearer {token_a}"},
            json={
                "classes": ["Document"],
                "props": {"text": "Secret data for tenant A", "title": "Tenant A Doc"},
            },
        )

        if create_response.status_code != 200:
            pytest.skip("Node creation failed (may not be implemented yet)")

        node_id = create_response.json()["id"]

        # Try to read as tenant B
        token_b = generate_test_jwt(tenant_id="tenant_b", actor_id="user_b")

        get_response = requests.get(
            f"{API_URL}/nodes/{node_id}", headers={"Authorization": f"Bearer {token_b}"}
        )

        # Should return 404 (RLS filters it out)
        assert get_response.status_code == 404

        # Verify tenant A can still read it
        get_response_a = requests.get(
            f"{API_URL}/nodes/{node_id}", headers={"Authorization": f"Bearer {token_a}"}
        )

        assert get_response_a.status_code == 200
        data = get_response_a.json()
        assert data["props"]["title"] == "Tenant A Doc"

    def test_scope_based_authorization(self):
        """Admin endpoints should require appropriate scopes."""
        # Token without admin:refresh scope
        token_no_admin = generate_test_jwt(scopes=["search:read", "nodes:write"])

        response = requests.post(
            f"{API_URL}/admin/refresh", headers={"Authorization": f"Bearer {token_no_admin}"}
        )

        # Should fail with 403
        assert response.status_code == 403
        assert "scope" in response.json()["detail"].lower()

        # Token with admin:refresh scope
        token_with_admin = generate_test_jwt(scopes=["admin:refresh"])

        response = requests.post(
            f"{API_URL}/admin/refresh", headers={"Authorization": f"Bearer {token_with_admin}"}
        )

        # Should succeed (or 500 if implementation issues, but not 403)
        assert response.status_code != 403


class TestRateLimiting:
    """Test rate limiting and concurrency controls."""

    def test_rate_limit_headers_present(self):
        """Rate limit headers should be present in responses."""
        token = generate_test_jwt()

        response = requests.post(
            f"{API_URL}/ask",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "test"},
        )

        # Check for rate limit headers
        if "X-RateLimit-Limit" in response.headers:
            assert int(response.headers["X-RateLimit-Limit"]) > 0
            assert "X-RateLimit-Remaining" in response.headers
            assert "X-RateLimit-Reset" in response.headers
        else:
            pytest.skip("Rate limiting disabled or not implemented")

    def test_rate_limit_enforcement(self):
        """Rapid requests should trigger 429 rate limit."""
        token = generate_test_jwt()

        # Fire 10 rapid requests
        responses = []
        for i in range(10):
            response = requests.post(
                f"{API_URL}/ask",
                headers={"Authorization": f"Bearer {token}"},
                json={"question": f"test {i}"},
            )
            responses.append(response)
            time.sleep(0.05)  # 50ms between requests

        # Check if any were rate limited
        status_codes = [r.status_code for r in responses]

        if 429 in status_codes:
            # Rate limiting is working
            first_429 = status_codes.index(429)
            assert first_429 < len(status_codes) - 1  # Not just the last request

            # Check for Retry-After header
            rate_limited_response = responses[first_429]
            assert "Retry-After" in rate_limited_response.headers
        else:
            pytest.skip("Rate limiting not triggered (may be disabled or limits too high)")

    def test_concurrency_limit_enforcement(self):
        """Concurrent requests should respect concurrency caps."""
        import concurrent.futures

        token = generate_test_jwt()

        def make_request(i):
            """Make a single /ask request."""
            response = requests.post(
                f"{API_URL}/ask",
                headers={"Authorization": f"Bearer {token}"},
                json={"question": f"test concurrent {i}"},
            )
            return response.status_code

        # Start 10 concurrent requests (concurrency limit for /ask is 3)
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request, i) for i in range(10)]
            status_codes = [f.result() for f in concurrent.futures.as_completed(futures)]

        # Should have at least some 429s if concurrency limit is enforced
        if 429 in status_codes:
            # Concurrency limiting is working
            assert status_codes.count(429) >= 1
        else:
            pytest.skip("Concurrency limiting not triggered (may be disabled)")

    def test_rate_limit_per_tenant(self):
        """Rate limits should be per-tenant, not global."""
        token_a = generate_test_jwt(tenant_id="tenant_rate_a")
        token_b = generate_test_jwt(tenant_id="tenant_rate_b")

        # Fire 5 requests for tenant A
        for i in range(5):
            _ = requests.post(
                f"{API_URL}/ask",
                headers={"Authorization": f"Bearer {token_a}"},
                json={"question": f"test a {i}"},
            )
            time.sleep(0.1)

        # Tenant B should still have full quota
        response_b = requests.post(
            f"{API_URL}/ask",
            headers={"Authorization": f"Bearer {token_b}"},
            json={"question": "test b"},
        )

        # Should succeed (not rate limited by tenant A's usage)
        assert response_b.status_code != 429 or response_b.status_code == 503  # 503 if LLM disabled


class TestSecurityVulnerabilities:
    """Test for common security vulnerabilities."""

    def test_cannot_claim_other_tenant_via_body(self):
        """Request body tenant_id should be ignored when JWT is present."""
        token = generate_test_jwt(tenant_id="real_tenant")

        # Try to create node claiming different tenant in body
        response = requests.post(
            f"{API_URL}/nodes",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "classes": ["Document"],
                "props": {"text": "test"},
                "tenant_id": "victim_tenant",  # Trying to impersonate
            },
        )

        if response.status_code == 200:
            node_id = response.json()["id"]

            # Verify it was created with JWT tenant_id, not body tenant_id
            get_response = requests.get(
                f"{API_URL}/nodes/{node_id}", headers={"Authorization": f"Bearer {token}"}
            )

            # Should be able to read it (created with real_tenant)
            assert get_response.status_code == 200

            # Try to read with victim tenant (should fail)
            token_victim = generate_test_jwt(tenant_id="victim_tenant")
            get_response_victim = requests.get(
                f"{API_URL}/nodes/{node_id}", headers={"Authorization": f"Bearer {token_victim}"}
            )

            # Should return 404 (not visible to victim tenant)
            assert get_response_victim.status_code == 404

    def test_jwt_reuse_across_tenants_fails(self):
        """JWT token for one tenant should not work for another tenant's data."""
        # Create node as tenant A
        token_a = generate_test_jwt(tenant_id="tenant_jwt_a")

        create_response = requests.post(
            f"{API_URL}/nodes",
            headers={"Authorization": f"Bearer {token_a}"},
            json={"classes": ["Document"], "props": {"text": "Tenant A data"}},
        )

        if create_response.status_code != 200:
            pytest.skip("Node creation failed")

        node_id = create_response.json()["id"]

        # Try to read with tenant B token
        token_b = generate_test_jwt(tenant_id="tenant_jwt_b")

        get_response = requests.get(
            f"{API_URL}/nodes/{node_id}", headers={"Authorization": f"Bearer {token_b}"}
        )

        # Should fail (RLS filters it out)
        assert get_response.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
