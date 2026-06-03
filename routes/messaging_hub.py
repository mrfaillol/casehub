"""
CaseHub - Unified Messaging Hub Routes
Consolidates WhatsApp, Email, SMS, and Voice communications.
"""

from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

from core.form_utils import form_int, form_float
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, Client, Case
from auth import get_current_user
from models.tenant import tenant_query
from services.messaging_hub_service import MessagingHubService

# Import existing services for sending
try:
    from services.whatsapp import WhatsAppService
except ImportError:
    WhatsAppService = None

try:
    from services.email_service import email_service
except ImportError:
    email_service = None

try:
    from services.callhippo import callhippo_service
except ImportError:
    callhippo_service = None

# PREFIX = "/casehub"  # Imported from template_config.py
router = APIRouter(prefix="/messaging", tags=["messaging"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py
# templates.env.globals["PREFIX"] = PREFIX  # Configured in template_config.py


# =============================================================================
# MAIN VIEWS
# =============================================================================

@router.get("", response_class=HTMLResponse)
async def messaging_hub(
    request: Request,
    channel: Optional[str] = None,
    folder: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Main messaging hub dashboard."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    service = MessagingHubService(db, org_id=request.state.org_id)

    # Get initial data - filter by channel and folder if specified
    threads = service.get_threads(channel=channel, folder=folder, limit=50)
    unread_counts = service.get_unread_counts()
    channel_status = await service.get_channel_status()

    # Get clients for compose dropdown
    clients = tenant_query(db, Client, request.state.org_id).filter(Client.status != 'deleted').order_by(Client.first_name).all()

    return templates.TemplateResponse("app/messaging/hub.html", {
        "request": request,
        "PREFIX": PREFIX,
        "user": user,
        "threads": threads,
        "unread_counts": unread_counts,
        "stats": {
            "total_unread": unread_counts.get("total", 0),
            "whatsapp_unread": unread_counts.get("whatsapp", 0),
            "email_unread": unread_counts.get("email", 0),
            "sms_unread": unread_counts.get("sms", 0),
        },
        "channel_status": channel_status,
        "clients": clients,
        "selected_channel": channel,
        "selected_folder": folder,
        "selected_thread": None
    })


@router.get("/thread/{channel}/{contact}", response_class=HTMLResponse)
async def view_thread(
    request: Request,
    channel: str,
    contact: str,
    db: Session = Depends(get_db)
):
    """View a specific conversation thread."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    service = MessagingHubService(db, org_id=request.state.org_id)

    # Get thread messages
    messages = service.get_thread_messages(channel, contact, limit=200)

    # Mark as read
    service.mark_thread_as_read(channel, contact)

    # Get thread list for sidebar
    threads = service.get_threads(limit=50)
    unread_counts = service.get_unread_counts()
    channel_status = await service.get_channel_status()

    # Get clients for compose
    clients = tenant_query(db, Client, request.state.org_id).filter(Client.status != 'deleted').order_by(Client.first_name).all()

    # Find client info for this contact
    thread_client = None
    if messages and messages[0].get('client_id'):
        thread_client = tenant_query(db, Client, request.state.org_id).filter(Client.id == messages[0]['client_id']).first()

    return templates.TemplateResponse("app/messaging/hub.html", {
        "request": request,
        "PREFIX": PREFIX,
        "user": user,
        "threads": threads,
        "unread_counts": unread_counts,
        "stats": {
            "total_unread": unread_counts.get("total", 0),
            "whatsapp_unread": unread_counts.get("whatsapp", 0),
            "email_unread": unread_counts.get("email", 0),
            "sms_unread": unread_counts.get("sms", 0),
        },
        "channel_status": channel_status,
        "clients": clients,
        "selected_channel": channel,
        "selected_contact": contact,
        "selected_thread": {
            "channel": channel,
            "contact": contact,
            "client": thread_client,
            "messages": messages
        }
    })


# =============================================================================
# API - THREADS & MESSAGES
# =============================================================================

@router.get("/api/threads")
async def api_get_threads(
    request: Request,
    channel: Optional[str] = None,
    client_id: Optional[int] = None,
    search: Optional[str] = None,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Get conversation threads."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = MessagingHubService(db, org_id=request.state.org_id)
    threads = service.get_threads(
        channel=channel,
        client_id=client_id,
        search=search,
        unread_only=unread_only,
        limit=limit,
        offset=offset
    )

    # Convert datetime objects for JSON
    for thread in threads:
        if thread.get('last_message_at'):
            thread['last_message_at'] = thread['last_message_at'].isoformat()

    return JSONResponse({
        "threads": threads,
        "total_unread": service.get_unread_counts()['total']
    })


@router.get("/api/thread/{channel}/{contact}/messages")
async def api_get_thread_messages(
    request: Request,
    channel: str,
    contact: str,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Get messages for a specific thread."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = MessagingHubService(db, org_id=request.state.org_id)
    messages = service.get_thread_messages(channel, contact, limit=limit, offset=offset)

    # Convert datetime objects
    for msg in messages:
        if msg.get('message_at'):
            msg['message_at'] = msg['message_at'].isoformat()

    return JSONResponse({"messages": messages})


@router.get("/api/client/{client_id}/timeline")
async def api_get_client_timeline(
    request: Request,
    client_id: int,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get complete communication timeline for a client."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # Get client info
    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        return JSONResponse({"error": "Client not found"}, status_code=404)

    service = MessagingHubService(db, org_id=request.state.org_id)
    timeline = service.get_client_timeline(client_id, limit=limit)

    # Convert datetime objects
    for item in timeline:
        if item.get('timestamp'):
            item['timestamp'] = item['timestamp'].isoformat()

    return JSONResponse({
        "client": {
            "id": client.id,
            "name": f"{client.first_name} {client.last_name}",
            "email": client.email,
            "phone": client.phone
        },
        "timeline": timeline
    })


# =============================================================================
# API - SEND MESSAGES
# =============================================================================

@router.post("/api/send")
async def api_send_message(
    request: Request,
    channel: str = Form(...),
    to: str = Form(...),
    message: str = Form(...),
    subject: str = Form(None),
    client_id: str = Form(None),
    case_id: str = Form(None),
    db: Session = Depends(get_db)
):
    """
    Unified send endpoint - routes to appropriate service.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # Convert form strings to proper types
    client_id = form_int(client_id)
    case_id = form_int(case_id)

    result = {"success": False, "message": "Unknown channel"}

    try:
        if channel == "whatsapp":
            if WhatsAppService:
                wa_service = WhatsAppService(db)
                # Clean phone number
                phone = ''.join(filter(str.isdigit, to))
                if not phone.startswith('1') and len(phone) == 10:
                    phone = '1' + phone
                success = wa_service.send_message(phone, message)
                result = {"success": success, "message": "WhatsApp message sent" if success else "Failed to send"}
            else:
                result = {"success": False, "message": "WhatsApp service not available"}

        elif channel == "email":
            if email_service:
                success = email_service.send_email(
                    to_email=to,
                    subject=subject or f"Message from {__import__('config').settings.ORG_NAME}",
                    body=message
                )
                result = {"success": success, "message": "Email sent" if success else "Failed to send"}
            else:
                result = {"success": False, "message": "Email service not available"}

        elif channel == "sms":
            if callhippo_service:
                # Clean phone number
                phone = ''.join(filter(str.isdigit, to))
                success = callhippo_service.send_sms(phone, message)
                result = {"success": success, "message": "SMS sent" if success else "Failed to send"}
            else:
                result = {"success": False, "message": "SMS service not available"}

        else:
            result = {"success": False, "message": f"Unknown channel: {channel}"}

        # If successful, add to unified_messages
        if result.get("success"):
            service = MessagingHubService(db, org_id=request.state.org_id)

            # Auto-link if not provided
            if not client_id:
                links = service.auto_link_message(channel, user.email, to, subject, message)
                client_id = links.get('client_id')
                case_id = case_id or links.get('case_id')

            # Insert into unified_messages
            insert_query = """
                INSERT INTO unified_messages
                (channel, source_table, source_id, direction, from_identifier, to_identifier,
                 subject, preview, status, message_at, client_id, case_id, is_read)
                VALUES
                (:channel, 'manual_send', 0, 'outbound', :from_addr, :to_addr,
                 :subject, :preview, 'sent', NOW(), :client_id, :case_id, TRUE)
            """
            db.execute(text(insert_query), {
                'channel': channel,
                'from_addr': user.email,
                'to_addr': to,
                'subject': subject,
                'preview': message[:200] if message else None,
                'client_id': client_id,
                'case_id': case_id
            })
            db.commit()

    except Exception as e:
        result = {"success": False, "message": str(e)}

    return JSONResponse(result)


# =============================================================================
# API - MESSAGE ACTIONS
# =============================================================================

@router.post("/api/messages/{message_id}/read")
async def api_mark_read(
    request: Request,
    message_id: int,
    db: Session = Depends(get_db)
):
    """Mark a message as read."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = MessagingHubService(db, org_id=request.state.org_id)
    service.mark_as_read(message_id)
    return JSONResponse({"success": True})


@router.post("/api/messages/{message_id}/star")
async def api_toggle_star(
    request: Request,
    message_id: int,
    db: Session = Depends(get_db)
):
    """Toggle star on a message."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = MessagingHubService(db, org_id=request.state.org_id)
    is_starred = service.toggle_star(message_id)
    return JSONResponse({"success": True, "is_starred": is_starred})


@router.post("/api/messages/{message_id}/link")
async def api_link_message(
    request: Request,
    message_id: int,
    client_id: str = Form(None),
    case_id: str = Form(None),
    db: Session = Depends(get_db)
):
    """Manually link a message to a client or case."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # Convert form strings to proper types
    client_id = form_int(client_id)
    case_id = form_int(case_id)

    service = MessagingHubService(db, org_id=request.state.org_id)

    if client_id:
        service.link_to_client(message_id, client_id)
    if case_id:
        service.link_to_case(message_id, case_id)

    return JSONResponse({"success": True})


# =============================================================================
# API - SYNC
# =============================================================================

@router.post("/api/sync")
async def api_sync_all(request: Request, db: Session = Depends(get_db)):
    """Sync all channels."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = MessagingHubService(db, org_id=request.state.org_id)
    service.sync_all()

    return JSONResponse({
        "success": True,
        "message": "Sync completed",
        "unread_counts": service.get_unread_counts()
    })


@router.post("/api/sync/{channel}")
async def api_sync_channel(
    request: Request,
    channel: str,
    db: Session = Depends(get_db)
):
    """Sync a specific channel."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = MessagingHubService(db, org_id=request.state.org_id)

    if channel == "whatsapp":
        service.sync_whatsapp_messages()
    elif channel == "email":
        service.sync_email_messages()
    elif channel in ("sms", "call"):
        service.sync_callhippo_logs()
    else:
        return JSONResponse({"error": f"Unknown channel: {channel}"}, status_code=400)

    return JSONResponse({
        "success": True,
        "message": f"{channel} sync completed",
        "unread_counts": service.get_unread_counts()
    })


@router.get("/api/status")
async def api_get_status(request: Request, db: Session = Depends(get_db)):
    """Get status of all channels."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = MessagingHubService(db, org_id=request.state.org_id)
    return JSONResponse({
        "channels": await service.get_channel_status(),
        "unread": service.get_unread_counts()
    })


# =============================================================================
# DOCUMENT LINKING (for document upload linking to client)
# =============================================================================

@router.post("/api/documents/{document_id}/link")
async def api_link_document(
    request: Request,
    document_id: int,
    client_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """Link an uploaded document to a client."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # Update document's client_id
    from models import Document
    doc = tenant_query(db, Document, request.state.org_id).filter(Document.id == document_id).first()
    if not doc:
        return JSONResponse({"error": "Document not found"}, status_code=404)

    doc.client_id = client_id
    db.commit()

    return JSONResponse({
        "success": True,
        "message": "Document linked to client"
    })


# =============================================================================
# API - BULK OPERATIONS
# =============================================================================

@router.post("/api/bulk")
async def api_bulk_action(
    request: Request,
    operation: str = Form(...),
    message_ids: str = Form(...),
    client_id: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    """Execute bulk operations on messages."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    import json
    try:
        ids = json.loads(message_ids)
    except Exception as e:
        logger.error("Failed to parse message IDs JSON: %s", e)
        ids = []

    if not ids:
        return JSONResponse({"error": "No messages selected"}, status_code=400)

    success_count = 0

    try:
        if operation == "mark_read":
            for msg_id in ids:
                db.execute(text("UPDATE unified_messages SET is_read = TRUE WHERE id = :id"), {"id": msg_id})
                success_count += 1

        elif operation == "mark_unread":
            for msg_id in ids:
                db.execute(text("UPDATE unified_messages SET is_read = FALSE WHERE id = :id"), {"id": msg_id})
                success_count += 1

        elif operation == "link_client" and client_id:
            for msg_id in ids:
                db.execute(
                    text("UPDATE unified_messages SET client_id = :client_id WHERE id = :id"),
                    {"client_id": client_id, "id": msg_id}
                )
                success_count += 1

        elif operation == "delete":
            for msg_id in ids:
                db.execute(text("DELETE FROM unified_messages WHERE id = :id"), {"id": msg_id})
                success_count += 1

        elif operation == "star":
            for msg_id in ids:
                db.execute(text("UPDATE unified_messages SET is_starred = NOT COALESCE(is_starred, FALSE) WHERE id = :id"), {"id": msg_id})
                success_count += 1

        db.commit()
        return JSONResponse({"success": True, "count": success_count})

    except Exception as e:
        db.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/email-folders")
async def api_get_email_folders(request: Request, db: Session = Depends(get_db)):
    """Get available email folders."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # Get synced folders from email_messages
    result = db.execute(text("SELECT DISTINCT folder FROM email_messages WHERE folder IS NOT NULL ORDER BY folder"))
    synced_folders = [row[0] for row in result.fetchall()]

    # Get account for IMAP folder listing
    acc_result = db.execute(text("SELECT id FROM email_accounts WHERE enabled = TRUE LIMIT 1"))
    account = acc_result.fetchone()
    account_id = account[0] if account else None

    return JSONResponse({
        "synced_folders": synced_folders,
        "account_id": account_id
    })


# =============================================================================
# SMS CHANNEL - Placeholder for CallHippo integration
# =============================================================================

@router.get("/api/sms/status")
async def api_sms_status(request: Request, db: Session = Depends(get_db)):
    """Check SMS channel status - CallHippo integration."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    sms_available = callhippo_service is not None
    return JSONResponse({
        "channel": "sms",
        "provider": "CallHippo",
        "available": sms_available,
        "status": "active" if sms_available else "coming_soon",
        "message": "SMS ready via CallHippo" if sms_available else "SMS integration pending CallHippo API activation"
    })


@router.get("/api/sms/threads")
async def api_sms_threads(request: Request, db: Session = Depends(get_db)):
    """Get SMS conversation threads - CallHippo integration."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = MessagingHubService(db, org_id=request.state.org_id)
    threads = service.get_threads(channel="sms", limit=50)

    for thread in threads:
        if thread.get('last_message_at'):
            thread['last_message_at'] = thread['last_message_at'].isoformat()

    return JSONResponse({"threads": threads, "channel": "sms"})


@router.post("/api/thread/{channel}/{contact}/mark-read")
async def api_mark_thread_read(
    request: Request,
    channel: str,
    contact: str,
    db: Session = Depends(get_db)
):
    """Mark all messages in a thread as read."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    
    from sqlalchemy import text
    db.execute(text("""
        UPDATE unified_messages 
        SET is_read = true, updated_at = NOW()
        WHERE channel = :channel AND from_identifier = :contact AND is_read = false
    """), {"channel": channel, "contact": contact})
    db.commit()
    
    return JSONResponse({"success": True, "message": "Thread marked as read"})
