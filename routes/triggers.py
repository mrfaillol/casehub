"""
CaseHub - Case Triggers Routes
Automation triggers for case status changes.
"""
from typing import Optional
import json

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, User, Case
from auth import get_current_user
from models.tenant import tenant_query
from services.triggers_service import triggers_service, CREATE_TRIGGERS_TABLE, TriggerEvent, ActionType

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/triggers", tags=["triggers"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py


def ensure_tables(db: Session):
    """Ensure triggers tables exist."""
    try:
        db.execute(text(CREATE_TRIGGERS_TABLE))
        db.commit()
    except Exception as e:
        db.rollback()


@router.get("", response_class=HTMLResponse)
async def triggers_list(request: Request, case_id: Optional[int] = None, db: Session = Depends(get_db)):
    """List all triggers."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    # Get triggers
    if case_id:
        triggers = triggers_service.get_triggers_for_case(db, case_id)
        case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    else:
        try:
            result = db.execute(text("""
                SELECT t.*, c.case_number, c.case_name
                FROM case_triggers t
                LEFT JOIN cases c ON t.case_id = c.id
                WHERE c.org_id = :org_id
                ORDER BY t.created_at DESC
            """), {"org_id": request.state.org_id})
            triggers = [dict(row._mapping) for row in result.fetchall()]
        except Exception:
            db.rollback()
            triggers = []
        case = None

    # Get cases for filter
    cases = tenant_query(db, Case, request.state.org_id).order_by(Case.created_at.desc()).limit(50).all()

    return templates.TemplateResponse("app/triggers/list.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "triggers": triggers,
        "cases": cases,
        "selected_case": case,
        "events": triggers_service.get_available_events(),
        "actions": triggers_service.get_available_actions()
    })


@router.get("/new", response_class=HTMLResponse)
async def new_trigger(request: Request, case_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Create new trigger form."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    cases = tenant_query(db, Case, request.state.org_id).order_by(Case.created_at.desc()).limit(50).all()
    selected_case = None
    if case_id:
        selected_case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()

    return templates.TemplateResponse("app/triggers/create.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "cases": cases,
        "selected_case": selected_case,
        "events": triggers_service.get_available_events(),
        "actions": triggers_service.get_available_actions()
    })


@router.post("/create")
async def create_trigger(
    request: Request,
    case_id: int = Form(...),
    name: str = Form(...),
    event: str = Form(...),
    from_status: str = Form(None),
    to_status: str = Form(None),
    action: str = Form(...),
    task_title: str = Form(None),
    task_description: str = Form(None),
    task_priority: str = Form("medium"),
    note_content: str = Form(None),
    reminder_days: int = Form(7),
    db: Session = Depends(get_db)
):
    """Create a new trigger."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ensure_tables(db)

    # Build condition
    condition = {}
    if from_status:
        condition["from_status"] = from_status
    if to_status:
        condition["to_status"] = to_status

    # Build action config
    action_config = {}
    if action == ActionType.CREATE_TASK:
        action_config = {
            "title": task_title or "Auto-created task",
            "description": task_description or "",
            "priority": task_priority
        }
    elif action == ActionType.ADD_NOTE:
        action_config = {"content": note_content or "Trigger executed"}
    elif action == ActionType.CREATE_REMINDER:
        action_config = {
            "title": task_title or "Reminder",
            "description": task_description or "",
            "days": reminder_days
        }
    elif action == ActionType.SEND_NOTIFICATION:
        action_config = {
            "title": task_title or "Notification",
            "message": task_description or ""
        }

    result = triggers_service.create_trigger(
        db, case_id, event, condition, action, action_config, name, user.id
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))

    return RedirectResponse(url=f"{PREFIX}/triggers?case_id={case_id}", status_code=302)


@router.post("/{trigger_id}/toggle")
async def toggle_trigger(request: Request, trigger_id: str, db: Session = Depends(get_db)):
    """Enable/disable a trigger."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        db.execute(text("""
            UPDATE case_triggers SET enabled = NOT enabled
            WHERE trigger_id = :tid
              AND case_id IN (SELECT id FROM cases WHERE org_id = :org_id)
        """), {"tid": trigger_id, "org_id": request.state.org_id})
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return JSONResponse(content={"success": True})


@router.post("/{trigger_id}/delete")
async def delete_trigger(request: Request, trigger_id: str, db: Session = Depends(get_db)):
    """Delete a trigger."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        db.execute(text("DELETE FROM case_triggers WHERE trigger_id = :tid AND case_id IN (SELECT id FROM cases WHERE org_id = :org_id)"), {"tid": trigger_id, "org_id": request.state.org_id})
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/triggers", status_code=302)


@router.get("/api/defaults/{visa_type}", response_class=JSONResponse)
async def get_default_triggers(request: Request, visa_type: str, db: Session = Depends(get_db)):
    """Get default triggers for a visa type."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})

    triggers = triggers_service.get_triggers_by_visa_type(visa_type)
    return JSONResponse(content=triggers)


@router.post("/api/apply-defaults/{case_id}")
async def apply_default_triggers(request: Request, case_id: int, db: Session = Depends(get_db)):
    """Apply default triggers for a case based on visa type."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})

    ensure_tables(db)

    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        return JSONResponse(status_code=404, content={"error": "Case not found"})

    default_triggers = triggers_service.get_triggers_by_visa_type(case.visa_type)

    created = 0
    for t in default_triggers:
        result = triggers_service.create_trigger(
            db, case_id, t["event"], t["condition"], t["action"], t["action_config"],
            f"{case.visa_type}: {t['action']}", user.id
        )
        if result.get("success"):
            created += 1

    return JSONResponse(content={"success": True, "created": created})
