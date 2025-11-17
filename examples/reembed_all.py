#!/usr/bin/env python3
"""
Re-embed all nodes to apply L2 normalization retroactively.

This script is needed when the embedding normalization logic changes.
It will:
1. Fetch all nodes with embeddings
2. Re-compute embeddings using current embedding_provider (with L2 norm)
3. Update the database with normalized embeddings
4. Recompute drift scores and log to embedding_history table
"""

import os
import sys

import numpy as np
import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from activekg.common.logger import get_enhanced_logger
from activekg.engine.embedding_provider import EmbeddingProvider

logger = get_enhanced_logger(__name__)


def reembed_all_nodes(
    dsn: str,
    backend: str = "sentence-transformers",
    model_name: str | None = None,
    batch_size: int = 32,
    dry_run: bool = False,
) -> int:
    """Re-embed all nodes in the database.

    Args:
        dsn: PostgreSQL connection string
        backend: Embedding backend ('sentence-transformers' or 'ollama')
        model_name: Model name (defaults to all-MiniLM-L6-v2 for sentence-transformers)
        batch_size: Number of nodes to process at once
        dry_run: If True, don't update database

    Returns:
        Number of nodes re-embedded
    """
    logger.info(
        f"Starting re-embed process (backend={backend}, model={model_name}, dry_run={dry_run})"
    )

    # Initialize embedding provider
    embedder = EmbeddingProvider(backend=backend, model_name=model_name)

    # Connect to database
    conn = psycopg.connect(dsn, autocommit=False, row_factory=dict_row)
    register_vector(conn)
    cur = conn.cursor()

    try:
        # Fetch all nodes with text content
        cur.execute("""
            SELECT id, props->>'text' as text, embedding
            FROM nodes
            WHERE props->>'text' IS NOT NULL
            ORDER BY created_at
        """)
        nodes = cur.fetchall()

        if not nodes:
            logger.warning("No nodes found with text content")
            return 0

        logger.info(f"Found {len(nodes)} nodes to re-embed")

        # Process in batches
        updated_count = 0
        for i in range(0, len(nodes), batch_size):
            batch = nodes[i : i + batch_size]
            node_ids = [n["id"] for n in batch]
            texts = [n["text"] for n in batch]
            old_embeddings = [n["embedding"] for n in batch]

            logger.info(
                f"Processing batch {i // batch_size + 1}/{(len(nodes) - 1) // batch_size + 1} ({len(batch)} nodes)"
            )

            # Generate new normalized embeddings
            new_embeddings = embedder.encode(texts)

            # Update each node
            for node_id, old_emb, new_emb in zip(
                node_ids, old_embeddings, new_embeddings, strict=False
            ):
                # Calculate drift if old embedding exists
                drift_score = None
                if old_emb is not None:
                    # Handle both JSON string and list representations
                    if isinstance(old_emb, str):
                        import json

                        old_emb = json.loads(old_emb)
                    old_vec = np.array(old_emb, dtype=np.float32)
                    # Normalize old vector for fair comparison
                    old_norm = np.linalg.norm(old_vec)
                    if old_norm > 0:
                        old_vec = old_vec / old_norm

                    # Cosine similarity between old (normalized) and new (already normalized)
                    similarity = float(np.dot(old_vec, new_emb))
                    drift_score = 1.0 - similarity

                if not dry_run:
                    # Update embedding
                    cur.execute(
                        """
                        UPDATE nodes
                        SET embedding = %s,
                            drift_score = %s,
                            updated_at = NOW()
                        WHERE id = %s
                    """,
                        (new_emb.tolist(), drift_score or 0.0, node_id),
                    )

                    # Log to embedding_history table if drift is significant
                    if drift_score is not None and drift_score > 0.01:
                        cur.execute(
                            """
                            INSERT INTO embedding_history (node_id, drift_score, embedding_ref)
                            VALUES (%s, %s, %s)
                        """,
                            (node_id, drift_score, "reembed_normalization"),
                        )

                updated_count += 1

                # Log drift for monitoring
                if drift_score is not None:
                    if drift_score > 0.1:
                        logger.warning(
                            f"Node {node_id[:8]}... has significant drift: {drift_score:.4f}"
                        )
                    elif drift_score > 0.01:
                        logger.info(f"Node {node_id[:8]}... drift: {drift_score:.4f}")

            if not dry_run:
                conn.commit()
                logger.info(f"Committed batch {i // batch_size + 1}")

        logger.info(f"Re-embed complete: {updated_count} nodes updated")
        return updated_count

    except Exception as e:
        conn.rollback()
        logger.error(f"Re-embed failed: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Re-embed all nodes with current embedding model")
    parser.add_argument(
        "--dsn",
        default=os.getenv(
            "ACTIVEKG_DSN", "postgresql:///activekg?host=/var/run/postgresql&port=5433"
        ),
        help="PostgreSQL DSN",
    )
    parser.add_argument(
        "--backend",
        default="sentence-transformers",
        choices=["sentence-transformers", "ollama"],
        help="Embedding backend",
    )
    parser.add_argument("--model", help="Model name (defaults based on backend)")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size for processing")
    parser.add_argument(
        "--dry-run", action="store_true", help="Don't update database, just show what would be done"
    )

    args = parser.parse_args()

    count = reembed_all_nodes(
        dsn=args.dsn,
        backend=args.backend,
        model_name=args.model,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Re-embedded {count} nodes")
    if args.dry_run:
        print("Run without --dry-run to apply changes to database")
