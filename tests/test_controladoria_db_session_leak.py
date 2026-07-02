"""Regression test for the same DB-session-leak-across-slow-await bug class
as tests/test_whatsapp_chat_profile_pic_db_session_leak.py and
tests/test_whatsapp_crm_ai_db_session_leak.py.

Root cause: several Controladoria endpoints ran `get_current_user(request,
db)` (and, in `buscar_intimacoes`'s case, an additional `Case` query) through
the request's SQLAlchemy session, then `await`-ed a slow external call — the
ComunicaAPI/PDPJ/DataJud chain, which can take up to ~2min across providers
and fallbacks — WITHOUT releasing that session first. Because the session's
implicit transaction had already touched `users` (and, for
`buscar_intimacoes`, `cases`), it sat "idle in transaction" for the whole
external round-trip, holding a lock that every authenticated request
eventually needs.

These tests assert the fix by ordering: the DB session must be `.close()`d
before the (mocked) external call is awaited, for every endpoint in
routes/controladoria.py that matches this pattern.
"""
import asyncio
import json

import pytest

import routes.controladoria as controladoria
import services.datajud as datajud_module
from models.tenant import Organization
from models.client import Client
from models.case import Case

_ORG_ID = 503


class _Req:
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
def seeded_case(db):
    db.add(Organization(id=_ORG_ID, uuid="u-ctrl-leak", name="Org Controladoria Leak", slug="org-ctrl-leak"))
    db.flush()
    client = Client(first_name="Maria", last_name="Souza")
    db.add(client)
    db.flush()
    case = Case(
        org_id=_ORG_ID,
        client_id=client.id,
        case_number="1234567-89.2024.8.13.0001",
        case_name="Maria Souza x Réu",
    )
    db.add(case)
    db.commit()
    return db


def _spy_on_close(session, order, label="db.close"):
    """Wrap session.close so tests can assert call order vs. the external call."""
    original_close = session.close

    def _spy(*args, **kwargs):
        order.append(label)
        return original_close(*args, **kwargs)

    session.close = _spy
    return session


@pytest.fixture()
def mock_auth(monkeypatch):
    user = type("U", (), {"org_id": _ORG_ID, "organization_id": _ORG_ID})()
    monkeypatch.setattr(controladoria, "get_current_user", lambda req, s: user)
    return user


def test_buscar_intimacoes_closes_db_before_datajud_call(seeded_case, monkeypatch, mock_auth):
    """POST /controladoria/buscar-intimacoes — fetches monitored cases via
    `db`, then loops calling DataJud per case; must release the session
    before those (potentially many, slow) external round-trips."""
    db = seeded_case
    order = []
    _spy_on_close(db, order)

    async def _fake_get_movimentacoes(numero):
        order.append("datajud_call")
        return [
            {
                "nome": "Intimação eletrônica",
                "dataHora": "2026-06-01T10:00:00",
                "complementosTabelados": [],
            }
        ]

    monkeypatch.setattr(datajud_module.datajud_client, "get_movimentacoes", _fake_get_movimentacoes)

    resp = asyncio.run(controladoria.buscar_intimacoes(_Req(_ORG_ID), db=db))
    payload = _body(resp)

    assert order == ["db.close", "datajud_call"], (
        "buscar_intimacoes must release its DB session before awaiting the "
        "DataJud call for each monitored case, or a slow/hung upstream "
        "leaves an idle-in-transaction Postgres session holding a lock on "
        "`users`/`cases`."
    )
    assert payload["success"] is True
    assert payload["total"] == 1
    assert payload["intimacoes"][0]["case_name"] == "Maria Souza x Réu"


def test_buscar_comunicaapi_closes_db_before_search_chain(seeded_case, monkeypatch, mock_auth):
    """POST /controladoria/buscar-comunicaapi — the ComunicaAPI/PDPJ chain can
    take up to ~2min across providers+fallbacks; must release the DB session
    before it."""
    db = seeded_case
    order = []
    _spy_on_close(db, order)

    async def _fake_chain(numero_oab, uf_oab, data_inicio, data_fim, org_id=None):
        order.append("search_chain_call")
        return {
            "items": [{"texto": "Intimação de Maria Souza", "id": "abc123"}],
            "provider": "ComunicaAPI PJE/CNJ",
            "provider_status": "ok",
            "reason": None,
            "last_error": None,
            "fallback_active": False,
            "fallback_chain": [],
            "auth_status": "configured",
            "grant_attempted": "client_credentials",
            "source": "ComunicaAPI PJE/CNJ",
            "last_attempt_at": None,
            "code": None,
        }

    monkeypatch.setattr(controladoria, "_search_intimacoes_oab_chain", _fake_chain)

    req = _Req(_ORG_ID, body={"numero_oab": "123456", "uf_oab": "MG"})
    resp = asyncio.run(controladoria.buscar_comunicaapi(req, db=db))
    payload = _body(resp)

    assert order == ["db.close", "search_chain_call"], (
        "buscar_comunicaapi must release its DB session before awaiting the "
        "ComunicaAPI/PDPJ search chain."
    )
    assert payload["success"] is True
    assert payload["total"] == 1


def test_api_datajud_busca_closes_db_before_datajud_call(seeded_case, monkeypatch, mock_auth):
    """GET /controladoria/api/datajud — `db` is unused after auth; must
    release it before the DataJud round-trip."""
    db = seeded_case
    order = []
    _spy_on_close(db, order)

    async def _fake_consultar_processo(termo, tribunal=None):
        order.append("datajud_call")
        return {"numeroProcesso": termo, "tribunal": tribunal}

    monkeypatch.setattr(datajud_module.datajud_client, "consultar_processo", _fake_consultar_processo)

    resp = asyncio.run(
        controladoria.api_datajud_busca(
            _Req(_ORG_ID), tipo="numero", q="1234567-89.2024.8.13.0001", tribunal="TJMG", db=db
        )
    )
    payload = _body(resp)

    assert order == ["db.close", "datajud_call"], (
        "api_datajud_busca must release its DB session before awaiting the "
        "DataJud call."
    )
    assert payload["ok"] is True
