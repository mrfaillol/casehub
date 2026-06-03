"""
CaseHub - Authentication Module
"""
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Request, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import jwt

from config import settings
from models import get_db, User

logger = logging.getLogger(__name__)

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"

# Access token: 30 minutes
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Refresh token: 7 days
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Sentinela T1: hard-fail tokens missing org_id once transition window expires.
# Default 7-day grace lets in-flight tokens keep working while everything is
# re-issued. Set to "1" to enforce immediately.
REQUIRE_ORG_ID_IN_TOKEN = os.getenv("CASEHUB_REQUIRE_ORG_ID_IN_TOKEN", "0") == "1"

# Bearer token security scheme for API
bearer_scheme = HTTPBearer(auto_error=False)
_USER_CACHE_MISSING = object()


def _get_cached_request_user(request: Request):
    state = getattr(request, "state", None)
    if state is None:
        return _USER_CACHE_MISSING
    state_dict = getattr(state, "_state", None)
    if isinstance(state_dict, dict) and "user" in state_dict:
        return state_dict["user"]
    if "user" in getattr(state, "__dict__", {}):
        return state.__dict__["user"]
    return _USER_CACHE_MISSING


def _set_cached_request_user(request: Request, user: Optional[User]) -> None:
    state = getattr(request, "state", None)
    if state is not None:
        state.user = user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a long-lived refresh token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def make_token(user: User, kind: str = "access", **extra) -> str:
    """Build an access or refresh JWT for a user with org_id ALWAYS embedded.

    Sentinela T1 mitigation: every token issued by CaseHub must carry the
    issuing user's `org_id` so TenantMiddleware can fall back to it when the
    request hits the apex (casehub.legal without subdomain) and so
    `get_current_user` can enforce the (user.org_id == request.state.org_id)
    guard for non-superadmins.

    Use this helper instead of calling `create_access_token` directly, to
    keep the org_id contract centralized. The `extra` kwargs are merged into
    the payload (e.g. `user_id=...` for legacy compatibility).
    """
    if user is None:
        raise ValueError("make_token requires a User instance")
    payload = {
        "sub": user.email,
        "org_id": getattr(user, "org_id", None),
        **extra,
    }
    if kind == "refresh":
        return create_refresh_token(payload)
    return create_access_token(payload)


def _decode_token(token: str, expected_type: Optional[str] = None) -> Optional[dict]:
    """Decode and validate a JWT token. Returns payload or None."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # If caller specifies expected type, enforce it
        if expected_type and payload.get("type") != expected_type:
            return None
        return payload
    except jwt.PyJWTError:
        return None


def _enforce_tenant_binding(request: Request, user: Optional[User], payload: dict) -> Optional[User]:
    """Sentinela T1 + IDOR C5 defense-in-depth: reconcile the JWT-bound user
    with the tenant resolved by TenantMiddleware.

    Two independent guards run here (both for non-superadmins):

    1. Tenant mismatch: reject when ``user.org_id != request.state.org_id``.
       This binds identity (JWT ``sub`` -> User.org_id) to the resolved tenant
       so a session cannot operate against a tenant it does not belong to.

    2. Unscoped admin (IDOR C5 / council ruling 2026-05-29-idor-c5-xorgid-root,
       condition 4): reject when ``user.org_id IS NULL`` on a request that *did*
       resolve a concrete tenant. A tenant-less account (e.g. the legacy
       startup/migration admin) must never inherit an arbitrary resolved
       tenant's scope and become a cross-tenant view. This generalises the
       per-route pattern in routes/improvement_tasks.py:209-211 to the single
       auth chokepoint, so every route that authenticates via
       get_current_user / get_current_user_api is covered without touching the
       ~71 routes individually.

    Superadmins are exempt (they intentionally pivot across tenants via
    impersonation). Tokens missing `org_id` are logged during the grace
    window and rejected when `CASEHUB_REQUIRE_ORG_ID_IN_TOKEN=1`.
    """
    if user is None:
        return None

    token_org_id = payload.get("org_id")
    if token_org_id is None:
        if REQUIRE_ORG_ID_IN_TOKEN:
            logger.warning(
                "Token without org_id rejected (sub=%s, REQUIRE_ORG_ID_IN_TOKEN=1)",
                payload.get("sub"),
            )
            return None
        logger.warning(
            "Token without org_id accepted during grace window (sub=%s); "
            "set CASEHUB_REQUIRE_ORG_ID_IN_TOKEN=1 in prod to enforce.",
            payload.get("sub"),
        )

    request_org_id = getattr(request.state, "org_id", None) if hasattr(request, "state") else None
    user_role = (getattr(user, "role", "") or "").lower()
    user_type = (getattr(user, "user_type", "") or "").lower()
    is_superadmin = user_role == "superadmin" or user_type == "superadmin"

    if is_superadmin:
        return user

    # Guard 1 — tenant mismatch (Sentinela T1).
    if request_org_id is not None and user.org_id is not None and user.org_id != request_org_id:
        logger.warning(
            "Tenant mismatch: user=%s user.org_id=%s request.state.org_id=%s host=%s path=%s",
            user.email,
            user.org_id,
            request_org_id,
            request.headers.get("host"),
            request.url.path if hasattr(request, "url") else "?",
        )
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    # Guard 2 — unscoped admin on a resolved tenant (IDOR C5 defense-in-depth).
    # Only fires when a concrete tenant was resolved: single-tenant / setup
    # flows where no tenant context exists (request_org_id is None) are left
    # untouched, preserving bootstrap of a fresh install.
    if request_org_id is not None and user.org_id is None:
        logger.warning(
            "Unscoped account on resolved tenant rejected (IDOR C5): user=%s "
            "request.state.org_id=%s host=%s path=%s",
            user.email,
            request_org_id,
            request.headers.get("host"),
            request.url.path if hasattr(request, "url") else "?",
        )
        raise HTTPException(
            status_code=403,
            detail="Account is not scoped to an organization",
        )

    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    cached_user = _get_cached_request_user(request)
    if cached_user is not _USER_CACHE_MISSING:
        return cached_user

    # Use casehub_token to avoid WordPress cookie conflicts
    token = request.cookies.get("casehub_token")
    if not token:
        _set_cached_request_user(request, None)
        return None
    payload = _decode_token(token)
    if not payload:
        _set_cached_request_user(request, None)
        return None
    email = payload.get("sub")
    if not email:
        _set_cached_request_user(request, None)
        return None
    user = db.query(User).filter(User.email == email).first()
    user = _enforce_tenant_binding(request, user, payload)
    _set_cached_request_user(request, user)
    return user

def get_current_user_api(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Get current user from API request.
    Supports both Bearer token (Authorization header) and cookie authentication.
    """
    cached_user = _get_cached_request_user(request)
    if cached_user is not _USER_CACHE_MISSING:
        return cached_user

    token = None

    # Try Bearer token first
    if credentials:
        token = credentials.credentials
    else:
        # Fallback to cookie
        token = request.cookies.get("casehub_token")

    if not token:
        _set_cached_request_user(request, None)
        return None

    payload = _decode_token(token)
    if not payload:
        _set_cached_request_user(request, None)
        return None
    email = payload.get("sub")
    if not email:
        _set_cached_request_user(request, None)
        return None
    user = db.query(User).filter(User.email == email).first()
    user = _enforce_tenant_binding(request, user, payload)
    _set_cached_request_user(request, user)
    return user

def require_auth_api(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Require authentication for API endpoints.
    Raises HTTPException if not authenticated.
    """
    user = get_current_user_api(request, credentials, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return user


def validate_refresh_token(token: str, db: Session) -> Optional[User]:
    """Validate a refresh token and return the user, or None."""
    payload = _decode_token(token, expected_type="refresh")
    if not payload:
        return None
    email = payload.get("sub")
    if not email:
        return None
    user = db.query(User).filter(User.email == email).first()
    if user and not user.enabled:
        return None
    return user
