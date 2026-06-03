"""
CaseHub - Reserved subdomain blocklist model.

The canonical seed lives in migrations/2026-05-24_onboarding_subdomain.sql;
this model exists so tests (SQLite in-memory) can create the table without
running the production migration.
"""
from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.sql import func

from .base import Base


class ReservedSubdomain(Base):
    __tablename__ = "reserved_subdomains"

    slug = Column(String(100), primary_key=True)
    reason = Column(String(50), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<ReservedSubdomain {self.slug} ({self.reason})>"
