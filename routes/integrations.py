"""CaseHub Basic integrations status page."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import socket
import time
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request as UrlRequest, urlopen

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from auth import get_current_user
from config import settings
from core.template_config import PREFIX, inject_org_context, templates
from models import get_db, Organization
from services.google_calendar import GoogleCalendarService
from services.per_org_credentials import get_org_drive_token_path

logger = logging.getLogger(__name__)

# OAuth incremental/união de escopos: quando a MESMA conta Google já tem o Calendar
# conectado e o usuário conecta o Drive (ou vice-versa), o Google devolve o token com
# a UNIÃO dos escopos (drive + calendar.*). Sem isto, oauthlib levanta "Scope has
# changed" como erro e o callback caía em ?drive_error=oauth_callback_failed
# (UsuarioDemo, alpha 29/05). Process-wide → cobre Drive e Calendar.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

router = APIRouter(prefix="/integrations", tags=["integrations"])
OAUTH_STATE_MAX_AGE_SECONDS = 10 * 60


def _configured_path(path_value: str) -> bool:
    if not path_value:
        return False
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = Path(settings.BASE_DIR) / path
    return path.exists()


def _resolve_app_path(path_value: str, fallback: str) -> Path:
    raw = path_value or fallback
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path(settings.BASE_DIR) / path
    return path


def _google_drive_redirect_uri(request: Request) -> str:
    forwarded_host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
    forwarded_proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "https").split(",")[0].strip()
    configured = (settings.BASE_URL or "").strip().rstrip("/")
    if forwarded_host and not forwarded_host.startswith(("localhost", "127.0.0.1")):
        base = f"{forwarded_proto if forwarded_proto != 'http' else 'https'}://{forwarded_host}"
    elif configured:
        base = configured
    else:
        base = str(request.base_url).rstrip("/")
    return f"{base}{PREFIX}/integrations/google-drive/callback"


def _google_drive_paths(org_id: int | None = None) -> tuple[Path, Path]:
    """Return (client_secrets_path, per_org_token_path).

    The OAuth client secrets file stays global — same Google Cloud client
    across orgs. Only the token path is tenant-scoped, under
    ``credentials/org_{org_id}/drive_token.json``.

    ``org_id=None`` falls back to ``DEFAULT_ORG_ID`` so the integration card
    status check (which has no request context) keeps reporting the default
    tenant's state.
    """
    from services.per_org_credentials import DEFAULT_ORG_ID

    credentials = _google_drive_credentials_path()
    token_path = get_org_drive_token_path(int(org_id) if org_id else DEFAULT_ORG_ID)
    return credentials, token_path


def _google_drive_credentials_path() -> Path:
    """Resolve the shared Google OAuth client file used by Drive.

    Drive historically had ``google_drive_credentials.json`` while Calendar and
    Gmail use the shared ``google_client_secret.json``. Try the Drive-specific
    file first, then the shared Google client so an office that already has
    Google OAuth configured can complete Drive consent without duplicating
    credentials.
    """
    candidates = []
    explicit_drive = (settings.GOOGLE_DRIVE_CREDENTIALS_PATH or "").strip()
    if explicit_drive:
        candidates.append(_resolve_app_path(explicit_drive, ""))
    candidates.append(_resolve_app_path("", "credentials/google_drive_credentials.json"))

    calendar_override = (
        os.getenv("GOOGLE_CALENDAR_CREDENTIALS_PATH")
        or getattr(settings, "GOOGLE_CALENDAR_CREDENTIALS_PATH", "")
        or ""
    ).strip()
    if calendar_override:
        candidates.append(_resolve_app_path(calendar_override, ""))
    candidates.extend([
        _resolve_app_path("", "credentials/google_client_secret.json"),
        _resolve_app_path("", "credentials/google_calendar_credentials.json"),
    ])

    seen = set()
    unique_candidates = []
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique_candidates.append(candidate)

    for candidate in unique_candidates:
        if candidate.exists():
            return candidate
    return unique_candidates[0]


def _google_drive_root_status(
    db: Session | None,
    org_id: int | None = None,
) -> tuple[str, str]:
    """Return (root_id, source) for the Drive explorer root."""
    if db is not None and org_id is not None:
        try:
            org = db.query(Organization).filter(Organization.id == org_id).first()
            if org is not None and getattr(org, "google_drive_root_id", None):
                return org.google_drive_root_id, "org"
        except Exception as exc:
            logger.warning("Drive root probe failed for org %s: %s", org_id, exc)
    if settings.GOOGLE_DRIVE_ROOT_ID:
        return settings.GOOGLE_DRIVE_ROOT_ID, "global"
    return "", "root-fallback"


def _google_drive_root_id(db: Session | None, org_id: int | None = None) -> str:
    """Return the tenant Drive root folder id, falling back to global settings."""
    return _google_drive_root_status(db, org_id)[0]


def _google_drive_root_source(db: Session | None, org_id: int | None = None) -> str:
    return _google_drive_root_status(db, org_id)[1]


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def _oauth_state_signature(payload: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def _encode_drive_oauth_state(user, org_id: int) -> str:
    """Encode signed Drive OAuth state binding the consent flow to a tenant.

    The ``org`` claim is later validated against ``request.state.org_id``
    so a callback hitting a different subdomain (or a replay across
    tenants) fails ``_decode_drive_oauth_state``.
    """
    payload = {
        "scope": "google-drive",
        "uid": getattr(user, "id", None),
        "sub": getattr(user, "email", ""),
        "org": int(org_id),
        "iat": int(time.time()),
        "nonce": secrets.token_urlsafe(16),
    }
    encoded = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{encoded}.{_oauth_state_signature(encoded)}"


def _decode_drive_oauth_state(state: str, user, expected_org_id: int) -> bool:
    """Validate signed Drive OAuth state: signature, age, scope, uid, sub, org.

    Returns ``False`` (drops the callback) whenever the encoded ``org``
    claim does not match ``expected_org_id`` — prevents an org's consent
    from being persisted under another org's token path.
    """
    try:
        encoded, signature = (state or "").split(".", 1)
    except ValueError:
        return False

    expected = _oauth_state_signature(encoded)
    if not hmac.compare_digest(signature, expected):
        return False

    try:
        payload = json.loads(_b64url_decode(encoded).decode("utf-8"))
    except Exception:
        return False

    now = int(time.time())
    issued_at = int(payload.get("iat") or 0)
    if not (now - OAUTH_STATE_MAX_AGE_SECONDS <= issued_at <= now + 60):
        return False
    if payload.get("scope") != "google-drive":
        return False
    if payload.get("uid") != getattr(user, "id", None):
        return False
    if payload.get("sub") != getattr(user, "email", ""):
        return False
    if int(payload.get("org") or 0) != int(expected_org_id):
        logger.warning(
            "Drive OAuth state org mismatch: payload=%s expected=%s",
            payload.get("org"), expected_org_id,
        )
        return False
    return True


def _http_probe(base_url: str, suffix: str = "/health") -> tuple[bool, str]:
    if not base_url:
        return False, "URL nao configurada."
    try:
        target = urljoin(base_url.rstrip("/") + "/", suffix.lstrip("/"))
        request = UrlRequest(target, headers={"User-Agent": "CaseHub integration status"})
        with urlopen(request, timeout=1.8) as response:
            status = getattr(response, "status", 0)
            if 200 <= status < 400:
                return True, f"Health check respondeu HTTP {status}."
            return False, f"Health check respondeu HTTP {status}."
    except Exception as e:
        return False, f"Health check indisponivel: {type(e).__name__}."


def _json_probe(base_url: str, suffix: str = "/api/status") -> tuple[bool, str, dict]:
    if not base_url:
        return False, "URL nao configurada.", {}
    try:
        target = urljoin(base_url.rstrip("/") + "/", suffix.lstrip("/"))
        request = UrlRequest(target, headers={"User-Agent": "CaseHub integration status"})
        with urlopen(request, timeout=2.2) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
            ready = bool(
                payload.get("connected")
                or payload.get("isReady")
                or payload.get("ready")
                or payload.get("ok")
                or payload.get("status") == "ready"
            )
            return ready, f"Status respondeu {payload.get('status') or getattr(response, 'status', 0)}.", payload
    except Exception as e:
        return False, f"Status indisponivel: {type(e).__name__}.", {}


def _tcp_probe(host: str, port: int) -> bool:
    if not host or not port:
        return False
    try:
        with socket.create_connection((host, int(port)), timeout=1.8):
            return True
    except Exception:
        return False


def _status(
    name: str,
    state: str,
    summary: str,
    detail: str,
    action_label: str,
    action_url: str,
    icon: str,
    setup_url: str = "",
    setup_label: str = "Manual",
    steps: list[str] | None = None,
    diagnostic: str = "",
    disconnect_url: str = "",
    lgpd_notice: str = "",
    extra: dict | None = None,
) -> dict:
    payload = {
        "name": name,
        "state": state,
        "summary": summary,
        "detail": detail,
        "action_label": action_label,
        "action_url": action_url,
        "icon": icon,
        "setup_url": setup_url,
        "setup_label": setup_label,
        "steps": steps or [],
        "diagnostic": diagnostic,
        "disconnect_url": disconnect_url,
        "lgpd_notice": lgpd_notice,
        "state_label": {
            "ok": "Funcionando",
            "warn": "Parcial",
            "down": "Nao conectado",
        }.get(state, "Revisar"),
    }
    if extra:
        payload.update(extra)
    return payload


def _pdpj_status(org_id=None) -> dict:
    try:
        from services.comunicaapi import pdpj_auth

        auth = pdpj_auth.public_status(org_id)
        if auth.get("token_cached"):
            return _status(
                "PDPJ/CNJ",
                "ok",
                "Autenticacao oficial encontrada.",
                "Fonte preferencial para intimacoes e prazos processuais.",
                "Abrir Controladoria",
                f"{PREFIX}/controladoria",
                "scale-balanced",
                f"{PREFIX}/oauth/pdpj/status",
                "Status tecnico",
            )
        if auth.get("configured"):
            code = auth.get("last_error_code") or "auth_pending"
            reason = auth.get("last_error_message") or "Credenciais existem, mas o token PDPJ ainda nao foi validado."
            if code == "invalid_client":
                reason = "PDPJ rejeitou client_id/client_secret; e necessario validar a credencial/autorizacao no CNJ."
            return _status(
                "PDPJ/CNJ",
                "down",
                "Autorizacao oficial pendente.",
                reason,
                "Ver status",
                f"{PREFIX}/controladoria",
                "scale-balanced",
                f"{PREFIX}/oauth/pdpj/connect",
                "Conectar PDPJ",
                [
                    "Confirmar no CNJ/PDPJ que o client_id esta autorizado para o CaseHub.",
                    "Entrar como administrador e usar o fluxo Conectar PDPJ.",
                    "Validar a busca por OAB na Controladoria antes de considerar a importacao oficial ativa.",
                ],
                diagnostic=code,
            )
    except Exception:
        pass
    return _status(
        "PDPJ/CNJ",
        "down",
        "Credenciais oficiais ausentes ou nao lidas.",
        "Sem essa autorizacao, o CaseHub nao pode prometer importacao automatica oficial de prazos por OAB.",
        "Ver Controladoria",
        f"{PREFIX}/controladoria",
        "scale-balanced",
        f"{PREFIX}/oauth/pdpj/connect",
        "Conectar PDPJ",
        [
            "Solicitar ou confirmar credenciais oficiais PDPJ/CNJ.",
            "Configurar PDPJ_CLIENT_ID e PDPJ_CLIENT_SECRET no servidor.",
            "Usar Conectar PDPJ para gerar refresh_token quando o CNJ exigir authorization_code.",
        ],
    )


def _integration_cards(org_id: int | None = None, db: Session | None = None) -> list[dict]:
    calendar_count = 0
    calendar_has_client = False
    calendar_diag = "Google Calendar ainda nao validado."
    try:
        calendar_service = GoogleCalendarService()
        calendar_accounts = calendar_service.get_connected_accounts(verify_live=True)
        calendar_count = sum(1 for account in calendar_accounts if account.get("connected"))
        calendar_has_client = bool(calendar_service.get_client_redirect_uris())
        calendar_diag = "OAuth client local encontrado." if calendar_has_client else "Arquivo OAuth local ausente ou sem redirect URIs."
    except Exception as exc:
        calendar_diag = f"Probe indisponivel: {type(exc).__name__}."

    # Gmail OAuth probe — same multi-tenant pattern as Calendar/Drive.
    # GMAIL_OAUTH_ENABLED feature flag lets ops hide the card without removing
    # the route (set False to revert to "Em breve" SMTP-only UI).
    gmail_oauth_enabled = bool(getattr(settings, "GMAIL_OAUTH_ENABLED", False))
    gmail_count = 0
    gmail_email = ""
    gmail_has_client = False
    gmail_diag = "Gmail OAuth ainda nao validado."
    if gmail_oauth_enabled:
        try:
            from services.gmail_service import GmailService

            gmail_service = GmailService(org_id=org_id)
            gmail_accounts = gmail_service.get_connected_accounts(verify_live=True)
            gmail_count = sum(1 for account in gmail_accounts if account.get("connected"))
            if gmail_accounts:
                connected_account = next(
                    (a for a in gmail_accounts if a.get("connected")),
                    None,
                )
                if connected_account:
                    gmail_email = connected_account.get("connected_email") or ""
            gmail_has_client = bool(gmail_service.get_client_redirect_uris())
            gmail_diag = (
                "OAuth client local encontrado."
                if gmail_has_client
                else "Arquivo OAuth local ausente ou sem redirect URIs."
            )
        except Exception as exc:
            gmail_diag = f"Probe indisponivel: {type(exc).__name__}."
    drive_root_id, drive_root_source = _google_drive_root_status(db, org_id)
    drive_root = bool(drive_root_id)
    drive_credentials_path, drive_token_path = _google_drive_paths(org_id)
    drive_token = drive_token_path.exists()
    drive_credentials = drive_credentials_path.exists()
    drive_state = "ok" if drive_root and drive_token else ("warn" if drive_token or drive_credentials else "down")
    drive_action_url = f"{PREFIX}/documents" if drive_token else f"{PREFIX}/integrations/google-drive/connect"
    drive_action_label = "Abrir documentos" if drive_token else "Conectar Drive"
    drive_summary = (
        "Drive pronto para arquivos."
        if drive_root and drive_token
        else "Drive conectado; Explorer abre Meu Drive." if drive_token
        else "Drive ainda nao validado."
    )
    drive_detail = (
        "Documentos locais continuam acessiveis; Explorer usa a pasta raiz do escritorio."
        if drive_root and drive_token
        else "Documentos locais continuam acessiveis; sem pasta raiz do escritorio, o Explorer abre Meu Drive e uploads organizados continuam pendentes."
        if drive_token
        else "Documentos locais continuam acessiveis; conecte o OAuth Drive para listar arquivos do Google Drive."
    )
    whatsapp_ok, whatsapp_diag, whatsapp_payload = _json_probe(settings.WHATSAPP_BOT_URL, "/api/status")
    if not whatsapp_payload:
        whatsapp_ok, whatsapp_diag = _http_probe(settings.WHATSAPP_BOT_URL)
    maestro_ok, maestro_diag = _http_probe(os.getenv("OLLAMA_URL", ""), "/api/tags")
    stripe_ready = bool(settings.STRIPE_SECRET_KEY and settings.STRIPE_WEBHOOK_SECRET)
    stripe_partial = bool(settings.STRIPE_SECRET_KEY or settings.STRIPE_PUBLISHABLE_KEY)
    twilio_ready = bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and (settings.TWILIO_FROM_NUMBER or settings.TWILIO_WHATSAPP_FROM))
    twilio_partial = bool(settings.TWILIO_ACCOUNT_SID or settings.TWILIO_AUTH_TOKEN or settings.TWILIO_FROM_NUMBER or settings.TWILIO_WHATSAPP_FROM)
    moskit_ready = bool(settings.MOSKIT_API_KEY and settings.MOSKIT_RESPONSIBLE_ID and settings.MOSKIT_PIPELINE_ID)
    moskit_partial = bool(settings.MOSKIT_API_KEY or settings.MOSKIT_RESPONSIBLE_ID or settings.MOSKIT_PIPELINE_ID)
    webhooks_ready = bool(settings.CRM_WEBHOOK_API_KEY)
    smtp_secret = settings.SMTP_PASS or os.getenv("SMTP_PASSWORD") or os.getenv("GMAIL_CENTER_APP_PASSWORD")
    smtp_reachable = _tcp_probe(settings.SMTP_HOST, settings.SMTP_PORT)

    cards = [
        _status(
            "WhatsApp Chat",
            "ok" if whatsapp_ok else "down",
            "Sessao WhatsApp pronta para listar conversas." if whatsapp_ok else "Sessao WhatsApp nao validada.",
            "A tela de atendimento usa o bot lite e agora consulta conversas/mensagens reais do whatsapp-web.js.",
            "Abrir chat",
            f"{PREFIX}/whatsapp-chat",
            "message-circle",
            f"{settings.WHATSAPP_BOT_URL.rstrip('/') + '/api/status' if settings.WHATSAPP_BOT_URL else '#'}",
            "Status tecnico",
            [
                "Confirmar que o container whatsapp-bot esta em ready.",
                "Validar que /api/conversations retorna conversas reais, sem abrir QR/reconnect.",
                "Usar a tela WhatsApp Chat para atendimento humano dentro do shell.",
            ],
            diagnostic=whatsapp_diag,
        ),
        _status(
            "Maestro",
            "ok" if maestro_ok else "warn",
            "Modelo local respondeu." if maestro_ok else "Modulo visivel; IA local depende do Ollama.",
            "Assistente interno para chat, sugestoes e apoio ao CaseHub.md.",
            "Abrir Maestro",
            f"{PREFIX}/assistente",
            "sparkles",
            f"{PREFIX}/assistente/config",
            "Configurar",
            [
                "Manter OLLAMA_URL acessivel no ambiente do app.",
                "Abrir o modulo Maestro pelo shell e validar sugestoes em rotas seguras.",
                "Nao ativar coleta de treinamento sem decisao explicita.",
            ],
            diagnostic=maestro_diag,
        ),
        _status(
            "Moskit / Leads",
            "ok" if moskit_ready else ("warn" if moskit_partial else "down"),
            "Pipeline Moskit configurado." if moskit_ready else "Credenciais Moskit incompletas.",
            "Integra leads, funil e handoff comercial com o workspace.",
            "Abrir Leads",
            f"{PREFIX}/leads",
            "chart-no-axes-column",
            f"{PREFIX}/moskit",
            "Painel Moskit",
            [
                "Configurar MOSKIT_API_KEY.",
                "Configurar MOSKIT_RESPONSIBLE_ID e MOSKIT_PIPELINE_ID.",
                "Validar importacao/sync pelo painel de leads antes de automacoes.",
            ],
            diagnostic=f"api_key={'sim' if settings.MOSKIT_API_KEY else 'nao'}; responsavel={'sim' if settings.MOSKIT_RESPONSIBLE_ID else 'nao'}; pipeline={'sim' if settings.MOSKIT_PIPELINE_ID else 'nao'}",
        ),
        _status(
            "Stripe / Assinatura",
            "ok" if stripe_ready else ("warn" if stripe_partial else "down"),
            "Stripe pronto para webhooks." if stripe_ready else "Stripe parcialmente configurado.",
            "Status de billing e checkout; nao altera produtos/precos nesta tela.",
            "Abrir assinatura",
            f"{PREFIX}/subscription",
            "credit-card",
            "https://dashboard.stripe.com/apikeys",
            "Stripe",
            [
                "Configurar STRIPE_SECRET_KEY e STRIPE_WEBHOOK_SECRET.",
                "Validar webhook antes de depender de automacao de assinatura.",
                "Manter alteracao de precos fora desta tela.",
            ],
            diagnostic=f"secret={'sim' if settings.STRIPE_SECRET_KEY else 'nao'}; publishable={'sim' if settings.STRIPE_PUBLISHABLE_KEY else 'nao'}; webhook={'sim' if settings.STRIPE_WEBHOOK_SECRET else 'nao'}",
        ),
        _status(
            "Twilio / SMS",
            "ok" if twilio_ready else ("warn" if twilio_partial else "down"),
            "Twilio pronto." if twilio_ready else "Twilio/SMS pendente.",
            "Canal telefonia/SMS separado do WhatsApp Web.",
            "Abrir Twilio",
            f"{PREFIX}/twilio",
            "phone",
            "https://console.twilio.com/",
            "Twilio Console",
            [
                "Configurar TWILIO_ACCOUNT_SID e TWILIO_AUTH_TOKEN.",
                "Configurar numero de envio SMS e/ou WhatsApp Twilio.",
                "Validar envio teste em ambiente controlado.",
            ],
            diagnostic=f"sid={'sim' if settings.TWILIO_ACCOUNT_SID else 'nao'}; token={'sim' if settings.TWILIO_AUTH_TOKEN else 'nao'}; from={'sim' if settings.TWILIO_FROM_NUMBER else 'nao'}; wa_from={'sim' if settings.TWILIO_WHATSAPP_FROM else 'nao'}",
        ),
        _status(
            "Webhooks CRM",
            "ok" if webhooks_ready else "down",
            "Chave de webhook configurada." if webhooks_ready else "Chave CRM_WEBHOOK_API_KEY ausente.",
            "Recebe eventos externos de leads, notificacoes e automacoes controladas.",
            "Abrir webhooks",
            f"{PREFIX}/webhooks",
            "workflow",
            f"{PREFIX}/route-map",
            "Ver rotas",
            [
                "Configurar CRM_WEBHOOK_API_KEY.",
                "Validar origem e assinatura antes de aceitar eventos externos.",
                "Monitorar logs de webhooks no painel.",
            ],
            diagnostic=f"api_key={'sim' if webhooks_ready else 'nao'}",
        ),
        _status(
            "Google Calendar",
            "ok" if calendar_count else ("warn" if calendar_has_client else "down"),
            f"{calendar_count} agenda validada" if calendar_count else "Aguardando OAuth Google valido.",
            "A agenda local funciona. A sincronizacao Google so fica ativa quando o OAuth aceita o redirect URI deste ambiente.",
            "Configurar agenda",
            f"{PREFIX}/google-calendar/settings",
            "calendar-days",
            "https://console.cloud.google.com/apis/credentials",
            "Abrir Google Cloud",
            [
                "Criar ou editar um OAuth Client do tipo Web application.",
                "Adicionar o redirect URI mostrado na tela Google Calendar do CaseHub.",
                "Entrar com a conta Google do escritorio e validar se os eventos aparecem.",
            ],
            diagnostic=calendar_diag,
            lgpd_notice="Ao conectar, voce autoriza o CaseHub a ler eventos da agenda do escritorio (escopo calendar.events). Voce pode revogar a qualquer momento na pagina 'Configurar agenda'. Dados ficam isolados no escritorio (multi-tenant) e nada e compartilhado entre orgs. LGPD: ver Termos.",
        ),
        _pdpj_status(org_id),
        _status(
            "DataJud",
            "ok",
            "Fallback publico CNJ pronto.",
            "Ajuda em consultas subsidiarias, mas nao substitui intimacoes oficiais PDPJ.",
            "Abrir Controladoria",
            f"{PREFIX}/controladoria",
            "landmark",
            "https://www.cnj.jus.br/sistemas/datajud/api-publica/",
            "Manual CNJ",
            [
                "Usar como apoio para consulta processual por numero/processo.",
                "Nao tratar como importacao oficial de intimacoes.",
                "Registrar manualmente prazos confirmados enquanto PDPJ nao estiver ativo.",
            ],
        ),
        _status(
            "Escavador",
            "ok" if settings.ESCAVADOR_API_KEY else "down",
            "Chave configurada." if settings.ESCAVADOR_API_KEY else "Chave de API ausente.",
            "Pode apoiar publicacoes e consultas quando configurado.",
            "Abrir Controladoria",
            f"{PREFIX}/controladoria",
            "magnifying-glass-chart",
            "https://api.escavador.com/v2/docs/",
            "Criar chave",
            [
                "Criar conta/contrato no Escavador e gerar Personal Access Token.",
                "Configurar ESCAVADOR_API_KEY no .env da instancia.",
                "Reiniciar o container e validar a busca subsidiaria na Controladoria.",
            ],
        ),
        _status(
            "JusBrasil",
            "ok" if settings.JUSBRASIL_API_KEY else "down",
            "Chave configurada." if settings.JUSBRASIL_API_KEY else "Chave de API ausente.",
            "Pode apoiar diarios/publicacoes quando configurado.",
            "Abrir Controladoria",
            f"{PREFIX}/controladoria",
            "newspaper",
            "https://api.jusbrasil.com.br/docs/autenticacao/api_key.html",
            "Criar token",
            [
                "Contratar/acessar Jusbrasil Solucoes e obter API Key.",
                "Configurar JUSBRASIL_API_KEY no .env da instancia.",
                "Reiniciar o container e validar diarios/publicacoes como apoio.",
            ],
        ),
        _status(
            "Google Drive",
            drive_state,
            drive_summary,
            drive_detail,
            drive_action_label,
            drive_action_url,
            "folder-open",
            f"{PREFIX}/integrations/google-drive/connect",
            "OAuth Drive",
            [
                "Ativar Google Drive API no Google Cloud.",
                "Usar o OAuth client compartilhado em credentials/google_client_secret.json ou credentials/google_drive_credentials.json.",
                "Entrar com a conta Google do escritorio pelo botao OAuth Drive.",
                "Configurar a pasta raiz do escritorio em GOOGLE_DRIVE_ROOT_ID ou organizations.google_drive_root_id para uploads organizados.",
            ],
            diagnostic=(
                f"org_id={org_id or 'default'}; root_id={'sim' if drive_root else 'nao'}; "
                f"root_source={drive_root_source}; token={'sim' if drive_token else 'nao'}; "
                f"credentials={'sim' if drive_credentials else 'nao'}; oauth_web=sim"
            ),
            disconnect_url=(f"{PREFIX}/integrations/google-drive/disconnect" if drive_token else ""),
            lgpd_notice="Ao conectar, voce autoriza o CaseHub a acessar arquivos do Drive do escritorio. Voce pode revogar a qualquer momento clicando em Desconectar. Dados ficam isolados no escritorio (multi-tenant) e nada e compartilhado entre orgs. LGPD: ver Termos.",
            extra={
                "drive_root_id": drive_root_id,
                "drive_root_source": drive_root_source,
            },
        ),
        _status(
            "E-mail (SMTP/IMAP)",
            "ok" if settings.SMTP_USER and smtp_secret and smtp_reachable else ("warn" if settings.SMTP_USER and smtp_secret else "down"),
            "SMTP pronto para teste." if settings.SMTP_USER and smtp_secret and smtp_reachable else "Conecte sua conta de e-mail em 3 passos.",
            "Suporta Gmail, Outlook, iCloud, Hostinger, IMAP/SMTP genericos. Use senha de app quando 2FA estiver ativo.",
            "Configurar SMTP",
            f"{PREFIX}/integrations/email/smtp-setup",
            "envelope",
            f"{PREFIX}/integrations/email/smtp-setup#tutorial",
            "Tutorial completo",
            [
                "Ative 2FA na sua conta de e-mail e crie uma senha de app dedicada.",
                "Use as configuracoes pre-prontas (Gmail/Outlook/iCloud) ou IMAP/SMTP customizado.",
                "Teste envio + recebimento antes de habilitar templates automaticos.",
            ],
            diagnostic=f"host={'ok' if smtp_reachable else 'sem conexao'}; usuario={'sim' if settings.SMTP_USER else 'nao'}; segredo={'sim' if smtp_secret else 'nao'}",
        ),
        _status(
            "Gmail OAuth",
            ("ok" if gmail_count else ("warn" if gmail_has_client else "down"))
            if gmail_oauth_enabled
            else "warn",
            (
                f"Conectado a {gmail_email}" if gmail_count and gmail_email
                else "Caixa Gmail conectada." if gmail_count
                else "Login com Google em 1 clique (escopo leitura + envio)."
            ) if gmail_oauth_enabled else "Em breve — fase 2 multi-tenant.",
            (
                "Caixa de entrada do escritorio sincronizada via Gmail API. Token isolado por escritorio (multi-tenant)."
                if gmail_oauth_enabled
                else "Login com Google em 1 clique para sincronizar caixa de entrada sem senha de app. Liberado apos alpha 30/05."
            ),
            (
                "Desconectar Gmail" if gmail_count and gmail_oauth_enabled
                else "Conectar Gmail" if gmail_oauth_enabled
                else "Saiba mais"
            ),
            (
                f"{PREFIX}/gmail/connect/info" if gmail_oauth_enabled
                else f"{PREFIX}/integrations/email/smtp-setup"
            ),
            "envelope-open-text",
            (
                f"{PREFIX}/gmail/status" if gmail_oauth_enabled
                else "https://developers.google.com/gmail/api/quickstart"
            ),
            "Status tecnico" if gmail_oauth_enabled else "Doc oficial Gmail API",
            [
                "Crie/edite o OAuth Client (Web application) no Google Cloud Console.",
                "Adicione o redirect URI deste ambiente em Authorized Redirect URIs.",
                "Clique em Conectar Gmail e entre com a conta Google do escritorio.",
            ] if gmail_oauth_enabled else [
                "Pos-alpha: vamos enumerar Authorized Redirect URIs por tenant no Google Cloud Console.",
                "Por enquanto, use SMTP com senha de app (acima) — entrega e recebimento funcionam normalmente.",
                "Nenhuma diferenca de funcionalidade para o usuario final entre SMTP e OAuth.",
            ],
            diagnostic=(
                f"oauth_gmail=ativo; conectado={'sim' if gmail_count else 'nao'}; email={gmail_email or 'n/a'}; client={'sim' if gmail_has_client else 'nao'}"
                if gmail_oauth_enabled else "oauth_gmail=pendente; usar SMTP no card acima"
            ),
            disconnect_url=(
                f"{PREFIX}/gmail/disconnect/info" if (gmail_oauth_enabled and gmail_count) else ""
            ),
            lgpd_notice=(
                "Ao conectar, voce autoriza o CaseHub a ler e enviar e-mails da conta Gmail do escritorio "
                "(escopos gmail.readonly + gmail.send). Token armazenado isolado por escritorio (multi-tenant). "
                "Voce pode revogar a qualquer momento clicando em Desconectar Gmail ou em https://myaccount.google.com/permissions. "
                "LGPD: ver Termos."
                if gmail_oauth_enabled else ""
            ),
        ),
    ]
    return cards


# OAuth error code → user-friendly PT-BR message
# Used to translate redirect-back error params (?drive_error=foo) into a
# readable banner instead of exposing OAuth jargon to the end user.
OAUTH_FRIENDLY_ERRORS = {
    "redirect_uri_mismatch": (
        "URL de retorno nao autorizada. Suporte: support@example.com"
    ),
    "invalid_grant": "Token expirado. Tente reconectar.",
    "access_denied": (
        "Voce cancelou a permissao. Tudo bem — pode tentar de novo quando quiser."
    ),
    "no_tenant_context": (
        "Sessao sem contexto de escritorio. Faca login novamente."
    ),
    "credentials_missing": (
        "Credenciais OAuth do Google ainda nao configuradas neste servidor. "
        "Suporte: support@example.com"
    ),
    "oauth_start_failed": (
        "Nao foi possivel iniciar o login Google. Tente novamente em alguns segundos."
    ),
    "missing_code": (
        "Resposta do Google chegou incompleta. Tente conectar de novo."
    ),
    "invalid_state": (
        "Sessao OAuth expirou ou foi adulterada. Conecte novamente a partir desta tela."
    ),
    "oauth_callback_failed": (
        "Algo deu errado ao receber a resposta do Google. Tente novamente; se persistir, "
        "support@example.com."
    ),
    "disconnect_noop": (
        "Nada para desconectar — Drive ja estava desligado deste escritorio."
    ),
    "disconnect_failed": (
        "Nao foi possivel desconectar agora. Tente em alguns segundos."
    ),
    "invalid_drive_root_id": (
        "Cole um ID de pasta do Google Drive ou um link valido de pasta."
    ),
    "drive_root_admin_required": (
        "Apenas administradores podem alterar a raiz do Drive do escritorio."
    ),
    "drive_root_save_failed": (
        "Nao foi possivel salvar a raiz do Drive agora. Tente novamente."
    ),
    # Gmail OAuth — same surface as Drive/Calendar, plus a couple of extras.
    "org_mismatch": (
        "Seguranca: o consentimento veio para outro escritorio. Conecte novamente."
    ),
    "auth_failed": (
        "Nao foi possivel completar o login com o Google. Tente novamente."
    ),
}


def _friendly_error(code: str | None) -> str:
    if not code:
        return ""
    return OAUTH_FRIENDLY_ERRORS.get(
        code,
        f"Erro do Google: {code}. Suporte: support@example.com",
    )


@router.get("", response_class=HTMLResponse)
async def integrations_index(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    drive_error_code = request.query_params.get("drive_error")
    drive_error_friendly = _friendly_error(drive_error_code)
    gmail_error_code = request.query_params.get("gmail_error")
    gmail_error_friendly = _friendly_error(gmail_error_code)

    return templates.TemplateResponse(
        "integrations/index.html",
        {
            "request": request,
            "user": user,
            "PREFIX": PREFIX,
            "integrations": _integration_cards(getattr(request.state, "org_id", None), db),
            "drive_error_friendly": drive_error_friendly,
            "drive_disconnected": bool(request.query_params.get("drive_disconnected")),
            "drive_root_saved": bool(request.query_params.get("drive_root_saved")),
            "drive_root_cleared": bool(request.query_params.get("drive_root_cleared")),
            "gmail_error_friendly": gmail_error_friendly,
            "gmail_connected": bool(request.query_params.get("gmail_connected")),
            "gmail_disconnected": bool(request.query_params.get("gmail_disconnected")),
            **inject_org_context(request, user),
        },
    )


@router.post("/google-drive/root-folder")
async def google_drive_root_folder(request: Request, db: Session = Depends(get_db)):
    """Persist the tenant default Drive folder id without touching OAuth."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    if getattr(user, "user_type", "") not in ("admin", "superadmin"):
        return RedirectResponse(
            url=f"{PREFIX}/integrations?drive_error=drive_root_admin_required",
            status_code=302,
        )

    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        return RedirectResponse(
            url=f"{PREFIX}/integrations?drive_error=no_tenant_context",
            status_code=302,
        )

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org is None:
        return RedirectResponse(
            url=f"{PREFIX}/integrations?drive_error=no_tenant_context",
            status_code=302,
        )

    try:
        form = await request.form()
        raw_id = (form.get("drive_root_id") or "").strip()
        if raw_id == "":
            org.google_drive_root_id = None
            db.commit()
            logger.info(
                "Drive root cleared org_id=%s user_id=%s",
                org_id,
                getattr(user, "id", None),
            )
            return RedirectResponse(
                url=f"{PREFIX}/integrations?drive_root_cleared=1",
                status_code=302,
            )

        from routes.clients import _parse_drive_folder_id

        folder_id = _parse_drive_folder_id(raw_id)
        if not folder_id:
            return RedirectResponse(
                url=f"{PREFIX}/integrations?drive_error=invalid_drive_root_id",
                status_code=302,
            )

        org.google_drive_root_id = folder_id
        db.commit()
        logger.info(
            "Drive root saved org_id=%s user_id=%s",
            org_id,
            getattr(user, "id", None),
        )
        return RedirectResponse(
            url=f"{PREFIX}/integrations?drive_root_saved=1",
            status_code=302,
        )
    except Exception:
        db.rollback()
        logger.exception("Failed to save Drive root for org %s", org_id)
        return RedirectResponse(
            url=f"{PREFIX}/integrations?drive_error=drive_root_save_failed",
            status_code=302,
        )


@router.post("/email/smtp-test")
async def email_smtp_test(request: Request, db: Session = Depends(get_db)):
    """Valida credenciais SMTP via conexão TLS + login real (sem persistir).

    Persistência das credenciais segue em env-var via Settings — para não vazar
    senha de app no DB. Este endpoint só valida que os dados informados
    chegariam ao servidor com sucesso.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        form = await request.form()
        host = (form.get("smtp_host") or "").strip()
        port = int(form.get("smtp_port") or 587)
        user_email = (form.get("smtp_user") or "").strip()
        password = (form.get("smtp_password") or "").strip()
    except Exception as e:
        return JSONResponse({"success": False, "error": f"Form inválido: {e}"}, status_code=400)

    if not (host and port and user_email):
        return JSONResponse({"success": False, "error": "host, porta e usuário são obrigatórios"}, status_code=400)
    if not password:
        return JSONResponse({"success": False, "error": "Cole a senha de app antes de testar"}, status_code=400)

    import smtplib
    import socket
    import ssl
    try:
        if port == 465:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, timeout=10, context=ctx) as smtp:
                smtp.login(user_email, password)
        else:
            with smtplib.SMTP(host, port, timeout=10) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(user_email, password)
        return JSONResponse({
            "success": True,
            "message": f"SMTP {host}:{port} conectou com {user_email}. Salve as credenciais no .env do servidor para persistir.",
        })
    except smtplib.SMTPAuthenticationError as e:
        return JSONResponse({
            "success": False,
            "error": "Login recusado — verifique se está usando uma senha de app (não a senha principal) e que 2FA está ativo na conta.",
        }, status_code=401)
    except (socket.timeout, smtplib.SMTPConnectError) as e:
        return JSONResponse({
            "success": False,
            "error": f"Servidor {host}:{port} inalcançável — confirme host/porta.",
        }, status_code=502)
    except ssl.SSLError as e:
        return JSONResponse({
            "success": False,
            "error": f"Erro TLS — tente porta {'465' if port == 587 else '587'}.",
        }, status_code=400)
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"Erro inesperado: {type(e).__name__}: {e}",
        }, status_code=500)


@router.get("/email/smtp-setup", response_class=HTMLResponse)
async def email_smtp_setup(request: Request, db: Session = Depends(get_db)):
    """Tutorial + form de configuração SMTP/IMAP com presets de provedores."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    return templates.TemplateResponse(
        "integrations/email_smtp_setup.html",
        {
            "request": request,
            "user": user,
            "PREFIX": PREFIX,
            "current": {
                "smtp_host": settings.SMTP_HOST or "",
                "smtp_port": settings.SMTP_PORT or 587,
                "smtp_user": settings.SMTP_USER or "",
                "smtp_configured": bool(settings.SMTP_USER and (settings.SMTP_PASS or os.getenv("SMTP_PASSWORD"))),
            },
            **inject_org_context(request, user),
        },
    )


@router.get("/google-drive/connect")
async def google_drive_connect(request: Request, db: Session = Depends(get_db)):
    """Start a web OAuth flow that creates the per-org Drive token."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        # TenantMiddleware should always set this; refuse to start a flow
        # that cannot resolve to a token path.
        return RedirectResponse(
            url=f"{PREFIX}/integrations?drive_error=no_tenant_context",
            status_code=302,
        )

    credentials_path, _token_path = _google_drive_paths(org_id)
    if not credentials_path.exists():
        return RedirectResponse(
            url=f"{PREFIX}/integrations?drive_error=credentials_missing",
            status_code=302,
        )

    try:
        from google_auth_oauthlib.flow import Flow

        flow = Flow.from_client_secrets_file(
            str(credentials_path),
            scopes=["https://www.googleapis.com/auth/drive"],
            redirect_uri=_google_drive_redirect_uri(request),
        )
        auth_url, _state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=_encode_drive_oauth_state(user, org_id),
        )
        return RedirectResponse(url=auth_url, status_code=302)
    except Exception:
        return RedirectResponse(
            url=f"{PREFIX}/integrations?drive_error=oauth_start_failed",
            status_code=302,
        )


@router.get("/google-drive/callback")
async def google_drive_callback(request: Request, db: Session = Depends(get_db)):
    """Persist the connected Google account token for Drive/Docs operations.

    Token is written as JSON (``creds.to_json()``) into the per-org
    ``credentials/org_{id}/drive_token.json`` path. Pickle is no longer
    used anywhere in the Drive pipeline.
    """
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        return RedirectResponse(
            url=f"{PREFIX}/integrations?drive_error=no_tenant_context",
            status_code=302,
        )

    if request.query_params.get("error"):
        return RedirectResponse(
            url=f"{PREFIX}/integrations?drive_error={request.query_params.get('error')}",
            status_code=302,
        )
    code = request.query_params.get("code")
    if not code:
        return RedirectResponse(url=f"{PREFIX}/integrations?drive_error=missing_code", status_code=302)
    if not _decode_drive_oauth_state(request.query_params.get("state", ""), user, org_id):
        return RedirectResponse(url=f"{PREFIX}/integrations?drive_error=invalid_state", status_code=302)

    credentials_path, token_path = _google_drive_paths(org_id)
    try:
        from google_auth_oauthlib.flow import Flow

        flow = Flow.from_client_secrets_file(
            str(credentials_path),
            scopes=["https://www.googleapis.com/auth/drive"],
            redirect_uri=_google_drive_redirect_uri(request),
        )
        flow.fetch_token(code=code)

        # JSON token written atomically with 0o600 (same primitive as Calendar).
        token_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                fd = None
                handle.write(flow.credentials.to_json())
        finally:
            if fd is not None:
                os.close(fd)
        os.chmod(token_path, 0o600)

        return RedirectResponse(url=f"{PREFIX}/integrations?drive_connected=1", status_code=302)
    except Exception:
        logger.exception("Drive OAuth callback failed for org %s", org_id)
        return RedirectResponse(
            url=f"{PREFIX}/integrations?drive_error=oauth_callback_failed",
            status_code=302,
        )


@router.post("/google-drive/disconnect")
async def google_drive_disconnect(request: Request, db: Session = Depends(get_db)):
    """Revoke and remove the per-org Drive OAuth token.

    Calls ``GoogleDriveHandler.disconnect_drive_account()`` so the refresh
    token is revoked on Google and the local ``credentials/org_{id}/
    drive_token.json`` is deleted. Returns the integrations page with a
    ``drive_disconnected`` query param so the UI can flash a banner.
    """
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        return RedirectResponse(
            url=f"{PREFIX}/integrations?drive_error=no_tenant_context",
            status_code=302,
        )

    try:
        from services.google_drive_handler import GoogleDriveHandler

        handler = GoogleDriveHandler(db, org_id=org_id)
        outcome = handler.disconnect_drive_account()
        flag = "drive_disconnected=1" if outcome.get("removed_file") else "drive_error=disconnect_noop"
    except Exception:
        logger.exception("Drive disconnect failed for org %s", org_id)
        flag = "drive_error=disconnect_failed"

    return RedirectResponse(url=f"{PREFIX}/integrations?{flag}", status_code=302)
