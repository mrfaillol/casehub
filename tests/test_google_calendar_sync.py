import json
import pickle
import stat
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace


def _create_minimal_appointments_table(db):
    from sqlalchemy import text

    db.execute(text("DROP TABLE IF EXISTS gcal_calendar_selection"))
    db.execute(text("DROP TABLE IF EXISTS gcal_sync_state_v2"))
    db.execute(text("DROP TABLE IF EXISTS gcal_sync_state_calendar"))
    db.execute(text("DROP TABLE IF EXISTS gcal_sync_state"))
    db.execute(text("DROP TABLE IF EXISTS appointments"))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER NOT NULL,
            title VARCHAR(255),
            type VARCHAR(50),
            client_name VARCHAR(255),
            date DATE,
            time_start TIME,
            time_end TIME,
            is_virtual BOOLEAN DEFAULT FALSE,
            notes TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.commit()


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

    service = GoogleCalendarService()
    status = service.get_account_status("center")
    token_file = Path(service.get_token_file("center"))

    assert status["legacy_token_imported"] is True
    assert token_file.exists()
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
    token_data = json.loads(token_file.read_text(encoding="utf-8"))
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

    user = SimpleNamespace(id=7, email="casehub_team@example.com")
    other_user = SimpleNamespace(id=8, email="other@example.com")
    request = SimpleNamespace(
        headers={"host": "tenanta.casehub.legal"},
        url=SimpleNamespace(scheme="https"),
        base_url="https://tenanta.casehub.legal/",
        state=SimpleNamespace(org_id=4),
    )

    state = _encode_oauth_state("center", user, request)

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
        lambda account, body, calendar_id="primary": created_events.append(body) or {
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


def test_sync_appointment_exports_local_as_google_location(monkeypatch, tmp_path):
    from services.google_calendar import GoogleCalendarService

    created_events = []
    monkeypatch.setenv("GOOGLE_CALENDAR_TOKEN_DIR", str(tmp_path))
    service = GoogleCalendarService()
    monkeypatch.setattr(service, "get_default_write_account", lambda: "center")
    monkeypatch.setattr(
        service,
        "create_event",
        lambda account, body, calendar_id="primary": created_events.append(body) or {"id": "gcal-local"},
    )

    result = service.sync_appointment({
        "id": 77,
        "title": "Pericia",
        "type": "pericia",
        "date": date(2026, 6, 8),
        "time_start": "14:00",
        "local": "IML Belo Horizonte",
    })

    assert result["synced"] is True
    assert created_events[0]["location"] == "IML Belo Horizonte"


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
        lambda account, body, calendar_id="primary": created_events.append(body) or {"id": "gcal-456"},
    )

    result = service.sync_appointment({
        "id": 42,
        "title": "Audiencia",
        "type": "audiencia",
        "client_name": "Cliente Ficticio Alpha",
        "date": date(2026, 5, 4),
        "notes": "Sala virtual",
        "local": "Forum reservado",
    })

    assert result["synced"] is True
    serialized_event = json.dumps(created_events[0], ensure_ascii=False)
    assert created_events[0]["summary"] == "Compromisso CaseHub"
    assert "Cliente Ficticio Alpha" not in serialized_event
    assert "Sala virtual" not in serialized_event
    assert "Forum reservado" not in serialized_event
    assert created_events[0]["extendedProperties"]["private"]["casehub_appointment_id"] == "42"


def test_appointment_type_label_capitalizes_each_word():
    from services.google_calendar import GoogleCalendarService

    assert GoogleCalendarService._format_appointment_type("reuniao_cliente") == "Reuniao Cliente"


def test_disconnect_account_revokes_refresh_token_then_removes_file(monkeypatch, tmp_path):
    from services.google_calendar import GoogleCalendarService

    monkeypatch.setenv("GOOGLE_CALENDAR_TOKEN_DIR", str(tmp_path))
    service = GoogleCalendarService()
    token_file = Path(service.get_token_file("center"))
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


def test_export_unsynced_appointments_pushes_local_rows(db, monkeypatch):
    from sqlalchemy import text
    from services.google_calendar import GoogleCalendarService

    _create_minimal_appointments_table(db)
    service = GoogleCalendarService(db, org_id=4)
    service._ensure_sync_schema(db)
    db.execute(
        text("""
            INSERT INTO appointments
                (org_id, title, type, date, time_start, time_end, origin, gcal_event_id)
            VALUES
                (4, 'Atendimento', 'atendimento', '2026-06-15', '16:00', '17:00', 'casehub', NULL),
                (4, 'Consulta', 'consulta', '2026-06-15', '14:00', '15:00', 'casehub', 'existing-gcal'),
                (4, 'Google importado', 'outro', '2026-06-15', '11:00', '12:00', 'google', NULL),
                (2, 'Outra org', 'outro', '2026-06-15', '10:00', '11:00', 'casehub', NULL)
        """)
    )
    db.commit()

    created = []
    monkeypatch.setattr(service, "get_default_write_account", lambda: "center")
    monkeypatch.setattr(service, "get_write_calendar_id", lambda account: "primary")
    monkeypatch.setattr(
        service,
        "create_event",
        lambda account, body, calendar_id="primary": created.append((account, calendar_id, body)) or {
            "id": "new-gcal",
            "htmlLink": "https://calendar.google.com/event",
        },
    )

    result = service.export_unsynced_appointments(
        start_date=date(2026, 6, 15),
        end_date=date(2026, 6, 15),
    )

    assert result["candidates"] == 1
    assert result["processed"] == 1
    assert result["exported"] == 1
    assert result["failed"] == 0
    assert created[0][0] == "center"
    assert created[0][1] == "primary"
    assert created[0][2]["extendedProperties"]["private"]["casehub_appointment_id"] == "1"
    rows = db.execute(
        text("""
            SELECT id, gcal_event_id, google_calendar_account, google_calendar_id
            FROM appointments
            ORDER BY id
        """)
    ).fetchall()
    assert rows[0] == (1, "new-gcal", "center", "primary")
    assert rows[1][1] == "existing-gcal"
    assert rows[2][1] is None
    assert rows[3][1] is None


def test_export_unsynced_appointments_prioritizes_requested_range(db, monkeypatch):
    from sqlalchemy import text
    from services.google_calendar import GoogleCalendarService

    _create_minimal_appointments_table(db)
    service = GoogleCalendarService(db, org_id=4)
    service._ensure_sync_schema(db)
    db.execute(
        text("""
            INSERT INTO appointments
                (org_id, title, type, date, time_start, time_end, origin, gcal_event_id)
            VALUES
                (4, 'Antigo', 'outro', '2026-06-01', '09:00', '10:00', 'casehub', NULL),
                (4, 'Semana visivel', 'atendimento', '2026-06-15', '16:00', '17:00', 'casehub', NULL)
        """)
    )
    db.commit()

    created = []
    monkeypatch.setattr(service, "get_default_write_account", lambda: "center")
    monkeypatch.setattr(service, "get_write_calendar_id", lambda account: "primary")
    monkeypatch.setattr(
        service,
        "create_event",
        lambda account, body, calendar_id="primary": created.append(body) or {"id": "visible-gcal"},
    )

    result = service.export_unsynced_appointments(
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 30),
        priority_start_date=date(2026, 6, 15),
        priority_end_date=date(2026, 6, 19),
        limit=1,
    )

    assert result["candidates"] == 2
    assert result["processed"] == 1
    assert result["exported"] == 1
    assert created[0]["summary"] == "Semana visivel"


def test_sync_schema_additive_preserves_legacy_and_inherits_primary(db):
    """Opção B (Council 2026-06-13): migração ADITIVA — gcal_sync_state legado fica
    INTOCADO (sem DROP/RENAME/ALTER), o cursor 'primary' é herdado read-only via
    fallback, e a migração é idempotente (re-run não erra nem deixa órfão)."""
    from sqlalchemy import text
    from services.google_calendar import GoogleCalendarService

    _create_minimal_appointments_table(db)
    db.execute(text("""
        CREATE TABLE gcal_sync_state (
            org_id INTEGER NOT NULL,
            account_name VARCHAR(50) NOT NULL,
            sync_token TEXT,
            last_run_at TIMESTAMP,
            PRIMARY KEY (org_id, account_name)
        )
    """))
    db.execute(text("""
        INSERT INTO gcal_sync_state (org_id, account_name, sync_token, last_run_at)
        VALUES (4, 'center', 'legacy-token', CURRENT_TIMESTAMP)
    """))
    db.commit()

    # Idempotente: rodar 2x (G2) — sem erro, sem objeto órfão
    GoogleCalendarService._ensure_sync_schema(db)
    GoogleCalendarService._ensure_sync_schema(db)

    # Legado INTOCADO: nenhuma coluna calendar_id adicionada, token preservado
    columns = [row[1] for row in db.execute(text("PRAGMA table_info(gcal_sync_state)")).fetchall()]
    assert "calendar_id" not in columns
    legacy = db.execute(text(
        "SELECT sync_token FROM gcal_sync_state WHERE org_id = 4 AND account_name = 'center'"
    )).fetchone()
    assert legacy[0] == "legacy-token"

    # Sidecar criado; NENHUM órfão gcal_sync_state_v2
    tables = {r[0] for r in db.execute(
        text("SELECT name FROM sqlite_master WHERE type='table'")
    ).fetchall()}
    assert "gcal_sync_state_calendar" in tables
    assert "gcal_sync_state_v2" not in tables

    # Cursor 'primary' herdado read-only do legado via fallback
    service = GoogleCalendarService(db, org_id=4)
    assert service._get_sync_token("center", "primary") == "legacy-token"

    # Token fresco no sidecar tem precedência; legado continua intocado
    service._save_sync_token("center", "primary", "fresh-token")
    assert service._get_sync_token("center", "primary") == "fresh-token"
    legacy_after = db.execute(text(
        "SELECT sync_token FROM gcal_sync_state WHERE org_id = 4 AND account_name = 'center'"
    )).fetchone()
    assert legacy_after[0] == "legacy-token"


def test_calendar_selection_defaults_to_primary_only(db, monkeypatch):
    from services.google_calendar import GoogleCalendarService

    _create_minimal_appointments_table(db)
    service = GoogleCalendarService(db, org_id=4)
    monkeypatch.setattr(service, "get_calendars", lambda account: [
        {"id": "primary", "summary": "Principal", "primary": True},
        {"id": "shared-family", "summary": "Compartilhada"},
    ])

    selection = service.get_calendar_selection("center")

    by_id = {cal["id"]: cal for cal in selection}
    assert by_id["primary"]["enabled"] is True
    assert by_id["primary"]["is_write_target"] is True
    assert by_id["shared-family"]["enabled"] is False
    assert by_id["shared-family"]["is_write_target"] is False
    assert service._enabled_calendar_ids("center") == ["primary"]


def test_calendar_selection_persists_enabled_and_write_target(db, monkeypatch):
    monkeypatch.setenv("CASEHUB_FF_SECONDARY_CALENDAR_SYNC", "on")  # #803 gate: asserts secondary-cal ON behavior
    from services.google_calendar import GoogleCalendarService

    _create_minimal_appointments_table(db)
    service = GoogleCalendarService(db, org_id=4)
    monkeypatch.setattr(service, "get_calendars", lambda account: [
        {"id": "primary", "summary": "Principal", "primary": True},
        {"id": "team", "summary": "Equipe"},
    ])

    assert service.save_calendar_selection("center", ["primary", "team"], "team") is True

    assert service._enabled_calendar_ids("center") == ["team", "primary"]
    assert service.get_write_calendar_id("center") == "team"
    selection = {cal["id"]: cal for cal in service.get_calendar_selection("center")}
    assert selection["team"]["enabled"] is True
    assert selection["team"]["is_write_target"] is True
    assert selection["primary"]["enabled"] is True
    assert selection["primary"]["is_write_target"] is False


class _FakeGoogleEvents:
    def __init__(self, responses, errors=None):
        self.responses = responses
        self.errors = errors or {}
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        calendar_id = kwargs["calendarId"]
        error = self.errors.get(calendar_id)
        if error:
            return SimpleNamespace(execute=lambda: (_ for _ in ()).throw(error))
        response = self.responses.get(calendar_id, {"items": [], "nextSyncToken": f"tok-{calendar_id}"})
        return SimpleNamespace(execute=lambda: response)


class _FakeGoogleService:
    def __init__(self, events):
        self._events = events

    def events(self):
        return self._events


def _google_event(event_id, title):
    return {
        "id": event_id,
        "summary": title,
        "status": "confirmed",
        "etag": f"etag-{event_id}",
        "start": {"date": "2026-06-20"},
        "end": {"date": "2026-06-21"},
    }


def test_import_events_iterates_enabled_calendars_and_persists_account(db, monkeypatch):
    monkeypatch.setenv("CASEHUB_FF_SECONDARY_CALENDAR_SYNC", "on")  # #803 gate: asserts secondary-cal ON behavior
    from sqlalchemy import text
    from services.google_calendar import GoogleCalendarService

    _create_minimal_appointments_table(db)
    service = GoogleCalendarService(db, org_id=4)
    monkeypatch.setattr(service, "get_calendars", lambda account: [
        {"id": "primary", "summary": "Principal", "primary": True},
        {"id": "team", "summary": "Equipe"},
    ])
    assert service.save_calendar_selection("center", ["primary", "team"], "team") is True
    fake_events = _FakeGoogleEvents({
        "primary": {"items": [_google_event("gcal-primary", "Primary")], "nextSyncToken": "tok-primary"},
        "team": {"items": [_google_event("gcal-team", "Team")], "nextSyncToken": "tok-team"},
    })
    monkeypatch.setattr(service, "get_service", lambda account: _FakeGoogleService(fake_events))

    summary = service.import_events("center")

    assert summary["imported"] == 2
    assert [call["calendarId"] for call in fake_events.calls] == ["team", "primary"]
    rows = db.execute(text("""
        SELECT gcal_event_id, google_calendar_id, google_calendar_account
        FROM appointments
        ORDER BY gcal_event_id
    """)).fetchall()
    assert [tuple(row) for row in rows] == [
        ("gcal-primary", "primary", "center"),
        ("gcal-team", "team", "center"),
    ]
    token_rows = db.execute(text("""
        SELECT calendar_id, sync_token
        FROM gcal_sync_state_calendar
        WHERE org_id = 4 AND account_name = 'center'
        ORDER BY calendar_id
    """)).fetchall()
    assert [tuple(row) for row in token_rows] == [("primary", "tok-primary"), ("team", "tok-team")]


def test_import_events_resets_only_expired_calendar_token(db, monkeypatch):
    monkeypatch.setenv("CASEHUB_FF_SECONDARY_CALENDAR_SYNC", "on")  # #803 gate: asserts secondary-cal ON behavior
    from sqlalchemy import text
    from googleapiclient.errors import HttpError
    from services.google_calendar import GoogleCalendarService

    _create_minimal_appointments_table(db)
    service = GoogleCalendarService(db, org_id=4)
    monkeypatch.setattr(service, "get_calendars", lambda account: [
        {"id": "primary", "summary": "Principal", "primary": True},
        {"id": "team", "summary": "Equipe"},
    ])
    assert service.save_calendar_selection("center", ["primary", "team"], "team") is True
    service._save_sync_token("center", "primary", "old-primary")
    service._save_sync_token("center", "team", "old-team")
    gone = HttpError(SimpleNamespace(status=410, reason="Gone"), b"")
    fake_events = _FakeGoogleEvents(
        {"primary": {"items": [], "nextSyncToken": "new-primary"}},
        errors={"team": gone},
    )
    monkeypatch.setattr(service, "get_service", lambda account: _FakeGoogleService(fake_events))

    summary = service.import_events("center")

    assert summary["error"] == "sync_token_expired_reset"
    tokens = dict(db.execute(text("""
        SELECT calendar_id, sync_token
        FROM gcal_sync_state_calendar
        WHERE org_id = 4 AND account_name = 'center'
    """)).fetchall())
    assert tokens["primary"] == "new-primary"
    assert tokens["team"] is None


def test_sync_appointment_uses_configured_write_calendar(db, monkeypatch):
    monkeypatch.setenv("CASEHUB_FF_SECONDARY_CALENDAR_SYNC", "on")  # #803 gate: asserts secondary-cal ON behavior
    from services.google_calendar import GoogleCalendarService

    _create_minimal_appointments_table(db)
    service = GoogleCalendarService(db, org_id=4)
    monkeypatch.setattr(service, "get_default_write_account", lambda: "center")
    monkeypatch.setattr(service, "get_calendars", lambda account: [
        {"id": "primary", "summary": "Principal", "primary": True},
        {"id": "team", "summary": "Equipe"},
    ])
    assert service.save_calendar_selection("center", ["primary", "team"], "team") is True
    created = []
    monkeypatch.setattr(
        service,
        "create_event",
        lambda account, body, calendar_id="primary": created.append((account, calendar_id, body)) or {"id": "gcal-team"},
    )

    result = service.sync_appointment({
        "id": 99,
        "title": "Reuniao",
        "date": date(2026, 6, 20),
    })

    assert result["synced"] is True
    assert result["calendar_id"] == "team"
    assert created[0][0:2] == ("center", "team")


def test_get_all_events_uses_enabled_calendar_selection(db, monkeypatch):
    monkeypatch.setenv("CASEHUB_FF_SECONDARY_CALENDAR_SYNC", "on")  # #803 gate: asserts secondary-cal ON behavior
    from services.google_calendar import GoogleCalendarService

    _create_minimal_appointments_table(db)
    service = GoogleCalendarService(db, org_id=4)
    monkeypatch.setattr(service, "has_credentials", lambda account: True)
    monkeypatch.setattr(service, "get_calendars", lambda account: [
        {"id": "primary", "summary": "Principal", "primary": True},
        {"id": "team", "summary": "Equipe"},
        {"id": "personal", "summary": "Pessoal"},
    ])
    assert service.save_calendar_selection("center", ["primary", "team"], "team") is True
    calls = []

    def fake_get_events(account, calendar_id="primary", time_min=None, time_max=None, max_results=100):
        calls.append((account, calendar_id))
        return [{
            "id": f"event-{calendar_id}",
            "title": "Evento",
            "start": "2026-06-20",
            "calendar_id": calendar_id,
            "source": account,
        }]

    monkeypatch.setattr(service, "get_events", fake_get_events)

    events = service.get_all_events(["center"])

    assert calls == [("center", "team"), ("center", "primary")]
    assert [event["calendar_id"] for event in events] == ["team", "primary"]


def test_delete_appointment_event_uses_stored_account_and_calendar(db, monkeypatch):
    from services.google_calendar import GoogleCalendarService

    _create_minimal_appointments_table(db)
    service = GoogleCalendarService(db, org_id=4)
    calls = []
    monkeypatch.setattr(service, "has_credentials", lambda account: account == "center")
    monkeypatch.setattr(
        service,
        "delete_event",
        lambda account, event_id, calendar_id="primary": calls.append((account, event_id, calendar_id)),
    )

    result = service.delete_appointment_event(
        "gcal-team",
        account_name="center",
        calendar_id="team",
    )

    assert result["synced"] is True
    assert result["calendar_id"] == "team"
    assert calls == [("center", "gcal-team", "team")]


def test_delete_appointment_event_does_not_fallback_to_primary_when_target_known(db, monkeypatch):
    from googleapiclient.errors import HttpError
    from services.google_calendar import GoogleCalendarService

    _create_minimal_appointments_table(db)
    service = GoogleCalendarService(db, org_id=4)
    calls = []
    not_found = HttpError(SimpleNamespace(status=404, reason="Not Found"), b"")
    monkeypatch.setattr(service, "has_credentials", lambda account: True)
    monkeypatch.setattr(service, "default_accounts", lambda: ["center", "info"])

    def fake_delete(account, event_id, calendar_id="primary"):
        calls.append((account, event_id, calendar_id))
        raise not_found

    monkeypatch.setattr(service, "delete_event", fake_delete)

    result = service.delete_appointment_event(
        "gcal-team",
        account_name="center",
        calendar_id="team",
    )

    assert result["synced"] is False
    assert result["code"] == "google_delete_failed"
    assert calls == [("center", "gcal-team", "team")]


def test_calendar_selection_route_persists_enabled_and_write_target(db, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import google_calendar as route_mod

    captured = {}

    def _get_db_override():
        yield db

    def fake_has_credentials(self, account_name):
        captured["org_id"] = self.org_id
        return account_name == "center"

    def fake_save_selection(self, account_name, calendar_ids, write_calendar_id=None):
        captured["account_name"] = account_name
        captured["calendar_ids"] = calendar_ids
        captured["write_calendar_id"] = write_calendar_id
        return True

    monkeypatch.setattr(
        route_mod,
        "get_current_user",
        lambda request, db: SimpleNamespace(id=7, email="casehub_team@example.com", org_id=4),
    )
    monkeypatch.setattr(route_mod.GoogleCalendarService, "has_credentials", fake_has_credentials)
    monkeypatch.setattr(route_mod.GoogleCalendarService, "save_calendar_selection", fake_save_selection)

    app = FastAPI()

    @app.middleware("http")
    async def add_org_context(request, call_next):
        request.state.org_id = 4
        return await call_next(request)

    app.include_router(route_mod.router, prefix="/casehub")
    app.dependency_overrides[route_mod.get_db] = _get_db_override
    client = TestClient(app)

    response = client.post(
        "/casehub/google-calendar/calendars/center/selection",
        data={"calendar_ids": ["primary", "team"], "write_calendar_id": "team"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith(
        "/casehub/google-calendar/settings?success=calendar_selection_saved"
    )
    assert captured == {
        "org_id": 4,
        "account_name": "center",
        "calendar_ids": ["primary", "team"],
        "write_calendar_id": "team",
    }


def test_manual_sync_endpoint_message_reports_updated_count(db, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import calendar as route_mod

    def _get_db_override():
        yield db

    def fake_import_all_connected(self):
        return {
            "accounts": [{"account": "center"}],
            "imported": 1,
            "updated": 2,
            "cancelled": 3,
            "skipped_loop": 0,
        }

    captured_export = {}

    def fake_export_unsynced_appointments(self, **kwargs):
        captured_export.update(kwargs)
        return {
            "account": "center",
            "candidates": 4,
            "processed": 4,
            "exported": 4,
            "failed": 0,
            "skipped": 0,
            "error": "",
        }

    monkeypatch.setattr(
        route_mod,
        "get_current_user",
        lambda request, db: SimpleNamespace(id=7, email="casehub_team@example.com", org_id=4),
    )
    monkeypatch.setattr(route_mod.GoogleCalendarService, "import_all_connected", fake_import_all_connected)
    monkeypatch.setattr(
        route_mod.GoogleCalendarService,
        "export_unsynced_appointments",
        fake_export_unsynced_appointments,
    )

    app = FastAPI()

    @app.middleware("http")
    async def add_org_context(request, call_next):
        request.state.org_id = 4
        return await call_next(request)

    app.include_router(route_mod.router, prefix="/casehub")
    app.dependency_overrides[route_mod.get_db] = _get_db_override
    client = TestClient(app)

    response = client.post(
        "/casehub/calendar/sync-google?start_date=2026-06-15&end_date=2026-06-19"
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["imported"] == 1
    assert payload["updated"] == 2
    assert payload["cancelled"] == 3
    assert payload["exported"] == 4
    assert payload["export_candidates"] == 4
    assert payload["export_processed"] == 4
    assert payload["export_pending"] == 0
    assert payload["message"] == (
        "Sincronizado: 1 novo(s), 2 atualizado(s), 3 removido(s), "
        "4 enviado(s) ao Google."
    )
    assert captured_export == {
        "priority_start_date": date(2026, 6, 15),
        "priority_end_date": date(2026, 6, 19),
    }


# ── events.watch realtime push (webhook receiver) — DORMANT behind flag ──────

GCAL_WEBHOOK_URL = "/casehub/calendar/gcal-webhook"


def _ensure_watch_table(db):
    """Create gcal_watch_channels in the in-memory test DB (startup migration
    runner does not run for the minimal TestClient app)."""
    from sqlalchemy import text

    db.execute(text("""
        CREATE TABLE IF NOT EXISTS gcal_watch_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER NOT NULL,
            account_name VARCHAR(50) NOT NULL,
            channel_id VARCHAR(255) NOT NULL,
            resource_id VARCHAR(512),
            channel_token_hash VARCHAR(64) NOT NULL,
            expiration TIMESTAMP,
            last_message_number BIGINT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.commit()


def _insert_channel(db, *, org_id, account_name, channel_id, token):
    from sqlalchemy import text
    from services.google_calendar import hash_channel_token

    db.execute(
        text("""
            INSERT INTO gcal_watch_channels
                (org_id, account_name, channel_id, resource_id,
                 channel_token_hash, last_message_number)
            VALUES (:o, :a, :cid, :rid, :h, 0)
        """),
        {"o": org_id, "a": account_name, "cid": channel_id,
         "rid": "res-1", "h": hash_channel_token(token)},
    )
    db.commit()


def _webhook_client(db, monkeypatch, import_calls):
    """Mount the calendar router on a minimal app and stub import_events so no
    Google API is touched. Returns (TestClient)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import calendar as route_mod
    import services.google_calendar as gc_mod

    def _get_db_override():
        yield db

    # Record every per-account import the webhook triggers; never hit Google.
    def _fake_import(self, account_name):
        import_calls.append((self.org_id, account_name))
        return {"account": account_name, "imported": 0}

    monkeypatch.setattr(gc_mod.GoogleCalendarService, "import_events", _fake_import)

    app = FastAPI()
    app.include_router(route_mod.router, prefix="/casehub")
    app.dependency_overrides[route_mod.get_db] = _get_db_override
    return TestClient(app)


def test_webhook_flag_off_is_200_noop(db, monkeypatch):
    monkeypatch.delenv("GOOGLE_CALENDAR_WATCH_ENABLED", raising=False)
    monkeypatch.setattr(
        "config.settings.GOOGLE_CALENDAR_WATCH_ENABLED", False, raising=False
    )
    import_calls = []
    client = _webhook_client(db, monkeypatch, import_calls)

    resp = client.post(GCAL_WEBHOOK_URL, headers={
        "X-Goog-Channel-ID": "casehub-anything",
        "X-Goog-Resource-State": "exists",
        "X-Goog-Channel-Token": "whatever",
        "X-Goog-Message-Number": "1",
    })

    assert resp.status_code == 200
    assert import_calls == []  # flag OFF -> never imports


def test_webhook_unknown_channel_no_import(db, monkeypatch):
    monkeypatch.setenv("GOOGLE_CALENDAR_WATCH_ENABLED", "true")
    _ensure_watch_table(db)
    import_calls = []
    client = _webhook_client(db, monkeypatch, import_calls)

    resp = client.post(GCAL_WEBHOOK_URL, headers={
        "X-Goog-Channel-ID": "casehub-does-not-exist",
        "X-Goog-Resource-State": "exists",
        "X-Goog-Channel-Token": "irrelevant",
        "X-Goog-Message-Number": "1",
    })

    assert resp.status_code == 200
    assert import_calls == []


def test_webhook_valid_channel_sync_handshake_is_noop(db, monkeypatch):
    monkeypatch.setenv("GOOGLE_CALENDAR_WATCH_ENABLED", "true")
    _ensure_watch_table(db)
    _insert_channel(db, org_id=4, account_name="center",
                    channel_id="casehub-ch1", token="tok-secret-1")
    import_calls = []
    client = _webhook_client(db, monkeypatch, import_calls)

    resp = client.post(GCAL_WEBHOOK_URL, headers={
        "X-Goog-Channel-ID": "casehub-ch1",
        "X-Goog-Resource-State": "sync",
        "X-Goog-Channel-Token": "tok-secret-1",
        "X-Goog-Message-Number": "1",
    })

    assert resp.status_code == 200
    assert import_calls == []  # handshake never imports


def test_webhook_valid_exists_imports_once_for_owning_org(db, monkeypatch):
    monkeypatch.setenv("GOOGLE_CALENDAR_WATCH_ENABLED", "true")
    _ensure_watch_table(db)
    _insert_channel(db, org_id=4, account_name="center",
                    channel_id="casehub-ch2", token="tok-secret-2")
    import_calls = []
    client = _webhook_client(db, monkeypatch, import_calls)

    resp = client.post(GCAL_WEBHOOK_URL, headers={
        "X-Goog-Channel-ID": "casehub-ch2",
        "X-Goog-Resource-State": "exists",
        "X-Goog-Channel-Token": "tok-secret-2",
        "X-Goog-Message-Number": "1",
    })

    assert resp.status_code == 200
    assert import_calls == [(4, "center")]  # owning org only, exactly once


def test_webhook_replayed_message_number_ignored(db, monkeypatch):
    monkeypatch.setenv("GOOGLE_CALENDAR_WATCH_ENABLED", "true")
    _ensure_watch_table(db)
    _insert_channel(db, org_id=4, account_name="center",
                    channel_id="casehub-ch3", token="tok-secret-3")
    import_calls = []
    client = _webhook_client(db, monkeypatch, import_calls)

    headers = {
        "X-Goog-Channel-ID": "casehub-ch3",
        "X-Goog-Resource-State": "exists",
        "X-Goog-Channel-Token": "tok-secret-3",
        "X-Goog-Message-Number": "5",
    }
    first = client.post(GCAL_WEBHOOK_URL, headers=headers)
    replay = client.post(GCAL_WEBHOOK_URL, headers=headers)  # same msg number
    older = client.post(GCAL_WEBHOOK_URL, headers={**headers, "X-Goog-Message-Number": "3"})

    assert first.status_code == replay.status_code == older.status_code == 200
    assert import_calls == [(4, "center")]  # only the first (new) message imported


def test_webhook_bad_token_rejected_no_import(db, monkeypatch):
    monkeypatch.setenv("GOOGLE_CALENDAR_WATCH_ENABLED", "true")
    _ensure_watch_table(db)
    _insert_channel(db, org_id=4, account_name="center",
                    channel_id="casehub-ch4", token="tok-secret-4")
    import_calls = []
    client = _webhook_client(db, monkeypatch, import_calls)

    resp = client.post(GCAL_WEBHOOK_URL, headers={
        "X-Goog-Channel-ID": "casehub-ch4",
        "X-Goog-Resource-State": "exists",
        "X-Goog-Channel-Token": "WRONG-token",
        "X-Goog-Message-Number": "1",
    })

    assert resp.status_code == 200  # never leak; stay silent
    assert import_calls == []  # bad token -> no processing


def test_validate_channel_token_is_constant_time_and_rejects_empty():
    from services.google_calendar import GoogleCalendarService, hash_channel_token

    channel = {"channel_token_hash": hash_channel_token("the-secret")}
    assert GoogleCalendarService.validate_channel_token(channel, "the-secret") is True
    assert GoogleCalendarService.validate_channel_token(channel, "nope") is False
    assert GoogleCalendarService.validate_channel_token(channel, "") is False
    assert GoogleCalendarService.validate_channel_token({}, "the-secret") is False
