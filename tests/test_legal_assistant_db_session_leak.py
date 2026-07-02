"""Regression test for the same DB-session-leak-across-slow-await bug class
as tests/test_whatsapp_chat_profile_pic_db_session_leak.py,
tests/test_whatsapp_crm_ai_db_session_leak.py, etc.

Root cause: POST /api/legal-assistant/ask ran `get_current_user(request, db)`
through the request's SQLAlchemy session, then `await`-ed `query_legal_
assistant()` — a Gemini API call with a 45s httpx timeout — WITHOUT
releasing that session first. Because the session's implicit transaction had
already touched `users`, it sat "idle in transaction" for up to 45s per
request, holding a lock that every authenticated request eventually needs.

This test asserts the fix by ordering: the DB session must be `.close()`d
before the (mocked) Gemini call is awaited.
"""
import asyncio

import pytest

import routes.legal_assistant as legal_assistant
from models.tenant import Organization

_ORG_ID = 505


class _Req:
    """Minimal Request stub: no cookies needed, auth is monkeypatched."""

    def __init__(self):
        self.state = type("S", (), {})()
        self.cookies = {}


@pytest.fixture()
def seeded_db(db):
    db.add(Organization(id=_ORG_ID, uuid="u-legal-leak", name="Org Legal Leak", slug="org-legal-leak"))
    db.commit()
    return db


def _spy_on_close(session, order, label="db.close"):
    original_close = session.close

    def _spy(*args, **kwargs):
        order.append(label)
        return original_close(*args, **kwargs)

    session.close = _spy
    return session


@pytest.fixture()
def mock_auth(monkeypatch):
    user = type("U", (), {"org_id": _ORG_ID, "organization_id": _ORG_ID})()
    monkeypatch.setattr(legal_assistant, "get_current_user", lambda req, s: user)
    return user


def test_ask_legal_assistant_closes_db_before_gemini_call(seeded_db, monkeypatch, mock_auth):
    db = seeded_db
    order = []
    _spy_on_close(db, order)

    async def _fake_query_legal_assistant(question, context, history):
        order.append("gemini_call")
        return "Resposta do assistente.", ["fonte-1"]

    monkeypatch.setattr(legal_assistant, "query_legal_assistant", _fake_query_legal_assistant)

    question = legal_assistant.LegalQuestion(question="Quais os requisitos do EB-2?")
    resp = asyncio.run(legal_assistant.ask_legal_assistant(_Req(), question, db=db))

    assert order == ["db.close", "gemini_call"], (
        "ask_legal_assistant must release its DB session before awaiting the "
        "Gemini call (up to 45s timeout), or a slow/hung upstream leaves an "
        "idle-in-transaction Postgres session holding a lock on `users`."
    )
    assert resp.response == "Resposta do assistente."
    assert resp.sources == ["fonte-1"]
