"""
CaseHub - Onboarding Routes
Signup flow and setup wizard for new organizations.
"""
import os
import re
import uuid
import secrets
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, User
from models.tenant import Organization, create_org, get_org_by_slug
from auth import create_access_token, get_current_user, ACCESS_TOKEN_EXPIRE_MINUTES
from core.template_config import templates, PREFIX
from config import settings
from services.notifications import send_email
from services.subdomain_validator import (
    check_subdomain as validate_subdomain,
    slugify as canonical_slugify,
)
from services.captcha import verify as verify_captcha
from services.email_verification import issue_token as issue_email_token, consume_token as consume_email_token
from services.email_domain_validator import is_disposable, looks_valid, domain_of
from urllib.parse import quote as urllib_quote

try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False

logger = logging.getLogger(__name__)

router = APIRouter(tags=["onboarding"])

# Plan tiers shown in the signup wizard (/setup/plan). Spec (Victor, 28/05/2026):
# exactly two plans, R$129 + Enterprise "sob consulta", usuários ILIMITADOS por
# enquanto em ambos (max_users = -1 => unlimited, ver plan_enforcement.py).
# Keep keys in sync with routes/subscription.PLAN_FEATURES.
DEFAULT_PLAN = "office"

PLAN_TIERS = {
    "office": {
        "name": "Pequenos escritórios e Sociedade Unipessoal de Advocacia",
        "price": 129,
        "price_label": None,
        "contact_only": False,
        "max_users": -1,     # unlimited (por enquanto)
        "max_clients": -1,   # unlimited (por enquanto)
        "max_storage_gb": 50,
        "features": ["Gestão de processos", "Documentos", "CRM", "WhatsApp", "Agenda", "Controladoria"],
        "stripe_price_id": os.getenv("STRIPE_PRICE_OFFICE", ""),
    },
    "enterprise": {
        "name": "Enterprise",
        "price": None,            # sob consulta — sem preço fixo
        "price_label": "Sob consulta",
        "contact_only": True,
        "max_users": -1,     # unlimited (por enquanto)
        "max_clients": -1,   # unlimited (por enquanto)
        "max_storage_gb": 500,
        "features": ["Tudo do plano menor", "SSO / SAML", "Suporte dedicado", "Integrações sob medida", "SLA"],
        "stripe_price_id": "",    # contato comercial, sem checkout self-service
    },
}


def slugify(name: str) -> str:
    """Convert firm name to URL-safe slug.

    Delegates to services.subdomain_validator.slugify so signup, wizard, and
    auto-suggestions all agree on the canonical form.
    """
    s = canonical_slugify(name)
    return s if s else "org"


# ---------------------------------------------------------------------------
# Public API: subdomain availability check (used by /signup + /setup/subdomain)
# ---------------------------------------------------------------------------

@router.get("/api/onboarding/check-subdomain")
async def check_subdomain_api(
    slug: str = "",
    db: Session = Depends(get_db),
):
    """Live-validation endpoint for the subdomain input.

    Returns JSON with `available`, `reason`, `message`, `suggestions`, and the
    normalized `canonical_slug`. Caller is expected to debounce (~300ms).
    """
    result = validate_subdomain(db, slug)
    return result.to_dict()


# ---------------------------------------------------------------------------
# Tour progress API (Fatia D — persist tour state per user, cross-device)
# ---------------------------------------------------------------------------

# Whitelist of tour step IDs accepted by /api/onboarding/tour-step.
# Keep in sync with static/js/onboarding-tour-basic.js step ids.
_VALID_TOUR_STEPS = {
    "welcome",
    "navigation",
    "controladoria",
    "agenda",
    "tarefas",
    "clientes",
    "processos",
    "next",
}


@router.post("/api/onboarding/tour-step")
async def tour_step(
    request: Request,
    db: Session = Depends(get_db),
):
    """Record current tour step for resume support across devices."""
    user = get_current_user(request, db)
    if not user:
        return {"ok": False, "reason": "unauthenticated"}

    try:
        body = await request.json()
    except Exception:
        body = {}
    step_id = (body.get("step_id") or "").strip()

    if step_id not in _VALID_TOUR_STEPS:
        return {"ok": False, "reason": "invalid_step"}

    user.onboarding_tour_step = step_id
    db.commit()
    return {"ok": True, "step_id": step_id}


@router.post("/api/onboarding/tour-complete")
async def tour_complete(
    request: Request,
    db: Session = Depends(get_db),
):
    """Mark the onboarding tour as finished. Idempotent."""
    user = get_current_user(request, db)
    if not user:
        return {"ok": False, "reason": "unauthenticated"}

    if user.onboarding_completed_at is None:
        user.onboarding_completed_at = datetime.now()
    user.onboarding_tour_step = None
    db.commit()
    return {"ok": True, "completed_at": user.onboarding_completed_at.isoformat()}


@router.post("/api/onboarding/tour-restart")
async def tour_restart(
    request: Request,
    db: Session = Depends(get_db),
):
    """Reset tour progress so the user can replay it from step 1."""
    user = get_current_user(request, db)
    if not user:
        return {"ok": False, "reason": "unauthenticated"}

    user.onboarding_completed_at = None
    user.onboarding_tour_step = None
    db.commit()
    return {"ok": True}


def _get_setup_step(request: Request) -> int:
    """Read current setup step from cookie."""
    try:
        return int(request.cookies.get("setup_step", "1"))
    except (TypeError, ValueError):
        return 1


def _set_setup_step(response, step: int):
    """Set setup step cookie."""
    response.set_cookie("setup_step", str(step), max_age=86400, path="/", httponly=True)
    return response


def _get_setup_org_id(request: Request) -> int:
    """Get the org_id from setup cookie (set during signup)."""
    try:
        return int(request.cookies.get("setup_org_id", "0"))
    except (TypeError, ValueError):
        return 0


def _get_setup_org(db: Session, request: Request) -> dict:
    """Fetch the org being set up."""
    org_id = _get_setup_org_id(request)
    if not org_id:
        return None
    result = db.execute(
        text("SELECT * FROM organizations WHERE id = :id"),
        {"id": org_id}
    ).mappings().first()
    return dict(result) if result else None


# =========================================================================
# Public Routes - Signup
# =========================================================================

@router.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    """Render the signup page. Dual-mode: self-service (when feature flag is
    on) or access_request (legacy)."""
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    suggested_slug = request.query_params.get("slug", "")
    return templates.TemplateResponse("onboarding/signup.html", {
        "request": request,
        "PREFIX": PREFIX,
        "error": error,
        "success": success,
        "self_service": bool(settings.SELF_SERVICE_SIGNUP_ENABLED),
        "turnstile_site_key": settings.CF_TURNSTILE_SITE_KEY or "",
        "suggested_slug": suggested_slug,
    })


def _client_ip(request: Request) -> str:
    """Best-effort client IP, honoring X-Forwarded-For when behind nginx."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _ensure_signup_audit_table(db: Session):
    """Idempotent guard for orgs that haven't applied the 2026-05-24 migration."""
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS signup_audit_log (
            id SERIAL PRIMARY KEY,
            org_id INTEGER,
            user_id INTEGER,
            email VARCHAR(200) NOT NULL,
            slug VARCHAR(100) NOT NULL,
            firm_name VARCHAR(255),
            ip_address VARCHAR(64),
            user_agent TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            captcha_score NUMERIC(3,2),
            flagged_reason VARCHAR(200)
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS email_verifications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token VARCHAR(255) NOT NULL UNIQUE,
            email VARCHAR(200) NOT NULL,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            consumed_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            ip_address VARCHAR(64),
            user_agent TEXT
        )
    """))
    db.commit()


def _signup_rate_limited(db: Session, ip: str, email_domain: str):
    """Return user-facing error string if rate-limited, else None."""
    ip_cap = settings.SIGNUP_RATE_LIMIT_PER_IP_PER_HOUR
    dom_cap = settings.SIGNUP_RATE_LIMIT_PER_DOMAIN_PER_DAY

    ip_count = db.execute(
        text("SELECT COUNT(*) FROM signup_audit_log WHERE ip_address = :ip AND created_at > NOW() - INTERVAL '1 hour'"),
        {"ip": ip},
    ).scalar() or 0
    if ip_count >= ip_cap:
        return "Muitas tentativas neste IP. Tente novamente em 1 hora."

    if email_domain:
        dom_count = db.execute(
            text("SELECT COUNT(*) FROM signup_audit_log WHERE email LIKE :pat AND created_at > NOW() - INTERVAL '1 day'"),
            {"pat": f"%@{email_domain}"},
        ).scalar() or 0
        if dom_count >= dom_cap:
            return f"Muitas tentativas para o domínio {email_domain} hoje."

    return None


@router.post("/signup")
async def signup_submit(
    request: Request,
    firm_name: str = Form(...),
    admin_email: str = Form(...),
    admin_name: str = Form(""),
    phone: str = Form(""),
    password: str = Form(""),
    slug: str = Form(""),
    cf_turnstile_response: str = Form("", alias="cf-turnstile-response"),
    db: Session = Depends(get_db),
):
    """Signup handler — dual mode.

    Self-service (settings.SELF_SERVICE_SIGNUP_ENABLED=True):
        Validates captcha + slug + password + rate-limit; creates real
        Organization (is_active=FALSE) + User (email_verified_at=NULL); sends
        verification email. User activates by clicking the link.

    Legacy (flag OFF — current default until Council ruling):
        Saves an access_request row; admin reviews manually.
    """
    import logging
    logger = logging.getLogger(__name__)

    if not firm_name.strip():
        return RedirectResponse(url=f"{PREFIX}/signup?error=Nome+do+escritorio+obrigatorio", status_code=302)
    if not admin_email.strip() or "@" not in admin_email:
        return RedirectResponse(url=f"{PREFIX}/signup?error=Email+valido+obrigatorio", status_code=302)

    client_ip = _client_ip(request)

    # -----------------------------------------------------------------------
    # SELF-SERVICE PATH (Fatia B — gated by feature flag + Council ruling)
    # -----------------------------------------------------------------------
    if settings.SELF_SERVICE_SIGNUP_ENABLED:
        email_norm = admin_email.strip().lower()
        firm_norm = firm_name.strip()
        ua = request.headers.get("user-agent", "")[:500]

        if not looks_valid(email_norm):
            return RedirectResponse(url=f"{PREFIX}/signup?error={urllib_quote('Email inválido')}", status_code=302)
        if is_disposable(email_norm):
            return RedirectResponse(url=f"{PREFIX}/signup?error={urllib_quote('Use um email permanente do escritório')}", status_code=302)
        if len(password) < 8 or not any(c.isupper() for c in password) or not any(c.isdigit() for c in password):
            return RedirectResponse(url=f"{PREFIX}/signup?error={urllib_quote('Senha: mín 8 caracteres, 1 maiúscula, 1 número')}", status_code=302)

        cap = verify_captcha(cf_turnstile_response, remote_ip=client_ip)
        if not cap.success:
            email_masked = email_norm.split("@")[0][:2] + "***@" + email_norm.split("@")[1]
            logger.warning("signup captcha failed ip=%s email=%s codes=%s", client_ip, email_masked, cap.error_codes)
            return RedirectResponse(url=f"{PREFIX}/signup?error={urllib_quote('Verifique que você não é um robô')}", status_code=302)

        _ensure_signup_audit_table(db)
        rate_err = _signup_rate_limited(db, client_ip, domain_of(email_norm))
        if rate_err:
            logger.warning("signup rate-limited ip=%s email=%s reason=%s", client_ip, email_norm, rate_err)
            return RedirectResponse(url=f"{PREFIX}/signup?error={urllib_quote(rate_err)}", status_code=302)

        chosen_slug = (slug or canonical_slugify(firm_norm)).strip().lower()
        slug_check = validate_subdomain(db, chosen_slug)
        if not slug_check.available:
            return RedirectResponse(url=f"{PREFIX}/signup?error={urllib_quote(slug_check.message)}&slug={urllib_quote(chosen_slug)}", status_code=302)

        existing = db.query(User).filter(User.email == email_norm).first()
        if existing:
            return RedirectResponse(url=f"{PREFIX}/signup?error={urllib_quote('Email já cadastrado. Faça login.')}", status_code=302)

        try:
            new_org = Organization(
                uuid=str(uuid.uuid4()),
                name=firm_norm,
                slug=slug_check.canonical_slug,
                email=email_norm,
                plan=DEFAULT_PLAN,
                is_active=False,
                created_via="self_service",
                subdomain_locked=False,
            )
            db.add(new_org)
            db.flush()

            new_user = User(
                email=email_norm,
                name=admin_name.strip() or email_norm.split("@")[0].title(),
                password_hash=User.hash_password(password),
                user_type="admin",
                enabled=True,
                must_change_password=False,
                email_verified_at=None,
            )
            if hasattr(new_user, "org_id"):
                new_user.org_id = new_org.id
            if phone.strip():
                new_user.phone = phone.strip()
            db.add(new_user)
            db.flush()

            db.execute(
                text("""
                    INSERT INTO signup_audit_log (org_id, user_id, email, slug, firm_name, ip_address, user_agent)
                    VALUES (:org_id, :user_id, :email, :slug, :firm, :ip, :ua)
                """),
                {"org_id": new_org.id, "user_id": new_user.id, "email": email_norm,
                 "slug": new_org.slug, "firm": firm_norm, "ip": client_ip, "ua": ua},
            )
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("self-service signup failed: %s", e, exc_info=True)
            return RedirectResponse(url=f"{PREFIX}/signup?error={urllib_quote('Erro ao criar escritório. Tente novamente.')}", status_code=302)

        # Issue verification token + email
        token = issue_email_token(db, new_user.id, email_norm, ip_address=client_ip, user_agent=ua)
        verify_url = f"{settings.BASE_URL}{PREFIX}/verify-email?token={token}"
        try:
            send_email(
                to_email=email_norm,
                subject="Confirme seu cadastro no CaseHub",
                html_body=templates.get_template("email/verify_signup.html").render(
                    user_name=new_user.name,
                    firm_name=firm_norm,
                    slug=new_org.slug,
                    verify_url=verify_url,
                    ttl_hours=settings.EMAIL_VERIFY_TOKEN_TTL_HOURS,
                ),
            )
        except Exception as e:
            logger.error("verification email send failed: %s", e)

        return RedirectResponse(url=f"{PREFIX}/signup/check-email?email={urllib_quote(email_norm)}", status_code=302)

    # -----------------------------------------------------------------------
    # LEGACY ACCESS_REQUEST PATH (flag OFF — preserved for instant rollback)
    # -----------------------------------------------------------------------
    try:
        db.execute(
            text("""
                INSERT INTO access_requests (firm_name, email, name, phone, ip_address, created_at)
                VALUES (:firm, :email, :name, :phone, :ip, NOW())
                ON CONFLICT (email) DO UPDATE SET firm_name = :firm, name = :name, phone = :phone, ip_address = :ip, created_at = NOW()
            """),
            {"firm": firm_name.strip(), "email": admin_email.strip().lower(),
             "name": admin_name.strip(), "phone": phone.strip(), "ip": client_ip},
        )
        db.commit()
        logger.info("Access request: %s (%s) from IP %s", admin_email, firm_name, client_ip)
    except Exception:
        db.rollback()
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS access_requests (
                    id SERIAL PRIMARY KEY,
                    firm_name VARCHAR(255),
                    email VARCHAR(255) UNIQUE,
                    name VARCHAR(255),
                    phone VARCHAR(50),
                    ip_address VARCHAR(100),
                    status VARCHAR(20) DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
            db.commit()
            db.execute(
                text("""
                    INSERT INTO access_requests (firm_name, email, name, phone, ip_address)
                    VALUES (:firm, :email, :name, :phone, :ip)
                """),
                {"firm": firm_name.strip(), "email": admin_email.strip().lower(),
                 "name": admin_name.strip(), "phone": phone.strip(), "ip": client_ip},
            )
            db.commit()
        except Exception as e2:
            logger.error("Failed to save access request: %s", e2)

    return RedirectResponse(
        url=f"{PREFIX}/signup?success=Solicitacao+enviada!+Entraremos+em+contato+em+breve.",
        status_code=302,
    )


# ---------------------------------------------------------------------------
# Self-service signup: post-submit "check your email" + verification consume
# ---------------------------------------------------------------------------

@router.get("/signup/check-email", response_class=HTMLResponse)
async def signup_check_email(request: Request):
    """Post-signup confirmation page asking the user to click the email link."""
    email = request.query_params.get("email", "")
    return templates.TemplateResponse("onboarding/check_email.html", {
        "request": request,
        "PREFIX": PREFIX,
        "email": email,
    })


@router.get("/verify-email", response_class=HTMLResponse)
async def verify_email(
    request: Request,
    token: str = "",
    db: Session = Depends(get_db),
):
    """Consume verification token → activate User + Organization → auto-login.

    Idempotent in the sense that re-using a consumed/expired token returns an
    explanatory error (without state change) instead of crashing.
    """
    if not token:
        return RedirectResponse(url=f"{PREFIX}/signup?error={urllib_quote('Token ausente')}", status_code=302)

    record = consume_email_token(db, token)
    if not record:
        return templates.TemplateResponse("onboarding/verify_email_error.html", {
            "request": request,
            "PREFIX": PREFIX,
            "reason": "invalid_or_expired",
        }, status_code=400)

    user = db.query(User).filter(User.id == record["user_id"]).first()
    if not user:
        return RedirectResponse(url=f"{PREFIX}/signup?error={urllib_quote('Usuário não encontrado')}", status_code=302)

    user.email_verified_at = datetime.utcnow()
    org = db.query(Organization).filter(Organization.id == user.org_id).first() if user.org_id else None
    if org:
        org.is_active = True
    db.commit()

    # Auto-login: set JWT cookie + redirect to setup/welcome on the new subdomain.
    access_token = create_access_token(data={"sub": user.email, "user_id": user.id, "org_id": user.org_id})
    target_host = f"{org.slug}.casehub.legal" if org else None
    redirect_url = f"https://{target_host}{PREFIX}/setup/welcome" if target_host else f"{PREFIX}/setup/welcome"

    response = RedirectResponse(url=redirect_url, status_code=302)
    # Sentinela T1: scope the JWT cookie to the tenant's host instead of the
    # apex domain. A cookie set with domain='.casehub.legal' was shared across
    # every subdomain, so a session opened under default.casehub.legal could
    # be reused on sampletenant.casehub.legal (which the spoofed X-Org-Id
    # path used to abuse). domain=None makes the cookie host-locked.
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=access_token,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
        domain=None,
    )
    if org:
        response.set_cookie("setup_org_id", str(org.id), max_age=86400, path="/", httponly=True)
        response.set_cookie("setup_step", "1", max_age=86400, path="/", httponly=True)
    return response


# =========================================================================
# Setup Wizard Steps
# =========================================================================

@router.get("/setup")
async def setup_alias():
    """Compatibility entrypoint for the setup wizard."""
    return RedirectResponse(url=f"{PREFIX}/setup/welcome", status_code=302)


@router.get("/onboarding")
@router.get("/onboarding/wizard")
async def onboarding_wizard_alias():
    """Compatibility entrypoint for older onboarding wizard links."""
    return RedirectResponse(url=f"{PREFIX}/setup/welcome", status_code=302)


@router.get("/setup/welcome", response_class=HTMLResponse)
async def setup_welcome(request: Request, db: Session = Depends(get_db)):
    """Step 1: Welcome page after signup."""
    org = _get_setup_org(db, request)
    if not org:
        return RedirectResponse(url=f"{PREFIX}/signup", status_code=302)
    user = get_current_user(request, db)
    response = templates.TemplateResponse("onboarding/welcome.html", {
        "request": request,
        "PREFIX": PREFIX,
        "org": org,
        "user": user,
        "step": 1,
        "total_steps": 6,
    })
    _set_setup_step(response, 1)
    return response


@router.get("/setup/subdomain", response_class=HTMLResponse)
async def setup_subdomain(request: Request, db: Session = Depends(get_db)):
    """Step 2: Choose the organization's subdomain.

    Suggests a slug derived from the org's current name. JS does live-check
    against /api/onboarding/check-subdomain; POST re-validates server-side.
    """
    org = _get_setup_org(db, request)
    if not org:
        return RedirectResponse(url=f"{PREFIX}/signup", status_code=302)
    user = get_current_user(request, db)

    # If the org already has a non-default slug locked, skip this step.
    if org.get("subdomain_locked"):
        return RedirectResponse(url=f"{PREFIX}/setup/branding", status_code=302)

    suggested = org.get("slug") or canonical_slugify(org.get("name") or "")

    error = request.query_params.get("error")
    response = templates.TemplateResponse("onboarding/subdomain.html", {
        "request": request,
        "PREFIX": PREFIX,
        "org": org,
        "user": user,
        "step": 2,
        "total_steps": 6,
        "suggested_slug": suggested,
        "error": error,
        "product": getattr(settings, "CASEHUB_PRODUCT", "lite"),
    })
    _set_setup_step(response, 2)
    return response


@router.post("/setup/subdomain")
async def setup_subdomain_save(
    request: Request,
    slug: str = Form(...),
    db: Session = Depends(get_db),
):
    """Persist the chosen subdomain after defense-in-depth re-validation."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/signup", status_code=302)
    org_id = user.org_id

    result = validate_subdomain(db, slug)
    if not result.available:
        # Bounce back with error; JS likely caught this, but defense-in-depth.
        return RedirectResponse(
            url=f"{PREFIX}/setup/subdomain?error={result.message}",
            status_code=302,
        )

    try:
        db.execute(
            text("""
                UPDATE organizations
                   SET slug = :slug,
                       updated_at = NOW()
                 WHERE id = :org_id
            """),
            {"slug": result.canonical_slug, "org_id": org_id},
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Setup subdomain save failed: {e}")
        return RedirectResponse(
            url=f"{PREFIX}/setup/subdomain?error=Falha+ao+salvar+subdomínio",
            status_code=302,
        )

    return RedirectResponse(url=f"{PREFIX}/setup/branding", status_code=302)


@router.get("/setup/branding", response_class=HTMLResponse)
async def setup_branding(request: Request, db: Session = Depends(get_db)):
    """Step 3: Upload logo, choose colors."""
    org = _get_setup_org(db, request)
    if not org:
        return RedirectResponse(url=f"{PREFIX}/signup", status_code=302)
    user = get_current_user(request, db)
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    response = templates.TemplateResponse("onboarding/branding.html", {
        "request": request,
        "PREFIX": PREFIX,
        "org": org,
        "user": user,
        "step": 3,
        "total_steps": 6,
        "success": success,
        "error": error,
    })
    _set_setup_step(response, 3)
    return response


@router.post("/setup/branding")
async def setup_branding_save(
    request: Request,
    primary_color: str = Form("#ffffff"),
    secondary_color: str = Form("#1a1a1a"),
    db: Session = Depends(get_db),
):
    """Save branding during setup."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/signup", status_code=302)
    org_id = user.org_id

    try:
        db.execute(
            text("""
                UPDATE organizations
                SET primary_color = :primary_color,
                    secondary_color = :secondary_color,
                    updated_at = NOW()
                WHERE id = :org_id
            """),
            {
                "primary_color": primary_color,
                "secondary_color": secondary_color,
                "org_id": org_id,
            },
        )
        db.commit()
        return RedirectResponse(url=f"{PREFIX}/setup/drive", status_code=302)
    except Exception as e:
        db.rollback()
        logger.error(f"Setup branding save failed: {e}")
        return RedirectResponse(
            url=f"{PREFIX}/setup/branding?error=Failed+to+save+branding",
            status_code=302,
        )


@router.get("/setup/drive", response_class=HTMLResponse)
async def setup_drive(request: Request, db: Session = Depends(get_db)):
    """Step 4: Google Drive OAuth connection."""
    org = _get_setup_org(db, request)
    if not org:
        return RedirectResponse(url=f"{PREFIX}/signup", status_code=302)
    user = get_current_user(request, db)
    response = templates.TemplateResponse("onboarding/drive.html", {
        "request": request,
        "PREFIX": PREFIX,
        "org": org,
        "user": user,
        "step": 4,
        "total_steps": 6,
    })
    _set_setup_step(response, 4)
    return response


@router.get("/setup/team", response_class=HTMLResponse)
async def setup_team(request: Request, db: Session = Depends(get_db)):
    """Step 5: Invite team members."""
    org = _get_setup_org(db, request)
    if not org:
        return RedirectResponse(url=f"{PREFIX}/signup", status_code=302)
    user = get_current_user(request, db)
    success = request.query_params.get("success")
    error = request.query_params.get("error")
    response = templates.TemplateResponse("onboarding/team.html", {
        "request": request,
        "PREFIX": PREFIX,
        "org": org,
        "user": user,
        "step": 5,
        "total_steps": 6,
        "success": success,
        "error": error,
    })
    _set_setup_step(response, 5)
    return response


@router.post("/setup/team")
async def setup_team_invite(
    request: Request,
    emails: str = Form(""),
    db: Session = Depends(get_db),
):
    """Send team invitation emails."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/signup", status_code=302)
    org_id = user.org_id

    org_row = db.execute(
        text("SELECT * FROM organizations WHERE id = :id"), {"id": org_id}
    ).mappings().first()
    org = dict(org_row) if org_row else None
    if not org:
        return RedirectResponse(url=f"{PREFIX}/signup", status_code=302)

    # Parse emails (comma or newline separated)
    email_list = [e.strip().lower() for e in re.split(r'[,\n]+', emails) if e.strip() and "@" in e.strip()]

    if not email_list:
        return RedirectResponse(
            url=f"{PREFIX}/setup/team?error=No+valid+emails+provided",
            status_code=302,
        )

    emails_to_invite = email_list[:10]  # Cap at 10 invites during setup
    # Batch the per-email existence check (N+1 -> 1 SELECT). Capped at 10, so
    # the absolute win is modest, but the pattern is the right shape.
    existing_emails = {
        u.email
        for u in db.query(User).filter(User.email.in_(emails_to_invite)).all()
    }

    invited_count = 0
    for email in emails_to_invite:
        if email in existing_emails:
            continue

        # Create user with temporary password (must_change_password=True)
        temp_pass = secrets.token_urlsafe(12)
        new_user = User(
            email=email,
            name=email.split("@")[0].title(),
            password_hash=User.hash_password(temp_pass),
            user_type="case_worker",
            enabled=True,
            must_change_password=True,
        )
        if hasattr(new_user, 'org_id'):
            new_user.org_id = org_id
        db.add(new_user)
        invited_count += 1

        # Send invitation email via SMTP
        org_name = org.get('name', str(org_id))
        login_url = f"{settings.BASE_URL}{PREFIX}/login"
        invite_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #2563eb;">You've been invited to {org_name}</h2>
            <p>Hello,</p>
            <p>You have been invited to join <strong>{org_name}</strong> on CaseHub.
               Your account has been created and is ready to use.</p>
            <table style="background: #f8fafc; border-radius: 8px; padding: 16px; width: 100%; margin: 20px 0;">
                <tr><td style="padding: 8px; color: #64748b;">Login URL</td>
                    <td style="padding: 8px;"><a href="{login_url}">{login_url}</a></td></tr>
                <tr><td style="padding: 8px; color: #64748b;">Email</td>
                    <td style="padding: 8px;"><strong>{email}</strong></td></tr>
                <tr><td style="padding: 8px; color: #64748b;">Temporary Password</td>
                    <td style="padding: 8px;"><code style="background:#e2e8f0; padding:4px 8px; border-radius:4px;">{temp_pass}</code></td></tr>
            </table>
            <p style="color: #dc2626;"><strong>Important:</strong> You will be asked to change your password on first login.</p>
            <p>If you have any questions, please contact your administrator.</p>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;">
            <p style="color: #94a3b8; font-size: 12px;">This is an automated message from CaseHub.</p>
        </body>
        </html>
        """
        try:
            send_email(
                to_email=email,
                subject=f"You've been invited to {org_name}",
                html_body=invite_html,
            )
        except Exception as e:
            logger.error(f"Failed to send invitation email to {email}: {e}")

        logger.info(f"Invited {email} to org {org_name}")

    db.commit()
    return RedirectResponse(
        url=f"{PREFIX}/setup/team?success=Invited+{invited_count}+team+member(s)",
        status_code=302,
    )


@router.get("/setup/plan", response_class=HTMLResponse)
async def setup_plan(request: Request, db: Session = Depends(get_db)):
    """Step 6: Choose plan."""
    org = _get_setup_org(db, request)
    if not org:
        return RedirectResponse(url=f"{PREFIX}/signup", status_code=302)
    user = get_current_user(request, db)
    response = templates.TemplateResponse("onboarding/plan.html", {
        "request": request,
        "PREFIX": PREFIX,
        "org": org,
        "user": user,
        "step": 6,
        "total_steps": 6,
        "plans": PLAN_TIERS,
    })
    _set_setup_step(response, 6)
    return response


@router.post("/setup/plan")
async def setup_plan_save(
    request: Request,
    plan: str = Form(DEFAULT_PLAN),
    db: Session = Depends(get_db),
):
    """Save selected plan (and create Stripe checkout session if configured)."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/signup", status_code=302)
    org_id = user.org_id

    if plan not in PLAN_TIERS:
        plan = DEFAULT_PLAN

    tier = PLAN_TIERS[plan]

    try:
        db.execute(
            text("""
                UPDATE organizations
                SET plan = :plan,
                    max_users = :max_users,
                    max_clients = :max_clients,
                    max_storage_gb = :max_storage_gb,
                    updated_at = NOW()
                WHERE id = :org_id
            """),
            {
                "plan": plan,
                "max_users": tier["max_users"],
                "max_clients": tier["max_clients"],
                "max_storage_gb": tier["max_storage_gb"],
                "org_id": org_id,
            },
        )
        db.commit()

        # If Stripe is configured, create checkout session for priced plans.
        # Contact-only plans (Enterprise "sob consulta") have no self-service
        # checkout and fall through to /setup/complete.
        if (
            settings.STRIPE_SECRET_KEY
            and STRIPE_AVAILABLE
            and not tier.get("contact_only")
        ):
            stripe_price_id = tier.get("stripe_price_id", "")
            if stripe_price_id:
                try:
                    stripe.api_key = settings.STRIPE_SECRET_KEY

                    # Get org for customer creation
                    org = _get_setup_org(db, request)

                    # Create or retrieve Stripe customer
                    customer_id = org.get("stripe_customer_id") if org else None
                    if not customer_id:
                        customer = stripe.Customer.create(
                            email=org.get("email", "") if org else "",
                            name=org.get("name", "") if org else "",
                            metadata={"org_id": str(org_id), "org_slug": org.get("slug", "") if org else ""},
                        )
                        customer_id = customer.id
                        db.execute(
                            text("UPDATE organizations SET stripe_customer_id = :cid WHERE id = :oid"),
                            {"cid": customer_id, "oid": org_id},
                        )
                        db.commit()

                    # Create Stripe Checkout Session
                    session = stripe.checkout.Session.create(
                        customer=customer_id,
                        payment_method_types=["card"],
                        line_items=[{"price": stripe_price_id, "quantity": 1}],
                        mode="subscription",
                        success_url=f"{settings.BASE_URL}{PREFIX}/setup/complete?session_id={{CHECKOUT_SESSION_ID}}",
                        cancel_url=f"{settings.BASE_URL}{PREFIX}/setup/plan",
                        metadata={
                            "org_id": str(org_id),
                            "plan": plan,
                        },
                    )

                    return RedirectResponse(url=session.url, status_code=303)

                except Exception as e:
                    logger.error(f"Stripe checkout creation failed: {e}")
                    # Fall through to complete without payment
            else:
                logger.warning(f"No stripe_price_id configured for plan '{plan}', skipping checkout")

        return RedirectResponse(url=f"{PREFIX}/setup/complete", status_code=302)

    except Exception as e:
        db.rollback()
        logger.error(f"Setup plan save failed: {e}")
        return RedirectResponse(
            url=f"{PREFIX}/setup/plan?error=Failed+to+save+plan",
            status_code=302,
        )


@router.get("/setup/complete", response_class=HTMLResponse)
async def setup_complete(request: Request, db: Session = Depends(get_db)):
    """Setup complete - redirect to dashboard."""
    org = _get_setup_org(db, request)
    if not org:
        return RedirectResponse(url=f"{PREFIX}/signup", status_code=302)
    user = get_current_user(request, db)

    response = templates.TemplateResponse("onboarding/complete.html", {
        "request": request,
        "PREFIX": PREFIX,
        "org": org,
        "user": user,
    })
    # Clean up setup cookies
    response.delete_cookie("setup_step", path="/")
    response.delete_cookie("setup_org_id", path="/")
    return response


# =========================================================================
# First-Login Wizard (individual user onboarding)
# =========================================================================

@router.get("/first-login", response_class=HTMLResponse)
async def first_login_page(request: Request, db: Session = Depends(get_db)):
    """Show first-login wizard for users with must_change_password=True."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    if not getattr(user, 'must_change_password', False):
        return RedirectResponse(url=f"{PREFIX}/dashboard", status_code=302)

    return templates.TemplateResponse("onboarding/first_login.html", {
        "request": request,
        "PREFIX": PREFIX,
        "user": user,
    })


@router.get("/first-login/connections", response_class=HTMLResponse)
async def first_login_connections(request: Request, db: Session = Depends(get_db)):
    """Post-password first-login checklist for essential integrations."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    return templates.TemplateResponse("app/onboarding/connections.html", {
        "request": request,
        "PREFIX": PREFIX,
        "user": user,
    })


@router.post("/first-login")
async def first_login_submit(
    request: Request,
    name: str = Form(...),
    phone: str = Form(""),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    """Process first-login wizard: update profile + change password."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    errors = []
    if not name.strip():
        errors.append("Nome é obrigatório")
    if len(new_password) < 6:
        errors.append("Senha deve ter pelo menos 6 caracteres")
    if new_password != confirm_password:
        errors.append("Senhas não coincidem")

    if errors:
        return templates.TemplateResponse("onboarding/first_login.html", {
            "request": request,
            "PREFIX": PREFIX,
            "user": user,
            "errors": errors,
        })

    # Update user profile
    user.name = name.strip()
    if phone.strip():
        user.phone = phone.strip()
    user.password_hash = User.hash_password(new_password)
    user.must_change_password = False
    user.last_password_change = datetime.now()
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/first-login/connections", status_code=302)
