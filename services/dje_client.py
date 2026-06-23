"""
CaseHub — Domicílio Judicial Eletrônico (DJE) Client.

API oficial do PDPJ/CNJ para o "Domicílio Judicial Eletrônico": consulta de
comunicações/intimações endereçadas ao titular (advogado, escritório ou órgão)
cadastrado no domicílio eletrônico.

Auth (validado ao vivo):
------------------------
1. OAuth2 ``client_credentials`` contra o Keycloak do PDPJ (o MESMO realm
   ``pje`` usado pela ComunicaAPI — ver services/comunicaapi.py):
       POST <SSO token URL>  grant_type=client_credentials, client_id, client_secret
   -> {access_token, expires_in, ...}
2. Chamada ao gateway DJE com ``Authorization: Bearer <access_token>``:
       GET  <base>/api/v1/eu             -> 200 (auth OK)
       GET  <base>/api/v1/comunicacoes   -> requer header ``tenantId`` (UUID) +
                                            query ``statusCiente`` + paginação
                                            (``page``, ``size``).

De onde vem o tenantId:
-----------------------
``GET /api/v1/eu`` retorna ``UsuarioPerfilViewModel`` com ``perfis[]``
(``PerfilViewModel``), cada um com ``tenantId`` (UUID string) + ``tenantName``.
Resolvemos o tenantId a partir do primeiro perfil que tenha um ``tenantId``
não-vazio e o cacheamos por org.

PROD vs HML:
------------
``settings.DJE_ENV`` ("prod" default | "hml") chaveia base URL + SSO token URL
(ver config.py). Tudo é env-overridable.

Segurança:
----------
- Credenciais por-tenant vêm de services/pdpj_credentials.py
  (``resolve_pdpj_client_credentials_from_runtime``) — NUNCA hardcoded.
- O httpx client poolado (services/pdpj_client.get_pdpj_client) é
  credential-free; Authorization e o corpo do token são 100% per-request.
- Token + tenantId são cacheados por-org em buckets isolados (sem bleed
  cross-tenant), espelhando o PDPJAuthClient da ComunicaAPI.

Degradação graciosa:
--------------------
Se as credenciais PDPJ não estiverem configuradas para a org, logamos um
warning e retornamos estrutura vazia (não crasha) — mesma postura da
ComunicaAPI.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from config import settings
from services.pdpj_client import get_pdpj_client

logger = logging.getLogger(__name__)


def _dje_base_url() -> str:
    """Resolve the DJE gateway base URL for the configured environment."""
    if str(getattr(settings, "DJE_ENV", "prod")).strip().lower() == "hml":
        return settings.DJE_HML_BASE_URL.rstrip("/")
    return settings.DJE_PROD_BASE_URL.rstrip("/")


def _dje_token_url() -> str:
    """Resolve the PDPJ Keycloak token URL for the configured environment."""
    if str(getattr(settings, "DJE_ENV", "prod")).strip().lower() == "hml":
        return settings.DJE_HML_SSO_TOKEN_URL
    return settings.DJE_PROD_SSO_TOKEN_URL


class DJEClient:
    """Async client for the PDPJ Domicílio Judicial Eletrônico gateway.

    Per-org isolated token + tenantId caches (no cross-tenant credential bleed,
    mirroring services/comunicaapi.PDPJAuthClient). Lazily authenticates via
    client_credentials and resolves tenantId from ``GET /api/v1/eu``.
    """

    # Default statusCiente filter for /comunicacoes. The gateway requires this
    # query param; "N" = comunicações ainda NÃO cientes (pendentes/novas) — o
    # caso de uso mais comum (puxar intimações novas). Override via arg.
    DEFAULT_STATUS_CIENTE = "N"

    TOKEN_TIMEOUT = 15.0
    API_TIMEOUT = 30.0
    # Renew slightly before expiry to avoid using a token that dies mid-flight.
    _EXPIRY_MARGIN = 30.0

    class _OrgState:
        __slots__ = ("access_token", "expires_at", "tenant_id")

        def __init__(self) -> None:
            self.access_token: Optional[str] = None
            self.expires_at: float = 0.0
            self.tenant_id: Optional[str] = None

    def __init__(self) -> None:
        self._state: Dict[int, "DJEClient._OrgState"] = {}
        self._locks: Dict[int, asyncio.Lock] = {}

    # ── per-org bucket helpers ──────────────────────────────────────────
    def _bucket(self, org_id: int) -> "DJEClient._OrgState":
        st = self._state.get(org_id)
        if st is None:
            st = self._OrgState()
            self._state[org_id] = st
        return st

    def _lock(self, org_id: int) -> asyncio.Lock:
        lock = self._locks.get(org_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[org_id] = lock
        return lock

    def _credentials_for(self, org_id: int):
        # Imported lazily (mirrors services/comunicaapi.py) so importing this
        # module never drags in the SQLAlchemy model stack — keeps the client
        # unit-testable without a DB / heavy deps.
        from services.pdpj_credentials import (
            resolve_pdpj_client_credentials_from_runtime,
        )

        return resolve_pdpj_client_credentials_from_runtime(org_id)

    def is_configured_for(self, org_id: int) -> bool:
        return self._credentials_for(org_id).configured

    async def invalidate_cache(self, org_id: int) -> None:
        """Drop the cached token + tenantId for an org (e.g. on 401/403)."""
        async with self._lock(org_id):
            st = self._bucket(org_id)
            st.access_token = None
            st.expires_at = 0.0
            st.tenant_id = None

    # ── auth ────────────────────────────────────────────────────────────
    async def _get_access_token(self, org_id: int) -> Optional[str]:
        """Return a valid access_token for the org, refreshing if needed."""
        credentials = self._credentials_for(org_id)
        if not credentials.configured:
            logger.warning(
                "DJE: credenciais PDPJ ausentes para org_id=%s — pulando auth.",
                org_id,
            )
            return None

        st = self._bucket(org_id)
        if st.access_token and time.time() < st.expires_at - self._EXPIRY_MARGIN:
            return st.access_token

        async with self._lock(org_id):
            # Double-check after acquiring the lock.
            if st.access_token and time.time() < st.expires_at - self._EXPIRY_MARGIN:
                return st.access_token

            data = {
                "grant_type": "client_credentials",
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret,
            }
            try:
                client = get_pdpj_client()
                resp = await client.post(
                    _dje_token_url(),
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=self.TOKEN_TIMEOUT,
                )
                resp.raise_for_status()
                token_data = resp.json()
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                # Never log the request body (it carries the client_secret).
                logger.error(
                    "DJE: falha ao obter access_token (org_id=%s): %s",
                    org_id, type(exc).__name__,
                )
                st.access_token = None
                st.expires_at = 0.0
                return None

            access_token = token_data.get("access_token")
            if not access_token:
                logger.error("DJE: token endpoint não retornou access_token (org_id=%s)", org_id)
                st.access_token = None
                st.expires_at = 0.0
                return None

            try:
                expires_in = int(token_data.get("expires_in", 300))
            except (TypeError, ValueError):
                expires_in = 300
            st.access_token = access_token
            st.expires_at = time.time() + expires_in
            logger.info("DJE: access_token obtido (org_id=%s), expira em %ds", org_id, expires_in)
            return access_token

    def _auth_headers(self, access_token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

    # ── tenantId resolution ─────────────────────────────────────────────
    async def _resolve_tenant_id(self, org_id: int, access_token: str) -> Optional[str]:
        """Resolve (and cache per-org) the DJE tenantId via GET /api/v1/eu.

        The tenantId is the UUID found on the user's first profile
        (``UsuarioPerfilViewModel.perfis[].tenantId``). It is required as a
        header on /comunicacoes and most write endpoints.
        """
        st = self._bucket(org_id)
        if st.tenant_id:
            return st.tenant_id

        try:
            client = get_pdpj_client()
            resp = await client.get(
                f"{_dje_base_url()}/api/v1/eu",
                headers=self._auth_headers(access_token),
                timeout=self.API_TIMEOUT,
            )
            resp.raise_for_status()
            eu = resp.json() or {}
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            logger.error(
                "DJE: falha ao resolver tenantId via /api/v1/eu (org_id=%s): %s",
                org_id, type(exc).__name__,
            )
            return None

        tenant_id = self._extract_tenant_id(eu)
        if tenant_id:
            st.tenant_id = tenant_id
            logger.info("DJE: tenantId resolvido para org_id=%s", org_id)
        else:
            logger.warning(
                "DJE: nenhum tenantId encontrado em /api/v1/eu (org_id=%s).", org_id
            )
        return tenant_id

    @staticmethod
    def _extract_tenant_id(eu: Dict[str, Any]) -> Optional[str]:
        """Pull the first non-empty tenantId from an /api/v1/eu payload."""
        perfis = eu.get("perfis") or []
        if isinstance(perfis, list):
            for perfil in perfis:
                if isinstance(perfil, dict):
                    tid = perfil.get("tenantId")
                    if tid:
                        return str(tid)
        # Defensive fallbacks if the schema ever flattens the field.
        for key in ("tenantId", "tenant_id"):
            if eu.get(key):
                return str(eu[key])
        return None

    # ── comunicações (intimações) ───────────────────────────────────────
    async def listar_comunicacoes(
        self,
        org_id: int,
        *,
        status_ciente: Optional[str] = None,
        data_inicio: Optional[str] = None,
        data_fim: Optional[str] = None,
        numero_processo: Optional[str] = None,
        page: int = 0,
        size: int = 20,
    ) -> Dict[str, Any]:
        """List DJE comunicações (intimações) for the org's tenant.

        Returns a dict ``{items, count, page, size, total_pages, source}``.
        On missing credentials / auth failure / tenantId failure it returns an
        empty result with an ``error`` key — it never raises to the caller.
        """
        empty = lambda reason, error=None: {  # noqa: E731 - terse local helper
            "items": [],
            "count": 0,
            "page": page,
            "size": size,
            "total_pages": 0,
            "source": f"DJE/PDPJ ({reason})",
            **({"error": error} if error else {}),
        }

        if not self.is_configured_for(org_id):
            logger.warning(
                "DJE: credenciais PDPJ ausentes para org_id=%s — retornando vazio.",
                org_id,
            )
            return empty("inativo — credenciais PDPJ ausentes", "missing_credentials")

        access_token = await self._get_access_token(org_id)
        if not access_token:
            return empty("erro auth PDPJ", "auth_failure")

        tenant_id = await self._resolve_tenant_id(org_id, access_token)
        if not tenant_id:
            return empty("tenantId não resolvido", "missing_tenant_id")

        params: Dict[str, Any] = {
            "statusCiente": status_ciente or self.DEFAULT_STATUS_CIENTE,
            "page": page,
            "size": size,
        }
        if data_inicio:
            params["dataInicio"] = data_inicio
        if data_fim:
            params["dataFim"] = data_fim
        if numero_processo:
            params["numeroProcesso"] = numero_processo

        headers = self._auth_headers(access_token)
        headers["tenantId"] = tenant_id

        try:
            client = get_pdpj_client()
            resp = await client.get(
                f"{_dje_base_url()}/api/v1/comunicacoes",
                params=params,
                headers=headers,
                timeout=self.API_TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json() or {}
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.error("DJE: /comunicacoes HTTP %s (org_id=%s)", status, org_id)
            if status in (401, 403):
                await self.invalidate_cache(org_id)
            return empty(f"HTTP {status}", f"http_{status}")
        except httpx.RequestError as exc:
            logger.error("DJE: erro de rede em /comunicacoes (org_id=%s): %s",
                         org_id, type(exc).__name__)
            return empty("erro de rede", "network")

        # RespostaPaginadaComunicacaoProcessualViewModel: {page: Paginacao, data: [...]}
        raw_items = payload.get("data") or payload.get("items") or []
        page_info = payload.get("page") or {}
        normalized = [self._normalize(it) for it in raw_items if isinstance(it, dict)]

        return {
            "items": normalized,
            "count": _safe_int(page_info.get("totalElements"), len(normalized)),
            "page": _safe_int(page_info.get("number"), page),
            "size": _safe_int(page_info.get("size"), size),
            "total_pages": _safe_int(page_info.get("totalPages"), 0),
            "source": "DJE/PDPJ",
        }

    @staticmethod
    def _normalize(item: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a ComunicacaoProcessualViewModel into a clean CaseHub dict."""
        def first(*keys: str) -> Any:
            for key in keys:
                value = item.get(key)
                if value not in (None, ""):
                    return value
            return ""

        return {
            "numero_comunicacao": first("numeroComunicacao"),
            "numero_processo": first("numeroProcesso"),
            "tribunal": first("tribunalOrigem"),
            "uf": first("uf"),
            "orgao": first("orgaoLegal", "varaJudicial"),
            "instancia": first("instancia"),
            "assunto": first("assunto"),
            "classe": first("classe"),
            "tipo_comunicacao": first("tipoComunicacao"),
            "tipo_intimacao": first("tipoIntimacao"),
            "data_disponibilizacao": first("dataComunicacao"),
            "data_final_ciencia": first("dataFinalCiencia"),
            "prazo": first("prazo"),
            "tipo_prazo": first("tipoPrazo"),
            "urgente": first("urgente"),
            "segredo_justica": item.get("segredoJustica", False),
            "ciente": item.get("ciente", False),
            "status": first("status"),
            "meio_envio": first("meioEnvio"),
            "parte_interessada": first("parteInteressada"),
            "links_documentos": item.get("linksDocumentos") or [],
            "source": "DJE/PDPJ",
        }


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# Singleton client
dje_client = DJEClient()
