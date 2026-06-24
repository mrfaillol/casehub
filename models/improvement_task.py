"""
CaseHub - Improvement Task Model

Receives improvement tasks pushed by the external Command Center
(`model-router.example` ingest endpoints) after intake-triage classified them via
the runtime-routing-matrix.

Authority: ruling 2026-05-06-cmd-control-center-activation
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from .base import Base


class ImprovementTask(Base):
    """A task pushed by the operational control center to drive improvement."""
    __tablename__ = "improvement_tasks"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)

    # Provenance
    envelope_ref = Column(String(120), unique=True, index=True, nullable=False)  # idempotency key from ops-orchestrator
    source = Column(String(80), nullable=False, default="ingest:command-center")  # e.g. "ingest:log", "ingest:finding"
    requested_runtime = Column(String(40))  # codex|claude|gemini|copilot
    skill = Column(String(80))  # matrix-resolved skill name

    # Task content
    kind = Column(String(80), nullable=False, index=True)  # template-refactor, ui-polish, security-finding, etc.
    title = Column(String(255), nullable=False)
    summary = Column(Text)
    # JSONB on Postgres (matches migration), JSON on SQLite (test environment).
    payload = Column(JSON().with_variant(JSONB(), "postgresql"))
    payload_hash_sha256 = Column(String(64), index=True)
    priority = Column(String(8), default="P2")  # P0-P3

    # State machine
    status = Column(String(24), default="received", index=True)
    # received -> dispatched -> in_progress -> done | failed | quarantined
    dispatch_url = Column(String(500))  # link to PR draft or worklog when produced
    failure_reason = Column(Text)
    halt_blocked = Column(Boolean, default=False, index=True)

    # Timestamps
    received_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    dispatched_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "envelope_ref": self.envelope_ref,
            "source": self.source,
            "requested_runtime": self.requested_runtime,
            "skill": self.skill,
            "kind": self.kind,
            "title": self.title,
            "summary": self.summary,
            "priority": self.priority,
            "status": self.status,
            "dispatch_url": self.dispatch_url,
            "halt_blocked": self.halt_blocked,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "dispatched_at": self.dispatched_at.isoformat() if self.dispatched_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "payload_hash_sha256": self.payload_hash_sha256,
        }
