import json
from types import SimpleNamespace

import httpx
import pytest


def _http_status_error(status_code=400, payload=None):
    request = httpx.Request("POST", "https://sso.cloud.pje.jus.br/token")
    response = httpx.Response(status_code, json=payload or {"error": "invalid_client"}, request=request)
    return httpx.HTTPStatusError("PDPJ rejected credentials", request=request, response=response)


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
    auth.client_id = "vieira-sales-adv"
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

    result = await comunicaapi.ComunicaAPIClient().buscar_por_oab("209176", "MG")

    assert result["count"] == 0
    assert result["error"] == "missing_credentials"
    assert "message" in result


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
