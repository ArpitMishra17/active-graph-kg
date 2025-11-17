"""
Connector framework for ingesting external content into Active Graph KG.

Supports S3, GCS, Azure Blob, Google Drive, Notion, and ATS systems.
"""

from .base import BaseConnector, ChangeItem, ConnectorStats, FetchResult
from .chunker import chunk_text, create_chunk_nodes
from .providers.s3 import S3Connector
from .retry import PermanentError, TransientError, clear_dlq, inspect_dlq, with_retry_and_dlq
from .schemas import (
    AzureBlobConnectorConfig,
    ConnectorQuota,
    DriveConnectorConfig,
    GCSConnectorConfig,
    S3ConnectorConfig,
)
from .throttle import IngestionThrottle

__all__ = [
    "BaseConnector",
    "ConnectorStats",
    "FetchResult",
    "ChangeItem",
    "chunk_text",
    "create_chunk_nodes",
    "S3ConnectorConfig",
    "GCSConnectorConfig",
    "AzureBlobConnectorConfig",
    "DriveConnectorConfig",
    "ConnectorQuota",
    "IngestionThrottle",
    "with_retry_and_dlq",
    "TransientError",
    "PermanentError",
    "inspect_dlq",
    "clear_dlq",
    "S3Connector",
]
