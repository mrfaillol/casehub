import json
from types import SimpleNamespace
import uuid

import httpx
import pytest
from sqlalchemy import text

from models.tenant import Organization


def _http_status_error(status_code=400, payload=None):
    request = httpx.Request("POST", "https://sso.cloud.pje.jus.br/token")
    response = httpx.Response(status_code, json=payload or {"error": "invalid_client"}, request=request)
    return httpx.HTTPStatusError("PDPJ rejected credentials", request=request, response=response)


def _create_org(db, settings=None):
    org = Organization(
        uuid=str(uuid.uuid4()),
        name="Escritorio Demo",
        slug=f"example-{uuid.uuid4().hex[:8]}",
        settings=settings or {},
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def test_public_pdpj_error_message_explains_resource_scope_403():
    from services.comunicaapi import public_pdpj_error_message

    message = public_pdpj_error_message("http_403")

    assert "permissao/escopo" in message
    assert "refresh" not in message.lower()


def test_tenant_pdpj_credentials_are_encrypted_and_redacted(db, monkeypatch):
    from services.pdpj_credentials import (
        public_pdpj_credential_status,
        resolve_pdpj_client_credentials,
        store_tenant_pdpj_client_credentials,
    )

    org = _create_org(db)
    raw_client_id = "legalops-dje-client"
    raw_secret = "tenant-secret-value"

    status = store_tenant_pdpj_client_credentials(
        db,
        org.id,
        client_id=raw_client_id,
        client_secret=raw_secret,
        user_id=7,
    )
    db.commit()

    row = db.execute(text("SELECT settings FROM organizations WHERE id = :id"), {"id": org.id}).fetchone()
    serialized_settings = json.dumps(row.settings if isinstance(row.settings, dict) else str(row.settings))
    assert raw_secret not in serialized_settings
    assert status["configured"] is True
    assert status["source"] == "database"
    assert raw_secret not in json.dumps(status)

    resolved = resolve_pdpj_client_credentials(db, org.id)
    assert resolved.configured is True
    assert resolved.client_id == raw_client_id
    assert resolved.client_secret == raw_secret

    public = public_pdpj_credential_status(db, org.id)
    assert raw_secret not in json.dumps(public)
    assert public["client_secret_fingerprint"]


def test_tenant_pdpj_credentials_prefer_database_over_env(db, monkeypatch):
    from services.pdpj_credentials import (
        resolve_pdpj_client_credentials,
        store_tenant_pdpj_client_credentials,
    )

    org = _create_org(db)
    store_tenant_pdpj_client_credentials(
        db,
        org.id,
        client_id="tenant-client",
        client_secret="tenant-secret",
    )
    db.commit()

    resolved = resolve_pdpj_client_credentials(
        db,
        org.id,
        env_client_id="global-client",
        env_client_secret="global-secret",
    )

    assert resolved.source == "database"
    assert resolved.client_id == "tenant-client"
    assert resolved.client_secret == "tenant-secret"


def test_partial_tenant_pdpj_credentials_fail_closed_without_env_fallback(db):
    from services.pdpj_credentials import resolve_pdpj_client_credentials

    org = _create_org(db, settings={"pdpj_client_id": "partial-client"})

    resolved = resolve_pdpj_client_credentials(
        db,
        org.id,
        env_client_id="global-client",
        env_client_secret="global-secret",
    )

    assert resolved.source == "database"
    assert resolved.configured is False
    assert resolved.error == "tenant_credentials_incomplete"
    assert resolved.client_id == "partial-client"
    assert resolved.client_secret == ""


def test_pdpj_request_org_id_does_not_default_to_org_one():
    from routes.pdpj_oauth import _request_org_id

    assert _request_org_id(SimpleNamespace(state=SimpleNamespace())) is None
    assert _request_org_id(
        SimpleNamespace(state=SimpleNamespace()),
        SimpleNamespace(org_id=9),
    ) == 9
    assert _request_org_id(
        SimpleNamespace(state=SimpleNamespace(org_id="4")),
        SimpleNamespace(org_id=9),
    ) == 4


@pytest.mark.asyncio
async def test_pdpj_probe_reports_missing_credentials(monkeypatch):
    from services.comunicaapi import PDPJAuthClient

    monkeypatch.delenv("PDPJ_CLIENT_ID", raising=False)
    monkeypatch.delenv("PDPJ_CLIENT_SECRET", raising=False)

    auth = PDPJAuthClient()
    result = await auth.probe_client_credentials()

    assert result["success"] is False
    assert result["code"] == "missing_credentials"
    assert result["auth"]["has_client_id"] is False


@pytest.mark.asyncio
async def test_get_access_token_preserves_invalid_client(monkeypatch):
    from services.comunicaapi import PDPJAuthClient

    auth = PDPJAuthClient()
    auth.client_id = "example-law-client"
    auth.client_secret = "secret"

    async def fail_client_credentials(org_id=None):
        auth._set_last_error("invalid_client", 400, "Invalid client", org_id=org_id)
        raise _http_status_error(400, {"error": "invalid_client", "error_description": "Invalid client"})

    monkeypatch.setattr(auth, "_authenticate_client_credentials", fail_client_credentials)

    token = await auth.get_access_token()

    assert token is None
    assert auth.last_error_code == "invalid_client"
    assert auth.public_status()["last_error_message"]


@pytest.mark.asyncio
async def test_comunicaapi_missing_credentials_is_not_empty_success(monkeypatch):
    import services.comunicaapi as comunicaapi

    auth = comunicaapi.PDPJAuthClient()
    auth.client_id = ""
    auth.client_secret = ""
    monkeypatch.setattr(comunicaapi, "pdpj_auth", auth)
    monkeypatch.setattr(comunicaapi.settings, "DEMO_MODE", False)

    result = await comunicaapi.ComunicaAPIClient().buscar_por_oab("209176", "MG", org_id=1)

    assert result["count"] == 0
    assert result["error"] == "missing_credentials"
    assert "message" in result


@pytest.mark.asyncio
async def test_comunicaapi_requires_explicit_org_id(monkeypatch):
    import services.comunicaapi as comunicaapi

    auth = comunicaapi.PDPJAuthClient()
    auth.client_id = "client"
    auth.client_secret = "secret"
    monkeypatch.setattr(comunicaapi, "pdpj_auth", auth)
    monkeypatch.setattr(comunicaapi.settings, "DEMO_MODE", False)

    result = await comunicaapi.ComunicaAPIClient().buscar_por_oab("209176", "MG")

    assert result["count"] == 0
    assert result["error"] == "missing_org_id"


@pytest.mark.asyncio
async def test_controladoria_route_returns_failure_for_pdpj_error(monkeypatch):
    import routes.controladoria as controladoria
    import services.comunicaapi as comunicaapi

    class FakeRequest:
        state = SimpleNamespace(org_id=1)

        async def json(self):
            return {"numero_oab": "209176", "uf_oab": "MG"}

    class FakeClient:
        async def buscar_por_oab(self, *args, **kwargs):
            assert kwargs["org_id"] == 1
            return {
                "items": [],
                "count": 0,
                "source": "ComunicaAPI PJE/CNJ (sem access_token)",
                "error": "invalid_client",
                "message": "O CNJ/PDPJ rejeitou o client_id/client_secret configurado.",
            }

    monkeypatch.setattr(controladoria, "get_current_user", lambda request, db: SimpleNamespace(id=1))
    monkeypatch.setattr(comunicaapi, "comunicaapi_client", FakeClient())

    async def empty_provider(provider):
        async def inner(*args, **kwargs):
            return {
                "items": [],
                "attempt": controladoria._provider_attempt(provider, "empty", "empty", count=0),
            }
        return inner

    monkeypatch.setattr(controladoria, "_try_datajud_provider", await empty_provider("DataJud (CNJ)"))
    monkeypatch.setattr(controladoria, "_try_escavador_provider", await empty_provider("Escavador"))
    monkeypatch.setattr(controladoria, "_try_jusbrasil_provider", await empty_provider("JusBrasil"))

    response = await controladoria.buscar_comunicaapi(FakeRequest(), db=SimpleNamespace())
    payload = json.loads(response.body.decode("utf-8"))

    assert response.status_code == 502
    assert payload["success"] is False
    assert payload["code"] == "invalid_client"
    assert payload["provider_status"] == "failed"
    assert payload["fallback_active"] is True
    assert payload["intimacoes"] == []
