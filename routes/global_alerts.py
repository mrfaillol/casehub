"""
CaseHub - Global Alerts Routes
Manage system-wide alert banners.
"""
from typing import Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

from core.form_utils import form_int, form_float
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.request_utils import get_request_org_id
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, User
from auth import get_current_user
from services.global_alerts_service import (
    global_alerts_service, CREATE_GLOBAL_ALERTS_TABLE,
    AlertType, AlertTarget
)

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/global-alerts", tags=["global_alerts"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py


def ensure_tables(db: Session):
    """Ensure global alerts tables exist."""
    try:
        db.execute(text(CREATE_GLOBAL_ALERTS_TABLE))
        db.commit()
    except Exception as e:
        db.rollback()


@router.get("", response_class=HTMLResponse)
async def alerts_list(
    request: Request,
    show_inactive: bool = False,
    db: Session = Depends(get_db)
):
    """List all global alerts (admin view)."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    # Get alerts
    query = """
        SELECT a.*, u.name as creator_name
        FROM global_alerts a
        LEFT JOIN users u ON a.created_by = u.id
        WHERE a.org_id = :org_id
    """
    params = {"org_id": get_request_org_id(request)}

    if not show_inactive:
        query += " AND a.is_active = true"

    query += " ORDER BY a.priority DESC, a.created_at DESC"

    try:
        result = db.execute(text(query), params)
        alerts = result.fetchall()
    except Exception:
        db.rollback()
        alerts = []

    return templates.TemplateResponse("app/global_alerts/list.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "alerts": alerts,
        "show_inactive": show_inactive,
        "alert_types": [t.value for t in AlertType],
        "alert_targets": [t.value for t in AlertTarget]
    })


@router.get("/new", response_class=HTMLResponse)
async def new_alert(
    request: Request,
    db: Session = Depends(get_db)
):
    """Create new global alert form."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    # Get cases and clients for targeting
    org_id = get_request_org_id(request)
    try:
        cases = db.execute(text("SELECT id, case_number, case_name FROM cases WHERE org_id = :org_id ORDER BY created_at DESC LIMIT 100"), {"org_id": org_id}).fetchall()
        clients = db.execute(text("SELECT id, first_name, last_name FROM clients WHERE org_id = :org_id ORDER BY created_at DESC LIMIT 100"), {"org_id": org_id}).fetchall()
    except Exception as e:
        logger.error("Failed to fetch cases/clients for global alert targeting: %s", e)
        db.rollback()
        cases = []
        clients = []

    return templates.TemplateResponse("app/global_alerts/create.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "alert_types": [t.value for t in AlertType],
        "alert_targets": [t.value for t in AlertTarget],
        "cases": cases,
        "clients": clients
    })


@router.post("/create")
async def create_alert(
    request: Request,
    title: str = Form(...),
    message: str = Form(...),
    alert_type: str = Form("info"),
    target: str = Form("all"),
    target_id: str = Form(None),
    start_date: str = Form(None),
    end_date: str = Form(None),
    dismissible: bool = Form(True),
    priority: int = Form(0),
    db: Session = Depends(get_db)
):
    """Create a new global alert."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Convert form strings to proper types
    target_id = form_int(target_id)

    ensure_tables(db)

    # Parse dates
    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date.replace('T', ' '))
        except Exception as e:
            logger.error("Failed to parse start_date '%s': %s", start_date, e)
            start_dt = datetime.now()
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date.replace('T', ' '))
        except Exception:
            db.rollback()

    try:
        db.execute(text("""
            INSERT INTO global_alerts
            (title, message, alert_type, target, target_id, start_date, end_date, dismissible, priority, created_by, org_id)
            VALUES (:title, :message, :type, :target, :target_id, :start, :end, :dismiss, :priority, :uid, :org_id)
        """), {
            "title": title,
            "message": message,
            "type": alert_type,
            "target": target,
            "target_id": target_id if target in ['case', 'client'] else None,
            "start": start_dt or datetime.now(),
            "end": end_dt,
            "dismiss": dismissible,
            "priority": priority,
            "uid": user.id,
            "org_id": request.state.org_id
        })
        db.commit()

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/global-alerts", status_code=302)


@router.post("/{alert_id}/toggle")
async def toggle_alert(
    request: Request,
    alert_id: int,
    db: Session = Depends(get_db)
):
    """Toggle alert active status."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        db.execute(text("""
            UPDATE global_alerts
            SET is_active = NOT is_active, updated_at = NOW()
            WHERE id = :id AND org_id = :org_id
        """), {"id": alert_id, "org_id": request.state.org_id})
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/global-alerts", status_code=302)


@router.post("/{alert_id}/delete")
async def delete_alert(
    request: Request,
    alert_id: int,
    db: Session = Depends(get_db)
):
    """Delete an alert."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        db.execute(text("DELETE FROM global_alerts WHERE id = :id AND org_id = :org_id"), {"id": alert_id, "org_id": request.state.org_id})
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/global-alerts", status_code=302)


# === API Endpoints ===

@router.get("/api/active", response_class=JSONResponse)
async def get_active_alerts(
    request: Request,
    case_id: Optional[int] = None,
    client_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """API: Get active alerts for the current context."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})

    ensure_tables(db)

    # Get user's dismissed alerts
    try:
        dismissed_result = db.execute(text(
            "SELECT alert_id FROM dismissed_alerts WHERE user_id = :uid"
        ), {"uid": user.id})
        dismissed_ids = [row.alert_id for row in dismissed_result.fetchall()]
    except Exception:
        db.rollback()
        dismissed_ids = []

    # Get active alerts
    try:
        result = db.execute(text("""
            SELECT id, title, message, alert_type, target, target_id, dismissible, priority
            FROM global_alerts
            WHERE is_active = true
              AND org_id = :org_id
              AND (start_date IS NULL OR start_date <= NOW())
              AND (end_date IS NULL OR end_date >= NOW())
            ORDER BY priority DESC, created_at DESC
        """), {"org_id": request.state.org_id})
        alerts = [dict(row._mapping) for row in result.fetchall()]
    except Exception:
        db.rollback()
        alerts = []

    # Filter based on context
    filtered = global_alerts_service.filter_alerts_for_user(
        alerts,
        user_type="staff",
        case_id=case_id,
        client_id=client_id,
        dismissed_ids=dismissed_ids
    )

    # Add Bootstrap classes and icons
    for alert in filtered:
        alert["bootstrap_class"] = global_alerts_service.get_bootstrap_class(alert.get("alert_type"))
        alert["icon"] = global_alerts_service.get_icon(alert.get("alert_type"))

    return JSONResponse(content=filtered)


@router.post("/api/dismiss/{alert_id}")
async def dismiss_alert(
    request: Request,
    alert_id: int,
    db: Session = Depends(get_db)
):
    """API: Dismiss an alert for the current user."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})

    try:
        db.execute(text("""
            INSERT INTO dismissed_alerts (alert_id, user_id)
            VALUES (:aid, :uid)
            ON CONFLICT (alert_id, user_id) DO NOTHING
        """), {"aid": alert_id, "uid": user.id})
        db.commit()
        return JSONResponse(content={"success": True})
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"error": str(e)})
