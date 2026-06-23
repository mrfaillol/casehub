"""Tests for the Domicílio Judicial Eletrônico (DJE) client + route.

No network: httpx is mocked via ``httpx.MockTransport`` injected into a real
``httpx.AsyncClient`` that replaces the pooled ``get_pdpj_client``. All secrets
are obviously-fake and resolved through a monkeypatched credentials resolver
(never read from a real DB / never hardcoded into source).

    python -m pytest tests/test_dje_client.py --noconftest
"""
from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

import services.dje_client as dje_mod
from services.dje_client import DJEClient


# ── fakes ────────────────────────────────────────────────────────────────
FAKE_TOKEN = "fake-jwt-access-token"
FAKE_TENANT_ID = "11111111-2222-3333-4444-555555555555"


def _fake_creds(configured=True):
    return SimpleNamespace(
        client_id="fake-client-id" if configured else "",
        client_secret="fake-client-secret" if configured else "",
        configured=configured,
        source="database" if configured else "none",
        error="" if configured else "missing_credentials",
    )


class _Recorder:
    """Captures the requests the client makes so we can assert on them."""

    def __init__(self):
        self.token_calls = 0
        self.last_comunicacoes_request: httpx.Request | None = None
        self.eu_calls = 0


def _make_transport(rec: _Recorder, *, eu_payload=None, comunicacoes_payload=None,
                    comunicacoes_status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/protocol/openid-connect/token"):
            rec.token_calls += 1
            # The client_secret must travel in the body, never logged.
            assert b"client_credentials" in request.content
            return httpx.Response(200, json={"access_token": FAKE_TOKEN, "expires_in": 300})
        if url.endswith("/api/v1/eu"):
            rec.eu_calls += 1
            assert request.headers["Authorization"] == f"Bearer {FAKE_TOKEN}"
            return httpx.Response(200, json=eu_payload or _default_eu())
        if "/api/v1/comunicacoes" in url:
            rec.last_comunicacoes_request = request
            if comunicacoes_status != 200:
                return httpx.Response(comunicacoes_status, json={"error": "boom"})
            return httpx.Response(200, json=comunicacoes_payload or _default_comunicacoes())
        return httpx.Response(404, json={"error": "unexpected path", "url": url})

    return httpx.MockTransport(handler)


def _default_eu():
    return {
        "pessoa": {"id": 1, "nome": "Fulano"},
        "perfis": [
            {"id": 1, "tenantId": "", "tenantName": "empty-first"},
            {"id": 2, "tenantId": FAKE_TENANT_ID, "tenantName": "Escritório X"},
        ],
    }


def _default_comunicacoes():
    return {
        "page": {"number": 0, "size": 20, "totalElements": 1, "totalPages": 1},
        "data": [
            {
                "numeroComunicacao": "C-123",
                "numeroProcesso": "0001234-56.2024.8.13.0145",
                "tribunalOrigem": "TJMG",
                "uf": "MG",
                "orgaoLegal": "1ª Vara Cível",
                "assunto": "Intimação",
                "tipoComunicacao": "Intimação",
                "dataComunicacao": "2026-06-10",
                "dataFinalCiencia": "2026-06-20",
                "prazo": 15,
                "tipoPrazo": "DIAS_UTEIS",
                "ciente": False,
                "linksDocumentos": ["https://example/doc1"],
            }
        ],
    }


@pytest.fixture
def patched_client(monkeypatch):
    """Return a factory that wires a fresh DJEClient to a mocked transport."""

    def factory(*, configured=True, eu_payload=None, comunicacoes_payload=None,
                comunicacoes_status=200):
        rec = _Recorder()
        transport = _make_transport(
            rec,
            eu_payload=eu_payload,
            comunicacoes_payload=comunicacoes_payload,
            comunicacoes_status=comunicacoes_status,
        )
        mock_async_client = httpx.AsyncClient(transport=transport)
        monkeypatch.setattr(dje_mod, "get_pdpj_client", lambda: mock_async_client)
        client = DJEClient()
        # Patch credential resolution on the instance (the real resolver does a
        # lazy DB import inside DJEClient._credentials_for). Fake, never a DB hit.
        monkeypatch.setattr(client, "_credentials_for", lambda org_id: _fake_creds(configured))
        return client, rec, mock_async_client

    return factory


# ── token acquisition + caching ───────────────────────────────────────────
async def test_token_acquired_and_cached(patched_client):
    client, rec, mc = patched_client()
    try:
        t1 = await client._get_access_token(org_id=4)
        t2 = await client._get_access_token(org_id=4)
    finally:
        await mc.aclose()
    assert t1 == FAKE_TOKEN
    assert t2 == FAKE_TOKEN
    # second call served from cache -> only one token request
    assert rec.token_calls == 1


# ── tenantId resolution + header ───────────────────────────────────────────
async def test_tenant_id_resolved_and_sent_as_header(patched_client):
    client, rec, mc = patched_client()
    try:
        result = await client.listar_comunicacoes(org_id=4)
    finally:
        await mc.aclose()
    assert result["source"] == "DJE/PDPJ"
    # tenantId came from the SECOND profile (first had empty tenantId)
    req = rec.last_comunicacoes_request
    assert req is not None
    assert req.headers["tenantId"] == FAKE_TENANT_ID
    # required query params present
    assert "statusCiente=N" in str(req.url)
    assert "page=0" in str(req.url)
    assert "size=20" in str(req.url)


async def test_tenant_id_cached_across_calls(patched_client):
    client, rec, mc = patched_client()
    try:
        await client.listar_comunicacoes(org_id=4)
        await client.listar_comunicacoes(org_id=4)
    finally:
        await mc.aclose()
    # /api/v1/eu hit once; tenantId cached afterwards
    assert rec.eu_calls == 1


# ── comunicações parsing ───────────────────────────────────────────────────
async def test_comunicacoes_parsed(patched_client):
    client, _, mc = patched_client()
    try:
        result = await client.listar_comunicacoes(org_id=4)
    finally:
        await mc.aclose()
    assert result["count"] == 1
    assert result["total_pages"] == 1
    item = result["items"][0]
    assert item["numero_comunicacao"] == "C-123"
    assert item["numero_processo"] == "0001234-56.2024.8.13.0145"
    assert item["tribunal"] == "TJMG"
    assert item["orgao"] == "1ª Vara Cível"
    assert item["prazo"] == 15
    assert item["ciente"] is False
    assert item["links_documentos"] == ["https://example/doc1"]
    assert item["source"] == "DJE/PDPJ"


# ── creds missing -> empty, no crash ───────────────────────────────────────
async def test_missing_credentials_returns_empty(patched_client):
    client, rec, mc = patched_client(configured=False)
    try:
        result = await client.listar_comunicacoes(org_id=4)
    finally:
        await mc.aclose()
    assert result["items"] == []
    assert result["count"] == 0
    assert result["error"] == "missing_credentials"
    # no token / no gateway call attempted
    assert rec.token_calls == 0
    assert rec.eu_calls == 0


# ── upstream error -> empty + cache invalidated ────────────────────────────
async def test_upstream_403_returns_empty_and_invalidates(patched_client):
    client, _, mc = patched_client(comunicacoes_status=403)
    try:
        result = await client.listar_comunicacoes(org_id=4)
    finally:
        await mc.aclose()
    assert result["items"] == []
    assert result["error"] == "http_403"
    # token + tenantId cache dropped after 403
    st = client._bucket(4)
    assert st.access_token is None
    assert st.tenant_id is None


# ── env switch PROD vs HML ─────────────────────────────────────────────────
def test_env_switch_prod_vs_hml(monkeypatch):
    monkeypatch.setattr(dje_mod.settings, "DJE_ENV", "prod")
    assert dje_mod._dje_base_url() == "https://gateway.cloud.pje.jus.br/domicilio-eletronico"
    assert dje_mod._dje_token_url().startswith("https://sso.cloud.pje.jus.br/")
    monkeypatch.setattr(dje_mod.settings, "DJE_ENV", "hml")
    assert dje_mod._dje_base_url() == "https://gateway.stg.cloud.pje.jus.br/domicilio-eletronico-hml"
    assert dje_mod._dje_token_url().startswith("https://sso.stg.cloud.pje.jus.br/")


# ── tenantId extraction helper ─────────────────────────────────────────────
def test_extract_tenant_id_picks_first_nonempty():
    assert DJEClient._extract_tenant_id(_default_eu()) == FAKE_TENANT_ID
    assert DJEClient._extract_tenant_id({"perfis": []}) is None
    assert DJEClient._extract_tenant_id({"tenantId": "flat-uuid"}) == "flat-uuid"


# ── route flag gating ──────────────────────────────────────────────────────
def test_route_flag_off_raises_404(monkeypatch):
    import routes.dje as dje_route
    from fastapi import HTTPException

    monkeypatch.setattr(dje_route.feature_flags, "is_enabled", lambda name: False)
    with pytest.raises(HTTPException) as exc:
        dje_route._require_enabled()
    assert exc.value.status_code == 404


def test_route_flag_on_passes(monkeypatch):
    import routes.dje as dje_route

    monkeypatch.setattr(dje_route.feature_flags, "is_enabled", lambda name: True)
    # should not raise
    dje_route._require_enabled()


def test_route_module_exports_router_with_path():
    import routes.dje as dje_route

    paths = {r.path for r in dje_route.router.routes}
    assert "/dje/comunicacoes" in paths
