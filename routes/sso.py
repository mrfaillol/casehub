"""
CaseHub - SSO Routes
Single Sign-On with Google and Microsoft OAuth2.
"""
import json
import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, User
from auth import get_current_user, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from models.tenant import tenant_query
from middleware.features import require_feature
from services.sso_service import sso_service, CREATE_SSO_TABLE, SSOProvider
from config import settings

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/sso", tags=["sso"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py


def _build_request_base(request: Request) -> str:
    """Build base URL (scheme://host[:port]) from the incoming request.

    Preserves the subdomain so OAuth redirect_uri matches the tenant the user
    started from (e.g. ``cliente.example.com``). Falls back to
    ``request.url.hostname`` when the proxy header is missing.

    ``X-Forwarded-Host`` / ``X-Forwarded-Proto`` are trusted because the
    Mumbai nginx config (deploy/nginx-casehub.conf) sets both unconditionally
    on every upstream proxy_pass block. The app is not reachable without that
    proxy in production.
    """
    forwarded_proto = request.headers.get("x-forwarded-proto")
    scheme = (forwarded_proto.split(",")[0].strip()
              if forwarded_proto else request.url.scheme)

    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        # X-Forwarded-Host may be a comma-separated list; take the first hop.
        host_header = forwarded_host.split(",")[0].strip()
        # When the proxy provides the public host we ignore request.url.port
        # (that's the upstream container port, not the public-facing one).
        upstream_port: Optional[int] = None
    else:
        host_header = request.headers.get("host") or request.url.hostname or ""
        upstream_port = request.url.port

    # Strip any port already embedded in the host header so we don't duplicate.
    if ":" in host_header:
        host, _, embedded_port = host_header.partition(":")
        try:
            port: Optional[int] = int(embedded_port)
        except ValueError:
            port = upstream_port
    else:
        host = host_header
        port = upstream_port

    base = f"{scheme}://{host}"
    if port and port not in (80, 443):
        base += f":{port}"
    return base


def ensure_tables(db: Session):
    """Ensure SSO tables exist."""
    try:
        db.execute(text(CREATE_SSO_TABLE))
        db.commit()
    except Exception as e:
        db.rollback()


@router.get("", response_class=HTMLResponse)
async def sso_settings(
    request: Request,
    db: Session = Depends(get_db),
    _feature=Depends(require_feature("sso")),
):
    """SSO settings page - manage connected accounts."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    # Get user's SSO connections
    try:
        result = db.execute(text("""
            SELECT * FROM sso_connections WHERE user_id = :uid
        """), {"uid": user.id})
        connections = result.fetchall()
    except Exception as e:
        logger.error("Failed to fetch SSO connections: %s", e)
        connections = []

    providers = sso_service.get_available_providers()

    return templates.TemplateResponse("app/sso/settings.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "providers": providers,
        "connections": connections
    })


@router.get("/login/{provider}")
async def sso_login(
    request: Request,
    provider: str,
    next: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Initiate SSO login flow."""
    ensure_tables(db)

    # Validate provider
    if provider not in [p.value for p in SSOProvider]:
        raise HTTPException(status_code=400, detail="Invalid provider")

    # Generate state
    state = sso_service.generate_state()

    # Build redirect URI from the live request so the subdomain is preserved
    # (cliente.example.com stays on cliente-alpha instead of falling
    # back to the apex BASE_URL, which would resolve to the default org).
    base = _build_request_base(request)
    redirect_uri = f"{base}{PREFIX}/sso/callback/{provider}"

    # Capture tenant context resolved by TenantMiddleware so the callback can
    # validate that we land on the same org we left from.
    org_id = getattr(request.state, "org_id", None)

    # Get authorization URL
    auth_url = sso_service.get_authorization_url(provider, redirect_uri, state)

    if not auth_url:
        raise HTTPException(status_code=400, detail="Provider not configured")

    # Store state (carries org_id so callback validates tenant integrity).
    try:
        db.execute(text("""
            INSERT INTO sso_states (state, provider, redirect_url, org_id)
            VALUES (:state, :provider, :redirect, :org_id)
        """), {
            "state": state,
            "provider": provider,
            "redirect": next or f"{PREFIX}/",
            "org_id": org_id,
        })
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/callback/{provider}")
async def sso_callback(
    request: Request,
    provider: str,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Handle OAuth2 callback."""
    ensure_tables(db)

    if error:
        return RedirectResponse(url=f"{PREFIX}/login?error={error}", status_code=302)

    if not code or not state:
        return RedirectResponse(url=f"{PREFIX}/login?error=missing_params", status_code=302)

    # Verify state
    try:
        result = db.execute(text("""
            SELECT * FROM sso_states
            WHERE state = :state AND provider = :provider AND expires_at > NOW()
        """), {"state": state, "provider": provider})
        state_row = result.fetchone()

        if not state_row:
            return RedirectResponse(url=f"{PREFIX}/login?error=invalid_state", status_code=302)

        redirect_url = state_row.redirect_url or f"{PREFIX}/"

        # Tenant integrity check: the org we left from (login) must match the
        # org the callback resolved to (subdomain). A mismatch usually means
        # the user got redirected to apex mid-flow (BASE_URL leak) and would
        # silently log into the wrong tenant. NULL on either side is treated
        # as legacy/pre-migration and skipped for backward compat.
        state_org_id = getattr(state_row, "org_id", None)
        current_org_id = getattr(request.state, "org_id", None)
        if (state_org_id is not None and current_org_id is not None
                and state_org_id != current_org_id):
            logger.warning(
                "SSO state org_id mismatch: state=%s request=%s provider=%s",
                state_org_id, current_org_id, provider,
            )
            db.execute(text("DELETE FROM sso_states WHERE state = :state"),
                       {"state": state})
            db.commit()
            return RedirectResponse(
                url=f"{PREFIX}/login?error=tenant_mismatch",
                status_code=302,
            )

        # Delete used state
        db.execute(text("DELETE FROM sso_states WHERE state = :state"), {"state": state})
        db.commit()

    except Exception as e:
        return RedirectResponse(url=f"{PREFIX}/login?error=state_error", status_code=302)

    # Exchange code for token
    config = sso_service.get_provider_config(provider)
    client_id, client_secret = sso_service.get_client_credentials(provider)
    # redirect_uri sent to the token endpoint must byte-match the one used at
    # /sso/login (same subdomain, same scheme, same port). Derive it from the
    # live request again rather than settings.BASE_URL.
    base = _build_request_base(request)
    redirect_uri = f"{base}{PREFIX}/sso/callback/{provider}"

    try:
        async with httpx.AsyncClient() as client:
            # Get tokens
            token_response = await client.post(
                config["token_url"],
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

            if token_response.status_code != 200:
                return RedirectResponse(url=f"{PREFIX}/login?error=token_error", status_code=302)

            tokens = token_response.json()
            access_token = tokens.get("access_token")
            refresh_token = tokens.get("refresh_token")
            expires_in = tokens.get("expires_in", 3600)

            # Get user info
            headers = {"Authorization": f"Bearer {access_token}"}
            userinfo_response = await client.get(config["userinfo_url"], headers=headers)

            if userinfo_response.status_code != 200:
                return RedirectResponse(url=f"{PREFIX}/login?error=userinfo_error", status_code=302)

            user_data = userinfo_response.json()

    except Exception as e:
        return RedirectResponse(url=f"{PREFIX}/login?error=oauth_error", status_code=302)

    # Map user info
    user_info = sso_service.map_user_info(provider, user_data)

    # Check if SSO connection exists
    try:
        result = db.execute(text("""
            SELECT sc.*, u.id as user_id, u.email as user_email
            FROM sso_connections sc
            JOIN users u ON sc.user_id = u.id
            WHERE sc.provider = :provider AND sc.provider_user_id = :pid
        """), {"provider": provider, "pid": user_info["provider_id"]})
        existing = result.fetchone()

        if existing:
            # Update tokens and login
            db.execute(text("""
                UPDATE sso_connections
                SET access_token = :token, refresh_token = :refresh,
                    token_expires_at = :expires, last_login_at = NOW()
                WHERE id = :id
            """), {
                "token": access_token,
                "refresh": refresh_token,
                "expires": datetime.now() + timedelta(seconds=expires_in),
                "id": existing.id
            })
            db.commit()

            # Get user and create session
            user = tenant_query(db, User, request.state.org_id).filter(User.id == existing.user_id).first()
            if user:
                response = RedirectResponse(url=redirect_url, status_code=302)
                token = create_access_token(data={"sub": user.email}); response.set_cookie(key="casehub_token", value=token, httponly=True, max_age=ACCESS_TOKEN_EXPIRE_MINUTES*60, path="/", samesite="lax")
                return response

        else:
            # Check if user with this email exists
            result = db.execute(text("SELECT * FROM users WHERE email = :email"),
                               {"email": user_info["email"]})
            existing_user = result.fetchone()

            if existing_user:
                # Link to existing user
                db.execute(text("""
                    INSERT INTO sso_connections
                    (user_id, provider, provider_user_id, email, access_token, refresh_token, token_expires_at, profile_data, last_login_at)
                    VALUES (:uid, :provider, :pid, :email, :token, :refresh, :expires, :profile, NOW())
                """), {
                    "uid": existing_user.id,
                    "provider": provider,
                    "pid": user_info["provider_id"],
                    "email": user_info["email"],
                    "token": access_token,
                    "refresh": refresh_token,
                    "expires": datetime.now() + timedelta(seconds=expires_in),
                    "profile": json.dumps(user_info)
                })
                db.commit()

                user = tenant_query(db, User, request.state.org_id).filter(User.id == existing_user.id).first()
                if user:
                    response = RedirectResponse(url=redirect_url, status_code=302)
                    token = create_access_token(data={"sub": user.email}); response.set_cookie(key="casehub_token", value=token, httponly=True, max_age=ACCESS_TOKEN_EXPIRE_MINUTES*60, path="/", samesite="lax")
                    return response

            else:
                # No user found - redirect to login with error
                return RedirectResponse(
                    url=f"{PREFIX}/login?error=no_account&email={user_info['email']}",
                    status_code=302
                )

    except Exception as e:
        db.rollback()
        return RedirectResponse(url=f"{PREFIX}/login?error=db_error", status_code=302)

    return RedirectResponse(url=f"{PREFIX}/login", status_code=302)


@router.post("/connect/{provider}")
async def connect_provider(
    request: Request,
    provider: str,
    db: Session = Depends(get_db)
):
    """Connect an SSO provider to existing account."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Redirect to SSO login with return to settings
    return RedirectResponse(
        url=f"{PREFIX}/sso/login/{provider}?next={PREFIX}/sso",
        status_code=302
    )


@router.post("/disconnect/{connection_id}")
async def disconnect_provider(
    request: Request,
    connection_id: int,
    db: Session = Depends(get_db)
):
    """Disconnect an SSO provider from account."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        # Verify connection belongs to user
        db.execute(text("""
            DELETE FROM sso_connections
            WHERE id = :id AND user_id = :uid
        """), {"id": connection_id, "uid": user.id})
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/sso", status_code=302)


# === API Endpoints ===

@router.get("/api/providers", response_class=JSONResponse)
async def get_providers(request: Request):
    """API: Get available SSO providers."""
    providers = sso_service.get_available_providers()
    return JSONResponse(content=[
        {"id": p["id"].value, "name": p["name"], "icon": p["icon"], "color": p["color"]}
        for p in providers
    ])
