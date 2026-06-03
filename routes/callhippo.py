"""
CaseHub - CallHippo Routes
SMS and Voice Call Management Interface
"""
import hmac
import os
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, Client
from auth import get_current_user
from models.tenant import tenant_query
from i18n import get_translations
from services.callhippo import callhippo_service

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/callhippo", tags=["callhippo"])


def _verify_callhippo_webhook_token(token: str) -> None:
    """C8: CallHippo does not sign webhooks, so we gate them with a path secret.

    The webhook URL configured in the CallHippo dashboard must embed a secret
    matching CALLHIPPO_WEBHOOK_TOKEN. Constant-time compare. Fail closed: if the
    secret is unset the webhook is disabled (returns 404, not 200) so an
    unconfigured deploy cannot accept forged inbound events / log poisoning.
    """
    expected = os.getenv("CALLHIPPO_WEBHOOK_TOKEN", "")
    if not expected or not token or not hmac.compare_digest(token, expected):
        # 404 (not 403) to avoid confirming the endpoint exists to scanners.
        raise HTTPException(status_code=404, detail="Not found")
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
async def callhippo_dashboard(request: Request, db: Session = Depends(get_db)):
    """CallHippo dashboard with SMS and calls."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Get clients with phone numbers for quick selection
    clients = tenant_query(db, Client, request.state.org_id).filter(
        Client.phone.isnot(None),
        Client.phone != ""
    ).order_by(Client.first_name).limit(50).all()

    return templates.TemplateResponse("app/callhippo/dashboard.html", {
        **get_context(request, db),
        "clients": clients,
        "is_configured": callhippo_service.is_configured(),
        "from_number": callhippo_service.from_number
    })


@router.get("/api/status")
async def api_get_status(request: Request, db: Session = Depends(get_db)):
    """Get CallHippo configuration status."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    account_info = await callhippo_service.get_account_info()

    return JSONResponse({
        "configured": callhippo_service.is_configured(),
        "from_number": callhippo_service.from_number,
        "account": account_info.get("data") if account_info.get("success") else None
    })


@router.get("/api/numbers")
async def api_get_numbers(request: Request, db: Session = Depends(get_db)):
    """Get available phone numbers."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    result = await callhippo_service.get_numbers()
    return JSONResponse(result)


@router.post("/api/sms/send")
async def api_send_sms(
    request: Request,
    to: str = Form(...),
    message: str = Form(...),
    db: Session = Depends(get_db)
):
    """Send SMS to a phone number."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    result = await callhippo_service.send_sms(to, message)

    # Log the SMS
    try:
        db.execute(text("""
            INSERT INTO callhippo_logs (type, from_number, to_number, content, status, sent_by, created_at)
            VALUES ('sms', :from_num, :to_num, :content, :status, :sent_by, NOW())
        """), {
            "from_num": callhippo_service.from_number,
            "to_num": to,
            "content": message,
            "status": "sent" if result.get("success") else "failed",
            "sent_by": user.id
        })
        db.commit()
    except Exception as e:
        logger.error("Failed to log SMS to database: %s", e)

    return JSONResponse(result)


@router.post("/api/call/initiate")
async def api_initiate_call(
    request: Request,
    to: str = Form(...),
    db: Session = Depends(get_db)
):
    """Initiate outbound call."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    result = await callhippo_service.make_call(to)

    # Log the call
    try:
        db.execute(text("""
            INSERT INTO callhippo_logs (type, from_number, to_number, status, sent_by, created_at)
            VALUES ('call', :from_num, :to_num, :status, :sent_by, NOW())
        """), {
            "from_num": callhippo_service.from_number,
            "to_num": to,
            "status": "initiated" if result.get("success") else "failed",
            "sent_by": user.id
        })
        db.commit()
    except Exception as e:
        logger.error("Failed to log call to database: %s", e)

    return JSONResponse(result)


@router.get("/api/calls/history")
async def api_get_call_history(
    request: Request,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get call history."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    result = await callhippo_service.get_call_logs(limit=limit)
    return JSONResponse(result)


@router.get("/api/sms/history")
async def api_get_sms_history(
    request: Request,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get SMS history."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    result = await callhippo_service.get_sms_history(limit=limit)
    return JSONResponse(result)


@router.post("/api/client/{client_id}/sms")
async def api_send_client_sms(
    client_id: int,
    request: Request,
    message: str = Form(...),
    db: Session = Depends(get_db)
):
    """Send SMS to a specific client."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        return JSONResponse({"error": "Client not found"}, status_code=404)

    phone = client.phone or client.whatsapp
    if not phone:
        return JSONResponse({"error": "Client has no phone number"}, status_code=400)

    client_name = f"{client.first_name} {client.last_name}".strip() or "Client"
    result = await callhippo_service.send_client_sms(phone, client_name, message)

    return JSONResponse(result)


@router.post("/api/client/{client_id}/call")
async def api_call_client(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Initiate call to a specific client."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        return JSONResponse({"error": "Client not found"}, status_code=404)

    phone = client.phone or client.whatsapp
    if not phone:
        return JSONResponse({"error": "Client has no phone number"}, status_code=400)

    result = await callhippo_service.make_call(phone)
    return JSONResponse(result)


@router.post("/api/appointment-reminder")
async def api_send_appointment_reminder(
    request: Request,
    client_id: int = Form(...),
    date: str = Form(...),
    time: str = Form(...),
    db: Session = Depends(get_db)
):
    """Send appointment reminder to client."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        return JSONResponse({"error": "Client not found"}, status_code=404)

    phone = client.phone or client.whatsapp
    if not phone:
        return JSONResponse({"error": "Client has no phone number"}, status_code=400)

    client_name = client.first_name or "Client"
    result = await callhippo_service.send_appointment_reminder(phone, client_name, date, time)

    return JSONResponse(result)


# Webhook endpoint for incoming SMS — secured by path secret (C8).
# Configure CallHippo with: {PREFIX}/callhippo/webhook/<CALLHIPPO_WEBHOOK_TOKEN>/sms
@router.post("/webhook/{token}/sms")
async def webhook_incoming_sms(token: str, request: Request, db: Session = Depends(get_db)):
    """Handle incoming SMS webhook from CallHippo."""
    _verify_callhippo_webhook_token(token)
    try:
        data = await request.json()

        # Log incoming SMS
        try:
            db.execute(text("""
                INSERT INTO callhippo_logs (type, from_number, to_number, content, status, webhook_data, created_at)
                VALUES ('sms_incoming', :from_num, :to_num, :content, 'received', :webhook_data, NOW())
            """), {
                "from_num": data.get("from"),
                "to_num": data.get("to"),
                "content": data.get("body") or data.get("message"),
                "webhook_data": str(data)
            })
            db.commit()
        except Exception as e:
            logger.error("Failed to log incoming CallHippo SMS: %s", e)
            db.rollback()

        return JSONResponse({"status": "ok"})
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# Webhook endpoint for call events — secured by path secret (C8).
# Configure CallHippo with: {PREFIX}/callhippo/webhook/<CALLHIPPO_WEBHOOK_TOKEN>/call
@router.post("/webhook/{token}/call")
async def webhook_call_event(token: str, request: Request, db: Session = Depends(get_db)):
    """Handle call event webhook from CallHippo."""
    _verify_callhippo_webhook_token(token)
    try:
        data = await request.json()

        # Log call event
        try:
            db.execute(text("""
                INSERT INTO callhippo_logs (type, from_number, to_number, status, duration, webhook_data, created_at)
                VALUES ('call_event', :from_num, :to_num, :status, :duration, :webhook_data, NOW())
            """), {
                "from_num": data.get("from"),
                "to_num": data.get("to"),
                "status": data.get("status") or data.get("callStatus"),
                "duration": data.get("duration"),
                "webhook_data": str(data)
            })
            db.commit()
        except Exception as e:
            logger.error("Failed to log CallHippo call event: %s", e)
            db.rollback()

        return JSONResponse({"status": "ok"})
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
