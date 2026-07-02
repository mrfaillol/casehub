"""Regression test for the DB-session-leak-across-slow-await bug class
(2026-07-01 incident class: a Postgres session sitting idle-in-transaction
while an endpoint `await`s a slow external AI call holds a lock on `users`
— touched by ~every authenticated request via get_current_user — which can
queue behind a concurrent schema-ensure ALTER TABLE and take the whole site
down).

routes/whatsapp_crm.py's AI-assist endpoints (`api_crm_ai_suggest`,
`api_crm_ai_summary`, `api_crm_ai_draft`, `api_lead_summary`) query
wa_contacts/wa_conversations/wa_messages through the request's SQLAlchemy
session, then `await` a slow external AI call (`_maestro_generate` —
Ollama/provider fallback) WITHOUT releasing that session first.

These tests assert the fix by ordering: the DB session must be `.close()`d
before the (mocked) AI call is awaited, for every AI-assist endpoint.
"""
import asyncio
import json

import pytest

import routes.whatsapp_crm as wcrm
from models.tenant import Organization
from models.whatsapp_clone import WaContact

_ORG_ID = 501


class _JsonRequest:
    """Minimal Request stub: tenant org_id on .state + a JSON body."""

    def __init__(self, org_id, body=None):
        self.state = type("S", (), {"org_id": org_id})()
        self.cookies = {}
        self._body = body or {}

    async def json(self):
        return self._body


def _body(resp):
    return json.loads(resp.body)


@pytest.fixture()
def seeded_contact(db):
    db.add(Organization(id=_ORG_ID, uuid="u-crm-leak", name="Org CRM Leak", slug="org-crm-leak"))
    db.flush()
    db.add(WaContact(
        org_id=_ORG_ID, phone="+5511999990001", display_name="Cliente Teste",
        lead_stage="triagem", tags=[],
    ))
    db.commit()
    return db


def _spy_on_close(session, order, label="db.close"):
    """Wrap session.close so tests can assert call order vs. the AI call."""
    original_close = session.close

    def _spy(*args, **kwargs):
        order.append(label)
        return original_close(*args, **kwargs)

    session.close = _spy
    return session


def _fake_maestro_generate_factory(order, response):
    async def _fake(prompt, **kwargs):
        order.append("ai_call")
        return response
    return _fake


@pytest.fixture()
def mock_auth(monkeypatch):
    monkeypatch.setattr(wcrm, "get_current_user", lambda req, s: object())


def test_lead_summary_closes_db_before_ai_call(seeded_contact, monkeypatch, mock_auth):
    """GET /api/lead-summary/{phone} — the highest-frequency offender (fires
    on every conversation open via chat.js loadConversationSummary(), not
    just a manual AI button click)."""
    db = seeded_contact
    order = []
    _spy_on_close(db, order)
    monkeypatch.setattr(wcrm, "_conversation_history", lambda *a, **k: "Cliente: Oi, preciso de ajuda")
    monkeypatch.setattr(
        wcrm, "_maestro_generate",
        _fake_maestro_generate_factory(order, '{"currentSituation": "ok"}'),
    )

    resp = asyncio.run(wcrm.api_lead_summary(_JsonRequest(_ORG_ID), phone="+5511999990001", db=db))
    payload = _body(resp)

    assert order == ["db.close", "ai_call"], (
        "api_lead_summary must release its DB session before awaiting the "
        "external AI call, or a slow/hung AI upstream leaves an "
        "idle-in-transaction Postgres session holding a lock on `users` "
        "(2026-07-01 prod outage)."
    )
    assert payload["summary"]["currentSituation"] == "ok"


def test_crm_ai_suggest_closes_db_before_ai_call(seeded_contact, monkeypatch, mock_auth):
    db = seeded_contact
    order = []
    _spy_on_close(db, order)
    monkeypatch.setattr(wcrm, "_conversation_history", lambda *a, **k: "Cliente: Oi, preciso de ajuda")
    monkeypatch.setattr(
        wcrm, "_maestro_generate",
        _fake_maestro_generate_factory(order, "Resposta sugerida"),
    )

    req = _JsonRequest(_ORG_ID, body={"phone": "+5511999990001"})
    resp = asyncio.run(wcrm.api_crm_ai_suggest(req, db=db))
    payload = _body(resp)

    assert order == ["db.close", "ai_call"]
    assert payload["suggestion"] == "Resposta sugerida"


def test_crm_ai_summary_closes_db_before_ai_call(seeded_contact, monkeypatch, mock_auth):
    db = seeded_contact
    order = []
    _spy_on_close(db, order)
    monkeypatch.setattr(wcrm, "_conversation_history", lambda *a, **k: "Cliente: Oi, preciso de ajuda")
    monkeypatch.setattr(
        wcrm, "_maestro_generate",
        _fake_maestro_generate_factory(order, "Resumo da conversa"),
    )

    req = _JsonRequest(_ORG_ID, body={"phone": "+5511999990001"})
    resp = asyncio.run(wcrm.api_crm_ai_summary(req, db=db))
    payload = _body(resp)

    assert order == ["db.close", "ai_call"]
    assert payload["summary"] == "Resumo da conversa"


def test_crm_ai_draft_closes_db_before_ai_call(seeded_contact, monkeypatch, mock_auth):
    db = seeded_contact
    order = []
    _spy_on_close(db, order)
    monkeypatch.setattr(wcrm, "_conversation_history", lambda *a, **k: "Cliente: Oi, preciso de ajuda")
    monkeypatch.setattr(
        wcrm, "_maestro_generate",
        _fake_maestro_generate_factory(order, "Mensagem redigida"),
    )

    req = _JsonRequest(_ORG_ID, body={"phone": "+5511999990001", "instruction": "peça o CPF"})
    resp = asyncio.run(wcrm.api_crm_ai_draft(req, db=db))
    payload = _body(resp)

    assert order == ["db.close", "ai_call"]
    assert payload["draft"] == "Mensagem redigida"


def test_lead_summary_never_calls_ai_when_no_history(seeded_contact, monkeypatch, mock_auth):
    """No conversation -> no history -> the AI call (and thus the DB-hold
    risk) never happens at all; db.close() should still not be skipped."""
    db = seeded_contact
    order = []
    _spy_on_close(db, order)
    monkeypatch.setattr(wcrm, "_conversation_history", lambda *a, **k: "")

    called = {"ai": False}

    async def _fake(prompt, **kwargs):
        called["ai"] = True
        return "should not be called"

    monkeypatch.setattr(wcrm, "_maestro_generate", _fake)

    # Unknown phone -> _get_contact returns None -> early "no conversation" return.
    resp = asyncio.run(wcrm.api_lead_summary(_JsonRequest(_ORG_ID), phone="+5511900000000", db=db))
    payload = _body(resp)

    assert payload == {"error": "no conversation"}
    assert called["ai"] is False
