#!/usr/bin/env python3
"""
Debug repository search + RLS context.

Usage:
  ACTIVEKG_DSN=postgresql://... TENANT=eval_tenant \
  python scripts/debug_repo_search.py --query "java spring" --hybrid 0
"""

import argparse
import os

from activekg.engine.embedding_provider import EmbeddingProvider
from activekg.graph.repository import GraphRepository


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--hybrid", type=int, default=0, help="1=hybrid, 0=vector")
    ap.add_argument("--topk", type=int, default=10)
    args = ap.parse_args()

    dsn = os.getenv("ACTIVEKG_DSN")
    if not dsn:
        raise SystemExit("ACTIVEKG_DSN not set")

    tenant = os.getenv("TENANT")
    print(f"DSN set, tenant={tenant}")

    repo = GraphRepository(dsn)
    embedder = EmbeddingProvider()

    # Verify tenant context via a direct call
    with repo._conn(tenant_id=tenant) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_setting('app.current_tenant_id', true)")
            print("current_setting(app.current_tenant_id)=", cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM nodes")
            print("visible nodes:", cur.fetchone()[0])

    qv = embedder.encode([args.query])[0]
    if args.hybrid:
        res = repo.hybrid_search(args.query, qv, top_k=args.topk, tenant_id=tenant)
    else:
        res = repo.vector_search(qv, top_k=args.topk, tenant_id=tenant)

    print(f"results={len(res)}")
    for i, (node, score) in enumerate(res[:10]):
        print(
            f"{i + 1}. {node.id} sim={score:.4f} title={node.props.get('title') if isinstance(node.props, dict) else None}"
        )


if __name__ == "__main__":
    main()
