"""
CaseHub - Bulk Operations Service
Perform bulk actions on multiple records.
"""
from datetime import datetime
from typing import List, Optional, Dict
from enum import Enum


class BulkOperation(str, Enum):
    UPDATE_STATUS = "update_status"
    ASSIGN_USER = "assign_user"
    DELETE = "delete"
    EXPORT = "export"
    TAG = "tag"
    SEND_EMAIL = "send_email"


class EntityType(str, Enum):
    CASE = "case"
    CLIENT = "client"
    TASK = "task"
    DOCUMENT = "document"


class BulkService:
    """Service for bulk operations."""

    # Available operations per entity type
    OPERATIONS = {
        EntityType.CASE: [
            {"id": "update_status", "label": "Update Status", "icon": "fa-exchange-alt"},
            {"id": "assign_user", "label": "Assign User", "icon": "fa-user-plus"},
            {"id": "delete", "label": "Delete Cases", "icon": "fa-trash", "danger": True},
            {"id": "export", "label": "Export to CSV", "icon": "fa-file-export"},
        ],
        EntityType.CLIENT: [
            {"id": "update_status", "label": "Update Status", "icon": "fa-exchange-alt"},
            {"id": "send_email", "label": "Send Email", "icon": "fa-envelope"},
            {"id": "delete", "label": "Delete Clients", "icon": "fa-trash", "danger": True},
            {"id": "export", "label": "Export to CSV", "icon": "fa-file-export"},
        ],
        EntityType.TASK: [
            {"id": "update_status", "label": "Update Status", "icon": "fa-exchange-alt"},
            {"id": "assign_user", "label": "Assign User", "icon": "fa-user-plus"},
            {"id": "delete", "label": "Delete Tasks", "icon": "fa-trash", "danger": True},
        ],
        EntityType.DOCUMENT: [
            {"id": "delete", "label": "Delete Documents", "icon": "fa-trash", "danger": True},
            {"id": "export", "label": "Download All", "icon": "fa-download"},
        ],
    }

    # Status options per entity
    STATUS_OPTIONS = {
        EntityType.CASE: [
            {"value": "intake", "label": "Intake"},
            {"value": "document_collection", "label": "Document Collection"},
            {"value": "drafting", "label": "Drafting"},
            {"value": "review", "label": "Review"},
            {"value": "filed", "label": "Filed"},
            {"value": "rfe", "label": "RFE"},
            {"value": "approved", "label": "Approved"},
            {"value": "denied", "label": "Denied"},
        ],
        EntityType.CLIENT: [
            {"value": "lead", "label": "Lead"},
            {"value": "prospect", "label": "Prospect"},
            {"value": "active", "label": "Active"},
            {"value": "inactive", "label": "Inactive"},
        ],
        EntityType.TASK: [
            {"value": "todo", "label": "To Do"},
            {"value": "in_progress", "label": "In Progress"},
            {"value": "completed", "label": "Completed"},
            {"value": "blocked", "label": "Blocked"},
        ],
    }

    def get_operations(self, entity_type: str) -> List[dict]:
        """Get available operations for an entity type."""
        return self.OPERATIONS.get(entity_type, [])

    def get_status_options(self, entity_type: str) -> List[dict]:
        """Get status options for an entity type."""
        return self.STATUS_OPTIONS.get(entity_type, [])

    def validate_operation(self, entity_type: str, operation: str) -> bool:
        """Check if operation is valid for entity type."""
        ops = self.get_operations(entity_type)
        return any(op["id"] == operation for op in ops)

    def generate_csv(self, headers: List[str], rows: List[List]) -> str:
        """Generate CSV content from data."""
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        return output.getvalue()


# SQL for bulk operation logs
CREATE_BULK_LOG_TABLE = """
CREATE TABLE IF NOT EXISTS bulk_operation_logs (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,
    operation VARCHAR(50) NOT NULL,
    entity_ids INTEGER[] NOT NULL,
    total_count INTEGER NOT NULL,
    success_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    parameters JSONB,
    status VARCHAR(20) DEFAULT 'completed',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    created_by INTEGER REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_bulk_log_entity ON bulk_operation_logs(entity_type);
CREATE INDEX IF NOT EXISTS idx_bulk_log_created ON bulk_operation_logs(created_at);
"""


# Singleton instance
bulk_service = BulkService()
