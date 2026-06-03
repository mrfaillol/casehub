"""
CaseHub - WhatsApp Routes
Send and manage WhatsApp notifications
"""
from core.form_utils import form_int, form_float
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text

import logging

logger = logging.getLogger(__name__)

from models import get_db, Client, Case
from auth import get_current_user
from models.tenant import tenant_query
from i18n import get_translations
from services.whatsapp import WhatsAppService

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])
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
async def whatsapp_dashboard(request: Request, db: Session = Depends(get_db)):
    """WhatsApp notifications dashboard."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    service = WhatsAppService(db)
    stats = service.get_message_stats(30)
    
    # Get recent messages
    try:
        recent = db.execute(text("""
            SELECT * FROM whatsapp_messages
            ORDER BY sent_at DESC
            LIMIT 50
        """)).fetchall()
    except Exception as e:
        logger.error("Failed to fetch recent WhatsApp messages: %s", e)
        db.rollback()
        recent = []

    # Get queued messages
    try:
        queued = db.execute(text("""
            SELECT * FROM whatsapp_queue
            WHERE status = 'pending'
            ORDER BY created_at
        """)).fetchall()
    except Exception as e:
        logger.error("Failed to fetch queued WhatsApp messages: %s", e)
        db.rollback()
        queued = []

    return templates.TemplateResponse("app/whatsapp/dashboard.html", {
        **get_context(request, db),
        "stats": stats,
        "recent": recent,
        "queued": queued
    })


@router.get("/send", response_class=HTMLResponse)
async def send_message_page(request: Request, client_id: int = None, db: Session = Depends(get_db)):
    """Send WhatsApp message page."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    client = None
    if client_id:
        client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()

    # Get clients with WhatsApp numbers
    clients = tenant_query(db, Client, request.state.org_id).filter(
        Client.whatsapp.isnot(None),
        Client.whatsapp != ""
    ).all()

    return templates.TemplateResponse("app/whatsapp/send.html", {
        **get_context(request, db),
        "client": client,
        "clients": clients
    })


@router.post("/send")
async def send_message(
    request: Request,
    phone: str = Form(...),
    message: str = Form(...),
    template: str = Form(None),
    db: Session = Depends(get_db)
):
    """Send a WhatsApp message."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = WhatsAppService(db)
    result = service.send_message(phone, message, template)
    
    return JSONResponse(result)


@router.post("/send/case-update")
async def send_case_update(
    request: Request,
    case_id: int = Form(...),
    details: str = Form(None),
    db: Session = Depends(get_db)
):
    """Send case update notification."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case or not case.client:
        return JSONResponse({"error": "Case or client not found"}, status_code=404)

    client = case.client
    phone = client.whatsapp or client.phone
    
    if not phone:
        return JSONResponse({"error": "Client has no phone number"}, status_code=400)

    service = WhatsAppService(db)
    result = service.send_case_update(
        phone,
        case.case_number or str(case.id),
        case.status,
        details
    )
    
    return JSONResponse(result)


@router.post("/send/document-request")
async def send_document_request(
    request: Request,
    client_id: int = Form(...),
    documents: str = Form(...),
    case_id: str = Form(None),
    db: Session = Depends(get_db)
):
    """Send document request notification."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # Convert form strings to proper types
    case_id = form_int(case_id)

    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        return JSONResponse({"error": "Client not found"}, status_code=404)

    phone = client.whatsapp or client.phone
    if not phone:
        return JSONResponse({"error": "Client has no phone number"}, status_code=400)

    case_number = None
    if case_id:
        case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
        if case:
            case_number = case.case_number

    doc_list = [d.strip() for d in documents.split('\n') if d.strip()]
    
    service = WhatsAppService(db)
    result = service.send_document_request(phone, doc_list, case_number)
    
    return JSONResponse(result)


@router.post("/process-queue")
async def process_queue(request: Request, db: Session = Depends(get_db)):
    """Process queued messages."""
    user = get_current_user(request, db)
    if not user or user.user_type != "admin":
        return JSONResponse({"error": "Admin access required"}, status_code=403)

    service = WhatsAppService(db)
    processed = service.process_queue()
    
    return JSONResponse({
        "success": True,
        "processed": processed
    })


@router.get("/api/stats")
async def get_stats(request: Request, db: Session = Depends(get_db)):
    """Get WhatsApp message statistics."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = WhatsAppService(db)
    stats = service.get_message_stats(30)
    
    return JSONResponse(stats)
