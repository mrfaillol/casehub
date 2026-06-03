"""
CaseHub - Google Calendar integration service.

Reads Google events for the calendar overlay and writes CaseHub appointments
as Google Calendar events when an account is connected. Local appointments
remain the source of truth; Google sync is best-effort.
"""
import json
import logging
import os
import pickle
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
from sqlalchemy.orm import Session

from config import settings
from i18n import get_translations
from services.per_org_credentials import (
    DEFAULT_ORG_ID,
    get_org_credentials_dir,
    get_org_token_path,
    migrate_legacy_credentials_to_org,
)

logger = logging.getLogger(__name__)


SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
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


def _json_scopes(value: Any) -> set[str]:
    if isinstance(value, str):
        return {scope for scope in value.split() if scope}
    if isinstance(value, list):
        return {str(scope) for scope in value if scope}
    return set()


class GoogleCalendarService:
    """Service for Google Calendar OAuth, event reads, and appointment sync.

    Multi-tenant: each org gets isolated token storage in `credentials/org_{id}/`.
    When `org_id` is None, falls back to `DEFAULT_ORG_ID` (legacy single-tenant
    callers stay functional; default-org first call triggers one-shot migration
    of legacy `credentials/token_*.json` → `credentials/org_{DEFAULT}/calendar_token_*.json`).
    """

    def __init__(self, db: Session = None, org_id: int = None):
        self.db = db
        # Multi-tenant fallback: org_id explicit > caller default. Never fail-hard
        # on None to preserve compatibility with legacy single-tenant call sites.
        self.org_id = int(org_id) if org_id else DEFAULT_ORG_ID

        self.setup_error = ""
        try:
            self.credentials_dir = get_org_credentials_dir(self.org_id)
        except (OSError, ValueError) as e:
            # Surface as setup_error rather than crashing — agenda must keep loading
            # even when token dir is unavailable.
            self.setup_error = "Google Calendar indisponivel: diretorio de tokens sem permissao."
            logger.warning("%s org_id=%s error=%s", self.setup_error, self.org_id, e)
            self.credentials_dir = Path(settings.BASE_DIR) / "credentials" / f"org_{self.org_id}"

        # OAuth client secret JSON is shared across orgs (it's the app's OAuth
        # client identity, NOT a per-tenant token). Lives in `credentials/` parent.
        self.client_secrets_file = self.credentials_dir.parent / "google_client_secret.json"

        # First call for the default org migrates legacy single-tenant tokens
        # into `credentials/org_{DEFAULT_ORG_ID}/`. Idempotent — safe to retry.
        if self.org_id == DEFAULT_ORG_ID and not self.setup_error:
            try:
                migrate_legacy_credentials_to_org(self.org_id)
            except Exception as e:  # noqa: BLE001 — migration must never block service init
                logger.warning("Legacy token migration to org %s skipped: %s", self.org_id, e)

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
        """Get path to token file for this org + account."""
        return str(get_org_token_path(self.org_id, "calendar", account_name))

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
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)

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
                events = self.get_events(
                    account,
                    calendar_id="primary",
                    time_min=time_min,
                    time_max=time_max,
                )
                all_events.extend(events)

        all_events.sort(key=lambda x: x["start"])
        return all_events

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
        account = account_name or self.get_default_write_account()
        if not account:
            return {
                "synced": False,
                "code": "google_calendar_not_connected",
                "message": "Google Calendar nao conectado.",
            }

        event_body = self._appointment_event_body(appointment)
        existing_event_id = appointment.get("gcal_event_id")

        try:
            if existing_event_id:
                event = self.update_event(account, existing_event_id, event_body)
            else:
                event = self.create_event(account, event_body)
            return {
                "synced": True,
                "account": account,
                "event_id": event.get("id", existing_event_id),
                "htmlLink": event.get("htmlLink", ""),
                "meetLink": event.get("hangoutLink", ""),
            }
        except HttpError as e:
            status = getattr(getattr(e, "resp", None), "status", None)
            if existing_event_id and status == 404:
                try:
                    event = self.create_event(account, event_body)
                    return {
                        "synced": True,
                        "account": account,
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

    def delete_appointment_event(self, event_id: Optional[str]) -> Dict[str, Any]:
        """Delete a Google event from any connected default account."""
        if not event_id:
            return {"synced": False, "code": "no_google_event", "message": ""}

        connected_accounts = [account for account in self.default_accounts() if self.has_credentials(account)]
        if not connected_accounts:
            return {
                "synced": False,
                "code": "google_calendar_not_connected",
                "message": "Evento local excluido; Google Calendar nao estava conectado.",
            }

        last_error = None
        for account in connected_accounts:
            try:
                self.delete_event(account, event_id)
                return {"synced": True, "account": account, "event_id": event_id}
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
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
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
