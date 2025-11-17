#!/usr/bin/env python3
"""Test JWT request to server."""

from datetime import UTC, datetime, timedelta

import jwt
import requests

# Generate token
payload = {
    "sub": "eval_seeder",
    "tenant_id": "eval_tenant",
    "actor_type": "user",
    "scopes": ["nodes:write", "admin:refresh"],
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

# Try making a request
headers = {"Authorization": f"Bearer {token}"}
test_payload = {"text": "Test node", "classes": ["Test"], "props": {}, "metadata": {}}

try:
    r = requests.post("http://localhost:8000/nodes", json=test_payload, headers=headers)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text}")
except Exception as e:
    print(f"Error: {e}")
