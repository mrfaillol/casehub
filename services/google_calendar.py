"""
CaseHub - Google Calendar integration service.

Reads Google events for the calendar overlay and writes CaseHub appointments
as Google Calendar events when an account is connected. Local appointments
remain the source of truth; Google sync is best-effort.
"""
import hashlib
import hmac
import json
import logging
import os
import pickle
import secrets
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from core.feature_flags import is_enabled
from i18n import get_translations
from services.per_org_credentials import (
    DEFAULT_ORG_ID,
    get_org_credentials_dir,
    migrate_legacy_credentials_to_org,
)

logger = logging.getLogger(__name__)


# gmail.send lets the connected OFFICE account send transactional e-mail
# (welcome credentials, etc.) as itself — no SMTP password, no personal mailbox.
# gmail.readonly lets the SAME office token read the INBOX so the /emails tab
# can show the office mailbox without an IMAP app password (ruling
# 2026-06-03-casehub-email-credential-encryption, Option B). Both are appended
# to SCOPES so the ONE reconnect the office does (calendar) widens consent to
# also grant send + read. Calendar scopes are preserved untouched.
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    GMAIL_SEND_SCOPE,
    GMAIL_READONLY_SCOPE,
]

WRITE_SCOPE = "https://www.googleapis.com/auth/calendar.events"
DEFAULT_KNOWN_ACCOUNTS = ("center", "info")
VALID_SEND_UPDATES = {"all", "externalOnly", "none"}
GOOGLE_OAUTH_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
EVENT_DETAIL_MODES = {"details", "neutral"}


def _write_private_text(path: Path, content: str) -> None:
    """Write OAuth material with permissions suitable for refresh tokens/secrets."""
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


def _resolve_path(path_value: str, default_path: Path) -> Path:
    raw = path_value or str(default_path)
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path(settings.BASE_DIR) / path
    return path


def _calendar_token_base_dir() -> Optional[Path]:
    """Optional Calendar-specific token root, preserving per-org subdirectories."""
    token_dir = os.getenv("GOOGLE_CALENDAR_TOKEN_DIR") or getattr(
        settings, "GOOGLE_CALENDAR_TOKEN_DIR", ""
    )
    if not token_dir:
        return None
    base = _resolve_path(token_dir, Path(settings.BASE_DIR) / "credentials")
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(base, 0o700)
    except OSError:
        pass
    return base


def _json_scopes(value: Any) -> set[str]:
    if isinstance(value, str):
        return {scope for scope in value.split() if scope}
    if isinstance(value, list):
        return {str(scope) for scope in value if scope}
    return set()


def hash_channel_token(token: str) -> str:
    """SHA-256 hex digest of a watch channel token.

    The raw channel_token is the bearer secret Google echoes back in
    X-Goog-Channel-Token on every push. We persist ONLY this hash so a DB leak
    cannot be replayed against the webhook. Comparison is constant-time
    (see GoogleCalendarService.validate_channel_token)."""
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


class GoogleCalendarService:
    """Service for Google Calendar OAuth, event reads, and appointment sync.

    Multi-tenant: each org gets isolated token storage in `credentials/org_{id}/`.
    When `org_id` is None, falls back to `DEFAULT_ORG_ID` (legacy single-tenant
    callers stay functional; default-org first call triggers one-shot migration
    of legacy `credentials/token_*.json` → `credentials/org_{DEFAULT}/calendar_token_*.json`).
    """

    def __init__(self, db: Session = None, org_id: int = None, user_id: int = None):
        self.db = db
        self._explicit_org_id = org_id is not None
        self._legacy_token_dir = None
        # Multi-tenant fallback: org_id explicit > caller default. Never fail-hard
        # on None to preserve compatibility with legacy single-tenant call sites.
        self.org_id = int(org_id) if org_id else DEFAULT_ORG_ID
        # Per-USER mode (additive): when user_id is set, calendar tokens are
        # stored/read from credentials/org_{org_id}/users/{user_id}/calendar_token.json
        # instead of the office account slots (center/info). When None (default),
        # behaviour is identical to the legacy per-org flow — office slots untouched.
        self.user_id = int(user_id) if user_id else None

        self.setup_error = ""
        self._token_base_dir = _calendar_token_base_dir()
        try:
            if self._token_base_dir is not None:
                if not self._explicit_org_id and not self.user_id:
                    self.credentials_dir = self._token_base_dir
                    self._legacy_token_dir = self.credentials_dir
                else:
                    self.credentials_dir = self._token_base_dir / f"org_{self.org_id}"
                self.credentials_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                try:
                    os.chmod(self.credentials_dir, 0o700)
                except OSError:
                    pass
            else:
                self.credentials_dir = get_org_credentials_dir(self.org_id)
        except (OSError, ValueError) as e:
            # Surface as setup_error rather than crashing — agenda must keep loading
            # even when token dir is unavailable.
            self.setup_error = "Google Calendar indisponivel: diretorio de tokens sem permissao."
            logger.warning("%s org_id=%s error=%s", self.setup_error, self.org_id, e)
            self.credentials_dir = Path(settings.BASE_DIR) / "credentials" / f"org_{self.org_id}"

        # OAuth client secret JSON is shared across orgs (it's the app's OAuth
        # client identity, NOT a per-tenant token). Lives in `credentials/` parent.
        client_secret_path = os.getenv("GOOGLE_CALENDAR_CREDENTIALS_PATH") or getattr(
            settings, "GOOGLE_CALENDAR_CREDENTIALS_PATH", ""
        )
        if client_secret_path:
            self.client_secrets_file = _resolve_path(
                client_secret_path,
                Path(settings.BASE_DIR) / "credentials" / "google_client_secret.json",
            )
        elif self._legacy_token_dir is not None:
            self.client_secrets_file = self.credentials_dir / "google_client_secret.json"
        else:
            self.client_secrets_file = self.credentials_dir.parent / "google_client_secret.json"

        # First call for the default org migrates legacy single-tenant tokens
        # into `credentials/org_{DEFAULT_ORG_ID}/`. Idempotent — safe to retry.
        if self.org_id == DEFAULT_ORG_ID and not self.setup_error and self._legacy_token_dir is None:
            try:
                if self._token_base_dir is not None:
                    self._migrate_legacy_calendar_tokens_from_base(self._token_base_dir)
                else:
                    migrate_legacy_credentials_to_org(self.org_id)
            except Exception as e:  # noqa: BLE001 — migration must never block service init
                logger.warning("Legacy token migration to org %s skipped: %s", self.org_id, e)

    def _migrate_legacy_calendar_tokens_from_base(self, base_dir: Path) -> None:
        """Copy legacy root token files into this service's per-org token dir."""
        for legacy_name, account_name in (
            ("token_center.json", "center"),
            ("token_info.json", "info"),
        ):
            legacy = base_dir / legacy_name
            target = self.credentials_dir / f"calendar_token_{account_name}.json"
            if not legacy.exists() or target.exists():
                continue
            _write_private_text(target, legacy.read_text(encoding="utf-8"))

    def _ensure_client_secrets_file(self) -> bool:
        """Locate the shared OAuth client secret JSON.

        The OAuth client identity (`google_client_secret.json`) is **not**
        per-tenant — it is the application's identity with Google. It lives in
        `credentials/` (parent of `credentials/org_{id}/`) and is shared across
        all tenants. We only verify presence here.

        Falls back to the legacy ILC `google_calendar_credentials.json` or the
        consolidated `credentials.json` layout when the canonical file is
        missing, but always materializes the resulting client secret JSON in
        the shared parent directory.
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
            logger.info("Created Google Calendar client secrets file from consolidated legacy credentials")
            return True
        except Exception as e:
            logger.warning("Could not read legacy Google Calendar credentials layout: %s", e)
            return False

    def get_token_file(self, account_name: str) -> str:
        """Get path to token file for this org + account (or per-user).

        Per-USER mode: when this service was constructed with a `user_id`, the
        calendar token lives in the user's own subtree, fully isolated from the
        office account slots. `account_name` is ignored in that mode (the user
        connects a single Google account). Office (center/info) flows that
        construct the service WITHOUT user_id keep the legacy per-org path.
        """
        if self.user_id:
            user_dir = self.credentials_dir / "users" / str(self.user_id)
            user_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                os.chmod(user_dir, 0o700)
                os.chmod(user_dir.parent, 0o700)
            except OSError:
                pass
            return str(user_dir / "calendar_token.json")
        if self._legacy_token_dir is not None:
            safe_account = "".join(c for c in account_name if c.isalnum() or c in ("-", "_"))
            if not safe_account:
                safe_account = "default"
            return str(self._legacy_token_dir / f"token_{safe_account}.json")
        safe_account = "".join(c for c in account_name if c.isalnum() or c in ("-", "_"))
        if not safe_account:
            safe_account = "default"
        return str(self.credentials_dir / f"calendar_token_{safe_account}.json")

    def get_client_redirect_uris(self) -> List[str]:
        """Return authorized redirect URIs declared in the local OAuth client file."""
        if not self._ensure_client_secrets_file():
            return []

        try:
            data = json.loads(self.client_secrets_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Could not read Google Calendar OAuth client file: %s", e)
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

    def _legacy_token_path(self) -> Optional[Path]:
        legacy_path = os.getenv("GOOGLE_CALENDAR_LEGACY_TOKEN_PATH") or getattr(
            settings,
            "GOOGLE_CALENDAR_LEGACY_TOKEN_PATH",
            "",
        )
        if legacy_path:
            return _resolve_path(legacy_path, Path(legacy_path))
        return None

    def _import_legacy_pickle_token(self, account_name: str) -> bool:
        """Import the ILC stable pickle token into the current JSON token format."""
        if account_name != "center":
            return False

        token_file = Path(self.get_token_file(account_name))
        if token_file.exists():
            return False

        legacy_path = self._legacy_token_path()
        if not legacy_path or not legacy_path.exists():
            return False

        try:
            with open(legacy_path, "rb") as handle:
                creds = pickle.load(handle)
            if not isinstance(creds, Credentials):
                logger.warning("Legacy Google Calendar token is not a Credentials object: %s", legacy_path)
                return False
            _write_private_text(token_file, creds.to_json())
            logger.info("Imported legacy Google Calendar pickle token for account %s", account_name)
            return True
        except Exception as e:
            logger.warning("Could not import legacy Google Calendar pickle token: %s", e)
            return False

    def _read_token_json(self, account_name: str) -> dict:
        self._import_legacy_pickle_token(account_name)
        token_file = self.get_token_file(account_name)
        if not os.path.exists(token_file):
            return {}
        try:
            with open(token_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning("Google Calendar token for %s is unreadable: %s", account_name, e)
            return {}

    def _token_needs_reconnect(self, account_name: str) -> bool:
        token_data = self._read_token_json(account_name)
        if not token_data:
            return False
        scopes = _json_scopes(token_data.get("scopes") or token_data.get("scope"))
        return bool(scopes and WRITE_SCOPE not in scopes)

    def get_account_status(self, account_name: str, verify_live: bool = False) -> Dict[str, Any]:
        legacy_imported = self._import_legacy_pickle_token(account_name)
        token_file = self.get_token_file(account_name)
        token_exists = os.path.exists(token_file)
        credentials_file_exists = self._ensure_client_secrets_file()
        needs_reconnect = self._token_needs_reconnect(account_name)
        connected = False
        error = ""
        live_status: Dict[str, Any] = {
            "verified_live": False,
            "calendar_count": 0,
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
                live_status = self.verify_calendar_access(account_name)
                connected = bool(live_status.get("verified_live"))
                if not connected:
                    error = live_status.get("live_error") or "calendar_not_verified"
            elif token_exists and not error:
                error = "calendar_not_verified"

        return {
            "name": account_name,
            "email": self._account_email(account_name),
            "connected": connected,
            "can_write": connected and not needs_reconnect,
            "needs_reconnect": needs_reconnect,
            "token_exists": token_exists,
            "credentials_file_exists": credentials_file_exists,
            "legacy_token_imported": legacy_imported,
            "error": error,
            **live_status,
        }

    def has_credentials(self, account_name: str) -> bool:
        creds = self.get_credentials(account_name)
        return creds is not None and creds.valid

    def get_credentials(self, account_name: str) -> Optional[Credentials]:
        """Get credentials for an account, refreshing if needed."""
        self._import_legacy_pickle_token(account_name)
        token_file = self.get_token_file(account_name)

        if not os.path.exists(token_file) or self._token_needs_reconnect(account_name):
            return None

        try:
            creds = Credentials.from_authorized_user_file(token_file)  # usa os scopes GRANTED do token, não SCOPES expandido (senão refresh de token calendar-only -> invalid_scope ao adicionar gmail.*)

            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                _write_private_text(Path(token_file), creds.to_json())

            return creds if creds and creds.valid else None
        except Exception as e:
            logger.error("Error getting Google Calendar credentials for %s: %s", account_name, e)
            return None

    def get_auth_url(self, account_name: str, redirect_uri: str, state_name: str = None) -> str:
        """Get OAuth2 authorization URL."""
        if not self._ensure_client_secrets_file():
            raise FileNotFoundError(
                "Google client secrets file not found. "
                f"Configure GOOGLE_CALENDAR_CREDENTIALS_PATH or add {self.client_secrets_file}."
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
        """Handle OAuth2 callback and save credentials."""
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
            logger.error("Error handling Google Calendar OAuth callback: %s", e)
            return False

    def get_service(self, account_name: str):
        """Get Google Calendar API service."""
        creds = self.get_credentials(account_name)
        if not creds:
            return None

        return build("calendar", "v3", credentials=creds)

    def verify_calendar_access(self, account_name: str) -> Dict[str, Any]:
        """Verify that a stored token can actually read visible Google calendars."""
        service = self.get_service(account_name)
        if not service:
            return {
                "verified_live": False,
                "calendar_count": 0,
                "connected_email": "",
                "live_error": "no_valid_credentials",
            }

        try:
            result = service.calendarList().list(maxResults=10).execute()
            items = result.get("items", [])
            primary = next((cal for cal in items if cal.get("primary")), None)
            connected_email = ""
            if primary:
                connected_email = primary.get("id") or ""
            elif items:
                connected_email = items[0].get("id") or ""
            return {
                "verified_live": bool(items),
                "calendar_count": len(items),
                "connected_email": connected_email,
                "live_error": "" if items else "no_calendars_visible",
            }
        except HttpError as e:
            status = getattr(getattr(e, "resp", None), "status", "unknown")
            logger.warning("Google Calendar live verification failed for %s: %s", account_name, e)
            return {
                "verified_live": False,
                "calendar_count": 0,
                "connected_email": "",
                "live_error": f"google_http_{status}",
            }
        except Exception as e:
            logger.warning("Google Calendar live verification failed for %s: %s", account_name, e)
            return {
                "verified_live": False,
                "calendar_count": 0,
                "connected_email": "",
                "live_error": "verification_failed",
            }

    # ── Transactional e-mail via Gmail API (office account, OAuth) ──────
    #
    # Sends e-mail AS the connected office account using the gmail.send
    # scope. No SMTP password, no personal mailbox. Org-scoped: only the
    # office account(s) connected for THIS org can send. Best-effort:
    # tokens granted before gmail.send was added return a clear
    # 'needs_gmail_consent' status instead of crashing — Equipe CaseHub reconnects
    # the office account once and consent widens to include send.

    def _account_can_send_email(self, account_name: str) -> bool:
        """True if the stored token for this account carries gmail.send scope."""
        token_data = self._read_token_json(account_name)
        if not token_data:
            return False
        scopes = _json_scopes(token_data.get("scopes") or token_data.get("scope"))
        return GMAIL_SEND_SCOPE in scopes

    def get_email_send_account(self) -> Optional[str]:
        """Pick a connected office account whose token can send Gmail.

        Prefers the default write account when it already has gmail.send;
        otherwise returns the first connected account that does. Returns
        None when an account is connected but none has the send scope yet
        (callers map that to needs_gmail_consent)."""
        preferred = self.get_default_write_account()
        if preferred and self._account_can_send_email(preferred):
            return preferred
        for account in self.default_accounts():
            if self.has_credentials(account) and self._account_can_send_email(account):
                return account
        return None

    def send_email_as_office(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a transactional e-mail via the office Gmail account (OAuth).

        Returns a status dict. NEVER raises and NEVER logs token material.
        Statuses:
          {'success': True, 'account': '<acct>', 'from': '<email>', 'id': '<msgid>'}
          {'success': False, 'error': 'needs_gmail_consent'}   # reconnect office acct
          {'success': False, 'error': 'google_calendar_not_connected'}
          {'success': False, 'error': 'invalid_recipient'|'send_failed'|...}
        """
        import base64
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        # Header-injection guard (parity with EmailService._validate_email_input).
        if not to_email or "\n" in to_email or "\r" in to_email:
            return {"success": False, "error": "invalid_recipient"}
        if "\n" in (subject or "") or "\r" in (subject or ""):
            return {"success": False, "error": "invalid_subject"}

        connected = [a for a in self.default_accounts() if self.has_credentials(a)]
        if not connected:
            return {"success": False, "error": "google_calendar_not_connected"}

        account = account_name or self.get_email_send_account()
        if not account or not self._account_can_send_email(account):
            # Office account connected for calendar, but token predates the
            # gmail.send scope → Equipe CaseHub must reconnect to widen consent.
            return {"success": False, "error": "needs_gmail_consent"}

        creds = self.get_credentials(account)
        if not creds:
            return {"success": False, "error": "google_calendar_not_connected"}

        from_email = self._account_email(account)
        try:
            mime = MIMEMultipart("alternative")
            mime["Subject"] = subject or ""
            mime["From"] = from_email
            mime["To"] = to_email
            if text_content:
                mime.attach(MIMEText(text_content, "plain", "utf-8"))
            mime.attach(MIMEText(html_content or "", "html", "utf-8"))
            raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii")

            gmail = build("gmail", "v1", credentials=creds)
            sent = gmail.users().messages().send(
                userId="me", body={"raw": raw}
            ).execute()
            return {
                "success": True,
                "account": account,
                "from": from_email,
                "id": sent.get("id", ""),
            }
        except HttpError as e:
            status = getattr(getattr(e, "resp", None), "status", None)
            if status in (401, 403):
                # Scope/grant problem at the API boundary → treat as consent.
                logger.warning(
                    "Gmail send denied (org=%s acct=%s http=%s) — reconnect needed",
                    self.org_id, account, status,
                )
                return {"success": False, "error": "needs_gmail_consent"}
            logger.warning(
                "Gmail send failed org=%s acct=%s http=%s", self.org_id, account, status
            )
            return {"success": False, "error": f"google_http_{status or 'error'}"}
        except Exception as e:  # noqa: BLE001 — best-effort, must never crash caller
            logger.warning("Gmail send error org=%s acct=%s: %s", self.org_id, account, type(e).__name__)
            return {"success": False, "error": "send_failed"}

    # ── Inbox read via Gmail API (office account, OAuth) ────────────────
    #
    # Reads the INBOX of the connected OFFICE account using the
    # gmail.readonly scope carried on the SAME calendar token. No IMAP, no
    # app password (ruling 2026-06-03, Option B). Best-effort: a token that
    # predates gmail.readonly (office not yet reconnected) yields a clear
    # 'needs_gmail_readonly_consent' status — never a crash.

    def _account_can_read_email(self, account_name: str) -> bool:
        """True if the stored token for this account carries gmail.readonly."""
        token_data = self._read_token_json(account_name)
        if not token_data:
            return False
        scopes = _json_scopes(token_data.get("scopes") or token_data.get("scope"))
        return GMAIL_READONLY_SCOPE in scopes

    def get_email_read_account(self) -> Optional[str]:
        """Pick a connected office account whose token can read Gmail.

        Prefers the default write account; otherwise the first connected
        account carrying gmail.readonly. Returns None when an account is
        connected but none has the read scope yet (caller maps that to
        needs_gmail_readonly_consent)."""
        preferred = self.get_default_write_account()
        if preferred and self._account_can_read_email(preferred):
            return preferred
        for account in self.default_accounts():
            if self.has_credentials(account) and self._account_can_read_email(account):
                return account
        return None

    @staticmethod
    def _gmail_header(payload: Dict[str, Any], name: str) -> str:
        for h in (payload.get("headers") or []):
            if str(h.get("name", "")).lower() == name.lower():
                return h.get("value") or ""
        return ""

    @staticmethod
    def _gmail_decode_b64(data: str) -> str:
        import base64
        if not data:
            return ""
        try:
            return base64.urlsafe_b64decode(data.encode("ascii")).decode("utf-8", "replace")
        except Exception:
            return ""

    def _gmail_extract_bodies(self, payload: Dict[str, Any]) -> tuple:
        """Walk a Gmail message payload tree → (text_plain, text_html). Best-effort."""
        text_plain = ""
        text_html = ""
        stack = [payload or {}]
        while stack:
            part = stack.pop()
            if not isinstance(part, dict):
                continue
            mime = part.get("mimeType") or ""
            body = part.get("body") or {}
            data = body.get("data")
            if mime == "text/plain" and data and not text_plain:
                text_plain = self._gmail_decode_b64(data)
            elif mime == "text/html" and data and not text_html:
                text_html = self._gmail_decode_b64(data)
            for child in (part.get("parts") or []):
                stack.append(child)
        return text_plain, text_html

    def fetch_inbox_messages(
        self, account_name: Optional[str] = None, max_results: int = 50
    ) -> Dict[str, Any]:
        """Read recent INBOX messages (with body) via the office OAuth token.

        Returns a status dict. NEVER raises, NEVER logs token material.
        Statuses:
          {'status': 'ok', 'account': '<acct>', 'email': '<addr>', 'messages': [...]}
          {'status': 'needs_gmail_readonly_consent'}   # reconnect office acct
          {'status': 'not_connected'}                  # no office Google account
          {'status': 'error', 'error': 'google_http_<n>'|'fetch_failed'}
        Each message dict: gmail_id, thread_id, message_id (RFC822 Message-ID),
        sender, recipients, cc, subject, date (RFC2822 str), received_at
        (datetime|None), body_text, body_html, snippet.
        """
        connected = [a for a in self.default_accounts() if self.has_credentials(a)]
        if not connected:
            return {"status": "not_connected", "messages": []}

        account = account_name or self.get_email_read_account()
        if not account or not self._account_can_read_email(account):
            # Office account connected for calendar, but token predates the
            # gmail.readonly scope → reconnect needed to widen consent.
            return {"status": "needs_gmail_readonly_consent", "messages": []}

        creds = self.get_credentials(account)
        if not creds:
            return {"status": "not_connected", "messages": []}

        try:
            import email.utils as _eut
            gmail = build("gmail", "v1", credentials=creds)
            try:
                profile = gmail.users().getProfile(userId="me").execute()
                connected_email = profile.get("emailAddress") or self._account_email(account)
            except Exception:
                connected_email = self._account_email(account)

            cap = max(1, min(int(max_results or 50), 50))
            listing = gmail.users().messages().list(
                userId="me", labelIds=["INBOX"], maxResults=cap,
            ).execute()
            ids = [m.get("id") for m in (listing.get("messages") or []) if m.get("id")]

            messages: List[Dict[str, Any]] = []
            for gid in ids:
                try:
                    full = gmail.users().messages().get(
                        userId="me", id=gid, format="full",
                    ).execute()
                except HttpError:
                    continue
                payload = full.get("payload") or {}
                date_hdr = self._gmail_header(payload, "Date")
                received_at = None
                if date_hdr:
                    try:
                        received_at = _eut.parsedate_to_datetime(date_hdr)
                        if received_at and received_at.tzinfo is not None:
                            received_at = received_at.astimezone(timezone.utc).replace(tzinfo=None)
                    except Exception:
                        received_at = None
                text_plain, text_html = self._gmail_extract_bodies(payload)
                messages.append({
                    "gmail_id": gid,
                    "thread_id": full.get("threadId") or "",
                    "message_id": self._gmail_header(payload, "Message-ID"),
                    "sender": self._gmail_header(payload, "From"),
                    "recipients": self._gmail_header(payload, "To"),
                    "cc": self._gmail_header(payload, "Cc"),
                    "subject": self._gmail_header(payload, "Subject"),
                    "date": date_hdr,
                    "received_at": received_at,
                    "body_text": text_plain,
                    "body_html": text_html,
                    "snippet": full.get("snippet") or "",
                })
            return {
                "status": "ok",
                "account": account,
                "email": connected_email,
                "messages": messages,
            }
        except HttpError as e:
            status = getattr(getattr(e, "resp", None), "status", None)
            if status in (401, 403):
                logger.warning(
                    "Gmail inbox read denied (org=%s acct=%s http=%s) — reconnect needed",
                    self.org_id, account, status,
                )
                return {"status": "needs_gmail_readonly_consent", "messages": []}
            logger.warning(
                "Gmail inbox read failed org=%s acct=%s http=%s", self.org_id, account, status
            )
            return {"status": "error", "error": f"google_http_{status or 'error'}", "messages": []}
        except Exception as e:  # noqa: BLE001 — best-effort, must never crash caller
            logger.warning("Gmail inbox read error org=%s acct=%s: %s",
                           self.org_id, account, type(e).__name__)
            return {"status": "error", "error": "fetch_failed", "messages": []}

    def get_calendars(self, account_name: str) -> List[Dict]:
        """Get list of calendars for an account."""
        service = self.get_service(account_name)
        if not service:
            return []

        try:
            calendars = []
            page_token = None

            while True:
                calendar_list = service.calendarList().list(pageToken=page_token).execute()

                for cal in calendar_list.get("items", []):
                    calendars.append({
                        "id": cal["id"],
                        "summary": cal.get("summary", "Unnamed"),
                        "primary": cal.get("primary", False),
                        "backgroundColor": cal.get("backgroundColor", "#4285f4"),
                    })

                page_token = calendar_list.get("nextPageToken")
                if not page_token:
                    break

            return calendars
        except HttpError as e:
            logger.error("Error getting Google Calendar calendars: %s", e)
            return []

    def get_events(
        self,
        account_name: str,
        calendar_id: str = "primary",
        time_min: datetime = None,
        time_max: datetime = None,
        max_results: int = 100,
    ) -> List[Dict]:
        """Get events from a calendar."""
        service = self.get_service(account_name)
        if not service:
            return []

        if not time_min:
            time_min = datetime.utcnow() - timedelta(days=30)
        if not time_max:
            time_max = datetime.utcnow() + timedelta(days=60)

        try:
            events = []
            page_token = None
            time_min_str = self._to_utc_string(time_min)
            time_max_str = self._to_utc_string(time_max)

            while True:
                events_result = service.events().list(
                    calendarId=calendar_id,
                    timeMin=time_min_str,
                    timeMax=time_max_str,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                    pageToken=page_token,
                ).execute()

                for event in events_result.get("items", []):
                    start = event.get("start", {})
                    end = event.get("end", {})
                    all_day = "date" in start

                    events.append({
                        "id": event["id"],
                        "title": event.get("summary", "(No title)"),
                        "start": start.get("date") or start.get("dateTime", ""),
                        "end": end.get("date") or end.get("dateTime", ""),
                        "allDay": all_day,
                        "description": event.get("description", ""),
                        "location": event.get("location", ""),
                        "htmlLink": event.get("htmlLink", ""),
                        "source": account_name,
                        "calendar_id": calendar_id,
                    })

                page_token = events_result.get("nextPageToken")
                if not page_token:
                    break

            return events
        except HttpError as e:
            logger.error("Error getting Google Calendar events: %s", e)
            return []

    def get_all_events(
        self,
        accounts: List[str],
        time_min: datetime = None,
        time_max: datetime = None,
    ) -> List[Dict]:
        """Get events from multiple accounts."""
        all_events = []

        for account in accounts:
            if self.has_credentials(account):
                for calendar_id in self._enabled_calendar_ids(account):
                    events = self.get_events(
                        account,
                        calendar_id=calendar_id,
                        time_min=time_min,
                        time_max=time_max,
                    )
                    all_events.extend(events)

        all_events.sort(key=lambda x: x["start"])
        return all_events

    # ── Two-way sync: import Google → CaseHub ───────────────────────────
    #
    # Push (CaseHub → Google) lives in sync_appointment/create_event/etc.
    # This block adds the missing leg: importing Google events into the
    # `appointments` table as first-class compromissos (origin='google').
    #
    # Anti-loop contract (critical):
    #   (a) A Google event carrying extendedProperties.private.casehub_appointment_id
    #       OR matching an existing appointments.gcal_event_id is an event that
    #       ORIGINATED in CaseHub → light update only, never a duplicate row.
    #   (b) A genuinely new Google event becomes an appointment with
    #       origin='google' + gcal_event_id + google_calendar_id.
    #   (c) origin='google' appointments are NEVER pushed back to Google
    #       (routes/calendar._wants_google_sync skips them) → no echo loop.
    #   (d) Google cancellations (status='cancelled') delete the imported row;
    #       CaseHub deletions already remove the Google event (delete_appointment_event).
    #
    # Incremental: a per-(org, account, calendar) syncToken is persisted in
    # gcal_sync_state. Calendar selection is opt-in: an account starts with only
    # its primary calendar enabled, never every visible calendar.
    # On the first run (or HTTP 410 GONE) we fall back to a -30d..+120d window
    # and re-seed the token. All best-effort: failures never raise to the agenda.

    SYNC_WINDOW_PAST_DAYS = 30
    SYNC_WINDOW_FUTURE_DAYS = 120

    @staticmethod
    def _ensure_sync_schema(db: Session) -> None:
        """Additive, idempotent schema for two-way sync. Safe to call on every
        request (lazy at agenda load). Mirrors routes/tasks._ensure_kanban_schema."""
        bind = db.get_bind()
        dialect = bind.dialect.name if bind is not None else "sqlite"
        ts_type = "TIMESTAMPTZ" if dialect == "postgresql" else "TIMESTAMP"

        def _has_column(table: str, column: str) -> bool:
            if dialect == "postgresql":
                return bool(db.execute(
                    text("""
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = :table AND column_name = :column
                    """),
                    {"table": table, "column": column},
                ).first())
            return any(
                row[1] == column
                for row in db.execute(text(f"PRAGMA table_info({table})")).fetchall()
            )

        additions = [
            # gcal_event_id already exists in the live alpha schema; ADD is
            # guarded by the information_schema check below, so it's a no-op there.
            ("appointments", "gcal_event_id", "VARCHAR(255)"),
            ("appointments", "origin", "VARCHAR(20) DEFAULT 'casehub'"),
            ("appointments", "google_calendar_id", "VARCHAR(255)"),
            ("appointments", "google_calendar_account", "VARCHAR(50)"),
            ("appointments", "gcal_etag", "VARCHAR(255)"),
            ("appointments", "last_synced_at", ts_type),
            ("appointments", "local", "VARCHAR(255)"),
            ("appointments", "pericia_status", "VARCHAR(50)"),
        ]
        for table, column, definition in additions:
            try:
                if not _has_column(table, column):
                    db.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
                    db.commit()
            except Exception:
                db.rollback()
        # Per-(org, account, calendar) incremental syncToken store. Existing
        # two-column PK tables are migrated by copy+swap and their cursor is
        # preserved as the account's primary-calendar cursor.
        try:
            # ADDITIVE per-(org, account, calendar) syncToken store — Council ruling
            # 2026-06-13-t6-gcal-multicalendar-migration (Opção B). The legacy 2-col
            # gcal_sync_state table is left UNTOUCHED (NO DROP/RENAME/ALTER, sem perda
            # de dados em prod org-4); per-calendar cursors live in this sidecar and the
            # account's existing 'primary' cursor is inherited READ-ONLY from the legacy
            # table on first read (ver _get_sync_token). Idempotente (IF NOT EXISTS) e
            # rollback-trivial (DROP TABLE gcal_sync_state_calendar).
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS gcal_sync_state_calendar (
                    org_id INTEGER NOT NULL,
                    account_name VARCHAR(50) NOT NULL,
                    calendar_id VARCHAR(255) NOT NULL DEFAULT 'primary',
                    sync_token TEXT,
                    last_run_at TIMESTAMP,
                    PRIMARY KEY (org_id, account_name, calendar_id)
                )
            """))
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS gcal_calendar_selection (
                    org_id INTEGER NOT NULL,
                    account_name VARCHAR(50) NOT NULL,
                    calendar_id VARCHAR(255) NOT NULL,
                    enabled BOOLEAN DEFAULT TRUE,
                    summary VARCHAR(255),
                    is_write_target BOOLEAN DEFAULT FALSE,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (org_id, account_name, calendar_id)
                )
            """))
            db.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_appointments_gcal_event "
                "ON appointments (org_id, gcal_event_id)"
            ))
            db.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_appointments_gcal_account_calendar "
                "ON appointments (org_id, google_calendar_account, google_calendar_id)"
            ))
            db.commit()
        except Exception:
            db.rollback()

    @staticmethod
    def _clean_calendar_id(calendar_id: Optional[str]) -> str:
        value = str(calendar_id or "").strip()
        if not value or "\x00" in value:
            return ""
        return value[:255]

    @staticmethod
    def _calendar_summary(cal: Dict[str, Any]) -> str:
        return str(cal.get("summary") or cal.get("id") or "Calendario Google")[:255]

    @staticmethod
    def _primary_calendar_id(calendars: List[Dict[str, Any]]) -> str:
        for cal in calendars:
            if cal.get("primary") and cal.get("id"):
                return str(cal.get("id"))[:255]
        return "primary"

    def _selection_rows(self, account_name: str) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            text("""
                SELECT calendar_id, enabled, summary, is_write_target
                FROM gcal_calendar_selection
                WHERE org_id = :o AND account_name = :a
                ORDER BY CASE WHEN is_write_target THEN 0 ELSE 1 END, calendar_id
            """),
            {"o": self.org_id, "a": account_name},
        ).fetchall()
        return [dict(row._mapping) for row in rows]

    def _seed_default_calendar_selection(
        self,
        account_name: str,
        calendars: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        calendars = calendars or []
        primary_id = self._primary_calendar_id(calendars)
        summary = "Primary"
        for cal in calendars:
            if str(cal.get("id") or "") == primary_id:
                summary = self._calendar_summary(cal)
                break
        self.db.execute(
            text("""
                INSERT INTO gcal_calendar_selection
                    (org_id, account_name, calendar_id, enabled, summary, is_write_target, updated_at)
                VALUES (:o, :a, :cid, TRUE, :summary, TRUE, CURRENT_TIMESTAMP)
                ON CONFLICT (org_id, account_name, calendar_id)
                DO UPDATE SET enabled = TRUE, summary = :summary,
                              is_write_target = TRUE, updated_at = CURRENT_TIMESTAMP
            """),
            {"o": self.org_id, "a": account_name, "cid": primary_id, "summary": summary},
        )
        self.db.commit()
        return primary_id

    def get_calendar_selection(self, account_name: str) -> List[Dict[str, Any]]:
        """Return visible calendars plus persisted opt-in/write-target state."""
        if self.db is None:
            return []
        self._ensure_sync_schema(self.db)
        calendars = self.get_calendars(account_name)
        try:
            rows = self._selection_rows(account_name)
            if not rows:
                self._seed_default_calendar_selection(account_name, calendars)
                rows = self._selection_rows(account_name)
        except Exception:
            self.db.rollback()
            rows = []

        selected = {str(row["calendar_id"]): row for row in rows}
        output: List[Dict[str, Any]] = []
        seen = set()
        for cal in calendars:
            cid = self._clean_calendar_id(cal.get("id"))
            if not cid:
                continue
            row = selected.get(cid, {})
            seen.add(cid)
            output.append({
                "id": cid,
                "summary": self._calendar_summary(cal),
                "primary": bool(cal.get("primary")),
                "backgroundColor": cal.get("backgroundColor", "#4285f4"),
                "enabled": bool(row.get("enabled", False)),
                "is_write_target": bool(row.get("is_write_target", False)),
            })
        for cid, row in selected.items():
            if cid in seen:
                continue
            output.append({
                "id": cid,
                "summary": row.get("summary") or cid,
                "primary": cid == "primary",
                "backgroundColor": "#4285f4",
                "enabled": bool(row.get("enabled", False)),
                "is_write_target": bool(row.get("is_write_target", False)),
            })
        return output

    def save_calendar_selection(
        self,
        account_name: str,
        calendar_ids: List[str],
        write_calendar_id: Optional[str] = None,
    ) -> bool:
        """Persist the user's explicit calendar opt-in for one account."""
        if self.db is None:
            return False
        self._ensure_sync_schema(self.db)
        calendars = self.get_calendars(account_name)
        visible = {self._clean_calendar_id(cal.get("id")): cal for cal in calendars}
        selected = []
        for calendar_id in calendar_ids:
            cid = self._clean_calendar_id(calendar_id)
            if not cid:
                continue
            if visible and cid not in visible:
                continue
            if cid not in selected:
                selected.append(cid)
        if not selected:
            return False
        write_id = self._clean_calendar_id(write_calendar_id) or selected[0]
        if write_id not in selected:
            write_id = selected[0]
        source_ids = list(visible.keys()) if visible else selected
        try:
            for cid in source_ids:
                cal = visible.get(cid, {})
                self.db.execute(
                    text("""
                        INSERT INTO gcal_calendar_selection
                            (org_id, account_name, calendar_id, enabled, summary, is_write_target, updated_at)
                        VALUES (:o, :a, :cid, :enabled, :summary, :write, CURRENT_TIMESTAMP)
                        ON CONFLICT (org_id, account_name, calendar_id)
                        DO UPDATE SET enabled = :enabled, summary = :summary,
                                      is_write_target = :write, updated_at = CURRENT_TIMESTAMP
                    """),
                    {
                        "o": self.org_id,
                        "a": account_name,
                        "cid": cid,
                        "enabled": cid in selected,
                        "summary": self._calendar_summary(cal) if cal else cid,
                        "write": cid == write_id,
                    },
                )
            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            return False

    def _enabled_calendar_ids(self, account_name: str) -> List[str]:
        if self.db is None:
            return ["primary"]
        # [deploy gated] T6 secondary-calendar sync (#781, gated by #800).
        # When the flag is OFF (default = current prod behavior) only the
        # 'primary' calendar is read/synced — secondary/non-primary calendar
        # opt-in is never activated. The additive schema (_ensure_sync_schema)
        # still runs everywhere; only the multi-calendar activation is gated.
        if not is_enabled("secondary_calendar_sync"):
            return ["primary"]
        self._ensure_sync_schema(self.db)
        try:
            rows = self._selection_rows(account_name)
            if not rows:
                calendars = self.get_calendars(account_name)
                self._seed_default_calendar_selection(account_name, calendars)
                rows = self._selection_rows(account_name)
            enabled = [str(row["calendar_id"]) for row in rows if row.get("enabled")]
            return enabled or ["primary"]
        except Exception:
            self.db.rollback()
            return ["primary"]

    def get_write_calendar_id(self, account_name: str) -> str:
        if self.db is None:
            return "primary"
        # [deploy gated] T6 secondary-calendar sync (#781, gated by #800).
        # OFF (default) = writes always target the 'primary' calendar, i.e.
        # current prod behavior; a non-primary write target is never honored
        # until the flag is explicitly enabled.
        if not is_enabled("secondary_calendar_sync"):
            return "primary"
        self._ensure_sync_schema(self.db)
        try:
            rows = self._selection_rows(account_name)
            if not rows:
                calendars = self.get_calendars(account_name)
                self._seed_default_calendar_selection(account_name, calendars)
                rows = self._selection_rows(account_name)
            for row in rows:
                if row.get("enabled") and row.get("is_write_target"):
                    return str(row["calendar_id"])
            for row in rows:
                if row.get("enabled"):
                    return str(row["calendar_id"])
        except Exception:
            self.db.rollback()
        return "primary"

    def _get_sync_token(self, account_name: str, calendar_id: str = "primary") -> Optional[str]:
        try:
            row = self.db.execute(
                text("""
                    SELECT sync_token FROM gcal_sync_state_calendar
                    WHERE org_id = :o AND account_name = :a AND calendar_id = :cid
                """),
                {"o": self.org_id, "a": account_name, "cid": calendar_id},
            ).fetchone()
            if row and row[0]:
                return row[0]
        except Exception:
            self.db.rollback()
        # Additive fallback: inherit the account's primary cursor from the legacy
        # 2-col gcal_sync_state table (read-only) so prod sync continues seamlessly
        # without migrating/dropping it. Only for the primary calendar; once a fresh
        # token is saved to the sidecar it takes precedence. Legacy table absent on
        # fresh DBs → handled by except.
        if calendar_id == "primary":
            try:
                row = self.db.execute(
                    text("SELECT sync_token FROM gcal_sync_state WHERE org_id = :o AND account_name = :a"),
                    {"o": self.org_id, "a": account_name},
                ).fetchone()
                return row[0] if row and row[0] else None
            except Exception:
                self.db.rollback()
        return None

    def _save_sync_token(self, account_name: str, calendar_id: str, token: Optional[str]) -> None:
        try:
            self.db.execute(
                text("""
                    INSERT INTO gcal_sync_state_calendar
                        (org_id, account_name, calendar_id, sync_token, last_run_at)
                    VALUES (:o, :a, :cid, :tok, CURRENT_TIMESTAMP)
                    ON CONFLICT (org_id, account_name, calendar_id)
                    DO UPDATE SET sync_token = :tok, last_run_at = CURRENT_TIMESTAMP
                """),
                {"o": self.org_id, "a": account_name, "cid": calendar_id, "tok": token},
            )
            self.db.commit()
        except Exception:
            self.db.rollback()

    @staticmethod
    def _parse_gcal_datetime(node: Dict[str, Any]):
        """Return (date_obj, time_obj|None, all_day_bool) from a Google start/end node."""
        if not node:
            return None, None, False
        raw_date = node.get("date")
        if raw_date:
            try:
                return datetime.fromisoformat(raw_date[:10]).date(), None, True
            except ValueError:
                return None, None, True
        raw_dt = node.get("dateTime")
        if raw_dt:
            try:
                # Normalize trailing Z and offsets; persist wall-clock date+time.
                dt = datetime.fromisoformat(raw_dt.replace("Z", "+00:00"))
                tz_name = settings.DEFAULT_TIMEZONE or "America/Sao_Paulo"
                if dt.tzinfo is not None:
                    try:
                        from zoneinfo import ZoneInfo  # py3.9+
                        dt = dt.astimezone(ZoneInfo(tz_name))
                    except Exception:
                        dt = dt.astimezone()
                    dt = dt.replace(tzinfo=None)
                return dt.date(), dt.time().replace(microsecond=0), False
            except ValueError:
                return None, None, False
        return None, None, False

    def import_events(self, account_name: str) -> Dict[str, Any]:
        """Pull Google events for one connected account into appointments.

        org-scoped, best-effort, anti-loop. Returns a small summary dict;
        never raises (the agenda must keep rendering even if Google is down)."""
        summary = {"account": account_name, "imported": 0, "updated": 0,
                   "cancelled": 0, "skipped_loop": 0, "error": ""}
        if self.db is None:
            summary["error"] = "no_db"
            return summary

        service = self.get_service(account_name)
        if not service:
            summary["error"] = "not_connected"
            return summary

        try:
            self._ensure_sync_schema(self.db)

            calendar_ids = self._enabled_calendar_ids(account_name)
            summary["calendars"] = calendar_ids

            for calendar_id in calendar_ids:
                list_kwargs: Dict[str, Any] = {
                    "calendarId": calendar_id,
                    "singleEvents": True,
                    "maxResults": 250,
                    "showDeleted": True,  # need cancellations to reflect deletes
                }
                sync_token = self._get_sync_token(account_name, calendar_id)
                if sync_token:
                    list_kwargs["syncToken"] = sync_token
                else:
                    now = datetime.utcnow()
                    list_kwargs["timeMin"] = self._to_utc_string(now - timedelta(days=self.SYNC_WINDOW_PAST_DAYS))
                    list_kwargs["timeMax"] = self._to_utc_string(now + timedelta(days=self.SYNC_WINDOW_FUTURE_DAYS))
                    list_kwargs["orderBy"] = "startTime"

                page_token = None
                next_sync_token = None
                while True:
                    if page_token:
                        list_kwargs["pageToken"] = page_token
                    try:
                        resp = service.events().list(**list_kwargs).execute()
                    except HttpError as e:
                        status = getattr(getattr(e, "resp", None), "status", None)
                        if status == 410:
                            # Token expired/invalid: drop only this calendar cursor.
                            self._save_sync_token(account_name, calendar_id, None)
                            summary["error"] = "sync_token_expired_reset"
                            break
                        raise

                    for ev in resp.get("items", []):
                        self._apply_google_event(account_name, calendar_id, ev, summary)

                    page_token = resp.get("nextPageToken")
                    next_sync_token = resp.get("nextSyncToken") or next_sync_token
                    if not page_token:
                        break
                    # syncToken/timeMin are page-1 only; clear time bounds for paging.
                    list_kwargs.pop("syncToken", None)
                    list_kwargs.pop("timeMin", None)
                    list_kwargs.pop("timeMax", None)
                    list_kwargs.pop("orderBy", None)

                if next_sync_token:
                    self._save_sync_token(account_name, calendar_id, next_sync_token)
            self.db.commit()
        except HttpError as e:
            self.db.rollback()
            status = getattr(getattr(e, "resp", None), "status", "error")
            summary["error"] = f"google_http_{status}"
            logger.warning("Google Calendar import failed for org=%s acct=%s: %s",
                           self.org_id, account_name, e)
        except Exception as e:  # noqa: BLE001 — best-effort, must not break agenda
            self.db.rollback()
            summary["error"] = "import_failed"
            logger.warning("Google Calendar import error org=%s acct=%s: %s",
                           self.org_id, account_name, e)
        return summary

    def _apply_google_event(
        self,
        account_name: str,
        calendar_id: str,
        ev: Dict[str, Any],
        summary: Dict[str, Any],
    ) -> None:
        """UPSERT a single Google event into appointments (org-scoped, anti-loop)."""
        gcal_id = ev.get("id")
        if not gcal_id:
            return
        status = ev.get("status")
        ext_private = (ev.get("extendedProperties") or {}).get("private") or {}
        casehub_appt_id = ext_private.get("casehub_appointment_id")

        # Find any existing row tied to this Google event id (org-scoped).
        existing = self.db.execute(
            text("""
                SELECT id, origin FROM appointments
                WHERE org_id = :o AND gcal_event_id = :g
                LIMIT 1
            """),
            {"o": self.org_id, "g": gcal_id},
        ).fetchone()

        # Cancellation from Google: reflect by removing imported rows (origin
        # 'google'). For CaseHub-origin rows we leave the local copy intact —
        # the CaseHub→Google delete path owns that direction; here we just
        # clear the dangling link so we don't keep updating a dead event.
        if status == "cancelled":
            if existing:
                if (existing[1] or "casehub") == "google":
                    self.db.execute(
                        text("DELETE FROM appointments WHERE id = :id AND org_id = :o"),
                        {"id": existing[0], "o": self.org_id},
                    )
                    summary["cancelled"] += 1
                else:
                    self.db.execute(
                        text("UPDATE appointments SET gcal_event_id = NULL, "
                             "google_calendar_account = NULL, google_calendar_id = NULL, "
                             "last_synced_at = CURRENT_TIMESTAMP "
                             "WHERE id = :id AND org_id = :o"),
                        {"id": existing[0], "o": self.org_id},
                    )
            return

        title = (ev.get("summary") or "(Sem titulo)").strip()[:255]
        description = ev.get("description") or None
        location = (ev.get("location") or None)
        if location:
            location = location[:255]
        etag = (ev.get("etag") or "")[:255]
        gcal_calendar_id = self._clean_calendar_id(calendar_id) or "primary"

        s_date, s_time, _all_day = self._parse_gcal_datetime(ev.get("start") or {})
        _e_date, e_time, _ = self._parse_gcal_datetime(ev.get("end") or {})
        if not s_date:
            return  # unusable event (no start) — skip silently

        # (a) Existing Google-origin rows are updated from Google. CaseHub-origin
        # rows are light-updated only, never duplicated or overwritten.
        if existing:
            existing_origin = existing[1] or "casehub"
            if existing_origin == "google":
                self.db.execute(
                    text("""
                        UPDATE appointments
                        SET title = :title, date = :date, time_start = :ts,
                            time_end = :te, notes = :notes, local = :loc,
                            gcal_etag = :etag, google_calendar_id = :cal,
                            google_calendar_account = :acct,
                            last_synced_at = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id AND org_id = :o
                    """),
                    {"title": title, "date": s_date, "ts": s_time, "te": e_time,
                     "notes": description, "loc": location, "etag": etag, "acct": account_name,
                     "cal": gcal_calendar_id, "id": existing[0], "o": self.org_id},
                )
                summary["updated"] += 1
                return
            else:
                self.db.execute(
                    text("""
                        UPDATE appointments
                        SET gcal_etag = :etag, google_calendar_id = :cal,
                            google_calendar_account = :acct,
                            last_synced_at = CURRENT_TIMESTAMP
                        WHERE id = :id AND org_id = :o
                    """),
                    {"etag": etag, "cal": gcal_calendar_id, "acct": account_name,
                     "id": existing[0], "o": self.org_id},
                )
            summary["skipped_loop"] += 1
            return

        if casehub_appt_id:
            # CaseHub event whose gcal_event_id was never stored back: relink.
            try:
                appt_int = int(casehub_appt_id)
            except (TypeError, ValueError):
                summary["skipped_loop"] += 1
                return
            self.db.execute(
                text("""
                    UPDATE appointments
                    SET gcal_event_id = :g, gcal_etag = :etag,
                        google_calendar_id = :cal, google_calendar_account = :acct,
                        last_synced_at = CURRENT_TIMESTAMP
                    WHERE id = :id AND org_id = :o AND gcal_event_id IS NULL
                """),
                {"g": gcal_id, "etag": etag, "cal": gcal_calendar_id, "acct": account_name,
                 "id": appt_int, "o": self.org_id},
            )
            summary["skipped_loop"] += 1
            return

        # (b) Brand-new Google event → import as origin='google' compromisso.
        self.db.execute(
            text("""
                INSERT INTO appointments
                    (org_id, title, type, date, time_start, time_end, notes, local,
                     gcal_event_id, origin, google_calendar_id, google_calendar_account,
                     gcal_etag, last_synced_at)
                VALUES
                    (:o, :title, 'outro', :date, :ts, :te, :notes, :loc,
                     :g, 'google', :cal, :acct, :etag, CURRENT_TIMESTAMP)
            """),
            {"o": self.org_id, "title": title, "date": s_date,
             "ts": s_time, "te": e_time, "notes": description, "loc": location,
             "g": gcal_id, "cal": gcal_calendar_id, "acct": account_name, "etag": etag},
        )
        summary["imported"] += 1

    def import_all_connected(self) -> Dict[str, Any]:
        """Import from every connected default account for this org. Best-effort.

        TODO(per-user calendar, 03/06): also import the logged-in user's own
        connected calendar (per-user token in users/{uid}/calendar_token.json).
        Left out for now to avoid touching the working office two-way sync:
        per-user events would need a per-user service instance
        (GoogleCalendarService(db, org_id, user_id=...)) AND a decision on how
        per-user events tag/dedupe against org-scoped appointment rows
        (gcal_sync_state PK is org_id+account_name; a per-user import must use a
        distinct account_name like f"user_{uid}" to avoid clobbering the office
        sync cursor). Wire only after the office sync regression-tests cover it.
        """
        result = {"accounts": [], "imported": 0, "updated": 0, "cancelled": 0, "skipped_loop": 0}
        for account in self.default_accounts():
            if not self.has_credentials(account):
                continue
            s = self.import_events(account)
            result["accounts"].append(s)
            result["imported"] += s.get("imported", 0)
            result["updated"] += s.get("updated", 0)
            result["cancelled"] += s.get("cancelled", 0)
            result["skipped_loop"] += s.get("skipped_loop", 0)
        return result

    def export_unsynced_appointments(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 20,
        priority_start_date: Optional[date] = None,
        priority_end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Push local CaseHub appointments that still have no Google event id.

        Manual "Sincronizar agora" is the operator backfill path: page-load sync
        only pulls Google -> CaseHub, while this method exports existing local
        rows that predate successful write-sync or were saved while Google was
        unavailable. Google-origin rows are explicitly skipped to preserve the
        anti-loop contract.
        """
        summary = {
            "account": "",
            "candidates": 0,
            "processed": 0,
            "exported": 0,
            "failed": 0,
            "skipped": 0,
            "error": "",
        }
        if self.db is None:
            summary["error"] = "no_db"
            return summary

        account = self.get_default_write_account()
        if not account:
            summary["error"] = "not_connected"
            return summary
        summary["account"] = account

        today = date.today()
        start_date = start_date or (today - timedelta(days=self.SYNC_WINDOW_PAST_DAYS))
        end_date = end_date or (today + timedelta(days=self.SYNC_WINDOW_FUTURE_DAYS))
        priority_start_date = priority_start_date or start_date
        priority_end_date = priority_end_date or end_date
        try:
            limit = max(1, min(int(limit or 20), 50))
        except (TypeError, ValueError):
            limit = 20

        try:
            self._ensure_sync_schema(self.db)
            total = self.db.execute(
                text("""
                    SELECT COUNT(*)
                    FROM appointments
                    WHERE org_id = :org_id
                      AND date BETWEEN :start_date AND :end_date
                      AND gcal_event_id IS NULL
                      AND COALESCE(origin, 'casehub') <> 'google'
                """),
                {
                    "org_id": self.org_id,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            ).scalar() or 0
            rows = self.db.execute(
                text("""
                    SELECT id, title, type, client_name, date, time_start, time_end,
                           is_virtual, notes, local, pericia_status, gcal_event_id,
                           google_calendar_id, google_calendar_account,
                           COALESCE(origin, 'casehub') AS origin
                    FROM appointments
                    WHERE org_id = :org_id
                      AND date BETWEEN :start_date AND :end_date
                      AND gcal_event_id IS NULL
                      AND COALESCE(origin, 'casehub') <> 'google'
                    ORDER BY
                      CASE
                        WHEN date BETWEEN :priority_start_date AND :priority_end_date THEN 0
                        ELSE 1
                      END,
                      date ASC, time_start ASC NULLS LAST, id ASC
                    LIMIT :limit
                """),
                {
                    "org_id": self.org_id,
                    "start_date": start_date,
                    "end_date": end_date,
                    "priority_start_date": priority_start_date,
                    "priority_end_date": priority_end_date,
                    "limit": limit,
                },
            ).fetchall()
        except Exception as e:  # noqa: BLE001 — best-effort, route must stay 200
            self.db.rollback()
            summary["error"] = "query_failed"
            logger.warning("Google Calendar export query failed org=%s: %s", self.org_id, e)
            return summary

        summary["candidates"] = int(total)
        summary["processed"] = len(rows)
        for row in rows:
            appointment = dict(row._mapping)
            if (appointment.get("origin") or "casehub") == "google":
                summary["skipped"] += 1
                continue

            result = self.sync_appointment(appointment, account_name=account)
            event_id = result.get("event_id")
            if result.get("synced") and event_id:
                try:
                    self.db.execute(
                        text("""
                            UPDATE appointments
                            SET gcal_event_id = :event_id,
                                google_calendar_id = :calendar_id,
                                google_calendar_account = :account,
                                last_synced_at = CURRENT_TIMESTAMP,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = :id AND org_id = :org_id
                        """),
                        {
                            "event_id": event_id,
                            "calendar_id": result.get("calendar_id"),
                            "account": result.get("account") or account,
                            "id": appointment.get("id"),
                            "org_id": self.org_id,
                        },
                    )
                    self.db.commit()
                    summary["exported"] += 1
                except Exception as e:  # noqa: BLE001
                    self.db.rollback()
                    summary["failed"] += 1
                    summary["error"] = summary["error"] or "save_failed"
                    logger.warning(
                        "Google Calendar export link save failed org=%s appt=%s: %s",
                        self.org_id,
                        appointment.get("id"),
                        e,
                    )
            else:
                summary["failed"] += 1
                summary["error"] = summary["error"] or result.get("code") or "export_failed"

        return summary

    # ── Realtime push: events.watch / channels.stop (DORMANT, Fase 4) ────
    #
    # Polling (import_all_connected) is the permanent fallback. This block adds
    # the OPTIONAL push leg behind GOOGLE_CALENDAR_WATCH_ENABLED.
    #
    # register_watch() asks Google to POST a lightweight ping to our PUBLIC
    # receiver whenever the connected primary calendar changes. The ping carries
    # NO event data — on receipt we pull authoritative deltas via the SAME
    # import_events() machinery (anti-loop, org-scoped, syncToken). A random
    # channel_token is generated per channel; we store only its SHA-256 hash and
    # hand the raw token to Google so we can authenticate inbound pushes.
    #
    # These helpers are only invoked when the flag is ON (guarded admin action /
    # connect hook). They are NEVER called on the request hot path and never
    # auto-register. Channel id is a fresh uuid4; token is 32 bytes urlsafe.

    @staticmethod
    def watch_enabled() -> bool:
        """Master kill switch for the realtime push path. Default OFF."""
        raw = os.getenv("GOOGLE_CALENDAR_WATCH_ENABLED")
        if raw is not None:
            return raw.strip().lower() in {"1", "true", "yes", "on"}
        return bool(getattr(settings, "GOOGLE_CALENDAR_WATCH_ENABLED", False))

    def _ensure_watch_schema(self) -> None:
        """Idempotent, additive create of gcal_watch_channels.

        Startup _run_pending_migrations already creates this table; this is a
        defensive lazy fallback so the helpers work in smoke/test apps that did
        not run the full migration step. Mirrors _ensure_sync_schema."""
        if self.db is None:
            return
        bind = self.db.get_bind()
        dialect = bind.dialect.name if bind is not None else "sqlite"
        pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if dialect == "sqlite" else "SERIAL PRIMARY KEY"
        now_default = "CURRENT_TIMESTAMP" if dialect == "sqlite" else "NOW()"
        try:
            self.db.execute(text(f"""
                CREATE TABLE IF NOT EXISTS gcal_watch_channels (
                    id {pk},
                    org_id INTEGER NOT NULL,
                    account_name VARCHAR(50) NOT NULL,
                    channel_id VARCHAR(255) NOT NULL,
                    resource_id VARCHAR(512),
                    channel_token_hash VARCHAR(64) NOT NULL,
                    expiration TIMESTAMP,
                    last_message_number BIGINT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT {now_default}
                )
            """))
            self.db.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_gcal_watch_channel_id "
                "ON gcal_watch_channels (channel_id)"
            ))
            self.db.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_gcal_watch_org_account "
                "ON gcal_watch_channels (org_id, account_name)"
            ))
            self.db.commit()
        except Exception:
            self.db.rollback()

    def find_channel(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """Look up a stored watch channel by its (Google-routed) channel_id.

        Returns the row as a dict (org_id authoritative) or None. Never raises:
        the webhook must always be able to answer 200 quickly."""
        if self.db is None or not channel_id:
            return None
        try:
            row = self.db.execute(
                text("""
                    SELECT id, org_id, account_name, channel_id, resource_id,
                           channel_token_hash, last_message_number
                    FROM gcal_watch_channels
                    WHERE channel_id = :cid
                """),
                {"cid": channel_id},
            ).fetchone()
            return dict(row._mapping) if row else None
        except Exception:
            self.db.rollback()
            return None

    @staticmethod
    def validate_channel_token(channel: Dict[str, Any], presented_token: str) -> bool:
        """Constant-time check of the inbound X-Goog-Channel-Token against the
        stored hash. Rejects empty tokens. Used by the webhook receiver."""
        if not channel or not presented_token:
            return False
        stored_hash = str(channel.get("channel_token_hash") or "")
        if not stored_hash:
            return False
        presented_hash = hash_channel_token(presented_token)
        return hmac.compare_digest(presented_hash, stored_hash)

    def mark_channel_message(self, channel_pk: int, message_number: int) -> bool:
        """Atomically advance last_message_number for replay/out-of-order dedupe.

        Returns True when this message is NEW (strictly greater than the stored
        watermark) and the row was advanced; False when it is a replay or an
        out-of-order/older message that must be ignored. The UPDATE ... WHERE
        :n > last_message_number is the atomic guard so concurrent pushes for the
        same channel cannot both pass."""
        if self.db is None or not channel_pk:
            return False
        try:
            result = self.db.execute(
                text("""
                    UPDATE gcal_watch_channels
                    SET last_message_number = :n
                    WHERE id = :pk AND :n > last_message_number
                """),
                {"n": int(message_number), "pk": int(channel_pk)},
            )
            self.db.commit()
            return result.rowcount > 0
        except Exception:
            self.db.rollback()
            return False

    def register_watch(
        self,
        account_name: str,
        webhook_url: str,
        calendar_id: str = "primary",
        ttl_seconds: int = 7 * 24 * 3600,
    ) -> Dict[str, Any]:
        """Register a Google events.watch push channel for one connected account.

        Only meaningful when GOOGLE_CALENDAR_WATCH_ENABLED is ON AND the
        receiver host is domain-verified in GCP. Persists the channel row
        (org-scoped, token stored as hash only). Best-effort: returns a status
        dict, never raises to the caller.

        webhook_url MUST be the absolute https URL of the public receiver
        (e.g. https://<host>/casehub/calendar/gcal-webhook). The caller builds
        it; we never trust a request host here."""
        if not self.watch_enabled():
            return {"ok": False, "error": "watch_disabled"}
        if not webhook_url or not webhook_url.lower().startswith("https://"):
            # Google rejects non-https receivers; fail clearly instead of
            # registering a channel that can never deliver.
            return {"ok": False, "error": "https_webhook_required"}
        service = self.get_service(account_name)
        if not service:
            return {"ok": False, "error": "not_connected"}

        self._ensure_watch_schema()
        channel_id = f"casehub-{uuid.uuid4().hex}"
        channel_token = secrets.token_urlsafe(32)
        expiration_ms = int((datetime.utcnow() + timedelta(seconds=ttl_seconds)).timestamp() * 1000)
        body = {
            "id": channel_id,
            "type": "web_hook",
            "address": webhook_url,
            "token": channel_token,
            "params": {"ttl": str(int(ttl_seconds))},
            "expiration": expiration_ms,
        }
        try:
            resp = service.events().watch(calendarId=calendar_id, body=body).execute()
        except HttpError as e:
            status = getattr(getattr(e, "resp", None), "status", "error")
            logger.warning("events.watch failed org=%s acct=%s http=%s",
                           self.org_id, account_name, status)
            return {"ok": False, "error": f"google_http_{status}"}
        except Exception as e:  # noqa: BLE001 — best-effort
            logger.warning("events.watch error org=%s acct=%s: %s",
                           self.org_id, account_name, type(e).__name__)
            return {"ok": False, "error": "watch_failed"}

        resource_id = str(resp.get("resourceId") or "")[:512]
        exp_raw = resp.get("expiration")
        try:
            expiration_dt = (
                datetime.utcfromtimestamp(int(exp_raw) / 1000) if exp_raw else None
            )
        except (TypeError, ValueError):
            expiration_dt = None
        try:
            self.db.execute(
                text("""
                    INSERT INTO gcal_watch_channels
                        (org_id, account_name, channel_id, resource_id,
                         channel_token_hash, expiration, last_message_number)
                    VALUES (:o, :a, :cid, :rid, :hash, :exp, 0)
                """),
                {
                    "o": self.org_id, "a": account_name, "cid": channel_id,
                    "rid": resource_id, "hash": hash_channel_token(channel_token),
                    "exp": expiration_dt,
                },
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            # The channel exists at Google but we failed to persist it; stop it
            # so we don't leak an un-trackable channel that we can never validate.
            try:
                service.channels().stop(
                    body={"id": channel_id, "resourceId": resource_id}
                ).execute()
            except Exception:
                pass
            return {"ok": False, "error": "persist_failed"}

        return {
            "ok": True,
            "channel_id": channel_id,
            "resource_id": resource_id,
            "expiration": expiration_dt.isoformat() if expiration_dt else None,
        }

    def stop_watch(self, channel_id: str) -> Dict[str, Any]:
        """Stop a previously-registered watch channel and delete its row.

        Looks the channel up by id (org-scoped to THIS service's org), calls
        channels().stop(), then removes the local record. Best-effort."""
        if self.db is None or not channel_id:
            return {"ok": False, "error": "no_db_or_channel"}
        try:
            row = self.db.execute(
                text("""
                    SELECT account_name, resource_id
                    FROM gcal_watch_channels
                    WHERE channel_id = :cid AND org_id = :o
                """),
                {"cid": channel_id, "o": self.org_id},
            ).fetchone()
        except Exception:
            self.db.rollback()
            return {"ok": False, "error": "lookup_failed"}
        if not row:
            return {"ok": False, "error": "channel_not_found"}

        account_name, resource_id = row[0], row[1]
        service = self.get_service(account_name)
        stopped = False
        if service is not None:
            try:
                service.channels().stop(
                    body={"id": channel_id, "resourceId": resource_id or ""}
                ).execute()
                stopped = True
            except Exception as e:  # noqa: BLE001 — best-effort
                logger.warning("channels.stop error org=%s channel=%s: %s",
                               self.org_id, channel_id, type(e).__name__)
        try:
            self.db.execute(
                text("DELETE FROM gcal_watch_channels WHERE channel_id = :cid AND org_id = :o"),
                {"cid": channel_id, "o": self.org_id},
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
        return {"ok": True, "stopped_at_google": stopped}

    def create_event(self, account_name: str, event_body: Dict[str, Any], calendar_id: str = "primary") -> Dict[str, Any]:
        service = self.get_service(account_name)
        if not service:
            raise RuntimeError("google_calendar_not_connected")
        kwargs = {
            "calendarId": calendar_id,
            "body": event_body,
            "sendUpdates": self._send_updates(),
        }
        if self._create_meet_enabled() and event_body.get("conferenceData"):
            kwargs["conferenceDataVersion"] = 1
        return service.events().insert(
            **kwargs,
        ).execute()

    def patch_event(
        self,
        account_name: str,
        event_id: str,
        event_body: Dict[str, Any],
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        service = self.get_service(account_name)
        if not service:
            raise RuntimeError("google_calendar_not_connected")
        kwargs = {
            "calendarId": calendar_id,
            "eventId": event_id,
            "body": event_body,
            "sendUpdates": self._send_updates(),
        }
        if self._create_meet_enabled() and event_body.get("conferenceData"):
            kwargs["conferenceDataVersion"] = 1
        return service.events().patch(
            **kwargs,
        ).execute()

    def update_event(
        self,
        account_name: str,
        event_id: str,
        event_body: Dict[str, Any],
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        return self.patch_event(
            account_name,
            event_id,
            event_body,
            calendar_id=calendar_id,
        )

    def delete_event(self, account_name: str, event_id: str, calendar_id: str = "primary") -> None:
        service = self.get_service(account_name)
        if not service:
            raise RuntimeError("google_calendar_not_connected")
        service.events().delete(
            calendarId=calendar_id,
            eventId=event_id,
            sendUpdates=self._send_updates(),
        ).execute()

    def sync_appointment(self, appointment: Dict[str, Any], account_name: Optional[str] = None) -> Dict[str, Any]:
        """Create or update a Google event for a CaseHub appointment."""
        account = account_name or appointment.get("google_calendar_account") or self.get_default_write_account()
        if not account:
            return {
                "synced": False,
                "code": "google_calendar_not_connected",
                "message": "Google Calendar nao conectado.",
            }

        event_body = self._appointment_event_body(appointment)
        existing_event_id = appointment.get("gcal_event_id")
        calendar_id = (
            self._clean_calendar_id(appointment.get("google_calendar_id"))
            if existing_event_id else ""
        ) or self.get_write_calendar_id(account)

        try:
            if existing_event_id:
                event = self.update_event(account, existing_event_id, event_body, calendar_id=calendar_id)
            else:
                event = self.create_event(account, event_body, calendar_id=calendar_id)
            return {
                "synced": True,
                "account": account,
                "calendar_id": calendar_id,
                "event_id": event.get("id", existing_event_id),
                "htmlLink": event.get("htmlLink", ""),
                "meetLink": event.get("hangoutLink", ""),
            }
        except HttpError as e:
            status = getattr(getattr(e, "resp", None), "status", None)
            if existing_event_id and status == 404:
                try:
                    write_calendar_id = self.get_write_calendar_id(account)
                    event = self.create_event(account, event_body, calendar_id=write_calendar_id)
                    return {
                        "synced": True,
                        "account": account,
                        "calendar_id": write_calendar_id,
                        "event_id": event.get("id"),
                        "htmlLink": event.get("htmlLink", ""),
                        "meetLink": event.get("hangoutLink", ""),
                        "recreated": True,
                    }
                except Exception as recreate_error:
                    logger.warning("Google Calendar recreate failed: %s", recreate_error)
            logger.warning("Google Calendar appointment sync failed: %s", e)
            return {
                "synced": False,
                "code": f"google_http_{status or 'error'}",
                "message": "Compromisso salvo no CaseHub, mas nao sincronizado com Google Calendar.",
            }
        except Exception as e:
            logger.warning("Google Calendar appointment sync failed: %s", e)
            return {
                "synced": False,
                "code": "google_sync_failed",
                "message": "Compromisso salvo no CaseHub, mas nao sincronizado com Google Calendar.",
            }

    def delete_appointment_event(
        self,
        event_id: Optional[str],
        account_name: Optional[str] = None,
        calendar_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Delete a Google event from its stored account/calendar when known."""
        if not event_id:
            return {"synced": False, "code": "no_google_event", "message": ""}

        candidates = []
        stored_calendar_id = self._clean_calendar_id(calendar_id)
        if account_name:
            if self.has_credentials(account_name):
                candidates.append((account_name, stored_calendar_id or "primary"))
        else:
            fallback_calendar_id = stored_calendar_id or "primary"
            for account in self.default_accounts():
                if self.has_credentials(account):
                    candidates.append((account, fallback_calendar_id))

        if not candidates:
            return {
                "synced": False,
                "code": "google_calendar_not_connected",
                "message": "Evento local excluido; Google Calendar nao estava conectado.",
            }

        last_error = None
        for account, target_calendar_id in candidates:
            try:
                self.delete_event(account, event_id, calendar_id=target_calendar_id)
                return {
                    "synced": True,
                    "account": account,
                    "calendar_id": target_calendar_id,
                    "event_id": event_id,
                }
            except HttpError as e:
                status = getattr(getattr(e, "resp", None), "status", None)
                if status == 404:
                    continue
                last_error = e
            except Exception as e:
                last_error = e

        if last_error:
            logger.warning("Google Calendar delete failed: %s", last_error)
        return {
            "synced": False,
            "code": "google_delete_failed",
            "message": "Compromisso excluido no CaseHub; remocao no Google Calendar precisa de revisao.",
        }

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
            creds = Credentials.from_authorized_user_file(token_file)  # usa os scopes GRANTED do token, não SCOPES expandido (senão refresh de token calendar-only -> invalid_scope ao adicionar gmail.*)
        except Exception as e:
            logger.warning("Could not load Google Calendar token for revocation: %s", e)
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
            logger.warning("Google Calendar token revoke returned HTTP %s", e.code)
            return False
        except Exception as e:
            logger.warning("Google Calendar token revoke failed: %s", e)
            return False

    def get_connected_accounts(self, verify_live: bool = False) -> List[Dict]:
        """Get list of known accounts and sanitized connection status."""
        return [self.get_account_status(account, verify_live=verify_live) for account in self.default_accounts()]

    def default_accounts(self) -> List[str]:
        raw = os.getenv("GOOGLE_CALENDAR_DEFAULT_ACCOUNTS") or getattr(settings, "GOOGLE_CALENDAR_DEFAULT_ACCOUNTS", "")
        if raw:
            accounts = [item.strip() for item in raw.split(",") if item.strip()]
            return accounts or list(DEFAULT_KNOWN_ACCOUNTS)
        return list(DEFAULT_KNOWN_ACCOUNTS)

    def get_default_write_account(self) -> Optional[str]:
        for account in self.default_accounts():
            if self.has_credentials(account):
                return account
        return None

    def send_updates(self) -> str:
        raw = os.getenv("GOOGLE_CALENDAR_SEND_UPDATES") or getattr(
            settings,
            "GOOGLE_CALENDAR_SEND_UPDATES",
            "none",
        )
        value = (raw or "none").strip()
        return value if value in VALID_SEND_UPDATES else "none"

    def _send_updates(self) -> str:
        return self.send_updates()

    def create_meet_enabled(self) -> bool:
        raw = os.getenv("GOOGLE_CALENDAR_CREATE_MEET")
        if raw is not None:
            return raw.strip().lower() in {"1", "true", "yes", "on"}
        return bool(getattr(settings, "GOOGLE_CALENDAR_CREATE_MEET", False))

    def _create_meet_enabled(self) -> bool:
        return self.create_meet_enabled()

    def event_detail_mode(self) -> str:
        raw = os.getenv("GOOGLE_CALENDAR_EVENT_DETAIL_MODE") or getattr(
            settings,
            "GOOGLE_CALENDAR_EVENT_DETAIL_MODE",
            "details",
        )
        value = (raw or "details").strip().lower()
        return value if value in EVENT_DETAIL_MODES else "details"

    def _event_detail_mode(self) -> str:
        return self.event_detail_mode()

    def _event_translations(self) -> Dict[str, str]:
        raw = os.getenv("GOOGLE_CALENDAR_EVENT_LANG") or getattr(settings, "GOOGLE_CALENDAR_EVENT_LANG", "pt-BR")
        return get_translations(raw)

    def _event_text(self, key: str, fallback: str) -> str:
        return self._event_translations().get(key, fallback)

    @staticmethod
    def _format_appointment_type(value: str) -> str:
        label = str(value or "").strip().replace("_", " ")
        return " ".join(part[:1].upper() + part[1:] for part in label.split()) if label else ""

    def _account_email(self, account_name: str) -> str:
        if account_name == "center":
            email = settings.ORG_CENTER_EMAIL or settings.GMAIL_CENTER_EMAIL
            if email:
                return email
        if account_name == "info" and settings.ORG_EMAIL:
            return settings.ORG_EMAIL
        org_domain = settings.ORG_DOMAIN or "example.com"
        return f"{account_name}@{org_domain}"

    def _appointment_event_body(self, appointment: Dict[str, Any]) -> Dict[str, Any]:
        appt_date = self._coerce_date(appointment.get("date"))
        start_time = self._coerce_time(appointment.get("time_start"))
        end_time = self._coerce_time(appointment.get("time_end"))
        timezone_name = settings.DEFAULT_TIMEZONE or os.getenv("GOOGLE_CALENDAR_TIMEZONE") or "America/Sao_Paulo"

        title = str(appointment.get("title") or "").strip()
        client_name = str(appointment.get("client_name") or "").strip()
        appointment_type = self._format_appointment_type(str(appointment.get("type") or ""))
        notes = str(appointment.get("notes") or "").strip()
        location = str(appointment.get("local") or appointment.get("location") or "").strip()

        if self._event_detail_mode() == "neutral":
            summary = self._event_text("google_calendar_neutral_title", "Compromisso CaseHub")
            description = self._event_text(
                "google_calendar_neutral_description",
                "Criado pelo CaseHub. Abra o CaseHub para detalhes.",
            )
        else:
            summary = title or appointment_type or self._event_text("google_calendar_default_title", "Agendamento")
            if client_name and client_name.lower() not in summary.lower():
                summary = f"{summary} - {client_name}"

            description_parts = [self._event_text("google_calendar_created_by", "Criado pelo CaseHub.")]
            if client_name:
                description_parts.append(f"{self._event_text('google_calendar_client_label', 'Cliente')}: {client_name}")
            if appointment_type:
                description_parts.append(f"{self._event_text('google_calendar_type_label', 'Tipo')}: {appointment_type}")
            if notes:
                description_parts.append(notes)
            description = "\n".join(description_parts)

        event = {
            "summary": summary,
            "description": description,
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": 30},
                    {"method": "popup", "minutes": 10},
                ],
            },
            "extendedProperties": {
                "private": {
                    "casehub_appointment_id": str(appointment.get("id", "")),
                    "casehub_source": "casehub-lite",
                }
            },
        }

        if start_time:
            start_dt = datetime.combine(appt_date, start_time)
            end_dt = datetime.combine(appt_date, end_time or self._plus_one_hour(start_time))
            event["start"] = {"dateTime": start_dt.isoformat(), "timeZone": timezone_name}
            event["end"] = {"dateTime": end_dt.isoformat(), "timeZone": timezone_name}
        else:
            event["start"] = {"date": appt_date.isoformat()}
            event["end"] = {"date": (appt_date + timedelta(days=1)).isoformat()}

        if location and self._event_detail_mode() != "neutral":
            event["location"] = location[:255]

        if self._create_meet_enabled() and start_time:
            request_id = "casehub-{id}-{day}-{start}".format(
                id=appointment.get("id", "new"),
                day=appt_date.strftime("%Y%m%d"),
                start=start_time.strftime("%H%M"),
            )
            event["conferenceData"] = {
                "createRequest": {
                    "requestId": request_id,
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            }

        return event

    @staticmethod
    def _to_utc_string(dt: datetime) -> str:
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _coerce_date(value: Any) -> date:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str) and value:
            return datetime.fromisoformat(value[:10]).date()
        return date.today()

    @staticmethod
    def _coerce_time(value: Any) -> Optional[time]:
        if isinstance(value, time):
            return value
        if isinstance(value, str) and value:
            value = value.strip()
            try:
                return datetime.strptime(value[:5], "%H:%M").time()
            except ValueError:
                return None
        return None

    @staticmethod
    def _plus_one_hour(value: time) -> time:
        return (datetime.combine(date.today(), value) + timedelta(hours=1)).time()
