"""
CaseHub - Audit Trail Service
Logs all important actions in the system for compliance and security
"""
import json
import logging
from datetime import datetime
from typing import Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


class AuditService:
    """Service for logging audit trail events."""

    # Action types
    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_DELETE = "delete"
    ACTION_VIEW = "view"
    ACTION_LOGIN = "login"
    ACTION_LOGOUT = "logout"
    ACTION_EXPORT = "export"
    ACTION_IMPORT = "import"
    ACTION_EMAIL = "email"
    ACTION_STATUS_CHANGE = "status_change"

    # Entity types
    ENTITY_CLIENT = "client"
    ENTITY_CASE = "case"
    ENTITY_DOCUMENT = "document"
    ENTITY_TASK = "task"
    ENTITY_INVOICE = "invoice"
    ENTITY_USER = "user"
    ENTITY_BILLING = "billing"
    ENTITY_TIME_ENTRY = "time_entry"
    ENTITY_QUESTIONNAIRE = "questionnaire"

    def __init__(self, db: Session, org_id: int = None):
        self.db = db
        self.org_id = org_id

    def log(
        self,
        action: str,
        entity_type: str,
        entity_id: Optional[int] = None,
        user_id: Optional[int] = None,
        user_email: Optional[str] = None,
        description: Optional[str] = None,
        old_values: Optional[dict] = None,
        new_values: Optional[dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        metadata: Optional[dict] = None
    ):
        """Log an audit event."""
        try:
            # Build details JSON
            details = {}
            if old_values:
                details["old"] = old_values
            if new_values:
                details["new"] = new_values
            if metadata:
                details["metadata"] = metadata

            self.db.execute(text("""
                INSERT INTO audit_log (
                    action, entity_type, entity_id, user_id, user_email,
                    description, details, ip_address, user_agent, org_id, created_at
                ) VALUES (
                    :action, :entity_type, :entity_id, :user_id, :user_email,
                    :description, :details, :ip_address, :user_agent, :org_id, NOW()
                )
            """), {
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "user_id": user_id,
                "user_email": user_email,
                "description": description,
                "details": json.dumps(details) if details else None,
                "ip_address": ip_address,
                "user_agent": user_agent[:500] if user_agent else None,
                "org_id": self.org_id
            })
            self.db.commit()
            return True
        except Exception as e:
            logger.critical(f"AUDIT LOGGING FAILED: {e}")
            return False

    def log_client_action(
        self,
        action: str,
        client_id: int,
        user_id: int,
        user_email: str,
        description: str = None,
        old_values: dict = None,
        new_values: dict = None,
        ip_address: str = None
    ):
        """Log client-related action."""
        return self.log(
            action=action,
            entity_type=self.ENTITY_CLIENT,
            entity_id=client_id,
            user_id=user_id,
            user_email=user_email,
            description=description or f"Client {action}",
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address
        )

    def log_case_action(
        self,
        action: str,
        case_id: int,
        user_id: int,
        user_email: str,
        description: str = None,
        old_values: dict = None,
        new_values: dict = None,
        ip_address: str = None
    ):
        """Log case-related action."""
        return self.log(
            action=action,
            entity_type=self.ENTITY_CASE,
            entity_id=case_id,
            user_id=user_id,
            user_email=user_email,
            description=description or f"Case {action}",
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address
        )

    def log_login(
        self,
        user_id: int,
        user_email: str,
        success: bool,
        ip_address: str = None,
        user_agent: str = None
    ):
        """Log login attempt."""
        return self.log(
            action=self.ACTION_LOGIN,
            entity_type=self.ENTITY_USER,
            entity_id=user_id,
            user_id=user_id,
            user_email=user_email,
            description=f"Login {'successful' if success else 'failed'}",
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"success": success}
        )

    def get_entity_history(
        self,
        entity_type: str,
        entity_id: int,
        limit: int = 50
    ) -> list:
        """Get audit history for a specific entity."""
        result = self.db.execute(text("""
            SELECT * FROM audit_log
            WHERE entity_type = :entity_type AND entity_id = :entity_id
            ORDER BY created_at DESC
            LIMIT :limit
        """), {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "limit": limit
        })
        return result.fetchall()

    def get_user_activity(
        self,
        user_id: int,
        limit: int = 100
    ) -> list:
        """Get all activity for a specific user."""
        result = self.db.execute(text("""
            SELECT * FROM audit_log
            WHERE user_id = :user_id
            ORDER BY created_at DESC
            LIMIT :limit
        """), {"user_id": user_id, "limit": limit})
        return result.fetchall()

    def get_recent_activity(
        self,
        limit: int = 100,
        action_filter: str = None,
        entity_filter: str = None
    ) -> list:
        """Get recent system activity."""
        query = "SELECT * FROM audit_log WHERE 1=1"
        params = {"limit": limit}

        if self.org_id:
            query += " AND org_id = :org_id"
            params["org_id"] = self.org_id
        if action_filter:
            query += " AND action = :action"
            params["action"] = action_filter
        if entity_filter:
            query += " AND entity_type = :entity_type"
            params["entity_type"] = entity_filter

        query += " ORDER BY created_at DESC LIMIT :limit"

        result = self.db.execute(text(query), params)
        return result.fetchall()


def get_audit_service(db: Session, org_id: int = None) -> AuditService:
    """Get audit service instance."""
    return AuditService(db, org_id=org_id)
