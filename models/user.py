"""
CaseHub - User Model
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, ForeignKey, Text
from sqlalchemy.sql import func
import bcrypt
import enum

from .base import Base

class UserType(enum.Enum):
    ADMIN = "admin"
    ATTORNEY = "attorney"
    CASE_WORKER = "case_worker"
    PARALEGAL = "paralegal"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    email = Column(String(200), unique=True, index=True, nullable=False)
    name = Column(String(200), nullable=False)
    password_hash = Column(String(255), nullable=False)
    user_type = Column(String(50), default="case_worker")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    must_change_password = Column(Boolean, default=True)
    last_password_change = Column(DateTime(timezone=True))

    # Onboarding state (Fatia A — persistent tour progress, cross-device)
    onboarding_completed_at = Column(DateTime(timezone=True), nullable=True)
    onboarding_tour_step = Column(String(50), nullable=True)
    email_verified_at = Column(DateTime(timezone=True), nullable=True)

    # Profile fields
    photo_url = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    bio = Column(Text, nullable=True)
    department = Column(String, nullable=True)
    ui_theme = Column(String(20), default="neuromorphic")  # "glass", "neuromorphic", or "desktop"
    oab_number = Column(String, nullable=True)
    # Per-user identity color (badge/avatar). DB column added by
    # _run_pending_migrations; mapping it here lets the CRM owner-badge read it.
    color = Column(String(20), default="#1C2447")

    def verify_password(self, password: str) -> bool:
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))

    @staticmethod
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
