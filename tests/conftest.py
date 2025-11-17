"""
Pytest fixtures for ActiveKG tests.
"""

import os
from datetime import datetime

import pytest

from activekg.engine.embedding_provider import EmbeddingProvider
from activekg.graph.models import Node
from activekg.graph.repository import GraphRepository
from activekg.triggers.pattern_store import PatternStore
from activekg.triggers.trigger_engine import TriggerEngine


@pytest.fixture(scope="session")
def dsn():
    """Database DSN."""
    return os.getenv(
        "ACTIVEKG_DSN", "postgresql://activekg:activekg@localhost:5432/activekg"
    )


@pytest.fixture(scope="session")
def repo(dsn):
    """Graph repository instance."""
    return GraphRepository(dsn)


@pytest.fixture(scope="session")
def embedder():
    """Embedding provider instance."""
    return EmbeddingProvider()


@pytest.fixture(scope="session")
def pattern_store(dsn):
    """Pattern store instance."""
    return PatternStore(dsn)


@pytest.fixture(scope="session")
def trigger_engine(pattern_store, repo):
    """Trigger engine instance."""
    return TriggerEngine(pattern_store, repo)


@pytest.fixture(scope="function")
def node_id(repo, embedder):
    """Create a test node and return its ID."""
    node = Node(
        classes=["TestDoc"],
        props={"text": "Machine learning fundamentals", "category": "AI"},
        refresh_policy={"interval": "5m", "drift_threshold": 0.15},
        triggers=[{"name": "test_pattern", "threshold": 0.8}],
        last_refreshed=datetime.utcnow(),
        drift_score=0.05,
    )
    node.embedding = embedder.encode([node.props["text"]])[0]
    return repo.create_node(node)
