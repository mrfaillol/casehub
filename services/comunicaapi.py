"""
CaseHub — ComunicaAPI PJE/CNJ Client (v2 — OAuth2 PDPJ)

API oficial do CNJ para consulta de intimações/comunicações processuais.

CONTEXTO v2 (Abril/2026):
-------------------------
Em 03/Nov/2025 o CNJ passou a exigir autenticação 2FA/MFA para acesso à
ComunicaAPI via PDPJ (Plataforma de Democratização do Poder Judiciário).
A partir de 18/Mai/2026 isso vira obrigatório geral. Por isso essa v2
implementa OAuth2 (authorization_code + refresh_token) contra o Keycloak
do PDPJ em `https://sso.cloud.pje.jus.br/auth/realms/pje`.

Docs:
- API: https://comunicaapi.pje.jus.br/swagger/index.html
- Auth: https://www.pdpj.jus.br/documentacao/
- Cadastro de aplicação: https://domicilio-eletronico.pdpj.jus.br

Variáveis de ambiente necessárias (.env):
    PDPJ_CLIENT_ID=<seu_client_id_do_PDPJ>        # obrigatório
    PDPJ_CLIENT_SECRET=<seu_client_secret>        # obrigatório
    PDPJ_REFRESH_TOKEN=<refresh_token_longo>      # opcional (fallback)

Estratégia de autenticação (em ordem):
1. **client_credentials** (primário): server-to-server, não precisa refresh_token.
   Funciona quando o cliente OAuth2 está configurado como confidential + service
   account no Keycloak do PDPJ. É o fluxo em produção na instância de produção.
2. **refresh_token** (fallback): usado se client_credentials falhar. O refresh_token
   pode vir do `.env` (PDPJ_REFRESH_TOKEN) OU do banco de dados em
   `organizations.settings->>'pdpj_refresh_token'`, persistido pelo fluxo
   authorization_code em /casehub/oauth/pdpj/callback.

Isso quer dizer: a VARIÁVEL `PDPJ_REFRESH_TOKEN` do .env **não é obrigatória**
se o grant type client_credentials estiver disponível. Está mantida como
compatibilidade + fallback para instâncias que dependem de authorization_code.

Usage:
    from services.comunicaapi import comunicaapi_client

    resultado = await comunicaapi_client.buscar_por_oab("123456", "MG")
    resultado = await comunicaapi_client.buscar_por_oab("123456", "MG",
        data_inicio="2026-03-01", data_fim="2026-04-01")

Fallback:
    Se credenciais PDPJ não estiverem configuradas, o cliente loga warning
    e retorna estrutura vazia (não crasha). Isso permite que o sistema
    continue operacional enquanto Example User configura o PDPJ.
"""
import asyncio
import hashlib
import httpx
import logging
import os
import re
import time
from datetime import date, timedelta
from typing import Optional, List, Dict, Any
from config import settings
from services.pdpj_client import get_pdpj_client

logger = logging.getLogger(__name__)

# ──────────── Constantes ────────────

COMUNICAAPI_BASE_URL = "https://comunicaapi.pje.jus.br/api/v1"
PDPJ_TOKEN_URL = "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/token"

# Mock data para DEMO_MODE — intimações fictícias
_DEMO_INTIMACOES = {
    "items": [
        {"tribunal": "PJE / TJMG", "processo": "0001234-56.2024.8.13.0145", "tipo": "Intimação", "texto": "Intimação para manifestação sobre laudo pericial. Prazo: 15 dias úteis.", "data": "2026-04-08", "advogados": [{"nome": "Dr. Carlos Silva", "oab": "MG 654.321"}]},
        {"tribunal": "PJE / TRT 3ª Região", "processo": "0007890-12.2025.5.03.0037", "tipo": "Intimação", "texto": "Audiência de instrução e julgamento designada para 22/04/2026 às 14:00.", "data": "2026-04-07", "advogados": [{"nome": "Dr. Carlos Silva", "oab": "MG 654.321"}]},
        {"tribunal": "PJE / TRF 1ª Região", "processo": "0005678-34.2024.4.01.3801", "tipo": "Despacho", "texto": "Intime-se a parte autora para se manifestar em 10 dias sobre os embargos.", "data": "2026-04-06", "advogados": [{"nome": "Dra. Ana Santos", "oab": "MG 789.012"}]},
        {"tribunal": "PJE / TJMG", "processo": "0003456-78.2025.8.13.0145", "tipo": "Publicação", "texto": "Sentença proferida. Procedente o pedido para condenar a ré ao pagamento de R$ 45.000,00.", "data": "2026-04-05", "advogados": [{"nome": "Dr. Carlos Silva", "oab": "MG 654.321"}]},
        {"tribunal": "PJE / TRT 3ª Região", "processo": "0009012-45.2025.5.03.0037", "tipo": "Intimação", "texto": "Prazo para apresentação de contrarrazões ao recurso ordinário. 8 dias úteis.", "data": "2026-04-04", "advogados": [{"nome": "Dra. Ana Santos", "oab": "MG 789.012"}]},
    ],
    "count": 5,
    "source": "ComunicaAPI PJE/CNJ (demo)",
}

PDPJ_PUBLIC_ERROR_MESSAGES = {
    "missing_org_id": "Tenant nao identificado para a consulta PDPJ.",
    "missing_credentials": "Credenciais PDPJ ausentes. Configure credenciais do tenant ou PDPJ_CLIENT_ID/PDPJ_CLIENT_SECRET.",
    "tenant_credentials_incomplete": "Credenciais PDPJ do tenant incompletas. Regrave client_id e secret_id.",
    "tenant_credentials_decrypt_failed": "Credenciais PDPJ do tenant nao puderam ser lidas. Regrave a credencial.",
    "invalid_client": "O CNJ/PDPJ rejeitou o client_id/client_secret configurado.",
    "invalid_grant": "O token PDPJ expirou ou foi revogado. Reconecte a integracao.",
    "unauthorized_client": "O cliente PDPJ nao esta autorizado para este grant type.",
    "no_access_token": "O PDPJ nao retornou access_token para a consulta.",
    "empty_token_response": "O PDPJ respondeu sem access_token.",
    "network": "Erro de rede ao contactar o PDPJ/CNJ.",
}

_OAUTH_SECRET_RE = re.compile(
    r"(?i)\b(client_secret|access_token|refresh_token|id_token|authorization)"
    r"([\"']?\s*[:=]\s*[\"']?)([^\"'\s,&}]+)"
)
_BEARER_RE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+")


def _safe_oauth_error(value: str) -> str:
    """Redact OAuth-like values before diagnostics/logging."""
    text = str(value or "")
    text = _OAUTH_SECRET_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}<redacted>", text)
    return _BEARER_RE.sub(r"\1<redacted>", text)


# ──────────── PDPJ OAuth2 Client ────────────

class PDPJAuthClient:
    """
    Gerencia autenticação OAuth2 contra o PDPJ (Keycloak).

    Dois modos de autenticação (auto-detectados):

    1. **client_credentials** (primário): usa apenas client_id + client_secret.
       O CNJ configura o client com serviceAccountsEnabled=true e emite
       as credenciais diretamente. Não precisa de refresh_token.

    2. **refresh_token** (fallback): usa client_id + client_secret + refresh_token
       obtido via authorization_code flow (/casehub/oauth/pdpj/connect).
       Usado quando o CNJ exige que o titular da OAB autorize explicitamente.

    Cache simples em memória: access_token tem ~5 minutos; refresh
    on-demand na chamada de get_access_token() quando estiver expirado
    (com margem de 30s) e protegido por lock para evitar race conditions.
    """

    # Default tenant bucket used when a caller does not (yet) thread org_id.
    # NOTE: this is a compatibility fallback, NOT a shared cross-tenant cache —
    # each org_id gets its own isolated _OrgTokenState (see _state()).
    DEFAULT_ORG_ID = 1

    class _OrgTokenState:
        """Per-tenant OAuth token state. Isolated so org A's PDPJ access_token
        / refresh_token can never be reused to authenticate org B's queries
        (IDOR C6 — cross-tenant credential bleed via the old singleton)."""

        __slots__ = (
            "access_token",
            "expires_at",
            "refresh_token",
            "db_token_loaded",
            "last_grant_type",
            "last_error_code",
            "last_error_status",
            "last_error_description",
        )

        def __init__(self, refresh_token: str = ""):
            self.access_token: Optional[str] = None
            self.expires_at: float = 0.0
            self.refresh_token: str = refresh_token
            self.db_token_loaded: bool = False
            self.last_grant_type: Optional[str] = None
            self.last_error_code: Optional[str] = None
            self.last_error_status: Optional[int] = None
            self.last_error_description: Optional[str] = None

    def __init__(self):
        # Env credentials remain a compatibility fallback. Tenant-scoped DB
        # credentials take precedence via _client_credentials_for(org_id).
        self.client_id = os.getenv("PDPJ_CLIENT_ID", "")
        self.client_secret = os.getenv("PDPJ_CLIENT_SECRET", "")
        # Env-level refresh_token seeds ONLY the default-org bucket; other orgs
        # load their own token from organizations.settings (per-tenant).
        self._env_refresh_token = os.getenv("PDPJ_REFRESH_TOKEN", "")
        # Per-org token state + per-org locks (no shared mutable token state).
        self._tokens: Dict[int, "PDPJAuthClient._OrgTokenState"] = {}
        self._locks: Dict[int, asyncio.Lock] = {}
        self._registry_lock = asyncio.Lock()

    def _state(self, org_id: Optional[int]) -> "PDPJAuthClient._OrgTokenState":
        """Return (creating if needed) the isolated token state for an org."""
        oid = org_id if org_id is not None else self.DEFAULT_ORG_ID
        st = self._tokens.get(oid)
        if st is None:
            seed = self._env_refresh_token if oid == self.DEFAULT_ORG_ID else ""
            st = self._OrgTokenState(refresh_token=seed)
            self._tokens[oid] = st
        return st

    def _lock_for(self, org_id: Optional[int]) -> asyncio.Lock:
        """Return (creating if needed) the per-org asyncio lock."""
        oid = org_id if org_id is not None else self.DEFAULT_ORG_ID
        lock = self._locks.get(oid)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[oid] = lock
        return lock

    # ── Backward-compat shims for legacy callers (pdpj_oauth.py, controladoria.py,
    #    integrations.py) that read/write attributes on the default-org bucket. ──
    @property
    def refresh_token(self) -> str:
        return self._state(self.DEFAULT_ORG_ID).refresh_token

    @refresh_token.setter
    def refresh_token(self, value: str) -> None:
        self._state(self.DEFAULT_ORG_ID).refresh_token = value or ""

    @property
    def _access_token(self) -> Optional[str]:
        return self._state(self.DEFAULT_ORG_ID).access_token

    @_access_token.setter
    def _access_token(self, value: Optional[str]) -> None:
        self._state(self.DEFAULT_ORG_ID).access_token = value

    @property
    def _expires_at(self) -> float:
        return self._state(self.DEFAULT_ORG_ID).expires_at

    @_expires_at.setter
    def _expires_at(self, value: float) -> None:
        self._state(self.DEFAULT_ORG_ID).expires_at = value

    @property
    def _last_grant_type(self) -> Optional[str]:
        return self._state(self.DEFAULT_ORG_ID).last_grant_type

    def _clear_last_error(self, org_id: Optional[int] = None) -> None:
        st = self._state(org_id)
        st.last_error_code = None
        st.last_error_status = None
        st.last_error_description = None

    def _set_last_error(
        self,
        code: str,
        status: Optional[int] = None,
        description: Optional[str] = None,
        org_id: Optional[int] = None,
    ) -> None:
        st = self._state(org_id)
        st.last_error_code = code
        st.last_error_status = status
        st.last_error_description = (description or "")[:240] or None

    @property
    def last_error_code(self) -> Optional[str]:
        return self._state(self.DEFAULT_ORG_ID).last_error_code

    def _client_credentials_for(self, org_id: Optional[int] = None):
        """Resolve tenant credentials, then env fallback if the tenant is unset."""
        from services.pdpj_credentials import resolve_pdpj_client_credentials_from_runtime

        return resolve_pdpj_client_credentials_from_runtime(
            org_id,
            env_client_id=self.client_id,
            env_client_secret=self.client_secret,
        )

    def is_configured_for(self, org_id: Optional[int] = None) -> bool:
        return self._client_credentials_for(org_id).configured

    def public_status(self, org_id: Optional[int] = None) -> Dict[str, Any]:
        """Return sanitized auth state for admin diagnostics and UI responses."""
        st = self._state(org_id)
        credentials = self._client_credentials_for(org_id)
        expires_in = int(max(st.expires_at - time.time(), 0)) if st.access_token else 0
        return {
            "configured": credentials.configured,
            "credential_source": credentials.source,
            "credential_error": credentials.error,
            "has_client_id": bool(credentials.client_id),
            "has_client_secret": bool(credentials.client_secret),
            "client_id_fingerprint": credentials.client_id_fingerprint,
            "client_secret_fingerprint": credentials.client_secret_fingerprint,
            "has_refresh_token": bool(st.refresh_token),
            "token_cached": bool(st.access_token and expires_in > 0),
            "token_expires_in_seconds": expires_in,
            "last_grant_type": st.last_grant_type,
            "last_error_code": st.last_error_code,
            "last_error_status": st.last_error_status,
            "last_error_message": public_pdpj_error_message(st.last_error_code),
        }

    def load_token_from_db(self, org_id: int = 1) -> None:
        """
        Try to load refresh_token from organizations.settings JSONB into the
        per-org token bucket. Called lazily on first get_access_token() when the
        org's refresh_token is empty, regardless of whether client_id/secret are
        configured (so /callback authorization_code flow pode persistir o token
        no DB e o cliente ler de lá). Only attempts once per org to avoid
        repeated DB hits on misconfigured instances.
        """
        st = self._state(org_id)
        if st.refresh_token or st.db_token_loaded:
            return
        st.db_token_loaded = True
        db = None
        try:
            from models.base import SessionLocal
            from sqlalchemy import text
            db = SessionLocal()
            result = db.execute(
                text("SELECT settings->>'pdpj_refresh_token' FROM organizations WHERE id = :id"),
                {"id": org_id},
            )
            row = result.fetchone()
            if row and row[0]:
                st.refresh_token = row[0]
                logger.info("PDPJ: refresh_token loaded from database (org_id=%s)", org_id)
        except Exception as e:
            logger.debug("PDPJ: could not load token from DB: %s", e)
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass

    @property
    def is_configured(self) -> bool:
        """True se client_id + client_secret estão presentes.
        refresh_token é opcional (client_credentials não precisa)."""
        return self.is_configured_for(self.DEFAULT_ORG_ID)

    def _has_refresh_token(self, org_id: Optional[int] = None) -> bool:
        """True se refresh_token está disponível (para fallback grant)."""
        return bool(self._state(org_id).refresh_token)

    async def get_access_token(self, org_id: int = 1) -> Optional[str]:
        """
        Retorna access_token válido PARA O ORG informado. Renova automaticamente
        se expirado. Cada org usa seu próprio bucket de token + lock — nunca
        compartilha access_token/refresh_token entre tenants (IDOR C6).

        Estratégia:
        1. Tenta client_credentials grant (sem refresh_token)
        2. Se falhar e tiver refresh_token (env/DB do org), tenta refresh_token grant
        3. Se ambos falharem, retorna None (degradação graciosa)
        """
        credentials = self._client_credentials_for(org_id)
        if not credentials.configured:
            self._set_last_error(credentials.error or "missing_credentials", org_id=org_id)
            return None

        st = self._state(org_id)

        # Carrega refresh_token do DB se ainda não tentou e não está em memória.
        # Copilot feedback 2026-04-24: load_token_from_db() precisa rodar mesmo
        # quando is_configured==True, senão o fallback refresh_token nunca vê
        # o token persistido via /callback flow.
        if not st.refresh_token:
            self.load_token_from_db(org_id if org_id is not None else self.DEFAULT_ORG_ID)

        # Cache hit (com 30s de margem antes de expirar)
        if st.access_token and time.time() < st.expires_at - 30:
            return st.access_token

        async with self._lock_for(org_id):
            # Double-check após adquirir lock (outra coroutine pode ter renovado)
            if st.access_token and time.time() < st.expires_at - 30:
                return st.access_token

            # Estratégia 1: client_credentials (preferido — sem refresh_token)
            try:
                await self._authenticate_client_credentials(org_id)
                return st.access_token
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                logger.warning(
                    "PDPJ: client_credentials falhou (%s), tentando refresh_token...",
                    str(e)[:100],
                )

            # Estratégia 2: refresh_token (fallback)
            if self._has_refresh_token(org_id):
                try:
                    await self._authenticate_refresh_token(org_id)
                    return st.access_token
                except (httpx.HTTPStatusError, httpx.RequestError):
                    pass

            # Ambos falharam
            logger.error("PDPJ: todos os métodos de autenticação falharam (org_id=%s)", org_id)
            return None

    async def invalidate_cache(self, org_id: int = 1) -> None:
        """
        Limpa o access_token cacheado do org sob o lock dele, pra forçar refresh
        na próxima chamada de get_access_token(). Usado quando upstream retorna
        401/403 e suspeitamos que o token está revogado.
        """
        async with self._lock_for(org_id):
            st = self._state(org_id)
            st.access_token = None
            st.expires_at = 0.0

    async def _authenticate_client_credentials(self, org_id: Optional[int] = None) -> None:
        """Obtém access_token via client_credentials grant (server-to-server)."""
        logger.info("PDPJ: autenticando via client_credentials")
        credentials = self._client_credentials_for(org_id)

        data = {
            "grant_type": "client_credentials",
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
        }

        await self._do_token_request(data, "client_credentials", org_id)

    async def _authenticate_refresh_token(self, org_id: Optional[int] = None) -> None:
        """Troca refresh_token por novo access_token via PDPJ."""
        logger.info("PDPJ: renovando access_token via refresh_token")

        st = self._state(org_id)
        credentials = self._client_credentials_for(org_id)
        data = {
            "grant_type": "refresh_token",
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "refresh_token": st.refresh_token,
        }

        await self._do_token_request(data, "refresh_token", org_id)

    async def _do_token_request(
        self, data: dict, grant_type: str, org_id: Optional[int] = None
    ) -> None:
        """Executa a requisição ao token endpoint e processa a resposta."""
        st = self._state(org_id)
        try:
            client = get_pdpj_client()
            resp = await client.post(
                PDPJ_TOKEN_URL,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15.0,
            )
            resp.raise_for_status()
            token_data = resp.json()

            st.access_token = token_data.get("access_token")
            expires_in_raw = token_data.get("expires_in", 300)
            try:
                expires_in = int(expires_in_raw)
            except (TypeError, ValueError):
                expires_in = 300
            st.expires_at = time.time() + expires_in
            st.last_grant_type = grant_type
            self._clear_last_error(org_id)

            if not st.access_token:
                self._set_last_error("empty_token_response", resp.status_code, org_id=org_id)
                raise httpx.HTTPStatusError(
                    "PDPJ token response did not include access_token",
                    request=resp.request,
                    response=resp,
                )

            # Se PDPJ retornou novo refresh_token, atualiza em memória (do org)
            new_refresh = token_data.get("refresh_token")
            if new_refresh and new_refresh != st.refresh_token:
                st.refresh_token = new_refresh
                # Log apenas hash parcial — nunca substring do token.
                # Copilot feedback 2026-04-24: log-centralized env + rotation hint
                # exposure aumentam risco de correlação/social engineering.
                new_hash = hashlib.sha256(new_refresh.encode()).hexdigest()[:12]
                logger.warning(
                    "PDPJ: refresh_token rotacionado (hash=%s). Reconecte via "
                    "/casehub/oauth/pdpj/connect para persistir no storage da instância.",
                    new_hash,
                )

            logger.info(
                "PDPJ: access_token obtido via %s, expira em %ds",
                grant_type, expires_in,
            )

        except httpx.HTTPStatusError as e:
            if st.last_error_code == "empty_token_response":
                error_code = "empty_token_response"
                error_description = st.last_error_description or ""
            else:
                error_code = f"http_{e.response.status_code}"
                error_description = ""
                try:
                    error_body = e.response.json()
                    error_code = error_body.get("error") or error_code
                    error_description = _safe_oauth_error(error_body.get("error_description") or "")
                except Exception:
                    error_description = _safe_oauth_error(e.response.text[:160])
            self._set_last_error(error_code, e.response.status_code, error_description, org_id=org_id)
            logger.error(
                "PDPJ: falha no %s — status %s, body: %s",
                grant_type, e.response.status_code, _safe_oauth_error(e.response.text[:300]),
            )
            st.access_token = None
            st.expires_at = 0.0
            raise
        except httpx.RequestError as e:
            self._set_last_error("network", None, str(e), org_id=org_id)
            logger.error("PDPJ: erro de rede no %s: %s", grant_type, e)
            st.access_token = None
            st.expires_at = 0.0
            raise

    async def probe_client_credentials(self, org_id: int = 1) -> Dict[str, Any]:
        """Run a sanitized read-only token probe against PDPJ client_credentials."""
        credentials = self._client_credentials_for(org_id)
        if not credentials.configured:
            code = credentials.error or "missing_credentials"
            self._set_last_error(code, org_id=org_id)
            return {
                "success": False,
                "code": code,
                "message": public_pdpj_error_message(code),
                "auth": self.public_status(org_id),
            }

        async with self._lock_for(org_id):
            try:
                await self._authenticate_client_credentials(org_id)
                return {
                    "success": True,
                    "code": "token_ok",
                    "message": "PDPJ client_credentials aceito pelo CNJ.",
                    "auth": self.public_status(org_id),
                }
            except (httpx.HTTPStatusError, httpx.RequestError):
                code = self._state(org_id).last_error_code or "no_access_token"
                return {
                    "success": False,
                    "code": code,
                    "message": public_pdpj_error_message(code),
                    "auth": self.public_status(org_id),
                }


# Singleton auth client
pdpj_auth = PDPJAuthClient()


def public_pdpj_error_message(code: Optional[str]) -> str:
    if not code:
        return ""
    if code == "http_403":
        return (
            "ComunicaAPI/CNJ negou acesso ao recurso. A credencial autentica, "
            "mas o cliente PDPJ precisa de permissao/escopo para este endpoint."
        )
    if code == "http_401":
        return "ComunicaAPI/CNJ rejeitou a autorizacao da chamada ao recurso."
    if code.startswith("http_"):
        return f"ComunicaAPI/CNJ respondeu {code.upper().replace('_', ' ')}."
    if code.startswith("auth_failure"):
        return "Falha ao autenticar no PDPJ/CNJ."
    return PDPJ_PUBLIC_ERROR_MESSAGES.get(code, "Integracao PDPJ indisponivel no momento.")


# ──────────── ComunicaAPI Client ────────────

class ComunicaAPIClient:
    """Client for the ComunicaAPI PJE/CNJ (v2 com OAuth2 PDPJ)."""

    def __init__(self):
        self.base_url = COMUNICAAPI_BASE_URL
        self.timeout = 30.0

    async def buscar_por_oab(
        self,
        numero_oab: str,
        uf_oab: str = "MG",
        data_inicio: Optional[str] = None,
        data_fim: Optional[str] = None,
        org_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Buscar comunicacoes/intimacoes por numero OAB e UF.

        Args:
            numero_oab: Numero da OAB (apenas digitos, ex: "123456")
            uf_oab: UF da OAB (ex: "MG", "SP", "RJ")
            data_inicio: Data inicio (YYYY-MM-DD). Default: 30 dias atrás.
            data_fim: Data fim (YYYY-MM-DD). Default: hoje.

        Returns:
            dict com keys: items (list), count (int), source (str).
            Em caso de credenciais PDPJ ausentes ou 403, retorna dict vazio
            com `source` indicando o motivo.
        """
        # Demo mode — retornar mock data
        if settings.DEMO_MODE:
            logger.info(
                "ComunicaAPI DEMO: returning mock intimações for OAB %s/%s",
                numero_oab, uf_oab,
            )
            return dict(_DEMO_INTIMACOES)

        if org_id is None:
            logger.warning("ComunicaAPI: consulta bloqueada sem org_id explicito")
            return {
                "items": [],
                "count": 0,
                "source": "ComunicaAPI PJE/CNJ (tenant nao identificado)",
                "error": "missing_org_id",
                "message": public_pdpj_error_message("missing_org_id"),
                "auth": pdpj_auth.public_status(None),
            }

        # Org para isolamento de credenciais PDPJ (IDOR C6).
        effective_org_id = org_id

        # Credenciais PDPJ configuradas?
        if not pdpj_auth.is_configured_for(effective_org_id):
            logger.warning(
                "ComunicaAPI: credenciais PDPJ ausentes para org_id=%s. Configure "
                "credenciais do tenant ou PDPJ_CLIENT_ID/PDPJ_CLIENT_SECRET no .env. "
                "PDPJ_REFRESH_TOKEN é opcional (apenas se usar authorization_code "
                "flow em vez de client_credentials). Retornando resultado vazio.",
                effective_org_id,
            )
            return {
                "items": [],
                "count": 0,
                "source": "ComunicaAPI PJE/CNJ (inativo — credenciais PDPJ ausentes)",
                "error": "missing_credentials",
                "message": public_pdpj_error_message("missing_credentials"),
                "auth": pdpj_auth.public_status(effective_org_id),
            }

        # Normalização de datas
        if not data_inicio:
            data_inicio = (date.today() - timedelta(days=30)).isoformat()
        if not data_fim:
            data_fim = date.today().isoformat()

        # Limpeza do OAB (só dígitos)
        oab_clean = "".join(c for c in numero_oab if c.isdigit())

        params = {
            "numeroOab": oab_clean,
            "ufOab": uf_oab.upper(),
            "dataDisponibilizacaoInicio": data_inicio,
            "dataDisponibilizacaoFim": data_fim,
        }

        logger.info(
            "ComunicaAPI: buscando OAB %s/%s de %s a %s (com auth PDPJ)",
            oab_clean, uf_oab, data_inicio, data_fim,
        )

        # Obter access_token (isolado por org)
        try:
            access_token = await pdpj_auth.get_access_token(effective_org_id)
        except Exception as e:
            logger.error("ComunicaAPI: falha ao obter access_token: %s", e)
            code = pdpj_auth._state(effective_org_id).last_error_code or "auth_failure"
            return {
                "items": [],
                "count": 0,
                "source": "ComunicaAPI PJE/CNJ (erro auth PDPJ)",
                "error": code,
                "message": public_pdpj_error_message(code),
                "auth": pdpj_auth.public_status(effective_org_id),
            }

        if not access_token:
            code = pdpj_auth._state(effective_org_id).last_error_code or "no_access_token"
            return {
                "items": [],
                "count": 0,
                "source": "ComunicaAPI PJE/CNJ (sem access_token)",
                "error": code,
                "message": public_pdpj_error_message(code),
                "auth": pdpj_auth.public_status(effective_org_id),
            }

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        # Requisição autenticada
        try:
            client = get_pdpj_client()
            resp = await client.get(
                f"{self.base_url}/comunicacao",
                params=params,
                headers=headers,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            items = data.get("items", [])
            count = data.get("count", len(items))

            logger.info("ComunicaAPI: %d comunicacoes encontradas", count)

            normalized = [self._normalize_item(it) for it in items]

            return {
                "items": normalized,
                "count": count,
                "raw_items": items,
                "source": "ComunicaAPI PJE/CNJ",
            }

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            # Corpo da resposta vai apenas pro log; deixamos fora do dict
            # retornado pra evitar vazamento acidental de PII/conteúdo
            # upstream em camadas superiores que possam serializar o erro.
            logger.error("ComunicaAPI HTTP %s: %s", status, e.response.text[:300])

            # 401/403 = provavelmente token inválido. Força próxima renovação
            # via método público (sob o mesmo lock do org no PDPJAuthClient).
            if status in (401, 403):
                await pdpj_auth.invalidate_cache(effective_org_id)
                logger.warning(
                    "ComunicaAPI: %s recebido, token cache invalidado (org_id=%s). "
                    "Verifique autorizacao do cliente PDPJ para o recurso/endpoint "
                    "CNJ solicitado.",
                    status, effective_org_id,
                )

            return {
                "items": [],
                "count": 0,
                "source": f"ComunicaAPI PJE/CNJ (HTTP {status})",
                "error": f"http_{status}",
                "message": public_pdpj_error_message(f"http_{status}"),
                "auth": pdpj_auth.public_status(effective_org_id),
            }
        except httpx.RequestError as e:
            logger.error("ComunicaAPI: erro de rede: %s", e)
            return {
                "items": [],
                "count": 0,
                "source": "ComunicaAPI PJE/CNJ (erro de rede)",
                "error": "network",
                "message": public_pdpj_error_message("network"),
                "auth": pdpj_auth.public_status(effective_org_id),
            }
        except Exception as e:
            logger.error("ComunicaAPI: erro inesperado: %s", e)
            return {
                "items": [],
                "count": 0,
                "source": "ComunicaAPI PJE/CNJ (erro inesperado)",
                "error": "unexpected",
                "message": public_pdpj_error_message("unexpected"),
                "auth": pdpj_auth.public_status(effective_org_id),
            }

    def _normalize_item(self, item: dict) -> dict:
        """Normaliza um item da ComunicaAPI para o formato CaseHub padrão."""
        advogados = [
            {"nome": adv.get("nome", ""), "oab": adv.get("oab", "")}
            for adv in item.get("destinatarioadvogados", [])
        ]

        destinatarios = [
            {"nome": dest.get("nome", ""), "tipo": dest.get("tipo", "")}
            for dest in item.get("destinatarios", [])
        ]

        return {
            "id": item.get("id", ""),
            "numero_processo": item.get("numeroprocessocommascara") or item.get("numero_processo", ""),
            "tribunal": item.get("siglaTribunal", ""),
            "orgao": item.get("nomeOrgao", ""),
            "tipo_comunicacao": item.get("tipoComunicacao", ""),
            "texto": item.get("texto", ""),
            "data_disponibilizacao": item.get("data_disponibilizacao", ""),
            "status": item.get("status", ""),
            "advogados": advogados,
            "destinatarios": destinatarios,
            "source": "ComunicaAPI PJE/CNJ",
        }

    async def buscar_intimacoes_recentes(
        self,
        numero_oab: str,
        uf_oab: str = "MG",
        dias: int = 7,
        org_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Buscar intimacoes dos ultimos N dias (convenience method).
        Útil para cron job diário (buscar últimas 24h ou 7 dias).
        """
        data_inicio = (date.today() - timedelta(days=dias)).isoformat()
        data_fim = date.today().isoformat()
        resultado = await self.buscar_por_oab(
            numero_oab, uf_oab,
            data_inicio=data_inicio,
            data_fim=data_fim,
            org_id=org_id,
        )
        return resultado.get("items", [])


# Singleton client
comunicaapi_client = ComunicaAPIClient()
