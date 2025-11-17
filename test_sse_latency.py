#!/usr/bin/env python3
"""Test SSE streaming latency for /ask/stream endpoint."""
import time
import requests
import sys

# Generate test JWT
import jwt
from datetime import datetime, timedelta, timezone

SECRET_KEY = "test-secret-key-min-32-chars-long-for-testing-purposes"
ALGORITHM = "HS256"
AUDIENCE = "activekg"
ISSUER = "https://test-auth.activekg.local"

def generate_token():
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "test-user",
        "tenant_id": "test_tenant",
        "scopes": ["read", "write"],
        "email": "test@example.com",
        "name": "Test User",
        "iat": now,
        "exp": now + timedelta(hours=1),
        "aud": AUDIENCE,
        "iss": ISSUER,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def test_sse_latency():
    token = generate_token()
    url = "http://localhost:8000/ask/stream"

    payload = {
        "question": "Test",
        "stream": True
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    print("🔍 Testing SSE streaming latency...")
    print(f"URL: {url}")
    print(f"Question: {payload['question']}")

    start_time = time.time()
    first_chunk_time = None
    chunk_count = 0

    try:
        with requests.post(url, json=payload, headers=headers, stream=True, timeout=10) as response:
            response.raise_for_status()

            for line in response.iter_lines():
                if not line:
                    continue

                chunk_count += 1

                if first_chunk_time is None:
                    first_chunk_time = time.time()
                    latency_ms = (first_chunk_time - start_time) * 1000
                    print(f"\n✅ First chunk received: {latency_ms:.1f}ms")

                    if latency_ms < 300:
                        print(f"   ✅ PASS: Latency < 300ms")
                    else:
                        print(f"   ⚠️  WARNING: Latency >= 300ms (expected < 300ms)")

                    # Decode first chunk to show content
                    try:
                        decoded = line.decode('utf-8')
                        if decoded.startswith('data: '):
                            print(f"   Content: {decoded[6:50]}...")
                    except:
                        pass

                # Stop after getting a few chunks
                if chunk_count >= 5:
                    break

        total_time = time.time() - start_time
        print(f"\n📊 Stats:")
        print(f"   Total chunks received: {chunk_count}")
        print(f"   Total time: {total_time * 1000:.1f}ms")
        print(f"   First chunk latency: {(first_chunk_time - start_time) * 1000:.1f}ms")

        return (first_chunk_time - start_time) * 1000 < 300

    except requests.exceptions.RequestException as e:
        print(f"\n❌ ERROR: {e}")
        return False

if __name__ == "__main__":
    success = test_sse_latency()
    sys.exit(0 if success else 1)
