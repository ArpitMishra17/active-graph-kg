"""Smoke tests for Google Drive connector with mocked Google API.

These tests verify DriveConnector functionality without external dependencies by
mocking the Google Drive API client and service account credentials.

Test Coverage:
- Connector initialization with service account
- stat() for binary files (PDF with md5Checksum)
- stat() for Google Workspace docs (modifiedTime:version ETag fallback)
- fetch_text() for binary PDF files
- fetch_text() for Google Doc HTML export
- fetch_text() file size limit enforcement
- list_changes() initial sync (no cursor)
- list_changes() incremental sync with cursor
- list_changes() filtering trashed files
- stat() 404 error handling
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.http import HttpError


@pytest.fixture(autouse=True)
def mock_google_services():
    """Mock Google API client and service account credentials globally for all tests."""
    with (
        patch("activekg.connectors.providers.drive.build") as mock_build,
        patch(
            "activekg.connectors.providers.drive.service_account.Credentials.from_service_account_info"
        ) as mock_creds,
    ):
        # Mock credentials
        mock_credentials = MagicMock()
        mock_creds.return_value = mock_credentials

        yield {"build": mock_build, "credentials": mock_creds}


class TestDriveConnectorSmoke:
    """Smoke tests for DriveConnector with mocked Google API."""

    @classmethod
    def setup_class(cls):
        """Setup test fixtures."""
        cls.tenant_id = "test-tenant"
        cls.config = {
            "credentials": json.dumps(
                {
                    "type": "service_account",
                    "project_id": "test-project",
                    "private_key_id": "key123",
                    "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC\n-----END PRIVATE KEY-----\n",
                    "client_email": "test@test-project.iam.gserviceaccount.com",
                    "client_id": "123456789",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/test%40test-project.iam.gserviceaccount.com",
                }
            ),
            "root_folders": ["folder_abc"],
            "poll_interval_seconds": 300,
            "page_size": 100,
            "use_changes_feed": True,
            "max_file_size_bytes": 100 * 1024 * 1024,  # 100MB
            "enabled": True,
        }

    def test_connector_initialization(self, mock_google_services):
        """Test DriveConnector initializes successfully with service account."""
        from activekg.connectors.providers.drive import DriveConnector

        # Mock the Drive API service
        mock_service = MagicMock()
        mock_google_services["build"].return_value = mock_service

        # Initialize connector
        connector = DriveConnector(tenant_id=self.tenant_id, config=self.config)

        # Assertions
        assert connector.tenant_id == self.tenant_id
        assert connector.page_size == 100
        assert connector.use_changes_feed is True
        assert connector.max_file_size_bytes == 100 * 1024 * 1024
        assert len(connector.root_folders) == 1

        # Verify Google API was initialized
        mock_google_services["build"].assert_called_once()
        mock_google_services["credentials"].assert_called_once()

    def test_stat_binary_file_with_md5(self, mock_google_services):
        """Test stat() for binary file (PDF) with md5Checksum."""
        from activekg.connectors.providers.drive import DriveConnector

        # Mock Drive API files.get response
        mock_service = MagicMock()
        mock_files = MagicMock()
        mock_get = MagicMock()

        mock_file_metadata = {
            "id": "pdf_file_123",
            "name": "report.pdf",
            "mimeType": "application/pdf",
            "modifiedTime": "2025-11-12T10:30:00.000Z",
            "version": "7",
            "size": "2048576",
            "md5Checksum": "5d41402abc4b2a76b9719d911017c592",
            "owners": [{"emailAddress": "owner@example.com"}],
            "trashed": False,
        }

        mock_get.execute.return_value = mock_file_metadata
        mock_files.get.return_value = mock_get
        mock_service.files.return_value = mock_files
        mock_google_services["build"].return_value = mock_service

        # Initialize connector and call stat
        connector = DriveConnector(tenant_id=self.tenant_id, config=self.config)
        stats = connector.stat("drive://pdf_file_123")

        # Assertions - stat() returns ConnectorStats dataclass
        assert stats.exists is True
        assert stats.etag == "5d41402abc4b2a76b9719d911017c592"
        assert stats.mime_type == "application/pdf"
        assert stats.size == 2048576
        assert stats.owner == "owner@example.com"
        assert stats.modified_at is not None

        # Verify API call
        mock_files.get.assert_called_once_with(
            fileId="pdf_file_123",
            fields="id,name,mimeType,modifiedTime,version,size,md5Checksum,owners,trashed",
            supportsAllDrives=True,
        )

    def test_stat_workspace_doc_etag_fallback(self, mock_google_services):
        """Test stat() for Google Workspace doc with modifiedTime:version ETag fallback."""
        from activekg.connectors.providers.drive import DriveConnector

        # Mock Drive API files.get response
        mock_service = MagicMock()
        mock_files = MagicMock()
        mock_get = MagicMock()

        mock_file_metadata = {
            "id": "doc_file_456",
            "name": "presentation.slides",
            "mimeType": "application/vnd.google-apps.presentation",
            "modifiedTime": "2025-11-12T11:30:00.000Z",
            "version": "42",
            "md5Checksum": None,  # Google Workspace docs don't have MD5
            "owners": [{"emailAddress": "owner@example.com"}],
            "trashed": False,
        }

        mock_get.execute.return_value = mock_file_metadata
        mock_files.get.return_value = mock_get
        mock_service.files.return_value = mock_files
        mock_google_services["build"].return_value = mock_service

        # Initialize connector and call stat
        connector = DriveConnector(tenant_id=self.tenant_id, config=self.config)
        stats = connector.stat("drive://doc_file_456")

        # Assertions - ETag should use modifiedTime:version fallback
        assert stats.exists is True
        assert stats.etag == "2025-11-12T11:30:00.000Z:42"  # Fallback ETag
        assert stats.mime_type == "application/vnd.google-apps.presentation"
        assert stats.size is None  # Workspace docs don't have size
        assert stats.owner == "owner@example.com"

    def test_fetch_text_binary_pdf(self, mock_google_services):
        """Test fetch_text() for binary PDF file."""
        from activekg.connectors.providers.drive import DriveConnector

        # Mock Drive API responses
        mock_service = MagicMock()
        mock_files = MagicMock()

        # Mock files.get for metadata
        mock_get = MagicMock()
        mock_get.execute.return_value = {
            "id": "pdf_123",
            "name": "test.pdf",
            "mimeType": "application/pdf",
            "size": "1024",
            "webViewLink": "https://drive.google.com/file/d/pdf_123/view",
        }

        # Mock files.get_media for content download
        mock_get_media = MagicMock()

        # Create a minimal valid PDF for testing (content is mocked via pdfplumber)
        _pdf_content = b"%PDF-1.4\n%%EOF"

        # Mock MediaIoBaseDownload behavior
        with patch("activekg.connectors.providers.drive.MediaIoBaseDownload") as mock_downloader:
            mock_download_instance = MagicMock()
            mock_download_instance.next_chunk.return_value = (MagicMock(progress=lambda: 1.0), True)
            mock_downloader.return_value = mock_download_instance

            # Mock pdfplumber to avoid actual PDF parsing
            with patch("activekg.connectors.providers.drive.pdfplumber") as mock_pdfplumber:
                mock_pdf = MagicMock()
                mock_page = MagicMock()
                mock_page.extract_text.return_value = "Sample PDF text content"
                mock_pdf.pages = [mock_page]
                mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf

                mock_files.get.return_value = mock_get
                mock_files.get_media.return_value = mock_get_media
                mock_service.files.return_value = mock_files
                mock_google_services["build"].return_value = mock_service

                # Initialize connector and fetch text
                connector = DriveConnector(tenant_id=self.tenant_id, config=self.config)
                result = connector.fetch_text("drive://pdf_123")

                # Assertions - fetch_text() returns FetchResult dataclass
                assert result.text == "Sample PDF text content"
                assert result.title == "test.pdf"
                assert result.metadata["file_id"] == "pdf_123"
                assert result.metadata["mime_type"] == "application/pdf"
                assert result.metadata["size"] == 1024

                # Verify API calls
                mock_files.get.assert_called_once_with(
                    fileId="pdf_123",
                    fields="id,name,mimeType,size,webViewLink",
                    supportsAllDrives=True,
                )
                mock_files.get_media.assert_called_once_with(
                    fileId="pdf_123", supportsAllDrives=True
                )

    def test_fetch_text_google_doc_export(self, mock_google_services):
        """Test fetch_text() for Google Doc with HTML export."""
        from activekg.connectors.providers.drive import DriveConnector

        # Mock Drive API responses
        mock_service = MagicMock()
        mock_files = MagicMock()

        # Mock files.get for metadata
        mock_get = MagicMock()
        mock_get.execute.return_value = {
            "id": "doc_789",
            "name": "design_doc.gdoc",
            "mimeType": "application/vnd.google-apps.document",
            "webViewLink": "https://docs.google.com/document/d/doc_789/edit",
        }

        # Mock files.export_media for HTML export
        mock_export = MagicMock()
        html_content = b"<html><body><h1>Test Document</h1><p>Content here.</p></body></html>"

        # Mock MediaIoBaseDownload behavior for export
        with patch("activekg.connectors.providers.drive.MediaIoBaseDownload") as mock_downloader:
            mock_download_instance = MagicMock()
            mock_download_instance.next_chunk.return_value = (MagicMock(progress=lambda: 1.0), True)

            # Make the buffer contain our HTML content
            def mock_download_side_effect(buffer, request):
                buffer.write(html_content)
                return mock_download_instance

            mock_downloader.side_effect = mock_download_side_effect

            mock_files.get.return_value = mock_get
            mock_files.export_media.return_value = mock_export
            mock_service.files.return_value = mock_files
            mock_google_services["build"].return_value = mock_service

            # Initialize connector and fetch text
            connector = DriveConnector(tenant_id=self.tenant_id, config=self.config)
            result = connector.fetch_text("drive://doc_789")

            # Assertions - should extract text from HTML
            assert "Test Document" in result.text
            assert "Content here" in result.text
            assert result.title == "design_doc.gdoc"
            assert result.metadata["file_id"] == "doc_789"
            assert result.metadata["mime_type"] == "application/vnd.google-apps.document"

            # Verify export was called with correct MIME type
            mock_files.export_media.assert_called_once_with(fileId="doc_789", mimeType="text/html")

    def test_fetch_text_file_size_limit(self, mock_google_services):
        """Test fetch_text() enforces max file size limit."""
        from activekg.connectors.providers.drive import DriveConnector

        # Mock Drive API response with file exceeding size limit
        mock_service = MagicMock()
        mock_files = MagicMock()
        mock_get = MagicMock()

        mock_get.execute.return_value = {
            "id": "huge_file",
            "name": "huge.pdf",
            "mimeType": "application/pdf",
            "size": str(200 * 1024 * 1024),  # 200MB exceeds 100MB limit
            "webViewLink": "https://drive.google.com/file/d/huge_file/view",
        }

        mock_files.get.return_value = mock_get
        mock_service.files.return_value = mock_files
        mock_google_services["build"].return_value = mock_service

        # Initialize connector
        connector = DriveConnector(tenant_id=self.tenant_id, config=self.config)

        # Should raise ValueError for file size exceeding limit
        with pytest.raises(ValueError, match="File size .* exceeds limit"):
            connector.fetch_text("drive://huge_file")

    def test_list_changes_initial_sync(self, mock_google_services):
        """Test list_changes() initial sync (no cursor)."""
        from activekg.connectors.providers.drive import DriveConnector

        # Mock Drive API responses
        mock_service = MagicMock()
        mock_changes = MagicMock()

        # Mock getStartPageToken for initial sync
        mock_start_token = MagicMock()
        mock_start_token.execute.return_value = {"startPageToken": "token_100"}
        mock_changes.getStartPageToken.return_value = mock_start_token

        # Mock changes.list response
        mock_list = MagicMock()
        mock_list.execute.return_value = {
            "changes": [
                {
                    "fileId": "file_1",
                    "removed": False,
                    "file": {
                        "id": "file_1",
                        "name": "doc1.txt",
                        "mimeType": "text/plain",
                        "modifiedTime": "2025-11-12T10:00:00.000Z",
                        "trashed": False,
                        "parents": ["folder_abc"],
                    },
                },
                {
                    "fileId": "file_2",
                    "removed": False,
                    "file": {
                        "id": "file_2",
                        "name": "doc2.pdf",
                        "mimeType": "application/pdf",
                        "modifiedTime": "2025-11-12T10:05:00.000Z",
                        "trashed": False,
                        "parents": ["folder_abc"],
                    },
                },
            ],
            "newStartPageToken": "token_101",
        }

        mock_changes.list.return_value = mock_list
        mock_service.changes.return_value = mock_changes
        mock_google_services["build"].return_value = mock_service

        # Initialize connector
        connector = DriveConnector(tenant_id=self.tenant_id, config=self.config)

        # Call list_changes with no cursor (initial sync)
        changes, next_cursor = connector.list_changes(cursor=None)

        # Assertions - list_changes() returns tuple of (List[ChangeItem], Optional[str])
        assert isinstance(changes, list)
        assert len(changes) == 2

        # Verify first change
        assert changes[0].uri == "drive://file_1"
        assert changes[0].operation == "updated"
        assert changes[0].modified_at is not None

        # Verify second change
        assert changes[1].uri == "drive://file_2"
        assert changes[1].operation == "updated"

        # Verify cursor
        assert next_cursor is not None
        cursor_data = json.loads(next_cursor)
        assert cursor_data["page_token"] == "token_101"
        assert cursor_data["start_page_token"] == "token_101"

        # Verify API calls
        mock_changes.getStartPageToken.assert_called_once_with(supportsAllDrives=True)
        mock_changes.list.assert_called_once()

    def test_list_changes_incremental_with_cursor(self, mock_google_services):
        """Test list_changes() incremental sync with cursor."""
        from activekg.connectors.providers.drive import DriveConnector

        # Mock Drive API responses
        mock_service = MagicMock()
        mock_changes = MagicMock()

        # Mock changes.list response for incremental sync
        mock_list = MagicMock()
        mock_list.execute.return_value = {
            "changes": [
                {
                    "fileId": "file_3",
                    "removed": False,
                    "file": {
                        "id": "file_3",
                        "name": "updated.doc",
                        "mimeType": "application/vnd.google-apps.document",
                        "modifiedTime": "2025-11-12T11:00:00.000Z",
                        "trashed": False,
                        "parents": ["folder_abc"],
                    },
                }
            ],
            "newStartPageToken": "token_102",
        }

        mock_changes.list.return_value = mock_list
        mock_service.changes.return_value = mock_changes
        mock_google_services["build"].return_value = mock_service

        # Initialize connector
        connector = DriveConnector(tenant_id=self.tenant_id, config=self.config)

        # Call list_changes with existing cursor
        existing_cursor = json.dumps({"page_token": "token_101", "start_page_token": "token_101"})
        changes, next_cursor = connector.list_changes(cursor=existing_cursor)

        # Assertions
        assert len(changes) == 1
        assert changes[0].uri == "drive://file_3"
        assert changes[0].operation == "updated"

        # Verify cursor advanced
        cursor_data = json.loads(next_cursor)
        assert cursor_data["page_token"] == "token_102"

        # Verify API call used existing cursor
        mock_changes.list.assert_called_once()
        call_args = mock_changes.list.call_args
        assert call_args[1]["pageToken"] == "token_101"

    def test_list_changes_filters_trashed_files(self, mock_google_services):
        """Test list_changes() filters out trashed files."""
        from activekg.connectors.providers.drive import DriveConnector

        # Mock Drive API responses
        mock_service = MagicMock()
        mock_changes = MagicMock()

        # Mock getStartPageToken
        mock_start_token = MagicMock()
        mock_start_token.execute.return_value = {"startPageToken": "token_100"}
        mock_changes.getStartPageToken.return_value = mock_start_token

        # Mock changes.list with trashed and removed files
        mock_list = MagicMock()
        mock_list.execute.return_value = {
            "changes": [
                {
                    "fileId": "file_active",
                    "removed": False,
                    "file": {
                        "id": "file_active",
                        "name": "active.txt",
                        "mimeType": "text/plain",
                        "modifiedTime": "2025-11-12T10:00:00.000Z",
                        "trashed": False,
                        "parents": ["folder_abc"],
                    },
                },
                {
                    "fileId": "file_trashed",
                    "removed": False,
                    "file": {
                        "id": "file_trashed",
                        "name": "trashed.txt",
                        "mimeType": "text/plain",
                        "modifiedTime": "2025-11-12T10:01:00.000Z",
                        "trashed": True,
                        "parents": ["folder_abc"],
                    },
                },
                {"fileId": "file_removed", "removed": True, "file": {}},
            ],
            "newStartPageToken": "token_101",
        }

        mock_changes.list.return_value = mock_list
        mock_service.changes.return_value = mock_changes
        mock_google_services["build"].return_value = mock_service

        # Initialize connector
        connector = DriveConnector(tenant_id=self.tenant_id, config=self.config)

        # Call list_changes
        changes, next_cursor = connector.list_changes(cursor=None)

        # Assertions - should include active file and trashed file (marked as deleted)
        # Note: Removed files with empty file_info are filtered out by _should_include_file()
        assert len(changes) == 2

        # First change: active file
        assert changes[0].uri == "drive://file_active"
        assert changes[0].operation == "updated"

        # Second change: trashed file marked as deleted
        assert changes[1].uri == "drive://file_trashed"
        assert changes[1].operation == "deleted"

    def test_stat_handles_404_error(self, mock_google_services):
        """Test stat() handles 404 errors gracefully."""
        from activekg.connectors.providers.drive import DriveConnector

        # Mock Drive API to raise HttpError 404
        mock_service = MagicMock()
        mock_files = MagicMock()
        mock_get = MagicMock()

        # Create proper HttpError
        resp = MagicMock()
        resp.status = 404
        resp.reason = "Not Found"
        http_error = HttpError(
            resp=resp, content=b'{"error": {"code": 404, "message": "File not found"}}'
        )

        mock_get.execute.side_effect = http_error
        mock_files.get.return_value = mock_get
        mock_service.files.return_value = mock_files
        mock_google_services["build"].return_value = mock_service

        # Initialize connector
        connector = DriveConnector(tenant_id=self.tenant_id, config=self.config)

        # Call stat for non-existent file
        stats = connector.stat("drive://nonexistent_file")

        # Assertions - should return ConnectorStats with exists=False
        assert stats.exists is False
        assert stats.etag is None
        assert stats.size is None
        assert stats.mime_type is None
