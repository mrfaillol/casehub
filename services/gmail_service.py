"""
CaseHub - Gmail OAuth integration service (per-org multi-tenant).

Mirrors the structure of `services/google_calendar.py` so each org gets
isolated token storage in `credentials/org_{id}/gmail_token_{account}.json`.

Scope strategy (alpha 30/05):
- `gmail.readonly` lets us list/preview recent messages without granting
  send authority. We add `gmail.send` so the same connection can later
  power outbound CaseHub mail without a re-consent loop.

The OAuth client secret JSON is shared across orgs (it is the application's
identity with Google) and lives in `credentials/google_client_secret.json` —
the same file the Calendar service uses.

Token files are ALWAYS written with `0o600` and inside an `org_{id}/`
directory that itself enforces `0o700`. The Gmail token is NEVER stored in
the database; if the file is missing, the org simply has no Gmail link.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session

from config import settings
from services.per_org_credentials import (
    DEFAULT_ORG_ID,
    get_org_credentials_dir,
    get_org_token_path,
)

logger = logging.getLogger(__name__)


# Gmail API scopes
# - readonly: list + read messages (mail inbox preview, future templates lookup)
# - send: outbound mail via Gmail API (replaces SMTP for connected accounts)
# Keep both even if the alpha only uses readonly — single consent screen.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"

DEFAULT_KNOWN_ACCOUNTS = ("info",)  # Single account default — keeps card simple.
GOOGLE_OAUTH_REVOKE_URL = "https://oauth2.googleapis.com/revoke"


def _write_private_text(path: Path, content: str) -> None:
    """Write OAuth token with 0o600 permissions (mirrors Calendar service)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None
            handle.write(content)
    finally:
        if fd is not None:
            os.close(fd)
    os.chmod(path, 0o600)


def _json_scopes(value: Any) -> set[str]:
    if isinstance(value, str):
        return {scope for scope in value.split() if scope}
    if isinstance(value, list):
        return {str(scope) for scope in value if scope}
    return set()


class GmailService:
    """Service for Gmail OAuth, read access, and (future) outbound send.

    Multi-tenant: each org gets isolated token storage in
    `credentials/org_{id}/gmail_token_{account}.json`. When `org_id` is None,
    falls back to `DEFAULT_ORG_ID` so legacy single-tenant callers stay
    functional during the alpha migration.

    NOTE: Unlike Calendar, Gmail does NOT inherit any legacy single-tenant
    token files — Gmail OAuth is fresh in this service. SMTP usage of the
    `GMAIL_CENTER_APP_PASSWORD` is unrelated and continues to work.
    """

    def __init__(self, db: Session = None, org_id: int = None):
        self.db = db
        self.org_id = int(org_id) if org_id else DEFAULT_ORG_ID

        self.setup_error = ""
        try:
            self.credentials_dir = get_org_credentials_dir(self.org_id)
        except (OSError, ValueError) as e:
            self.setup_error = "Gmail indisponivel: diretorio de tokens sem permissao."
            logger.warning("%s org_id=%s error=%s", self.setup_error, self.org_id, e)
            self.credentials_dir = Path(settings.BASE_DIR) / "credentials" / f"org_{self.org_id}"

        # Shared OAuth client secret (same file Calendar/Drive use). Lives in
        # `credentials/` parent — NOT per-tenant.
        self.client_secrets_file = self.credentials_dir.parent / "google_client_secret.json"

    # ------------------------------------------------------------------
    # Client secret + redirect URI resolution
    # ------------------------------------------------------------------

    def _ensure_client_secrets_file(self) -> bool:
        """Verify the shared OAuth client secret JSON exists.

        Falls back to the legacy ILC `google_calendar_credentials.json` file
        which holds the same OAuth client identity (Google Cloud project does
        not change). Same fallback chain as Calendar so all three services
        (Calendar/Drive/Gmail) work on the same install.
        """
        if self.client_secrets_file.exists():
            return True

        parent_dir = self.client_secrets_file.parent
        legacy_client_file = parent_dir / "google_calendar_credentials.json"
        if legacy_client_file.exists():
            self.client_secrets_file = legacy_client_file
            return True

        consolidated_file = parent_dir / "credentials.json"
        if not consolidated_file.exists():
            return False

        try:
            data = json.loads(consolidated_file.read_text(encoding="utf-8"))
            oauth_creds = data.get("google_oauth2", {}).get("api_1", {})
            client_id = oauth_creds.get("client_id")
            client_secret = oauth_creds.get("client_secret")
            if not client_id or not client_secret:
                return False
            client_secret_json = {
                "installed": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uris": oauth_creds.get("redirect_uris", ["http://localhost"]),
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
            _write_private_text(
                self.client_secrets_file,
                json.dumps(client_secret_json, indent=2),
            )
            logger.info("Created shared OAuth client secret from consolidated legacy credentials")
            return True
        except Exception as e:
            logger.warning("Could not read legacy OAuth client layout: %s", e)
            return False

    def get_client_redirect_uris(self) -> List[str]:
        """Return authorized redirect URIs declared in the local OAuth client file."""
        if not self._ensure_client_secrets_file():
            return []

        try:
            data = json.loads(self.client_secrets_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Could not read OAuth client file: %s", e)
            return []

        client = data.get("web") or data.get("installed") or {}
        values = client.get("redirect_uris") or []
        if not isinstance(values, list):
            return []
        return [str(value).strip() for value in values if str(value).strip()]

    def redirect_uri_allowed(self, redirect_uri: str) -> bool:
        """Prevent sending the user into Google's redirect_uri_mismatch screen."""
        redirect_uri = (redirect_uri or "").strip()
        if not redirect_uri:
            return False
        return redirect_uri in self.get_client_redirect_uris()

    # ------------------------------------------------------------------
    # Token storage
    # ------------------------------------------------------------------

    def get_token_file(self, account_name: str) -> str:
        """Get path to token file for this org + account."""
        return str(get_org_token_path(self.org_id, "gmail", account_name))

    def _read_token_json(self, account_name: str) -> dict:
        token_file = self.get_token_file(account_name)
        if not os.path.exists(token_file):
            return {}
        try:
            with open(token_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning("Gmail token for %s is unreadable: %s", account_name, e)
            return {}

    def _token_needs_reconnect(self, account_name: str) -> bool:
        """Return True when the stored token lacks the readonly scope."""
        token_data = self._read_token_json(account_name)
        if not token_data:
            return False
        scopes = _json_scopes(token_data.get("scopes") or token_data.get("scope"))
        if not scopes:
            return False
        # Readonly is the minimum we need to consider the account "connected".
        return READONLY_SCOPE not in scopes

    def has_credentials(self, account_name: str) -> bool:
        creds = self.get_credentials(account_name)
        return creds is not None and creds.valid

    def get_credentials(self, account_name: str) -> Optional[Credentials]:
        """Get credentials for an account, refreshing if needed."""
        token_file = self.get_token_file(account_name)

        if not os.path.exists(token_file) or self._token_needs_reconnect(account_name):
            return None

        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)

            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                _write_private_text(Path(token_file), creds.to_json())

            return creds if creds and creds.valid else None
        except Exception as e:
            logger.error("Error getting Gmail credentials for %s: %s", account_name, e)
            return None

    # ------------------------------------------------------------------
    # OAuth flow
    # ------------------------------------------------------------------

    def get_auth_url(self, account_name: str, redirect_uri: str, state_name: str = None) -> str:
        """Get OAuth2 authorization URL."""
        if not self._ensure_client_secrets_file():
            raise FileNotFoundError(
                "Google client secrets file not found. "
                f"Configure the shared client secret or add {self.client_secrets_file}."
            )

        flow = Flow.from_client_secrets_file(
            str(self.client_secrets_file),
            scopes=SCOPES,
            redirect_uri=redirect_uri,
        )

        auth_url, _state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state_name or account_name,
        )

        return auth_url

    def handle_oauth_callback(self, code: str, account_name: str, redirect_uri: str) -> bool:
        """Handle OAuth2 callback and save credentials atomically with 0o600."""
        try:
            if not self._ensure_client_secrets_file():
                return False
            flow = Flow.from_client_secrets_file(
                str(self.client_secrets_file),
                scopes=SCOPES,
                redirect_uri=redirect_uri,
            )

            flow.fetch_token(code=code)
            creds = flow.credentials

            token_file = Path(self.get_token_file(account_name))
            _write_private_text(token_file, creds.to_json())

            return True
        except Exception as e:
            logger.error("Error handling Gmail OAuth callback: %s", e)
            return False

    # ------------------------------------------------------------------
    # Disconnect / revoke
    # ------------------------------------------------------------------

    def disconnect_account(self, account_name: str) -> bool:
        """Revoke and remove credentials for an account."""
        token_file = Path(self.get_token_file(account_name))
        if token_file.exists():
            self._revoke_account_token(token_file)
            token_file.unlink(missing_ok=True)
            return True
        return False

    def _revoke_account_token(self, token_file: Path) -> bool:
        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        except Exception as e:
            logger.warning("Could not load Gmail token for revocation: %s", e)
            return False

        token = getattr(creds, "refresh_token", None) or getattr(creds, "token", None)
        if not token:
            return False
        return self._revoke_google_token(token)

    def _revoke_google_token(self, token: str) -> bool:
        body = urlparse.urlencode({"token": token}).encode("utf-8")
        revoke_request = urlrequest.Request(
            GOOGLE_OAUTH_REVOKE_URL,
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urlrequest.urlopen(revoke_request, timeout=10) as response:
                status = getattr(response, "status", response.getcode())
                return 200 <= status < 300
        except urlerror.HTTPError as e:
            logger.warning("Gmail token revoke returned HTTP %s", e.code)
            return False
        except Exception as e:
            logger.warning("Gmail token revoke failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # Service builder + status
    # ------------------------------------------------------------------

    def get_service(self, account_name: str):
        """Get Gmail API service."""
        creds = self.get_credentials(account_name)
        if not creds:
            return None
        return build("gmail", "v1", credentials=creds)

    def verify_gmail_access(self, account_name: str) -> Dict[str, Any]:
        """Verify the stored token can call gmail.users.getProfile.

        Returns the connected email + (best-effort) message count from the
        primary profile, which is the cheapest live ping.
        """
        service = self.get_service(account_name)
        if not service:
            return {
                "verified_live": False,
                "message_count": 0,
                "connected_email": "",
                "live_error": "no_valid_credentials",
            }

        try:
            profile = service.users().getProfile(userId="me").execute()
            return {
                "verified_live": True,
                "message_count": int(profile.get("messagesTotal") or 0),
                "connected_email": profile.get("emailAddress") or "",
                "live_error": "",
            }
        except HttpError as e:
            status = getattr(getattr(e, "resp", None), "status", "unknown")
            logger.warning("Gmail live verification failed for %s: %s", account_name, e)
            return {
                "verified_live": False,
                "message_count": 0,
                "connected_email": "",
                "live_error": f"google_http_{status}",
            }
        except Exception as e:
            logger.warning("Gmail live verification failed for %s: %s", account_name, e)
            return {
                "verified_live": False,
                "message_count": 0,
                "connected_email": "",
                "live_error": "verification_failed",
            }

    def get_account_status(self, account_name: str, verify_live: bool = False) -> Dict[str, Any]:
        token_file = self.get_token_file(account_name)
        token_exists = os.path.exists(token_file)
        credentials_file_exists = self._ensure_client_secrets_file()
        needs_reconnect = self._token_needs_reconnect(account_name)
        connected = False
        error = ""
        live_status: Dict[str, Any] = {
            "verified_live": False,
            "message_count": 0,
            "connected_email": "",
            "live_error": "",
        }

        if token_exists and not needs_reconnect:
            connected = self.has_credentials(account_name)
            if not connected:
                error = "token_invalid"
        elif needs_reconnect:
            error = "needs_reconnect"
        elif not credentials_file_exists:
            error = "missing_client_secret"

        if verify_live:
            if connected:
                live_status = self.verify_gmail_access(account_name)
                connected = bool(live_status.get("verified_live"))
                if not connected:
                    error = live_status.get("live_error") or "gmail_not_verified"
            elif token_exists and not error:
                error = "gmail_not_verified"

        # Scope inventory: report which scopes the live token actually holds
        # so the UI can show "read-only" vs "read+send" without re-consent.
        token_data = self._read_token_json(account_name)
        token_scopes = _json_scopes(token_data.get("scopes") or token_data.get("scope"))

        return {
            "name": account_name,
            "connected": connected,
            "can_read": connected and READONLY_SCOPE in token_scopes,
            "can_send": connected and SEND_SCOPE in token_scopes,
            "needs_reconnect": needs_reconnect,
            "token_exists": token_exists,
            "credentials_file_exists": credentials_file_exists,
            "error": error,
            **live_status,
        }

    def get_connected_accounts(self, verify_live: bool = False) -> List[Dict]:
        """Get list of known accounts and sanitized connection status."""
        return [self.get_account_status(account, verify_live=verify_live) for account in self.default_accounts()]

    def default_accounts(self) -> List[str]:
        raw = os.getenv("GMAIL_DEFAULT_ACCOUNTS") or getattr(settings, "GMAIL_DEFAULT_ACCOUNTS", "")
        if raw:
            accounts = [item.strip() for item in raw.split(",") if item.strip()]
            return accounts or list(DEFAULT_KNOWN_ACCOUNTS)
        return list(DEFAULT_KNOWN_ACCOUNTS)

    # ------------------------------------------------------------------
    # Smoke + (future) inbound message helpers
    # ------------------------------------------------------------------

    def list_recent_messages(self, account_name: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Return sanitized metadata for the N most recent inbox messages.

        Used by the integrations card to confirm "yes, this token actually
        reads the inbox". Returns an empty list on any HttpError so the UI
        never 500s because Google rate-limited us mid-paint.
        """
        service = self.get_service(account_name)
        if not service:
            return []

        try:
            response = service.users().messages().list(
                userId="me",
                maxResults=max(1, min(int(max_results), 25)),
                labelIds=["INBOX"],
            ).execute()
            messages = response.get("messages", [])
            return [
                {"id": msg.get("id"), "threadId": msg.get("threadId")}
                for msg in messages
                if msg.get("id")
            ]
        except HttpError as e:
            logger.warning("Gmail list_recent_messages failed for %s: %s", account_name, e)
            return []
        except Exception as e:
            logger.warning("Gmail list_recent_messages unexpected error for %s: %s", account_name, e)
            return []

    # ------------------------------------------------------------------
    # Send + inbox helpers
    # ------------------------------------------------------------------

    def send_email(
        self,
        account_name: str,
        to: str,
        subject: str,
        body_html: str,
        body_text: str = "",
        cc: str = "",
        reply_to_message_id: str = "",
    ) -> dict:
        """Send an email via the Gmail API using the stored OAuth token.

        Returns {"success": True, "message_id": str} on success, or
        {"success": False, "error": str} on failure.
        """
        import base64
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        service = self.get_service(account_name)
        if not service:
            return {"success": False, "error": "no_service"}

        status = self.get_account_status(account_name)
        if not status.get("can_send"):
            return {"success": False, "error": "no_send_scope"}

        try:
            msg = MIMEMultipart("alternative")
            msg["To"] = to
            msg["Subject"] = subject
            if cc:
                msg["Cc"] = cc
            if reply_to_message_id:
                msg["In-Reply-To"] = reply_to_message_id
                msg["References"] = reply_to_message_id

            if body_text:
                msg.attach(MIMEText(body_text, "plain", "utf-8"))
            if body_html:
                msg.attach(MIMEText(body_html, "html", "utf-8"))

            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
            result = service.users().messages().send(
                userId="me", body={"raw": raw}
            ).execute()
            return {"success": True, "message_id": result.get("id", "")}
        except HttpError as e:
            status_code = getattr(getattr(e, "resp", None), "status", "unknown")
            logger.warning("Gmail send_email failed for %s: %s", account_name, e)
            return {"success": False, "error": f"gmail_http_{status_code}"}
        except Exception as e:
            logger.warning("Gmail send_email unexpected error for %s: %s", account_name, e)
            return {"success": False, "error": "send_failed"}

    def _extract_body(self, payload: dict) -> "tuple[str, str]":
        """Extract (plain_text, html) from a Gmail message payload (recursive)."""
        import base64

        plain, html = "", ""
        mime = payload.get("mimeType", "")

        if mime == "text/plain":
            data = payload.get("body", {}).get("data", "")
            if data:
                plain = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
        elif mime == "text/html":
            data = payload.get("body", {}).get("data", "")
            if data:
                html = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
        elif "multipart" in mime:
            for part in payload.get("parts", []):
                p, h = self._extract_body(part)
                plain = plain or p
                html = html or h
        return plain, html

    def list_messages_with_metadata(
        self, account_name: str, max_results: int = 50
    ) -> "list[dict]":
        """Return inbox messages with full headers and snippet.

        Each dict matches the shape expected by templates/app/emails/list.html:
        id, subject, sender, recipients, body_text, body_html, received_at, is_read.
        """
        from datetime import datetime

        service = self.get_service(account_name)
        if not service:
            return []

        try:
            response = service.users().messages().list(
                userId="me",
                maxResults=max(1, min(int(max_results), 50)),
                labelIds=["INBOX"],
            ).execute()
        except Exception as e:
            logger.warning("Gmail list_messages_with_metadata failed for %s: %s", account_name, e)
            return []

        ids = [m["id"] for m in response.get("messages", []) if m.get("id")]
        if not ids:
            return []

        result = []
        for msg_id in ids:
            try:
                msg = service.users().messages().get(
                    userId="me", id=msg_id, format="full"
                ).execute()
            except Exception as e:
                logger.warning("Gmail get message %s failed: %s", msg_id, e)
                continue

            headers = {
                h["name"].lower(): h["value"]
                for h in msg.get("payload", {}).get("headers", [])
            }
            plain, html = self._extract_body(msg.get("payload", {}))
            ts = int(msg.get("internalDate", 0)) / 1000
            result.append({
                "id": msg_id,
                "gmail_message_id": msg_id,
                "subject": headers.get("subject", "(Sem Assunto)"),
                "sender": headers.get("from", ""),
                "recipients": headers.get("to", ""),
                "cc": headers.get("cc", ""),
                "body_text": plain or msg.get("snippet", ""),
                "body_html": html,
                "received_at": datetime.fromtimestamp(ts) if ts else None,
                "is_read": "UNREAD" not in msg.get("labelIds", []),
                "client_id": None,
                "client_first_name": "",
                "client_last_name": "",
                "case_id": None,
                "case_number": None,
                "client_paralegal": "",
            })
        return result

    def get_message(self, account_name: str, message_id: str) -> "dict | None":
        """Fetch a single Gmail message by ID. Returns None on error."""
        from datetime import datetime

        service = self.get_service(account_name)
        if not service:
            return None

        try:
            msg = service.users().messages().get(
                userId="me", id=message_id, format="full"
            ).execute()
        except Exception as e:
            logger.warning("Gmail get_message %s failed: %s", message_id, e)
            return None

        headers = {
            h["name"].lower(): h["value"]
            for h in msg.get("payload", {}).get("headers", [])
        }
        plain, html = self._extract_body(msg.get("payload", {}))
        ts = int(msg.get("internalDate", 0)) / 1000
        return {
            "id": message_id,
            "gmail_message_id": message_id,
            "subject": headers.get("subject", "(Sem Assunto)"),
            "sender": headers.get("from", ""),
            "recipients": headers.get("to", ""),
            "cc": headers.get("cc", ""),
            "body_text": plain or msg.get("snippet", ""),
            "body_html": html,
            "received_at": datetime.fromtimestamp(ts) if ts else None,
            "is_read": "UNREAD" not in msg.get("labelIds", []),
            "client_id": None,
            "client_first_name": "",
            "client_last_name": "",
            "case_id": None,
            "case_number": None,
        }
