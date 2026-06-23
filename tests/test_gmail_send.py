"""Tests for GmailService.send_email(), list_messages_with_metadata(), get_message()."""
import base64
import pytest
from unittest.mock import MagicMock, patch, call
from services.gmail_service import GmailService, SEND_SCOPE, READONLY_SCOPE


class TestSendEmail:
    def test_send_email_success(self):
        svc = GmailService.__new__(GmailService)
        svc.org_id = 1
        svc.db = None

        mock_api = MagicMock()
        mock_api.users().messages().send().execute.return_value = {"id": "msg123"}

        with patch.object(svc, "get_service", return_value=mock_api):
            with patch.object(svc, "get_account_status", return_value={"can_send": True}):
                result = svc.send_email(
                    account_name="test@example.com",
                    to="cliente@exemplo.com",
                    subject="Prazo urgente",
                    body_html="<p>Atenção ao prazo</p>",
                    body_text="Atenção ao prazo",
                )

        assert result["success"] is True
        assert result["message_id"] == "msg123"

    def test_send_email_no_service_returns_error(self):
        svc = GmailService.__new__(GmailService)
        svc.org_id = 1
        svc.db = None

        with patch.object(svc, "get_service", return_value=None):
            result = svc.send_email(
                account_name="x@example.com",
                to="y@example.com",
                subject="s",
                body_html="b",
                body_text="b",
            )

        assert result["success"] is False
        assert result["error"] == "no_service"

    def test_send_email_no_send_scope_returns_error(self):
        svc = GmailService.__new__(GmailService)
        svc.org_id = 1
        svc.db = None

        mock_api = MagicMock()
        with patch.object(svc, "get_service", return_value=mock_api):
            with patch.object(svc, "get_account_status", return_value={"can_send": False}):
                result = svc.send_email(
                    account_name="x@example.com",
                    to="y@example.com",
                    subject="s",
                    body_html="b",
                    body_text="b",
                )

        assert result["success"] is False
        assert result["error"] == "no_send_scope"

    def test_send_email_includes_reply_headers_when_reply_to_given(self):
        svc = GmailService.__new__(GmailService)
        svc.org_id = 1
        svc.db = None

        captured = {}

        def fake_send(**kwargs):
            captured["body"] = kwargs.get("body", {})
            m = MagicMock()
            m.execute.return_value = {"id": "reply456"}
            return m

        mock_api = MagicMock()
        mock_api.users().messages().send = fake_send

        with patch.object(svc, "get_service", return_value=mock_api):
            with patch.object(svc, "get_account_status", return_value={"can_send": True}):
                result = svc.send_email(
                    account_name="x@example.com",
                    to="y@example.com",
                    subject="Re: test",
                    body_html="<p>reply</p>",
                    body_text="reply",
                    reply_to_message_id="original123",
                )

        assert result["success"] is True
        raw = base64.urlsafe_b64decode(captured["body"]["raw"] + "==").decode(
            "utf-8", errors="replace"
        )
        assert "In-Reply-To: original123" in raw
        assert "References: original123" in raw

    def test_send_email_includes_cc_when_provided(self):
        svc = GmailService.__new__(GmailService)
        svc.org_id = 1
        svc.db = None

        captured = {}

        def fake_send(**kwargs):
            captured["body"] = kwargs.get("body", {})
            m = MagicMock()
            m.execute.return_value = {"id": "cc789"}
            return m

        mock_api = MagicMock()
        mock_api.users().messages().send = fake_send

        with patch.object(svc, "get_service", return_value=mock_api):
            with patch.object(svc, "get_account_status", return_value={"can_send": True}):
                svc.send_email(
                    account_name="x@example.com",
                    to="dest@ex.com",
                    subject="Com CC",
                    body_html="<p>msg</p>",
                    body_text="msg",
                    cc="copia@ex.com",
                )

        raw = base64.urlsafe_b64decode(captured["body"]["raw"] + "==").decode(
            "utf-8", errors="replace"
        )
        assert "Cc: copia@ex.com" in raw


class TestListMessagesWithMetadata:
    def test_returns_empty_list_when_no_service(self):
        svc = GmailService.__new__(GmailService)
        svc.org_id = 1
        svc.db = None

        with patch.object(svc, "get_service", return_value=None):
            result = svc.list_messages_with_metadata("x@example.com", max_results=5)

        assert result == []

    def test_returns_mapped_messages(self):
        svc = GmailService.__new__(GmailService)
        svc.org_id = 1
        svc.db = None

        mock_api = MagicMock()
        mock_api.users().messages().list().execute.return_value = {
            "messages": [{"id": "abc", "threadId": "t1"}]
        }
        mock_api.users().messages().get().execute.return_value = {
            "id": "abc",
            "threadId": "t1",
            "internalDate": "1749600000000",
            "labelIds": ["INBOX", "UNREAD"],
            "snippet": "prazo urgente",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Prazo"},
                    {"name": "From", "value": "cliente@ex.com"},
                    {"name": "To", "value": "escritorio@example.com"},
                ],
                "mimeType": "text/plain",
                "body": {"data": ""},
            },
        }

        with patch.object(svc, "get_service", return_value=mock_api):
            result = svc.list_messages_with_metadata("x@example.com", max_results=5)

        assert len(result) == 1
        assert result[0]["subject"] == "Prazo"
        assert result[0]["sender"] == "cliente@ex.com"
        assert result[0]["is_read"] is False
        assert result[0]["body_text"] == "prazo urgente"
        assert result[0]["id"] == "abc"


class TestGetMessage:
    def test_returns_none_when_no_service(self):
        svc = GmailService.__new__(GmailService)
        svc.org_id = 1
        svc.db = None

        with patch.object(svc, "get_service", return_value=None):
            result = svc.get_message("x@example.com", "msg_id_123")

        assert result is None

    def test_returns_mapped_message(self):
        svc = GmailService.__new__(GmailService)
        svc.org_id = 1
        svc.db = None

        mock_api = MagicMock()
        mock_api.users().messages().get().execute.return_value = {
            "id": "xyz",
            "internalDate": "1749600000000",
            "labelIds": ["INBOX"],
            "snippet": "snip",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Teste"},
                    {"name": "From", "value": "a@b.com"},
                    {"name": "To", "value": "c@d.com"},
                ],
                "mimeType": "text/plain",
                "body": {"data": ""},
            },
        }

        with patch.object(svc, "get_service", return_value=mock_api):
            result = svc.get_message("x@example.com", "xyz")

        assert result is not None
        assert result["id"] == "xyz"
        assert result["subject"] == "Teste"
        assert result["is_read"] is True  # UNREAD not in labelIds
