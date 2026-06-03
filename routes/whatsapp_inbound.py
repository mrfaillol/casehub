"""
CaseHub - WhatsApp Inbound Routes

Endpoints:
  POST /whatsapp/inbound                       (HMAC-protected; called by whatsapp-bot bridge)
  GET  /whatsapp/inbound/pending/{client_id}   (admin: list pending field_requests + recent inbounds)
  POST /whatsapp/inbound/{message_id}/process  (admin: mark inbound as processed)
  POST /whatsapp/field-request                 (admin: create request "please send your CEP")
  POST /whatsapp/field-request/{id}/resolve    (admin: resolve a pending request with the typed value)
  POST /whatsapp/field-request/{id}/cancel     (admin: cancel a pending request)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from auth import get_current_user
from models import get_db, Client
from models.tenant import tenant_query
from models.whatsapp_inbound import WhatsappFieldRequest
from services.whatsapp import WhatsAppService
from services.whatsapp_inbound_service import (
    InboundAuthError,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    process_inbound,
    verify_inbound_signature,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp-inbound"])


def _merged_raw_payload(payload: dict) -> dict:
    """Keep bridge metadata even when the bot sends it outside raw_payload."""
    raw = payload.get("raw_payload")
    if not isinstance(raw, dict):
        raw = {}
    raw = dict(raw)
    for key in (
        "wa_message_id",
        "message_id",
        "id",
        "media_file",
        "media_url",
        "mediaUrl",
        "media_mime",
        "mimetype",
        "filename",
        "media_filename",
        "ocr_text",
        "media_ocr_text",
        "display_name",
        "pushname",
        "name",
        "profile_pic_url",
        "profilePicUrl",
    ):
        if key in payload and payload.get(key) is not None and key not in raw:
            raw[key] = payload.get(key)
    return raw


# ============================================================
# 1. Bot → CaseHub bridge endpoint (HMAC-protected)
# ============================================================
@router.post("/inbound")
async def receive_inbound(request: Request, db: Session = Depends(get_db)):
    """Receive an inbound WhatsApp message from the bridging microservice.

    Expected JSON body:
        {
          "from_phone": "5511999999999",
          "message": "01310-100",
          "media_type": "text",      // optional, defaults to 'text'
          "raw_payload": { ... }     // optional, audit
        }

    Headers:
        X-Casehub-Timestamp: <unix epoch seconds>
        X-Casehub-Signature: <hex hmac_sha256(secret, "<ts>.<body>")>
    """
    body_bytes = await request.body()
    try:
        verify_inbound_signature(
            body_bytes,
            request.headers.get(SIGNATURE_HEADER),
            request.headers.get(TIMESTAMP_HEADER),
        )
    except InboundAuthError as exc:
        logger.warning("inbound rejected: %s", exc)
        raise HTTPException(status_code=401, detail=str(exc))

    try:
        import json as _json
        payload = _json.loads(body_bytes or b"{}")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}")

    from_phone = payload.get("from_phone") or payload.get("from") or ""
    message = payload.get("message") or payload.get("body") or ""
    media_type = payload.get("media_type") or "text"
    # O bot manda media_type = msg.type do whatsapp-web.js, e o tipo de uma
    # mensagem de texto comum e "chat" — normalizar para "text", senao o
    # front trata um "Oi" como anexo/documento.
    if media_type in ("chat", "", None):
        media_type = "text"
    raw = _merged_raw_payload(payload)

    if not from_phone:
        raise HTTPException(status_code=400, detail="from_phone is required")

    if media_type != "text" and not message:
        message = f"[{media_type}] (no caption)"

    # Multi-tenant dispatch (F29, 2026-05-27): the multi-session bot forwards
    # X-Org-Id so we know which tenant owned the session that received the
    # message. Bot-supplied -> only valid when behind the HMAC signature
    # already verified above; the bot is a trusted internal client.
    requested_org_id: Optional[int] = None
    org_header = request.headers.get("X-Org-Id") or request.headers.get("x-org-id")
    if org_header:
        try:
            parsed = int(org_header)
            if parsed > 0:
                requested_org_id = parsed
        except (TypeError, ValueError):
            logger.warning("inbound: invalid X-Org-Id header value: %r", org_header)

    result = process_inbound(
        db,
        from_phone=from_phone,
        message=message,
        media_type=media_type,
        raw_payload=raw,
        requested_org_id=requested_org_id,
    )

    logger.info("inbound processed: %s", result)
    return JSONResponse(result)


# ============================================================
# 1b. Bot → CaseHub message_ack bridge (HMAC-protected)
# ============================================================
@router.post("/ack")
async def receive_ack(request: Request, db: Session = Depends(get_db)):
    """Receive a message_ack (delivery/read tick) from the whatsapp-bot bridge.

    casehub-bridge.js posts here whenever an outgoing message advances its
    WhatsApp ack (sent -> delivered -> read). Same HMAC scheme as /inbound.

    Body: { "wa_message_id": "<id>", "ack": -1..4, "status": "...", "to_phone": "..." }
    """
    body_bytes = await request.body()
    try:
        verify_inbound_signature(
            body_bytes,
            request.headers.get(SIGNATURE_HEADER),
            request.headers.get(TIMESTAMP_HEADER),
        )
    except InboundAuthError as exc:
        logger.warning("ack rejected: %s", exc)
        raise HTTPException(status_code=401, detail=str(exc))

    try:
        import json as _json
        payload = _json.loads(body_bytes or b"{}")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}")

    wa_message_id = payload.get("wa_message_id")
    ack = payload.get("ack")
    status = payload.get("status")
    if not wa_message_id:
        return JSONResponse({"ok": False, "skipped": "no wa_message_id"})

    # wa_message_id is WhatsApp's globally-unique id — resolve the owning org
    # from the stored message, then advance its tick status forward-only.
    # Multi-tenant (F29): if the bot sent X-Org-Id, prefer that scope to
    # disambiguate when 2 tenants happen to share the same wa_message_id
    # (theoretically impossible, but cheap to guard).
    from models.whatsapp_clone import WaMessage
    from services import whatsapp_clone_service

    requested_org_id: Optional[int] = None
    org_header = request.headers.get("X-Org-Id") or request.headers.get("x-org-id")
    if org_header:
        try:
            parsed = int(org_header)
            if parsed > 0:
                requested_org_id = parsed
        except (TypeError, ValueError):
            logger.warning("ack: invalid X-Org-Id header value: %r", org_header)

    q = db.query(WaMessage).filter(WaMessage.wa_message_id == wa_message_id)
    if requested_org_id is not None:
        q = q.filter(WaMessage.org_id == requested_org_id)
    matches = q.limit(2).all()
    if len(matches) > 1:
        logger.warning("ack skipped: ambiguous wa_message_id=%s", wa_message_id)
        return JSONResponse({"ok": False, "skipped": "ambiguous message"}, status_code=409)
    msg = matches[0] if matches else None
    if msg is None:
        return JSONResponse({"ok": True, "skipped": "unknown message"})

    updated = whatsapp_clone_service.update_message_status(
        db, org_id=msg.org_id, wa_message_id=wa_message_id, status=status, ack=ack,
    )
    return JSONResponse({"ok": True, "status": updated.status if updated else None})


# ============================================================
# 1c. Bot → CaseHub contact-sync bridge (HMAC-protected)
# ============================================================
def _org_from_header(request: Request) -> Optional[int]:
    """Parse the trusted X-Org-Id header (valid only behind a verified HMAC)."""
    raw = request.headers.get("X-Org-Id") or request.headers.get("x-org-id")
    if not raw:
        return None
    try:
        v = int(raw)
        return v if v > 0 else None
    except (TypeError, ValueError):
        logger.warning("invalid X-Org-Id header value: %r", raw)
        return None


@router.post("/contacts-sync")
async def receive_contacts_sync(request: Request, db: Session = Depends(get_db)):
    """Bulk-upsert WhatsApp contact identity (display_name + profile photo).

    Fired by the bot on `ready` with the full 1:1 roster so avatars and names
    populate for every contact — including those who haven't messaged since the
    wa_* tables existed. Same HMAC + X-Org-Id trust model as /inbound; the bot
    is a trusted internal client once the signature checks out.

    Body: { "contacts": [ {phone, display_name?, profile_pic_url?, is_business?}, ... ] }
    """
    body_bytes = await request.body()
    try:
        verify_inbound_signature(
            body_bytes,
            request.headers.get(SIGNATURE_HEADER),
            request.headers.get(TIMESTAMP_HEADER),
        )
    except InboundAuthError as exc:
        logger.warning("contacts-sync rejected: %s", exc)
        raise HTTPException(status_code=401, detail=str(exc))

    org_id = _org_from_header(request)
    if not org_id:
        raise HTTPException(status_code=400, detail="X-Org-Id is required")

    try:
        import json as _json
        payload = _json.loads(body_bytes or b"{}")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}")

    contacts = payload.get("contacts")
    if not isinstance(contacts, list):
        raise HTTPException(status_code=400, detail="contacts must be a list")

    from services.whatsapp_clone_service import upsert_contact

    updated = 0
    for c in contacts:
        if not isinstance(c, dict):
            continue
        phone = c.get("phone")
        if not phone:
            continue
        try:
            upsert_contact(
                db,
                org_id=org_id,
                phone=str(phone),
                display_name=(c.get("display_name") or None),
                profile_pic_url=(c.get("profile_pic_url") or None),
                is_business=c.get("is_business"),
                commit=False,
            )
            updated += 1
        except Exception as exc:  # noqa: BLE001 — one bad row must not abort the batch
            logger.warning("contacts-sync skip phone=%s: %s", phone, exc)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("contacts-sync commit failed (org=%s): %s", org_id, exc)
        raise HTTPException(status_code=500, detail="commit failed")

    logger.info("contacts-sync org=%s updated=%s received=%s", org_id, updated, len(contacts))
    return JSONResponse({"ok": True, "updated": updated, "received": len(contacts)})


# ============================================================
# 1d. Bot → CaseHub lifecycle events (HMAC-protected)
# ============================================================
# Plain-language reasons keyed by the whatsapp-web.js disconnect code so the
# in-app alert reads to a layperson ([parceiro]/[usuário]), not an engineer.
_WA_DISCONNECT_REASONS = {
    "logout": "a sessão foi encerrada (logout no celular, em Aparelhos conectados)",
    "navigation": "a janela do WhatsApp foi recarregada no servidor",
    "conflict": "outra sessão assumiu o WhatsApp deste número",
    "unpaired": "o aparelho foi desvinculado pelo celular",
    "unpaired_device": "o aparelho foi desvinculado pelo celular",
    "ban": "o número foi bloqueado pelo WhatsApp",
}


def _notify_org_disconnect(db: Session, org_id: int, reason: str) -> int:
    """Raise ONE urgent in-app notification per staff user that the WhatsApp
    session dropped. Deduped: skips if an unread disconnect alert for this org
    was raised in the last 30 minutes (the bot may emit several signals for a
    single drop — health-monitor + disconnected + change_state)."""
    from datetime import timedelta
    from models.notification import Notification
    from models.user import User

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    existing = (
        db.query(Notification)
        .filter(
            Notification.org_id == org_id,
            Notification.notification_type == "whatsapp_disconnected",
            Notification.is_read.is_(False),
            Notification.created_at >= cutoff,
        )
        .first()
    )
    if existing is not None:
        return 0

    pretty = _WA_DISCONNECT_REASONS.get((reason or "").strip().lower())
    if pretty:
        detail = f" Motivo: {pretty}."
    elif reason:
        detail = f" Detalhe técnico: {reason}."
    else:
        detail = ""
    message = (
        "A conexão do WhatsApp caiu e as mensagens pararam de chegar." + detail
        + " Reconecte em WhatsApp → reler o QR Code para voltar a receber mensagens."
    )

    targets = (
        db.query(User)
        .filter(User.org_id == org_id, User.enabled.is_(True), User.user_type != "superadmin")
        .all()
    )
    created = 0
    for u in targets:
        db.add(Notification(
            org_id=org_id,
            user_id=u.id,
            title="⚠️ WhatsApp desconectado",
            message=message,
            notification_type="whatsapp_disconnected",
            severity="urgent",
            action_url="/casehub/whatsapp",
        ))
        created += 1
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("disconnect notify commit failed (org=%s): %s", org_id, exc)
        return 0
    return created


@router.post("/event")
async def receive_wa_event(request: Request, db: Session = Depends(get_db)):
    """Session lifecycle events from the bot (currently: `disconnected`).

    On `disconnected` we raise an urgent in-app alert for the org's staff so a
    dropped WhatsApp session surfaces immediately instead of being noticed hours
    later. Same HMAC + X-Org-Id trust model as /inbound.

    Body: { "event": "disconnected", "reason": "<code>" }
    """
    body_bytes = await request.body()
    try:
        verify_inbound_signature(
            body_bytes,
            request.headers.get(SIGNATURE_HEADER),
            request.headers.get(TIMESTAMP_HEADER),
        )
    except InboundAuthError as exc:
        logger.warning("event rejected: %s", exc)
        raise HTTPException(status_code=401, detail=str(exc))

    try:
        import json as _json
        payload = _json.loads(body_bytes or b"{}")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}")

    event = str(payload.get("event") or "").strip().lower()
    reason = str(payload.get("reason") or "").strip()
    org_id = _org_from_header(request)

    if event != "disconnected":
        return JSONResponse({"ok": True, "ignored": event or "empty"})
    if not org_id:
        return JSONResponse({"ok": True, "ignored": "no-org"})

    notified = _notify_org_disconnect(db, org_id, reason)
    logger.info("wa event=disconnected org=%s reason=%r notified=%s", org_id, reason, notified)
    return JSONResponse({"ok": True, "event": event, "notified": notified})


# ============================================================
# 2. Admin: list pending requests + recent inbounds for a client
# ============================================================
@router.get("/inbound/pending/{client_id}")
async def list_pending_for_client(request: Request, client_id: int, db: Session = Depends(get_db)):
    """Admin view: pending field requests + last 20 inbound messages for a client."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    org_id = getattr(request.state, "org_id", None)

    client = tenant_query(db, Client, org_id).filter(Client.id == client_id).first()
    if not client:
        return JSONResponse({"error": "Client not found"}, status_code=404)

    pending_requests = (
        db.query(WhatsappFieldRequest)
        .filter(
            WhatsappFieldRequest.client_id == client_id,
            WhatsappFieldRequest.org_id == org_id,
            WhatsappFieldRequest.resolved_at.is_(None),
            WhatsappFieldRequest.cancelled_at.is_(None),
        )
        .order_by(WhatsappFieldRequest.sent_at.desc())
        .all()
    )

    inbounds = db.execute(
        text(
            """
            SELECT id, message, created_at, inbound_processed_at, media_type
            FROM whatsapp_messages
            WHERE org_id = :org_id AND client_id = :cid AND direction = 'incoming'
            ORDER BY created_at DESC
            LIMIT 20
            """
        ),
        {"org_id": org_id, "cid": client_id},
    ).fetchall()

    return JSONResponse(
        {
            "client_id": client_id,
            "pending_requests": [
                {
                    "id": r.id,
                    "field_name": r.field_name,
                    "field_label": r.field_label,
                    "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                    "responded_at": r.responded_at.isoformat() if r.responded_at else None,
                    "responded_inbound_id": r.responded_inbound_id,
                    "message_sent": r.message_sent,
                }
                for r in pending_requests
            ],
            "recent_inbounds": [
                {
                    "id": row.id,
                    "message": row.message,
                    "received_at": row.created_at.isoformat() if row.created_at else None,
                    "processed_at": row.inbound_processed_at.isoformat()
                    if row.inbound_processed_at
                    else None,
                    "media_type": row.media_type or "text",
                }
                for row in inbounds
            ],
        }
    )


# ============================================================
# 3. Admin: mark an inbound message as processed
# ============================================================
@router.post("/inbound/{message_id}/process")
async def mark_inbound_processed(request: Request, message_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    org_id = getattr(request.state, "org_id", None)
    result = db.execute(
        text(
            """
            UPDATE whatsapp_messages
            SET inbound_processed_at = NOW(),
                inbound_processed_by_user_id = :uid
            WHERE id = :mid AND org_id = :org_id AND direction = 'incoming'
            """
        ),
        {"mid": message_id, "org_id": org_id, "uid": user.id},
    )
    if result.rowcount == 0:
        db.rollback()
        return JSONResponse({"error": "Inbound message not found"}, status_code=404)
    db.commit()
    return JSONResponse({"success": True, "message_id": message_id})


# ============================================================
# 4. Admin: create a field request (sends WhatsApp + records the ask)
# ============================================================
@router.post("/field-request")
async def create_field_request(
    request: Request,
    client_id: int = Form(...),
    field_name: str = Form(...),
    field_label: str = Form(...),
    field_target: str = Form("client"),
    custom_message: str = Form(None),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    org_id = getattr(request.state, "org_id", None)
    client = tenant_query(db, Client, org_id).filter(Client.id == client_id).first()
    if not client:
        return JSONResponse({"error": "Client not found"}, status_code=404)

    phone = client.whatsapp or client.phone
    if not phone:
        return JSONResponse(
            {"error": "Client has no WhatsApp/phone on file"}, status_code=400
        )

    org_label = getattr(client, "organization", None)
    org_name = org_label.name if org_label else "CaseHub"
    client_display = (
        getattr(client, "full_name", None)
        or " ".join(
            part for part in (getattr(client, "first_name", None), getattr(client, "last_name", None)) if part
        ).strip()
        or "cliente"
    )

    message = (
        custom_message
        or (
            f"Olá {client_display}, precisamos do seu {field_label} para finalizar "
            f"seu cadastro. Pode responder por aqui? Obrigado, {org_name}."
        )
    )

    service = WhatsAppService(db)
    send_result = service.send_message(phone, message, template=f"field_request:{field_name}")

    # Record the request regardless of immediate send success (queue path also fine).
    fr = WhatsappFieldRequest(
        org_id=org_id,
        client_id=client_id,
        requested_by_user_id=user.id,
        field_name=field_name,
        field_label=field_label,
        field_target=field_target,
        message_sent=message,
        whatsapp_message_id=None,  # legacy whatsapp.py doesn't return PK; tolerate NULL
    )
    db.add(fr)
    db.commit()
    db.refresh(fr)

    return JSONResponse(
        {
            "success": True,
            "field_request_id": fr.id,
            "send_result": send_result,
        }
    )


# ============================================================
# 5. Admin: resolve a pending field_request with the typed value
# ============================================================
@router.post("/field-request/{request_id}/resolve")
async def resolve_field_request(
    request: Request,
    request_id: int,
    resolved_value: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    org_id = getattr(request.state, "org_id", None)
    fr = (
        db.query(WhatsappFieldRequest)
        .filter(WhatsappFieldRequest.id == request_id, WhatsappFieldRequest.org_id == org_id)
        .first()
    )
    if not fr:
        return JSONResponse({"error": "Field request not found"}, status_code=404)
    if fr.resolved_at or fr.cancelled_at:
        return JSONResponse(
            {"error": "Field request already finalized"}, status_code=409
        )

    fr.resolved_value = resolved_value
    fr.resolved_by_user_id = user.id
    fr.resolved_at = datetime.now(tz=timezone.utc)
    db.commit()

    try:
        from services.maestro_training.data_collector import attach_admin_resolve

        attach_admin_resolve(
            db,
            field_request_id=fr.id,
            resolved_value=resolved_value,
            user_id=user.id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Maestro training sample update failed for field_request=%s: %s", fr.id, exc)
        db.rollback()

    return JSONResponse({"success": True, "field_request_id": request_id})


# ============================================================
# 6. Admin: cancel a pending field_request
# ============================================================
@router.post("/field-request/{request_id}/cancel")
async def cancel_field_request(request: Request, request_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    org_id = getattr(request.state, "org_id", None)
    fr = (
        db.query(WhatsappFieldRequest)
        .filter(WhatsappFieldRequest.id == request_id, WhatsappFieldRequest.org_id == org_id)
        .first()
    )
    if not fr:
        return JSONResponse({"error": "Field request not found"}, status_code=404)
    if fr.resolved_at or fr.cancelled_at:
        return JSONResponse(
            {"error": "Field request already finalized"}, status_code=409
        )

    fr.cancelled_at = datetime.now(tz=timezone.utc)
    fr.cancelled_by_user_id = user.id
    db.commit()
    return JSONResponse({"success": True, "field_request_id": request_id})
