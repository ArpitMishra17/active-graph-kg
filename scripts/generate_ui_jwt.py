#!/usr/bin/env python3
"""Generate JWT token for UI access to seeded test data."""

from datetime import datetime, timedelta, timezone

import jwt

# Configuration from .env.test
JWT_SECRET = "test-secret-key-min-32-chars-long-for-testing-purposes"
JWT_ALG = "HS256"
JWT_AUDIENCE = "activekg"
JWT_ISSUER = "https://test-auth.activekg.local"
TENANT_ID = "test-tenant"


def generate_ui_token():
    """Generate JWT token for UI access."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "ui_user",
        "tenant_id": TENANT_ID,
        "actor_type": "user",
        "scopes": ["search:read", "ask:read", "kg:write", "admin:refresh"],
        "aud": JWT_AUDIENCE,
        "iss": JWT_ISSUER,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(hours=24),  # Valid for 24 hours
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)
    return token


if __name__ == "__main__":
    token = generate_ui_token()
    print("\n" + "=" * 80)
    print("JWT TOKEN FOR UI ACCESS")
    print("=" * 80)
    print(f"\nTenant: {TENANT_ID}")
    print("Scopes: read, write, admin")
    print("Valid for: 24 hours")
    print("\n" + "-" * 80)
    print("TOKEN:")
    print("-" * 80)
    print(token)
    print("-" * 80)
    print("\nTo use in the UI:")
    print("1. Open http://localhost:5173")
    print("2. Paste this token when prompted for authentication")
    print("3. You should now be able to query the seeded nodes")
    print("=" * 80 + "\n")
