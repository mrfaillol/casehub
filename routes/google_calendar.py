"""
CaseHub - Google Calendar Integration Routes
Connect and sync with Google Calendar accounts
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from models import User, get_db
from auth import get_current_user
from i18n import get_translations
from services.google_calendar import GoogleCalendarService
from core.template_config import templates, PREFIX
from config import settings

router = APIRouter(prefix="/google-calendar", tags=["google-calendar"])


ACCOUNT_SLUGS = {
    "principal": "info",
    "compartilhada": "center",
    "info": "info",
    "center": "center",
}

ACCOUNT_LABELS = {
    "info": "Agenda principal",
    "center": "Agenda auxiliar",
}

OAUTH_STATE_MAX_AGE_SECONDS = 10 * 60

LEGACY_CALENDAR_REPLACEMENTS = (
    (re.compile(r"Immigrant Law Center", re.IGNORECASE), "Escritorio"),
    (re.compile(r"Immigrant Law", re.IGNORECASE), "Escritorio"),
    (re.compile(r"immigrant\.law", re.IGNORECASE), "agenda do escritorio"),
    (re.compile(r"\binfo@[^\s,;<>\"']+", re.IGNORECASE), "agenda-principal@escritorio"),
    (re.compile(r"\bcenter@[^\s,;<>\"']+", re.IGNORECASE), "agenda-auxiliar@escritorio"),
    (re.compile(r"\[INFO\]", re.IGNORECASE), "[Agenda principal]"),
    (re.compile(r"\[CENTER\]", re.IGNORECASE), "[Agenda auxiliar]"),
)


# Sentinela T6: path traversal mitigation. The legacy fallback returned the
# raw user-supplied value when it wasn't in ACCOUNT_SLUGS, which let a
# request like POST /casehub/google-calendar/disconnect/..%2F..%2Fetc%2Fpasswd
# escape the credentials directory once it reached
# services/google_calendar.get_token_file. We now require the resolved value
# to match a safe identifier regex; everything else is replaced with an empty
# string so callers that build filesystem paths can refuse it cheaply, and
# routes that need a hard-fail call _require_account_id() below.
_SAFE_ACCOUNT_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _account_id(value: str) -> str:
    candidate = (value or "").strip().lower()
    mapped = ACCOUNT_SLUGS.get(candidate)
    if mapped is not None:
        return mapped
    # Unknown account: reject path-traversal-ish values eagerly.
    if _SAFE_ACCOUNT_ID.match(candidate):
        return candidate
    return ""


def _require_account_id(value: str) -> str:
    """Sentinela T6: raise HTTP 400 when account name fails the safe regex.

    Use this in any route that turns the account name into a filesystem path.
    """
    resolved = _account_id(value)
    if not resolved or not _SAFE_ACCOUNT_ID.match(resolved):
        raise HTTPException(status_code=400, detail="invalid account name")
    return resolved


def _account_label(value: str) -> str:
    return ACCOUNT_LABELS.get(_account_id(value), "Agenda Google")


def _calendar_account_context(account: dict) -> dict:
    slug = _account_id(account.get("name", ""))
    display_email = account.get("connected_email") or account.get("email") or "Conta Google do escritorio"
    return {
        **account,
        "slug": slug,
        "label": _account_label(slug),
        "display_email": display_email,
    }


def _sanitize_calendar_text(value: str) -> str:
    sanitized = str(value or "")
    for pattern, replacement in LEGACY_CALENDAR_REPLACEMENTS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


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


def _request_origin(request: Request) -> str:
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "https").split(",")[0].strip()
    if proto == "http" and host and not host.startswith(("localhost", "127.0.0.1")):
        proto = "https"
    return f"{proto}://{host}" if host else str(request.base_url).rstrip("/")


def _configured_origin() -> str:
    configured = (settings.BASE_URL or "").strip().rstrip("/")
    return configured


def _return_host_allowed(host: str) -> bool:
    host = (host or "").split(":")[0].lower()
    if not host:
        return False
    if host in {"localhost", "127.0.0.1"}:
        return True
    configured_host = urlparse(_configured_origin()).hostname or ""
    configured_host = configured_host.lower()
    if not configured_host:
        return True
    return host == configured_host or host.endswith("." + configured_host)


def _oauth_return_to(request: Request) -> str:
    origin = _request_origin(request)
    parsed = urlparse(origin)
    if not _return_host_allowed(parsed.netloc):
        origin = _configured_origin() or origin
    return f"{origin}{PREFIX}/google-calendar/settings"


def _oauth_settings_redirect(payload: Optional[dict], query: str) -> str:
    fallback = f"{PREFIX}/google-calendar/settings?{query}"
    if not payload:
        return fallback
    return_to = str(payload.get("return_to") or "").strip()
    parsed = urlparse(return_to)
    if parsed.scheme not in {"http", "https"} or not _return_host_allowed(parsed.netloc):
        return fallback
    separator = "&" if parsed.query else "?"
    return f"{return_to}{separator}{query}"


def _encode_oauth_state(account_name: str, user, request: Request, org_id: Optional[int] = None) -> str:
    """Encode signed OAuth state with org_id binding.

    The `org` claim binds the OAuth round-trip to a specific tenant so that
    a callback hitting another subdomain (or a stale state replay across
    tenants) fails the org_mismatch check in `_oauth_state_user_is_valid`.
    """
    payload = {
        "account": _account_id(account_name),
        "uid": getattr(user, "id", None),
        "sub": getattr(user, "email", ""),
        "org": org_id if org_id is not None else getattr(request.state, "org_id", None),
        "return_to": _oauth_return_to(request),
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

    if user is not None:
        if payload.get("uid") != getattr(user, "id", None):
            return None
        if payload.get("sub") != getattr(user, "email", ""):
            return None

    account = _account_id(payload.get("account") or "")
    if account not in ACCOUNT_LABELS:
        return None
    payload["account"] = account
    return payload


def _decode_oauth_state(state: str, user=None) -> Optional[str]:
    payload = _decode_oauth_state_payload(state, user)
    return payload.get("account") if payload else None


def _oauth_state_user_is_valid(
    payload: Optional[dict],
    db: Session,
    current_user=None,
    request: Optional[Request] = None,
) -> bool:
    """Validate signed state payload against current user + tenant.

    Rejects state where the encoded `org` claim differs from the live
    request's `request.state.org_id` (set by TenantMiddleware). Prevents
    a token issued during one tenant's flow from being persisted under
    another tenant's directory if a callback is replayed across subdomains.
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
        # Both must be present for the binding to be meaningful. Reject mismatch.
        if request_org is not None and payload_org is not None and request_org != payload_org:
            return False

    return db.query(User).filter(
        User.id == uid,
        User.email == email,
        User.enabled.is_(True),
    ).first() is not None


def _public_redirect_uri(request: Request) -> str:
    """Build the public OAuth callback URL behind Nginx/proxy.

    Always derives from the request (preserves tenant subdomain for
    multi-tenant OAuth callbacks). Kept as a thin alias of
    `_calendar_redirect_uri` for backwards-compat with external callers.
    """
    return _calendar_redirect_uri(request)


def get_context(request: Request, db: Session, **kwargs):
    """Build template context."""
    lang = request.cookies.get("lang", "en")
    user = get_current_user(request, db)
    return {
        "request": request,
        "PREFIX": PREFIX,
        "lang": lang,
        "t": get_translations(lang),
        "user": user,
        **kwargs
    }


def _settings_payload(request: Request, db: Session, service: GoogleCalendarService, **kwargs) -> dict:
    redirect_uri = _calendar_redirect_uri(request)
    if getattr(service, "setup_error", "") and "error" not in kwargs:
        kwargs["error"] = service.setup_error
    return {
        **get_context(request, db),
        "accounts": [_calendar_account_context(account) for account in service.get_connected_accounts(verify_live=True)],
        "redirect_uri": redirect_uri,
        "authorized_redirect_uris": service.get_client_redirect_uris(),
        "sync_options": {
            "default_accounts": service.default_accounts(),
            "send_updates": service.send_updates(),
            "create_meet": service.create_meet_enabled(),
            "event_detail_mode": service.event_detail_mode(),
        },
        **kwargs,
    }


def _calendar_redirect_uri(request: Request) -> str:
    """Derive OAuth redirect_uri from the current request, never from BASE_URL.

    Using `settings.BASE_URL` blindly breaks multi-subdomain tenancy:
    `cliente.example.com` would callback into the apex host and lose
    the tenant subdomain (TenantMiddleware uses subdomain to resolve org_id).

    We always honor the request's effective scheme/host/port (with proxy
    headers `x-forwarded-{host,proto}` taking precedence over the raw URL).
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

    # Promote http→https for non-local hosts (proxy may terminate TLS).
    if proto == "http" and host and not host.startswith(("localhost", "127.0.0.1")):
        proto = "https"

    if not host:
        # Last-ditch fallback only when request has no host at all.
        host = (settings.BASE_URL or "").strip().rstrip("/")
        return f"{host}{PREFIX}/google-calendar/callback"

    return f"{proto}://{host}{PREFIX}/google-calendar/callback"


@router.get("/settings", response_class=HTMLResponse)
async def calendar_settings(request: Request, db: Session = Depends(get_db)):
    """Google Calendar settings page"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    service = GoogleCalendarService(db, org_id=getattr(request.state, "org_id", None))
    oauth_setup_issue = None
    redirect_uri = _calendar_redirect_uri(request)
    if request.query_params.get("error") == "redirect_uri_mismatch":
        oauth_setup_issue = {
            "code": "redirect_uri_mismatch",
            "redirect_uri": redirect_uri,
            "message": "O endereco de retorno deste ambiente nao esta autorizado no OAuth do Google.",
        }

    return templates.TemplateResponse(
        "calendar/google_settings.html",
        _settings_payload(request, db, service, oauth_setup_issue=oauth_setup_issue),
    )


@router.get("/connect/{account_name}")
async def connect_account(
    request: Request,
    account_name: str,
    db: Session = Depends(get_db)
):
    """Start OAuth2 flow to connect Google Calendar"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    org_id = getattr(request.state, "org_id", None)
    # Sentinela T6: refuse invalid account names up front. The downstream
    # GoogleCalendarService.get_auth_url eventually writes to a token file
    # whose name is derived from this value, so any traversal must die here.
    safe_account = _require_account_id(account_name)
    service = GoogleCalendarService(db, org_id=org_id)

    redirect_uri = _calendar_redirect_uri(request)
    if not service.redirect_uri_allowed(redirect_uri):
        return templates.TemplateResponse(
            "calendar/google_settings.html",
            _settings_payload(
                request,
                db,
                service,
                oauth_setup_issue={
                    "code": "redirect_uri_mismatch",
                    "redirect_uri": redirect_uri,
                    "message": "O OAuth Client do Google nao lista este endereco de retorno. Corrija no Google Cloud antes de tentar entrar.",
                },
            ),
            status_code=200,
        )

    try:
        auth_url = service.get_auth_url(
            safe_account,
            redirect_uri,
            state_name=_encode_oauth_state(account_name, user, request, org_id=org_id),
        )
        return RedirectResponse(url=auth_url)
    except FileNotFoundError as e:
        return templates.TemplateResponse(
            "calendar/google_settings.html",
            _settings_payload(request, db, service, error=str(e)),
        )


@router.get("/callback")
async def oauth_callback(
    request: Request,
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
    db: Session = Depends(get_db)
):
    """Handle OAuth2 callback"""
    payload = _decode_oauth_state_payload(state) if state else None
    current_user = get_current_user(request, db)

    if error:
        return RedirectResponse(
            url=_oauth_settings_redirect(payload, f"error={error}"),
            status_code=302
        )

    if not code or not state:
        return RedirectResponse(
            url=f"{PREFIX}/google-calendar/settings?error=missing_params",
            status_code=302
        )

    # Validate the request-tenant binding BEFORE we trust the state's org claim.
    # If the live request lands on a different subdomain than the state was
    # issued for, refuse — otherwise we would persist a token under the wrong
    # org's credentials directory.
    if not _oauth_state_user_is_valid(payload, db, current_user, request=request):
        request_org = getattr(request.state, "org_id", None)
        payload_org = (payload or {}).get("org")
        if request_org is not None and payload_org is not None and request_org != payload_org:
            return RedirectResponse(
                url=f"{PREFIX}/google-calendar/settings?error=org_mismatch",
                status_code=302
            )
        return RedirectResponse(
            url=f"{PREFIX}/google-calendar/settings?error=invalid_state",
            status_code=302
        )

    account_name = payload["account"]
    # Instantiate the service against the state's org_id so the token lands
    # in `credentials/org_{state.org}/` — the same tenant that initiated the
    # flow. Cross-checked above via _oauth_state_user_is_valid.
    state_org_id = payload.get("org") or getattr(request.state, "org_id", None)
    service = GoogleCalendarService(db, org_id=state_org_id)
    redirect_uri = _calendar_redirect_uri(request)

    success = service.handle_oauth_callback(code, account_name, redirect_uri)

    if success:
        return RedirectResponse(
            url=_oauth_settings_redirect(payload, "success=1"),
            status_code=302
        )
    else:
        return RedirectResponse(
            url=_oauth_settings_redirect(payload, "error=auth_failed"),
            status_code=302
        )


@router.post("/disconnect/{account_name}")
async def disconnect_account(
    request: Request,
    account_name: str,
    db: Session = Depends(get_db)
):
    """Disconnect a Google Calendar account"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = GoogleCalendarService(db, org_id=getattr(request.state, "org_id", None))
    # Sentinela T6: hard-fail bad account names before they hit the
    # services layer (which builds filesystem paths from this value).
    safe_account = _require_account_id(account_name)
    await run_in_threadpool(service.disconnect_account, safe_account)

    return RedirectResponse(
        url=f"{PREFIX}/google-calendar/settings",
        status_code=302
    )


@router.get("/events")
async def get_google_events(
    request: Request,
    start: Optional[str] = None,
    end: Optional[str] = None,
    accounts: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get events from connected Google Calendar accounts.

    B2 (26/05): retorna lista vazia (200) quando Google não está conectado
    OU quando qualquer fetch falha — assim FullCalendar não joga HTTP 500
    no usuário só por causa de uma integração opcional. [parceiro] reportou
    HTTP 500 ao usar a agenda sem Google ([00:51:20] reunião 25/05).
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        service = GoogleCalendarService(db, org_id=getattr(request.state, "org_id", None))

        # Parse date range
        time_min = datetime.fromisoformat(start.replace('Z', '')) if start else datetime.utcnow() - timedelta(days=30)
        time_max = datetime.fromisoformat(end.replace('Z', '')) if end else datetime.utcnow() + timedelta(days=60)

        # Get account list
        if accounts:
            account_list = [_account_id(account) for account in accounts.split(',') if account.strip()]
        else:
            # Default to all connected accounts
            account_list = ['info', 'center']

        # Short-circuit: nenhum account com credenciais válidas → agenda standalone.
        connected = [a for a in account_list if service.has_credentials(a)]
        if not connected:
            return JSONResponse([])

        # Get events from all accounts
        events = service.get_all_events(connected, time_min, time_max)
    except Exception as exc:  # noqa: BLE001 — agenda nunca pode 500 por falha do Google
        import logging
        logging.getLogger(__name__).warning(
            "Google Calendar events fetch falhou; retornando lista vazia: %s", exc
        )
        return JSONResponse([])

    # Format for FullCalendar
    formatted_events = []
    for event in events:
        source_label = _account_label(event['source'])
        # Color based on source account
        if event['source'] == 'info':
            color = '#4285f4'  # Google blue
        elif event['source'] == 'center':
            color = '#34a853'  # Google green
        else:
            color = '#9e9e9e'

        formatted_events.append({
            "id": f"gcal_{event['source']}_{event['id']}",
            "title": f"[{source_label}] {_sanitize_calendar_text(event['title'])}",
            "start": event['start'],
            "end": event['end'],
            "allDay": event['allDay'],
            "color": color,
            "url": event['htmlLink'],
            "extendedProps": {
                "type": "google",
                "source": event['source'],
                "sourceLabel": source_label,
                "description": _sanitize_calendar_text(event['description']),
                "location": _sanitize_calendar_text(event['location'])
            }
        })

    return JSONResponse(formatted_events)


@router.get("/calendars/{account_name}")
async def get_calendars(
    request: Request,
    account_name: str,
    db: Session = Depends(get_db)
):
    """Get list of calendars for an account"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = GoogleCalendarService(db, org_id=getattr(request.state, "org_id", None))

    # Sentinela T6: hard-fail bad account names; same surface as disconnect.
    safe_account = _require_account_id(account_name)
    if not service.has_credentials(safe_account):
        return JSONResponse({"error": "Account not connected"}, status_code=400)

    calendars = service.get_calendars(safe_account)
    return JSONResponse(calendars)


@router.get("/status")
async def google_calendar_status(request: Request, db: Session = Depends(get_db)):
    """Return sanitized Google Calendar connection status for the current org."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = GoogleCalendarService(db, org_id=getattr(request.state, "org_id", None))
    accounts = [_calendar_account_context(account) for account in service.get_connected_accounts(verify_live=True)]
    return JSONResponse({
        "connected": any(account.get("connected") for account in accounts),
        "write_ready": any(account.get("can_write") for account in accounts),
        "accounts": accounts,
        "redirect_uri": _calendar_redirect_uri(request),
        "sync_options": {
            "default_accounts": service.default_accounts(),
            "send_updates": service.send_updates(),
            "create_meet": service.create_meet_enabled(),
        },
    })
