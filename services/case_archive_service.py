"""
CaseHub - Case Archive/Close Reasons Service
Pre-defined reasons for closing and archiving cases.
"""
from datetime import datetime
from typing import List, Optional, Dict
from enum import Enum


class ArchiveAction(str, Enum):
    CLOSE = "close"
    ARCHIVE = "archive"
    REOPEN = "reopen"


class CaseArchiveService:
    """Service for case archive and close operations."""

    # Pre-defined close reasons
    CLOSE_REASONS = [
        {"id": "approved", "label": "Case Approved", "icon": "fa-check-circle", "color": "success"},
        {"id": "denied", "label": "Case Denied", "icon": "fa-times-circle", "color": "danger"},
        {"id": "withdrawn", "label": "Client Withdrew", "icon": "fa-user-minus", "color": "warning"},
        {"id": "abandoned", "label": "Client Abandoned", "icon": "fa-user-slash", "color": "secondary"},
        {"id": "transferred", "label": "Transferred to Another Firm", "icon": "fa-exchange-alt", "color": "info"},
        {"id": "duplicate", "label": "Duplicate Case", "icon": "fa-copy", "color": "secondary"},
        {"id": "no_response", "label": "Client No Response", "icon": "fa-phone-slash", "color": "warning"},
        {"id": "payment_issue", "label": "Payment Issues", "icon": "fa-dollar-sign", "color": "danger"},
        {"id": "other", "label": "Other", "icon": "fa-ellipsis-h", "color": "secondary"},
    ]

    # Pre-defined archive reasons
    ARCHIVE_REASONS = [
        {"id": "completed", "label": "Case Completed Successfully", "icon": "fa-trophy", "color": "success"},
        {"id": "old_case", "label": "Old Case (Archival)", "icon": "fa-archive", "color": "secondary"},
        {"id": "data_retention", "label": "Data Retention Policy", "icon": "fa-database", "color": "info"},
        {"id": "client_request", "label": "Client Requested Archive", "icon": "fa-user-cog", "color": "primary"},
        {"id": "legal_hold", "label": "Legal Hold", "icon": "fa-gavel", "color": "warning"},
        {"id": "inactive", "label": "Long-term Inactive", "icon": "fa-clock", "color": "secondary"},
    ]

    def get_close_reasons(self) -> List[dict]:
        """Get list of close reasons."""
        return self.CLOSE_REASONS

    def get_archive_reasons(self) -> List[dict]:
        """Get list of archive reasons."""
        return self.ARCHIVE_REASONS

    def get_all_reasons(self) -> Dict[str, List[dict]]:
        """Get all reasons grouped by action type."""
        return {
            "close": self.CLOSE_REASONS,
            "archive": self.ARCHIVE_REASONS
        }

    def get_reason_label(self, reason_id: str, action: str = "close") -> str:
        """Get label for a reason ID."""
        reasons = self.CLOSE_REASONS if action == "close" else self.ARCHIVE_REASONS
        for r in reasons:
            if r["id"] == reason_id:
                return r["label"]
        return reason_id

    def validate_reason(self, reason_id: str, action: str = "close") -> bool:
        """Check if reason is valid for action type."""
        reasons = self.CLOSE_REASONS if action == "close" else self.ARCHIVE_REASONS
        return any(r["id"] == reason_id for r in reasons)


# SQL for case archive history table
CREATE_ARCHIVE_TABLES = """
CREATE TABLE IF NOT EXISTS case_archive_history (
    id SERIAL PRIMARY KEY,
    case_id INTEGER NOT NULL,
    action VARCHAR(20) NOT NULL,
    reason_id VARCHAR(50),
    reason_label VARCHAR(200),
    notes TEXT,
    previous_status VARCHAR(50),
    new_status VARCHAR(50),
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_archive_case ON case_archive_history(case_id);
CREATE INDEX IF NOT EXISTS idx_archive_action ON case_archive_history(action);
CREATE INDEX IF NOT EXISTS idx_archive_created ON case_archive_history(created_at);

-- Add archive columns to cases if not exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='cases' AND column_name='is_archived') THEN
        ALTER TABLE cases ADD COLUMN is_archived BOOLEAN DEFAULT false;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='cases' AND column_name='archived_at') THEN
        ALTER TABLE cases ADD COLUMN archived_at TIMESTAMP;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='cases' AND column_name='archived_reason') THEN
        ALTER TABLE cases ADD COLUMN archived_reason VARCHAR(50);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='cases' AND column_name='closed_at') THEN
        ALTER TABLE cases ADD COLUMN closed_at TIMESTAMP;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='cases' AND column_name='closed_reason') THEN
        ALTER TABLE cases ADD COLUMN closed_reason VARCHAR(50);
    END IF;
END $$;
"""


# Singleton instance
case_archive_service = CaseArchiveService()
