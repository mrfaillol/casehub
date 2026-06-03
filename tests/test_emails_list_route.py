"""Regression test for routes/emails.list_emails — error-path resilience.

The /casehub/emails page handler runs the email-list query in a try/except
that swallows a failure and falls back to `emails = []`. It did not roll back
the session. On Postgres a failed statement aborts the transaction, so the
next ORM query — the clients tenant_query a few lines below — raised
PendingRollbackError, turning the intended empty state into an HTTP 500.

The fake tenant_query below encodes that Postgres aborted-transaction contract
so the test is deterministic and backend-independent. Same defect class as the
whatsapp_lite / whatsapp dashboard rollback fixes.

Run: pytest tests/test_emails_list_route.py
"""
import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, PendingRollbackError

import routes.emails as em

_ORG_ID = 9


@pytest.fixture
def email_tables(db):
    """email_accounts / email_messages are raw-migration tables, not ORM models.
    list_emails queries them after the email-list query; create minimal versions
    so the handler can reach its render once the session is healthy."""
    db.execute(text("DROP TABLE IF EXISTS email_accounts"))
    db.execute(text("DROP TABLE IF EXISTS email_messages"))
    db.execute(text(
        "CREATE TABLE email_accounts "
        "(id INTEGER PRIMARY KEY, name TEXT, email_address TEXT, enabled BOOLEAN)"
    ))
    db.execute(text("CREATE TABLE email_messages (id INTEGER PRIMARY KEY, folder TEXT)"))
    db.commit()
    yield db
    db.rollback()
    db.execute(text("DROP TABLE IF EXISTS email_accounts"))
    db.execute(text("DROP TABLE IF EXISTS email_messages"))
    db.commit()


def _install_harness(db, monkeypatch):
    """The email-list query fails and poisons the session; the next
    tenant_query() raises until rollback() clears it."""
    state = {"poisoned": False, "rollbacks": 0}
    real_execute = db.execute

    def fake_execute(statement, *args, **kwargs):
        # "received_at" uniquely identifies the big email-list SELECT.
        if "received_at" in str(statement):
            state["poisoned"] = True
            raise OperationalError(str(statement), {}, Exception("email-list query failed"))
        return real_execute(statement, *args, **kwargs)

    real_rollback = db.rollback

    def fake_rollback():
        state["poisoned"] = False
        state["rollbacks"] += 1
        return real_rollback()

    real_tenant_query = em.tenant_query

    def fake_tenant_query(session, model, org_id):
        if state["poisoned"]:
            raise PendingRollbackError(
                "This Session's transaction has been rolled back "
                "due to a previous exception during flush."
            )
        return real_tenant_query(session, model, org_id)

    monkeypatch.setattr(db, "execute", fake_execute)
    monkeypatch.setattr(db, "rollback", fake_rollback)
    monkeypatch.setattr(em, "tenant_query", fake_tenant_query)
    monkeypatch.setattr(em, "get_current_user", lambda req, d: object())
    monkeypatch.setattr(em, "get_paralegal_mapping", lambda: {})
    monkeypatch.setattr(em.templates, "TemplateResponse",
                        lambda name, ctx: {"_template": name, **ctx})
    return state


@pytest.fixture
def request_stub(mock_request):
    mock_request.cookies = {}
    mock_request.state.org_id = _ORG_ID
    return mock_request


def test_list_emails_survives_failed_email_query(email_tables, monkeypatch, request_stub):
    """list_emails must not 500 when the email-list query fails: it rolls back,
    then renders the empty/error state. Regression for the missing db.rollback()
    (the clients tenant_query would otherwise raise PendingRollbackError)."""
    db = email_tables
    state = _install_harness(db, monkeypatch)

    result = asyncio.run(em.list_emails(request_stub, db=db))

    assert isinstance(result, dict)
    assert result["_template"] == "emails/list.html"
    assert result["emails"] == []           # empty state, not a 500
    assert result["clients"] == []
    assert state["rollbacks"] >= 1          # the except path rolled back
