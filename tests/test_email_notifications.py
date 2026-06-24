#!/usr/bin/env python3
"""
Unit Tests - Email Notification Service
Tests notify_client_approval(), notify_client_rejection(), template rendering
"""
import pytest
import sys
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, mock_open

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.notifications import (
    notify_client_approval,
    notify_client_rejection,
    load_email_template,
    send_email
)


class TestEmailNotifications:
    """Test suite for email notification service"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        db = Mock()
        db.query = Mock()
        db.commit = Mock()
        return db

    @pytest.fixture
    def mock_document(self):
        """Mock document object"""
        doc = Mock()
        doc.id = 1
        doc.name = "Brazilian Passport.pdf"
        doc.doc_type = "Passaporte"
        doc.client_id = 10
        doc.intake_package_id = None
        doc.uploaded_via = "client_portal"
        doc.rejection_reason = None
        doc.created_at = None
        doc.reviewed_at = None
        doc.approval_notification_sent = False
        doc.rejection_notification_sent = False
        return doc

    @pytest.fixture
    def mock_client(self):
        """Mock client object"""
        client = Mock()
        client.id = 10
        client.first_name = "PessoaDemo"
        client.last_name = "Silva"
        client.email = "pessoa_demo@example.com"
        return client

    @pytest.fixture
    def mock_package(self):
        """Mock intake package"""
        package = Mock()
        package.package_id = "ABC123"
        return package

    def test_notify_approval_success(self, mock_db, mock_document, mock_client, mock_package):
        """Test successful approval notification"""
        mock_db.query().filter().first.side_effect = [mock_document, mock_client, mock_package]

        with patch('services.notifications.email.load_email_template') as mock_load:
            mock_load.return_value = "<html>Test {{ client_name }}</html>"

            with patch('services.notifications.email.send_email') as mock_send:
                mock_send.return_value = True

                result = notify_client_approval(mock_db, 1)

        assert result["success"] is True
        assert mock_document.approval_notification_sent is True
        assert mock_document.client_notified_at is not None
        mock_db.commit.assert_called()

    def test_notify_approval_document_not_found(self, mock_db):
        """Test approval notification fails when document not found"""
        mock_db.query().filter().first.return_value = None

        result = notify_client_approval(mock_db, 999)

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_notify_approval_client_not_found(self, mock_db, mock_document):
        """Test approval notification fails when client not found"""
        mock_db.query().filter().first.side_effect = [mock_document, None]

        result = notify_client_approval(mock_db, 1)

        assert result["success"] is False
        assert "client" in result["error"].lower()

    def test_notify_approval_no_email(self, mock_db, mock_document, mock_client, mock_package):
        """Test approval notification fails when client has no email"""
        mock_client.email = None
        mock_db.query().filter().first.side_effect = [mock_document, mock_client, mock_package]

        result = notify_client_approval(mock_db, 1)

        assert result["success"] is False
        assert "email" in result["error"].lower()

    def test_notify_rejection_success(self, mock_db, mock_document, mock_client, mock_package):
        """Test successful rejection notification"""
        mock_document.rejection_reason = "Document is blurry, please rescan"
        mock_db.query().filter().first.side_effect = [mock_document, mock_client, mock_package]

        with patch('services.notifications.email.load_email_template') as mock_load:
            mock_load.return_value = "<html>Test {{ rejection_reason }}</html>"

            with patch('services.notifications.email.send_email') as mock_send:
                mock_send.return_value = True

                result = notify_client_rejection(mock_db, 1)

        assert result["success"] is True
        assert mock_document.rejection_notification_sent is True
        assert mock_document.client_notified_at is not None
        mock_db.commit.assert_called()

    def test_notify_rejection_without_reason(self, mock_db, mock_document, mock_client, mock_package):
        """Test rejection notification with no reason provided"""
        mock_document.rejection_reason = None
        mock_db.query().filter().first.side_effect = [mock_document, mock_client, mock_package]

        with patch('services.notifications.email.load_email_template') as mock_load:
            mock_load.return_value = "<html>Test</html>"

            with patch('services.notifications.email.send_email') as mock_send:
                mock_send.return_value = True

                result = notify_client_rejection(mock_db, 1)

        # Should still send, but with generic reason
        assert result["success"] is True

    def test_send_email_smtp_error(self, mock_db, mock_document, mock_client, mock_package):
        """Test email notification handles SMTP errors gracefully"""
        mock_db.query().filter().first.side_effect = [mock_document, mock_client, mock_package]

        with patch('services.notifications.email.load_email_template') as mock_load:
            mock_load.return_value = "<html>Test</html>"

            with patch('services.notifications.email.send_email') as mock_send:
                mock_send.side_effect = Exception("SMTP connection failed")

                result = notify_client_approval(mock_db, 1)

        assert result["success"] is False
        assert "SMTP" in result["error"] or "failed" in result["error"].lower()

    def test_load_email_template(self):
        """Test template loading"""
        mock_html = "<html><body>{{ test }}</body></html>"

        with patch('builtins.open', mock_open(read_data=mock_html)):
            template = load_email_template("test.html")

        assert template == mock_html
        assert "{{ test }}" in template

    def test_template_rendering_with_jinja2(self, mock_db, mock_document, mock_client, mock_package):
        """Test Jinja2 template rendering with actual variables"""
        mock_db.query().filter().first.side_effect = [mock_document, mock_client, mock_package]

        template_html = "<html>Hello {{ client_name }}, your document {{ document_name }} is approved.</html>"

        with patch('services.notifications.email.load_email_template') as mock_load:
            mock_load.return_value = template_html

            with patch('services.notifications.email.send_email') as mock_send:
                # Capture the rendered HTML
                def capture_html(to_email, subject, html_body, cc=None):
                    assert "PessoaDemo Silva" in html_body
                    assert "Brazilian Passport.pdf" in html_body
                    return True

                mock_send.side_effect = capture_html

                result = notify_client_approval(mock_db, 1)

        assert result["success"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
