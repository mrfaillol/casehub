"""Regression tests for routes/whatsapp_lite page handlers.

The Lite dashboard still needs error-path resilience: when the raw
`whatsapp_messages` SELECT fails (table absent in a given schema, transient DB
error), the handler must roll back the session *before* the next ORM query. On
Postgres a failed statement aborts the transaction; any later statement on the
same un-rolled-back session raises PendingRollbackError -> HTTP 500.

The Lite `/mensagens` entry is different: it must redirect to the full
WhatsApp clone instead of rendering a stale dashboard/history surface.

The fake `tenant_query` below encodes that Postgres contract (raise while the
session is poisoned, until rollback clears it), so the test is deterministic
and backend-independent rather than relying on SQLite quirks.

Run: pytest tests/test_whatsapp_lite_routes.py
"""
import asyncio

import pytest
from sqlalchemy.exc import OperationalError, PendingRollbackError

import routes.whatsapp_lite as wl
from models import Client
from models.tenant import Organization

_ORG_ID = 7


def _install_harness(db, monkeypatch):
    """Patch wl so a failed whatsapp_messages query poisons the session and the
    next tenant_query() raises until rollback() clears it — the Postgres
    aborted-transaction contract. Returns the mutable state dict."""
    state = {"poisoned": False, "rollbacks": 0}

    real_execute = db.execute

    def fake_execute(statement, *args, **kwargs):
        if "whatsapp_messages" in str(statement):
            state["poisoned"] = True
            raise OperationalError(
                "SELECT * FROM whatsapp_messages", {},
                Exception("no such table: whatsapp_messages"),
            )
        return real_execute(statement, *args, **kwargs)

    real_rollback = db.rollback

    def fake_rollback():
        state["poisoned"] = False
        state["rollbacks"] += 1
        return real_rollback()

    real_tenant_query = wl.tenant_query

    def fake_tenant_query(session, model, org_id):
        if state["poisoned"]:
            raise PendingRollbackError(
                "This Session's transaction has been rolled back "
                "due to a previous exception during flush."
            )
        return real_tenant_query(session, model, org_id)

    monkeypatch.setattr(db, "execute", fake_execute)
    monkeypatch.setattr(db, "rollback", fake_rollback)
    monkeypatch.setattr(wl, "tenant_query", fake_tenant_query)
    monkeypatch.setattr(wl, "get_current_user", lambda req, d: object())
    monkeypatch.setattr(
        wl.templates, "TemplateResponse",
        lambda name, ctx: {"_template": name, **ctx},
    )
    return state


@pytest.fixture
def request_stub(mock_request):
    mock_request.cookies = {}
    mock_request.state.org_id = _ORG_ID
    return mock_request


def test_message_history_redirects_to_clone_chat(db, monkeypatch, request_stub):
    """The Lite "Mensagens" entry should open the full chat experience, not
    render the stale Lite dashboard as a fake history screen."""
    db.add(Organization(id=_ORG_ID, uuid=f"uuid-{_ORG_ID}", name="Org 7", slug="org-7"))
    db.flush()
    monkeypatch.setattr(wl, "get_current_user", lambda req, d: object())
    monkeypatch.delenv("CASEHUB_WHATSAPP_CLONE_ENABLED", raising=False)

    result = asyncio.run(wl.message_history(request_stub, client_id=None, db=db))

    assert result.status_code == 302
    assert result.headers["location"] == f"{wl.PREFIX}/whatsapp-chat"


def test_message_history_redirects_client_to_clone_deeplink(db, monkeypatch, request_stub):
    db.add(Organization(id=_ORG_ID, uuid=f"uuid-{_ORG_ID}", name="Org 7", slug="org-7"))
    client = Client(
        id=42,
        org_id=_ORG_ID,
        first_name="PessoaDemo",
        last_name="Teste",
        whatsapp="+55 11 99999-9999",
    )
    db.add(client)
    db.flush()
    monkeypatch.setattr(wl, "get_current_user", lambda req, d: object())
    monkeypatch.delenv("CASEHUB_WHATSAPP_CLONE_ENABLED", raising=False)

    result = asyncio.run(wl.message_history(request_stub, client_id=42, db=db))

    assert result.status_code == 302
    assert result.headers["location"] == (
        f"{wl.PREFIX}/whatsapp-chat?phone=%2B55+11+99999-9999"
    )


def test_whatsapp_dashboard_survives_failed_messages_query(db, monkeypatch, request_stub):
    """Parity check: whatsapp_dashboard already rolls back on a failed
    whatsapp_messages query. Locks the contract both lite handlers must hold."""
    db.add(Organization(id=_ORG_ID, uuid=f"uuid-{_ORG_ID}", name="Org 7", slug="org-7"))
    db.flush()
    _install_harness(db, monkeypatch)

    result = asyncio.run(wl.whatsapp_dashboard(request_stub, db=db))

    assert isinstance(result, dict)
    assert result["_template"] == "app/whatsapp/lite_dashboard.html"
    assert result["recent"] == []
    assert result["stats"]["total"] == 0   # _get_message_stats degraded cleanly
