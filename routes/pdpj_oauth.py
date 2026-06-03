"""
CaseHub — PDPJ OAuth2 Callback
Rota de callback para o fluxo OAuth2 authorization_code do PDPJ (Keycloak CNJ).

Fluxo:
    1. Admin clica "Conectar PDPJ" na página de settings ou na controladoria
    2. Redireciona para o authorization endpoint do Keycloak PDPJ
    3. Titular OAB ([parceiro]) autentica com certificado digital / gov.br
    4. PDPJ redireciona de volta para /casehub/oauth/pdpj/callback com ?code=...
    5. Este handler troca o code por access_token + refresh_token
    6. Persiste o refresh_token no banco (org settings) — não no .env
    7. PDPJAuthClient no comunicaapi.py lê de lá a cada renovação

Notas:
    - O redirect_uri é construído dinamicamente usando settings.BASE_URL,
      então funciona em qualquer instância (dev, prod, white-label).
    - Só admins podem iniciar o fluxo (proteção contra CSRF + privilege).
    - O state é armazenado em session cookie (não no banco) para simplicidade.
"""
import hashlib
import httpx
import logging
import os
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from core.template_config import templates, PREFIX
from auth import get_current_user
from models import get_db
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/oauth/pdpj", tags=["pdpj_oauth"])

# ──────────── PDPJ Keycloak endpoints ────────────
PDPJ_AUTH_URL = "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/auth"
PDPJ_TOKEN_URL = "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/token"
PDPJ_USERINFO_URL = "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/userinfo"

# Staging (homologação) — usar quando PDPJ_ENV=staging no .env
PDPJ_STG_AUTH_URL = "https://sso.stg.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/auth"
PDPJ_STG_TOKEN_URL = "https://sso.stg.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/token"


def _get_pdpj_urls() -> tuple[str, str]:
    """Return (auth_url, token_url) based on environment."""
    if os.getenv("PDPJ_ENV", "production").lower() == "staging":
        return PDPJ_STG_AUTH_URL, PDPJ_STG_TOKEN_URL
    return PDPJ_AUTH_URL, PDPJ_TOKEN_URL


def _get_redirect_uri() -> str:
    """Build redirect_uri dynamically from BASE_URL + PREFIX."""
    base = settings.BASE_URL.rstrip("/")
    return f"{base}{PREFIX}/oauth/pdpj/callback"


def _get_client_credentials() -> tuple[str, str]:
    """Return (client_id, client_secret) from environment."""
    return (
        os.getenv("PDPJ_CLIENT_ID", ""),
        os.getenv("PDPJ_CLIENT_SECRET", ""),
    )


def _is_pdpj_admin(user) -> bool:
    return getattr(user, "user_type", "") in ("admin", "superadmin")


# ──────────── Routes ────────────

@router.get("/status", response_class=JSONResponse)
async def pdpj_status(
    request: Request,
    db: Session = Depends(get_db),
):
    """API: Check if PDPJ integration is configured and active."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)

    client_id, client_secret = _get_client_credentials()
    refresh_token = os.getenv("PDPJ_REFRESH_TOKEN", "")

    # Check org-level override (stored in DB)
    org_id = getattr(request.state, "org_id", 1)
    org_refresh = _get_org_pdpj_token(db, org_id)

    # Alinhado ao PDPJAuthClient.is_configured: client_credentials não precisa
    # de refresh_token, então "configured" considera só client_id/secret.
    # has_refresh_token fica exposto separado para admins diagnosticarem
    # qual grant type cada flow vai usar. (Copilot feedback 2026-04-24)
    configured = bool(client_id and client_secret)

    auth_state = {}
    try:
        from services.comunicaapi import pdpj_auth
        auth_state = pdpj_auth.public_status()
    except Exception:
        auth_state = {}

    return JSONResponse({
        "configured": configured,
        "has_client_id": bool(client_id),
        "has_client_secret": bool(client_secret),
        "has_refresh_token": bool(refresh_token or org_refresh),
        "token_source": "database" if org_refresh else ("env" if refresh_token else "none"),
        "redirect_uri": _get_redirect_uri(),
        "environment": os.getenv("PDPJ_ENV", "production"),
        "grant_strategy": "client_credentials_with_refresh_fallback",
        "auth": auth_state,
    })


@router.post("/probe", response_class=JSONResponse)
async def pdpj_probe(
    request: Request,
    db: Session = Depends(get_db),
):
    """Admin-only, sanitized probe of the PDPJ client_credentials grant."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)
    if not _is_pdpj_admin(user):
        raise HTTPException(status_code=403, detail="Apenas administradores podem testar o PDPJ")

    try:
        from services.comunicaapi import pdpj_auth
        result = await pdpj_auth.probe_client_credentials()
    except Exception as e:
        logger.error("PDPJ probe failed unexpectedly: %s", e)
        result = {
            "success": False,
            "code": "unexpected",
            "message": "Falha inesperada ao testar o PDPJ.",
            "auth": {},
        }

    return JSONResponse({
        **result,
        "environment": os.getenv("PDPJ_ENV", "production"),
        "grant_type": "client_credentials",
        "redirect_uri": _get_redirect_uri(),
    })


@router.get("/connect")
async def pdpj_connect(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Initiate PDPJ OAuth2 authorization_code flow.
    Only admins can trigger this — the redirect sends the user (OAB titular)
    to the PDPJ Keycloak login page.
    """
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Only admins can initiate PDPJ connection
    if not _is_pdpj_admin(user):
        raise HTTPException(status_code=403, detail="Apenas administradores podem conectar o PDPJ")

    client_id, _ = _get_client_credentials()
    if not client_id:
        return JSONResponse({
            "error": "PDPJ_CLIENT_ID não configurado. Aguarde as credenciais do CNJ.",
            "help": "Configure PDPJ_CLIENT_ID e PDPJ_CLIENT_SECRET no .env da instância.",
        }, status_code=400)

    # Generate CSRF state
    state = secrets.token_urlsafe(32)

    # Store state in a signed cookie (expires in 10 minutes)
    auth_url, _ = _get_pdpj_urls()
    redirect_uri = _get_redirect_uri()

    # Build authorization URL
    # Copilot feedback 2026-04-24: urlencode correto pra aceitar valores com
    # espaço (e.g. scope="openid profile email") e caracteres especiais em
    # redirect_uri. Manual "k=v" com join quebra a spec OAuth2.
    from urllib.parse import urlencode
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid profile email",
        "state": state,
    }
    full_url = f"{auth_url}?{urlencode(params)}"

    logger.info(
        "PDPJ OAuth: iniciando fluxo authorization_code (redirect_uri=%s)",
        redirect_uri,
    )

    response = RedirectResponse(url=full_url, status_code=302)
    # Store state in cookie for CSRF verification on callback
    is_https = settings.BASE_URL.startswith("https")
    response.set_cookie(
        key="pdpj_oauth_state",
        value=state,
        max_age=600,  # 10 minutes
        httponly=True,
        secure=is_https,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/callback")
async def pdpj_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Handle OAuth2 callback from PDPJ Keycloak.
    Exchanges authorization code for tokens and stores refresh_token.

    Defesa em profundidade (Copilot feedback 2026-04-24): o callback persiste
    credencial sensível (refresh_token) da organização. Além do state cookie
    (CSRF), exigimos sessão autenticada de admin — não basta que o flow tenha
    começado com admin; a conclusão também precisa.
    """
    # Defesa em profundidade: exige usuário autenticado + admin pra persistir
    # o refresh_token. Mesmo que o flow tenha começado com admin, o callback
    # precisa validar que a sessão ainda é válida.
    user = get_current_user(request, db)
    if not user:
        logger.warning("PDPJ OAuth callback: sessão ausente, rejeitando")
        return templates.TemplateResponse("pdpj_oauth_result.html", {
            "request": request,
            "PREFIX": PREFIX,
            "success": False,
            "error": "unauthenticated",
            "error_description": "Sessão expirada. Faça login e reinicie o fluxo de conexão PDPJ.",
        })
    if getattr(user, "user_type", "") not in ("admin", "superadmin"):
        logger.warning(
            "PDPJ OAuth callback: user_type=%s sem permissão",
            getattr(user, "user_type", "?"),
        )
        return templates.TemplateResponse("pdpj_oauth_result.html", {
            "request": request,
            "PREFIX": PREFIX,
            "success": False,
            "error": "forbidden",
            "error_description": "Apenas administradores podem concluir a conexão PDPJ.",
        })

    # Error from PDPJ
    if error:
        logger.error("PDPJ OAuth callback error: %s — %s", error, error_description)
        return templates.TemplateResponse("pdpj_oauth_result.html", {
            "request": request,
            "PREFIX": PREFIX,
            "success": False,
            "error": error,
            "error_description": error_description or "O PDPJ retornou um erro na autenticação.",
        })

    if not code or not state:
        return templates.TemplateResponse("pdpj_oauth_result.html", {
            "request": request,
            "PREFIX": PREFIX,
            "success": False,
            "error": "missing_params",
            "error_description": "Parâmetros code ou state ausentes no callback.",
        })

    # CSRF verification
    stored_state = request.cookies.get("pdpj_oauth_state")
    if not stored_state or stored_state != state:
        logger.warning("PDPJ OAuth: state mismatch (CSRF)")
        return templates.TemplateResponse("pdpj_oauth_result.html", {
            "request": request,
            "PREFIX": PREFIX,
            "success": False,
            "error": "invalid_state",
            "error_description": "Sessão expirada ou inválida. Tente novamente.",
        })

    # Exchange code for tokens
    client_id, client_secret = _get_client_credentials()
    _, token_url = _get_pdpj_urls()
    redirect_uri = _get_redirect_uri()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_response = await client.post(
                token_url,
                data={
                    "grant_type": "authorization_code",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if token_response.status_code != 200:
                logger.error(
                    "PDPJ OAuth: token exchange failed — HTTP %s: %s",
                    token_response.status_code,
                    token_response.text[:300],
                )
                return templates.TemplateResponse("pdpj_oauth_result.html", {
                    "request": request,
                    "PREFIX": PREFIX,
                    "success": False,
                    "error": f"token_error_{token_response.status_code}",
                    "error_description": "Falha ao trocar o código de autorização por tokens.",
                })

            tokens = token_response.json()

    except httpx.RequestError as e:
        logger.error("PDPJ OAuth: network error during token exchange: %s", e)
        return templates.TemplateResponse("pdpj_oauth_result.html", {
            "request": request,
            "PREFIX": PREFIX,
            "success": False,
            "error": "network_error",
            "error_description": f"Erro de rede ao contactar o PDPJ: {str(e)[:100]}",
        })

    access_token = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")
    expires_in = tokens.get("expires_in", 300)

    if not refresh_token:
        logger.warning("PDPJ OAuth: token exchange succeeded but no refresh_token returned")
        return templates.TemplateResponse("pdpj_oauth_result.html", {
            "request": request,
            "PREFIX": PREFIX,
            "success": False,
            "error": "no_refresh_token",
            "error_description": "O PDPJ não retornou um refresh_token. Verifique os escopos.",
        })

    # Get user info from PDPJ (optional — for logging/audit)
    pdpj_user_info = {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            info_resp = await client.get(
                PDPJ_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if info_resp.status_code == 200:
                pdpj_user_info = info_resp.json()
    except Exception as e:
        logger.warning("PDPJ OAuth: userinfo failed (non-critical): %s", e)

    # Store refresh_token in org settings (database — survives deploys)
    org_id = getattr(request.state, "org_id", 1)
    _store_org_pdpj_token(db, org_id, refresh_token, pdpj_user_info)

    # Also update the in-memory PDPJAuthClient singleton
    try:
        from services.comunicaapi import pdpj_auth
        pdpj_auth.refresh_token = refresh_token
        pdpj_auth._access_token = access_token
        pdpj_auth._expires_at = __import__("time").time() + int(expires_in)
        logger.info("PDPJ OAuth: in-memory PDPJAuthClient updated")
    except ImportError:
        logger.warning("PDPJ OAuth: could not update PDPJAuthClient (import failed)")

    logger.info(
        "PDPJ OAuth: integração ativada com sucesso (org_id=%s, pdpj_user=%s)",
        org_id,
        pdpj_user_info.get("preferred_username", "unknown"),
    )

    # Clear state cookie and show success page.
    # Copilot feedback 2026-04-24: NÃO expor substring do refresh_token na UI
    # (screenshots podem acabar em Slack/Teams/suporte). Exibimos apenas o hash
    # parcial SHA-256 que já é persistido no DB como pdpj_token_hash, para o
    # admin conseguir correlacionar o token ativo sem ter o valor real.
    token_hash_preview = hashlib.sha256(refresh_token.encode()).hexdigest()[:12]
    response = templates.TemplateResponse("pdpj_oauth_result.html", {
        "request": request,
        "PREFIX": PREFIX,
        "success": True,
        "pdpj_user": pdpj_user_info.get("name", pdpj_user_info.get("preferred_username", "")),
        "expires_in": expires_in,
        "token_hash": token_hash_preview,
    })
    response.delete_cookie("pdpj_oauth_state", path="/")
    return response


# ──────────── DB helpers ────────────

def _get_org_pdpj_token(db: Session, org_id: int) -> Optional[str]:
    """Read org-level PDPJ refresh_token from organizations.settings JSON."""
    try:
        result = db.execute(
            text("SELECT settings->>'pdpj_refresh_token' FROM organizations WHERE id = :id"),
            {"id": org_id},
        )
        row = result.fetchone()
        return row[0] if row and row[0] else None
    except Exception as e:
        logger.debug("Could not read org PDPJ token: %s", e)
        return None


def _store_org_pdpj_token(db: Session, org_id: int, refresh_token: str, user_info: dict) -> None:
    """Persist PDPJ refresh_token in organizations.settings JSONB."""
    try:
        # Hash parcial para log (nunca logamos o token completo)
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()[:12]

        db.execute(
            text("""
                UPDATE organizations
                SET settings = COALESCE(settings, '{}'::jsonb)
                    || jsonb_build_object(
                        'pdpj_refresh_token', :token,
                        'pdpj_connected_at', to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS'),
                        'pdpj_user', :user_name,
                        'pdpj_token_hash', :token_hash
                    )
                WHERE id = :org_id
            """),
            {
                "token": refresh_token,
                "org_id": org_id,
                "user_name": user_info.get("name", user_info.get("preferred_username", "")),
                "token_hash": token_hash,
            },
        )
        db.commit()
        logger.info(
            "PDPJ OAuth: refresh_token persisted in DB (org_id=%s, hash=%s)",
            org_id, token_hash,
        )
    except Exception as e:
        db.rollback()
        logger.error("PDPJ OAuth: failed to store refresh_token in DB: %s", e)
        # Fallback: log APENAS hash — sem substring do token.
        # Copilot feedback 2026-04-24: ambientes com log centralizado + hint
        # visível aumentam risco de correlação. Token real segue só em memória
        # do processo atual; admin precisa reconectar pra persistir.
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()[:12]
        logger.warning(
            "PDPJ OAuth: FALLBACK — token obtido mas não persistido (hash=%s). "
            "Admin deve reconectar via /casehub/oauth/pdpj/connect após corrigir "
            "o erro de DB, OU configurar PDPJ_REFRESH_TOKEN diretamente no .env "
            "se tiver acesso direto à VPS.",
            token_hash,
        )
