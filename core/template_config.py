from __future__ import annotations

"""
CaseHub - Centralized Template Configuration
IMPORTANTE: Única instância de Jinja2Templates para todo o app

Injects both static (settings-based) and dynamic (org-based) template globals.
Dynamic org branding is resolved per-request via inject_org_context().
"""
import json
from datetime import date, timedelta
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

import logging

from config import settings
from core.currency import format_currency, currency_symbol
from core.static_assets import asset_url, brand_kit_fallback_favicon_url
from core.jinja_runtime import configure_jinja_templates
from core.release_notice import get_casehub_release_notice

logger = logging.getLogger(__name__)

PREFIX = settings.PREFIX
APP_VERSION = "0.9.12-alpha"
CANONICAL_SUPPORT_EMAIL = "casehub@legalopsco.work"
RETIRED_SUPPORT_DOMAINS: set[str] = set()


def public_contact_email(value: str | None = None) -> str:
    """Return the public support email, blocking retired tenant contacts."""
    email = (value or settings.ORG_EMAIL or "").strip()
    domain = email.lower().rsplit("@", 1)[-1] if "@" in email else ""
    if domain in RETIRED_SUPPORT_DOMAINS:
        return CANONICAL_SUPPORT_EMAIL
    return email or CANONICAL_SUPPORT_EMAIL

# Instância ÚNICA e GLOBAL de templates
templates = Jinja2Templates(directory="templates")
configure_jinja_templates(templates)

# Configurações aplicadas UMA vez (static defaults from .env / settings)
templates.env.globals["PREFIX"] = PREFIX
templates.env.globals["now"] = lambda: date.today()
templates.env.globals["today_plus"] = lambda days: date.today() + timedelta(days=days)
templates.env.globals["version"] = APP_VERSION
templates.env.globals["asset_url"] = asset_url
templates.env.globals["brand_kit_fallback_favicon_url"] = brand_kit_fallback_favicon_url()

# Currency formatting (available in all templates)
templates.env.filters["format_currency"] = format_currency
templates.env.globals["currency_symbol"] = currency_symbol
templates.env.globals["org_currency"] = "BRL" if settings.CASEHUB_PRODUCT == "lite" else "USD"

# Organization defaults (overridden per-request when org context is available)
templates.env.globals["org_name"] = settings.ORG_NAME
templates.env.globals["org_email"] = public_contact_email(settings.ORG_EMAIL)
templates.env.globals["public_contact_email"] = public_contact_email
templates.env.globals["org_domain"] = settings.ORG_DOMAIN
templates.env.globals["org_center_email"] = settings.ORG_CENTER_EMAIL
templates.env.globals["base_url"] = settings.BASE_URL

# Theme defaults (will be overridden per-request by inject_org_context)
templates.env.globals["org_theme_primary"] = "#ffffff"
templates.env.globals["org_theme_secondary"] = "#1a1a1a"
templates.env.globals["org_theme_bg"] = "#0f0f0f"
templates.env.globals["org_logo"] = ""
templates.env.globals["org_favicon"] = ""
templates.env.globals["org_phone"] = ""
templates.env.globals["casehub_release_notice"] = get_casehub_release_notice()
templates.env.globals["casehub_maestro_fab_enabled"] = settings.CASEHUB_MAESTRO_FAB_ENABLED
templates.env.globals["casehub_work_intelligence_enabled"] = False
templates.env.globals["casehub_work_intelligence_client_events_enabled"] = False

# Gmail compose availability — global flag based on env + token presence.
# Per-request per-org check happens at the route level; this drives template visibility.
import os as _os
_gmail_oauth_enabled = bool(getattr(settings, "GMAIL_OAUTH_ENABLED", False))
_gmail_default_accounts_raw = getattr(settings, "GMAIL_DEFAULT_ACCOUNTS", "") or ""
_gmail_default_account = _gmail_default_accounts_raw.split(",")[0].strip() if _gmail_default_accounts_raw else ""
templates.env.globals["gmail_send_enabled"] = _gmail_oauth_enabled
templates.env.globals["gmail_send_account"] = _gmail_default_account


def inject_org_context(request: Request, user=None) -> dict:
    """
    Build a dict of org-specific template variables from request.state.org.
    Call this in route handlers and merge into TemplateResponse context:

        ctx = inject_org_context(request, user)
        return templates.TemplateResponse("page.html", {"request": request, **ctx, ...})

    If no org is resolved (e.g. single-tenant mode), returns base dict
    so the Jinja2 globals (defaults) are used instead.

    Also injects ui_theme from the current user (defaults to "neuromorphic").
    """
    # Resolve ui_theme from user object (passed explicitly or from request.state).
    # Guarded against DetachedInstanceError — em error handlers (404/500),
    # request.state.user pode vir de uma session já fechada e o getattr
    # dispara orm.exc.DetachedInstanceError ao tentar lazy-load. Fallback safe.
    _user = user or getattr(getattr(request, "state", None), "user", None)
    ui_theme = "neuromorphic"
    if _user:
        try:
            ui_theme = getattr(_user, "ui_theme", "neuromorphic") or "neuromorphic"
        except Exception:
            ui_theme = "neuromorphic"

    org = getattr(getattr(request, "state", None), "org", None)
    if not org:
        return {"ui_theme": ui_theme,
                "can_view_financeiro": (getattr(_user, "user_type", None) == "superadmin") if _user else False}

    # Parse org_settings from the settings JSONB column
    org_settings = {}
    if isinstance(org, dict):
        raw_settings = org.get("settings")
    else:
        raw_settings = getattr(org, "settings", None)
    if raw_settings:
        if isinstance(raw_settings, str):
            try:
                org_settings = json.loads(raw_settings)
            except (json.JSONDecodeError, TypeError):
                org_settings = {}
        elif isinstance(raw_settings, dict):
            org_settings = raw_settings

    # Resolve org_features from org.features JSON field + product defaults
    org_features = {}
    if isinstance(org, dict):
        org_features = org.get("features") or {}
    else:
        org_features = getattr(org, "features", None) or {}
    if isinstance(org_features, str):
        try:
            org_features = json.loads(org_features)
        except (json.JSONDecodeError, TypeError):
            org_features = {}
    if not isinstance(org_features, dict):
        org_features = {}
    # Merge with product defaults (org-level overrides product-level)
    from core.app_factory import PRODUCT_DEFAULTS
    product = getattr(getattr(request, "app", None), "state", None)
    product_name = getattr(product, "product", "lite") if product else "lite"
    product_features = PRODUCT_DEFAULTS.get(product_name, {}).get("features", {})
    merged_features = {**product_features, **org_features}

    # Gate de visibilidade do Financeiro (dado sensível, sócio-only) — espelha
    # o gate de /reports/financeiro: superadmin OU id na allowlist
    # org_settings.financeiro_user_ids. NÃO usa 'admin' genérico (QA/ops não veem).
    _can_fin = False
    if _user:
        try:
            if getattr(_user, "user_type", None) == "superadmin":
                _can_fin = True
            else:
                _can_fin = getattr(_user, "id", None) in (org_settings.get("financeiro_user_ids") or [])
        except Exception:
            _can_fin = False

    _wi_enabled = (
        bool(getattr(settings, "CASEHUB_WORK_INTELLIGENCE_ENABLED", False))
        and str(org_settings.get("work_intelligence_enabled", "")).strip().lower() in {"1", "true", "yes", "on"}
    )
    _wi_client_enabled = (
        _wi_enabled
        and bool(getattr(settings, "CASEHUB_WORK_INTELLIGENCE_CLIENT_EVENTS_ENABLED", False))
        and str(org_settings.get("work_intelligence_client_events_enabled", "")).strip().lower() in {"1", "true", "yes", "on"}
    )

    # org is a dict (set by TenantMiddleware)
    if isinstance(org, dict):
        return {
            "org_name": org.get("name") or settings.ORG_NAME,
            "org_slug": org.get("slug") or "",
            "org_email": public_contact_email(org.get("email")),
            "org_domain": org.get("website") or org.get("domain") or settings.ORG_DOMAIN,
            "org_phone": org.get("phone") or "",
            "org_logo": org.get("logo_url") or org_settings.get("logo_file_path") or "",
            "org_favicon": org.get("favicon_url") or "",
            "org_theme_primary": org.get("primary_color") or "#ffffff",
            "org_theme_secondary": org.get("secondary_color") or "#1a1a1a",
            "org_theme_bg": org_settings.get("theme_bg") or "#0f0f0f",
            "org_theme_accent": org_settings.get("accent_color") or "",
            "org_font": org_settings.get("font_family") or "",
            "org_case_prefix": org.get("case_prefix") or settings.CASE_PREFIX,
            "org_currency": org.get("currency") or "USD",
            "org_settings": org_settings,
            "org_features": merged_features,
            "base_url": settings.BASE_URL,
            "version": APP_VERSION,
            "can_view_financeiro": _can_fin,
            "ui_theme": ui_theme,
            "casehub_work_intelligence_enabled": _wi_enabled,
            "casehub_work_intelligence_client_events_enabled": _wi_client_enabled,
        }

    # org is an ORM object (Organization model)
    return {
        "org_name": getattr(org, "name", settings.ORG_NAME),
        "org_slug": getattr(org, "slug", "") or "",
        "org_email": public_contact_email(getattr(org, "email", None)),
        "org_domain": getattr(org, "website", None) or getattr(org, "domain", settings.ORG_DOMAIN),
        "org_phone": getattr(org, "phone", ""),
        "org_logo": getattr(org, "logo_url", "") or org_settings.get("logo_file_path") or "",
        "org_favicon": getattr(org, "favicon_url", "") or "",
        "org_theme_primary": getattr(org, "primary_color", "#ffffff") or "#ffffff",
        "org_theme_secondary": getattr(org, "secondary_color", "#1a1a1a") or "#1a1a1a",
        "org_theme_bg": org_settings.get("theme_bg") or "#0f0f0f",
        "org_theme_accent": org_settings.get("accent_color") or "",
        "org_font": org_settings.get("font_family") or "",
        "org_case_prefix": getattr(org, "case_prefix", settings.CASE_PREFIX),
        "org_currency": getattr(org, "currency", "USD") or "USD",
        "org_settings": org_settings,
        "org_features": merged_features,
        "base_url": settings.BASE_URL,
        "version": APP_VERSION,
        "can_view_financeiro": _can_fin,
        "ui_theme": ui_theme,
        "casehub_work_intelligence_enabled": _wi_enabled,
        "casehub_work_intelligence_client_events_enabled": _wi_client_enabled,
    }


class _PreviewMock:
    """Namespace inerte pra Jinja em preview/archive — qualquer atributo retorna "" e .get() retorna default."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
    def __getattr__(self, name):  # noqa: D401
        return ""
    def get(self, key, default=""):
        return default
    def __bool__(self):
        return True
    def __iter__(self):
        return iter([])


# Preview-only plan mock (archive viewer / offline template render).
# Mirrors the canonical 2-plan spec (Equipe CaseHub, 28/05/2026). max_users = -1 => unlimited.
_PREVIEW_PLANS = {
    "office": {
        "name": "Pequenos escritórios e Sociedade Unipessoal de Advocacia",
        "price": 129,
        "price_label": None,
        "contact_only": False,
        "features": ["Usuários ilimitados", "Processos", "Clientes", "CRM", "WhatsApp"],
        "max_users": -1, "max_clients": -1, "max_storage_gb": 50,
    },
    "enterprise": {
        "name": "Enterprise",
        "price": None,
        "price_label": "Sob consulta",
        "contact_only": True,
        "features": ["Usuários ilimitados", "Gerente dedicado", "SLA", "Integrações sob medida"],
        "max_users": -1, "max_clients": -1, "max_storage_gb": 500,
    },
}


def mock_preview_context(request):
    """Contexto Jinja seguro pra renderizar templates fora do fluxo real.

    Usado pelo archive viewer (routes/template_archive.py) e pelo preview
    do refactor-review (/_preview/<key>) — ambos renderizam templates que
    normalmente dependem de auth/sessão/fixture. Com este contexto, nunca
    estouram 500 por user/org/t/product/plans/etc ausentes.
    """
    org_mock = _PreviewMock(name="CaseHub Preview", slug="preview", plan="office")
    return {
        "request": request,
        "PREFIX": PREFIX,
        "product": "lite",
        "lang": "pt-BR",
        "theme": "light",
        "org_name": "CaseHub Preview",
        "org_slug": "preview",
        "org_logo": "",
        "org_settings": _PreviewMock(),
        "org_font": "",
        "org_theme_accent": "",
        "org_features": {},
        "showcase": True,
        "error": "",
        "success": "",
        "user": _PreviewMock(name="Preview User", email="preview@casehub.dev", id=0, user_type="staff"),
        "org": org_mock,
        "t": _PreviewMock(),
        "step": 1,
        "total_steps": 5,
        "token": "preview-token",
        "ui_theme": "glass",
        "is_desktop_frame": False,
        # Dados específicos de templates de onboarding:
        "plans": _PREVIEW_PLANS,
        "features": {},
        "settings": _PreviewMock(),
    }


logger.info(
    "Jinja2Templates initialized with auto_reload=%s, bytecode_cache=%s, version=%s",
    templates.env.auto_reload,
    bool(templates.env.bytecode_cache),
    APP_VERSION,
)
