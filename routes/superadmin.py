"""
CaseHub - Super Admin Panel Routes
Platform-level administration: org management, metrics, impersonation.
Access restricted to user_type='superadmin'.
"""
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from sqlalchemy.exc import SQLAlchemyError

from models import get_db, User
from models.tenant import Organization
from auth import get_current_user, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from core.template_config import templates, PREFIX
from core import feature_flags
from core.stepup import STEPUP_COOKIE_NAME, verify_token
from config import settings
from urllib.parse import quote

# Flag name (default OFF) gating 2FA enforcement on sensitive superadmin paths.
# Registered in core/feature_flags.py; env var CASEHUB_FF_SUPERADMIN_2FA_ENFORCEMENT.
SUPERADMIN_2FA_FLAG = "superadmin_2fa_enforcement"

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/superadmin", tags=["superadmin"])

# Canonical plans (Equipe CaseHub, 28/05/2026): office R$129/mês + Enterprise sob consulta.
# Enterprise has no fixed price (0 here => not counted as fixed MRR).
PLAN_PRICES = {
    "office": 129,
    "enterprise": 0,
}


def require_superadmin(request: Request, db: Session) -> User:
    """Require superadmin user. Returns user or None."""
    user = get_current_user(request, db)
    if not user or user.user_type != "superadmin":
        return None
    return user


def enforce_superadmin_2fa(request: Request, db: Session, user: User):
    """Gate sensitive superadmin actions on TOTP 2FA (issue #805 / T10, CWE-308).

    Returns ``None`` to allow the action to proceed, or a ``RedirectResponse``
    the caller MUST return to interrupt the action.

    HARD SAFETY CONTRACT (must never regress):

    * The feature flag ``superadmin_2fa_enforcement`` defaults OFF. While OFF
      (the current prod state) this function ALWAYS returns ``None`` — the
      sensitive paths behave exactly as before, with no new 2FA requirement.
      It can never lock a superadmin out of superadmin.

    * When the flag is ON:
        - superadmin has NOT enrolled  -> redirect to the 2FA setup page
          (enrollment grace). This is a guided redirect, NOT a 403 dead-end,
          so a superadmin without 2FA can always still reach /2fa/setup and
          enroll. No lockout.
        - superadmin IS enrolled but presents NO fresh step-up proof ->
          redirect to the step-up challenge (/2fa/step-up?next=...) to enter a
          current TOTP code. Also a guided redirect, never a 403 dead-end.
        - superadmin IS enrolled AND presents a valid, unexpired, user-bound
          step-up cookie -> allow (return None).

    STEP-UP VERIFICATION (T10 real fix, supersedes the enrollment-only check
    from PR #806): enrollment != verification. A stolen superadmin JWT alone no
    longer passes a sensitive action while the flag is ON — the actor must also
    prove a FRESH TOTP at action time. The proof is a short-lived, signed,
    user-bound cookie (``sa_2fa_stepup``; see core/stepup.py) minted by
    POST /2fa/step-up. A missing / expired / tampered / wrong-user cookie ->
    re-challenge (never a lockout). Auth here is a stateless JWT cookie with no
    SessionMiddleware, so the signed cookie is how "verified THIS session
    recently" is expressed without server-side session state.
    """
    if not feature_flags.is_enabled(SUPERADMIN_2FA_FLAG):
        # Flag OFF (default / current prod): behave exactly as before.
        return None

    # Flag ON. Determine enrollment. Sentinela review (2026-06-14, PR #806):
    # fail-open ONLY on a transient DB/operational error (SQLAlchemyError) so the
    # single platform admin is never locked out by a DB hiccup — logged at ERROR
    # so a *persistent* fail-open is detected, not masked. Any OTHER exception
    # (e.g. ImportError / signature drift in TwoFactorService) is left to
    # propagate loudly rather than silently disabling the control.
    from services.two_factor import TwoFactorService

    try:
        enrolled = bool(TwoFactorService(db).is_2fa_required(user.id))
    except SQLAlchemyError as exc:  # transient DB error: fail-open, but loud
        logger.error(
            "Superadmin 2FA enforcement could not read 2FA state for user %s "
            "(DB error -> allowing through to avoid lockout; investigate if "
            "persistent): %s",
            getattr(user, "id", "?"),
            exc,
        )
        return None

    if enrolled:
        # Enrolled: require a FRESH, signed, user-bound step-up proof. Enrollment
        # alone is NOT enough (closes the enrollment!=verification gap of #806).
        stepup_cookie = request.cookies.get(STEPUP_COOKIE_NAME)
        if verify_token(stepup_cookie, user.id):
            return None

        # No valid/fresh proof -> guide to the step-up challenge (NOT a 403).
        # Bounce back to the originally-requested path after verifying.
        try:
            next_path = request.url.path
        except Exception:
            next_path = f"{PREFIX}/superadmin"
        logger.info(
            "Superadmin %s hit a 2FA-gated path without a fresh step-up proof; "
            "redirecting to step-up challenge (flag ON).",
            getattr(user, "email", "?"),
        )
        return RedirectResponse(
            url=f"{PREFIX}/2fa/step-up?next={quote(next_path, safe='')}",
            status_code=302,
        )

    # Flag ON but not enrolled: guide to setup (enrollment grace, no dead-end).
    logger.warning(
        "Superadmin %s hit a 2FA-gated path without 2FA enrolled; "
        "redirecting to setup (flag ON).",
        getattr(user, "email", "?"),
    )
    return RedirectResponse(
        url=f"{PREFIX}/2fa/setup?enroll_required=superadmin",
        status_code=302,
    )


# =========================================================================
# Dashboard
# =========================================================================

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def superadmin_dashboard(request: Request, db: Session = Depends(get_db)):
    """Main super admin dashboard with key metrics."""
    user = require_superadmin(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Total orgs
    total_orgs = db.query(func.count(Organization.id)).scalar() or 0
    active_orgs = db.query(func.count(Organization.id)).filter(
        Organization.is_active == True
    ).scalar() or 0
    inactive_orgs = total_orgs - active_orgs

    # Total users
    total_users = db.query(func.count(User.id)).scalar() or 0

    # MRR calculation. Canonical plan: office R$129/mês. Enterprise é sob
    # consulta (sem preço fixo => 0). Legacy keys mapeados para contagem
    # histórica de orgs ainda armazenadas como starter/professional.
    mrr_result = db.execute(text("""
        SELECT COALESCE(SUM(
            CASE plan
                WHEN 'office' THEN 129
                WHEN 'starter' THEN 299
                WHEN 'professional' THEN 699
                WHEN 'enterprise' THEN 0
                ELSE 0
            END
        ), 0) as mrr
        FROM organizations
        WHERE is_active = TRUE
          AND subscription_status = 'active'
    """)).scalar() or 0

    # Recent orgs
    recent_orgs = db.query(Organization).order_by(
        Organization.created_at.desc()
    ).limit(5).all()

    # Signups this month
    first_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    signups_this_month = db.query(func.count(Organization.id)).filter(
        Organization.created_at >= first_of_month
    ).scalar() or 0

    return templates.TemplateResponse("app/superadmin/dashboard.html", {
        "request": request,
        "PREFIX": PREFIX,
        "user": user,
        "total_orgs": total_orgs,
        "active_orgs": active_orgs,
        "inactive_orgs": inactive_orgs,
        "total_users": total_users,
        "mrr": mrr_result,
        "signups_this_month": signups_this_month,
        "recent_orgs": recent_orgs,
    })


# =========================================================================
# Organizations List
# =========================================================================

@router.get("/orgs", response_class=HTMLResponse)
async def superadmin_orgs(request: Request, db: Session = Depends(get_db)):
    """List all organizations."""
    user = require_superadmin(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Get all orgs with user counts
    orgs_raw = db.execute(text("""
        SELECT o.*,
               COALESCE(u.user_count, 0) as user_count
        FROM organizations o
        LEFT JOIN (
            SELECT org_id, COUNT(*) as user_count
            FROM users
            WHERE org_id IS NOT NULL
            GROUP BY org_id
        ) u ON u.org_id = o.id
        ORDER BY o.created_at DESC
    """)).mappings().all()

    # Fallback: if users table has no org_id column, just list orgs
    if not orgs_raw:
        orgs = db.query(Organization).order_by(Organization.created_at.desc()).all()
        orgs_data = []
        for o in orgs:
            orgs_data.append({
                "id": o.id,
                "name": o.name,
                "slug": o.slug,
                "plan": o.plan,
                "is_active": o.is_active,
                "subscription_status": o.subscription_status,
                "created_at": o.created_at,
                "user_count": 0,
                "email": o.email,
            })
    else:
        orgs_data = [dict(r) for r in orgs_raw]

    return templates.TemplateResponse("app/superadmin/orgs.html", {
        "request": request,
        "PREFIX": PREFIX,
        "user": user,
        "orgs": orgs_data,
        "plan_prices": PLAN_PRICES,
    })


# =========================================================================
# Organization Detail
# =========================================================================

@router.get("/orgs/{org_id}", response_class=HTMLResponse)
async def superadmin_org_detail(org_id: int, request: Request, db: Session = Depends(get_db)):
    """View organization details."""
    user = require_superadmin(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Get users for this org
    try:
        org_users = db.execute(text(
            "SELECT * FROM users WHERE org_id = :org_id ORDER BY created_at DESC"
        ), {"org_id": org_id}).mappings().all()
        org_users = [dict(u) for u in org_users]
    except Exception:
        # org_id column might not exist on users
        org_users = []

    # Get counts
    try:
        case_count = db.execute(text(
            "SELECT COUNT(*) FROM cases WHERE org_id = :org_id"
        ), {"org_id": org_id}).scalar() or 0
    except Exception:
        case_count = 0

    try:
        client_count = db.execute(text(
            "SELECT COUNT(*) FROM clients WHERE org_id = :org_id"
        ), {"org_id": org_id}).scalar() or 0
    except Exception:
        client_count = 0

    try:
        doc_count = db.execute(text(
            "SELECT COUNT(*) FROM documents WHERE org_id = :org_id"
        ), {"org_id": org_id}).scalar() or 0
    except Exception:
        doc_count = 0

    success = request.query_params.get("success")
    error = request.query_params.get("error")

    return templates.TemplateResponse("app/superadmin/org_detail.html", {
        "request": request,
        "PREFIX": PREFIX,
        "user": user,
        "org": org,
        "org_users": org_users,
        "case_count": case_count,
        "client_count": client_count,
        "doc_count": doc_count,
        "plan_prices": PLAN_PRICES,
        "success": success,
        "error": error,
    })


# =========================================================================
# Toggle Org Active/Inactive
# =========================================================================

@router.post("/orgs/{org_id}/toggle")
async def superadmin_toggle_org(org_id: int, request: Request, db: Session = Depends(get_db)):
    """Activate or deactivate an organization."""
    user = require_superadmin(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # T10 (#805): gate org enable/disable on 2FA when the (default-OFF) flag is ON.
    guard = enforce_superadmin_2fa(request, db, user)
    if guard is not None:
        return guard

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    new_status = not org.is_active
    try:
        db.execute(text("""
            UPDATE organizations
            SET is_active = :active, updated_at = NOW()
            WHERE id = :org_id
        """), {"active": new_status, "org_id": org_id})
        db.commit()

        action = "activated" if new_status else "deactivated"
        logger.info(f"Superadmin id={user.id} {action} org {org.slug} (id={org_id})")
        return RedirectResponse(
            url=f"{PREFIX}/superadmin/orgs/{org_id}?success=Organization+{action}",
            status_code=302,
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Toggle org failed: {e}")
        return RedirectResponse(
            url=f"{PREFIX}/superadmin/orgs/{org_id}?error=Failed+to+update+status",
            status_code=302,
        )


# =========================================================================
# Update Org Plan
# =========================================================================

@router.post("/orgs/{org_id}/update-plan")
async def superadmin_update_plan(
    org_id: int,
    request: Request,
    plan: str = Form(...),
    db: Session = Depends(get_db),
):
    """Change an organization's plan tier."""
    user = require_superadmin(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # T10 (#805): gate plan changes on 2FA when the (default-OFF) flag is ON.
    guard = enforce_superadmin_2fa(request, db, user)
    if guard is not None:
        return guard

    if plan not in PLAN_PRICES:
        return RedirectResponse(
            url=f"{PREFIX}/superadmin/orgs/{org_id}?error=Invalid+plan",
            status_code=302,
        )

    # Map plan limits. Usuários ILIMITADOS por enquanto em ambos os planos
    # (max_users = -1 => unlimited, ver middleware/plan_enforcement.py).
    plan_limits = {
        "office": (-1, 100, 50),
        "enterprise": (-1, 9999, 500),
    }
    max_users, max_clients, max_storage = plan_limits[plan]

    try:
        db.execute(text("""
            UPDATE organizations
            SET plan = :plan,
                max_users = :max_users,
                max_clients = :max_clients,
                max_storage_gb = :max_storage,
                updated_at = NOW()
            WHERE id = :org_id
        """), {
            "plan": plan,
            "max_users": max_users,
            "max_clients": max_clients,
            "max_storage": max_storage,
            "org_id": org_id,
        })
        db.commit()

        logger.info(f"Superadmin id={user.id} changed org {org_id} to plan={plan}")
        return RedirectResponse(
            url=f"{PREFIX}/superadmin/orgs/{org_id}?success=Plan+updated+to+{plan}",
            status_code=302,
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Update plan failed: {e}")
        return RedirectResponse(
            url=f"{PREFIX}/superadmin/orgs/{org_id}?error=Failed+to+update+plan",
            status_code=302,
        )


# =========================================================================
# Metrics API (for charts)
# =========================================================================

@router.get("/metrics", response_class=JSONResponse)
async def superadmin_metrics(request: Request, db: Session = Depends(get_db)):
    """Return MRR chart data, signup trend, churn."""
    user = require_superadmin(request, db)
    if not user:
        return JSONResponse(status_code=403, content={"error": "Forbidden"})

    # Monthly signup trend (last 6 months)
    months = []
    signup_counts = []
    mrr_values = []
    now = datetime.utcnow()

    for i in range(5, -1, -1):
        month_date = now - timedelta(days=i * 30)
        month_start = month_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if i > 0:
            next_month = (month_start + timedelta(days=32)).replace(day=1)
        else:
            next_month = now

        label = month_start.strftime("%b %Y")
        months.append(label)

        count = db.query(func.count(Organization.id)).filter(
            Organization.created_at >= month_start,
            Organization.created_at < next_month,
        ).scalar() or 0
        signup_counts.append(count)

        # MRR for that month (active orgs as of month end)
        mrr = db.execute(text("""
            SELECT COALESCE(SUM(
                CASE plan
                    WHEN 'office' THEN 129
                    WHEN 'starter' THEN 299
                    WHEN 'professional' THEN 699
                    WHEN 'enterprise' THEN 0
                    ELSE 0
                END
            ), 0)
            FROM organizations
            WHERE is_active = TRUE
              AND created_at < :cutoff
        """), {"cutoff": next_month}).scalar() or 0
        mrr_values.append(int(mrr))

    return {
        "months": months,
        "signups": signup_counts,
        "mrr": mrr_values,
    }


# =========================================================================
# Impersonation
# =========================================================================

@router.post("/impersonate/{user_id}")
async def superadmin_impersonate(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Login as any user (sets special impersonation cookie)."""
    admin = require_superadmin(request, db)
    if not admin:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # T10 (#805): gate impersonation on 2FA when the (default-OFF) flag is ON.
    guard = enforce_superadmin_2fa(request, db, admin)
    if guard is not None:
        return guard

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Create token for target user.
    # Sentinela T1: include target user's org_id so middleware/auth pin the
    # impersonated session to the right tenant.
    token = create_access_token(data={"sub": target_user.email, "org_id": target_user.org_id})

    logger.warning(
        f"IMPERSONATION: superadmin {admin.email} impersonating "
        f"{target_user.email} (user_id={user_id})"
    )

    response = RedirectResponse(url=f"{PREFIX}/dashboard", status_code=302)
    response.set_cookie(
        key="casehub_token",
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
        samesite="lax",
    )
    # Set impersonation marker so the admin can "exit" back
    response.set_cookie(
        key="impersonating",
        value=admin.email,
        httponly=True,
        max_age=3600,
        path="/",
    )
    return response


@router.get("/exit-impersonation")
async def exit_impersonation(request: Request, db: Session = Depends(get_db)):
    """Exit impersonation and return to superadmin session."""
    original_email = request.cookies.get("impersonating")
    if not original_email:
        return RedirectResponse(url=f"{PREFIX}/superadmin", status_code=302)

    # Restore original admin session
    # Sentinela T1: re-embed org_id so the restored superadmin token is also
    # tenant-aware. Fall back to None if the original user can no longer be
    # found (shouldn't happen in practice since the cookie matched moments ago).
    original_user = db.query(User).filter(User.email == original_email).first()
    original_org_id = original_user.org_id if original_user else None
    token = create_access_token(data={"sub": original_email, "org_id": original_org_id})
    response = RedirectResponse(url=f"{PREFIX}/superadmin", status_code=302)
    response.set_cookie(
        key="casehub_token",
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
        samesite="lax",
    )
    response.delete_cookie("impersonating", path="/")
    return response
