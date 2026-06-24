"""T6 (#781) — automated validation fixture for the secondary/non-primary
Google-Calendar sync, gated behind the default-OFF feature flag
``secondary_calendar_sync`` (env ``CASEHUB_FF_SECONDARY_CALENDAR_SYNC``, #803).

Why this file exists
--------------------
The multi-calendar code (T6) is merged but had NEVER been exercised with the
flag ON in CI, because the gate added in #803 makes every secondary-calendar
path inert by default. We cannot run a live Google validation (no test Google
account with multiple calendars exists), so this fixture drives the *real*
code paths against a MOCKED Google Calendar API:

  * a 'primary' calendar + a secondary 'liga-ops@group.calendar.google.com'
    ("Liga Ops") calendar are visible;
  * the user opts the secondary calendar in and makes it the write target;
  * with the flag FORCED ON we assert the secondary calendar is honored on
    BOTH legs (inbound read import + outbound write target) and is also
    returned by ``_enabled_calendar_ids``;
  * with the flag OFF (control) we assert ONLY 'primary' is honored — i.e.
    the #803 gate genuinely keeps prod on current behavior until opt-in.

The mock is the smallest faithful stub of the googleapiclient service
(``service.events().list(...).execute()``) — the same style as the existing
``tests/test_google_calendar_sync.py`` fakes — so the assertions exercise the
production iteration/selection logic, not test doubles of it.

NOTE (pre-existing, see report): the multi-calendar tests in
``tests/test_google_calendar_sync.py`` were written before #803 and assert the
ON behavior WITHOUT toggling the flag; they now fail under the default-OFF
gate. This file deliberately toggles the flag (monkeypatch) so both ON and OFF
behavior are pinned, which is the missing #781 validation.
"""
from datetime import date
from types import SimpleNamespace

import pytest

from core import feature_flags

FLAG = "secondary_calendar_sync"

# A realistic secondary-calendar id (Google group calendar for "Liga Ops").
LIGA_OPS_CAL = "liga-ops@group.calendar.google.com"


# ── DB scaffolding (mirrors tests/test_google_calendar_sync.py) ──────────────
def _create_minimal_appointments_table(db):
    from sqlalchemy import text

    db.execute(text("DROP TABLE IF EXISTS gcal_calendar_selection"))
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


# ── Mocked Google Calendar API (smallest faithful stub) ──────────────────────
class _FakeGoogleEvents:
    """Stub for ``service.events()``: records every ``list`` call's kwargs and
    returns canned per-calendar responses, exactly like the real API surface
    ``service.events().list(**kwargs).execute()``."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        calendar_id = kwargs["calendarId"]
        response = self.responses.get(
            calendar_id, {"items": [], "nextSyncToken": f"tok-{calendar_id}"}
        )
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


def _two_calendars(_account):
    """primary + the secondary 'Liga Ops' calendar are visible to the account."""
    return [
        {"id": "primary", "summary": "Principal", "primary": True},
        {"id": LIGA_OPS_CAL, "summary": "Liga Ops"},
    ]


def _service_with_secondary_selection(db, monkeypatch):
    """Build a GoogleCalendarService for org 4 whose 'center' account has the
    secondary 'Liga Ops' calendar opted-in AND set as the write target."""
    from services.google_calendar import GoogleCalendarService

    _create_minimal_appointments_table(db)
    service = GoogleCalendarService(db, org_id=4)
    monkeypatch.setattr(service, "get_calendars", _two_calendars)
    # User opts both calendars in; Liga Ops becomes the write target.
    assert service.save_calendar_selection(
        "center", ["primary", LIGA_OPS_CAL], LIGA_OPS_CAL
    ) is True
    return service


@pytest.fixture
def flag_on(monkeypatch):
    """Force the #803 gate ON for the duration of a test (env-var path)."""
    monkeypatch.setenv("CASEHUB_FF_SECONDARY_CALENDAR_SYNC", "on")
    assert feature_flags.is_enabled(FLAG) is True
    yield


@pytest.fixture
def flag_off(monkeypatch):
    """Force the gate OFF (explicit control; also the registry default)."""
    monkeypatch.delenv("CASEHUB_FF_SECONDARY_CALENDAR_SYNC", raising=False)
    assert feature_flags.is_enabled(FLAG) is False
    yield


# ── 1. _enabled_calendar_ids returns BOTH primary + secondary when ON ────────
def test_enabled_calendar_ids_includes_secondary_when_flag_on(db, monkeypatch, flag_on):
    service = _service_with_secondary_selection(db, monkeypatch)

    enabled = service._enabled_calendar_ids("center")

    assert set(enabled) == {"primary", LIGA_OPS_CAL}, (
        "with the flag ON, the opted-in secondary calendar must be synced "
        "alongside primary — not just 'primary'"
    )


# ── 2. OUTBOUND write path targets the selected secondary calendar ───────────
def test_outbound_write_targets_selected_secondary_when_flag_on(db, monkeypatch, flag_on):
    service = _service_with_secondary_selection(db, monkeypatch)
    monkeypatch.setattr(service, "get_default_write_account", lambda: "center")

    # get_write_calendar_id is the single source of truth for the push target.
    assert service.get_write_calendar_id("center") == LIGA_OPS_CAL

    created = []
    monkeypatch.setattr(
        service,
        "create_event",
        lambda account, body, calendar_id="primary": created.append((account, calendar_id))
        or {"id": "gcal-ligaops", "htmlLink": "https://calendar.google.com/x"},
    )

    result = service.sync_appointment({
        "id": 501,
        "title": "Reuniao Liga Ops",
        "date": date(2026, 6, 20),
    })

    assert result["synced"] is True
    assert result["calendar_id"] == LIGA_OPS_CAL
    # The real push hit the secondary calendar, NOT hardcoded 'primary'.
    assert created == [("center", LIGA_OPS_CAL)]


# ── 3. INBOUND read path pulls events from the secondary calendar too ────────
def test_inbound_import_reads_secondary_calendar_when_flag_on(db, monkeypatch, flag_on):
    from sqlalchemy import text

    service = _service_with_secondary_selection(db, monkeypatch)
    fake_events = _FakeGoogleEvents({
        "primary": {"items": [_google_event("ev-primary", "Primary event")],
                    "nextSyncToken": "tok-primary"},
        LIGA_OPS_CAL: {"items": [_google_event("ev-ligaops", "Liga Ops event")],
                       "nextSyncToken": "tok-ligaops"},
    })
    monkeypatch.setattr(service, "get_service", lambda account: _FakeGoogleService(fake_events))

    summary = service.import_events("center")

    # Both calendars were polled (order: write target first, then primary).
    polled = {call["calendarId"] for call in fake_events.calls}
    assert polled == {"primary", LIGA_OPS_CAL}, (
        "inbound import must read the secondary calendar; got only %r" % polled
    )
    assert summary["imported"] == 2

    # The secondary-calendar event landed as an appointment tagged to its calendar.
    rows = dict(db.execute(text("""
        SELECT gcal_event_id, google_calendar_id FROM appointments
    """)).fetchall())
    assert rows.get("ev-ligaops") == LIGA_OPS_CAL, (
        "the event created in the secondary Google calendar did not import "
        "with its calendar id"
    )
    assert rows.get("ev-primary") == "primary"


# ── 4. CONTROL: with the flag OFF, only 'primary' is honored (gate works) ─────
def test_flag_off_collapses_to_primary_only(db, monkeypatch, flag_off):
    service = _service_with_secondary_selection(db, monkeypatch)
    monkeypatch.setattr(service, "get_default_write_account", lambda: "center")

    # Even though a secondary calendar is opted-in + write target in the DB,
    # the #803 gate keeps reads, the enabled set, and writes on 'primary'.
    assert service._enabled_calendar_ids("center") == ["primary"]
    assert service.get_write_calendar_id("center") == "primary"

    fake_events = _FakeGoogleEvents({
        "primary": {"items": [_google_event("ev-primary", "Primary event")],
                    "nextSyncToken": "tok-primary"},
        LIGA_OPS_CAL: {"items": [_google_event("ev-ligaops", "Liga Ops event")],
                       "nextSyncToken": "tok-ligaops"},
    })
    monkeypatch.setattr(service, "get_service", lambda account: _FakeGoogleService(fake_events))

    summary = service.import_events("center")

    polled = {call["calendarId"] for call in fake_events.calls}
    assert polled == {"primary"}, (
        "flag OFF must never poll the secondary calendar (prod-safe gate); "
        "polled %r" % polled
    )
    assert summary["imported"] == 1


# ── 5. is_enabled toggling pattern is honored mid-process ────────────────────
def test_gate_toggle_is_live_per_process_env(db, monkeypatch):
    """Sanity: the same selection state yields secondary-on vs primary-only
    purely from the env flag, proving the gate is the only switch."""
    service = _service_with_secondary_selection(db, monkeypatch)

    monkeypatch.delenv("CASEHUB_FF_SECONDARY_CALENDAR_SYNC", raising=False)
    assert service._enabled_calendar_ids("center") == ["primary"]

    monkeypatch.setenv("CASEHUB_FF_SECONDARY_CALENDAR_SYNC", "1")
    assert set(service._enabled_calendar_ids("center")) == {"primary", LIGA_OPS_CAL}
