"""
CaseHub - Webhooks Routes
Allows managing webhooks for entity events
"""
from core.form_utils import form_int, form_float
from fastapi import APIRouter, Depends, Request, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
import json
import httpx
from datetime import datetime

from models import get_db
from auth import get_current_user

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py

# Event types that can trigger webhooks
EVENT_TYPES = [
    "client.created",
    "client.updated",
    "client.deleted",
    "case.created",
    "case.updated",
    "case.deleted",
    "case.status_changed",
    "document.uploaded",
    "document.deleted",
    "task.created",
    "task.completed",
    "billing.payment_received",
]

# ============================================
# WEBHOOK MANAGEMENT
# ============================================

@router.get("", response_class=HTMLResponse)
async def list_webhooks(
    request: Request,
    entity_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all webhooks"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    query = "SELECT * FROM entity_webhooks WHERE org_id = :org_id"
    params = {"org_id": request.state.org_id}

    if entity_type:
        query += " AND entity_type = :entity_type"
        params["entity_type"] = entity_type

    query += " ORDER BY entity_type, event_type"
    
    result = db.execute(text(query), params)
    webhooks = result.fetchall()
    
    return templates.TemplateResponse("app/webhooks/list.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "webhooks": webhooks,
        "entity_type": entity_type or "",
        "entity_types": ["client", "case", "document", "task", "billing"]
    })

@router.get("/new", response_class=HTMLResponse)
async def new_webhook(request: Request, db: Session = Depends(get_db)):
    """Form to create new webhook"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    return templates.TemplateResponse("app/webhooks/form.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "webhook": None,
        "action": "Create",
        "entity_types": ["client", "case", "document", "task", "billing"],
        "event_types": EVENT_TYPES
    })

@router.post("/new")
async def create_webhook(
    request: Request,
    entity_type: str = Form(...),
    event_type: str = Form(...),
    webhook_url: str = Form(...),
    headers: str = Form(None),
    enabled: bool = Form(True),
    entity_id: str = Form(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Convert form strings to proper types
    entity_id = form_int(entity_id)

    if headers and len(headers) > 4096:
        raise HTTPException(status_code=400, detail="Headers too large (max 4KB)")

    headers_json = None
    if headers:
        try:
            headers_json = json.loads(headers)
        except json.JSONDecodeError:
            headers_json = None

    db.execute(
        text("""
            INSERT INTO entity_webhooks (entity_type, entity_id, event_type, webhook_url, headers, enabled, org_id)
            VALUES (:entity_type, :entity_id, :event_type, :webhook_url, :headers, :enabled, :org_id)
        """),
        {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "event_type": event_type,
            "webhook_url": webhook_url,
            "headers": json.dumps(headers_json) if headers_json else None,
            "enabled": enabled,
            "org_id": request.state.org_id
        }
    )
    db.commit()
    
    return RedirectResponse(url=f"{PREFIX}/webhooks", status_code=302)

@router.get("/{webhook_id}/edit", response_class=HTMLResponse)
async def edit_webhook_form(request: Request, webhook_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    result = db.execute(text("SELECT * FROM entity_webhooks WHERE id = :id AND org_id = :org_id"), {"id": webhook_id, "org_id": request.state.org_id})
    webhook = result.fetchone()

    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    return templates.TemplateResponse("app/webhooks/form.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "webhook": webhook,
        "action": "Update",
        "entity_types": ["client", "case", "document", "task", "billing"],
        "event_types": EVENT_TYPES
    })

@router.post("/{webhook_id}/edit")
async def update_webhook(
    webhook_id: int,
    request: Request,
    entity_type: str = Form(...),
    event_type: str = Form(...),
    webhook_url: str = Form(...),
    headers: str = Form(None),
    enabled: bool = Form(False),
    entity_id: str = Form(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Convert form strings to proper types
    entity_id = form_int(entity_id)

    if headers and len(headers) > 4096:
        raise HTTPException(status_code=400, detail="Headers too large (max 4KB)")

    headers_json = None
    if headers:
        try:
            headers_json = json.loads(headers)
        except json.JSONDecodeError:
            headers_json = None

    db.execute(
        text("""
            UPDATE entity_webhooks
            SET entity_type = :entity_type, entity_id = :entity_id, event_type = :event_type,
                webhook_url = :webhook_url, headers = :headers, enabled = :enabled, updated_at = NOW()
            WHERE id = :id AND org_id = :org_id
        """),
        {
            "id": webhook_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "event_type": event_type,
            "webhook_url": webhook_url,
            "headers": json.dumps(headers_json) if headers_json else None,
            "enabled": enabled,
            "org_id": request.state.org_id
        }
    )
    db.commit()
    
    return RedirectResponse(url=f"{PREFIX}/webhooks", status_code=302)

@router.post("/{webhook_id}/delete")
async def delete_webhook(webhook_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    db.execute(text("DELETE FROM entity_webhooks WHERE id = :id AND org_id = :org_id"), {"id": webhook_id, "org_id": request.state.org_id})
    db.commit()
    
    return RedirectResponse(url=f"{PREFIX}/webhooks", status_code=302)

@router.get("/{webhook_id}/logs", response_class=HTMLResponse)
async def view_webhook_logs(request: Request, webhook_id: int, db: Session = Depends(get_db)):
    """View webhook execution logs"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    result = db.execute(text("SELECT * FROM entity_webhooks WHERE id = :id AND org_id = :org_id"), {"id": webhook_id, "org_id": request.state.org_id})
    webhook = result.fetchone()

    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    result = db.execute(
        text("SELECT * FROM webhook_logs WHERE webhook_id = :webhook_id ORDER BY triggered_at DESC LIMIT 50"),
        {"webhook_id": webhook_id}
    )
    logs = result.fetchall()
    
    return templates.TemplateResponse("app/webhooks/logs.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "webhook": webhook,
        "logs": logs
    })

@router.post("/{webhook_id}/test")
async def test_webhook(webhook_id: int, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Test a webhook with sample data"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    
    result = db.execute(text("SELECT * FROM entity_webhooks WHERE id = :id AND org_id = :org_id"), {"id": webhook_id, "org_id": request.state.org_id})
    webhook = result.fetchone()

    if not webhook:
        return JSONResponse({"error": "Webhook not found"}, status_code=404)
    
    # Create test payload
    test_payload = {
        "event_type": webhook.event_type,
        "entity_type": webhook.entity_type,
        "test": True,
        "timestamp": datetime.now().isoformat(),
        "data": {
            "id": 1,
            "message": "This is a test webhook"
        }
    }
    
    # Trigger in background
    background_tasks.add_task(trigger_webhook, db, webhook.id, test_payload)
    
    return JSONResponse({"status": "Webhook test triggered", "payload": test_payload})


# ============================================
# WEBHOOK TRIGGER FUNCTIONS
# ============================================

async def trigger_webhook(db: Session, webhook_id: int, payload: dict):
    """Trigger a webhook with given payload"""
    result = db.execute(text("SELECT * FROM entity_webhooks WHERE id = :id"), {"id": webhook_id})
    webhook = result.fetchone()
    
    if not webhook or not webhook.enabled:
        return
    
    headers = {"Content-Type": "application/json"}
    if webhook.headers:
        try:
            custom_headers = json.loads(webhook.headers) if isinstance(webhook.headers, str) else webhook.headers
            headers.update(custom_headers)
        except (ValueError, KeyError):
            pass
    
    response_code = None
    response_body = None
    error_message = None
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                webhook.webhook_url,
                json=payload,
                headers=headers,
                timeout=30.0
            )
            response_code = response.status_code
            response_body = response.text[:1000]  # Limit response size
    except Exception as e:
        error_message = str(e)
        response_code = 0
    
    # Log the result
    db.execute(
        text("""
            INSERT INTO webhook_logs (webhook_id, event_type, payload, response_code, response_body, error_message)
            VALUES (:webhook_id, :event_type, :payload, :response_code, :response_body, :error_message)
        """),
        {
            "webhook_id": webhook_id,
            "event_type": payload.get("event_type"),
            "payload": json.dumps(payload),
            "response_code": response_code,
            "response_body": response_body,
            "error_message": error_message
        }
    )
    
    # Update webhook status
    if response_code is None or response_code >= 400:
        db.execute(
            text("""
                UPDATE entity_webhooks
                SET last_triggered_at = NOW(), last_response_code = :response_code,
                    failure_count = failure_count + 1
                WHERE id = :id
            """),
            {"id": webhook_id, "response_code": response_code}
        )
    else:
        db.execute(
            text("""
                UPDATE entity_webhooks
                SET last_triggered_at = NOW(), last_response_code = :response_code,
                    failure_count = 0
                WHERE id = :id
            """),
            {"id": webhook_id, "response_code": response_code}
        )
    
    db.commit()


async def trigger_webhooks_for_event(db: Session, event_type: str, entity_type: str, entity_id: int, data: dict):
    """Find and trigger all matching webhooks for an event"""
    result = db.execute(
        text("""
            SELECT * FROM entity_webhooks 
            WHERE enabled = true AND event_type = :event_type 
            AND (entity_type = :entity_type OR entity_type = '*')
            AND (entity_id IS NULL OR entity_id = :entity_id)
        """),
        {"event_type": event_type, "entity_type": entity_type, "entity_id": entity_id}
    )
    webhooks = result.fetchall()
    
    payload = {
        "event_type": event_type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "timestamp": datetime.now().isoformat(),
        "data": data
    }
    
    for webhook in webhooks:
        await trigger_webhook(db, webhook.id, payload)
