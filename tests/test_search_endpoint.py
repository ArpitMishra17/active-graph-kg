#!/usr/bin/env python3
"""Test /search endpoint directly to debug retrieval issues."""

import json
import os
from datetime import datetime, timedelta, timezone

import jwt
import requests


# Generate JWT token matching the eval script structure
def generate_jwt():
    payload = {
        "sub": "eval_user",
        "tenant_id": "eval_tenant",
        "actor_type": "user",
        "scopes": ["search:read"],
        "aud": os.getenv("JWT_AUDIENCE", "activekg"),
        "iss": os.getenv("JWT_ISSUER", "https://staging-auth.yourcompany.com"),
        "iat": datetime.now(timezone.utc),
        "nbf": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }

    secret = os.getenv("JWT_SECRET_KEY", "dev-secret-key-min-32-chars-long-for-testing")
    return jwt.encode(payload, secret, algorithm="HS256")


def test_search(query, use_hybrid=True, top_k=5, label=""):
    """Test search endpoint with a query."""
    token = generate_jwt()
    url = "http://localhost:8000/search"

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    data = {"query": query, "use_hybrid": use_hybrid, "top_k": top_k}

    print(f"\n{'=' * 80}")
    print(f"{label} - Testing query: {query}")
    print(f"use_hybrid={use_hybrid}, top_k={top_k}")
    print(f"{'=' * 80}\n")

    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            results = response.json()
            print(f"\nResults count: {len(results.get('results', []))}")

            for i, result in enumerate(results.get("results", [])[:3], 1):
                print(f"\n--- Result {i} ---")
                print(f"Node ID: {result.get('node_id')}")
                print(f"Score: {result.get('score', 'N/A')}")
                print(f"Class: {result.get('class', 'N/A')}")
                print(f"Text preview: {result.get('text', '')[:200]}...")
                if "props" in result:
                    print(f"Props: {json.dumps(result['props'], indent=2)[:200]}...")
        else:
            print("\nError response:")
            print(response.text)

    except Exception as e:
        print(f"Error: {e}")


# Test with a simple query first
simple_query = "Java Spring Boot"

print("\n\n" + "=" * 80)
print("TESTING VECTOR-ONLY SEARCH")
print("=" * 80)
test_search(simple_query, use_hybrid=False, top_k=5, label="VECTOR-ONLY")

print("\n\n" + "=" * 80)
print("TESTING HYBRID SEARCH")
print("=" * 80)
test_search(simple_query, use_hybrid=True, top_k=5, label="HYBRID")
