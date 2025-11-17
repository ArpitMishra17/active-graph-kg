#!/usr/bin/env python3
"""Batch-refresh nodes of a given class via /admin/refresh.

Usage:
  set -a; source .env.eval; set +a
  python3 scripts/admin_refresh_by_class.py --class Job --tenant-id default --batch-size 100

Behavior:
  - Reads ACTIVEKG_DSN to query Postgres for node IDs where <class> = ANY(classes)
  - Applies tenant context using RLS (SET LOCAL app.current_tenant_id)
  - Calls /admin/refresh in batches with an admin token (HS256 by default)

Env vars:
  - ACTIVEKG_DSN (required)
  - API_URL (default: http://localhost:8000)
  - JWT_ENABLED (true/false)
  - JWT_SECRET_KEY, JWT_ALGORITHM, JWT_AUDIENCE, JWT_ISSUER (for HS256 dev auth)
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import psycopg
import requests

try:
    import jwt
except Exception:
    jwt = None


def make_admin_token(tenant_id: str) -> str:
    jwt_enabled = os.getenv("JWT_ENABLED", "true").lower() == "true"
    if not jwt_enabled:
        return ""
    if jwt is None:
        print("⚠️  PyJWT not installed; proceeding without token (JWT_ENABLED may be false)")
        return ""
    secret = os.getenv("JWT_SECRET_KEY", "dev-secret-key-min-32-chars-long-for-testing")
    algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    audience = os.getenv("JWT_AUDIENCE", "activekg")
    issuer = os.getenv("JWT_ISSUER", "https://staging-auth.yourcompany.com")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "admin_batch_refresh",
        "tenant_id": tenant_id,
        "actor_type": "system",
        "scopes": ["admin:refresh", "search:read"],
        "aud": audience,
        "iss": issuer,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(hours=1),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def fetch_node_ids(dsn: str, node_class: str, tenant_id: str, limit: int | None) -> list[str]:
    ids: list[str] = []
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            # Apply tenant context for RLS (SET LOCAL cannot be parameterized; use set_config)
            cur.execute("SELECT set_config('app.current_tenant_id', %s, true)", (tenant_id,))
            sql = "SELECT id FROM nodes WHERE %s = ANY(classes) ORDER BY created_at DESC"
            if limit and limit > 0:
                sql += " LIMIT %s"
                cur.execute(sql, (node_class, limit))
            else:
                cur.execute(sql, (node_class,))
            for row in cur.fetchall():
                ids.append(str(row[0]))
    return ids


def post_refresh(api_url: str, token: str, batch: list[str]) -> bool:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.post(
        f"{api_url}/admin/refresh", json={"node_ids": batch}, headers=headers, timeout=60
    )
    if r.status_code != 200:
        print(f"  ❌ Refresh failed for batch of {len(batch)}: HTTP {r.status_code} - {r.text}")
        return False
    data = r.json()
    print(f"  ✓ Refreshed {data.get('refreshed', 0)} nodes (mode={data.get('mode')})")
    return True


def main():
    parser = argparse.ArgumentParser(description="Batch-refresh nodes by class via API")
    parser.add_argument(
        "--class", dest="node_class", default="Job", help="Class name to refresh (default: Job)"
    )
    parser.add_argument(
        "--tenant-id", default=os.getenv("TENANT", "default"), help="Tenant ID for RLS context"
    )
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for /admin/refresh")
    parser.add_argument(
        "--limit", type=int, default=0, help="Limit number of nodes to refresh (0 = all)"
    )
    parser.add_argument("--dry-run", action="store_true", help="List node IDs without refreshing")
    args = parser.parse_args()

    dsn = os.getenv("ACTIVEKG_DSN")
    if not dsn:
        print("❌ ACTIVEKG_DSN not set; export your database DSN and retry")
        sys.exit(1)

    api_url = os.getenv("API_URL", "http://localhost:8000")
    print("=== Batch Refresh by Class ===")
    print(f"Class:       {args.node_class}")
    print(f"Tenant:      {args.tenant_id}")
    print(f"API URL:     {api_url}")
    print(f"DSN:         {dsn}")

    # Collect IDs
    ids = fetch_node_ids(
        dsn, args.node_class, args.tenant_id, args.limit if args.limit and args.limit > 0 else None
    )
    if not ids:
        print("No nodes found for the given class and tenant.")
        return

    print(f"Found {len(ids)} nodes of class '{args.node_class}'.")
    if args.dry_run:
        for i in ids[:10]:
            print(f"  - {i}")
        if len(ids) > 10:
            print(f"  ... (+{len(ids) - 10} more)")
        return

    token = make_admin_token(args.tenant_id)

    # Refresh in batches
    total = 0
    for i in range(0, len(ids), args.batch_size):
        batch = ids[i : i + args.batch_size]
        ok = post_refresh(api_url, token, batch)
        if not ok:
            # continue with next batch
            pass
        total += len(batch)

    print(f"Done. Requested refresh for {total} nodes.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
