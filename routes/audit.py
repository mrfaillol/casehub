"""
CaseHub - Audit Trail Routes
View system activity and audit logs
"""
from datetime import datetime, date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, User
from auth import get_current_user
from models.tenant import tenant_query
from middleware.features import require_feature
from i18n import get_translations

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/audit", tags=["audit"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py


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


@router.get("", response_class=HTMLResponse)
async def audit_log(
    request: Request,
    action: Optional[str] = None,
    entity: Optional[str] = None,
    user_id: Optional[int] = None,
    days: int = 7,
    db: Session = Depends(get_db)
):
    """View audit log."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Only admins can view full audit log
    if user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    # Build query
    query = """
        SELECT al.*, u.name as user_name
        FROM audit_log al
        LEFT JOIN users u ON al.user_id = u.id
        WHERE al.created_at >= :since AND al.org_id = :org_id
    """
    params = {"since": datetime.now() - timedelta(days=days), "limit": 500, "org_id": request.state.org_id}

    if action:
        query += " AND al.action = :action"
        params["action"] = action
    if entity:
        query += " AND al.entity_type = :entity"
        params["entity"] = entity
    if user_id:
        query += " AND al.user_id = :user_id"
        params["user_id"] = user_id

    query += " ORDER BY al.created_at DESC LIMIT :limit"

    logs = db.execute(text(query), params).fetchall()

    # Get filter options
    actions = db.execute(text("SELECT DISTINCT action FROM audit_log WHERE org_id = :org_id ORDER BY action"), {"org_id": request.state.org_id}).fetchall()
    entities = db.execute(text("SELECT DISTINCT entity_type FROM audit_log WHERE org_id = :org_id ORDER BY entity_type"), {"org_id": request.state.org_id}).fetchall()
    users = tenant_query(db, User, request.state.org_id).filter(User.enabled == True).all()

    # Get stats
    stats = {}
    stats["total"] = db.execute(text("SELECT COUNT(*) FROM audit_log WHERE created_at >= :since AND org_id = :org_id"),
                                {"since": datetime.now() - timedelta(days=days), "org_id": request.state.org_id}).scalar()
    stats["logins"] = db.execute(text("SELECT COUNT(*) FROM audit_log WHERE action = 'login' AND created_at >= :since AND org_id = :org_id"),
                                 {"since": datetime.now() - timedelta(days=days), "org_id": request.state.org_id}).scalar()
    stats["creates"] = db.execute(text("SELECT COUNT(*) FROM audit_log WHERE action = 'create' AND created_at >= :since AND org_id = :org_id"),
                                  {"since": datetime.now() - timedelta(days=days), "org_id": request.state.org_id}).scalar()
    stats["updates"] = db.execute(text("SELECT COUNT(*) FROM audit_log WHERE action = 'update' AND created_at >= :since AND org_id = :org_id"),
                                  {"since": datetime.now() - timedelta(days=days), "org_id": request.state.org_id}).scalar()

    return templates.TemplateResponse("app/audit/log.html", {
        **get_context(request, db),
        "logs": logs,
        "actions": [a[0] for a in actions],
        "entities": [e[0] for e in entities],
        "users": users,
        "stats": stats,
        "filters": {
            "action": action,
            "entity": entity,
            "user_id": user_id,
            "days": days
        }
    })


@router.get("/entity/{entity_type}/{entity_id}", response_class=HTMLResponse)
async def entity_history(
    request: Request,
    entity_type: str,
    entity_id: int,
    db: Session = Depends(get_db)
):
    """View audit history for a specific entity."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Only admins can view entity audit history
    if user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    logs = db.execute(text("""
        SELECT al.*, u.name as user_name
        FROM audit_log al
        LEFT JOIN users u ON al.user_id = u.id
        WHERE al.entity_type = :entity_type AND al.entity_id = :entity_id AND al.org_id = :org_id
        ORDER BY al.created_at DESC
        LIMIT 100
    """), {"entity_type": entity_type, "entity_id": entity_id, "org_id": request.state.org_id}).fetchall()

    return templates.TemplateResponse("audit/entity_history.html", {
        **get_context(request, db),
        "logs": logs,
        "entity_type": entity_type,
        "entity_id": entity_id
    })


@router.get("/user/{user_id}", response_class=HTMLResponse)
async def user_activity(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db)
):
    """View activity for a specific user."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Only admins or the user themselves can view their activity
    if user.user_type != "admin" and user.id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    target_user = tenant_query(db, User, request.state.org_id).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    logs = db.execute(text("""
        SELECT * FROM audit_log
        WHERE user_id = :user_id AND org_id = :org_id
        ORDER BY created_at DESC
        LIMIT 200
    """), {"user_id": user_id, "org_id": request.state.org_id}).fetchall()

    return templates.TemplateResponse("audit/user_activity.html", {
        **get_context(request, db),
        "logs": logs,
        "target_user": target_user
    })


@router.get("/api/recent")
async def api_recent_activity(
    request: Request,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """API endpoint for recent activity (for dashboard widget)."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    logs = db.execute(text("""
        SELECT al.action, al.entity_type, al.description, al.created_at, u.name as user_name
        FROM audit_log al
        LEFT JOIN users u ON al.user_id = u.id
        WHERE al.org_id = :org_id
        ORDER BY al.created_at DESC
        LIMIT :limit
    """), {"limit": limit, "org_id": request.state.org_id}).fetchall()

    return JSONResponse([{
        "action": log.action,
        "entity_type": log.entity_type,
        "description": log.description,
        "created_at": log.created_at.isoformat() if log.created_at else None,
        "user_name": log.user_name
    } for log in logs])


@router.get("/export")
async def export_audit_log(
    request: Request,
    days: int = 30,
    db: Session = Depends(get_db),
    _feature=Depends(require_feature("audit")),
):
    """Export audit log as JSON."""
    user = get_current_user(request, db)
    if not user or user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    logs = db.execute(text("""
        SELECT al.*, u.name as user_name, u.email as user_email_full
        FROM audit_log al
        LEFT JOIN users u ON al.user_id = u.id
        WHERE al.created_at >= :since AND al.org_id = :org_id
        ORDER BY al.created_at DESC
    """), {"since": datetime.now() - timedelta(days=days), "org_id": request.state.org_id}).fetchall()

    # Log this export
    db.execute(text("""
        INSERT INTO audit_log (action, entity_type, user_id, user_email, description, created_at, org_id)
        VALUES ('export', 'audit_log', :user_id, :email, 'Exported audit log', NOW(), :org_id)
    """), {"user_id": user.id, "email": user.email, "org_id": request.state.org_id})
    db.commit()

    return JSONResponse([{
        "id": log.id,
        "action": log.action,
        "entity_type": log.entity_type,
        "entity_id": log.entity_id,
        "user_id": log.user_id,
        "user_name": log.user_name,
        "description": log.description,
        "details": log.details,
        "ip_address": log.ip_address,
        "created_at": log.created_at.isoformat() if log.created_at else None
    } for log in logs])
