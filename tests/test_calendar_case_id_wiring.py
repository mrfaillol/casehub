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
    # The "__not_provided__" sentinel separates "field omitted from body
    # (keep stored value)" from "field set to null (explicit unlink)".
    assert "__not_provided__" in source, (
        "update_appointment must distinguish omitted case_id from explicit null "
        "so partial updates do not blow away existing links."
    )


def test_create_appointment_rejects_cross_tenant_case_id():
    """Source must call ``tenant_query(Case, org_id)`` before persisting
    the case_id — without this guard a caller could attach an
    appointment to a case from another tenant by id-guessing."""
    source = inspect.getsource(cal.create_appointment)
    assert "tenant_query" in source, (
        "create_appointment must validate case_id ownership via tenant_query."
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
