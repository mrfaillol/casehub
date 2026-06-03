#!/usr/bin/env python3
"""
Unit Tests - Document Google Drive Sync Service
Tests sync_to_google_drive(), retry_failed_syncs(), error handling
"""
import pytest
import sys
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.document_sync import sync_to_google_drive, retry_failed_syncs


class TestDocumentSync:
    """Test suite for Google Drive sync service"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        db = Mock()
        db.query = Mock()
        db.commit = Mock()
        db.rollback = Mock()
        return db

    @pytest.fixture
    def mock_document(self):
        """Mock document object"""
        doc = Mock()
        doc.id = 1
        doc.name = "Test Document.pdf"
        doc.doc_type = "Passaporte"
        doc.file_path = "/tmp/test.pdf"
        doc.local_path = "/tmp/test.pdf"
        doc.org_id = 1
        doc.client_id = 10
        doc.case_id = None
        doc.visa_category = "EB1A"
        doc.content_hash = None
        doc.drive_file_id = None
        doc.drive_link = None
        doc.drive_folder_id = None
        doc.mime_type = "application/pdf"
        doc.drive_sync_status = "not_synced"
        doc.drive_retry_count = 0
        return doc

    @pytest.fixture
    def mock_client(self):
        """Mock client object"""
        client = Mock()
        client.id = 10
        client.org_id = 1
        client.first_name = "John"
        client.last_name = "Doe"
        client.drive_folder_id = None
        return client

    def tenant_query_patch(self):
        return patch(
            'services.document_sync.tenant_query',
            side_effect=lambda db, model, org_id: db.query(model),
        )

    def test_sync_success(self, mock_db, mock_document, mock_client):
        """Test successful Google Drive sync"""
        # Setup mocks
        mock_db.query().filter().first.side_effect = [mock_document, mock_client]

        with self.tenant_query_patch(), patch('services.document_sync.GoogleDriveHandler') as mock_handler_class:
            mock_handler = Mock()
            mock_handler.upload_document.return_value = {
                "success": True,
                "file_id": "1ABC123XYZ",
                "web_link": "https://drive.google.com/file/d/1ABC123XYZ/view"
            }
            mock_handler_class.return_value = mock_handler

            with patch('pathlib.Path.exists', return_value=True):
                result = sync_to_google_drive(mock_db, 1)

        # Assertions
        assert result["success"] is True
        assert result["file_id"] == "1ABC123XYZ"
        assert "drive.google.com" in result["web_link"]
        assert mock_document.drive_sync_status == "synced"
        assert mock_document.drive_file_id == "1ABC123XYZ"
        mock_db.commit.assert_called()

    def test_sync_file_not_found(self, mock_db, mock_document, mock_client):
        """Test sync fails when file doesn't exist"""
        mock_db.query().filter().first.side_effect = [mock_document, mock_client]

        with self.tenant_query_patch(), patch('pathlib.Path.exists', return_value=False):
            result = sync_to_google_drive(mock_db, 1)

        assert result["success"] is False
        assert "not found" in result["error"].lower()
        assert mock_document.drive_sync_status == "failed"

    def test_sync_document_not_found(self, mock_db):
        """Test sync fails when document doesn't exist in DB"""
        mock_db.query().filter().first.return_value = None

        result = sync_to_google_drive(mock_db, 999)

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_sync_client_not_found(self, mock_db, mock_document):
        """Test sync fails gracefully when client not found"""
        mock_db.query().filter().first.side_effect = [mock_document, None]

        with self.tenant_query_patch(), patch('pathlib.Path.exists', return_value=True):
            result = sync_to_google_drive(mock_db, 1)

        assert result["success"] is False
        assert "client" in result["error"].lower()

    def test_sync_requires_tenant_scope(self, mock_db, mock_document):
        """Test sync refuses global Drive lookups when tenant scope is unknown."""
        mock_document.org_id = None
        mock_db.query().filter().first.side_effect = [mock_document, None]

        result = sync_to_google_drive(mock_db, 1)

        assert result["success"] is False
        assert "tenant scope" in result["error"].lower()

    def test_sync_api_error(self, mock_db, mock_document, mock_client):
        """Test sync handles Google Drive API errors"""
        mock_db.query().filter().first.side_effect = [mock_document, mock_client]

        with self.tenant_query_patch(), patch('services.document_sync.GoogleDriveHandler') as mock_handler_class:
            mock_handler = Mock()
            mock_handler.upload_document.return_value = {
                "success": False,
                "error": "API quota exceeded"
            }
            mock_handler_class.return_value = mock_handler

            with patch('pathlib.Path.exists', return_value=True):
                result = sync_to_google_drive(mock_db, 1)

        assert result["success"] is False
        assert "API quota" in result["error"]
        assert mock_document.drive_sync_status == "failed"
        assert mock_document.drive_retry_count == 1

    def test_retry_failed_syncs(self, mock_db, mock_document, mock_client):
        """Test retry_failed_syncs processes failed documents"""
        mock_document.drive_sync_status = "failed"
        mock_document.drive_retry_count = 1
        mock_db.query().filter().all.return_value = [mock_document]
        mock_db.query().filter().first.side_effect = [mock_document, mock_client]

        with self.tenant_query_patch(), patch('services.document_sync.GoogleDriveHandler') as mock_handler_class:
            mock_handler = Mock()
            mock_handler.upload_document.return_value = {
                "success": True,
                "file_id": "1ABC123XYZ",
                "web_link": "https://drive.google.com/file/d/1ABC123XYZ/view"
            }
            mock_handler_class.return_value = mock_handler

            with patch('pathlib.Path.exists', return_value=True):
                results = retry_failed_syncs(mock_db, max_retries=5)

        assert results["total_attempted"] == 1
        assert results["successful"] == 1
        assert mock_document.drive_sync_status == "synced"

    def test_max_retries_exceeded(self, mock_db, mock_document):
        """Test documents with too many retries are skipped"""
        mock_document.drive_sync_status = "failed"
        mock_document.drive_retry_count = 10
        mock_db.query().filter().all.return_value = []

        results = retry_failed_syncs(mock_db, max_retries=5)

        assert results["total_attempted"] == 0  # Skipped due to max retries
        assert results["skipped"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
