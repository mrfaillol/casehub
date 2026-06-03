"""
CaseHub - WhatsApp Inbound Service

Responsibilities:
  1. Validate HMAC signature on inbound payloads from the whatsapp-bot bridge.
  2. Persist inbound messages onto whatsapp_messages (direction='incoming') with raw payload.
  3. Match the inbound message back to a client by phone.
  4. If a pending whatsapp_field_request exists for that client, link them.
  5. (Gated) Optionally seed a maestro_training_sample row when consent + flag agree.

This service is intentionally permissive at the matching layer: when the phone matches
multiple clients across multiple orgs, the record is persisted with org_id=NULL and
client_id=NULL — surfaced to admin "Triage" panel for human resolution. Beta will add
deterministic routing per org.
"""
from __future__ import annotations

import hmac
import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from urllib.parse import quote

from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from models import Client
from models.whatsapp_inbound import WhatsappFieldRequest, MaestroTrainingSample


logger = logging.getLogger(__name__)

# Header conventions for HMAC bridge auth.
SIGNATURE_HEADER = "X-Casehub-Signature"
TIMESTAMP_HEADER = "X-Casehub-Timestamp"
# Reject payloads older than this (clock skew window).
MAX_SIGNATURE_AGE_SECONDS = 300


class InboundAuthError(Exception):
    """Raised when HMAC validation fails or the request is stale."""


def _format_phone(raw: str) -> str:
    """Normalize phone to digits-only (matches services/whatsapp.py:format_phone behaviour)."""
    if not raw:
        return ""
    return "".join(ch for ch in raw if ch.isdigit())


def _clone_media_url(media_file: Optional[str]) -> Optional[str]:
    """Public, auth-gated path the clone frontend uses to fetch a media binary.

    Construido aqui (nao no bot) para o binario nunca sair numa URL publica: a
    rota GET {prefix}/api/media/{file} exige sessao CaseHub. O prefixo do clone
    depende da flag CASEHUB_WHATSAPP_CLONE_ENABLED (default OFF -> /whatsapp-chat).
    """
    if not media_file:
        return None
    try:
        from core.template_config import PREFIX
        prefix = PREFIX or ""
    except Exception:  # noqa: BLE001
        prefix = ""
    clone_on = str(os.getenv("CASEHUB_WHATSAPP_CLONE_ENABLED", "")).strip().lower() in (
        "1", "true", "yes", "on",
    )
    router_prefix = "/whatsapp" if clone_on else "/whatsapp-chat"
    return f"{prefix}{router_prefix}/api/media/{media_file}"


def _clone_chat_url(phone: str) -> str:
    """Auth-gated chat route for opening a specific WhatsApp contact."""
    try:
        from core.template_config import PREFIX
        prefix = PREFIX or ""
    except Exception:  # noqa: BLE001
        prefix = ""
    clone_on = str(os.getenv("CASEHUB_WHATSAPP_CLONE_ENABLED", "")).strip().lower() in (
        "1", "true", "yes", "on",
    )
    router_prefix = "/whatsapp" if clone_on else "/whatsapp-chat"
    return f"{prefix}{router_prefix}?phone={quote(phone, safe='')}"


def verify_inbound_signature(body_bytes: bytes, signature_header: Optional[str], timestamp_header: Optional[str]) -> None:
    """Raise InboundAuthError if HMAC does not match or timestamp is stale.

    Signature scheme: hex(hmac_sha256(secret, f"{timestamp}.{body}"))
    Both timestamp and body are required to prevent replay.
    """
    secret = getattr(settings, "CASEHUB_INBOUND_HMAC_SECRET", None)
    if not secret:
        raise InboundAuthError("CASEHUB_INBOUND_HMAC_SECRET is not configured")

    if not signature_header or not timestamp_header:
        raise InboundAuthError("missing signature or timestamp header")

    try:
        ts = int(timestamp_header)
    except (TypeError, ValueError):
        raise InboundAuthError("invalid timestamp header")

    now = int(datetime.now(tz=timezone.utc).timestamp())
    if abs(now - ts) > MAX_SIGNATURE_AGE_SECONDS:
        raise InboundAuthError("signature timestamp out of allowed window")

    payload = f"{ts}.".encode("utf-8") + body_bytes
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise InboundAuthError("signature mismatch")


def _match_client(db: Session, from_phone_digits: str) -> Tuple[Optional[int], Optional[int]]:
    """Return (org_id, client_id) match by phone. Ambiguity → both None."""
    if not from_phone_digits:
        return (None, None)

    # We do not have format_phone normalization on the stored Client.phone/whatsapp
    # columns guaranteed — match on suffix of length 10 (last 10 digits) which covers
    # both with-country-code and without variations.
    tail = from_phone_digits[-10:] if len(from_phone_digits) >= 10 else from_phone_digits

    rows = db.execute(
        text(
            """
            SELECT id, org_id FROM clients
            WHERE
                regexp_replace(COALESCE(phone, ''), '\\D', '', 'g') ~ :tail_re
                OR regexp_replace(COALESCE(whatsapp, ''), '\\D', '', 'g') ~ :tail_re
            ORDER BY updated_at DESC NULLS LAST, id DESC
            LIMIT 5
            """
        ),
        {"tail_re": f"{tail}$"},
    ).fetchall()

    if len(rows) == 1:
        return (rows[0].org_id, rows[0].id)

    if len(rows) > 1:
        # Ambiguous — defer to triage.
        logger.info("inbound match ambiguous: phone=%s matches=%d", tail, len(rows))
        return (None, None)

    return (None, None)


def _resolve_inbound_org(
    db: Session,
    matched_org_id: Optional[int],
    requested_org_id: Optional[int] = None,
) -> Optional[int]:
    """Org para atribuir um inbound, para o espelho no clone WhatsApp (wa_*).

    Precedence (F29, 2026-05-27):
    0. `requested_org_id` (header X-Org-Id do bot multi-session) — fonte
       deterministica; pula heuristica. Quando setado, garantimos so que a
       org existe; senao caimos no fluxo legacy. Isto resolve definitivamente
       o bug "cliente-alpha ve mensagens da default" sem depender do telefone.
    1. `matched_org_id` (telefone casou com um cliente) -> org desse cliente.
    2. sem match, deploy single-tenant (exatamente 1 org) -> essa org.
    3. 2+ orgs sem match -> fallback org slug='default' (ex.: id=2 em
       casehub.legal). Sem este fallback msg some do clone — mantido como
       safety net para inbounds que chegam sem header (bot legado, retest).
    """
    if requested_org_id and requested_org_id > 0:
        # Confirma que a org existe; um header falsificado nao deve criar
        # registros orfaos (a confirmacao tambem da pegada de auditoria).
        try:
            row = db.execute(
                text("SELECT id FROM organizations WHERE id = :id LIMIT 1"),
                {"id": requested_org_id},
            ).first()
            if row:
                return row.id
            logger.warning(
                "inbound: X-Org-Id=%s nao existe; caindo na heuristica",
                requested_org_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("_resolve_inbound_org requested_org_id failed: %s", exc)

    if matched_org_id:
        return matched_org_id
    try:
        rows = db.execute(text("SELECT id FROM organizations ORDER BY id LIMIT 2")).fetchall()
        if len(rows) == 1:
            return rows[0].id
        # 2+ orgs sem phone match -> fallback default
        default_row = db.execute(
            text("SELECT id FROM organizations WHERE slug = 'default' LIMIT 1")
        ).first()
        if default_row:
            return default_row.id
        # Sem org default -> primeira org por id (safety net)
        first = db.execute(text("SELECT id FROM organizations ORDER BY id LIMIT 1")).first()
        if first:
            return first.id
    except Exception as exc:  # noqa: BLE001
        logger.warning("_resolve_inbound_org failed: %s", exc)
    return None


def persist_inbound_message(
    db: Session,
    *,
    from_phone: str,
    message: str,
    media_type: str = "text",
    raw_payload: Optional[dict] = None,
    requested_org_id: Optional[int] = None,
) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """Insert an inbound row into whatsapp_messages. Returns (id, org_id, client_id).

    O write em whatsapp_messages (tabela legada, sem modelo SQLAlchemy) NAO e
    fatal: deploys novos (ex.: casehub.legal) podem nao ter essa tabela. O clone
    usa wa_*; whatsapp_messages so alimenta o match de field-request. Se a tabela
    faltar, loga e segue com id=None.
    """
    digits = _format_phone(from_phone)
    org_id, client_id = _match_client(db, digits)
    # F29 multi-tenant: o X-Org-Id (verificado por HMAC) e a fonte de verdade do
    # tenant dono da sessao que recebeu a mensagem. Sem isto, a linha ficava com
    # org_id NULL p/ remetentes nao-cadastrados (sem match de client) -> /api/messages
    # e /api/conversations (filtrados por org_id) nao achavam nada -> "Loading
    # messages..." eterno ([parceiro], alpha 29/05). Prefere o header; cai no match so se ausente.
    if requested_org_id and requested_org_id > 0:
        org_id = requested_org_id

    payload_json = json.dumps(raw_payload) if raw_payload else None

    inbound_id = None
    try:
        row = db.execute(
            text(
                """
                INSERT INTO whatsapp_messages
                    (org_id, phone, from_phone, direction, message, status, client_id, raw_payload, media_type, created_at)
                VALUES
                    (:org_id, :phone, :from_phone, 'incoming', :message, 'received', :client_id, CAST(:raw_payload AS JSONB), :media_type, NOW())
                RETURNING id
                """
            ),
            {
                "org_id": org_id,
                "phone": digits,
                "from_phone": digits,
                "message": (message or "")[:4000],
                "client_id": client_id,
                "raw_payload": payload_json,
                "media_type": media_type,
            },
        ).fetchone()
        db.commit()
        inbound_id = row.id
    except Exception as exc:  # noqa: BLE001 — legacy table is optional
        logger.warning(
            "persist_inbound_message: whatsapp_messages indisponivel (%s) "
            "— seguindo sem o write legado", exc
        )
        try:
            db.rollback()
        except Exception:
            pass
    return (inbound_id, org_id, client_id)


def link_pending_field_request(
    db: Session,
    *,
    inbound_id: Optional[int],
    org_id: Optional[int],
    client_id: Optional[int],
) -> Optional[WhatsappFieldRequest]:
    """If a pending field_request exists for this client, link the inbound. Returns the request."""
    if not inbound_id or not client_id:
        return None

    pending = (
        db.query(WhatsappFieldRequest)
        .filter(
            WhatsappFieldRequest.client_id == client_id,
            WhatsappFieldRequest.org_id == org_id,
            WhatsappFieldRequest.resolved_at.is_(None),
            WhatsappFieldRequest.cancelled_at.is_(None),
        )
        .order_by(WhatsappFieldRequest.sent_at.desc())
        .first()
    )
    if not pending:
        return None

    pending.responded_inbound_id = inbound_id
    pending.responded_at = datetime.now(tz=timezone.utc)
    db.commit()
    return pending


def seed_training_sample_if_enabled(
    db: Session,
    *,
    inbound_id: int,
    org_id: Optional[int],
    field_request: Optional[WhatsappFieldRequest],
    message: str,
) -> Optional[int]:
    """Collect a training sample only when ALL of these hold:
      - settings.MAESTRO_TRAINING_COLLECTION_ENABLED == True
      - org has explicit consent recorded
      - field_request exists (need labelled context)
    Returns inserted sample id, or None if skipped.
    """
    if not getattr(settings, "MAESTRO_TRAINING_COLLECTION_ENABLED", False):
        return None
    if not org_id or not field_request:
        return None

    consent_row = db.execute(
        text(
            """
            SELECT maestro_training_consent, maestro_training_consent_provider
            FROM org_settings WHERE org_id = :org_id
            """
        ),
        {"org_id": org_id},
    ).fetchone()
    if not consent_row or not consent_row.maestro_training_consent:
        return None

    sample = MaestroTrainingSample(
        org_id=org_id,
        source_inbound_id=inbound_id,
        source_field_request_id=field_request.id,
        source_field_name=field_request.field_name,
        raw_message=message[:4000],
        extracted_value=None,             # filled later when admin resolves the request
        is_correct_label=None,
        label_provenance="awaiting_admin",
        consent_recorded=True,
        consent_provider=consent_row.maestro_training_consent_provider,
        redaction_applied=False,
    )
    db.add(sample)
    db.commit()
    return sample.id


def mirror_inbound_to_clone(
    db: Session,
    *,
    org_id: Optional[int],
    from_phone: str,
    message: str,
    media_type: str = "text",
    raw_payload: Optional[dict] = None,
    client_id: Optional[int] = None,
) -> Optional[int]:
    """Mirror an inbound message into the WhatsApp-clone tables (wa_*).

    Runs IN ADDITION to the legacy whatsapp_messages write — the field-request
    matching flow still depends on whatsapp_messages, so that write stays.

    Skipped (returns None) when org_id is unknown (ambiguous phone match): the
    wa_* model requires a tenant; ambiguous inbounds stay only in the legacy
    table for the admin Triage panel. Never raises — a clone-mirror failure must
    not break inbound ingestion.
    """
    if not org_id:
        return None
    try:
        from models.whatsapp_clone import WaContact
        from services.whatsapp_clone_service import normalize_phone, record_message

        raw = raw_payload or {}
        wa_message_id = (
            raw.get("wa_message_id")
            or raw.get("message_id")
            or raw.get("id")
        )
        media_file = raw.get("media_file")
        media_url = (
            raw.get("media_url")
            or raw.get("mediaUrl")
            or _clone_media_url(media_file)
        )
        media_mime = raw.get("media_mime") or raw.get("mimetype")
        media_filename = raw.get("media_filename") or raw.get("filename")
        media_ocr_text = raw.get("ocr_text") or raw.get("media_ocr_text")
        display_name = raw.get("display_name") or raw.get("pushname") or raw.get("name")
        profile_pic_url = raw.get("profile_pic_url") or raw.get("profilePicUrl")
        e164_phone = normalize_phone(from_phone)
        existing_contact = None
        if e164_phone:
            existing_contact = (
                db.query(WaContact)
                .filter(WaContact.org_id == org_id, WaContact.phone == e164_phone)
                .first()
            )

        msg = record_message(
            db,
            org_id=org_id,
            phone=from_phone,
            body=message,
            direction="incoming",
            wa_message_id=wa_message_id,
            media_type=media_type or "text",
            media_url=media_url,
            media_mime=media_mime,
            media_filename=media_filename,
            media_ocr_text=media_ocr_text,
            from_me=False,
            author_phone=from_phone,
            display_name=display_name,
            profile_pic_url=profile_pic_url,
            auto_link_client_id=client_id,
        )
        if existing_contact is None:
            contact = (
                db.query(WaContact)
                .filter(WaContact.org_id == org_id, WaContact.phone == (e164_phone or msg.author_phone))
                .first()
            )
            if contact is not None and not contact.client_id:
                _notify_new_whatsapp_lead(
                    db,
                    org_id=org_id,
                    phone=contact.phone,
                    display_name=contact.display_name or display_name,
                    message=message,
                    media_type=media_type,
                )
        return msg.id
    except Exception as exc:  # noqa: BLE001 — mirror is best-effort
        logger.warning("mirror_inbound_to_clone failed (org=%s): %s", org_id, exc)
        try:
            db.rollback()
        except Exception:
            pass
        return None


def _notify_new_whatsapp_lead(
    db: Session,
    *,
    org_id: int,
    phone: str,
    display_name: Optional[str],
    message: str,
    media_type: str = "text",
) -> int:
    """Create one in-app alert when an unknown WhatsApp contact first appears."""
    if not org_id or not phone:
        return 0
    try:
        from models.notification import Notification
        from models.user import User

        action_url = _clone_chat_url(phone)
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)
        existing = (
            db.query(Notification)
            .filter(
                Notification.org_id == org_id,
                Notification.notification_type == "whatsapp_new_lead",
                Notification.action_url == action_url,
                Notification.is_read.is_(False),
                Notification.created_at >= cutoff,
            )
            .first()
        )
        if existing is not None:
            return 0

        name = (display_name or phone or "Novo contato").strip()
        snippet = (message or "").strip()
        if media_type and media_type != "text":
            snippet = f"Nova midia recebida ({media_type}). " + snippet
        snippet = snippet[:220] if snippet else "Nova conversa iniciada pelo WhatsApp."
        title = f"Novo lead no WhatsApp: {name}"[:255]

        targets = (
            db.query(User)
            .filter(User.org_id == org_id, User.enabled.is_(True), User.user_type != "superadmin")
            .all()
        )
        created = 0
        for user in targets:
            db.add(Notification(
                org_id=org_id,
                user_id=user.id,
                title=title,
                message=snippet,
                notification_type="whatsapp_new_lead",
                severity="warning",
                action_url=action_url,
            ))
            created += 1
        if created:
            db.commit()
        return created
    except Exception as exc:  # noqa: BLE001 — notification must never break inbound
        logger.warning("whatsapp new-lead notification failed (org=%s): %s", org_id, exc)
        try:
            db.rollback()
        except Exception:
            pass
        return 0


def process_inbound(
    db: Session,
    *,
    from_phone: str,
    message: str,
    media_type: str = "text",
    raw_payload: Optional[dict] = None,
    requested_org_id: Optional[int] = None,
) -> dict:
    """End-to-end inbound flow. Returns a small dict suitable for HTTP response.

    Multi-tenant (F29, 2026-05-27): `requested_org_id` carries the X-Org-Id
    header value forwarded by the multi-session bot. When set + valid, it
    skips the phone heuristic and assigns the message to that exact tenant.
    Falls back to the heuristic when missing or unknown.
    """
    inbound_id, matched_org_id, client_id = persist_inbound_message(
        db,
        from_phone=from_phone,
        message=message,
        media_type=media_type,
        raw_payload=raw_payload,
        requested_org_id=requested_org_id,
    )

    # When the bot announced the tenant explicitly (X-Org-Id), trust it over
    # the phone match — phone match may be wrong if the same phone exists in
    # 2 different tenants' client lists. The legacy flow (no header) keeps
    # the phone match precedence.
    if requested_org_id and requested_org_id > 0:
        resolved_org_id = requested_org_id
    else:
        resolved_org_id = matched_org_id

    field_request = link_pending_field_request(
        db, inbound_id=inbound_id, org_id=resolved_org_id, client_id=client_id
    )
    sample_id = seed_training_sample_if_enabled(
        db,
        inbound_id=inbound_id,
        org_id=resolved_org_id,
        field_request=field_request,
        message=message,
    )

    # Mirror into the WhatsApp-clone tables so the /casehub/whatsapp clone shows
    # this message live. Best-effort: never let it break the inbound write above.
    # Pass `requested_org_id` through — the resolver returns it directly when
    # the org exists, skipping the heuristic.
    clone_org_id = _resolve_inbound_org(
        db, resolved_org_id, requested_org_id=requested_org_id
    )
    wa_clone_message_id = mirror_inbound_to_clone(
        db,
        org_id=clone_org_id,
        from_phone=from_phone,
        message=message,
        media_type=media_type,
        raw_payload=raw_payload,
        client_id=client_id,
    )

    return {
        "inbound_id": inbound_id,
        "matched_client_id": client_id,
        "matched_org_id": matched_org_id,
        "resolved_org_id": resolved_org_id,
        "requested_org_id": requested_org_id,
        "linked_field_request_id": field_request.id if field_request else None,
        "training_sample_id": sample_id,
        "wa_clone_message_id": wa_clone_message_id,
    }
