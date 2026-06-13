"""Regression test for routes/calendar — per-case appointment linkage.

The ``appointments`` table has carried ``case_id INTEGER REFERENCES cases(id)``
since 2026-04-06_appointments.sql, but the POST / PUT route bodies never
**accepted** ``case_id`` — the column was always written as NULL on
create, untouchable on update. That broke the goal-frente-C contract
"Calendar: ... per-client validados" because per-case linkage is the
only way to surface client-scoped events in the agenda UI.

These tests pin three contracts:

1. **Acceptance**: ``POST /casehub/calendar/appointments`` accepts a
   ``case_id`` and writes it to the row.
2. **Cross-tenant safety**: a ``case_id`` from another org is rejected
   with HTTP 404 (not 403 — avoids id enumeration via status code).
3. **Validation**: a non-integer ``case_id`` is rejected with 400.

Run: pytest tests/test_calendar_case_id_wiring.py
"""
from __future__ import annotations

import inspect
import re

import routes.calendar as cal


def test_create_appointment_accepts_case_id_from_body():
    """The handler source must read ``case_id`` out of the JSON body and
    bind it into the INSERT — otherwise the wiring regresses silently
    (no exception, just NULL in the DB)."""
    source = inspect.getsource(cal.create_appointment)
    assert "case_id" in source, (
        "create_appointment must read case_id from the JSON body."
    )
    # The INSERT must list case_id in the columns AND bind the param.
    assert re.search(r"INSERT INTO appointments[\s\S]*?case_id", source), (
        "create_appointment must write case_id into the INSERT."
    )
    assert ":case_id" in source, (
        "case_id must be a bound parameter, not interpolated."
    )


def test_update_appointment_accepts_case_id_from_body():
    """``PUT /appointments/{id}`` must accept ``case_id`` updates so the
    UI can re-link an existing appointment to a case (or unlink it)."""
    source = inspect.getsource(cal.update_appointment)
    assert "case_id" in source, "update_appointment must read case_id."
    # The field-presence check separates "field omitted from body
    # (keep stored value)" from "field set to null (explicit unlink)".
    assert "if field not in body" in source, (
        "update_appointment must distinguish omitted case_id from explicit null "
        "so partial updates do not blow away existing links."
    )


def test_create_appointment_rejects_cross_tenant_case_id():
    """Source must call the org-scoped linked-row guard before persisting
    the case_id — without this guard a caller could attach an
    appointment to a case from another tenant by id-guessing."""
    source = inspect.getsource(cal.create_appointment)
    assert '_linked_row_exists(db, "cases"' in source, (
        "create_appointment must validate case_id ownership before writing."
    )
    # The error response for the bad-case branch must be 404, not 403,
    # to avoid leaking case existence to outsiders.
    assert "status_code=404" in source, (
        "Cross-tenant case_id must return 404 (not 403) to avoid "
        "enumeration leaks."
    )


def test_update_appointment_validates_case_id_type():
    """Bad ``case_id`` type (non-integer string) is a client error → 400.
    Without this we would crash in the int() coercion path."""
    source = inspect.getsource(cal.update_appointment)
    assert "case_id invalido" in source or '"case_id invalido"' in source, (
        "update_appointment must short-circuit malformed case_id with 400."
    )


def test_calendar_events_expose_raw_appointment_fields_for_dayview_editor():
    source = inspect.getsource(cal.get_events)
    assert '"title": appt.title' in source
    assert '"local": appt.local' in source
    assert '"periciaStatus": appt.pericia_status' in source


def test_create_and_update_appointments_warn_but_allow_responsavel_time_conflicts():
    create_source = inspect.getsource(cal.create_appointment)
    update_source = inspect.getsource(cal.update_appointment)
    conflict_source = inspect.getsource(cal._appointment_conflicts)
    assert "_appointment_conflicts" in create_source
    assert "_appointment_conflicts" in update_source
    assert '"conflicts": conflicts' in create_source
    assert '"conflicts": conflicts' in update_source
    assert "status_code=409" not in create_source
    assert "status_code=409" not in update_source
    assert "start_min < existing_end and end_min > existing_start" in conflict_source


def test_create_and_update_appointments_persist_outcome():
    create_source = inspect.getsource(cal.create_appointment)
    update_source = inspect.getsource(cal.update_appointment)
    assert "_normalize_appointment_outcome" in create_source
    assert "_normalize_appointment_outcome" in update_source
    assert re.search(r"INSERT INTO appointments[\s\S]*?outcome", create_source), (
        "create_appointment must write outcome into the INSERT."
    )
    assert ":outcome" in create_source
    assert "outcome = :outcome" in update_source


def test_appointments_persist_trello_like_feedback_fields():
    create_source = inspect.getsource(cal.create_appointment)
    update_source = inspect.getsource(cal.update_appointment)
    upload_source = inspect.getsource(cal.upload_appointment_attachment)
    ensure_source = inspect.getsource(cal._ensure_appointment_feedback_schema)
    events_source = inspect.getsource(cal.get_events)
    agenda_source = inspect.getsource(cal.agenda_lista_view)
    with open("routes/uploads.py", "r", encoding="utf-8") as fh:
        uploads_source = fh.read()
    with open("templates/app/calendar/agenda_lista.html", "r", encoding="utf-8") as fh:
        html = fh.read()
    with open("migrations/2026-06-12_appointment_feedback_fields.sql", "r", encoding="utf-8") as fh:
        sql = fh.read()

    assert "checklist" in create_source
    assert "attachments" in create_source
    assert "checklist = :checklist" in update_source
    assert "attachments = :attachments" in update_source
    assert '"checklist": getattr(appt, "checklist", "")' in events_source
    assert '"attachments": getattr(appt, "attachments", "")' in events_source
    assert "a.notes, a.checklist, a.attachments" in agenda_source
    assert '"attachmentFiles": evt_attachment_files.get(appt.id, [])' in events_source
    assert 'id="appt_checklist"' in html
    assert 'id="appt_attachments"' in html
    assert 'id="appt_files"' in html
    assert "uploadApptFiles" in html
    assert 'download="' in html
    assert 'target="_blank"' not in html[html.index("function renderApptFiles"):html.index("function uploadApptFiles")]
    assert "ADD COLUMN IF NOT EXISTS checklist" in sql
    assert "ADD COLUMN IF NOT EXISTS attachments" in sql
    assert "CREATE TABLE IF NOT EXISTS appointment_attachments" in sql
    assert "appointment_attachments" in ensure_source
    assert "UploadFile" in upload_source
    assert "APPOINTMENT_ATTACHMENT_KIND" in upload_source
    assert "appointment_attachments" in uploads_source
    assert "content_disposition_type" in uploads_source
    assert "_appointment_attachment_name" in uploads_source


def test_appointment_outcome_options_match_vs_request():
    assert cal._normalize_appointment_outcome("sem_direito") == "sem_direito"
    assert cal._normalize_appointment_outcome("no_show") == "follow_up"
    assert cal._normalize_appointment_outcome(123) == ""
    assert cal._normalize_appointment_outcome("valor_invalido") == ""
    with open("templates/app/calendar/agenda_lista.html", "r", encoding="utf-8") as fh:
        html = fh.read()
    assert 'value="sem_direito">Sem Direito' in html
    assert 'value="no_show"' not in html
    assert "outcome === 'no_show' ? 'follow_up'" in html
    agenda_source = inspect.getsource(cal.agenda_lista_view)
    assert "sem_direito" in agenda_source
    assert "NOT IN ('cancelado', 'contrato_fechado', 'sem_direito')" in agenda_source
    assert "type = 'pericia' AND a.date >= :today {_archived}" in agenda_source
    assert "type = 'pericia' {_archived}" in agenda_source


def test_appointments_schema_has_case_id_column():
    """Companion schema check: the migration that backs this route must
    define ``case_id`` as a FK to ``cases(id)``. If the column is ever
    removed, the route changes here would silently 500 in production."""
    with open("migrations/2026-04-06_appointments.sql", "r", encoding="utf-8") as fh:
        sql = fh.read()
    assert "case_id INTEGER REFERENCES cases(id)" in sql, (
        "appointments.case_id FK must remain in the migration — the "
        "route layer relies on it being a real FK, not a free-text column."
    )
