"""
CaseHub - Gmail OAuth integration routes (per-org multi-tenant).

Mirrors `routes/google_calendar.py`:
- HMAC-signed state with org_id claim
- Dynamic redirect_uri (preserves subdomain)
- Per-tenant token storage via `services.gmail_service.GmailService`

Endpoints:
- GET  /casehub/gmail/connect/{account_name}  -> redirect to Google consent
- GET  /casehub/gmail/callback                -> exchange code, write token
- POST /casehub/gmail/disconnect/{account_name} -> revoke + delete token
- GET  /casehub/gmail/status                  -> JSON state for the org
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from auth import get_current_user
from config import settings
from core.template_config import PREFIX, templates
from models import User, get_db
from services.gmail_service import GmailService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gmail", tags=["gmail"])


# ----------------------------------------------------------------------
# Account name sanitization (mirrors google_calendar Sentinela T6 hardening)
# ----------------------------------------------------------------------

ACCOUNT_SLUGS = {
    "info": "info",
    "principal": "info",
}

ACCOUNT_LABELS = {
    "info": "Caixa de entrada principal",
}

_SAFE_ACCOUNT_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

OAUTH_STATE_MAX_AGE_SECONDS = 10 * 60


def _account_id(value: str) -> str:
    candidate = (value or "").strip().lower()
    mapped = ACCOUNT_SLUGS.get(candidate)
    if mapped is not None:
        return mapped
    if _SAFE_ACCOUNT_ID.match(candidate):
        return candidate
    return ""


def _require_account_id(value: str) -> str:
    """Hard-fail HTTP 400 when account name fails the safe regex."""
    resolved = _account_id(value)
    if not resolved or not _SAFE_ACCOUNT_ID.match(resolved):
        raise HTTPException(status_code=400, detail="invalid account name")
    return resolved


# ----------------------------------------------------------------------
# HMAC-signed OAuth state (binds org_id to the consent round-trip)
# ----------------------------------------------------------------------

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


def _encode_oauth_state(account_name: str, user, request: Request, org_id: Optional[int] = None) -> str:
    """Encode signed OAuth state with org_id binding.

    The `org` claim binds the OAuth round-trip to a specific tenant so that
    a callback hitting another subdomain (or a stale state replay across
    tenants) fails the org_mismatch check.
    """
    payload = {
        "scope": "gmail",
        "account": _account_id(account_name),
        "uid": getattr(user, "id", None),
        "sub": getattr(user, "email", ""),
        "org": org_id if org_id is not None else getattr(request.state, "org_id", None),
        "iat": int(time.time()),
        "nonce": secrets.token_urlsafe(16),
    }
    encoded = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{encoded}.{_oauth_state_signature(encoded)}"


def _decode_oauth_state_payload(state: str, user=None) -> Optional[dict]:
    try:
        encoded, signature = (state or "").split(".", 1)
    except ValueError:
        return None

    expected = _oauth_state_signature(encoded)
    if not hmac.compare_digest(signature, expected):
        return None

    try:
        payload = json.loads(_b64url_decode(encoded).decode("utf-8"))
    except Exception:
        return None

    now = int(time.time())
    issued_at = int(payload.get("iat") or 0)
    if not (now - OAUTH_STATE_MAX_AGE_SECONDS <= issued_at <= now + 60):
        return None
    if payload.get("scope") != "gmail":
        return None

    if user is not None:
        if payload.get("uid") != getattr(user, "id", None):
            return None
        if payload.get("sub") != getattr(user, "email", ""):
            return None

    account = _account_id(payload.get("account") or "")
    if not account:
        return None
    payload["account"] = account
    return payload


def _oauth_state_user_is_valid(
    payload: Optional[dict],
    db: Session,
    current_user=None,
    request: Optional[Request] = None,
) -> bool:
    """Validate signed state payload against current user + tenant.

    Rejects state where the encoded `org` claim differs from the live
    request's `request.state.org_id` (set by TenantMiddleware).
    """
    if not payload:
        return False

    uid = payload.get("uid")
    email = str(payload.get("sub") or "").strip()
    if not uid or not email:
        return False

    if current_user is not None:
        if uid != getattr(current_user, "id", None):
            return False
        if email != getattr(current_user, "email", ""):
            return False

    if request is not None:
        request_org = getattr(request.state, "org_id", None)
        payload_org = payload.get("org")
        if request_org is not None and payload_org is not None and request_org != payload_org:
            return False

    return db.query(User).filter(
        User.id == uid,
        User.email == email,
        User.enabled.is_(True),
    ).first() is not None


# ----------------------------------------------------------------------
# Redirect URI (dynamic — preserves tenant subdomain)
# ----------------------------------------------------------------------

def _configured_origin() -> str:
    return (settings.BASE_URL or "").strip().rstrip("/")


# Allowlist of domain roots trusted for OAuth redirect targets.
# Subdomain tenants (e.g. tenanta.casehub.legal) match via the suffix
# check.  Anchored suffix — "evil.casehub.legal.evil.com".endswith(".casehub.legal")
# is False, so hostname injection cannot escalate past known roots.
_REDIRECT_ALLOWED_ROOTS: frozenset[str] = frozenset({
    "localhost",
    "127.0.0.1",
    "casehub.io",
    "casehub.legal",
    "demo.casehub.example",
    "casehub.example",
})


def _return_host_allowed(host: str) -> bool:
    host = (host or "").split(":")[0].lower().rstrip(".")
    if not host:
        return False
    if host in _REDIRECT_ALLOWED_ROOTS:
        return True
    return any(host.endswith("." + root) for root in _REDIRECT_ALLOWED_ROOTS)


def _gmail_redirect_uri(request: Request) -> str:
    """Derive OAuth redirect_uri from the current request (preserves subdomain).

    Same logic as Calendar — never blindly trust `settings.BASE_URL` because
    multi-subdomain tenancy needs the callback to land on the same host that
    started the consent flow.
    """
    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.netloc
        or ""
    ).split(",")[0].strip()

    proto = (
        request.headers.get("x-forwarded-proto")
        or request.url.scheme
        or "https"
    ).split(",")[0].strip()

    if proto == "http" and host and not host.startswith(("localhost", "127.0.0.1")):
        proto = "https"

    if not host:
        configured = _configured_origin()
        return f"{configured}{PREFIX}/gmail/callback"

    return f"{proto}://{host}{PREFIX}/gmail/callback"


def _settings_return_url(request: Request) -> str:
    """Where to send the user after callback (success or error)."""
    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or ""
    ).split(",")[0].strip()
    proto = (
        request.headers.get("x-forwarded-proto")
        or request.url.scheme
        or "https"
    ).split(",")[0].strip()
    if proto == "http" and host and not host.startswith(("localhost", "127.0.0.1")):
        proto = "https"
    if not host or not _return_host_allowed(host):
        return f"{PREFIX}/integrations"
    return f"{proto}://{host}{PREFIX}/integrations"


# ----------------------------------------------------------------------
# Friendly error messages (matches integrations OAUTH_FRIENDLY_ERRORS)
# ----------------------------------------------------------------------

OAUTH_FRIENDLY_ERRORS = {
    "redirect_uri_mismatch": (
        "URL de retorno nao autorizada no Google Cloud Console. Suporte: support@example.com"
    ),
    "invalid_grant": "Token expirado. Tente reconectar.",
    "access_denied": "Voce cancelou a permissao. Pode tentar de novo quando quiser.",
    "no_tenant_context": "Sessao sem contexto de escritorio. Faca login novamente.",
    "credentials_missing": (
        "Credenciais OAuth do Google ainda nao configuradas neste servidor. "
        "Suporte: support@example.com"
    ),
    "oauth_start_failed": "Nao foi possivel iniciar o login Google. Tente em alguns segundos.",
    "missing_code": "Resposta do Google chegou incompleta. Tente conectar de novo.",
    "invalid_state": "Sessao OAuth expirou ou foi adulterada. Conecte novamente a partir do app.",
    "org_mismatch": "Erro de seguranca: tentativa de conectar em outro escritorio. Conecte novamente.",
    "auth_failed": "Nao foi possivel completar o login com o Google. Tente novamente.",
    "disconnect_noop": "Nada para desconectar — Gmail ja estava desligado deste escritorio.",
    "disconnect_failed": "Nao foi possivel desconectar agora. Tente em alguns segundos.",
}


def _redirect_settings(request: Request, query: str) -> RedirectResponse:
    """Bounce back to /integrations with a query flag (success or error)."""
    base = _settings_return_url(request)
    sep = "&" if "?" in base else "?"
    return RedirectResponse(url=f"{base}{sep}{query}", status_code=302)


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------

@router.get("/connect/{account_name}")
async def connect_account(
    request: Request,
    account_name: str,
    db: Session = Depends(get_db),
):
    """Start OAuth2 flow to connect Gmail."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        return _redirect_settings(request, "gmail_error=no_tenant_context")

    safe_account = _require_account_id(account_name)
    service = GmailService(db, org_id=org_id)

    redirect_uri = _gmail_redirect_uri(request)
    if not service.redirect_uri_allowed(redirect_uri):
        # Same UX as Calendar: surface the mismatch with the actual URI so
        # the admin can copy/paste it into Cloud Console.
        return _redirect_settings(request, "gmail_error=redirect_uri_mismatch")

    try:
        auth_url = service.get_auth_url(
            safe_account,
            redirect_uri,
            state_name=_encode_oauth_state(account_name, user, request, org_id=org_id),
        )
        return RedirectResponse(url=auth_url, status_code=302)
    except FileNotFoundError:
        return _redirect_settings(request, "gmail_error=credentials_missing")
    except Exception:
        logger.exception("Gmail OAuth start failed for org %s", org_id)
        return _redirect_settings(request, "gmail_error=oauth_start_failed")


@router.get("/callback")
async def oauth_callback(
    request: Request,
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
    db: Session = Depends(get_db),
):
    """Handle OAuth2 callback."""
    payload = _decode_oauth_state_payload(state) if state else None
    current_user = get_current_user(request, db)

    if error:
        return _redirect_settings(request, f"gmail_error={error}")

    if not code or not state:
        return _redirect_settings(request, "gmail_error=missing_code")

    # Tenant binding check BEFORE we trust the state's org claim.
    if not _oauth_state_user_is_valid(payload, db, current_user, request=request):
        request_org = getattr(request.state, "org_id", None)
        payload_org = (payload or {}).get("org")
        if request_org is not None and payload_org is not None and request_org != payload_org:
            return _redirect_settings(request, "gmail_error=org_mismatch")
        return _redirect_settings(request, "gmail_error=invalid_state")

    account_name = payload["account"]
    # Pin the service to the state's org_id so the token lands in the same
    # tenant that initiated the flow.
    state_org_id = payload.get("org") or getattr(request.state, "org_id", None)
    service = GmailService(db, org_id=state_org_id)
    redirect_uri = _gmail_redirect_uri(request)

    success = await run_in_threadpool(
        service.handle_oauth_callback, code, account_name, redirect_uri
    )

    if success:
        return _redirect_settings(request, "gmail_connected=1")
    return _redirect_settings(request, "gmail_error=auth_failed")


@router.post("/disconnect/{account_name}")
async def disconnect_account(
    request: Request,
    account_name: str,
    db: Session = Depends(get_db),
):
    """Disconnect a Gmail account."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        return _redirect_settings(request, "gmail_error=no_tenant_context")

    service = GmailService(db, org_id=org_id)
    safe_account = _require_account_id(account_name)
    removed = await run_in_threadpool(service.disconnect_account, safe_account)

    flag = "gmail_disconnected=1" if removed else "gmail_error=disconnect_noop"
    return _redirect_settings(request, flag)


@router.get("/status")
async def gmail_status(request: Request, db: Session = Depends(get_db)):
    """Return sanitized Gmail connection status for the current org."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = GmailService(db, org_id=getattr(request.state, "org_id", None))
    accounts = service.get_connected_accounts(verify_live=True)
    return JSONResponse({
        "connected": any(account.get("connected") for account in accounts),
        "can_send": any(account.get("can_send") for account in accounts),
        "accounts": accounts,
        "redirect_uri": _gmail_redirect_uri(request),
        "default_accounts": service.default_accounts(),
    })


@router.get("/smoke")
async def gmail_smoke(request: Request, db: Session = Depends(get_db)):
    """Lightweight smoke endpoint: list 5 most recent inbox messages.

    Used by support to confirm "yes, Gmail OAuth is actually reading mail".
    Returns empty list (not 500) when Gmail is not connected.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = GmailService(db, org_id=getattr(request.state, "org_id", None))
    account = (request.query_params.get("account") or "info").strip().lower()
    try:
        safe_account = _require_account_id(account)
    except HTTPException:
        return JSONResponse({"messages": [], "error": "invalid_account"})

    messages = await run_in_threadpool(
        service.list_recent_messages, safe_account, 5
    )
    return JSONResponse({"messages": messages, "count": len(messages)})


@router.post("/send")
async def gmail_send(request: Request, db: Session = Depends(get_db)):
    """Send an email via the org's connected Gmail account.

    Accepts JSON: {to, subject, body, cc?, reply_to_message_id?,
                   account_name?, client_id?, case_id?}
    Returns JSON: {success, message_id?, provider, error?}
    """
    from core.template_config import inject_org_context

    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"success": False, "error": "unauthenticated"}, status_code=401)

    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        return JSONResponse({"success": False, "error": "no_org_context"}, status_code=400)

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "invalid_json"}, status_code=400)

    to = (payload.get("to") or "").strip()
    subject = (payload.get("subject") or "").strip()
    body_text = (payload.get("body") or "").strip()
    cc = (payload.get("cc") or "").strip()
    reply_to_msg_id = (payload.get("reply_to_message_id") or "").strip()
    client_id = payload.get("client_id")
    case_id = payload.get("case_id")

    if not to or "@" not in to:
        return JSONResponse({"success": False, "error": "invalid_to"}, status_code=400)
    if not subject:
        return JSONResponse({"success": False, "error": "missing_subject"}, status_code=400)
    if not body_text:
        return JSONResponse({"success": False, "error": "missing_body"}, status_code=400)

    import html as _html
    body_html = (
        "<!DOCTYPE html><html><body style='font-family:Arial,sans-serif;line-height:1.6'>"
        f"<div style='white-space:pre-wrap'>{_html.escape(body_text)}</div>"
        "<hr style='margin-top:24px;border:none;border-top:1px solid #ddd'>"
        "<small style='color:#999'>Enviado via CaseHub</small>"
        "</body></html>"
    )

    svc = GmailService(db, org_id=org_id)
    accounts = svc.get_connected_accounts()
    send_accounts = [a for a in accounts if a.get("can_send")]
    if not send_accounts:
        return JSONResponse({"success": False, "error": "no_send_account"}, status_code=503)

    account_name = (payload.get("account_name") or "").strip() or send_accounts[0]["name"]
    result = await run_in_threadpool(
        svc.send_email,
        account_name,
        to,
        subject,
        body_html,
        body_text,
        cc,
        reply_to_msg_id,
    )

    if result["success"]:
        try:
            from sqlalchemy import text as _text
            db.execute(
                _text("""
                    INSERT INTO sent_emails
                        (user_id, to_email, subject, body, client_id, case_id, sent_at)
                    VALUES (:uid, :to, :sub, :body, :cid, :csid, NOW())
                """),
                {
                    "uid": user.id, "to": to, "sub": subject, "body": body_text,
                    "cid": client_id, "csid": case_id,
                },
            )
            db.commit()
        except Exception as e:
            logger.warning("Failed to log sent email to sent_emails: %s", e)

    return JSONResponse({
        "success": result["success"],
        "message_id": result.get("message_id"),
        "provider": "gmail",
        "error": result.get("error"),
    })


@router.get("/inbox", response_class=HTMLResponse)
async def gmail_inbox(request: Request, db: Session = Depends(get_db)):
    """Gmail inbox: fetches messages via API and renders the email list view."""
    from core.template_config import inject_org_context

    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(f"{PREFIX}/login")

    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        return RedirectResponse(f"{PREFIX}/login")

    svc = GmailService(db, org_id=org_id)
    accounts = svc.get_connected_accounts()
    if not accounts:
        return RedirectResponse(f"{PREFIX}/gmail/accounts")

    try:
        emails = await run_in_threadpool(
            svc.list_messages_with_metadata, accounts[0]["name"], 50
        )
    except Exception as e:
        logger.warning("gmail_inbox list_messages_with_metadata failed: %s", e)
        emails = []

    return templates.TemplateResponse(
        "app/emails/list.html",
        {
            "request": request,
            **inject_org_context(request, user),
            "emails": emails,
            "product": "lite",
            "gmail_inbox_mode": True,
            "synced_folders": [],
            "search": "",
            "folder": None,
            "show_archived": False,
            "show_autoreplies": False,
            "clients": [],
            "account_ids": [],
        },
    )


@router.get("/message/{message_id}", response_class=HTMLResponse)
async def gmail_message(message_id: str, request: Request, db: Session = Depends(get_db)):
    """Fetch and display a single Gmail message."""
    from core.template_config import inject_org_context

    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(f"{PREFIX}/login")

    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        return RedirectResponse(f"{PREFIX}/login")

    svc = GmailService(db, org_id=org_id)
    accounts = svc.get_connected_accounts()
    if not accounts:
        return RedirectResponse(f"{PREFIX}/gmail/accounts")

    email = await run_in_threadpool(
        svc.get_message, accounts[0]["name"], message_id
    )
    if not email:
        raise HTTPException(status_code=404, detail="Message not found")

    return templates.TemplateResponse(
        "app/emails/view.html",
        {
            "request": request,
            **inject_org_context(request, user),
            "email": email,
            "product": "lite",
        },
    )
