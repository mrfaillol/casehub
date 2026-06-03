"""Regression tests for routes/whatsapp page handlers — error-path resilience.

The immigration WhatsApp dashboard (`GET /whatsapp`) runs two raw queries
(`whatsapp_messages`, `whatsapp_queue`), each in its own try/except. When a
query fails (table absent in a schema, transient DB error), the handler must
roll back the session: on Postgres a failed statement aborts the transaction,
so the next DB access — get_current_user() inside get_context() — would raise
PendingRollbackError -> HTTP 500. Both except blocks were missing the rollback.

The fake get_current_user below encodes the Postgres aborted-transaction
contract (raise while the session is poisoned) so the test is deterministic
and backend-independent.

Run: pytest tests/test_whatsapp_routes.py
"""
import asyncio

import pytest
from sqlalchemy.exc import OperationalError, PendingRollbackError

import routes.whatsapp as wr


def _install_harness(db, monkeypatch):
    """Patch wr so a failed whatsapp_messages/whatsapp_queue query poisons the
    session and the next get_current_user() raises until rollback() clears it.
    Returns the mutable state dict."""
    state = {"poisoned": False, "rollbacks": 0}

    real_execute = db.execute

    def fake_execute(statement, *args, **kwargs):
        sql = str(statement)
        if "whatsapp_messages" in sql or "whatsapp_queue" in sql:
            state["poisoned"] = True
            raise OperationalError(sql, {}, Exception("no such table"))
        return real_execute(statement, *args, **kwargs)

    real_rollback = db.rollback

    def fake_rollback():
        state["poisoned"] = False
        state["rollbacks"] += 1
        return real_rollback()

    def fake_get_current_user(request, session):
        if state["poisoned"]:
            raise PendingRollbackError(
                "This Session's transaction has been rolled back "
                "due to a previous exception during flush."
            )
        return object()

    class _FakeService:
        def __init__(self, _db):
            pass

        def get_message_stats(self, _days):
            return {"total": 0, "sent": 0, "failed": 0}

    monkeypatch.setattr(db, "execute", fake_execute)
    monkeypatch.setattr(db, "rollback", fake_rollback)
    monkeypatch.setattr(wr, "get_current_user", fake_get_current_user)
    monkeypatch.setattr(wr, "WhatsAppService", _FakeService)
    monkeypatch.setattr(
        wr.templates, "TemplateResponse",
        lambda name, ctx: {"_template": name, **ctx},
    )
    return state


@pytest.fixture
def request_stub(mock_request):
    mock_request.cookies = {}
    return mock_request


def test_whatsapp_dashboard_survives_failed_message_queries(db, monkeypatch, request_stub):
    """whatsapp_dashboard must not 500 when the whatsapp_messages /
    whatsapp_queue queries fail: it rolls back after each, then renders the
    empty/error state. Regression for the two except blocks that swallowed the
    DB error without db.rollback() (get_context -> get_current_user would then
    raise PendingRollbackError)."""
    state = _install_harness(db, monkeypatch)

    result = asyncio.run(wr.whatsapp_dashboard(request_stub, db=db))

    assert isinstance(result, dict)
    assert result["_template"] == "whatsapp/dashboard.html"
    assert result["recent"] == []          # empty state, not a 500
    assert result["queued"] == []
    assert state["rollbacks"] >= 2          # both except paths rolled back
