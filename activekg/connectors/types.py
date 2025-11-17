from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict


ConnectorProvider = Literal["s3", "gcs", "drive", "http", "local"]


class ConnectorConfigTD(TypedDict, total=False):
    id: str
    tenant_id: str
    provider: ConnectorProvider
    config: dict[str, Any]
    key_version: Optional[int]
    created_at: Optional[str]
    updated_at: Optional[str]


class ConnectorCursorTD(TypedDict, total=False):
    id: str
    tenant_id: str
    provider: ConnectorProvider
    cursor: dict[str, Any]
    updated_at: Optional[str]


class RotationBatchResultTD(TypedDict, total=False):
    rotated: int
    skipped: int
    errors: int
    dry_run: bool
    candidates: Optional[int]
    error: Optional[str]
