from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np


@dataclass
class Node:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str | None = None
    classes: list[str] = field(default_factory=list)
    props: dict[str, Any] = field(default_factory=dict)
    payload_ref: str | None = None
    embedding: np.ndarray | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    refresh_policy: dict[str, Any] = field(default_factory=dict)
    triggers: list[dict[str, Any]] = field(default_factory=list)
    version: int = 1
    # Active refresh tracking (explicit columns for query performance)
    last_refreshed: datetime | None = None
    drift_score: float | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Edge:
    src: str
    rel: str
    dst: str
    props: dict[str, Any] = field(default_factory=dict)
    tenant_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
