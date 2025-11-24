"""Google Cloud Storage connector implementation."""

import io
import json
import os
from typing import Any

import pdfplumber
from bs4 import BeautifulSoup
from docx import Document as DocxDocument
from google.api_core import exceptions as gcp_exceptions
from google.cloud import storage

from activekg.common.logger import get_enhanced_logger
from activekg.connectors.base import BaseConnector, ChangeItem, ConnectorStats, FetchResult

logger = get_enhanced_logger(__name__)


def _parse_gcs_uri(uri: str) -> tuple[str, str]:
    """Parse gs://bucket/object into (bucket, object_name)."""
    if not uri.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI: {uri}")
    parts = uri[5:].split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"GCS URI must be gs://bucket/object: {uri}")
    return parts[0], parts[1]


class GCSConnector(BaseConnector):
    """Google Cloud Storage implementation of BaseConnector.

    Config keys (validated by GCSConnectorConfig):
      - bucket: GCS bucket name
      - prefix: Optional prefix to filter objects (default: "")
      - project: GCP project ID (optional, can use GOOGLE_CLOUD_PROJECT env)
      - credentials_path: Path to service account JSON (optional, uses GOOGLE_APPLICATION_CREDENTIALS env)

    Authentication:
      - Explicitly via credentials_path config
      - Or GOOGLE_APPLICATION_CREDENTIALS environment variable
      - Or gcloud default credentials
    """

    def __init__(self, tenant_id: str, config: dict[str, Any]):
        super().__init__(tenant_id, config)

        # Get credentials path from config or environment
        credentials_path = config.get("credentials_path") or os.getenv(
            "GOOGLE_APPLICATION_CREDENTIALS"
        )
        project = config.get("project") or os.getenv("GOOGLE_CLOUD_PROJECT")

        # Initialize GCS client
        if credentials_path:
            self.client = storage.Client.from_service_account_json(
                credentials_path, project=project
            )
        else:
            # Use default credentials (gcloud, workload identity, etc.)
            self.client = storage.Client(project=project)

        logger.info(
            "GCS connector initialized",
            extra_fields={
                "tenant_id": tenant_id,
                "bucket": config.get("bucket"),
                "prefix": config.get("prefix", ""),
                "project": project or "default",
            },
        )

    def stat(self, uri: str) -> ConnectorStats:
        """Get metadata about a GCS object without downloading it.

        Args:
            uri: GCS URI in format gs://bucket/object

        Returns:
            ConnectorStats with metadata (uses 'generation' field for GCS versioning)
        """
        bucket_name, object_name = _parse_gcs_uri(uri)

        try:
            bucket = self.client.bucket(bucket_name)
            blob = bucket.get_blob(object_name)

            if blob is None:
                return ConnectorStats(exists=False)

            # GCS uses etag and generation for versioning
            # generation is a unique version identifier
            etag = blob.etag
            generation = str(blob.generation) if blob.generation else None
            size = blob.size
            mime_type = blob.content_type
            updated = blob.updated  # datetime object
            owner = blob.owner.get("entity") if blob.owner else None

            return ConnectorStats(
                exists=True,
                etag=etag,
                generation=generation,  # GCS-specific versioning
                modified_at=updated,
                size=size,
                mime_type=mime_type,
                owner=owner,
            )
        except gcp_exceptions.NotFound:
            return ConnectorStats(exists=False)
        except Exception as e:
            logger.error(
                f"GCS stat failed for {uri}: {e}", extra_fields={"tenant_id": self.tenant_id, "uri": uri}
            )
            raise

    def fetch_text(self, uri: str) -> FetchResult:
        """Download and extract text from a GCS object.

        Args:
            uri: GCS URI in format gs://bucket/object

        Returns:
            FetchResult with extracted text and metadata
        """
        bucket_name, object_name = _parse_gcs_uri(uri)

        try:
            bucket = self.client.bucket(bucket_name)
            blob = bucket.blob(object_name)

            # Download as bytes
            data = blob.download_as_bytes()
            content_type = blob.content_type or ""

            # Extract text based on content type
            text = self._extract_text(data, content_type)

            # Use object name as title (last component of path)
            title = object_name.split("/")[-1] if object_name else None

            metadata = {
                "bucket": bucket_name,
                "object": object_name,
                "content_type": content_type,
                "size": len(data),
                "generation": str(blob.generation) if blob.generation else None,
            }

            logger.info(
                "GCS fetch successful",
                extra_fields={
                    "tenant_id": self.tenant_id,
                    "uri": uri,
                    "text_length": len(text),
                    "content_type": content_type,
                },
            )

            return FetchResult(text=text, title=title, metadata=metadata)

        except gcp_exceptions.NotFound as e:
            logger.error(
                f"GCS object not found: {uri}", extra_fields={"tenant_id": self.tenant_id, "uri": uri}
            )
            raise FileNotFoundError(f"GCS object not found: {uri}") from e
        except Exception as e:
            logger.error(
                f"GCS fetch failed for {uri}: {e}", extra_fields={"tenant_id": self.tenant_id, "uri": uri}
            )
            raise

    def list_changes(self, cursor: str | None = None) -> tuple[list[ChangeItem], str | None]:
        """List objects in the configured bucket/prefix for backfill sync.

        This is a backfill operation that lists all objects. For true incremental sync,
        you would need to implement change notifications or poll modified_at timestamps.

        Args:
            cursor: JSON string with {"page_token": "..."} or None

        Returns:
            Tuple of (list of ChangeItems, next_cursor)
            - ChangeItems have operation="upsert" for all objects
            - next_cursor is JSON with page_token or None if done
        """
        bucket_name = self.config["bucket"]
        prefix = self.config.get("prefix", "")
        max_results = 1000  # GCS default page size

        # Parse cursor to get page_token
        page_token = None
        if cursor:
            try:
                data = json.loads(cursor)
                page_token = data.get("page_token")
            except Exception as e:
                logger.warning(
                    f"Invalid cursor format: {e}",
                    extra_fields={"tenant_id": self.tenant_id, "cursor": cursor},
                )

        try:
            bucket = self.client.bucket(bucket_name)

            # List blobs with pagination
            iterator = bucket.list_blobs(
                prefix=prefix, max_results=max_results, page_token=page_token
            )

            # Get current page
            page = next(iterator.pages)

            changes: list[ChangeItem] = []
            for blob in page:
                # Skip directory markers (objects ending with /)
                if blob.name.endswith("/"):
                    continue

                uri = f"gs://{bucket_name}/{blob.name}"
                etag = blob.etag
                updated = blob.updated  # datetime

                changes.append(
                    ChangeItem(
                        uri=uri,
                        operation="upsert",  # GCS doesn't distinguish create/update in listing
                        etag=etag,
                        modified_at=updated,
                    )
                )

            # Get next page token if available
            next_cursor = None
            if iterator.next_page_token:
                next_cursor = json.dumps({"page_token": iterator.next_page_token})

            logger.info(
                "GCS list_changes complete",
                extra_fields={
                    "tenant_id": self.tenant_id,
                    "bucket": bucket_name,
                    "prefix": prefix,
                    "changes_count": len(changes),
                    "has_more": next_cursor is not None,
                },
            )

            return changes, next_cursor

        except Exception as e:
            logger.error(
                f"GCS list_changes failed: {e}",
                extra_fields={"tenant_id": self.tenant_id, "bucket": bucket_name, "prefix": prefix},
            )
            raise

    # Text extraction helpers (reused from S3 pattern)

    def _extract_text(self, data: bytes, content_type: str) -> str:
        """Extract text from binary data based on content type."""
        ct = (content_type or "").lower()

        if "pdf" in ct:
            return self._pdf_to_text(data)

        if (
            "word" in ct
            or ct.endswith("/msword")
            or ct.endswith("/vnd.openxmlformats-officedocument.wordprocessingml.document")
        ):
            return self._docx_to_text(data)

        if "html" in ct or "text/html" in ct:
            return self._html_to_text(data)

        # Default: try UTF-8 decoding
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:
            return ""

    def _pdf_to_text(self, data: bytes) -> str:
        """Extract text from PDF bytes using pdfplumber."""
        txt = []
        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                for page in pdf.pages:
                    try:
                        extracted = page.extract_text()
                        if extracted:
                            txt.append(extracted)
                    except Exception:
                        continue
        except Exception as e:
            logger.warning(f"PDF extraction failed: {e}", extra_fields={"tenant_id": self.tenant_id})

        return "\n".join(t for t in txt if t)

    def _docx_to_text(self, data: bytes) -> str:
        """Extract text from DOCX bytes using python-docx."""
        try:
            bio = io.BytesIO(data)
            doc = DocxDocument(bio)
            return "\n".join(p.text for p in doc.paragraphs if p.text)
        except Exception as e:
            logger.warning(f"DOCX extraction failed: {e}", extra_fields={"tenant_id": self.tenant_id})
            return ""

    def _html_to_text(self, data: bytes) -> str:
        """Extract text from HTML bytes using BeautifulSoup."""
        try:
            soup = BeautifulSoup(data, "html.parser")

            # Remove script and style tags
            for tag in soup(["script", "style"]):
                tag.decompose()

            # Get text and normalize whitespace
            text = soup.get_text(" ")
            return " ".join(text.split())
        except Exception as e:
            logger.warning(f"HTML extraction failed: {e}", extra_fields={"tenant_id": self.tenant_id})
            return ""
