from __future__ import annotations

from typing import Any, Literal, TypedDict

ConnectorProvider = Literal["s3", "gcs", "drive", "http", "local"]


class ConnectorConfigTD(TypedDict, total=False):
    id: str
    tenant_id: str
    provider: ConnectorProvider
    config: dict[str, Any]
    key_version: int | None
    created_at: str | None
    updated_at: str | None


class ConnectorCursorTD(TypedDict, total=False):
    id: str
    tenant_id: str
    provider: ConnectorProvider
    cursor: dict[str, Any]
    updated_at: str | None


class RotationBatchResultTD(TypedDict, total=False):
    rotated: int
    skipped: int
    errors: int
    dry_run: bool
    candidates: int | None
    error: str | None
