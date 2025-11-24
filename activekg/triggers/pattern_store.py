from __future__ import annotations

from typing import Any

import numpy as np
import psycopg
from pgvector.psycopg import register_vector

from activekg.common.logger import get_enhanced_logger


class PatternStore:
    """Database-backed store for named embedding patterns.

    Patterns are stored in the 'patterns' table with vector embeddings.
    """

    def __init__(self, dsn: str):
        self.dsn = dsn
        self.logger = get_enhanced_logger(__name__)

    def _conn(self):
        conn = psycopg.connect(self.dsn)
        register_vector(conn)  # Register pgvector types
        return conn

    def set(self, name: str, vector: np.ndarray, description: str | None = None) -> None:
        """Store or update a pattern."""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO patterns (name, embedding, description, updated_at)
                    VALUES (%s, %s, %s, now())
                    ON CONFLICT (name)
                    DO UPDATE SET embedding = EXCLUDED.embedding,
                                  description = EXCLUDED.description,
                                  updated_at = now()
                    """,
                    (name, vector.tolist(), description),
                )
        self.logger.info("Pattern saved", extra_fields={"name": name})

    def get(self, name: str) -> np.ndarray | None:
        """Retrieve a pattern by name."""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT embedding FROM patterns WHERE name = %s", (name,))
                row = cur.fetchone()
                if row:
                    return np.array(row[0], dtype=np.float32)
                return None

    def list_patterns(self) -> list[dict[str, Any]]:
        """List all patterns with metadata."""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT name, description, created_at, updated_at FROM patterns ORDER BY name"
                )
                return [
                    {
                        "name": row[0],
                        "description": row[1],
                        "created_at": row[2].isoformat() if row[2] else None,
                        "updated_at": row[3].isoformat() if row[3] else None,
                    }
                    for row in cur.fetchall()
                ]

    def delete(self, name: str) -> bool:
        """Delete a pattern by name. Returns True if deleted, False if not found."""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM patterns WHERE name = %s", (name,))
                deleted = cur.rowcount > 0
                if deleted:
                    self.logger.info("Pattern deleted", extra_fields={"name": name})
                return deleted
