"""
CaseHub - Notification Model
In-app notification system for staff alerts.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from .base import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)

    # Content
    title = Column(String(255), nullable=False)
    message = Column(Text)
    notification_type = Column(String(50), nullable=False)
    # Types: document_received, document_approved, document_rejected,
    #        task_created, deadline_approaching, client_email, whatsapp_message
    severity = Column(String(20), default="info")  # info, warning, urgent

    # Related entities
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)

    # Target user
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Read state
    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime(timezone=True))

    # Navigation link
    action_url = Column(String(500))

    # Email tracking
    email_sent = Column(Boolean, default=False)
    email_sent_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", backref="notifications")
