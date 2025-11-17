"""Pydantic schemas for connector configuration validation."""

from pydantic import BaseModel, Field


class S3ConnectorConfig(BaseModel):
    """Configuration for S3 connector."""

    bucket: str
    prefix: str = ""
    region: str = "us-east-1"
    access_key_id: str = Field(..., min_length=16)
    secret_access_key: str = Field(..., min_length=32)
    poll_interval_seconds: int = Field(default=900, ge=60, le=3600)
    enabled: bool = True


class GCSConnectorConfig(BaseModel):
    """Configuration for Google Cloud Storage connector."""

    bucket: str
    prefix: str = ""
    service_account_json_path: str
    poll_interval_seconds: int = Field(default=900, ge=60, le=3600)
    enabled: bool = True


class AzureBlobConnectorConfig(BaseModel):
    """Configuration for Azure Blob Storage connector."""

    container: str
    prefix: str = ""
    connection_string: str = Field(..., min_length=32)
    poll_interval_seconds: int = Field(default=900, ge=60, le=3600)
    enabled: bool = True


class DriveConnectorConfig(BaseModel):
    """Configuration for Google Drive connector."""

    folder_id: str = Field(..., description="Google Drive folder ID to watch")
    service_account_json_path: str = Field(
        ..., description="Path to service account JSON credentials"
    )
    poll_interval_seconds: int = Field(default=900, ge=60, le=3600)
    enabled: bool = True


class ConnectorQuota(BaseModel):
    """Per-tenant quota limits."""

    max_docs_per_day: int = Field(default=10000, ge=1)
    max_storage_bytes: int = Field(default=10 * 1024 * 1024 * 1024, ge=1024)  # 10GB
    max_api_calls_per_hour: int = Field(default=5000, ge=1)
