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


class _FetchOneResult:
    def __init__(self, value):
        self.value = value

    def fetchone(self):
        return self.value


class _CaptureDB:
    def __init__(self, value):
        self.value = value
        self.query = ""
        self.params = {}

    def execute(self, query, params):
        self.query = str(query)
        self.params = params
        return _ScalarResult(self.value)

    def get_bind(self):
        # Mirror the SQLAlchemy Session interface; None -> SQLite ORDER BY path.
        return None


class _ImportDB:
    def __init__(self):
        self.inserts = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, query, params):
        query_text = str(query)
        if "SELECT COUNT(*) FROM prazos_processuais" in query_text:
            return _ScalarResult(0)
        if "SELECT id FROM cases" in query_text:
            return _FetchOneResult(None)
        if "INSERT INTO prazos_processuais" in query_text:
            self.inserts.append((query_text, params))
            return _ScalarResult(None)
        raise AssertionError(query_text)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _ImportRequest:
    def __init__(self, intimacoes):
        self.state = SimpleNamespace(org_id=1)
        self._intimacoes = intimacoes

    async def json(self):
        return {"intimacoes": self._intimacoes}


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


def test_prazos_vencidos_total_uses_filtered_overdue_predicate(monkeypatch):
    calls = []

    def fake_get_prazos(db, org_id, **kwargs):
        calls.append({"db": db, "org_id": org_id, **kwargs})
        return [
            {"urgencia": "vencido"},
            {"urgencia": "fatal"},
            {"urgencia": "vencido"},
            {"urgencia": "verde"},
        ]

    db = object()
    monkeypatch.setattr(controladoria, "_get_prazos", fake_get_prazos)

    total = controladoria._get_prazos_vencidos_total(
        db,
        1,
        search="cliente",
        status_filter="todos",
        mes="2026-05",
        tribunal="TRT3",
    )

    assert total == 2
    assert calls == [{
        "db": db,
        "org_id": 1,
        "search": "cliente",
        "status_filter": "todos",
        "mes": "2026-05",
        "tribunal": "TRT3",
    }]


def test_prazos_limit_sorts_null_deadlines_last(monkeypatch):
    monkeypatch.setattr(controladoria, "_ensure_controladoria_schema", lambda db: None)
    monkeypatch.setattr(
        controladoria,
        "_get_user_directory",
        lambda db, org_id: {"users": [], "by_id": {}, "by_name": {}},
    )
    db = _CaptureDB([])

    prazos = controladoria._get_prazos(db, 1, limit=10)

    assert prazos == []
    assert "CASE WHEN p.data_vencimento IS NULL THEN 1 ELSE 0 END ASC" in db.query
    assert "LIMIT :limit" in db.query
    assert db.params["limit"] == 10


def test_publication_fallback_items_are_not_auto_importable():
    item = controladoria._normalize_publication_item(
        {
            "id": "pub-1",
            "texto": "Prazo de 5 dias para manifestar.",
            "data": "2026-06-03",
            "numero_processo": "0001",
        },
        "Escavador",
    )

    assert item["importable"] is False


def test_deadline_source_metadata_requires_official_pdpj_source():
    official = controladoria._deadline_source_metadata({
        "source": "ComunicaAPI PJE/CNJ",
        "importable": True,
        "id": "com-1",
    })
    fallback = controladoria._deadline_source_metadata({
        "source": "DataJud (CNJ)",
        "importable": True,
        "id": "datajud-1",
    })

    assert official["official_source"] is True
    assert official["source_status"] == "official"
    assert fallback["official_source"] is False
    assert fallback["source_status"] == "manual_review_required"


def test_deadline_source_signature_is_required_for_official_import():
    item = {
        "source": "ComunicaAPI PJE/CNJ",
        "importable": True,
        "id": "com-1",
    }

    assert controladoria._valid_deadline_source_signature(item, org_id=1) is False
    item["source_signature"] = controladoria._deadline_source_signature(1, item)
    assert controladoria._valid_deadline_source_signature(item, org_id=1) is True
    assert controladoria._valid_deadline_source_signature(item, org_id=2) is False


def test_comunicaapi_normalizes_camelcase_payload():
    from services.comunicaapi import ComunicaAPIClient

    item = ComunicaAPIClient()._normalize_item({
        "numeroComunicacao": "123",
        "numeroProcessoComMascara": "0001234-56.2026.8.13.0001",
        "siglaTribunal": "TJMG",
        "nomeOrgao": "1a Vara",
        "tipoComunicacao": "Intimacao",
        "textoComunicacao": "Prazo de 5 dias para manifestar.",
        "dataDisponibilizacao": "2026-06-03",
    })

    assert item["id"] == "123"
    assert item["numero_processo"] == "0001234-56.2026.8.13.0001"
    assert item["data_disponibilizacao"] == "2026-06-03"
    assert item["texto"] == "Prazo de 5 dias para manifestar."


@pytest.mark.asyncio
async def test_importar_intimacoes_blocks_non_official_sources(monkeypatch):
    monkeypatch.setattr(controladoria, "get_current_user", lambda request, db: SimpleNamespace(user_type="admin"))
    monkeypatch.setattr(controladoria, "has_permission", lambda *args: True)
    db = _ImportDB()

    response = await controladoria.importar_intimacoes(
        _ImportRequest([
            {
                "numero_processo": "0001234-56.2026.8.13.0001",
                "texto": "Prazo de 5 dias para manifestar.",
                "data_disponibilizacao": "2026-06-03",
                "source": "DataJud (CNJ)",
                "importable": False,
            }
        ]),
        db=db,
    )
    body = json.loads(response.body.decode("utf-8"))

    assert response.status_code == 200
    assert body["imported"] == 0
    assert body["blocked"] == 1
    assert db.inserts == []
    assert db.commits == 1


@pytest.mark.asyncio
async def test_importar_intimacoes_blocks_official_item_without_extracted_days(monkeypatch):
    monkeypatch.setattr(controladoria, "get_current_user", lambda request, db: SimpleNamespace(user_type="admin"))
    monkeypatch.setattr(controladoria, "has_permission", lambda *args: True)
    db = _ImportDB()
    item = {
        "numero_processo": "0001234-56.2026.8.13.0001",
        "texto": "Intimação sem prazo numérico expresso.",
        "data_disponibilizacao": "2026-06-03",
        "source": "ComunicaAPI PJE/CNJ",
        "importable": True,
    }
    item["source_signature"] = controladoria._deadline_source_signature(1, item)

    response = await controladoria.importar_intimacoes(
        _ImportRequest([item]),
        db=db,
    )
    body = json.loads(response.body.decode("utf-8"))

    assert body["imported"] == 0
    assert body["blocked"] == 1
    assert db.inserts == []


@pytest.mark.asyncio
async def test_importar_intimacoes_records_official_source_metadata(monkeypatch):
    monkeypatch.setattr(controladoria, "get_current_user", lambda request, db: SimpleNamespace(user_type="admin"))
    monkeypatch.setattr(controladoria, "has_permission", lambda *args: True)
    db = _ImportDB()
    item = {
        "id": "comunicacao-123",
        "numero_processo": "0001234-56.2026.8.13.0001",
        "texto": "Prazo de 5 dias para manifestar.",
        "data_disponibilizacao": "2026-06-03",
        "source": "ComunicaAPI PJE/CNJ",
        "importable": True,
    }
    item["source_signature"] = controladoria._deadline_source_signature(1, item)

    response = await controladoria.importar_intimacoes(
        _ImportRequest([item]),
        db=db,
    )
    body = json.loads(response.body.decode("utf-8"))
    _, params = db.inserts[0]

    assert response.status_code == 200
    assert body["imported"] == 1
    assert body["blocked"] == 0
    assert params["source_provider"] == "ComunicaAPI PJE/CNJ"
    assert params["source_status"] == "official"
    assert params["source_reference"] == "comunicacao-123"
    assert len(params["source_payload_hash"]) == 64
    assert params["official_source"] is True
    assert params["calculation_engine_version"] == controladoria.PRAZOS_CALCULATION_ENGINE_VERSION
    assert params["data_inicio"] > params["data_intimacao"]


@pytest.mark.asyncio
async def test_importar_intimacoes_blocks_spoofed_official_source_without_signature(monkeypatch):
    monkeypatch.setattr(controladoria, "get_current_user", lambda request, db: SimpleNamespace(user_type="admin"))
    monkeypatch.setattr(controladoria, "has_permission", lambda *args: True)
    db = _ImportDB()

    response = await controladoria.importar_intimacoes(
        _ImportRequest([
            {
                "id": "forged-1",
                "numero_processo": "0001234-56.2026.8.13.0001",
                "texto": "Prazo de 5 dias para manifestar.",
                "data_disponibilizacao": "2026-06-03",
                "source": "ComunicaAPI PJE/CNJ",
                "importable": True,
            }
        ]),
        db=db,
    )
    body = json.loads(response.body.decode("utf-8"))

    assert body["imported"] == 0
    assert body["blocked"] == 1
    assert db.inserts == []


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
async def test_comunicaapi_auth_status_uses_requested_org(monkeypatch):
    from services import comunicaapi as comunica_mod

    calls = []

    async def buscar_por_oab(*args, **kwargs):
        return {
            "items": [],
            "error": "http_403",
            "source": "ComunicaAPI PJE/CNJ (HTTP 403)",
        }

    class FakeAuth:
        def public_status(self, org_id=None):
            calls.append(org_id)
            return {"configured": org_id == 4}

        def _state(self, org_id=None):
            return SimpleNamespace(last_grant_type="client_credentials")

    monkeypatch.setattr(comunica_mod, "comunicaapi_client", SimpleNamespace(buscar_por_oab=buscar_por_oab))
    monkeypatch.setattr(comunica_mod, "pdpj_auth", FakeAuth())

    result = await controladoria._try_comunicaapi_provider(
        "209176",
        "RJ",
        "2026-06-01",
        "2026-06-05",
        org_id=4,
    )

    assert result["auth_status"] == "configured"
    assert result["grant_attempted"] == "client_credentials"
    assert calls == [4]


@pytest.mark.asyncio
async def test_oab_chain_keeps_primary_pdpj_failure_reason(monkeypatch):
    async def comunica(*args, **kwargs):
        return {
            "items": [],
            "attempt": _attempt(
                "ComunicaAPI PJE/CNJ",
                "failed",
                "ComunicaAPI/CNJ negou acesso ao recurso.",
                error="http_403",
            ),
            "auth_status": "configured",
            "grant_attempted": "client_credentials",
            "source": "ComunicaAPI PJE/CNJ (HTTP 403)",
        }

    async def empty_provider(*args, **kwargs):
        return {"items": [], "attempt": _attempt("Fallback", "empty", "sem itens")}

    monkeypatch.setattr(controladoria, "_try_comunicaapi_provider", comunica)
    monkeypatch.setattr(controladoria, "_try_datajud_provider", empty_provider)
    monkeypatch.setattr(controladoria, "_try_escavador_provider", empty_provider)
    monkeypatch.setattr(controladoria, "_try_jusbrasil_provider", empty_provider)

    result = await controladoria._search_intimacoes_oab_chain(
        "209176",
        "RJ",
        "2026-06-01",
        "2026-06-05",
        org_id=4,
    )

    assert result["provider_status"] == "failed"
    assert result["code"] == "http_403"
    assert result["auth_status"] == "configured"
    assert "ComunicaAPI/CNJ negou acesso" in result["reason"]
    assert "Fallbacks nao retornaram" in result["reason"]


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

    # buscar_comunicaapi now closes `db` before awaiting the search chain
    # (2026-07-01 outage pattern, db-session-leak fix) — the fake `db` needs
    # a no-op close() to match the real Session's contract.
    response = await controladoria.buscar_comunicaapi(Request(), db=SimpleNamespace(close=lambda: None))
    body = json.loads(response.body.decode("utf-8"))

    assert response.status_code == 502
    assert body["success"] is False
    assert body["provider"] == "Nenhuma API"
    assert body["provider_status"] == "failed"
    assert body["fallback_active"] is True
    assert body["auth_status"] == "configured"
    assert body["grant_attempted"] == "client_credentials"
