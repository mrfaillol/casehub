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

from models import get_db, User
from models.tenant import Organization
from auth import get_current_user, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from core.template_config import templates, PREFIX
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/superadmin", tags=["superadmin"])

# Canonical plans (Victor, 28/05/2026): office R$129/mês + Enterprise sob consulta.
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
