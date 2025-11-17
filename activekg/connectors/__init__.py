"""
Connector framework for ingesting external content into Active Graph KG.

Supports S3, GCS, Azure Blob, Google Drive, Notion, and ATS systems.
"""
from .base import BaseConnector, ConnectorStats, FetchResult, ChangeItem
from .chunker import chunk_text, create_chunk_nodes
from .schemas import S3ConnectorConfig, GCSConnectorConfig, AzureBlobConnectorConfig, ConnectorQuota
from .throttle import IngestionThrottle
from .retry import with_retry_and_dlq, TransientError, PermanentError, inspect_dlq, clear_dlq
from .providers.s3 import S3Connector

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
    "ConnectorQuota",
    "IngestionThrottle",
    "with_retry_and_dlq",
    "TransientError",
    "PermanentError",
    "inspect_dlq",
    "clear_dlq",
    "S3Connector",
]
