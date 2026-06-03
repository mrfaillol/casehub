"""
CaseHub - WhatsApp Web Clone Models

Persistence layer for the web.whatsapp.com clone served at /casehub/whatsapp.
Companion to migration 2026-05-21_whatsapp_clone_schema.sql.

Three tables:
  * WaContact       — one row per WhatsApp peer (person / business / group).
  * WaConversation  — one thread per contact (recency, unread, bot/human flags).
  * WaMessage       — the message ledger (ticks, media, reactions, ordering).

The legacy flat `whatsapp_messages` table (services/whatsapp.py + the
field-request flow) is left untouched on purpose — see models/whatsapp_inbound.py.

JSONB columns use `.with_variant(JSONB(), "postgresql")` so the same model works
on the in-memory SQLite test DB (which has no JSONB).
"""
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Boolean,
    JSON,
    Date,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from .base import Base


# Cross-dialect JSON column (JSONB on Postgres, JSON on SQLite test runs).
_JSON = JSON().with_variant(JSONB(), "postgresql")


class WaContact(Base):
    """A WhatsApp peer: person, business account or group."""

    __tablename__ = "wa_contacts"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Identity
    phone = Column(String(32), nullable=False)            # E.164
    wa_jid = Column(String(128))                          # raw WhatsApp JID
    display_name = Column(String(255))
    profile_pic_url = Column(Text)

    # Classification
    is_business = Column(Boolean, default=False)
    is_group = Column(Boolean, default=False)

    # CRM linkage (Tier 3)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"))
    tags = Column(_JSON, default=list)
    lead_stage = Column(String(32))

    # CRM ownership + scoring (owner-tag feature 2026-05-30). owner_user_id is the
    # team member who "owns" this contact; the badge color is resolved from
    # that User.color in the service layer. lead_score is Phase-2 lead scoring.
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    lead_score = Column(Integer, default=0)

    # Follow-up scheduling (PR7) + normalized phone for dedup (PR8). Additive.
    follow_up_date = Column(Date)
    follow_up_note = Column(Text)
    normalized_phone = Column(String(32))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    conversation = relationship(
        "WaConversation",
        back_populates="contact",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "phone": self.phone,
            "wa_jid": self.wa_jid,
            "display_name": self.display_name,
            "profile_pic_url": self.profile_pic_url,
            "is_business": bool(self.is_business),
            "is_group": bool(self.is_group),
            "client_id": self.client_id,
            "tags": self.tags or [],
            "lead_stage": self.lead_stage,
            "owner_user_id": self.owner_user_id,
            "lead_score": self.lead_score or 0,
            "follow_up_date": self.follow_up_date.isoformat() if self.follow_up_date else None,
            "follow_up_note": self.follow_up_note,
        }

    def __repr__(self):
        return f"<WaContact org={self.org_id} phone={self.phone}>"


class WaConversation(Base):
    """A WhatsApp conversation thread (one per contact)."""

    __tablename__ = "wa_conversations"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contact_id = Column(
        Integer,
        ForeignKey("wa_contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Recency / ordering. last_message_id is a soft ref (no FK — avoids the
    # wa_messages <-> wa_conversations cycle).
    last_message_id = Column(Integer)
    last_message_at = Column(DateTime(timezone=True))
    unread_count = Column(Integer, default=0)

    # WhatsApp-style flags
    archived = Column(Boolean, default=False)
    pinned = Column(Boolean, default=False)
    muted_until = Column(DateTime(timezone=True))

    # Bot / human-takeover control
    bot_enabled = Column(Boolean, default=True)
    human_takeover = Column(Boolean, default=False)
    assigned_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    contact = relationship("WaContact", back_populates="conversation")
    messages = relationship(
        "WaMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="WaMessage.sent_at",
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "contact_id": self.contact_id,
            "last_message_id": self.last_message_id,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "unread_count": self.unread_count or 0,
            "archived": bool(self.archived),
            "pinned": bool(self.pinned),
            "muted_until": self.muted_until.isoformat() if self.muted_until else None,
            "bot_enabled": bool(self.bot_enabled),
            "human_takeover": bool(self.human_takeover),
            "never_contact": bool(self.human_takeover) and not bool(self.bot_enabled),
            "assigned_user_id": self.assigned_user_id,
        }

    def __repr__(self):
        return f"<WaConversation org={self.org_id} contact={self.contact_id}>"


class WaMessage(Base):
    """A single WhatsApp message (incoming or outgoing)."""

    __tablename__ = "wa_messages"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id = Column(
        Integer,
        ForeignKey("wa_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Dedup key — WhatsApp's own message id.
    wa_message_id = Column(String(128))

    direction = Column(String(16), nullable=False, default="incoming")  # incoming|outgoing
    body = Column(Text)

    # Media
    media_type = Column(String(32))      # text|image|audio|video|document|sticker|ptt
    media_url = Column(Text)
    media_mime = Column(String(128))
    media_filename = Column(String(255))
    media_ocr_text = Column(Text)        # texto extraído de PDFs recebidos (Fase 3 OCR)

    # Delivery ticks
    status = Column(String(16), default="sent")  # pending|sent|delivered|read|played|failed

    # Threading / reactions
    reply_to_message_id = Column(Integer, ForeignKey("wa_messages.id", ondelete="SET NULL"))
    reactions = Column(_JSON, default=list)

    from_me = Column(Boolean, default=False)
    author_phone = Column(String(32))

    # sent_at = WhatsApp-native timestamp — authority for message order.
    sent_at = Column(DateTime(timezone=True))
    edited_at = Column(DateTime(timezone=True))
    deleted_at = Column(DateTime(timezone=True))

    ai_generated = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    conversation = relationship("WaConversation", back_populates="messages")
    reply_to = relationship("WaMessage", remote_side=[id])

    # --- ack mapping: whatsapp-web.js numeric ack <-> our status string ------
    # ack: -1=failed 0=pending 1=sent(server) 2=delivered 3=read 4=played
    _ACK_TO_STATUS = {-1: "failed", 0: "pending", 1: "sent", 2: "delivered", 3: "read", 4: "played"}
    _STATUS_TO_ACK = {"failed": -1, "pending": 0, "sent": 1, "delivered": 2, "read": 3, "played": 4}

    @classmethod
    def status_from_ack(cls, ack) -> str:
        try:
            return cls._ACK_TO_STATUS.get(int(ack), "sent")
        except (TypeError, ValueError):
            return "sent"

    @property
    def ack(self) -> int:
        """Numeric ack the frontend (chat.js getAckIcon) expects."""
        return self._STATUS_TO_ACK.get(self.status or "sent", 1)

    def to_frontend_dict(self) -> dict:
        """Shape consumed by static/js/chat.js renderWhatsAppMessages().

        chat.js expects: role ('user'|'assistant'), content, created_at, id,
        ack, plus optional media_type / media_url / caption / filename.
        """
        # `chat` e o tipo de uma mensagem de TEXTO comum do whatsapp-web.js —
        # nao e midia. Normalizar para o front nao renderizar texto como anexo.
        _mt = (self.media_type or "text").lower()
        _is_text = _mt in ("text", "chat", "")
        return {
            "id": self.id,
            "wid": self.wa_message_id,
            "phone": self.author_phone,
            "role": "assistant" if self.from_me else "user",
            "content": self.body or "",
            "created_at": (self.sent_at or self.created_at).isoformat()
            if (self.sent_at or self.created_at)
            else None,
            "from_bot": bool(self.ai_generated),
            "ack": self.ack,
            "status": self.status,
            "direction": self.direction,
            "media_type": "text" if _is_text else _mt,
            "media_url": self.media_url,
            "mimetype": self.media_mime,
            "filename": self.media_filename,
            "ocr_text": self.media_ocr_text,
            "hasMedia": bool(self.media_url) or not _is_text,
            "reply_to_message_id": self.reply_to_message_id,
            "reactions": self.reactions or [],
            "edited_at": self.edited_at.isoformat() if self.edited_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }

    def __repr__(self):
        return f"<WaMessage conv={self.conversation_id} wamid={self.wa_message_id}>"


class WaContactNote(Base):
    """An org-scoped note jotted on a WhatsApp contact (CRM activity log).

    Replaces the 'notes live on the linked Client' stub: a lawyer can record
    context per lead without needing a Client record. Created via create_all on
    boot (new table — no ALTER needed).
    """

    __tablename__ = "wa_contact_notes"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    contact_id = Column(
        Integer, ForeignKey("wa_contacts.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    author_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    body = Column(Text, nullable=False)
    note_type = Column(String(32), default="note")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self, author_name=None) -> dict:
        return {
            "id": self.id,
            "body": self.body,
            "note_type": self.note_type or "note",
            "author_user_id": self.author_user_id,
            "author_name": author_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<WaContactNote org={self.org_id} contact={self.contact_id}>"


class WaTemplate(Base):
    """Org-owned quick-reply template (custom; on top of in-code global defaults).

    Created via create_all on boot. The 22 hardcoded QUICK_REPLY_TEMPLATES stay in
    code as global defaults; these rows are each firm's own additions.
    """

    __tablename__ = "wa_templates"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    category = Column(String(64), default="custom")
    name = Column(String(128), nullable=False)
    body_pt = Column(Text, nullable=False)
    body_en = Column(Text)
    body_es = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def body_for(self, lang) -> str:
        return getattr(self, "body_" + (lang or "pt"), None) or self.body_pt

    def to_dict(self) -> dict:
        return {
            "id": "c%d" % self.id,
            "category": self.category or "custom",
            "name": self.name,
            "is_custom": True,
            "body_pt": self.body_pt,
            "body_en": self.body_en,
            "body_es": self.body_es,
        }

    def __repr__(self):
        return f"<WaTemplate org={self.org_id} name={self.name}>"


class WaContactStageHistory(Base):
    """Append-only log of lead-stage transitions (analytics prerequisite, PR5).

    Velocity/conversion/aging analytics need transition timestamps that can't be
    derived retroactively — so capture them from now on. Created via create_all.
    """

    __tablename__ = "wa_contact_stage_history"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    contact_id = Column(
        Integer, ForeignKey("wa_contacts.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    from_stage = Column(String(32))
    to_stage = Column(String(32), nullable=False)
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    reason = Column(String(64))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "id": self.id, "from_stage": self.from_stage, "to_stage": self.to_stage,
            "actor_user_id": self.actor_user_id, "reason": self.reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<WaContactStageHistory contact={self.contact_id} {self.from_stage}->{self.to_stage}>"
