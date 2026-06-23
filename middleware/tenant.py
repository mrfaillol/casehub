"""
CaseHub - Tenant Middleware
Resolves the current organization (tenant) from the incoming request.

Resolution order (post-Sentinela T1 fix, 2026-05-27):
1. Subdomain / domain (Host header) — SUBDOMAIN IS AUTHORITATIVE.
2. JWT cookie org_id (user's home org) — fallback when apex (no subdomain).
3. Default organization fallback (single-tenant mode).

The legacy `X-Org-Id` header strategy was REMOVED because any authenticated
cookie holder could spoof it to read another tenant's data. It is now only
honored when the request originates from an internal IP listed in the optional
CASEHUB_INTERNAL_IPS env var (server-to-server / cron probes). Default behavior
is to strip X-Org-Id at nginx (proxy_set_header X-Org-Id ""). See Sentinela
audit `security-audit-multitenant-2026-05-27.md`, threats T1/T10.

Usage:
    app.add_middleware(TenantMiddleware)

    # In route handlers:
    from middleware.tenant import get_current_org
    org = get_current_org(request)
"""
import logging
import os
import time
from contextvars import ContextVar
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from models.base import SessionLocal

logger = logging.getLogger(__name__)

# Context variable to hold current organization for the request lifecycle
_current_org: ContextVar[Optional[dict]] = ContextVar("current_org", default=None)


class TenantMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware that resolves the tenant (organization) for each request
    and stores it in a context variable accessible throughout the request.
    """

    # Paths that don't require tenant resolution
    EXEMPT_PATHS = {
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/static",
        "/favicon.ico",
        "/signup",
        "/setup",
        "/superadmin",
        # Public legal pages — must be accessible without org context for Google OAuth verification
        "/casehub/privacy",
        "/casehub/terms",
        # Apex-level public legal pages (#786 / T13) — Google probes the bare
        # /privacy and /terms (and pt-BR/policy aliases) and expects 200-direct.
        "/privacy",
        "/terms",
        "/termos",
        "/privacy-policy",
        "/politica-de-privacidade",
    }

    CACHE_TTL = 300  # 5 minutes

    def __init__(self, app, default_org_slug: str = "default"):
        super().__init__(app)
        self.default_org_slug = default_org_slug
        self._org_cache: dict[str, dict] = {}  # domain -> org dict
        self._org_cache_ts: dict[str, float] = {}  # domain -> timestamp
        # Optional allowlist for internal IPs that may still send X-Org-Id
        # (e.g. localhost cron, sidecar probes). Comma-separated env var.
        raw_allow = os.getenv("CASEHUB_INTERNAL_IPS", "")
        self._internal_ips = {ip.strip() for ip in raw_allow.split(",") if ip.strip()}

    # Public, host-agnostic endpoints that resolve their own tenant from a
    # validated record instead of the request Host/cookie. Google's
    # events.watch push (POST /<prefix>/calendar/gcal-webhook) is untrusted
    # inbound and never carries our subdomain or auth cookie, so it must NOT be
    # rejected by org resolution. The webhook handler looks up the owning org
    # from the (token-validated) channel row — see routes/calendar.py.
    # Exact full paths (não suffix/endswith — evita over-match tipo
    # /evil/calendar/gcal-webhook burlar a resolução de tenant). Sentinela.
    EXEMPT_PATHS_EXACT = (
        "/casehub/calendar/gcal-webhook",
        "/calendar/gcal-webhook",
    )

    async def dispatch(self, request: Request, call_next):
        # Skip tenant resolution for exempt paths
        path = request.url.path
        if any(path.startswith(p) for p in self.EXEMPT_PATHS):
            return await call_next(request)
        if path in self.EXEMPT_PATHS_EXACT:
            return await call_next(request)

        org = await self._resolve_org(request)

        if org is None:
            return JSONResponse(
                status_code=404,
                content={"detail": "Organization not found for this domain."},
            )

        if not org.get("is_active", False):
            return JSONResponse(
                status_code=403,
                content={"detail": "Organization is inactive."},
            )

        # Store org in context variable and request state
        _current_org.set(org)
        request.state.org = org
        request.state.org_id = org["id"]

        response = await call_next(request)
        return response

    async def _resolve_org(self, request: Request) -> Optional[dict]:
        """Resolve organization from request using multiple strategies.

        Ordem (Sentinela T1 fix, 27/05/2026):
        1. Subdomain (host header) — AUTHORITATIVE for tenant identity.
           tenanta.casehub.legal SEMPRE resolve pra org tenanta.
        2. JWT cookie org_id (user's home org) — fallback quando apex
           (casehub.legal sem subdomain) ou subdomain não resolve.
        3. Default org slug (single-tenant mode).

        Legacy Strategy 1 (X-Org-Id header from arbitrary clients) was REMOVED
        because any authenticated cookie holder could spoof it. X-Org-Id is now
        only honored when the requester's peer IP is in CASEHUB_INTERNAL_IPS
        (server-to-server). nginx must strip X-Org-Id on inbound requests as
        defense-in-depth (see deploy/nginx-casehub.conf).

        Refs:
        - Sentinela audit `security-audit-multitenant-2026-05-27.md` T1.
        - F25 — chip header mostrava DEFAULT em vez de Escritorio Demo após login.
        """

        # Strategy 0 (constrained): X-Org-Id ONLY from internal IPs.
        # Default behavior keeps this disabled (set CASEHUB_INTERNAL_IPS to enable).
        if self._internal_ips:
            org_id_header = request.headers.get("X-Org-Id")
            if org_id_header:
                peer_ip = request.client.host if request.client else ""
                if peer_ip in self._internal_ips:
                    try:
                        return self._get_org_by_id(int(org_id_header))
                    except (TypeError, ValueError):
                        logger.warning(
                            "Internal X-Org-Id from %s had invalid value", peer_ip
                        )
                else:
                    logger.warning(
                        "Rejected X-Org-Id from non-internal peer %s (header value=%s)",
                        peer_ip,
                        org_id_header,
                    )

        # Strategy 1: Domain-based resolution (subdomain authoritative)
        host = request.headers.get("host", "").split(":")[0]  # Strip port

        # Check cache first (with TTL)
        if host in self._org_cache:
            cache_age = time.time() - self._org_cache_ts.get(host, 0)
            if cache_age < self.CACHE_TTL:
                return self._org_cache[host]
            else:
                del self._org_cache[host]
                self._org_cache_ts.pop(host, None)

        # Strategy 1a: Exact domain match
        org = self._get_org_by_domain(host)
        if org:
            self._org_cache[host] = org
            self._org_cache_ts[host] = time.time()
            return org

        # Strategy 1b: Subdomain extraction (e.g., tenanta.casehub.legal)
        parts = host.split(".")
        if len(parts) >= 3:
            slug = parts[0]
            # Exceções: subdomínios "técnicos" que devem cair em fallback default
            # (não são tenants): www, api, app, admin
            if slug not in {"www", "api", "app", "admin"}:
                org = self._get_org_by_slug(slug)
                if org:
                    self._org_cache[host] = org
                    self._org_cache_ts[host] = time.time()
                    return org

        # Strategy 2: JWT cookie org_id (user's home org) — fallback
        # Útil em apex (casehub.legal) ou quando subdomain não resolve
        token = request.cookies.get("casehub_token")
        if token:
            try:
                from jose import jwt as jose_jwt
                from config import settings as _s
                payload = jose_jwt.decode(token, _s.SECRET_KEY, algorithms=["HS256"])
                jwt_org_id = payload.get("org_id")
                if jwt_org_id:
                    org = self._get_org_by_id(int(jwt_org_id))
                    if org:
                        return org
            except Exception as e:
                logger.debug("JWT org_id resolution failed: %s", e)

        # Strategy 3: Default org fallback (single-tenant mode)
        org = self._get_org_by_slug(self.default_org_slug)
        if org:
            self._org_cache[host] = org
            self._org_cache_ts[host] = time.time()
        return org

    def _get_org_by_id(self, org_id: int) -> Optional[dict]:
        """Fetch organization by ID."""
        db: Session = SessionLocal()
        try:
            result = db.execute(
                text("SELECT * FROM organizations WHERE id = :id"),
                {"id": org_id},
            ).mappings().first()
            return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error fetching org by id {org_id}: {e}")
            return None
        finally:
            db.close()

    def _get_org_by_domain(self, domain: str) -> Optional[dict]:
        """Fetch organization by custom domain."""
        db: Session = SessionLocal()
        try:
            result = db.execute(
                text("SELECT * FROM organizations WHERE domain = :domain AND is_active = TRUE"),
                {"domain": domain},
            ).mappings().first()
            return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error fetching org by domain {domain}: {e}")
            return None
        finally:
            db.close()

    def _get_org_by_slug(self, slug: str) -> Optional[dict]:
        """Fetch organization by slug."""
        db: Session = SessionLocal()
        try:
            result = db.execute(
                text("SELECT * FROM organizations WHERE slug = :slug AND is_active = TRUE"),
                {"slug": slug},
            ).mappings().first()
            return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error fetching org by slug {slug}: {e}")
            return None
        finally:
            db.close()

    def clear_cache(self):
        """Clear the org cache (call after org updates)."""
        self._org_cache.clear()


def get_current_org(request: Request = None) -> Optional[dict]:
    """
    Get the current organization for this request.

    Can be called with or without a request object:
    - With request: reads from request.state.org
    - Without request: reads from context variable (set by middleware)
    """
    if request and hasattr(request.state, "org"):
        return request.state.org
    return _current_org.get()


def require_org(request: Request) -> dict:
    """
    Get the current organization or raise 403.
    Use as a FastAPI dependency.
    """
    org = get_current_org(request)
    if not org:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="No organization context found.")
    return org
