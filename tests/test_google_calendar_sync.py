import json
import pickle
import stat
import time
from datetime import date
from types import SimpleNamespace


def test_readonly_google_calendar_token_requires_reconnect(tmp_path, monkeypatch):
    from services.google_calendar import GoogleCalendarService

    token_dir = tmp_path / "tokens"
    token_dir.mkdir()
    (token_dir / "token_center.json").write_text(
        json.dumps({
            "token": "ya29.test",
            "refresh_token": "refresh",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "client",
            "client_secret": "secret",
            "scopes": ["https://www.googleapis.com/auth/calendar.events.readonly"],
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("GOOGLE_CALENDAR_TOKEN_DIR", str(token_dir))
    monkeypatch.setenv("GOOGLE_CALENDAR_CREDENTIALS_PATH", str(tmp_path / "google_client_secret.json"))

    status = GoogleCalendarService().get_account_status("center")

    assert status["needs_reconnect"] is True
    assert status["connected"] is False
    assert status["can_write"] is False


def test_legacy_ilc_pickle_token_imports_to_json(tmp_path, monkeypatch):
    from google.oauth2.credentials import Credentials
    from services.google_calendar import GoogleCalendarService

    legacy_token = tmp_path / "google_calendar_token.pickle"
    creds = Credentials(
        token="ya29.legacy",
        refresh_token="refresh",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="client",
        client_secret="secret",
        scopes=[
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/calendar.events",
        ],
    )
    with legacy_token.open("wb") as handle:
        pickle.dump(creds, handle)

    token_dir = tmp_path / "tokens"
    token_dir.mkdir()
    monkeypatch.setenv("GOOGLE_CALENDAR_TOKEN_DIR", str(token_dir))
    monkeypatch.setenv("GOOGLE_CALENDAR_LEGACY_TOKEN_PATH", str(legacy_token))

    status = GoogleCalendarService().get_account_status("center")

    assert status["legacy_token_imported"] is True
    assert (token_dir / "token_center.json").exists()
    assert stat.S_IMODE((token_dir / "token_center.json").stat().st_mode) == 0o600
    token_data = json.loads((token_dir / "token_center.json").read_text(encoding="utf-8"))
    assert "https://www.googleapis.com/auth/calendar.events" in token_data["scopes"]


def test_legacy_consolidated_credentials_can_create_client_secret(tmp_path, monkeypatch):
    from services.google_calendar import GoogleCalendarService

    credentials_dir = tmp_path / "credentials"
    credentials_dir.mkdir()
    (credentials_dir / "credentials.json").write_text(
        json.dumps({
            "google_oauth2": {
                "api_1": {
                    "client_id": "legacy-client",
                    "client_secret": "legacy-secret",
                    "redirect_uris": ["http://localhost:8080/"],
                }
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("GOOGLE_CALENDAR_TOKEN_DIR", str(credentials_dir))
    monkeypatch.delenv("GOOGLE_CALENDAR_CREDENTIALS_PATH", raising=False)

    status = GoogleCalendarService().get_account_status("center")

    assert status["credentials_file_exists"] is True
    generated = credentials_dir / "google_client_secret.json"
    assert generated.exists()
    assert stat.S_IMODE(generated.stat().st_mode) == 0o600
    data = json.loads(generated.read_text(encoding="utf-8"))
    assert data["installed"]["client_id"] == "legacy-client"


def test_oauth_state_is_signed_user_bound_and_tamper_rejected():
    from routes.google_calendar import (
        _b64url_encode,
        _decode_oauth_state,
        _encode_oauth_state,
        _oauth_state_signature,
    )

    user = SimpleNamespace(id=7, email="victor@example.com")
    other_user = SimpleNamespace(id=8, email="other@example.com")

    state = _encode_oauth_state("center", user)

    assert _decode_oauth_state(state, user) == "center"
    assert _decode_oauth_state(state, other_user) is None
    assert _decode_oauth_state(state + "x", user) is None
    assert _decode_oauth_state("center", user) is None

    future_payload = {
        "account": "center",
        "uid": user.id,
        "sub": user.email,
        "iat": int(time.time()) + 120,
        "nonce": "future",
    }
    encoded = _b64url_encode(json.dumps(future_payload, separators=(",", ":")).encode("utf-8"))
    future_state = f"{encoded}.{_oauth_state_signature(encoded)}"
    assert _decode_oauth_state(future_state, user) is None


def test_write_private_text_fchmods_before_writing(tmp_path, monkeypatch):
    import services.google_calendar as google_calendar

    events = []
    original_fchmod = google_calendar.os.fchmod
    original_fdopen = google_calendar.os.fdopen

    def fake_fchmod(fd, mode):
        events.append(("fchmod", mode))
        return original_fchmod(fd, mode)

    class GuardedHandle:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return self.handle.__exit__(exc_type, exc, tb)

        def write(self, content):
            assert events == [("fchmod", 0o600)]
            events.append(("write", content))
            return self.handle.write(content)

    def fake_fdopen(fd, *args, **kwargs):
        return GuardedHandle(original_fdopen(fd, *args, **kwargs))

    monkeypatch.setattr(google_calendar.os, "fchmod", fake_fchmod)
    monkeypatch.setattr(google_calendar.os, "fdopen", fake_fdopen)

    target = tmp_path / "token_center.json"
    google_calendar._write_private_text(target, "secret")

    assert events == [("fchmod", 0o600), ("write", "secret")]
    assert target.read_text(encoding="utf-8") == "secret"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_create_event_uses_meet_and_send_updates_when_enabled(monkeypatch, tmp_path):
    from services.google_calendar import GoogleCalendarService

    class FakeExecute:
        def execute(self):
            return {"id": "event-1", "hangoutLink": "https://meet.google.com/demo"}

    class FakeEvents:
        def __init__(self):
            self.kwargs = None

        def insert(self, **kwargs):
            self.kwargs = kwargs
            return FakeExecute()

    class FakeService:
        def __init__(self):
            self.events_obj = FakeEvents()

        def events(self):
            return self.events_obj

    fake_service = FakeService()
    monkeypatch.setenv("GOOGLE_CALENDAR_TOKEN_DIR", str(tmp_path))
    monkeypatch.setenv("GOOGLE_CALENDAR_CREATE_MEET", "true")
    monkeypatch.setenv("GOOGLE_CALENDAR_SEND_UPDATES", "all")
    service = GoogleCalendarService()
    monkeypatch.setattr(service, "get_service", lambda account: fake_service)

    result = service.create_event("center", {
        "summary": "Meeting",
        "conferenceData": {"createRequest": {"requestId": "casehub-1"}},
    })

    assert result["id"] == "event-1"
    assert fake_service.events_obj.kwargs["conferenceDataVersion"] == 1
    assert fake_service.events_obj.kwargs["sendUpdates"] == "all"


def test_sync_appointment_creates_google_event(monkeypatch, tmp_path):
    from services.google_calendar import GoogleCalendarService

    created_events = []
    monkeypatch.setenv("GOOGLE_CALENDAR_TOKEN_DIR", str(tmp_path))
    service = GoogleCalendarService()
    monkeypatch.setattr(service, "get_default_write_account", lambda: "center")
    monkeypatch.setattr(
        service,
        "create_event",
        lambda account, body: created_events.append(body) or {
            "id": "gcal-123",
            "htmlLink": "https://calendar.google.com/event",
        },
    )

    result = service.sync_appointment({
        "id": 42,
        "title": "Audiencia",
        "type": "audiencia",
        "client_name": "Cliente Ficticio Alpha",
        "date": date(2026, 5, 4),
        "time_start": "09:00",
        "time_end": "10:00",
        "notes": "Sala virtual",
    })

    assert result["synced"] is True
    assert result["account"] == "center"
    assert result["event_id"] == "gcal-123"
    assert created_events[0]["summary"] == "Audiencia - Cliente Ficticio Alpha"
    assert created_events[0]["description"] == "Criado pelo CaseHub.\nCliente: Cliente Ficticio Alpha\nTipo: Audiencia\nSala virtual"
    serialized_event = json.dumps(created_events[0], ensure_ascii=False)
    assert "Audiencia" in serialized_event
    assert "Cliente Ficticio Alpha" in serialized_event
    assert "Sala virtual" in serialized_event
    assert created_events[0]["extendedProperties"]["private"]["casehub_appointment_id"] == "42"


def test_sync_appointment_can_use_neutral_google_event_mode(monkeypatch, tmp_path):
    from services.google_calendar import GoogleCalendarService

    created_events = []
    monkeypatch.setenv("GOOGLE_CALENDAR_TOKEN_DIR", str(tmp_path))
    monkeypatch.setenv("GOOGLE_CALENDAR_EVENT_DETAIL_MODE", "neutral")
    service = GoogleCalendarService()
    monkeypatch.setattr(service, "get_default_write_account", lambda: "center")
    monkeypatch.setattr(
        service,
        "create_event",
        lambda account, body: created_events.append(body) or {"id": "gcal-456"},
    )

    result = service.sync_appointment({
        "id": 42,
        "title": "Audiencia",
        "type": "audiencia",
        "client_name": "Cliente Ficticio Alpha",
        "date": date(2026, 5, 4),
        "notes": "Sala virtual",
    })

    assert result["synced"] is True
    serialized_event = json.dumps(created_events[0], ensure_ascii=False)
    assert created_events[0]["summary"] == "Compromisso CaseHub"
    assert "Cliente Ficticio Alpha" not in serialized_event
    assert "Sala virtual" not in serialized_event
    assert created_events[0]["extendedProperties"]["private"]["casehub_appointment_id"] == "42"


def test_appointment_type_label_capitalizes_each_word():
    from services.google_calendar import GoogleCalendarService

    assert GoogleCalendarService._format_appointment_type("reuniao_cliente") == "Reuniao Cliente"


def test_disconnect_account_revokes_refresh_token_then_removes_file(monkeypatch, tmp_path):
    from services.google_calendar import GoogleCalendarService

    monkeypatch.setenv("GOOGLE_CALENDAR_TOKEN_DIR", str(tmp_path))
    token_file = tmp_path / "token_center.json"
    token_file.write_text(
        json.dumps({
            "token": "access-token",
            "refresh_token": "refresh-token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "client",
            "client_secret": "secret",
            "scopes": [
                "https://www.googleapis.com/auth/calendar.readonly",
                "https://www.googleapis.com/auth/calendar.events",
            ],
        }),
        encoding="utf-8",
    )

    service = GoogleCalendarService()
    revoked = []
    monkeypatch.setattr(service, "_revoke_google_token", lambda token: revoked.append(token) or True)

    assert service.disconnect_account("center") is True
    assert revoked == ["refresh-token"]
    assert not token_file.exists()


def test_sync_appointment_is_best_effort_when_no_account(tmp_path, monkeypatch):
    from services.google_calendar import GoogleCalendarService

    monkeypatch.setenv("GOOGLE_CALENDAR_TOKEN_DIR", str(tmp_path))
    service = GoogleCalendarService()
    monkeypatch.setattr(service, "get_default_write_account", lambda: None)

    result = service.sync_appointment({"id": 1, "title": "Reuniao", "date": "2026-05-04"})

    assert result["synced"] is False
    assert result["code"] == "google_calendar_not_connected"
