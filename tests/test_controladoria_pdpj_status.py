import json
from types import SimpleNamespace

import pytest

from routes import controladoria


def _attempt(provider, status, reason, error="", count=0):
    return {
        "provider": provider,
        "status": status,
        "reason": reason,
        "error": error,
        "count": count,
        "attempted_at": "2026-05-03T18:00:00Z",
    }


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value

    def fetchall(self):
        return self.value if isinstance(self.value, list) else []


class _CaptureDB:
    def __init__(self, value):
        self.value = value
        self.query = ""
        self.params = {}

    def execute(self, query, params):
        self.query = str(query)
        self.params = params
        return _ScalarResult(self.value)


def test_safe_api_error_redacts_oauth_like_values():
    raw = (
        "Authorization=Bearer abc+/=._token "
        "access_token:'tok+/=._' "
        "refresh_token=ref+/=._ "
        "client_secret:\"s3cr3t+/=._\""
    )

    sanitized = controladoria._safe_api_error(raw)

    assert "abc+/=._token" not in sanitized
    assert "tok+/=._" not in sanitized
    assert "ref+/=._" not in sanitized
    assert "s3cr3t+/=._" not in sanitized
    assert "Bearer <redacted>" in sanitized
    assert "access_token:'<redacted>'" in sanitized
    assert "refresh_token=<redacted>" in sanitized
    assert "client_secret:\"<redacted>\"" in sanitized


def test_prazos_filters_keep_todos_unrestricted():
    query = controladoria._append_prazos_filters(
        "WHERE p.org_id = :org_id",
        {"org_id": 1},
        status_filter="todos",
    )

    assert "p.status NOT IN ('concluido')" not in query
    assert "p.status = :status_filter" not in query


def test_prazos_vencidos_total_uses_filtered_overdue_predicate():
    db = _CaptureDB(7)

    total = controladoria._get_prazos_vencidos_total(
        db,
        1,
        search="cliente",
        status_filter="todos",
        mes="2026-05",
        tribunal="TRT3",
    )

    assert total == 7
    assert "LOWER(c.case_number)" in db.query
    assert "p.status = 'perdido'" in db.query
    assert "COALESCE(p.status, '') != 'concluido'" in db.query
    assert "p.status NOT IN ('concluido')" not in db.query
    assert db.params["search"] == "%cliente%"
    assert db.params["ano"] == 2026
    assert db.params["mes"] == 5
    assert db.params["trib_pat"] == "%.5.03.%"


def test_prazos_limit_sorts_null_deadlines_last():
    db = _CaptureDB([])

    prazos = controladoria._get_prazos(db, 1, limit=10)

    assert prazos == []
    assert "CASE WHEN p.data_vencimento IS NULL THEN 1 ELSE 0 END ASC" in db.query
    assert "LIMIT :limit" in db.query
    assert db.params["limit"] == 10


@pytest.mark.asyncio
async def test_oab_chain_uses_comunicaapi_when_available(monkeypatch):
    async def comunicaapi(*args, **kwargs):
        return {
            "items": [{"numero_processo": "0001", "source": "ComunicaAPI PJE/CNJ"}],
            "attempt": _attempt("ComunicaAPI PJE/CNJ", "ok", "primary ok", count=1),
            "auth_status": "configured",
            "grant_attempted": "client_credentials",
            "source": "ComunicaAPI PJE/CNJ",
        }

    async def should_not_run(*args, **kwargs):
        raise AssertionError("fallback should not run when ComunicaAPI has items")

    monkeypatch.setattr(controladoria, "_try_comunicaapi_provider", comunicaapi)
    monkeypatch.setattr(controladoria, "_try_datajud_provider", should_not_run)

    result = await controladoria._search_intimacoes_oab_chain("209176", "MG", "", "")

    assert result["provider"] == "ComunicaAPI PJE/CNJ"
    assert result["provider_status"] == "ok"
    assert result["fallback_active"] is False
    assert result["auth_status"] == "configured"
    assert result["grant_attempted"] == "client_credentials"
    assert result["items"][0]["source"] == "ComunicaAPI PJE/CNJ"


@pytest.mark.asyncio
async def test_oab_chain_empty_comunicaapi_does_not_call_fallback(monkeypatch):
    async def comunicaapi(*args, **kwargs):
        return {
            "items": [],
            "attempt": _attempt("ComunicaAPI PJE/CNJ", "empty", "no results", count=0),
            "auth_status": "configured",
            "grant_attempted": "client_credentials",
            "source": "ComunicaAPI PJE/CNJ",
        }

    async def should_not_run(*args, **kwargs):
        raise AssertionError("fallback should only run on integration failure")

    monkeypatch.setattr(controladoria, "_try_comunicaapi_provider", comunicaapi)
    monkeypatch.setattr(controladoria, "_try_datajud_provider", should_not_run)

    result = await controladoria._search_intimacoes_oab_chain("209176", "MG", "", "")

    assert result["provider_status"] == "empty"
    assert result["fallback_active"] is False
    assert result["items"] == []


@pytest.mark.asyncio
async def test_oab_chain_falls_back_to_datajud_with_limited_import(monkeypatch):
    async def comunicaapi(*args, **kwargs):
        return {
            "items": [],
            "attempt": _attempt("ComunicaAPI PJE/CNJ", "failed", "no token", error="no_access_token"),
            "auth_status": "configured",
            "grant_attempted": "client_credentials",
        }

    async def datajud(*args, **kwargs):
        return {
            "items": [
                {
                    "numero_processo": "0001234-56.2024.8.13.0145",
                    "source": "DataJud (CNJ)",
                    "importable": False,
                }
            ],
            "attempt": _attempt("DataJud (CNJ)", "ok", "fallback process search", count=1),
        }

    async def no_items(provider):
        async def inner(*args, **kwargs):
            return {
                "items": [],
                "attempt": _attempt(provider, "empty", "none", count=0),
            }
        return inner

    monkeypatch.setattr(controladoria, "_try_comunicaapi_provider", comunicaapi)
    monkeypatch.setattr(controladoria, "_try_datajud_provider", datajud)
    monkeypatch.setattr(controladoria, "_try_escavador_provider", await no_items("Escavador"))
    monkeypatch.setattr(controladoria, "_try_jusbrasil_provider", await no_items("JusBrasil"))

    result = await controladoria._search_intimacoes_oab_chain("209176", "MG", "", "")

    assert result["provider"] == "DataJud (CNJ)"
    assert result["provider_status"] == "fallback_limited"
    assert result["fallback_active"] is True
    assert result["last_error"] == "no_access_token"
    assert result["items"][0]["importable"] is False
    assert [attempt["provider"] for attempt in result["fallback_chain"]] == [
        "ComunicaAPI PJE/CNJ",
        "DataJud (CNJ)",
        "Escavador",
        "JusBrasil",
    ]


@pytest.mark.asyncio
async def test_oab_chain_failure_is_visible_and_sanitized(monkeypatch):
    secret_error = "client_secret=super-secret-value access_token=eyJabcdef.eyJghijkl.signature"

    async def comunicaapi(*args, **kwargs):
        return {
            "items": [],
            "attempt": controladoria._provider_attempt(
                "ComunicaAPI PJE/CNJ",
                "failed",
                "bad credentials",
                error=secret_error,
            ),
            "auth_status": "configured",
            "grant_attempted": "client_credentials",
        }

    async def empty(provider):
        async def inner(*args, **kwargs):
            return {
                "items": [],
                "attempt": _attempt(provider, "empty", "none", count=0),
            }
        return inner

    monkeypatch.setattr(controladoria, "_try_comunicaapi_provider", comunicaapi)
    monkeypatch.setattr(controladoria, "_try_datajud_provider", await empty("DataJud (CNJ)"))
    monkeypatch.setattr(controladoria, "_try_escavador_provider", await empty("Escavador"))
    monkeypatch.setattr(controladoria, "_try_jusbrasil_provider", await empty("JusBrasil"))

    result = await controladoria._search_intimacoes_oab_chain("209176", "MG", "", "")
    serialized = json.dumps(result)

    assert result["provider_status"] == "failed"
    assert result["reason"]
    assert "super-secret-value" not in serialized
    assert "eyJabcdef" not in serialized
    assert "<redacted>" in serialized


@pytest.mark.asyncio
async def test_buscar_comunicaapi_returns_failed_diagnostics_when_all_sources_fail(monkeypatch):
    async def chain(*args, **kwargs):
        return {
            "items": [],
            "provider": "Nenhuma API",
            "provider_status": "failed",
            "reason": "PDPJ invalid_client e fallbacks vazios.",
            "last_error": "invalid_client",
            "fallback_active": True,
            "fallback_chain": [_attempt("ComunicaAPI PJE/CNJ", "failed", "no token")],
            "auth_status": "configured",
            "grant_attempted": "client_credentials",
            "source": None,
            "last_attempt_at": "2026-05-03T18:00:00Z",
            "code": "invalid_client",
        }

    class Request:
        state = SimpleNamespace(org_id=1)

        async def json(self):
            return {"numero_oab": "209176", "uf_oab": "MG"}

    monkeypatch.setattr(controladoria, "get_current_user", lambda request, db: object())
    monkeypatch.setattr(controladoria, "_search_intimacoes_oab_chain", chain)

    response = await controladoria.buscar_comunicaapi(Request(), db=object())
    body = json.loads(response.body.decode("utf-8"))

    assert response.status_code == 502
    assert body["success"] is False
    assert body["provider"] == "Nenhuma API"
    assert body["provider_status"] == "failed"
    assert body["fallback_active"] is True
    assert body["auth_status"] == "configured"
    assert body["grant_attempted"] == "client_credentials"
