#!/usr/bin/env python3
"""Generate test JWT tokens for backend testing."""

import os
from datetime import datetime, timedelta, timezone

import jwt

# Load from environment
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "test-secret-key-min-32-chars-long-for-testing-purposes")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
AUDIENCE = os.getenv("JWT_AUDIENCE", "activekg")
ISSUER = os.getenv("JWT_ISSUER", "https://test-auth.activekg.local")


def generate_token(tenant_id="test_tenant", scopes=None, user_id="test-user"):
    """Generate a JWT token for testing."""
    if scopes is None:
        scopes = ["search:read", "ask:read", "kg:write", "admin:refresh"]

    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "scopes": scopes,
        "email": f"{user_id}@test.com",
        "name": "Test User",
        "iat": now,
        "exp": now + timedelta(hours=24),
        "aud": AUDIENCE,
        "iss": ISSUER,
    }

    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token


if __name__ == "__main__":
    import sys

    tenant = sys.argv[1] if len(sys.argv) > 1 else "test_tenant"

    # Generate admin token (with admin:refresh scope)
    admin_token = generate_token(
        tenant_id=tenant, scopes=["search:read", "ask:read", "kg:write", "admin:refresh"]
    )
    print(f"Admin Token: {admin_token}")

    # Generate regular user token (without admin:refresh)
    user_token = generate_token(
        tenant_id=tenant, scopes=["search:read", "ask:read", "kg:write"], user_id="regular-user"
    )
    print(f"\nRegular User Token: {user_token}")
