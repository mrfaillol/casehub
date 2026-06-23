"""
CaseHub White-Label - App Factory
Creates a FastAPI application configured for a specific product vertical.

Usage:
    from core.app_factory import create_app
    app = create_app("immigration")   # Full immigration product
    app = create_app("lite")          # Lightweight CRM-only product
"""
import asyncio
import logging
import os
import secrets
import time
import threading
from functools import lru_cache

logger = logging.getLogger(__name__)
from datetime import datetime, timedelta, date
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings
from models import Base, engine, get_db, init_db, SessionLocal, User
from auth import get_current_user, create_access_token, create_refresh_token, validate_refresh_token, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS
from core.static_assets import asset_url, brand_kit_fallback_favicon_url
from core.jinja_runtime import configure_jinja_templates
from core.release_notice import get_casehub_release_notice
from services.dashboard_metrics import (
    cached_basic_dashboard_html,
    get_basic_dashboard_context,
    get_legacy_dashboard_context,
)
from i18n import TRANSLATIONS, DEFAULT_LANG, get_translations

PREFIX = settings.PREFIX


def _flag_enabled(value: str) -> bool:
    return (value or "").lower() in {"1", "true", "yes", "on"}


def _env_or_setting(name: str) -> str:
    value = os.getenv(name)
    if value is not None:
        return value
    return getattr(settings, name, "") or ""


def _improvement_tasks_enabled() -> bool:
    return _flag_enabled(_env_or_setting("CASEHUB_IMPROVEMENT_TASKS_ENABLED"))


def _sanitize_public_error_context(org_ctx: dict) -> dict:
    """Prevent global ORG_* fallbacks from leaking into public error pages."""
    if "org_email" in org_ctx or "org_phone" in org_ctx:
        return org_ctx

    sanitized = dict(org_ctx)
    sanitized.update({
        "org_email": "",
        "org_phone": "",
        "org_domain": "",
    })
    return sanitized


def _accepted_improvement_hmac_key() -> str:
    return (
        _env_or_setting("CASEHUB_IMPROVEMENT_HMAC_KEY")
        or _env_or_setting("CASEHUB_OPS_HMAC_KEY")
    )


def _explicit_casehub_env() -> str:
    return (os.getenv("CASEHUB_ENV") or "").lower()


def _is_explicit_dev_env() -> bool:
    return _explicit_casehub_env() in {"dev", "development", "test", "ci"}


def _static_asset_file_exists(path: str) -> bool:
    url = asset_url(path).split("?", 1)[0]
    normalized = url.lstrip("/")
    if normalized.startswith("static/"):
        normalized = normalized[len("static/"):]
    return os.path.isfile(os.path.join(settings.BASE_DIR, "static", normalized))


def _run_preflight_checks() -> None:
    """Validate critical config gaps that would otherwise fail silently in runtime.

    Called from the FastAPI startup hook. Non-raising by design: legitimate traffic
    should keep flowing even if a non-core feature is misconfigured. Each gap is
    logged at ``critical`` (security/auth posture) or ``warning`` (cosmetic/UX)
    so operators see a single loud line in journalctl/docker logs at boot.

    Covered gaps (drawn from incident 2026-05-09):

    1. ``CASEHUB_IMPROVEMENT_TASKS_ENABLED=1`` but neither HMAC env var set —
       receiver would 401 every webhook silently. Operator usually wants both.
    2. ``templates/partials/head_css.html`` references ``brand-kit/tokens.css``
       but the file is missing under ``static/brand-kit/`` — browsers get 404,
       baseline brand tokens never load. Common deploy-gap symptom.
    """
    if _improvement_tasks_enabled() and not _accepted_improvement_hmac_key():
        logger.critical(
            "PRE-FLIGHT: CASEHUB_IMPROVEMENT_TASKS_ENABLED=1 but neither "
            "CASEHUB_IMPROVEMENT_HMAC_KEY nor CASEHUB_OPS_HMAC_KEY is set. "
            "improvement-tasks receiver will reject every HMAC request and "
            "only accept admin JWT — likely not the intended posture. "
            "Plant the same value used in the GitHub repo secret on the host's "
            "~/casehub/.env and restart."
        )

    base_dir = settings.BASE_DIR
    head_css = os.path.join(base_dir, "templates", "partials", "head_css.html")
    try:
        with open(head_css, encoding="utf-8") as fh:
            head_css_body = fh.read()
    except (OSError, UnicodeError):
        head_css_body = ""
    if "brand-kit/tokens.css" in head_css_body:
        if not _static_asset_file_exists("brand-kit/tokens.css"):
            logger.warning(
                "PRE-FLIGHT: templates/partials/head_css.html references "
                "brand-kit/tokens.css but the manifest-resolved static asset "
                "is missing on disk. Browsers will 404 the brand-kit baseline; "
                "confirm the latest deploy carried static/brand-kit/."
            )


@lru_cache(maxsize=8)
def resolve_deploy_commit(base_dir: str) -> str:
    """Resolve the deploy commit SHA for ``base_dir``.

    Reads ``.deploy-info`` (preferred), then ``.deploy-sha`` / ``VERSION_COMMIT``
    as fallbacks. The result is cached per ``base_dir`` so subsequent calls
    avoid disk I/O — important because this function is invoked from health
    check handlers running on the async event loop.

    Cache assumption: deploy markers are written once at deploy time (see
    ``deploy-dev`` fix in #234) and do not change while the process is alive.
    Restart the app to pick up a new value, or call
    ``resolve_deploy_commit.cache_clear()`` from a test/admin context.
    Thread-safe: ``functools.lru_cache`` uses an internal lock around its
    bookkeeping, and the underlying read is idempotent.
    """
    deploy_info = os.path.join(base_dir, ".deploy-info")
    try:
        with open(deploy_info, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("commit="):
                    value = line.split("=", 1)[1].strip()
                    if value:
                        return value
    except (OSError, UnicodeError) as exc:
        logger.warning("Failed reading deploy marker %s: %s", deploy_info, exc)
        pass
    for filename in (".deploy-sha", "VERSION_COMMIT"):
        try:
            with open(os.path.join(base_dir, filename), encoding="utf-8") as fh:
                value = fh.read().strip()
        except (OSError, UnicodeError) as exc:
            logger.warning("Failed reading deploy marker %s: %s", filename, exc)
            continue
        if value:
            return value
    return "unknown"


# ---------------------------------------------------------------------------
# LoginRateLimiter (shared across products)
# ---------------------------------------------------------------------------
class LoginRateLimiter:
    """Simple in-memory rate limiter for login attempts."""
    def __init__(self, max_attempts=5, window_seconds=300, lockout_seconds=900):
        self.max_attempts = max_attempts      # 5 attempts
        self.window_seconds = window_seconds  # per 5 min window
        self.lockout_seconds = lockout_seconds  # 15 min lockout after exceeded
        self._attempts = {}  # ip -> [(timestamp, ...)]
        self._lockouts = {}  # ip -> lockout_until timestamp
        self._lock = threading.Lock()

    def _cleanup(self):
        """Remove expired entries."""
        now = time.time()
        cutoff = now - self.window_seconds
        expired_ips = []
        for ip, timestamps in self._attempts.items():
            self._attempts[ip] = [t for t in timestamps if t > cutoff]
            if not self._attempts[ip]:
                expired_ips.append(ip)
        for ip in expired_ips:
            del self._attempts[ip]
        # Clean expired lockouts
        expired_lockouts = [ip for ip, until in self._lockouts.items() if until < now]
        for ip in expired_lockouts:
            del self._lockouts[ip]

    def is_locked(self, ip: str) -> bool:
        """Check if IP is locked out."""
        with self._lock:
            self._cleanup()
            if ip in self._lockouts:
                if time.time() < self._lockouts[ip]:
                    return True
                del self._lockouts[ip]
            return False

    def record_attempt(self, ip: str) -> bool:
        """Record a failed login attempt. Returns True if now locked out."""
        with self._lock:
            now = time.time()
            self._cleanup()
            if ip not in self._attempts:
                self._attempts[ip] = []
            self._attempts[ip].append(now)
            if len(self._attempts[ip]) >= self.max_attempts:
                self._lockouts[ip] = now + self.lockout_seconds
                self._attempts[ip] = []  # Reset counter
                return True
            return False

    def reset(self, ip: str):
        """Reset attempts on successful login."""
        with self._lock:
            self._attempts.pop(ip, None)
            self._lockouts.pop(ip, None)

    def remaining_lockout(self, ip: str) -> int:
        """Seconds remaining in lockout, or 0."""
        with self._lock:
            if ip in self._lockouts:
                remaining = int(self._lockouts[ip] - time.time())
                return max(0, remaining)
            return 0


# Singleton limiter shared by all app instances in this process
login_limiter = LoginRateLimiter()


# ---------------------------------------------------------------------------
# Middleware classes
# ---------------------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        # /showcase sets its own CSP with broader frame-ancestors
        if "/showcase" not in request.url.path:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
                "img-src 'self' data: https:; "
                "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
                "connect-src 'self' https://cdn.jsdelivr.net; "
                "frame-src 'self' https:; "
                "frame-ancestors 'self'"
            )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class AuditContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        from services.audit import set_audit_context
        ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if not ip:
            ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent", "")[:500]
        org_id = getattr(getattr(request, "state", None), "org_id", None)

        user_id = None
        user_email = None
        token = request.cookies.get("casehub_token")
        if token:
            try:
                import jwt as _jwt
                payload = _jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
                user_email = payload.get("sub")
            except Exception:
                pass

        # Real presence touch: bump last_activity for the authenticated user so
        # the dashboard "Online agora" reflects who is genuinely active. Throttled
        # to at most once / PRESENCE_TOUCH_SECONDS per email to avoid a DB write
        # on every request on the live alpha. Best-effort: never block the request.
        if user_email:
            self._touch_presence(user_email)

        set_audit_context(
            user_id=user_id,
            user_email=user_email,
            org_id=org_id,
            ip_address=ip,
            user_agent=ua,
        )
        return await call_next(request)

    # email -> monotonic deadline of next allowed DB write
    _presence_seen: dict = {}
    _presence_lock = threading.Lock()
    PRESENCE_TOUCH_SECONDS = 60

    def _touch_presence(self, email: str) -> None:
        import time as _time
        now_mono = _time.monotonic()
        with AuditContextMiddleware._presence_lock:
            deadline = AuditContextMiddleware._presence_seen.get(email, 0.0)
            if now_mono < deadline:
                return
            AuditContextMiddleware._presence_seen[email] = now_mono + self.PRESENCE_TOUCH_SECONDS
        db = None
        try:
            from models.base import SessionLocal
            from sqlalchemy import update as _sql_update
            db = SessionLocal()
            db.execute(
                _sql_update(User)
                .where(User.email == email)
                .values(last_activity=datetime.now())
            )
            db.commit()
        except Exception as exc:
            logger.warning("presence touch failed for %s: %s", email, exc)
            # Allow a retry sooner on failure (e.g. column not yet migrated).
            with AuditContextMiddleware._presence_lock:
                AuditContextMiddleware._presence_seen.pop(email, None)
            if db is not None:
                try:
                    db.rollback()
                except Exception:
                    pass
        finally:
            if db is not None:
                db.close()


# ---------------------------------------------------------------------------
# Helper functions (shared)
# ---------------------------------------------------------------------------
def get_lang(request: Request) -> str:
    """Get language from cookie or default based on product type."""
    cookie_lang = request.cookies.get("lang")
    if cookie_lang:
        return cookie_lang
    # Default based on product type
    product_state = getattr(getattr(request, "app", None), "state", None)
    if product_state and getattr(product_state, "product", None) == "lite":
        return "pt"
    return DEFAULT_LANG


def _accept_preference(accept_header: str, matcher) -> tuple[float, int]:
    """Return q-value and specificity for the best matching media range."""
    best_quality = 0.0
    best_specificity = -1
    for item in (accept_header or "").split(","):
        parts = [part.strip() for part in item.split(";") if part.strip()]
        if not parts:
            continue
        media_type = parts[0].lower()
        specificity = matcher(media_type)
        if specificity < 0:
            continue
        quality = 1.0
        for param in parts[1:]:
            if param.lower().startswith("q="):
                try:
                    quality = float(param[2:])
                except ValueError:
                    quality = 0.0
                break
        if specificity > best_specificity:
            best_quality = quality
            best_specificity = specificity
        elif specificity == best_specificity:
            best_quality = max(best_quality, quality)
    return best_quality, best_specificity


def _html_accept_specificity(media_type: str) -> int:
    if media_type == "text/html":
        return 2
    if media_type == "text/*":
        return 1
    if media_type == "*/*":
        return 0
    return -1


def _json_accept_specificity(media_type: str) -> int:
    if media_type == "application/json":
        return 2
    if media_type.startswith("application/") and media_type.endswith("+json"):
        return 2
    if media_type == "application/*":
        return 1
    if media_type == "*/*":
        return 0
    return -1


def _wants_html_response(request: Request) -> bool:
    """Prefer JSON when clients explicitly ask for JSON over HTML."""
    accept = request.headers.get("accept", "")
    html_q, html_specificity = _accept_preference(accept, _html_accept_specificity)
    json_q, json_specificity = _accept_preference(accept, _json_accept_specificity)
    return html_q > 0 and (html_q > json_q or (html_q == json_q and html_specificity > json_specificity))


def _request_path_with_query(request: Request) -> str:
    query = request.url.query
    return f"{request.url.path}?{query}" if query else request.url.path


def _minimal_500_html(error_ref: str) -> str:
    return (
        "<!doctype html><html><head><title>Internal Error</title></head>"
        "<body><main role=\"main\"><h1>Internal Error</h1>"
        "<p>Something went wrong on our end. Please try again later.</p>"
        f"<p>Error reference: <code>{error_ref}</code></p>"
        "</main></body></html>"
    )


def get_context(request: Request, db: Session = None, user=None, **kwargs) -> dict:
    """Build common context for templates, including org branding."""
    from core.template_config import inject_org_context
    lang = get_lang(request)
    t = get_translations(lang)
    if user is None and db:
        user = get_current_user(request, db)
    org_ctx = inject_org_context(request, user=user)
    return {
        "request": request,
        "PREFIX": PREFIX,
        "lang": lang,
        "t": t,
        "user": user,
        **org_ctx,
        **kwargs
    }


# ---------------------------------------------------------------------------
# Router registry
# ---------------------------------------------------------------------------

# CORE routers - shared by ALL products
CORE_ROUTERS = [
    "clients", "cases", "processes", "documents", "documents_api", "admin", "calendar",
    "tasks", "billing", "emails", "portal",
    "api", "reports",
    "import_data", "notifications", "notifications_api", "invoices", "audit", "workflow",
    "two_factor", "versions", "notes", "doc_templates",
    "settings", "payments", "alerts", "triggers",
    "global_alerts", "contacts", "sso", "referrals", "bulk",
    "client_relationships",
    "google_calendar", "gmail", "drive_explorer", "drive_upload", "maestro_learn", "integrations", "integrations_gateway", "email_templates_v2", "branding",
    "onboarding", "superadmin", "password_reset", "subscription",
    "tribunal", "prazos", "files", "checklist",
    "email_worker_status", "leads_analytics", "leads_scoring", "tickets",
    "controladoria", "dje", "tools_br", "tools_criminal", "tools_bancario", "tools_tributario", "pecas", "dashboard_api",
    "assistente", "customizacao",
    "profile",
    "import_br",
    "user_theme",
    "hub_tabs",
    "design_editor",
    "template_notes",
    "pdpj_oauth",
    "improvement_tasks",
    "work_intelligence",
    "casehub_md",
    "search",
    "team_messages",  # chat de equipe seguro org-scoped (/api/team-chat) — substitui o team_chat inseguro
    "legal",  # /privacy + /terms públicos (pré-requisito verificação Google OAuth)
]

# IMMIGRATION-specific routers (NOT loaded for Lite)
IMMIGRATION_ROUTERS = [
    "uscis", "uscis_status", "uscis_forms", "efiling", "case_wizard",
    "packets", "shipments", "intake", "case_archive", "ilc_tools",
    "lor_maker", "ps_maker", "package_maker",
    "whatsapp_chat", "callhippo", "moskit",
    "whatsapp_proxy",  # Generic /whatsapp-api/* reverse-proxy to the Node bot (unblocks QR)
    "whatsapp_crm",  # WhatsApp Web clone Tier-3 power-features (CRM/AI/pipeline); shares whatsapp_chat prefix
    "whatsapp_inbound",  # HMAC-protected bot bridge used by the clone stack
    # Moved from CORE (immigration/ILC-specific):
    "notion", "deadlines", "letters", "questionnaires",
    "custom_fields", "webhooks", "signatures", "team_chat",
    "legal_assistant", "communications",
    "whatsapp",  # Immigration uses original WhatsApp dashboard
]

# LITE-specific routers (NOT loaded for Immigration)
LITE_ROUTERS = [
    "whatsapp_chat",  # Full chat API used by the remake shell surface
    "whatsapp_lite",  # Lite uses simplified BR WhatsApp dashboard
    "whatsapp_inbound",  # Inbound bridge + field-request flow (alpha 25/05)
    "whatsapp_proxy",  # Generic /whatsapp-api/* reverse-proxy to the Node bot (unblocks QR)
    "whatsapp_crm",  # WhatsApp Web clone Tier-3 power-features (CRM/AI/pipeline); shares whatsapp_chat prefix
    "webhooks",  # Webhook management UI (Lite alpha 25/05 — Jaime audit)
    "case_wizard",  # Case intake wizard (Lite alpha 25/05)
]

# Communication integration routers (shared but optional)
COMMUNICATION_ROUTERS = [
    "twilio",
    "messaging_hub", "leads", "aila_api", "aila_wiki",
]

# WHITELABEL-specific routers (international law firms, no USCIS)
WHITELABEL_ROUTERS = [
    "intake", "case_archive",
    "lor_maker", "ps_maker", "package_maker",
    "whatsapp_chat",
    "whatsapp_proxy",  # Generic /whatsapp-api/* reverse-proxy to the Node bot (unblocks QR)
    "whatsapp_crm",  # WhatsApp Web clone Tier-3 power-features (CRM/AI/pipeline); shares whatsapp_chat prefix
    "whatsapp_inbound",  # HMAC-protected bot bridge used by the clone stack
    "notion", "deadlines", "processes", "letters", "questionnaires",
    "custom_fields", "webhooks", "signatures", "team_chat",
    "legal_assistant", "communications", "whatsapp",
]

# Internal dev/curation tooling — NÃO carregado em nenhum produto por default.
# Estes routers são públicos (sem get_current_user) e expõem tooling interno de
# design/curadoria (gen-lab digest, briefs, templates arquivados). Em produto
# cliente (lite/alpha) isso é information disclosure desnecessária.
# Habilitar só em dev via ENABLE_INTERNAL_TOOLS=1.
# Sentinela ruling 2026-05-28-t9-internal-routers-gating (CWE-862).
INTERNAL_DEV_ROUTERS = ["template_archive", "refactor_review", "artist_board"]
INTERNAL_TOOLS_ENABLED = os.getenv("ENABLE_INTERNAL_TOOLS", "").strip().lower() in ("1", "true", "yes")
_INTERNAL = INTERNAL_DEV_ROUTERS if INTERNAL_TOOLS_ENABLED else []

# Which router sets each product includes
PRODUCT_ROUTERS = {
    "immigration": CORE_ROUTERS + IMMIGRATION_ROUTERS + COMMUNICATION_ROUTERS + _INTERNAL,
    "lite": CORE_ROUTERS + LITE_ROUTERS + COMMUNICATION_ROUTERS + _INTERNAL,
    "whitelabel": CORE_ROUTERS + WHITELABEL_ROUTERS + COMMUNICATION_ROUTERS + _INTERNAL,
}

# Product-specific defaults (currency, language, timezone, features)
PRODUCT_DEFAULTS = {
    "immigration": {
        "currency": "USD",
        "currency_symbol": "$",
        "currency_locale": "en_US",
        "default_lang": "en",
        "timezone": "America/New_York",
        "date_format": "%m/%d/%Y",
        "features": {
            "uscis_tracking": True,
            "visa_types": True,
            "rfe_management": True,
            "client_portal": True,
            "whatsapp_bot": True,
            "intake_forms": True,
            "packet_builder": True,
            "efiling": True,
        },
    },
    "lite": {
        "currency": "BRL",
        "currency_symbol": "R$",
        "currency_locale": "pt_BR",
        "default_lang": "pt",
        "timezone": "America/Sao_Paulo",
        "date_format": "%d/%m/%Y",
        "features": {
            "browser_basic_shell": True,
            "neumorphic_core": True,
            "hub_tabs": False,
            "processo_tracking": True,
            "prazos_processuais": True,
            "tribunal_integration": True,
            "oab_lookup": True,
            "notion_integration": True,
            "google_workspace": True,
            "whatsapp_bot": True,
            "dark_mode": True,
        },
    },
    "whitelabel": {
        "currency": "USD",
        "currency_symbol": "$",
        "currency_locale": "en_US",
        "default_lang": "en",
        "timezone": "America/New_York",
        "date_format": "%m/%d/%Y",
        "features": {
            "client_portal": True,
            "intake_forms": True,
            "whatsapp_bot": False,
            "hub_tabs": True,
            "dark_mode": True,
            "notion_integration": True,
            "google_workspace": True,
        },
    },
}
def get_product_defaults(product: str) -> dict:
    """Get defaults for a product, with env var overrides."""
    defaults = PRODUCT_DEFAULTS.get(product, PRODUCT_DEFAULTS["immigration"]).copy()
    # Allow env var overrides
    if settings.DEFAULT_CURRENCY:
        defaults["currency"] = settings.DEFAULT_CURRENCY
    if settings.DEFAULT_TIMEZONE:
        defaults["timezone"] = settings.DEFAULT_TIMEZONE
    return defaults


def _import_router(module_name: str):
    """
    Import a router from routes.<module_name>.
    Returns a list of routers (some modules export multiple routers, e.g. leads).
    """
    import importlib
    try:
        mod = importlib.import_module(f"routes.{module_name}")
    except ImportError as e:
        logger.warning("[app_factory] Skipping routes.%s: %s", module_name, e)
        return []

    routers = []
    # Primary router
    if hasattr(mod, "router"):
        routers.append(mod.router)
    # Some modules export extra routers (e.g. leads has pages_router)
    if hasattr(mod, "pages_router"):
        routers.append(mod.pages_router)
    return routers


def _run_pending_migrations():
    """Run ALTER TABLE statements to add missing columns.
    Uses IF NOT EXISTS so it's safe to run multiple times."""
    from models.base import SessionLocal
    db = SessionLocal()
    try:
        bind = db.get_bind()
        dialect = bind.dialect.name if bind is not None else ""
        is_sqlite = dialect == "sqlite"
        pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if is_sqlite else "SERIAL PRIMARY KEY"
        now_default = "CURRENT_TIMESTAMP" if is_sqlite else "NOW()"
        false_default = "0" if is_sqlite else "FALSE"
        true_default = "1" if is_sqlite else "TRUE"
        timestamp_add_default = "TIMESTAMP" if is_sqlite else f"TIMESTAMP DEFAULT {now_default}"

        def _table_exists(table_name: str) -> bool:
            if is_sqlite:
                row = db.execute(
                    text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :table_name"),
                    {"table_name": table_name},
                ).fetchone()
                return bool(row)
            row = db.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = :table_name"
                ),
                {"table_name": table_name},
            ).fetchone()
            return bool(row)

        def _column_exists(table_name: str, column_name: str) -> bool:
            if is_sqlite:
                rows = db.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
                return any(row[1] == column_name for row in rows)
            row = db.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = :table_name AND column_name = :column_name"
                ),
                {"table_name": table_name, "column_name": column_name},
            ).fetchone()
            return bool(row)

        def _add_column_if_missing(table_name: str, column_name: str, definition: str) -> None:
            if not _table_exists(table_name):
                return
            if _column_exists(table_name, column_name):
                return
            db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))

        for table_name, column_name, definition in [
            # Brazilian law fields on cases
            ("cases", "numero_processo", "VARCHAR(50)"),
            ("cases", "tipo_acao", "VARCHAR(100)"),
            ("cases", "vara", "VARCHAR(100)"),
            ("cases", "comarca", "VARCHAR(100)"),
            ("cases", "tribunal", "VARCHAR(100)"),
            ("cases", "fase_processual", "VARCHAR(100)"),
            ("cases", "polo_ativo", "TEXT"),
            ("cases", "polo_passivo", "TEXT"),
            # Client schema drift between legacy demos, Basic dev, and the
            # current ORM model. These are nullable to keep old rows valid.
            ("clients", "first_name", "VARCHAR(100)"),
            ("clients", "middle_name", "VARCHAR(100)"),
            ("clients", "last_name", "VARCHAR(100)"),
            ("clients", "email", "VARCHAR(200)"),
            ("clients", "phone", "VARCHAR(50)"),
            ("clients", "whatsapp", "VARCHAR(50)"),
            ("clients", "date_of_birth", "DATE"),
            ("clients", "country_of_origin", "VARCHAR(100)"),
            ("clients", "ssn", "VARCHAR(200)"),
            ("clients", "alien_number", "VARCHAR(200)"),
            ("clients", "client_number", "VARCHAR(50)"),
            ("clients", "passport_number", "VARCHAR(200)"),
            ("clients", "cpf", "VARCHAR(200)"),
            ("clients", "rg", "VARCHAR(200)"),
            ("clients", "cnpj", "VARCHAR(200)"),
            ("clients", "oab_number", "VARCHAR(50)"),
            ("clients", "nationality", "VARCHAR(100)"),
            ("clients", "client_type", "VARCHAR(20) DEFAULT 'individual'"),
            ("clients", "address", "TEXT"),
            ("clients", "city", "VARCHAR(100)"),
            ("clients", "state", "VARCHAR(50)"),
            ("clients", "zip_code", "VARCHAR(20)"),
            ("clients", "org_id", "INTEGER"),
            ("clients", "status", "VARCHAR(50) DEFAULT 'active'"),
            ("clients", "notes", "TEXT"),
            ("clients", "drive_folder_id", "VARCHAR(200)"),
            ("clients", "drive_folder_name", "VARCHAR(300)"),
            ("clients", "tasks_folder_data", "TEXT"),
            ("clients", "created_at", timestamp_add_default),
            ("clients", "updated_at", "TIMESTAMP"),
            # Basic shell support columns
            ("tasks", "column_id", "INTEGER"),
            # Onboarding/subdomain rollout. These columns are mapped by the ORM,
            # so existing databases must receive them before the startup admin
            # query loads User rows.
            ("users", "last_activity", "TIMESTAMP"),
            ("users", "onboarding_completed_at", "TIMESTAMP"),
            ("users", "onboarding_tour_step", "VARCHAR(50)"),
            ("users", "email_verified_at", "TIMESTAMP"),
            ("organizations", "created_via", "VARCHAR(20) DEFAULT 'manual'"),
            ("organizations", "subdomain_locked", f"BOOLEAN DEFAULT {false_default}"),
            ("users", "color", "VARCHAR(20) DEFAULT '#1C2447'"),
            # Billing/payment routes expect this column on existing databases.
            ("billing_items", "invoice_number", "VARCHAR(50)"),
            # Controladoria columns added after the first Basic table bootstrap.
            # Existing dev/prod databases may already have prazos_processuais
            # without these fields, so CREATE TABLE IF NOT EXISTS is not enough.
            ("prazos_processuais", "tipo_peticao", "VARCHAR(120)"),
            ("prazos_processuais", "processo_override", "VARCHAR(80)"),
            ("prazos_processuais", "cliente_override", "VARCHAR(255)"),
            ("prazos_processuais", "data_conclusao", "DATE"),
            ("prazos_processuais", "ordem", "INTEGER DEFAULT 0"),
            ("prazos_processuais", "responsavel_user_id", "INTEGER"),
            ("prazos_processuais", "source_provider", "VARCHAR(120)"),
            ("prazos_processuais", "source_status", "VARCHAR(50) DEFAULT 'manual'"),
            ("prazos_processuais", "source_reference", "VARCHAR(255)"),
            ("prazos_processuais", "source_url", "TEXT"),
            ("prazos_processuais", "source_payload_hash", "VARCHAR(64)"),
            ("prazos_processuais", "source_fetched_at", "TIMESTAMP"),
            ("prazos_processuais", "source_version", "VARCHAR(80)"),
            ("prazos_processuais", "official_source", f"BOOLEAN DEFAULT {false_default}"),
            ("prazos_processuais", "calculation_engine_version", "VARCHAR(80)"),
            ("prazos_processuais", "calculation_notes", "TEXT"),
            ("appointments", "case_id", "INTEGER"),
            ("appointments", "prazo_id", "INTEGER"),
            ("appointments", "task_id", "INTEGER"),
            ("appointments", "gcal_event_id", "VARCHAR(255)"),
            # Perícia (aba Peric/Pe-Das1 planilha VS, 03/06): local físico/online
            # da perícia e o status de acompanhamento. Nullable/additive — só são
            # preenchidos quando type='pericia'.
            ("appointments", "local", "VARCHAR(255)"),
            ("appointments", "pericia_status", "VARCHAR(50)"),
            # Listas privadas no Kanban (03/06): visibility/created_by ficam no MODEL
            # Task -> são SELECTadas em TODA query de tarefa (Painel inclusive). Por isso
            # PRECISAM ser garantidas no STARTUP (não só no _ensure lazy do kanban_view),
            # senão Painel/qualquer página com query de task dá 500 UndefinedColumn.
            ("tasks", "visibility", "VARCHAR(20) DEFAULT 'org'"),
            ("tasks", "created_by", "INTEGER"),
            ("kanban_columns", "visibility", "VARCHAR(20) DEFAULT 'shared'"),
            ("kanban_columns", "owner_user_id", "INTEGER"),
            ("kanban_columns", "is_archived", f"BOOLEAN DEFAULT {false_default}"),
            # WhatsApp CRM owner-tag + lead scoring (feature 2026-05-30). Additive,
            # nullable. owner_user_id = team member who owns the contact (badge
            # color resolved from users.color). lead_score is Phase-2 scoring.
            ("wa_contacts", "owner_user_id", "INTEGER"),
            ("wa_contacts", "lead_score", "INTEGER DEFAULT 0"),
            # Follow-up scheduling (PR7) + normalized phone for dedup (PR8). Additive.
            ("wa_contacts", "follow_up_date", "DATE"),
            ("wa_contacts", "follow_up_note", "TEXT"),
            ("wa_contacts", "normalized_phone", "VARCHAR(32)"),
            # Operator attribution on outgoing clone messages. Nullable so
            # incoming/legacy/AI rows stay valid; records which CaseHub user
            # sent, independent of the QR-connector profile.
            ("wa_messages", "sent_by_user_id", "INTEGER"),
            # Automatic SQLAlchemy audit listeners run for every ORM insert.
            # If this table is absent, Postgres marks the main transaction as
            # aborted even though the listener catches the exception.
            ("audit_log", "org_id", "INTEGER"),
            ("audit_log", "details", "TEXT"),
            ("audit_log", "ip_address", "VARCHAR(100)"),
            ("audit_log", "user_agent", "VARCHAR(500)"),
            # Process template workflow tables can predate the current route.
            ("case_processes", "org_id", "INTEGER"),
            ("case_processes", "name", "VARCHAR(200)"),
            ("case_processes", "description", "TEXT"),
            ("case_processes", "area_of_practice", "VARCHAR(100)"),
            ("case_processes", "visa_types", "TEXT"),
            ("case_processes", "estimated_days", "INTEGER"),
            ("case_processes", "enabled", f"BOOLEAN DEFAULT {true_default}"),
            ("case_processes", "created_at", timestamp_add_default),
            ("case_processes", "updated_at", "TIMESTAMP"),
            ("process_steps", "process_id", "INTEGER"),
            ("process_steps", "step_number", "INTEGER"),
            ("process_steps", "name", "VARCHAR(200)"),
            ("process_steps", "description", "TEXT"),
            ("process_steps", "estimated_days", "INTEGER"),
            ("process_steps", "is_milestone", f"BOOLEAN DEFAULT {false_default}"),
            ("process_steps", "auto_start_next", f"BOOLEAN DEFAULT {true_default}"),
            ("process_steps", "email_on_complete", f"BOOLEAN DEFAULT {false_default}"),
            ("process_steps", "required_documents", "TEXT"),
            ("process_steps", "created_at", timestamp_add_default),
            ("process_steps", "updated_at", "TIMESTAMP"),
            ("case_process_tracking", "case_id", "INTEGER"),
            ("case_process_tracking", "process_id", "INTEGER"),
            ("case_process_tracking", "current_step_id", "INTEGER"),
            ("case_process_tracking", "started_at", timestamp_add_default),
            ("case_process_tracking", "completed_at", "TIMESTAMP"),
            ("case_step_progress", "case_id", "INTEGER"),
            ("case_step_progress", "step_id", "INTEGER"),
            ("case_step_progress", "status", "VARCHAR(50) DEFAULT 'pending'"),
            ("case_step_progress", "started_at", "TIMESTAMP"),
            ("case_step_progress", "completed_at", "TIMESTAMP"),
            ("case_step_progress", "target_date", "DATE"),
            ("case_step_progress", "assigned_to", "INTEGER"),
            ("case_step_progress", "completed_by", "INTEGER"),
            ("case_step_progress", "priority", "VARCHAR(20) DEFAULT 'medium'"),
            ("case_step_progress", "notes", "TEXT"),
            ("case_step_progress", "created_at", timestamp_add_default),
            ("case_step_progress", "updated_at", "TIMESTAMP"),
            # financial_entries soft-delete flag (Financeiro editável, 2026-06-04).
            # Soft-delete em dado financeiro real: "excluir" = ativo=FALSE; reads
            # agregam só ativo IS NOT FALSE. additive, default TRUE (linhas legadas
            # permanecem ativas). updated_at p/ trilha de edição inline.
            ("financial_entries", "ativo", f"BOOLEAN DEFAULT {true_default}"),
            ("financial_entries", "updated_at", "TIMESTAMP"),
        ]:
            try:
                _add_column_if_missing(table_name, column_name, definition)
            except Exception as e:
                logger.debug("Column migration skipped for %s.%s: %s", table_name, column_name, e)
                db.rollback()

        stmts = [
            # Custom fields tables
            f"""CREATE TABLE IF NOT EXISTS custom_field_definitions (
                id {pk},
                org_id INTEGER,
                entity_type VARCHAR(50) NOT NULL,
                field_name VARCHAR(100) NOT NULL,
                field_label VARCHAR(200),
                field_type VARCHAR(50) DEFAULT 'text',
                options TEXT,
                required BOOLEAN DEFAULT {false_default},
                display_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT {now_default}
            )""",
            f"""CREATE TABLE IF NOT EXISTS custom_field_values (
                id {pk},
                definition_id INTEGER REFERENCES custom_field_definitions(id),
                entity_id INTEGER NOT NULL,
                entity_type VARCHAR(50) NOT NULL,
                value TEXT,
                updated_at TIMESTAMP DEFAULT {now_default},
                UNIQUE(definition_id, entity_id, entity_type)
            )""",
            # Google Calendar realtime push (events.watch) channel registry.
            # DORMANT until GOOGLE_CALENDAR_WATCH_ENABLED is flipped ON; created
            # eagerly so the (no-op) webhook receiver can SELECT safely on day
            # one. Org-scoped: every channel row carries the authoritative org_id
            # + account that owns it, so the PUBLIC webhook never has to trust
            # the request host/body to decide which tenant to import for. The
            # channel_token is stored ONLY as a SHA-256 hash (never the secret
            # itself) so a DB leak cannot be replayed against Google's webhook.
            # last_message_number gives per-channel replay/out-of-order dedupe.
            f"""CREATE TABLE IF NOT EXISTS gcal_watch_channels (
                id {pk},
                org_id INTEGER NOT NULL,
                account_name VARCHAR(50) NOT NULL,
                channel_id VARCHAR(255) NOT NULL,
                resource_id VARCHAR(512),
                channel_token_hash VARCHAR(64) NOT NULL,
                expiration TIMESTAMP,
                last_message_number BIGINT DEFAULT 0,
                created_at TIMESTAMP DEFAULT {now_default}
            )""",
            f"""CREATE TABLE IF NOT EXISTS audit_log (
                id {pk},
                org_id INTEGER,
                action VARCHAR(100) NOT NULL,
                entity_type VARCHAR(100),
                entity_id INTEGER,
                user_id INTEGER,
                user_email VARCHAR(255),
                description TEXT,
                details TEXT,
                ip_address VARCHAR(100),
                user_agent VARCHAR(500),
                created_at TIMESTAMP DEFAULT {now_default}
            )""",
            f"""CREATE TABLE IF NOT EXISTS org_settings (
                org_id INTEGER NOT NULL,
                key VARCHAR(120) NOT NULL,
                value TEXT,
                PRIMARY KEY (org_id, key)
            )""",
            f"""CREATE TABLE IF NOT EXISTS work_intelligence_events (
                id {pk},
                org_id INTEGER NOT NULL,
                user_id INTEGER,
                event_type VARCHAR(80) NOT NULL,
                route VARCHAR(255),
                surface VARCHAR(120),
                duration_ms INTEGER,
                metadata TEXT,
                source VARCHAR(40) DEFAULT 'server',
                session_hash VARCHAR(64),
                occurred_at TIMESTAMP DEFAULT {now_default},
                created_at TIMESTAMP DEFAULT {now_default}
            )""",
            f"""CREATE TABLE IF NOT EXISTS work_intelligence_daily_metrics (
                id {pk},
                org_id INTEGER NOT NULL,
                metric_date DATE NOT NULL,
                workflow VARCHAR(120) NOT NULL,
                module VARCHAR(120),
                team_key VARCHAR(120) DEFAULT 'org',
                active_users INTEGER DEFAULT 0,
                event_count INTEGER DEFAULT 0,
                completed_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                backlog_count INTEGER DEFAULT 0,
                overdue_count INTEGER DEFAULT 0,
                avg_cycle_seconds INTEGER,
                friction_index NUMERIC(6, 2) DEFAULT 0,
                demand_resource_score NUMERIC(6, 2) DEFAULT 0,
                fragmentation_signal NUMERIC(6, 2) DEFAULT 0,
                quality_signal NUMERIC(6, 2) DEFAULT 0,
                metrics_json TEXT,
                sources_json TEXT,
                created_at TIMESTAMP DEFAULT {now_default},
                updated_at TIMESTAMP DEFAULT {now_default}
            )""",
            f"""CREATE TABLE IF NOT EXISTS work_intelligence_insights (
                id {pk},
                org_id INTEGER NOT NULL,
                insight_date DATE NOT NULL,
                scope_key VARCHAR(120) DEFAULT 'org',
                category VARCHAR(80) NOT NULL,
                severity VARCHAR(30) DEFAULT 'info',
                title VARCHAR(240) NOT NULL,
                body TEXT NOT NULL,
                evidence_json TEXT,
                source_refs_json TEXT,
                status VARCHAR(30) DEFAULT 'open',
                created_at TIMESTAMP DEFAULT {now_default},
                updated_at TIMESTAMP DEFAULT {now_default}
            )""",
            f"""CREATE TABLE IF NOT EXISTS work_intelligence_feedback (
                id {pk},
                org_id INTEGER NOT NULL,
                user_id INTEGER,
                insight_id INTEGER,
                feedback_type VARCHAR(40) NOT NULL,
                usefulness INTEGER,
                comment_redacted TEXT,
                created_at TIMESTAMP DEFAULT {now_default}
            )""",
            f"""CREATE TABLE IF NOT EXISTS org_ai_policies (
                id {pk},
                org_id INTEGER NOT NULL,
                feature VARCHAR(50) NOT NULL DEFAULT 'maestro',
                provider VARCHAR(50) NOT NULL DEFAULT 'ollama',
                model VARCHAR(120),
                endpoint_url TEXT,
                enabled BOOLEAN DEFAULT {true_default},
                created_at TIMESTAMP DEFAULT {now_default},
                updated_at TIMESTAMP DEFAULT {now_default}
            )""",
            f"""CREATE TABLE IF NOT EXISTS org_ai_provider_credentials (
                id {pk},
                org_id INTEGER NOT NULL,
                provider VARCHAR(50) NOT NULL,
                secret_ref VARCHAR(200),
                encrypted_secret TEXT,
                created_at TIMESTAMP DEFAULT {now_default},
                updated_at TIMESTAMP DEFAULT {now_default}
            )""",
            f"""CREATE TABLE IF NOT EXISTS maestro_inferences (
                id {pk},
                org_id INTEGER NOT NULL,
                user_id INTEGER,
                message_sha256 VARCHAR(64) NOT NULL,
                response_sha256 VARCHAR(64),
                model VARCHAR(120),
                provider VARCHAR(50) NOT NULL DEFAULT 'ollama',
                status VARCHAR(50),
                created_at TIMESTAMP DEFAULT {now_default}
            )""",
            # Basic module tables. Keep these bootstrap-safe for clean SQLite
            # smoke environments and Postgres deployments.
            f"""CREATE TABLE IF NOT EXISTS prazos_processuais (
                id {pk},
                case_id INTEGER,
                org_id INTEGER,
                tipo VARCHAR(100),
                data_intimacao DATE,
                data_inicio DATE,
                data_vencimento DATE,
                dias_prazo INTEGER,
                responsavel VARCHAR(200),
                status VARCHAR(50) DEFAULT 'pendente',
                descricao TEXT,
                uf VARCHAR(2),
                dobro BOOLEAN DEFAULT {false_default},
                tipo_peticao VARCHAR(120),
                processo_override VARCHAR(80),
                cliente_override VARCHAR(255),
                data_conclusao DATE,
                ordem INTEGER DEFAULT 0,
                responsavel_user_id INTEGER,
                source_provider VARCHAR(120),
                source_status VARCHAR(50) DEFAULT 'manual',
                source_reference VARCHAR(255),
                source_url TEXT,
                source_payload_hash VARCHAR(64),
                source_fetched_at TIMESTAMP,
                source_version VARCHAR(80),
                official_source BOOLEAN DEFAULT {false_default},
                calculation_engine_version VARCHAR(80),
                calculation_notes TEXT,
                created_at TIMESTAMP DEFAULT {now_default},
                updated_at TIMESTAMP DEFAULT {now_default}
            )""",
            f"""CREATE TABLE IF NOT EXISTS appointments (
                id {pk},
                org_id INTEGER,
                title VARCHAR(255) NOT NULL,
                type VARCHAR(50) DEFAULT 'atendimento',
                assigned_to INTEGER,
                case_id INTEGER,
                prazo_id INTEGER,
                task_id INTEGER,
                client_name VARCHAR(255),
                date DATE NOT NULL,
                time_start TIME,
                time_end TIME,
                is_virtual BOOLEAN DEFAULT {false_default},
                location VARCHAR(255),
                notes TEXT,
                gcal_event_id VARCHAR(255),
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT {now_default},
                updated_at TIMESTAMP DEFAULT {now_default}
            )""",
            f"""CREATE TABLE IF NOT EXISTS kanban_columns (
                id {pk},
                org_id INTEGER NOT NULL,
                name VARCHAR(120) NOT NULL,
                slug VARCHAR(80) NOT NULL,
                position INTEGER DEFAULT 0,
                color VARCHAR(20) DEFAULT '#94a3b8',
                is_done BOOLEAN DEFAULT {false_default},
                visibility VARCHAR(20) DEFAULT 'shared',
                owner_user_id INTEGER,
                is_archived BOOLEAN DEFAULT {false_default},
                created_at TIMESTAMP DEFAULT {now_default},
                updated_at TIMESTAMP DEFAULT {now_default}
            )""",
            f"""CREATE TABLE IF NOT EXISTS task_kanban_placements (
                id {pk},
                org_id INTEGER NOT NULL,
                task_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                column_id INTEGER NOT NULL,
                position INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT {now_default},
                updated_at TIMESTAMP DEFAULT {now_default},
                UNIQUE(user_id, task_id)
            )""",
            f"""CREATE TABLE IF NOT EXISTS task_assignees (
                task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                PRIMARY KEY (task_id, user_id)
            )""",
            f"""CREATE TABLE IF NOT EXISTS email_verifications (
                id {pk},
                user_id INTEGER NOT NULL REFERENCES users(id),
                token VARCHAR(255) NOT NULL UNIQUE,
                email VARCHAR(200) NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                consumed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT {now_default},
                ip_address VARCHAR(64),
                user_agent TEXT
            )""",
            f"""CREATE TABLE IF NOT EXISTS signup_audit_log (
                id {pk},
                org_id INTEGER REFERENCES organizations(id),
                user_id INTEGER REFERENCES users(id),
                email VARCHAR(200) NOT NULL,
                slug VARCHAR(100) NOT NULL,
                firm_name VARCHAR(255),
                ip_address VARCHAR(64),
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT {now_default},
                captcha_score NUMERIC(3,2),
                flagged_reason VARCHAR(200)
            )""",
            f"""CREATE TABLE IF NOT EXISTS entity_webhooks (
                id {pk},
                entity_type VARCHAR(50) NOT NULL,
                entity_id INTEGER,
                event_type VARCHAR(100) NOT NULL,
                webhook_url TEXT NOT NULL,
                headers TEXT,
                enabled BOOLEAN DEFAULT {true_default},
                last_triggered_at TIMESTAMP,
                last_response_code INTEGER,
                failure_count INTEGER DEFAULT 0,
                org_id INTEGER,
                created_at TIMESTAMP DEFAULT {now_default},
                updated_at TIMESTAMP DEFAULT {now_default}
            )""",
            f"""CREATE TABLE IF NOT EXISTS webhook_logs (
                id {pk},
                webhook_id INTEGER NOT NULL REFERENCES entity_webhooks(id),
                event_type VARCHAR(100),
                payload TEXT,
                response_code INTEGER,
                response_body TEXT,
                error_message TEXT,
                triggered_at TIMESTAMP DEFAULT {now_default}
            )""",
            f"""CREATE TABLE IF NOT EXISTS case_processes (
                id {pk},
                org_id INTEGER,
                name VARCHAR(200) NOT NULL,
                description TEXT,
                area_of_practice VARCHAR(100),
                visa_types TEXT,
                estimated_days INTEGER,
                enabled BOOLEAN DEFAULT {true_default},
                created_at TIMESTAMP DEFAULT {now_default},
                updated_at TIMESTAMP DEFAULT {now_default}
            )""",
            f"""CREATE TABLE IF NOT EXISTS process_steps (
                id {pk},
                process_id INTEGER REFERENCES case_processes(id),
                step_number INTEGER NOT NULL,
                name VARCHAR(200) NOT NULL,
                description TEXT,
                estimated_days INTEGER,
                is_milestone BOOLEAN DEFAULT {false_default},
                auto_start_next BOOLEAN DEFAULT {true_default},
                email_on_complete BOOLEAN DEFAULT {false_default},
                required_documents TEXT,
                created_at TIMESTAMP DEFAULT {now_default},
                updated_at TIMESTAMP DEFAULT {now_default}
            )""",
            f"""CREATE TABLE IF NOT EXISTS case_process_tracking (
                id {pk},
                case_id INTEGER REFERENCES cases(id),
                process_id INTEGER REFERENCES case_processes(id),
                current_step_id INTEGER REFERENCES process_steps(id),
                started_at TIMESTAMP DEFAULT {now_default},
                completed_at TIMESTAMP,
                UNIQUE(case_id, process_id)
            )""",
            f"""CREATE TABLE IF NOT EXISTS case_step_progress (
                id {pk},
                case_id INTEGER REFERENCES cases(id),
                step_id INTEGER REFERENCES process_steps(id),
                status VARCHAR(50) DEFAULT 'pending',
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                target_date DATE,
                assigned_to INTEGER,
                completed_by INTEGER,
                priority VARCHAR(20) DEFAULT 'medium',
                notes TEXT,
                created_at TIMESTAMP DEFAULT {now_default},
                updated_at TIMESTAMP DEFAULT {now_default},
                UNIQUE(case_id, step_id)
            )""",
            # Proc-M: movimentações/andamentos MANUAIS de processo (04/06). Aditiva,
            # org-scoped, SEM relationship ORM em Case -> nunca é SELECTada em queries
            # de caso (evita o lazy _ensure 500). org_id NOT NULL: toda linha pertence
            # a um tenant; a rota valida que o caso é do org antes de inserir.
            f"""CREATE TABLE IF NOT EXISTS case_movements (
                id {pk},
                org_id INTEGER NOT NULL,
                case_id INTEGER NOT NULL,
                data DATE NOT NULL DEFAULT CURRENT_DATE,
                tipo VARCHAR(50) NOT NULL DEFAULT 'Andamento',
                descricao TEXT NOT NULL,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT {now_default},
                updated_at TIMESTAMP
            )""",
            # Indexes
            "CREATE INDEX IF NOT EXISTS ix_cases_numero_processo ON cases (numero_processo)",
            "CREATE INDEX IF NOT EXISTS ix_prazos_org_status_venc ON prazos_processuais (org_id, status, data_vencimento)",
            "CREATE INDEX IF NOT EXISTS ix_appointments_org_date ON appointments (org_id, date)",
            # channel_id is the primary lookup key the webhook validates against;
            # it must be globally unique (Google routes by it). The org+account
            # index supports stop_watch/re-registration housekeeping.
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_gcal_watch_channel_id ON gcal_watch_channels (channel_id)",
            "CREATE INDEX IF NOT EXISTS ix_gcal_watch_org_account ON gcal_watch_channels (org_id, account_name)",
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_org_ai_policies_org_feature ON org_ai_policies (org_id, feature)",
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_org_ai_provider_credentials_org_provider ON org_ai_provider_credentials (org_id, provider)",
            "CREATE INDEX IF NOT EXISTS ix_maestro_inferences_org_created ON maestro_inferences (org_id, created_at)",
            "CREATE INDEX IF NOT EXISTS ix_kanban_columns_org_position ON kanban_columns (org_id, position)",
            "CREATE INDEX IF NOT EXISTS ix_kanban_columns_owner_visibility ON kanban_columns (org_id, owner_user_id, visibility)",
            "CREATE INDEX IF NOT EXISTS ix_task_kanban_placements_column ON task_kanban_placements (org_id, user_id, column_id, position)",
            "CREATE INDEX IF NOT EXISTS idx_task_assignees_user ON task_assignees (user_id)",
            "CREATE INDEX IF NOT EXISTS idx_task_assignees_task ON task_assignees (task_id)",
            "INSERT INTO task_assignees (task_id, user_id) SELECT id, assigned_to FROM tasks WHERE assigned_to IS NOT NULL ON CONFLICT DO NOTHING",
            "CREATE INDEX IF NOT EXISTS ix_users_onboarding_completed_at ON users (onboarding_completed_at)",
            "CREATE INDEX IF NOT EXISTS ix_users_email_verified_at ON users (email_verified_at)",
            "CREATE INDEX IF NOT EXISTS ix_users_last_activity ON users (last_activity)",
            "CREATE INDEX IF NOT EXISTS ix_organizations_created_via ON organizations (created_via)",
            "CREATE INDEX IF NOT EXISTS ix_email_verifications_token ON email_verifications (token)",
            "CREATE INDEX IF NOT EXISTS ix_email_verifications_user_id ON email_verifications (user_id)",
            "CREATE INDEX IF NOT EXISTS ix_email_verifications_expires_at ON email_verifications (expires_at)",
            "CREATE INDEX IF NOT EXISTS ix_signup_audit_log_email ON signup_audit_log (email)",
            "CREATE INDEX IF NOT EXISTS ix_signup_audit_log_slug ON signup_audit_log (slug)",
            "CREATE INDEX IF NOT EXISTS ix_signup_audit_log_created_at ON signup_audit_log (created_at)",
            "CREATE INDEX IF NOT EXISTS idx_ew_event ON entity_webhooks (event_type, entity_type)",
            "CREATE INDEX IF NOT EXISTS idx_ew_org_id ON entity_webhooks (org_id)",
            "CREATE INDEX IF NOT EXISTS idx_wl_webhook ON webhook_logs (webhook_id)",
            "CREATE INDEX IF NOT EXISTS ix_audit_log_org_created ON audit_log (org_id, created_at)",
            "CREATE INDEX IF NOT EXISTS ix_audit_log_entity ON audit_log (entity_type, entity_id)",
            "CREATE INDEX IF NOT EXISTS ix_audit_log_user ON audit_log (user_id)",
            "CREATE INDEX IF NOT EXISTS ix_audit_log_action ON audit_log (action)",
            "CREATE INDEX IF NOT EXISTS ix_wi_events_org_occurred ON work_intelligence_events (org_id, occurred_at)",
            "CREATE INDEX IF NOT EXISTS ix_wi_events_org_type ON work_intelligence_events (org_id, event_type)",
            "CREATE INDEX IF NOT EXISTS ix_wi_events_org_user ON work_intelligence_events (org_id, user_id)",
            "CREATE INDEX IF NOT EXISTS ix_wi_daily_org_date ON work_intelligence_daily_metrics (org_id, metric_date)",
            "CREATE INDEX IF NOT EXISTS ix_wi_insights_org_date ON work_intelligence_insights (org_id, insight_date)",
            "CREATE INDEX IF NOT EXISTS ix_wi_feedback_org_insight ON work_intelligence_feedback (org_id, insight_id)",
            "CREATE INDEX IF NOT EXISTS ix_case_processes_org_name ON case_processes (org_id, name)",
            "CREATE INDEX IF NOT EXISTS ix_process_steps_process_order ON process_steps (process_id, step_number)",
            "CREATE INDEX IF NOT EXISTS ix_case_process_tracking_case ON case_process_tracking (case_id)",
            "CREATE INDEX IF NOT EXISTS ix_case_step_progress_case ON case_step_progress (case_id)",
            "CREATE INDEX IF NOT EXISTS ix_case_movements_org_case_data ON case_movements (org_id, case_id, data DESC, id DESC)",
            # whatsapp_messages: composite index for the legacy WhatsApp dashboard
            # top-N query (WHERE org_id=? ORDER BY created_at DESC LIMIT 10). The
            # single-column (org_id) index alone still forces a sort of every org
            # row; the composite lets the ORDER BY ... LIMIT read straight off it.
            "CREATE INDEX IF NOT EXISTS ix_whatsapp_messages_org_created ON whatsapp_messages (org_id, created_at)",
        ]
        for stmt in stmts:
            try:
                db.execute(text(stmt))
            except Exception as e:
                logger.debug("Migration statement skipped: %s", e)
                db.rollback()
                continue
        db.commit()
        logger.info("Pending migrations applied successfully")
    except Exception as e:
        logger.warning("Migration error: %s", e)
        db.rollback()
    finally:
        db.close()


STARTUP_DB_BOOTSTRAP_RETRY_SECONDS = 5
STARTUP_DB_BOOTSTRAP_MAX_RETRY_SECONDS = 60


def _bootstrap_default_admin() -> None:
    db = None
    try:
        db = SessionLocal()
        admin = db.query(User).filter(User.email == settings.ADMIN_EMAIL).first()
        if not admin:
            temp_password = secrets.token_urlsafe(16)
            admin = User(
                email=settings.ADMIN_EMAIL,
                name="Administrator",
                password_hash=User.hash_password(temp_password),
                user_type="admin",
                must_change_password=True,
            )
            db.add(admin)
            db.commit()
            logger.info(
                "Default admin user created: %s / %s (must change on first login)",
                settings.ADMIN_EMAIL,
                temp_password,
            )
    except Exception:
        if db is not None:
            db.rollback()
        raise
    finally:
        if db is not None:
            db.close()


def _run_startup_db_bootstrap() -> bool:
    """Run the DB-dependent boot work once, returning False instead of crashing."""
    try:
        init_db()
        _run_pending_migrations()
        _bootstrap_default_admin()
    except Exception as exc:
        logger.critical(
            "Startup DB bootstrap incomplete: database unavailable at boot "
            "(%s). App starts DEGRADED; /casehub/healthz returns 503 until the "
            "DB is reachable. Scheduling retry instead of crashing into a 502 "
            "loop.",
            exc,
        )
        return False
    return True


async def _retry_startup_db_bootstrap() -> None:
    delay = STARTUP_DB_BOOTSTRAP_RETRY_SECONDS
    attempt = 1
    while True:
        await asyncio.sleep(delay)
        if _run_startup_db_bootstrap():
            logger.info("Startup DB bootstrap recovered after %s retry attempt(s)", attempt)
            return
        attempt += 1
        delay = min(delay * 2, STARTUP_DB_BOOTSTRAP_MAX_RETRY_SECONDS)


# ---------------------------------------------------------------------------
# The factory
# ---------------------------------------------------------------------------
def _preflight_check() -> None:
    """Fail-fast no startup se dependencias criticas faltarem.

    Resolve casehub#299 A3: prod 2026-05-09 servia HTML referenciando
    /static/brand-kit/tokens.css que retornava 404. HMAC keys ausentes
    em prod silenciosamente quebram improvement-tasks/ops endpoints.

    Levanta RuntimeError com mensagem acionavel — startup falha audivelmente
    em vez de degradar em runtime com 500/404.
    """
    errors = []

    # 1. brand-kit tokens.css obrigatorio (referenciado por templates/partials/head_css.html)
    if not _static_asset_file_exists("brand-kit/tokens.css"):
        errors.append(
            "static asset ausente: asset_url('brand-kit/tokens.css') nao resolve "
            "para arquivo existente em static/. Verifique se o deploy levou "
            "static/brand-kit/ completo e, se houver cache-bust, o arquivo do "
            "manifest tambem existe."
        )

    # 2. HMAC key obrigatoria somente quando o receiver estiver ativo.
    is_demo = bool(getattr(settings, "DEMO_MODE", False))
    env_name = _explicit_casehub_env() or "production-assumed"
    if (
        not is_demo
        and not _is_explicit_dev_env()
        and _improvement_tasks_enabled()
        and not _accepted_improvement_hmac_key()
    ):
        errors.append(
            "CASEHUB_IMPROVEMENT_TASKS_ENABLED=1 mas nenhuma chave HMAC aceita "
            "(CASEHUB_IMPROVEMENT_HMAC_KEY ou CASEHUB_OPS_HMAC_KEY) foi configurada."
        )

    if errors:
        for err in errors:
            logger.error("[preflight] %s", err)
        raise RuntimeError(
            "CaseHub preflight failed (%d error%s). Veja logs acima." % (
                len(errors), "" if len(errors) == 1 else "s",
            )
        )

    logger.info("[preflight] OK — brand-kit/tokens.css present, HMAC gate consistent (env=%s)",
                env_name or "prod")


def create_app(product: str = "immigration") -> FastAPI:
    """
    Create a fully configured CaseHub FastAPI application.

    Args:
        product: One of "immigration", "lite". Determines which routers
                 are mounted. Defaults to "immigration" (full feature set).

    Returns:
        A ready-to-serve FastAPI instance.
    """
    if product not in PRODUCT_ROUTERS:
        raise ValueError(f"Unknown product '{product}'. Available: {list(PRODUCT_ROUTERS.keys())}")

    _preflight_check()

    app = FastAPI(
        title=f"{settings.ORG_NAME} CaseHub",
        description=f"{settings.ORG_NAME} Case Management System ({product})",
        version="0.9.12-alpha",
        docs_url=None if settings.DEMO_MODE else "/docs",
        redoc_url=None if settings.DEMO_MODE else "/redoc",
        openapi_url=None if settings.DEMO_MODE else "/openapi.json",
    )

    # Store product type and defaults on app state
    app.state.product = product
    app.state.product_defaults = get_product_defaults(product)

    # ------------------------------------------------------------------
    # Middleware (order matters: last added = first executed)
    # ------------------------------------------------------------------
    app.add_middleware(SecurityHeadersMiddleware)

    from middleware.tenant import TenantMiddleware
    app.add_middleware(TenantMiddleware)

    from middleware.plan_enforcement import PlanEnforcementMiddleware
    app.add_middleware(PlanEnforcementMiddleware)

    from middleware.rate_limit import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware)

    app.add_middleware(AuditContextMiddleware)

    # Demo guard — must be first executed (last added) to block before anything else
    if settings.DEMO_MODE:
        from middleware.demo_guard import DemoGuardMiddleware
        app.add_middleware(DemoGuardMiddleware)
        logger.info("DEMO_MODE enabled — destructive/external actions blocked")

    # ------------------------------------------------------------------
    # Static files & templates
    # ------------------------------------------------------------------
    app.mount("/static", StaticFiles(directory="static"), name="static")
    # Sentinela T11 fix: /uploads is no longer a public StaticFiles mount.
    # It is now served by routes/uploads.py with auth + per-tenant guards.
    # The router is registered below (after middleware) at the apex so URLs
    # stay /uploads/<kind>/<filename> for backward compatibility with the
    # previously-public layout.
    templates = Jinja2Templates(directory="templates")
    configure_jinja_templates(templates)
    templates.env.globals["PREFIX"] = PREFIX
    templates.env.globals["now"] = lambda: date.today()
    templates.env.globals["product"] = product
    templates.env.globals["internal_tools_enabled"] = INTERNAL_TOOLS_ENABLED
    defaults = get_product_defaults(product)
    templates.env.globals["currency"] = defaults["currency"]
    templates.env.globals["currency_symbol"] = defaults["currency_symbol"]
    templates.env.globals["date_format"] = defaults["date_format"]
    templates.env.globals["product_features"] = defaults["features"]
    templates.env.globals["demo_mode"] = settings.DEMO_MODE
    templates.env.globals["asset_url"] = asset_url
    templates.env.globals["brand_kit_fallback_favicon_url"] = brand_kit_fallback_favicon_url()
    templates.env.globals["casehub_release_notice"] = get_casehub_release_notice()
    templates.env.globals["casehub_maestro_fab_enabled"] = settings.CASEHUB_MAESTRO_FAB_ENABLED

    # LegalOps Co. public contact info — used by landing + login templates.
    # Override at runtime via env if any of these change without re-deploy.
    templates.env.globals["LEGALOPS_CNPJ"] = os.getenv("LEGALOPS_CNPJ", "")
    templates.env.globals["LEGALOPS_EMAIL"] = os.getenv("LEGALOPS_EMAIL", "casehub@legalopsco.work")
    templates.env.globals["LEGALOPS_WHATSAPP"] = os.getenv("LEGALOPS_WHATSAPP", "")
    templates.env.globals["LEGALOPS_WHATSAPP_DIGITS"] = os.getenv("LEGALOPS_WHATSAPP_DIGITS", "")
    templates.env.globals["LEGALOPS_LOCATION"] = os.getenv("LEGALOPS_LOCATION", "")

    # Translation function as a global (so templates don't depend on each route passing it)
    def _jinja_t():
        """Return translation dict; re-evaluated per-render via Jinja2 call."""
        return get_translations(defaults["default_lang"])
    templates.env.globals["t"] = _jinja_t()

    # Jinja2 custom filters
    def format_currency(value, currency=None):
        if currency is None:
            currency = defaults["currency"]
        symbols = {"USD": "$", "BRL": "R$", "EUR": "€", "GBP": "£"}
        symbol = symbols.get(currency, currency)
        try:
            val = float(value or 0)
            if currency == "BRL":
                return f"{symbol} {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return f"{symbol}{val:,.2f}"
        except (ValueError, TypeError):
            return f"{symbol} 0.00"

    templates.env.filters["format_currency"] = format_currency

    # ------------------------------------------------------------------
    # Startup event
    # ------------------------------------------------------------------
    @app.on_event("startup")
    async def startup():
        _run_preflight_checks()
        db_bootstrap_ok = _run_startup_db_bootstrap()

        # Register automatic audit listeners on all SQLAlchemy models
        try:
            from services.audit import setup_audit_listeners
            setup_audit_listeners(Base)
        except Exception as e:
            logger.warning("Audit listeners setup failed (non-critical): %s", e)

        if not db_bootstrap_ok:
            asyncio.create_task(_retry_startup_db_bootstrap())

        # Start surveillance background worker
        try:
            from services.lead_surveillance import surveillance_loop
            asyncio.create_task(surveillance_loop())
            logger.info("Lead surveillance worker started")
        except Exception as e:
            logger.error("Surveillance worker failed to start: %s", e)

        # Maestro Sentinel: dispara run_sentinel_all_orgs uma vez por dia às 08:00 BRT (11:00 UTC)
        if os.getenv("MAESTRO_SENTINEL_ENABLED", "1").lower() not in {"0", "false", "no", "off"}:
            try:
                import asyncio as _aio
                from datetime import datetime as _dt, timezone as _tz, timedelta as _td
                from services.maestro_sentinel import run_sentinel_all_orgs as _sentinel

                async def _sentinel_daily():
                    loop = _aio.get_event_loop()
                    while True:
                        try:
                            now = _dt.now(_tz.utc)
                            target = now.replace(hour=11, minute=0, second=0, microsecond=0)
                            if now >= target:
                                target += _td(days=1)
                            await _aio.sleep((target - now).total_seconds())
                            await loop.run_in_executor(None, _sentinel)
                        except _aio.CancelledError:
                            break
                        except Exception as _e:
                            logger.warning("sentinel daily: erro (%s) — aguarda 1h", _e)
                            await _aio.sleep(3600)

                asyncio.create_task(_sentinel_daily())
                logger.info("Maestro Sentinel agendado (08:00 BRT / 11:00 UTC diário)")
            except Exception as _se:
                logger.warning("Maestro Sentinel falhou ao inicializar: %s", _se)

        # Notion cache warm
        if os.getenv("NOTION_TOKEN"):
            try:
                from services.notion_tasks import notion_tasks_service
                notion_tasks_service.get_all_tasks(use_cache=False)
                logger.info("Notion tasks cache warmed on startup")
            except Exception as e:
                logger.warning("Notion cache warm failed (non-critical): %s", e)
        else:
            logger.info("Notion integration skipped (no NOTION_TOKEN)")

        logger.info("CaseHub started with product: %s", product)

    @app.on_event("shutdown")
    async def shutdown():
        # Release the pooled httpx clients (WhatsApp bot bridge + PDPJ /
        # ComunicaAPI) so their keep-alive connections close cleanly.
        try:
            from services.whatsapp_bot_client import aclose_bot_client
            await aclose_bot_client()
        except Exception as e:
            logger.warning("WhatsApp bot client shutdown failed (non-critical): %s", e)
        try:
            from services.pdpj_client import aclose_pdpj_client
            await aclose_pdpj_client()
        except Exception as e:
            logger.warning("PDPJ client shutdown failed (non-critical): %s", e)

    # ------------------------------------------------------------------
    # Core routes (login, logout, dashboard, set-language, root redirect)
    # ------------------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request, db: Session = Depends(get_db)):
        # Public landing — renders for anyone hitting casehub.legal/ (not authenticated).
        # Authenticated users skip the marketing page and go straight to the product.
        # O root NUNCA pode ser cacheado: browsers mobile cacheavam a landing 200
        # de antes do redirect e a serviam do disco sem rebater no servidor, então
        # o redirect tenant→login "não acontecia" no celular. no-store força
        # revalidação em toda navegação e faz o cache stale se auto-curar.
        _no_store = "no-store, no-cache, must-revalidate, max-age=0"
        user = get_current_user(request, db)
        if user:
            _r = RedirectResponse(url=f"{PREFIX}/dashboard", status_code=302)
            _r.headers["Cache-Control"] = _no_store
            return _r
        # Tenant subdomains are login portals, not
        # marketing pages — redirect unauthenticated users directly to the login page.
        _org = getattr(request.state, "org", None)
        _org_slug = (_org.get("slug") if isinstance(_org, dict) else getattr(_org, "slug", "")) or ""
        if _org_slug and _org_slug != "default":
            _r = RedirectResponse(url=f"{PREFIX}/login", status_code=302)
            _r.headers["Cache-Control"] = _no_store
            return _r
        _resp = templates.TemplateResponse("landing.html", get_context(request))
        _resp.headers["Cache-Control"] = _no_store
        return _resp

    @app.get(PREFIX, response_class=HTMLResponse, include_in_schema=False)
    @app.get(f"{PREFIX}/", response_class=HTMLResponse, include_in_schema=False)
    async def casehub_root(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
        return RedirectResponse(url=f"{PREFIX}/dashboard", status_code=302)

    @app.get(f"{PREFIX}/maestro", include_in_schema=False)
    @app.get(f"{PREFIX}/maestro/", include_in_schema=False)
    async def maestro_legacy_redirect():
        """Legacy alias — nav top mostra 'Maestro' mas rota canônica é /assistente."""
        return RedirectResponse(url=f"{PREFIX}/assistente", status_code=301)

    @app.get(f"{PREFIX}/legal/privacy", response_class=HTMLResponse, include_in_schema=False)
    @app.get(f"{PREFIX}/legal/privacy/", response_class=HTMLResponse, include_in_schema=False)
    async def legal_privacy_page(request: Request):
        """LGPD privacy policy — referenced by Connect/Disconnect LGPD disclosures."""
        return templates.TemplateResponse("legal/privacy.html", get_context(request))

    # ------------------------------------------------------------------
    # Apex-level public legal pages (NO PREFIX) — Google OAuth consent-screen
    # verification (#786 / T13) probes the bare https://<host>/privacy and
    # /terms URLs and is smoother when they answer HTTP 200 *directly* (no
    # 301/302 redirect). The `routes/legal.py` router is mounted under PREFIX,
    # so its /privacy lands at /casehub/privacy and the bare paths 404'd. These
    # apex aliases serve the same templates 200-direct. The /static/legal/*.html
    # files and the StaticFiles mount stay intact (unchanged).
    @app.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
    @app.get("/privacy/", response_class=HTMLResponse, include_in_schema=False)
    @app.get("/privacy-policy", response_class=HTMLResponse, include_in_schema=False)
    @app.get("/politica-de-privacidade", response_class=HTMLResponse, include_in_schema=False)
    async def public_privacy_page(request: Request):
        """Public privacy policy — 200-direct for Google OAuth verification (#786)."""
        return templates.TemplateResponse("legal/privacy.html", get_context(request))

    @app.get("/terms", response_class=HTMLResponse, include_in_schema=False)
    @app.get("/terms/", response_class=HTMLResponse, include_in_schema=False)
    @app.get("/termos", response_class=HTMLResponse, include_in_schema=False)
    async def public_terms_page(request: Request):
        """Public terms of service — 200-direct for Google OAuth verification (#786)."""
        return templates.TemplateResponse("legal/terms.html", get_context(request))

    @app.get(f"{PREFIX}/kanban", include_in_schema=False)
    @app.get(f"{PREFIX}/kanban/", include_in_schema=False)
    async def kanban_legacy_alias():
        """Legacy alias — kanban canônico é /tasks/kanban."""
        return RedirectResponse(url=f"{PREFIX}/tasks/kanban", status_code=301)

    @app.get(f"{PREFIX}/billing-dashboard", include_in_schema=False)
    @app.get(f"{PREFIX}/billing-dashboard/", include_in_schema=False)
    async def billing_dashboard_legacy_alias():
        """Legacy alias — billing canônico é /billing."""
        return RedirectResponse(url=f"{PREFIX}/billing", status_code=301)

    @app.get(f"{PREFIX}/set-language/{{lang}}")
    async def set_language(lang: str, request: Request):
        if lang not in TRANSLATIONS:
            lang = DEFAULT_LANG
        referer = request.headers.get("referer", f"{PREFIX}/dashboard")
        response = RedirectResponse(url=referer, status_code=302)
        response.set_cookie(key="lang", value=lang, max_age=365 * 24 * 3600, path="/")
        return response

    @app.get(f"{PREFIX}/showcase", response_class=HTMLResponse)
    async def showcase_page(request: Request):
        """Read-only login preview for embedding on a public marketing site."""
        ctx = get_context(request)
        ctx["showcase"] = True
        ctx["product"] = "lite"
        ctx["org_name"] = "CaseHub"
        ctx["org_slug"] = "showcase"
        ctx["org_settings"] = {}
        resp = templates.TemplateResponse("login.html", ctx)
        # Allow iframe only from the current origin by default.
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
            "connect-src 'self' https://cdn.jsdelivr.net; "
            "frame-ancestors 'self'"
        )
        if "X-Frame-Options" in resp.headers:
            del resp.headers["X-Frame-Options"]
        return resp

    @app.get(f"{PREFIX}/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        return templates.TemplateResponse("login.html", get_context(request))

    @app.post(f"{PREFIX}/login")
    async def login(
        request: Request,
        email: str = Form(...),
        password: str = Form(...),
        db: Session = Depends(get_db),
    ):
        client_ip = request.client.host if request.client else "unknown"

        if login_limiter.is_locked(client_ip):
            remaining = login_limiter.remaining_lockout(client_ip)
            minutes = max(1, remaining // 60)
            return templates.TemplateResponse("login.html", {
                **get_context(request),
                "error": f"Too many failed attempts. Try again in {minutes} minute{'s' if minutes != 1 else ''}."
            })

        # Login searches ALL orgs by email (not tenant-scoped) so users from any org can login
        user = db.query(User).filter(User.email == email, User.enabled == True).first()
        if not user or not user.verify_password(password):
            locked = login_limiter.record_attempt(client_ip)
            error_msg = "Invalid email or password"
            if locked:
                error_msg = "Too many failed attempts. Account locked for 15 minutes."
            return templates.TemplateResponse("login.html", {
                **get_context(request),
                "error": error_msg
            })

        if not user.enabled:
            return templates.TemplateResponse("login.html", {
                **get_context(request),
                "error": "Account disabled"
            })

        login_limiter.reset(client_ip)
        access_token = create_access_token(data={"sub": user.email, "org_id": user.org_id})
        refresh_token = create_refresh_token(data={"sub": user.email, "org_id": user.org_id})

        # Redirect to first-login wizard if user hasn't completed onboarding
        redirect_url = f"{PREFIX}/first-login" if getattr(user, 'must_change_password', False) else f"{PREFIX}/dashboard"
        response = RedirectResponse(url=redirect_url, status_code=302)
        response.set_cookie(
            key="casehub_token",
            value=access_token,
            httponly=True,
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            path="/",
            samesite="lax",
        )
        response.set_cookie(
            key="casehub_refresh",
            value=refresh_token,
            httponly=True,
            max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
            path="/",
            samesite="lax",
        )
        return response

    @app.get(f"{PREFIX}/logout")
    async def logout():
        response = RedirectResponse(url=f"{PREFIX}/login", status_code=302)
        response.delete_cookie("casehub_token", path="/")
        response.delete_cookie("casehub_refresh", path="/")
        return response

    @app.post(f"{PREFIX}/change-password")
    async def change_password(
        request: Request,
        new_password: str = Form(...),
        db: Session = Depends(get_db),
    ):
        user = get_current_user(request, db)
        if not user:
            return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
        user.password_hash = User.hash_password(new_password)
        user.must_change_password = False
        db.commit()
        return RedirectResponse(url=f"{PREFIX}/dashboard", status_code=302)

    @app.get(f"{PREFIX}/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request, db: Session = Depends(get_db)):
        """Canonical /dashboard renders the new UI Remake template (Wave 2 swap).
        Legacy templates dashboard_modular.html and dashboard.html preserved at
        /casehub/dashboard/legacy for fallback during stabilization."""
        user = get_current_user(request, db)
        if not user:
            return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
        today = date.today()
        org_id = getattr(request.state, "org_id", None)
        dashboard_context = get_basic_dashboard_context(
            db=db, org_id=org_id, user_id=user.id, today=today, user=user,
        )
        ctx = {
            **get_context(request, db, user=user),
            "user": user, "today": today, "now": datetime.now(),
            **dashboard_context,
        }
        return templates.TemplateResponse("app/dashboard.html", ctx)

    @app.get(f"{PREFIX}/dashboard/legacy", response_class=HTMLResponse)
    async def dashboard_legacy(request: Request, db: Session = Depends(get_db)):
        """Fallback to legacy dashboard during Wave 2 stabilization."""
        user = get_current_user(request, db)
        if not user:
            return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
        today = date.today()
        org_id = getattr(request.state, "org_id", None)
        use_basic_dashboard = product == "lite" or org_id == 42
        template_name = "dashboard_modular.html" if use_basic_dashboard else "dashboard.html"
        if use_basic_dashboard:
            variant = "|".join([
                f"lang={get_lang(request)}",
                f"theme={getattr(user, 'ui_theme', '') or 'default'}",
                f"desktop_frame={request.query_params.get('desktop_frame', '0')}",
            ])
            def render_dashboard_html() -> str:
                dashboard_context = get_basic_dashboard_context(
                    db=db, org_id=org_id, user_id=user.id, today=today, user=user,
                )
                context = {
                    **get_context(request, db, user=user),
                    "user": user, "today": today, "now": datetime.now(),
                    **dashboard_context,
                }
                return templates.env.get_template(template_name).render(context)
            html = cached_basic_dashboard_html(
                org_id=org_id, user_id=user.id, today=today,
                variant=variant, renderer=render_dashboard_html,
            )
            return HTMLResponse(html)
        dashboard_context = get_legacy_dashboard_context(
            db=db, org_id=request.state.org_id, user_id=user.id,
            today=today, product=product, user=user,
        )
        return templates.TemplateResponse(template_name, {
            **get_context(request, db, user=user),
            "user": user, "today": today, "now": datetime.now(),
            **dashboard_context,
        })

    # ------------------------------------------------------------------
    # UI Remake 2026-05-23 — Ondas 1+2+3
    # Parallel /casehub/v2/* surfaces. Reuses existing helpers/contexts;
    # legacy routes untouched.
    # ------------------------------------------------------------------
    # /v2/dashboard → 301 redirect to canonical (Wave 3 swap)
    # ─── Wave 2: Canonical handlers for module list views ───
    # Registered BEFORE app.include_router(...) loop (line ~1772);
    # FastAPI first-match-wins means these override the legacy
    # router's list/index routes. Sub-paths like /clients/{id}/edit
    # continue to work via the legacy router include.

    @app.get(f"{PREFIX}/clients", response_class=HTMLResponse)
    async def clients_canonical(
        request: Request,
        search: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        db: Session = Depends(get_db),
    ):
        from sqlalchemy import or_ as _or
        from models import Client as _Client
        from models.tenant import tenant_query as _tenant_query
        user = get_current_user(request, db)
        if not user:
            return RedirectResponse(url=f"{PREFIX}/login?next={PREFIX}/clients", status_code=302)
        query = _tenant_query(db, _Client, request.state.org_id)
        if search:
            f = f"%{search}%"
            query = query.filter(_or(
                _Client.first_name.ilike(f), _Client.last_name.ilike(f),
                _Client.email.ilike(f), _Client.client_number.ilike(f),
            ))
        if status:
            query = query.filter(_Client.status == status)
        total = query.count()
        per_page = 20
        clients = query.order_by(_Client.first_name.asc(), _Client.last_name.asc()).offset((page - 1) * per_page).limit(per_page).all()
        return templates.TemplateResponse("app/clients/list.html", {
            **get_context(request, db, user=user),
            "user": user, "today": date.today(),
            "clients": clients, "total": total, "page": page, "per_page": per_page,
            "search": search or "", "status": status or "",
        })

    @app.get(f"{PREFIX}/cases", response_class=HTMLResponse)
    async def cases_canonical(
        request: Request,
        search: Optional[str] = None,
        status: Optional[str] = None,
        visa_type: Optional[str] = None,
        page: int = 1,
        db: Session = Depends(get_db),
    ):
        from sqlalchemy import or_ as _or
        from models import Case as _Case
        from models.tenant import tenant_query as _tenant_query
        user = get_current_user(request, db)
        if not user:
            return RedirectResponse(url=f"{PREFIX}/login?next={PREFIX}/cases", status_code=302)
        query = _tenant_query(db, _Case, request.state.org_id)
        if search:
            f = f"%{search}%"
            query = query.filter(_or(
                _Case.case_number.ilike(f), _Case.case_name.ilike(f),
                _Case.receipt_number.ilike(f),
            ))
        if status:
            query = query.filter(_Case.status == status)
        if visa_type:
            query = query.filter(_Case.visa_type == visa_type)
        total = query.count()
        per_page = 20
        cases = query.order_by(_Case.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
        return templates.TemplateResponse("app/cases/list.html", {
            **get_context(request, db, user=user),
            "user": user, "today": date.today(),
            "cases": cases, "total": total, "page": page, "per_page": per_page,
            "search": search or "", "status": status or "", "visa_type": visa_type or "",
        })

    @app.get(f"{PREFIX}/tasks/kanban", response_class=HTMLResponse)
    async def tasks_kanban_canonical(request: Request, db: Session = Depends(get_db)):
        from routes.tasks import kanban_view as _kanban_view
        user = get_current_user(request, db)
        if not user:
            return RedirectResponse(url=f"{PREFIX}/login?next={PREFIX}/tasks/kanban", status_code=302)
        legacy = await _kanban_view(request=request, db=db)
        ctx = getattr(legacy, "context", None) or {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        return templates.TemplateResponse("app/tasks/kanban.html", ctx)

    @app.get(f"{PREFIX}/controladoria", response_class=HTMLResponse)
    async def controladoria_canonical(
        request: Request,
        search: str = "",
        status: str = "",
        mes: str = "",
        tribunal: str = "",
        db: Session = Depends(get_db),
    ):
        from routes.controladoria import controladoria_dashboard as _ctrl_view
        user = get_current_user(request, db)
        if not user:
            return RedirectResponse(url=f"{PREFIX}/login?next={PREFIX}/controladoria", status_code=302)
        legacy = await _ctrl_view(
            request=request, search=search, status=status, mes=mes, tribunal=tribunal, db=db,
        )
        ctx = getattr(legacy, "context", None) or {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        return templates.TemplateResponse("app/controladoria/dashboard.html", ctx)

    @app.get(f"{PREFIX}/calendar", response_class=HTMLResponse)
    async def calendar_canonical(request: Request, db: Session = Depends(get_db)):
        # 03/06 (UsuarioDemo/Equipe CaseHub): a tela canônica da aba Agenda é /calendar/agenda
        # (lista + calendário logo abaixo, com seletor de visualização Lista+Calendário /
        # Só lista / Só calendário). Este handler prevalece sobre routes/calendar.py, então
        # o redirect TEM que estar aqui: qualquer hit em /calendar (aba antiga persistida,
        # bookmark, ?view=) cai em /calendar/agenda preservando a query string.
        user = get_current_user(request, db)
        if not user:
            return RedirectResponse(url=f"{PREFIX}/login?next={PREFIX}/calendar/agenda", status_code=302)
        q = request.url.query
        target = f"{PREFIX}/calendar/agenda" + (f"?{q}" if q else "")
        return RedirectResponse(url=target, status_code=302)

    @app.get(f"{PREFIX}/billing", response_class=HTMLResponse)
    async def billing_canonical(request: Request, db: Session = Depends(get_db)):
        from routes.billing import billing_dashboard as _billing_view
        user = get_current_user(request, db)
        if not user:
            return RedirectResponse(url=f"{PREFIX}/login?next={PREFIX}/billing", status_code=302)
        legacy = await _billing_view(request=request, case_id=None, status=None, db=db)
        ctx = getattr(legacy, "context", None) or {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        return templates.TemplateResponse("app/billing/list.html", ctx)

    @app.get(f"{PREFIX}/documents", response_class=HTMLResponse)
    async def documents_canonical(
        request: Request,
        search: Optional[str] = None,
        doc_type: Optional[str] = None,
        db: Session = Depends(get_db),
    ):
        from routes.documents import list_documents as _docs_view
        user = get_current_user(request, db)
        if not user:
            return RedirectResponse(url=f"{PREFIX}/login?next={PREFIX}/documents", status_code=302)
        legacy = await _docs_view(
            request=request, search=search, doc_type=doc_type, status=None, page=1, per_page=50, db=db,
        )
        ctx = getattr(legacy, "context", None) or {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        return templates.TemplateResponse("app/documents/list.html", ctx)

    @app.get(f"{PREFIX}/drive", response_class=HTMLResponse)
    @app.get(f"{PREFIX}/drive/", response_class=HTMLResponse)
    async def drive_legacy_alias(request: Request):
        # 15/06 alpha feedback: users refer to the module as "Drive"; keep the
        # old/direct URL alive while the canonical app surface remains
        # /documents.
        q = request.url.query
        target = f"{PREFIX}/documents" + (f"?{q}" if q else "")
        return RedirectResponse(url=target, status_code=302)

    @app.get(f"{PREFIX}/signup", response_class=HTMLResponse)
    async def signup_canonical(request: Request):
        return templates.TemplateResponse("app/signup/form.html", {
            "request": request, "PREFIX": PREFIX,
        })

    @app.get(f"{PREFIX}/settings", response_class=HTMLResponse)
    async def settings_canonical(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return RedirectResponse(url=f"{PREFIX}/login?next={PREFIX}/settings", status_code=302)
        return templates.TemplateResponse("app/settings/index.html", {
            **get_context(request, db, user=user),
            "user": user, "today": date.today(),
        })

    @app.get(f"{PREFIX}/profile", response_class=HTMLResponse)
    async def profile_canonical(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return RedirectResponse(url=f"{PREFIX}/login?next={PREFIX}/profile", status_code=302)
        return templates.TemplateResponse("app/profile/index.html", {
            **get_context(request, db, user=user),
            "user": user, "today": date.today(),
        })

    # ─── Wave 2 expansion: register ALL canonical sub-route handlers ───
    # External module to keep app_factory readable. Registers ~45 handlers
    # for clients/cases/tasks/invoices/billing/documents/doc-templates/admin/
    # 2fa/integrations/subscription/settings/calendar/bulk/ilc-tools/tools/
    # questionnaires/letters/uscis/emails/whatsapp/onboarding sub-paths.
    from core.v2_canonical_routes import register_canonical_routes as _reg_canonical
    _reg_canonical(app, templates, get_context, PREFIX)

    # ─── Wave 5: CaseHub.md módulo próprio + tab primária ───
    @app.get(f"{PREFIX}/md", response_class=HTMLResponse)
    async def md_list_canonical(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return RedirectResponse(url=f"{PREFIX}/login?next={PREFIX}/md", status_code=302)
        # Template app/md/index.html não existe — módulo ainda não enviado.
        # Short-circuit para o dashboard evita 500 (TemplateNotFound).
        return RedirectResponse(url=f"{PREFIX}/dashboard", status_code=302)

    @app.get(f"{PREFIX}/md/new", response_class=HTMLResponse)
    async def md_new_canonical(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return RedirectResponse(url=f"{PREFIX}/login?next={PREFIX}/md/new", status_code=302)
        # Template app/md/editor.html não existe — short-circuit p/ dashboard.
        return RedirectResponse(url=f"{PREFIX}/dashboard", status_code=302)

    @app.get(f"{PREFIX}/md/{{doc_id}}", response_class=HTMLResponse)
    async def md_detail_canonical(doc_id: str, request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
        # Template app/md/editor.html não existe — short-circuit p/ dashboard.
        return RedirectResponse(url=f"{PREFIX}/dashboard", status_code=302)


    @app.post("/api/v1/auth/login")
    async def api_login(
        request: Request,
        email: str = Form(...),
        password: str = Form(...),
        db: Session = Depends(get_db),
    ):
        """API login endpoint - returns JWT token"""
        client_ip = request.client.host if request.client else "unknown"

        if login_limiter.is_locked(client_ip):
            remaining = login_limiter.remaining_lockout(client_ip)
            raise HTTPException(
                status_code=429,
                detail=f"Too many failed attempts. Try again in {remaining} seconds.",
            )

        # Login searches ALL orgs by email (API endpoint)
        user = db.query(User).filter(User.email == email, User.enabled == True).first()
        if not user or not user.verify_password(password):
            login_limiter.record_attempt(client_ip)
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if not user.enabled:
            raise HTTPException(status_code=401, detail="Account disabled")

        login_limiter.reset(client_ip)

        # Sentinela T1: every token must carry org_id so TenantMiddleware can
        # fall back to JWT at the apex and so get_current_user can enforce the
        # tenant binding (user.org_id == request.state.org_id).
        access_token = create_access_token(data={"sub": user.email, "org_id": user.org_id})
        refresh_token = create_refresh_token(data={"sub": user.email, "org_id": user.org_id})
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "user_type": user.user_type,
            },
        }

    @app.post(f"{PREFIX}/auth/refresh")
    async def auth_refresh(request: Request, db: Session = Depends(get_db)):
        """Refresh the access token using a valid refresh token."""
        refresh_token = request.cookies.get("casehub_refresh")

        if not refresh_token:
            try:
                body = await request.json()
                refresh_token = body.get("refresh_token")
            except Exception:
                pass

        if not refresh_token:
            raise HTTPException(status_code=401, detail="No refresh token provided")

        user = validate_refresh_token(refresh_token, db)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

        # Sentinela T1: include org_id when re-issuing access tokens.
        new_access_token = create_access_token(data={"sub": user.email, "org_id": user.org_id})

        response = JSONResponse({
            "access_token": new_access_token,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        })
        response.set_cookie(
            key="casehub_token",
            value=new_access_token,
            httponly=True,
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            path="/",
            samesite="lax",
        )
        return response

    # ------------------------------------------------------------------
    # Feedback & health endpoints
    # ------------------------------------------------------------------
    @app.post("/api/feedback")
    async def submit_feedback(request: Request, db: Session = Depends(get_db)):
        """Submit user feedback - logs and sends to Google Chat webhook"""
        import json
        import httpx

        data = await request.json()
        feedback_type = data.get("type", "other")
        message = data.get("message", "")
        page = data.get("page", "unknown")

        user = get_current_user(request, db)
        user_email = user.email if user else "anonymous"

        feedback_log = {
            "timestamp": datetime.now().isoformat(),
            "user": user_email,
            "type": feedback_type,
            "page": page,
            "message": message,
        }

        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "feedback.jsonl")

        with open(log_file, "a") as f:
            f.write(json.dumps(feedback_log) + "\n")

        GOOGLE_CHAT_WEBHOOK = os.getenv("GOOGLE_CHAT_WEBHOOK_FEEDBACK", "")
        if GOOGLE_CHAT_WEBHOOK:
            try:
                chat_message = {
                    "text": f"*CaseHub Feedback* ({feedback_type})\n\n*User:* {user_email}\n*Page:* {page}\n\n{message}"
                }
                async with httpx.AsyncClient() as client:
                    await client.post(GOOGLE_CHAT_WEBHOOK, json=chat_message, timeout=5)
            except Exception as e:
                logger.error("Failed to send to Google Chat: %s", e)

        return {"success": True, "message": "Feedback received"}

    def _version_commit() -> str:
        return resolve_deploy_commit(os.path.dirname(os.path.dirname(__file__)))

    # Warm the deploy-commit cache once at startup so health checks don't
    # touch disk on the async event loop. Markers are written by the deploy
    # pipeline (see deploy-dev fix in #234) before the app boots.
    _version_commit()

    def _health_payload(include_marker: bool = False) -> tuple[dict, bool]:
        start = time.time()
        checks = {"db": False, "templates": False}
        try:
            db = next(get_db())
            # Cheap connectivity probe — NOT a full-table COUNT(User.id), which
            # blocks the worker proportional to row count on every health hit
            # (incident 2026-06-16 VS 504: worker saturation). SELECT 1 confirms
            # the pool/connection is usable without scanning a table.
            db.execute(text("SELECT 1")).scalar()
            checks["db"] = True
            db.close()
        except Exception as e:
            checks["db_error"] = str(e)[:200]
        try:
            checks["templates"] = os.path.exists("templates/dashboard.html")
        except Exception:
            pass
        elapsed_ms = round((time.time() - start) * 1000, 1)
        all_ok = all(v for k, v in checks.items() if not k.endswith("_error"))
        payload = {
            "status": "healthy" if all_ok else "degraded",
            "service": "casehub",
            "product": product,
            "version": "0.9.12-alpha",
            "commit": _version_commit(),
            "checks": checks,
            "response_ms": elapsed_ms,
        }
        if include_marker:
            payload["marker"] = "casehub-live-v1"
        return payload, all_ok

    @app.get("/api/health")
    async def health_check():
        payload, _ = _health_payload()
        return payload

    @app.get(f"{PREFIX}/healthz")
    async def casehub_healthz():
        payload, all_ok = _health_payload(include_marker=True)
        status_code = 200 if all_ok else 503
        return JSONResponse(payload, status_code=status_code)

    # Goal frente A lists ``/casehub/health`` as one of the canonical
    # healthcheck endpoints — alias to ``/casehub/healthz`` so probes /
    # uptime monitors that follow the goal text don't 404. Same payload,
    # same status semantics; one truth, two URLs.
    @app.get(f"{PREFIX}/health")
    async def casehub_health_alias():
        payload, all_ok = _health_payload(include_marker=True)
        status_code = 200 if all_ok else 503
        return JSONResponse(payload, status_code=status_code)

    # Pure LIVENESS — proves the process + event loop can answer, WITHOUT
    # touching the DB, disk, or any external upstream (Ollama/WhatsApp/Maestro).
    # An external restart-probe MUST target /livez, not /healthz: coupling a
    # restart trigger to the DB or an upstream turns a transient dependency
    # hiccup into a restart-loop that amplifies an outage (incident 2026-06-16
    # VS 504). Readiness (DB connectivity) stays in /healthz, which may 503.
    # _version_commit() is cached at startup, so this never touches disk.
    @app.get(f"{PREFIX}/livez")
    async def casehub_livez():
        return JSONResponse(
            {
                "status": "alive",
                "service": "casehub",
                "product": product,
                "version": "0.9.12-alpha",
                "commit": _version_commit(),
                "marker": "casehub-live-v1",
            },
            status_code=200,
        )

    # Goal frente A lists ``/casehub/google/status`` — the existing
    # surface is ``/casehub/google-calendar/status`` (auth-gated, returns
    # connection state of the per-user google_calendar). Provide an
    # unauthenticated, lightweight aggregator at the goal-listed path
    # that reports whether the integration is CONFIGURED on this deploy
    # (not whether any specific user has connected). Keeps the goal's
    # probe list honest without exposing per-user data unauth.
    @app.get(f"{PREFIX}/google/status")
    async def casehub_google_status():
        # CONFIGURED means: required env / credentials path is set so the
        # Google Calendar / Drive integrations CAN run. It does NOT
        # confirm a working OAuth token for any user — that lives behind
        # /casehub/google-calendar/status (auth-gated).
        try:
            from services.google_drive_handler import CREDENTIALS_PATH
            drive_creds_path_set = bool(CREDENTIALS_PATH)
        except Exception:
            drive_creds_path_set = False
        return JSONResponse({
            "configured": drive_creds_path_set,
            "per_user_status_endpoint": f"{PREFIX}/google-calendar/status",
            "note": (
                "This endpoint reports deploy-level configuration only. "
                "Use per_user_status_endpoint (auth required) to check "
                "the current user's connection state."
            ),
        })

    # ------------------------------------------------------------------
    # Manual page (user guide)
    # ------------------------------------------------------------------
    @app.get(f"{PREFIX}/manual", response_class=HTMLResponse)
    async def manual_page(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
        return templates.TemplateResponse("manual/index.html", {
            **get_context(request, db),
            "user": user,
        })

    # ------------------------------------------------------------------
    # WhatsApp Bot Control Proxy (only for immigration product)
    # ------------------------------------------------------------------
    if product == "immigration":
        @app.post('/api/bot-control')
        async def bot_control_proxy(request: Request):
            import httpx
            try:
                data = await request.json()
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f'{settings.WHATSAPP_BOT_URL}/api/bot-control',
                        json=data,
                        timeout=10.0,
                    )
                    return resp.json()
            except Exception as e:
                return {'success': False, 'error': str(e)}

        @app.get("/whatsapp")
        async def whatsapp_page(request: Request):
            return templates.TemplateResponse("whatsapp.html", get_context(request))

        @app.get("/api/bot-status")
        async def bot_status_proxy():
            import httpx
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{settings.WHATSAPP_BOT_URL}/api/bot-status", timeout=10.0)
                    return resp.json()
            except Exception as e:
                return {"error": str(e), "globalEnabled": True, "botIsActive": True}

        @app.post("/api/bot-toggle")
        async def bot_toggle_proxy():
            import httpx
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(f"{settings.WHATSAPP_BOT_URL}/api/bot-toggle", timeout=10.0)
                    return resp.json()
            except Exception as e:
                return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Include routers based on product
    # ------------------------------------------------------------------
    router_names = PRODUCT_ROUTERS[product]
    included = []
    skipped = []

    for name in router_names:
        routers = _import_router(name)
        if routers:
            for r in routers:
                app.include_router(r, prefix=PREFIX)
            included.append(name)
        else:
            skipped.append(name)

    logger.info("[app_factory] Product=%s: %d router modules loaded, %d skipped", product, len(included), len(skipped))
    if skipped:
        logger.info("[app_factory] Skipped: %s", ', '.join(skipped))

    # Sentinela T11 fix: auth-gated /uploads. Mounted at the apex (no PREFIX)
    # so URLs match the previous public StaticFiles mount.
    try:
        from routes.uploads import router as uploads_router
        app.include_router(uploads_router)
        logger.info("[app_factory] /uploads router registered (auth + tenant-gated)")
    except Exception as exc:
        logger.error("[app_factory] Failed to register uploads router: %s", exc)

    # ------------------------------------------------------------------
    # Custom error pages (404, 403, 500)
    # ------------------------------------------------------------------
    from starlette.exceptions import HTTPException as StarletteHTTPException
    from core.template_config import inject_org_context

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        org_ctx = _sanitize_public_error_context(inject_org_context(request))
        lang = get_lang(request)
        t = get_translations(lang)
        ctx = {
            "request": request,
            "PREFIX": PREFIX,
            "t": t,
            "detail": exc.detail,
            "retry_url": _request_path_with_query(request),
            **org_ctx,
        }
        wants_html = _wants_html_response(request)

        if exc.status_code == 404:
            return templates.TemplateResponse(
                "errors/404.html", ctx, status_code=404,
            )
        elif exc.status_code == 402:
            if not wants_html:
                return JSONResponse(
                    {"detail": exc.detail}, status_code=exc.status_code,
                )
            ctx.update({
                "error_code": "402",
                "error_title": t.get("error.plan_unavailable", "Recurso indisponivel no plano"),
                "detail": t.get("error.plan_unavailable_detail", "Este recurso nao esta incluso no plano atual. Voce pode continuar usando o CaseHub ou revisar o plano."),
                "show_upgrade_action": True,
            })
            return templates.TemplateResponse(
                "errors/403.html", ctx, status_code=402,
            )
        elif exc.status_code == 403:
            return templates.TemplateResponse(
                "errors/403.html", ctx, status_code=403,
            )
        elif exc.status_code >= 500:
            error_ref = secrets.token_hex(4)
            logger.error("HTTP %s request error [%s] path=%s", exc.status_code, error_ref, request.url.path)
            if not wants_html:
                return JSONResponse(
                    {"detail": "Internal Server Error", "error_ref": error_ref},
                    status_code=exc.status_code,
                )
            ctx.update({"error_ref": error_ref})
            try:
                return templates.TemplateResponse(
                    "errors/500.html", ctx, status_code=exc.status_code,
                )
            except Exception:
                logger.exception("Failed to render 500 template [%s] path=%s", error_ref, request.url.path)
                return HTMLResponse(_minimal_500_html(error_ref), status_code=exc.status_code)

        # Default: JSON response for other status codes
        return JSONResponse(
            {"detail": exc.detail}, status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        error_ref = secrets.token_hex(4)
        logger.exception("Unhandled request error [%s] path=%s", error_ref, request.url.path)

        wants_html = _wants_html_response(request)
        if not wants_html:
            return JSONResponse(
                {"detail": "Internal Server Error", "error_ref": error_ref},
                status_code=500,
            )

        org_ctx = inject_org_context(request)
        lang = get_lang(request)
        t = get_translations(lang)
        try:
            return templates.TemplateResponse(
                "errors/500.html",
                {
                    "request": request,
                    "PREFIX": PREFIX,
                    "t": t,
                    "detail": "internal_error",
                    "error_ref": error_ref,
                    "retry_url": _request_path_with_query(request),
                    **org_ctx,
                },
                status_code=500,
            )
        except Exception:
            logger.exception("Failed to render 500 template [%s] path=%s", error_ref, request.url.path)
            return HTMLResponse(_minimal_500_html(error_ref), status_code=500)

    return app
