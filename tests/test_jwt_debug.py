#!/usr/bin/env python3
"""Debug JWT generation."""

from datetime import datetime, timedelta, timezone

import jwt

# Generate JWT
payload = {
    "sub": "eval_seeder",
    "tenant_id": "eval_tenant",
    "actor_type": "user",
    "scopes": ["kg:write", "admin:refresh"],
    "aud": "activekg",
    "iss": "https://staging-auth.yourcompany.com",
    "iat": datetime.now(timezone.utc),
    "nbf": datetime.now(timezone.utc),
    "exp": datetime.now(timezone.utc) + timedelta(hours=1),
}

secret = "dev-secret-key-min-32-chars-long-for-testing"
algorithm = "HS256"

print("Payload:", payload)
print()

token = jwt.encode(payload, secret, algorithm=algorithm)
print("Generated token:", token)
print()

# Try to decode it
try:
    decoded = jwt.decode(
        token,
        secret,
        algorithms=[algorithm],
        audience="activekg",
        issuer="https://staging-auth.yourcompany.com",
        leeway=30,
        options={
            "verify_signature": True,
            "verify_exp": True,
            "verify_nbf": True,
            "verify_iat": True,
            "verify_aud": True,
            "verify_iss": True,
        },
    )
    print("Decoded successfully:", decoded)
except Exception as e:
    print(f"Decode error: {e}")
    import traceback

    traceback.print_exc()
