"""Google Drive connector implementation with Changes API support."""

import io
import json
from datetime import datetime
from typing import Any

import pdfplumber
from bs4 import BeautifulSoup
from docx import Document as DocxDocument
from google.oauth2 import service_account
from googleapiclient import errors as google_errors
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from activekg.common.logger import get_enhanced_logger
from activekg.connectors.base import BaseConnector, ChangeItem, ConnectorStats, FetchResult

logger = get_enhanced_logger(__name__)


def _parse_drive_uri(uri: str) -> str:
    """Parse drive://{file_id} into file_id."""
    if not uri.startswith("drive://"):
        raise ValueError(f"Invalid Drive URI: {uri}")
    file_id = uri[8:]  # Remove "drive://" prefix
    if not file_id:
        raise ValueError(f"Drive URI must be drive://{{file_id}}: {uri}")
    return file_id


class DriveConnector(BaseConnector):
    """Google Drive implementation of BaseConnector with Changes API support.

    Config keys (validated by DriveConnectorConfig):
      - credentials: Service account JSON (encrypted)
      - subject_email: Optional email for domain-wide delegation
      - project: Optional GCP project ID
      - shared_drives: List of Shared Drive IDs to sync
      - root_folders: List of My Drive folder IDs to sync
      - include_folders: Folder ID allowlist (empty = all)
      - exclude_folders: Folder ID blocklist
      - include_mime_types: MIME type allowlist (empty = all)
      - export_formats: Dict of Google MIME -> export MIME for Workspace docs
      - use_changes_feed: Use Changes API for incremental sync (default: True)
      - page_size: Page size for API requests (default: 100, max: 1000)
      - max_file_size_bytes: Max file size to download (default: 100MB)

    Authentication:
      - Service account via credentials field
      - Optional domain-wide delegation via subject_email

    URI Format:
      - drive://{file_id}

    Changes API:
      - Uses pageToken for resumable incremental sync
      - Cursor format: {"page_token": "...", "start_page_token": "..."}

    Known Limitations (v1):
      1. Shared Drives Scope:
         - Current implementation uses a single global Changes API cursor
         - This covers "My Drive + shared items" but may not capture all Shared Drive changes
         - For complete coverage: enumerate driveIds and maintain cursor per drive
         - Alternative: Add 'scope' column to connector_cursors table (e.g., "drive:{driveId}")

      2. Folder Filtering Ancestry:
         - _should_include_file() only checks direct parents (file_info["parents"])
         - Nested items under root_folders may be missed if parent folder not in ancestry
         - For correctness: Precompute allowed folder ancestry during initial backfill
         - Alternative: Accept best-effort v1 limitation and document in setup guide

      3. ETag Handling:
         - Binary files use md5Checksum as ETag
         - Google Workspace docs use modifiedTime:version fallback when md5Checksum empty
         - Version changes may not always indicate content changes for Workspace docs
    """

    DRIVE_API_VERSION = "v3"
    DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"

    def __init__(self, tenant_id: str, config: dict[str, Any]):
        super().__init__(tenant_id, config)

        # Parse service account credentials from config (already decrypted)
        credentials_json = config.get("credentials")
        if not credentials_json:
            raise ValueError("Drive connector requires 'credentials' field")

        credentials_dict = json.loads(credentials_json)
        subject_email = config.get("subject_email")

        # Create credentials with drive.readonly scope
        creds = service_account.Credentials.from_service_account_info(
            credentials_dict, scopes=[self.DRIVE_SCOPE]
        )

        # Apply domain-wide delegation if subject_email provided
        if subject_email:
            creds = creds.with_subject(subject_email)
            logger.info(
                "Drive connector with domain-wide delegation",
                extra_fields={"tenant_id": tenant_id, "subject_email": subject_email},
            )

        # Initialize Drive API client
        self.service = build("drive", self.DRIVE_API_VERSION, credentials=creds)

        # Store config parameters
        self.shared_drives = config.get("shared_drives", [])
        self.root_folders = config.get("root_folders", [])
        self.include_folders = config.get("include_folders", [])
        self.exclude_folders = config.get("exclude_folders", [])
        self.include_mime_types = config.get("include_mime_types", [])
        self.export_formats = config.get(
            "export_formats",
            {
                "application/vnd.google-apps.document": "text/html",
                "application/vnd.google-apps.spreadsheet": "text/csv",
                "application/vnd.google-apps.presentation": "text/plain",
            },
        )
        self.use_changes_feed = config.get("use_changes_feed", True)
        self.page_size = min(config.get("page_size", 100), 1000)
        self.max_file_size_bytes = config.get("max_file_size_bytes", 100 * 1024 * 1024)

        logger.info(
            "Drive connector initialized",
            extra_fields={
                "tenant_id": tenant_id,
                "shared_drives_count": len(self.shared_drives),
                "root_folders_count": len(self.root_folders),
                "use_changes_feed": self.use_changes_feed,
                "page_size": self.page_size,
            },
        )

    def stat(self, uri: str) -> ConnectorStats:
        """Get metadata about a Drive file without downloading it.

        Args:
            uri: Drive URI in format drive://file_id

        Returns:
            ConnectorStats with metadata
        """
        file_id = _parse_drive_uri(uri)

        try:
            # Request file metadata
            file_metadata = (
                self.service.files()
                .get(
                    fileId=file_id,
                    fields="id,name,mimeType,modifiedTime,version,size,md5Checksum,owners,trashed",
                    supportsAllDrives=True,
                )
                .execute()
            )

            # Check if file is trashed
            if file_metadata.get("trashed", False):
                return ConnectorStats(exists=False)

            # Extract metadata
            mime_type = file_metadata.get("mimeType")
            modified_time_str = file_metadata.get("modifiedTime")
            modified_at = (
                datetime.fromisoformat(modified_time_str.replace("Z", "+00:00"))
                if modified_time_str
                else None
            )
            size = int(file_metadata.get("size", 0)) if "size" in file_metadata else None

            # ETag: Use MD5 for binary files, fallback to modifiedTime:version for Google Workspace docs
            etag = file_metadata.get("md5Checksum")
            if not etag and modified_time_str:
                # Google Workspace docs don't have md5Checksum, use modifiedTime:version as ETag
                version = file_metadata.get("version", "")
                etag = f"{modified_time_str}:{version}"

            owners = file_metadata.get("owners", [])
            owner = owners[0].get("emailAddress") if owners else None

            return ConnectorStats(
                exists=True,
                etag=etag,
                modified_at=modified_at,
                size=size,
                mime_type=mime_type,
                owner=owner,
            )

        except google_errors.HttpError as e:
            if e.resp.status == 404:
                return ConnectorStats(exists=False)
            logger.error(
                f"Drive stat failed for {uri}: {e}",
                extra_fields={"tenant_id": self.tenant_id, "uri": uri},
            )
            raise
        except Exception as e:
            logger.error(
                f"Drive stat failed for {uri}: {e}",
                extra_fields={"tenant_id": self.tenant_id, "uri": uri},
            )
            raise

    def fetch_text(self, uri: str) -> FetchResult:
        """Download and extract text from a Drive file.

        Args:
            uri: Drive URI in format drive://file_id

        Returns:
            FetchResult with extracted text and metadata
        """
        file_id = _parse_drive_uri(uri)

        try:
            # Get file metadata first
            file_metadata = (
                self.service.files()
                .get(
                    fileId=file_id,
                    fields="id,name,mimeType,size,webViewLink",
                    supportsAllDrives=True,
                )
                .execute()
            )

            mime_type = file_metadata.get("mimeType", "")
            file_name = file_metadata.get("name", "")
            file_size = int(file_metadata.get("size", 0)) if "size" in file_metadata else None
            web_view_link = file_metadata.get("webViewLink")

            # Check file size limit
            if file_size and file_size > self.max_file_size_bytes:
                logger.warning(
                    "Drive file exceeds max size limit",
                    extra_fields={
                        "tenant_id": self.tenant_id,
                        "uri": uri,
                        "size": file_size,
                        "limit": self.max_file_size_bytes,
                    },
                )
                raise ValueError(
                    f"File size ({file_size} bytes) exceeds limit ({self.max_file_size_bytes} bytes)"
                )

            # Check if file is a Google Workspace doc that needs export
            if mime_type in self.export_formats:
                export_mime = self.export_formats[mime_type]
                text = self._export_google_doc(file_id, export_mime, mime_type)
            else:
                # Download binary file
                data = self._download_file(file_id)
                text = self._extract_text(data, mime_type)

            metadata = {
                "file_id": file_id,
                "file_name": file_name,
                "mime_type": mime_type,
                "size": file_size,
                "web_view_link": web_view_link,
            }

            logger.info(
                "Drive fetch successful",
                extra_fields={
                    "tenant_id": self.tenant_id,
                    "uri": uri,
                    "text_length": len(text),
                    "mime_type": mime_type,
                },
            )

            return FetchResult(text=text, title=file_name, metadata=metadata)

        except google_errors.HttpError as e:
            if e.resp.status == 404:
                logger.error(
                    f"Drive file not found: {uri}",
                    extra_fields={"tenant_id": self.tenant_id, "uri": uri},
                )
                raise FileNotFoundError(f"Drive file not found: {uri}") from e
            logger.error(
                f"Drive fetch failed for {uri}: {e}",
                extra_fields={"tenant_id": self.tenant_id, "uri": uri},
            )
            raise
        except Exception as e:
            logger.error(
                f"Drive fetch failed for {uri}: {e}",
                extra_fields={"tenant_id": self.tenant_id, "uri": uri},
            )
            raise

    def list_changes(self, cursor: str | None = None) -> tuple[list[ChangeItem], str | None]:
        """List changes using Drive Changes API for incremental sync.

        Args:
            cursor: JSON string with {"page_token": "...", "start_page_token": "..."} or None

        Returns:
            Tuple of (list of ChangeItems, next_cursor)
            - ChangeItems have operation="created", "updated", or "deleted"
            - next_cursor is JSON with page_token or None if done with current batch
        """
        try:
            # Parse cursor
            page_token = None
            start_page_token = None
            if cursor:
                try:
                    data = json.loads(cursor)
                    page_token = data.get("page_token")
                    start_page_token = data.get("start_page_token")
                except Exception as e:
                    logger.warning(
                        f"Invalid cursor format: {e}",
                        extra_fields={"tenant_id": self.tenant_id, "cursor": cursor},
                    )

            # Get start page token if this is the first sync
            if not page_token and not start_page_token:
                response = (
                    self.service.changes().getStartPageToken(supportsAllDrives=True).execute()
                )
                start_page_token = response.get("startPageToken")
                page_token = start_page_token
                logger.info(
                    "Drive Changes API: Initial sync started",
                    extra_fields={
                        "tenant_id": self.tenant_id,
                        "start_page_token": start_page_token,
                    },
                )

            # List changes
            response = (
                self.service.changes()
                .list(
                    pageToken=page_token,
                    pageSize=self.page_size,
                    fields="nextPageToken,newStartPageToken,changes(fileId,removed,file(id,name,mimeType,modifiedTime,trashed,parents))",
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                )
                .execute()
            )

            changes: list[ChangeItem] = []
            for change in response.get("changes", []):
                file_id = change.get("fileId")
                removed = change.get("removed", False)
                file_info = change.get("file", {})

                # Determine if file should be included
                if not self._should_include_file(file_info):
                    continue

                # Determine operation
                if removed or file_info.get("trashed", False):
                    operation = "deleted"
                else:
                    # We don't distinguish create vs update in Changes API
                    operation = "updated"

                uri = f"drive://{file_id}"
                modified_time_str = file_info.get("modifiedTime")
                modified_at = (
                    datetime.fromisoformat(modified_time_str.replace("Z", "+00:00"))
                    if modified_time_str
                    else None
                )

                changes.append(
                    ChangeItem(
                        uri=uri,
                        operation=operation,
                        etag=None,  # MD5 not available in Changes API response
                        modified_at=modified_at,
                    )
                )

            # Determine next cursor
            next_cursor = None
            next_page_token = response.get("nextPageToken")
            new_start_page_token = response.get("newStartPageToken")

            if next_page_token:
                # More changes in current batch
                next_cursor = json.dumps(
                    {
                        "page_token": next_page_token,
                        "start_page_token": start_page_token or new_start_page_token,
                    }
                )
            elif new_start_page_token:
                # Batch complete, save new start token for next sync
                next_cursor = json.dumps(
                    {"page_token": new_start_page_token, "start_page_token": new_start_page_token}
                )

            logger.info(
                "Drive list_changes complete",
                extra_fields={
                    "tenant_id": self.tenant_id,
                    "changes_count": len(changes),
                    "has_more": next_page_token is not None,
                    "new_start_page_token": new_start_page_token,
                },
            )

            return changes, next_cursor

        except Exception as e:
            logger.error(
                f"Drive list_changes failed: {e}", extra_fields={"tenant_id": self.tenant_id}
            )
            raise

    def _should_include_file(self, file_info: dict[str, Any]) -> bool:
        """Check if file should be included based on config filters.

        Args:
            file_info: File metadata dict from Drive API

        Returns:
            True if file should be included
        """
        if not file_info:
            return False

        mime_type = file_info.get("mimeType", "")
        parents = file_info.get("parents", [])

        # Skip folders
        if mime_type == "application/vnd.google-apps.folder":
            return False

        # MIME type filtering
        if self.include_mime_types and mime_type not in self.include_mime_types:
            return False

        # Folder filtering (if configured)
        if self.shared_drives or self.root_folders or self.include_folders or self.exclude_folders:
            # Exclude folders
            if self.exclude_folders and any(parent in self.exclude_folders for parent in parents):
                return False

            # Include folders (allowlist)
            if self.include_folders and not any(
                parent in self.include_folders for parent in parents
            ):
                return False

            # Root folders check (if specified)
            if self.root_folders and not any(parent in self.root_folders for parent in parents):
                return False

            # Shared drives check (if specified)
            # Note: Shared drive membership is not directly in parents, would need additional API call
            # For now, we rely on Changes API with includeItemsFromAllDrives=True

        return True

    def _download_file(self, file_id: str) -> bytes:
        """Download binary file content.

        Args:
            file_id: Drive file ID

        Returns:
            File content as bytes
        """
        request = self.service.files().get_media(fileId=file_id, supportsAllDrives=True)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)

        done = False
        while not done:
            status, done = downloader.next_chunk()

        return buffer.getvalue()

    def _export_google_doc(self, file_id: str, export_mime: str, original_mime: str) -> str:
        """Export Google Workspace document to text.

        Args:
            file_id: Drive file ID
            export_mime: Target MIME type for export
            original_mime: Original Google Workspace MIME type

        Returns:
            Extracted text
        """
        request = self.service.files().export_media(fileId=file_id, mimeType=export_mime)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)

        done = False
        while not done:
            status, done = downloader.next_chunk()

        data = buffer.getvalue()

        # Extract text from exported format
        if export_mime == "text/html":
            return self._extract_html(data)
        elif export_mime == "text/csv":
            return data.decode("utf-8", errors="ignore")
        elif export_mime == "text/plain":
            return data.decode("utf-8", errors="ignore")
        else:
            # Fallback
            return data.decode("utf-8", errors="ignore")

    def _extract_text(self, data: bytes, content_type: str) -> str:
        """Extract text from binary data based on content type.

        Args:
            data: File content as bytes
            content_type: MIME type

        Returns:
            Extracted text
        """
        ct = (content_type or "").lower()

        if "pdf" in ct:
            return self._extract_pdf(data)
        elif "html" in ct or "htm" in ct:
            return self._extract_html(data)
        elif (
            "word" in ct
            or "docx" in ct
            or "vnd.openxmlformats-officedocument.wordprocessingml" in ct
        ):
            return self._extract_docx(data)
        elif "plain" in ct or "text" in ct:
            return data.decode("utf-8", errors="ignore")
        else:
            # Attempt UTF-8 decode as fallback
            try:
                return data.decode("utf-8", errors="ignore")
            except Exception:
                logger.warning(f"Could not extract text from content type: {content_type}")
                return ""

    def _extract_pdf(self, data: bytes) -> str:
        """Extract text from PDF bytes."""
        try:
            buffer = io.BytesIO(data)
            with pdfplumber.open(buffer) as pdf:
                text_parts = []
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
                return "\n\n".join(text_parts)
        except Exception as e:
            logger.warning(f"PDF extraction failed: {e}")
            return ""

    def _extract_html(self, data: bytes) -> str:
        """Extract text from HTML bytes."""
        try:
            soup = BeautifulSoup(data, "html.parser")
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            text = soup.get_text(separator="\n", strip=True)
            return text
        except Exception as e:
            logger.warning(f"HTML extraction failed: {e}")
            return ""

    def _extract_docx(self, data: bytes) -> str:
        """Extract text from DOCX bytes."""
        try:
            buffer = io.BytesIO(data)
            doc = DocxDocument(buffer)
            paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
            return "\n\n".join(paragraphs)
        except Exception as e:
            logger.warning(f"DOCX extraction failed: {e}")
            return ""
