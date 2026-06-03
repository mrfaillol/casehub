"""
CaseHub - WhatsApp Inbound + Field Request Models

Companion to the existing whatsapp_messages table (see services/whatsapp.py for outbound),
adds two new models:

* WhatsappFieldRequest — admin-initiated "please send me the CEP" tracker.
* MaestroTrainingSample — gated dataset row for the Maestro pipeline (default disabled).

Inbound messages themselves reuse the whatsapp_messages table with direction='incoming'
plus new columns added in migration 2026-05-19_whatsapp_inbound_and_maestro_training.sql.
"""
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Boolean,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from .base import Base


class WhatsappFieldRequest(Base):
    __tablename__ = "whatsapp_field_requests"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))

    field_name = Column(String(64), nullable=False)
    field_label = Column(String(128), nullable=False)
    field_target = Column(String(32), default="client")

    message_sent = Column(Text, nullable=False)
    # FK enforced at DB level via migration; whatsapp_messages has no SQLAlchemy model (legacy raw SQL).
    whatsapp_message_id = Column(Integer)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())

    responded_inbound_id = Column(Integer)
    responded_at = Column(DateTime(timezone=True))

    resolved_value = Column(Text)
    resolved_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at = Column(DateTime(timezone=True))

    cancelled_at = Column(DateTime(timezone=True))
    cancelled_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    @property
    def is_pending(self) -> bool:
        return self.resolved_at is None and self.cancelled_at is None

    @property
    def has_response(self) -> bool:
        return self.responded_inbound_id is not None and self.resolved_at is None


class MaestroTrainingSample(Base):
    """Gated dataset row for the Maestro pipeline.

    Default schema state: empty. Inserts require:
      - settings.MAESTRO_TRAINING_COLLECTION_ENABLED == True
      - org.maestro_training_consent == True (per-org opt-in)
      - explicit consent_provider matching the DPA in scope

    See migrations/2026-05-19_*.sql and docs/maestro/pipeline-treinamento.md.
    """

    __tablename__ = "maestro_training_samples"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    # FK enforced at DB level via migration; whatsapp_messages has no SQLAlchemy model (legacy raw SQL).
    source_inbound_id = Column(Integer)
    source_field_request_id = Column(Integer, ForeignKey("whatsapp_field_requests.id", ondelete="SET NULL"))
    source_field_name = Column(String(64), index=True)

    raw_message = Column(Text, nullable=False)
    extracted_value = Column(Text)
    validated_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    validated_at = Column(DateTime(timezone=True))
    is_correct_label = Column(Boolean)
    label_provenance = Column(String(32), default="admin_resolve")

    consent_recorded = Column(Boolean, default=False)
    consent_provider = Column(String(32))
    redaction_applied = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
