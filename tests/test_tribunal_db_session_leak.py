"""Regression test for the same DB-session-leak-across-slow-await bug class
as tests/test_whatsapp_chat_profile_pic_db_session_leak.py,
tests/test_whatsapp_crm_ai_db_session_leak.py and
tests/test_controladoria_db_session_leak.py.

Root cause: every endpoint in routes/tribunal.py ran `get_current_user(request,
db)` through the request's SQLAlchemy session, then `await`-ed the
DataJud/Escavador/JusBrasil/ComunicaAPI search chain — which can take up to
~2min across providers and fallbacks — WITHOUT releasing that session first.
Because the session's implicit transaction had already touched `users`, it
sat "idle in transaction" for the whole external round-trip, holding a lock
that every authenticated request eventually needs.

`get_current_user()` caches the resolved user on `request.state` (see
auth.py's `_get_cached_request_user`/`_set_cached_request_user`), so the
`_get_context()` call these handlers make AFTER the external search (to
build the template context) is safe to run against a closed-then-reopened
session — it hits the cache and never touches the DB again.

These tests assert the fix by ordering: the DB session must be `.close()`d
before the (mocked) external call is awaited, for every endpoint in
routes/tribunal.py that matches this pattern.
"""
import asyncio
import json

import pytest

import routes.tribunal as tribunal
from models.tenant import Organization
from services.escavador import EscavadorClient

_ORG_ID = 504


class _Req:
    """Minimal Request stub: tenant org_id on .state, no cookies needed."""

    def __init__(self, org_id):
        self.state = type("S", (), {"org_id": org_id})()
        self.cookies = {}

    async def json(self):
        return {}


@pytest.fixture()
def seeded_db(db):
    db.add(Organization(id=_ORG_ID, uuid="u-tribunal-leak", name="Org Tribunal Leak", slug="org-tribunal-leak"))
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
    monkeypatch.setattr(tribunal, "get_current_user", lambda req, s: user)
    return user


def test_tribunal_consulta_closes_db_before_search_chain(seeded_db, monkeypatch, mock_auth):
    """POST /tribunal/consulta — CNJ-number search path; must release the DB
    session before the DataJud round-trip, and still render the template
    afterwards (which re-resolves the user via the request-level cache, not
    a fresh DB query)."""
    db = seeded_db
    order = []
    _spy_on_close(db, order)

    async def _fake_consultar_processo(cnj, tribunal=None):
        order.append("datajud_call")
        return {"numeroProcesso": cnj}

    monkeypatch.setattr(tribunal.datajud_client, "consultar_processo", _fake_consultar_processo)

    resp = asyncio.run(
        tribunal.tribunal_consulta(
            _Req(_ORG_ID), db=db, query="1234567-89.2024.8.13.0001",
            tribunal="TJMG", search_type="numero",
        )
    )

    assert order == ["db.close", "datajud_call"], (
        "tribunal_consulta must release its DB session before awaiting the "
        "DataJud/Escavador/JusBrasil/ComunicaAPI search chain."
    )
    assert resp.status_code == 200


def test_tribunal_processo_detail_closes_db_before_search_chain(seeded_db, monkeypatch, mock_auth):
    """GET /tribunal/processo/{numero_cnj} — must release DB before the
    DataJud detail lookup."""
    db = seeded_db
    order = []
    _spy_on_close(db, order)

    async def _fake_consultar_processo(cnj):
        order.append("datajud_call")
        return {"numeroProcesso": cnj, "movimentos": []}

    monkeypatch.setattr(tribunal.datajud_client, "consultar_processo", _fake_consultar_processo)

    resp = asyncio.run(
        tribunal.tribunal_processo_detail(_Req(_ORG_ID), numero_cnj="1234567-89.2024.8.13.0001", db=db)
    )

    assert order == ["db.close", "datajud_call"], (
        "tribunal_processo_detail must release its DB session before "
        "awaiting the DataJud/Escavador/JusBrasil chain."
    )
    assert resp.status_code == 200


def test_tribunal_monitorar_closes_db_before_monitoring_calls(seeded_db, monkeypatch, mock_auth):
    """POST /tribunal/monitorar — `db` is unused after auth; must release it
    before the Escavador/JusBrasil monitoring calls."""
    db = seeded_db
    order = []
    _spy_on_close(db, order)

    monkeypatch.setattr(EscavadorClient, "is_configured", property(lambda self: True))

    async def _fake_monitorar_processo(cnj):
        order.append("escavador_call")
        return {"status": "ok"}

    monkeypatch.setattr(tribunal.escavador_client, "monitorar_processo", _fake_monitorar_processo)

    resp = asyncio.run(
        tribunal.tribunal_monitorar(_Req(_ORG_ID), db=db, numero_cnj="1234567-89.2024.8.13.0001")
    )
    payload = json.loads(resp.body)

    assert order == ["db.close", "escavador_call"], (
        "tribunal_monitorar must release its DB session before awaiting the "
        "Escavador/JusBrasil monitoring calls."
    )
    assert payload["status"] == "ok"


def test_tribunal_publicacoes_closes_db_before_search_calls(seeded_db, monkeypatch, mock_auth):
    """GET /tribunal/publicacoes — must release DB before the
    Escavador/JusBrasil publication lookups."""
    db = seeded_db
    order = []
    _spy_on_close(db, order)

    async def _fake_buscar_publicacoes(nome=None, oab=None):
        order.append("escavador_call")
        return [{"titulo": "Publicação"}]

    monkeypatch.setattr(tribunal.escavador_client, "buscar_publicacoes", _fake_buscar_publicacoes)

    resp = asyncio.run(tribunal.tribunal_publicacoes(_Req(_ORG_ID), db=db, nome="Maria Souza", oab=None))

    assert order == ["db.close", "escavador_call"], (
        "tribunal_publicacoes must release its DB session before awaiting "
        "the Escavador/JusBrasil publication lookups."
    )
    assert resp.status_code == 200
