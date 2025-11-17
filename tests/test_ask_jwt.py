#!/usr/bin/env python3
"""Test JWT request to /ask endpoint."""

from datetime import UTC, datetime, timedelta

import jwt
import requests

# Generate token with search:read scope
payload = {
    "sub": "eval_user",
    "tenant_id": "eval_tenant",
    "actor_type": "user",
    "scopes": ["search:read"],
    "aud": "activekg",
    "iss": "https://staging-auth.yourcompany.com",
    "iat": datetime.now(UTC),
    "nbf": datetime.now(UTC),
    "exp": datetime.now(UTC) + timedelta(hours=1),
}
secret = "dev-secret-key-min-32-chars-long-for-testing"
token = jwt.encode(payload, secret, algorithm="HS256")

print(f"Token: {token}")
print()

# Try making a request to /ask
headers = {"Authorization": f"Bearer {token}"}
test_payload = {"question": "What are the main performance issues reported?"}

try:
    r = requests.post("http://localhost:8000/ask", json=test_payload, headers=headers)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:500]}")  # First 500 chars
except Exception as e:
    print(f"Error: {e}")
