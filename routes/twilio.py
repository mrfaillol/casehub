"""
CaseHub - Twilio Routes
SMS, Voice Call, and WhatsApp Management Interface

Follows the same pattern as callhippo.py routes for consistency.
"""
import base64
import hashlib
import hmac
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, Client
from auth import get_current_user
from models.tenant import tenant_query
from i18n import get_translations
from services.twilio import twilio_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/twilio", tags=["twilio"])

# Empty TwiML — used for every webhook reply so we never echo attacker input.
_EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'

# Allow disabling signature enforcement ONLY in explicit non-prod contexts.
_TWILIO_SKIP_VALIDATION = os.getenv("TWILIO_SKIP_WEBHOOK_VALIDATION", "").lower() in {"1", "true", "yes"}


def _twilio_public_url(request: Request) -> str:
    """Reconstruct the exact public URL Twilio signed.

    Twilio computes the signature over the full URL it POSTed to. Behind nginx
    we honor X-Forwarded-Proto/Host so the scheme/host match the public origin
    (otherwise the locally-seen http://internal URL would never validate).
    """
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if host:
        path = request.url.path
        if request.url.query:
            path = f"{path}?{request.url.query}"
        return f"{proto}://{host}{path}"
    return str(request.url)


def _validate_twilio_signature(request: Request, url: str, params: dict) -> bool:
    """Validate X-Twilio-Signature (HMAC-SHA1) without the Twilio SDK.

    Mirrors twilio.request_validator.RequestValidator: signature =
    base64(HMAC-SHA1(auth_token, url + sorted(k+v for POST params))).
    Constant-time compare. The `twilio` package is NOT a dependency here
    (the service uses raw httpx), so we implement the documented algorithm.

    Fail-closed: missing token/signature => invalid (unless explicitly skipped
    in a non-prod context via TWILIO_SKIP_WEBHOOK_VALIDATION).
    """
    if _TWILIO_SKIP_VALIDATION:
        return True

    auth_token = getattr(twilio_service, "auth_token", "") or ""
    signature = request.headers.get("X-Twilio-Signature", "")
    if not auth_token or not signature:
        return False

    payload = url
    for key in sorted(params.keys()):
        payload += key + (params[key] if params[key] is not None else "")

    mac = hmac.new(auth_token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1)
    expected = base64.b64encode(mac.digest()).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def _already_processed(db: Session, sid: str) -> bool:
    """Dedup by Twilio SID — webhooks retry, and replays must be idempotent.

    Best-effort: if twilio_logs is absent we degrade to 'not processed' so the
    insert path (also wrapped) still runs without 500ing the webhook.
    """
    if not sid:
        return False
    try:
        row = db.execute(
            text("SELECT 1 FROM twilio_logs WHERE sid = :sid LIMIT 1"),
            {"sid": sid},
        ).fetchone()
        return row is not None
    except Exception:
        db.rollback()
        return False


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
async def twilio_dashboard(request: Request, db: Session = Depends(get_db)):
    """Twilio dashboard with SMS, Calls, and WhatsApp."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    clients = tenant_query(db, Client, request.state.org_id).filter(
        Client.phone.isnot(None),
        Client.phone != ""
    ).order_by(Client.first_name).limit(50).all()

    return templates.TemplateResponse("app/twilio/dashboard.html", {
        **get_context(request, db),
        "clients": clients,
        "is_configured": twilio_service.is_configured(),
        "from_number": twilio_service.from_number,
        "whatsapp_configured": bool(twilio_service.whatsapp_from),
    })


# ── Status & Info ────────────────────────────────────────────────────────

@router.get("/api/status")
async def api_get_status(request: Request, db: Session = Depends(get_db)):
    """Get Twilio configuration status."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    account_info = await twilio_service.get_account_info()

    return JSONResponse({
        "configured": twilio_service.is_configured(),
        "from_number": twilio_service.from_number,
        "whatsapp_from": twilio_service.whatsapp_from,
        "whatsapp_configured": bool(twilio_service.whatsapp_from),
        "account": account_info.get("data") if account_info.get("success") else None,
    })


@router.get("/api/numbers")
async def api_get_numbers(request: Request, db: Session = Depends(get_db)):
    """Get available phone numbers."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    result = await twilio_service.get_numbers()
    return JSONResponse(result)


# ── SMS ──────────────────────────────────────────────────────────────────

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

    result = await twilio_service.send_sms(to, message)

    try:
        db.execute(text("""
            INSERT INTO twilio_logs (type, from_number, to_number, content, status, sid, sent_by, created_at)
            VALUES ('sms', :from_num, :to_num, :content, :status, :sid, :sent_by, NOW())
        """), {
            "from_num": twilio_service.from_number,
            "to_num": to,
            "content": message,
            "status": result.get("status", "sent" if result.get("success") else "failed"),
            "sid": result.get("sid", ""),
            "sent_by": str(user.id),
        })
        db.commit()
    except Exception:
        pass  # Table might not exist yet

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

    result = await twilio_service.get_sms_history(limit=limit)
    return JSONResponse(result)


# ── Voice Calls ──────────────────────────────────────────────────────────

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

    result = await twilio_service.make_call(to)

    try:
        db.execute(text("""
            INSERT INTO twilio_logs (type, from_number, to_number, status, sid, sent_by, created_at)
            VALUES ('call', :from_num, :to_num, :status, :sid, :sent_by, NOW())
        """), {
            "from_num": twilio_service.from_number,
            "to_num": to,
            "status": result.get("status", "initiated" if result.get("success") else "failed"),
            "sid": result.get("sid", ""),
            "sent_by": str(user.id),
        })
        db.commit()
    except Exception:
        pass

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

    result = await twilio_service.get_call_logs(limit=limit)
    return JSONResponse(result)


# ── WhatsApp ─────────────────────────────────────────────────────────────

@router.post("/api/whatsapp/send")
async def api_send_whatsapp(
    request: Request,
    to: str = Form(...),
    message: str = Form(...),
    db: Session = Depends(get_db)
):
    """Send WhatsApp message."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    result = await twilio_service.send_whatsapp(to, message)

    try:
        db.execute(text("""
            INSERT INTO twilio_logs (type, from_number, to_number, content, status, sid, sent_by, created_at)
            VALUES ('whatsapp', :from_num, :to_num, :content, :status, :sid, :sent_by, NOW())
        """), {
            "from_num": twilio_service.whatsapp_from,
            "to_num": to,
            "content": message,
            "status": result.get("status", "sent" if result.get("success") else "failed"),
            "sid": result.get("sid", ""),
            "sent_by": str(user.id),
        })
        db.commit()
    except Exception:
        pass

    return JSONResponse(result)


# ── Client-specific endpoints ────────────────────────────────────────────

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
    result = await twilio_service.send_client_sms(phone, client_name, message)
    return JSONResponse(result)


@router.post("/api/client/{client_id}/whatsapp")
async def api_send_client_whatsapp(
    client_id: int,
    request: Request,
    message: str = Form(...),
    db: Session = Depends(get_db)
):
    """Send WhatsApp message to a specific client."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        return JSONResponse({"error": "Client not found"}, status_code=404)

    phone = client.whatsapp or client.phone
    if not phone:
        return JSONResponse({"error": "Client has no phone/WhatsApp number"}, status_code=400)

    client_name = f"{client.first_name} {client.last_name}".strip() or "Client"
    result = await twilio_service.send_client_whatsapp(phone, client_name, message)
    return JSONResponse(result)


@router.post("/api/appointment-reminder")
async def api_send_appointment_reminder(
    request: Request,
    client_id: int = Form(...),
    date: str = Form(...),
    time: str = Form(...),
    channel: str = Form("sms"),  # "sms" or "whatsapp"
    db: Session = Depends(get_db)
):
    """Send appointment reminder to client via SMS or WhatsApp."""
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

    if channel == "whatsapp":
        wa_phone = client.whatsapp or client.phone
        result = await twilio_service.send_client_whatsapp(
            wa_phone, client_name,
            f"you have an appointment on {date} at {time}. Reply CONFIRM to confirm."
        )
    else:
        result = await twilio_service.send_appointment_reminder(phone, client_name, date, time)

    return JSONResponse(result)


# ── Webhooks (receive data from Twilio) ──────────────────────────────────

@router.post("/webhook/sms")
async def webhook_incoming_sms(request: Request, db: Session = Depends(get_db)):
    """Handle incoming SMS webhook from Twilio.

    Twilio sends form-encoded data with fields like:
    From, To, Body, MessageSid, AccountSid, etc.
    """
    try:
        form_data = await request.form()
        data = {k: (v if isinstance(v, str) else str(v)) for k, v in form_data.items()}

        # C7: reject forged inbound webhooks — verify Twilio's HMAC signature.
        if not _validate_twilio_signature(request, _twilio_public_url(request), data):
            logger.warning("Twilio SMS webhook: invalid X-Twilio-Signature (To=%s)", data.get("To", ""))
            raise HTTPException(status_code=403, detail="Invalid signature")

        sid = data.get("MessageSid", "")
        if _already_processed(db, sid):
            # Idempotent: Twilio retries; do not double-log.
            return HTMLResponse(content=_EMPTY_TWIML, media_type="application/xml")

        try:
            db.execute(text("""
                INSERT INTO twilio_logs (type, from_number, to_number, content, status, sid, webhook_data, created_at)
                VALUES ('sms_incoming', :from_num, :to_num, :content, 'received', :sid, :webhook_data, NOW())
            """), {
                "from_num": data.get("From", ""),
                "to_num": data.get("To", ""),
                "content": data.get("Body", ""),
                "sid": sid,
                "webhook_data": str(data),
            })
            db.commit()
        except Exception:
            db.rollback()  # Table might not exist yet — webhook still ACKs.

        # Return TwiML response (empty = no auto-reply)
        return HTMLResponse(content=_EMPTY_TWIML, media_type="application/xml")
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/webhook/call")
async def webhook_call_event(request: Request, db: Session = Depends(get_db)):
    """Handle call status webhook from Twilio.

    Twilio sends form-encoded status callbacks.
    """
    try:
        form_data = await request.form()
        data = {k: (v if isinstance(v, str) else str(v)) for k, v in form_data.items()}

        # C7: reject forged call-status callbacks.
        if not _validate_twilio_signature(request, _twilio_public_url(request), data):
            logger.warning("Twilio call webhook: invalid X-Twilio-Signature (To=%s)", data.get("To", ""))
            raise HTTPException(status_code=403, detail="Invalid signature")

        sid = data.get("CallSid", "")
        # Call events legitimately repeat per status transition, so we only
        # suppress exact duplicate (sid, status) rows, not all repeats.
        status_val = data.get("CallStatus", "")
        try:
            dup = db.execute(
                text("SELECT 1 FROM twilio_logs WHERE sid = :sid AND status = :status AND type = 'call_event' LIMIT 1"),
                {"sid": sid, "status": status_val},
            ).fetchone()
        except Exception:
            db.rollback()
            dup = None
        if sid and dup is not None:
            return HTMLResponse(content=_EMPTY_TWIML, media_type="application/xml")

        try:
            db.execute(text("""
                INSERT INTO twilio_logs (type, from_number, to_number, status, sid, duration, webhook_data, created_at)
                VALUES ('call_event', :from_num, :to_num, :status, :sid, :duration, :webhook_data, NOW())
            """), {
                "from_num": data.get("From", ""),
                "to_num": data.get("To", ""),
                "status": status_val,
                "sid": sid,
                "duration": int(data.get("CallDuration", 0)) if data.get("CallDuration") else None,
                "webhook_data": str(data),
            })
            db.commit()
        except Exception:
            db.rollback()

        return HTMLResponse(content=_EMPTY_TWIML, media_type="application/xml")
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/webhook/whatsapp")
async def webhook_incoming_whatsapp(request: Request, db: Session = Depends(get_db)):
    """Handle incoming WhatsApp message webhook from Twilio.

    Twilio WhatsApp webhooks use the same format as SMS but with whatsapp: prefix on numbers.
    """
    try:
        form_data = await request.form()
        data = {k: (v if isinstance(v, str) else str(v)) for k, v in form_data.items()}

        # C7: reject forged inbound WhatsApp webhooks.
        if not _validate_twilio_signature(request, _twilio_public_url(request), data):
            logger.warning("Twilio WhatsApp webhook: invalid X-Twilio-Signature (To=%s)", data.get("To", ""))
            raise HTTPException(status_code=403, detail="Invalid signature")

        from_number = data.get("From", "").replace("whatsapp:", "")
        to_number = data.get("To", "").replace("whatsapp:", "")

        sid = data.get("MessageSid", "")
        if _already_processed(db, sid):
            return HTMLResponse(content=_EMPTY_TWIML, media_type="application/xml")

        try:
            db.execute(text("""
                INSERT INTO twilio_logs (type, from_number, to_number, content, status, sid, webhook_data, created_at)
                VALUES ('whatsapp_incoming', :from_num, :to_num, :content, 'received', :sid, :webhook_data, NOW())
            """), {
                "from_num": from_number,
                "to_num": to_number,
                "content": data.get("Body", ""),
                "sid": sid,
                "webhook_data": str(data),
            })
            db.commit()
        except Exception:
            db.rollback()

        return HTMLResponse(content=_EMPTY_TWIML, media_type="application/xml")
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
