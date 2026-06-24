"""
CaseHub - Document Model
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Date, Boolean, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from .base import Base

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    doc_type = Column(String(100))  # passport, i94, visa, diploma, lor, etc.
    status = Column(String(50), default="pending")  # pending, received, reviewed, approved, rejected, expired, pending_approval
    file_path = Column(String(500))
    file_size = Column(Integer)
    file_hash = Column(String(64))  # SHA256 hash for deduplication
    mime_type = Column(String(100))
    expiration_date = Column(Date)
    notes = Column(Text)
    
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    case_id = Column(Integer, ForeignKey("cases.id"))
    # Anexo de cartão Kanban (Trello-style, pedido alpha UsuarioDemo). Nullable: a maioria
    # dos documentos não pertence a uma tarefa. ondelete=SET NULL preserva o arquivo
    # quando a tarefa é apagada (vira documento solto da org, não some).
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    
    # New columns for document management system
    drive_file_id = Column(String(100))
    drive_link = Column(String(500))
    original_filename = Column(String(500))
    local_path = Column(String(1000))
    
    # LLM classification fields
    llm_classified = Column(Boolean, default=False)
    classification_confidence = Column(Float)
    visa_category = Column(String(50))
    suggested_exhibit = Column(String(10))
    
    # Client portal upload fields
    uploaded_via = Column(String(20), default="staff_upload")  # staff_upload, client_portal, email
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    reviewed_at = Column(DateTime(timezone=True))
    rejection_reason = Column(Text)

    # OCR fields (added 2026-02-27)
    ocr_text = Column(Text)
    ocr_language = Column(String(10), default="en")
    ocr_confidence = Column(Float)
    ocr_processed_at = Column(DateTime(timezone=True))
    ocr_status = Column(String(20), default="pending")  # pending, processing, completed, failed

    # Deduplication fields (added 2026-02-27)
    content_hash = Column(String(64))  # SHA256 of file content
    duplicate_of = Column(Integer, ForeignKey("documents.id"))

    # Path management fields (added 2026-02-27)
    storage_path = Column(String(1000))  # Actual file location
    public_slug = Column(String(500))    # Human-readable URL slug
    storage_backend = Column(String(20), default="local")  # local, drive, s3

    # Unified workflow state (added 2026-02-27, replaces status field)
    workflow_state = Column(String(30), default="uploaded")  # uploaded, pending_review, approved, rejected, pending_client, archived

    # Intake integration fields (added 2026-02-20)
    intake_item_id = Column(Integer)
    intake_package_id = Column(Integer)
    drive_sync_status = Column(String(50), default="not_synced")  # not_synced, pending, synced, failed
    drive_sync_error = Column(Text)
    drive_synced_at = Column(DateTime(timezone=True))
    drive_retry_count = Column(Integer, default=0)
    client_notified_at = Column(DateTime(timezone=True))
    approval_notification_sent = Column(Boolean, default=False)
    rejection_notification_sent = Column(Boolean, default=False)

    # Unified document state (added 2026-03-20)
    # Consolidates status, workflow_state, ocr_status, drive_sync_status into one field.
    # Values: uploaded, pending_review, approved, rejected, synced
    state = Column(String(30), default="uploaded")

    # Portal visibility (added 2026-03-03)
    client_visible = Column(Boolean, default=True)

    # Relationships
    client = relationship("Client", back_populates="documents")
    case = relationship("Case", back_populates="documents")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
