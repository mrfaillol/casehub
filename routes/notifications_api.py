"""
CaseHub - Notifications API Routes
Endpoints for the in-app notification bell system.
"""
import os
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_

from models import get_db
from models.notification import Notification
from models.client import Client
from models.user import User
from auth import get_current_user
from models.tenant import tenant_query
from services.notifications import create_notification, create_notification_for_all_staff
from config import settings

logger = logging.getLogger(__name__)

WEBHOOK_API_KEY = os.getenv("CRM_WEBHOOK_API_KEY", "")

router = APIRouter(prefix="/api/notifications", tags=["notifications-api"])


@router.get("/unread-count")
async def get_unread_count(request: Request, db: Session = Depends(get_db)):
    """Polled every 10s by the bell icon to show badge count."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"count": 0})

    count = tenant_query(db, Notification, request.state.org_id).filter(
        Notification.user_id == user.id,
        Notification.is_read == False
    ).count()

    return {"count": count}


@router.get("/recent")
async def get_recent_notifications(
    request: Request,
    limit: int = 20,
    unread_only: bool = False,
    db: Session = Depends(get_db)
):
    """Get recent notifications for the dropdown panel."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    query = tenant_query(db, Notification, request.state.org_id).filter(Notification.user_id == user.id)

    if unread_only:
        query = query.filter(Notification.is_read == False)

    total = query.count()
    notifications = query.order_by(desc(Notification.created_at)).limit(limit).all()

    return {
        "total": total,
        "notifications": [
            {
                "id": n.id,
                "title": n.title,
                "message": n.message,
                "type": n.notification_type,
                "severity": n.severity,
                "is_read": n.is_read,
                "action_url": n.action_url,
                "created_at": n.created_at.isoformat() if n.created_at else None,
                "time_ago": _time_ago(n.created_at),
            }
            for n in notifications
        ],
    }


@router.post("/mark-read")
async def mark_notifications_read(request: Request, db: Session = Depends(get_db)):
    """Mark specific notifications or all as read. Body: {"ids": [1,2]} or {"ids": []} for all."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    data = await request.json()
    notification_ids = data.get("ids", [])

    now = datetime.now(timezone.utc)

    if notification_ids:
        tenant_query(db, Notification, request.state.org_id).filter(
            Notification.user_id == user.id,
            Notification.id.in_(notification_ids),
            Notification.is_read == False,
        ).update(
            {Notification.is_read: True, Notification.read_at: now},
            synchronize_session=False,
        )
    else:
        tenant_query(db, Notification, request.state.org_id).filter(
            Notification.user_id == user.id,
            Notification.is_read == False,
        ).update(
            {Notification.is_read: True, Notification.read_at: now},
            synchronize_session=False,
        )

    db.commit()
    return {"success": True}


@router.post("/whatsapp-message")
async def whatsapp_message_notification(
    request: Request,
    x_api_key: str = Header(None),
    db: Session = Depends(get_db),
):
    """
    Webhook from WhatsApp bot: notify caseworkers when a client sends a WhatsApp message.
    Authenticated via X-API-Key header (same key as leads webhook).
    Body: {"phone": "5532...", "name": "Client Name", "message_preview": "...", "is_known_client": true}
    """
    if not x_api_key or x_api_key != WEBHOOK_API_KEY:
        return JSONResponse({"error": "Invalid API key"}, status_code=401)

    try:
        body = await request.json()
        phone = body.get("phone", "")
        client_name = body.get("name", "Unknown")
        message_preview = body.get("message_preview", "")[:200]
        is_known_client = body.get("is_known_client", False)

        if not phone:
            return JSONResponse({"error": "Phone required"}, status_code=400)

        # Try to find client in DB by phone/whatsapp number.
        #
        # Perf note (alpha-critical webhook hot path — fires every inbound
        # WhatsApp message). Previously the only predicates were
        # ``Client.phone.contains(...)`` + ``Client.whatsapp.contains(...)``,
        # which compile to ``LIKE '%xxx%'``. Postgres **cannot serve LIKE
        # with a leading wildcard from a btree index** — every inbound
        # message triggered a full Client table scan in the per-org
        # subset, cost O(N_clients) per message. For a high-volume firm
        # that pegs the worker.
        #
        # Two-step lookup (mirrors PR #579 fix for routes/whatsapp_chat
        # api_get_lead): (1) exact equality on raw + digits-only phone —
        # uses any indexed phone/whatsapp column. (2) suffix endswith
        # fallback only on miss, gated on ``len(normalised) >= 10`` so a
        # short or partial number cannot collide with an unrelated client.
        phone_normalized = phone.replace("+", "").replace("-", "").replace(" ", "")
        client = tenant_query(db, Client, request.state.org_id).filter(
            or_(
                Client.phone == phone,
                Client.whatsapp == phone,
                Client.phone == phone_normalized,
                Client.whatsapp == phone_normalized,
            )
        ).first()
        if client is None and len(phone_normalized) >= 10:
            suffix = phone_normalized[-10:]
            client = tenant_query(db, Client, request.state.org_id).filter(
                or_(
                    Client.phone.endswith(suffix),
                    Client.whatsapp.endswith(suffix),
                )
            ).first()

        client_id = client.id if client else None
        if client:
            client_name = client.full_name or client_name

        # Find client's case for the action URL
        case_id = None
        action_url = None
        if client and client.cases:
            case_id = client.cases[0].id
            action_url = f"{settings.PREFIX}/clients/{client.id}"
        else:
            action_url = f"{settings.PREFIX}/whatsapp/chat/{phone_normalized}"

        title = f"WhatsApp from {client_name}"
        message = message_preview if message_preview else "New WhatsApp message received"

        # Create notification for all staff
        notifications = create_notification_for_all_staff(
            db=db,
            title=title,
            notification_type="whatsapp_message",
            message=message,
            severity="info",
            client_id=client_id,
            case_id=case_id,
            action_url=action_url,
            org_id=request.state.org_id,
        )
        db.commit()

        logger.info(f"WhatsApp notification: {client_name} ({phone}) -> {len(notifications)} staff notified")

        return {
            "status": "ok",
            "notifications_created": len(notifications),
            "client_found": client is not None,
            "client_name": client_name,
        }

    except Exception as e:
        logger.error(f"WhatsApp notification error: {e}")
        db.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/sentinel-run")
async def run_sentinel(request: Request, db: Session = Depends(get_db)):
    """Trigger do Maestro Sentinel. Protegido por CRM_WEBHOOK_API_KEY ou admin.
    Cron diário: POST /api/notifications/sentinel-run com X-Api-Key.
    """
    import hmac as _hmac
    api_key = request.headers.get("X-Api-Key", "")
    key_ok = bool(WEBHOOK_API_KEY) and _hmac.compare_digest(api_key, WEBHOOK_API_KEY)
    if not key_ok:
        user = get_current_user(request, db)
        if not user or not getattr(user, "is_admin", False):
            return JSONResponse({"error": "Não autorizado"}, status_code=403)
    try:
        from services.maestro_sentinel import run_sentinel_all_orgs
        result = run_sentinel_all_orgs()
        return {"ok": True, **result}
    except Exception as e:
        logger.error("sentinel-run error: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


def _time_ago(dt):
    """Human-readable time ago string."""
    if not dt:
        return ""
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        from datetime import timezone as tz
        dt = dt.replace(tzinfo=tz.utc)
    diff = now - dt
    seconds = diff.total_seconds()
    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    elif seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    elif seconds < 604800:
        return f"{int(seconds // 86400)}d ago"
    else:
        return dt.strftime("%b %d")
