"""Base connector interface for all external data sources."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any
import hashlib


@dataclass
class ConnectorStats:
    """Metadata about a resource from the external source."""
    exists: bool
    etag: Optional[str] = None
    generation: Optional[str] = None  # For GCS
    modified_at: Optional[datetime] = None
    size: Optional[int] = None
    mime_type: Optional[str] = None
    owner: Optional[str] = None


@dataclass
class FetchResult:
    """Result of fetching text content from a resource."""
    text: str
    title: Optional[str] = None
    metadata: Dict[str, Any] = None


@dataclass
class ChangeItem:
    """A single change event from list_changes()."""
    uri: str
    operation: str  # "created", "updated", "deleted"
    etag: Optional[str] = None
    modified_at: Optional[datetime] = None


class BaseConnector(ABC):
    """Base class for all connectors.
    
    Connectors implement three core methods:
    - stat(uri): Get metadata about a resource
    - fetch_text(uri): Fetch and parse text content
    - list_changes(cursor): List changes since cursor
    """
    
    def __init__(self, tenant_id: str, config: Dict[str, Any]):
        self.tenant_id = tenant_id
        self.config = config
        self.provider_name = self.__class__.__name__.replace("Connector", "").lower()
    
    @abstractmethod
    def stat(self, uri: str) -> ConnectorStats:
        """Get metadata about a resource without downloading content.
        
        Args:
            uri: Resource URI (e.g., s3://bucket/key, drive:file/xyz)
        
        Returns:
            ConnectorStats with etag, modified_at, size, etc.
        """
        pass
    
    @abstractmethod
    def fetch_text(self, uri: str) -> FetchResult:
        """Fetch and parse text content from a resource.
        
        Args:
            uri: Resource URI
        
        Returns:
            FetchResult with text, title, metadata
        """
        pass
    
    @abstractmethod
    def list_changes(self, cursor: Optional[str] = None) -> tuple[List[ChangeItem], Optional[str]]:
        """List changes since cursor (incremental sync).
        
        Args:
            cursor: Last sync cursor (None for initial backfill)
        
        Returns:
            Tuple of (changes, next_cursor)
        """
        pass
    
    def to_external_id(self, uri: str) -> str:
        """Convert URI to external_id format.
        
        Format: {provider}:{tenant}:{resource_id}
        """
        # Extract resource_id from URI
        resource_id = uri.split("://", 1)[-1] if "://" in uri else uri.split(":", 1)[-1]
        return f"{self.provider_name}:{self.tenant_id}:{resource_id}"
    
    def compute_content_hash(self, text: str) -> str:
        """Compute SHA256 hash of content for dedup."""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
    
    def needs_refresh(self, stats: ConnectorStats, existing_node: Optional[Dict[str, Any]]) -> bool:
        """Check if resource needs re-embedding.
        
        Fast path: Compare ETag
        Slow path: Compare content hash (if ETag missing/unreliable)
        """
        if not existing_node:
            return True  # New resource
        
        existing_props = existing_node.get("props", {})
        
        # Fast path: ETag comparison
        if stats.etag and existing_props.get("etag"):
            if stats.etag == existing_props.get("etag"):
                return False  # No change
        
        # ETag changed or missing - will need content hash check
        # (caller should fetch text and compare hashes)
        return True
