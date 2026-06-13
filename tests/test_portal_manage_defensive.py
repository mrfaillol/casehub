"""Regression test for routes/portal.manage_portal_access — defensive against
missing portal_access table.

The /casehub/portal/manage handler queried the portal_access table in raw SQL,
but no migration creates that table. On fresh deploys (alpha Mumbai 2026-05)
the table is absent: Postgres raises UndefinedTable -> ProgrammingError,
SQLAlchemy poisons the transaction, the handler turned into an HTTP 500
family. Same defect class as PR #558 (emails rollback).

The route now wraps the query in try/except (OperationalError,
ProgrammingError), rolls the session back, and returns an empty result with
``table_missing=true``. This keeps the route safe to expose without enabling
the portal feature, and once a migration creates ``portal_access`` the route
silently starts returning real data again.

Run: pytest tests/test_portal_manage_defensive.py
"""
import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError, ProgrammingError

import routes.portal as portal


_ORG_ID = 13


def _make_request(org_id=_ORG_ID):
    """Minimal request stub that matches what manage_portal_access reads.

    ``state.org_id`` is the only attribute the handler touches before the DB
    work; we attach it via SimpleNamespace so the missing-table branch can
    short-circuit without touching anything else."""
    request = SimpleNamespace()
    request.state = SimpleNamespace(org_id=org_id)
    request.cookies = {}
    return request


def _patch_auth(monkeypatch, user=object()):
    """Bypass session-auth so the test never depends on auth wiring."""
    monkeypatch.setattr(portal, "get_current_user", lambda req, db: user)


def _run(coro):
    return asyncio.run(coro)


def _install_failing_execute(db, monkeypatch, exc_cls):
    """Replace db.execute with a stub that raises ``exc_cls`` once the
    portal_access query reaches the session — mimics Postgres' real
    UndefinedTable behaviour without needing a real Postgres backend."""
    state = {"rollbacks": 0}
    real_execute = db.execute
    real_rollback = db.rollback

    def fake_execute(statement, *args, **kwargs):
        # The handler issues exactly one SELECT against portal_access; we
        # match on the table name so unrelated execute() calls keep working.
        if "portal_access" in str(statement):
            raise exc_cls(str(statement), {}, Exception("relation \"portal_access\" does not exist"))
        return real_execute(statement, *args, **kwargs)

    def fake_rollback():
        state["rollbacks"] += 1
        return real_rollback()

    monkeypatch.setattr(db, "execute", fake_execute)
    monkeypatch.setattr(db, "rollback", fake_rollback)
    return state


def test_manage_portal_returns_empty_when_table_missing(db, monkeypatch):
    """ProgrammingError on the portal_access SELECT must not 500 — it must
    roll the session back and return ``table_missing=true``."""
    _patch_auth(monkeypatch)
    state = _install_failing_execute(db, monkeypatch, ProgrammingError)

    response = _run(portal.manage_portal_access(_make_request(), db))

    payload = response.body if isinstance(response.body, dict) else None
    # JSONResponse exposes the dict via .body bytes; decode for the assertion.
    import json
    payload = json.loads(response.body)

    assert payload == {
        "total": 0,
        "active": 0,
        "emails_sent": 0,
        "accesses": [],
        "table_missing": True,
    }
    # The session was rolled back exactly once — required so the next ORM
    # query on this request does not raise PendingRollbackError.
    assert state["rollbacks"] == 1


def test_manage_portal_returns_empty_on_operational_error(db, monkeypatch):
    """OperationalError (e.g. dropped connection, table locked) follows the
    same defensive degradation path — empty result + rollback, no 500."""
    _patch_auth(monkeypatch)
    state = _install_failing_execute(db, monkeypatch, OperationalError)

    response = _run(portal.manage_portal_access(_make_request(), db))

    import json
    payload = json.loads(response.body)

    assert payload["table_missing"] is True
    assert payload["accesses"] == []
    assert state["rollbacks"] == 1


def test_manage_portal_redirects_unauthenticated(db, monkeypatch):
    """Sanity guard: the auth branch still wins before the DB path; an
    unauthenticated request must redirect to login, never touch the table."""
    monkeypatch.setattr(portal, "get_current_user", lambda req, db: None)

    response = _run(portal.manage_portal_access(_make_request(), db))

    # RedirectResponse exposes the status code on .status_code and the
    # location on .headers["location"].
    assert response.status_code == 302
    assert "/login" in response.headers["location"]
