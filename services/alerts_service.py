"""
CaseHub - Alerts Service
Document expiration alerts and notifications.
"""
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from enum import Enum


class AlertType(str, Enum):
    DOCUMENT_EXPIRING = "document_expiring"
    DOCUMENT_EXPIRED = "document_expired"
    CASE_DEADLINE = "case_deadline"
    TASK_OVERDUE = "task_overdue"
    PAYMENT_DUE = "payment_due"
    STATUS_CHANGE = "status_change"
    SYSTEM = "system"


class AlertPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertsService:
    """Service for managing alerts and notifications."""

    # Alert thresholds for document expiration (days before expiry)
    EXPIRATION_THRESHOLDS = [90, 60, 30, 14, 7, 1, 0]

    # Document types that commonly expire
    EXPIRING_DOCUMENT_TYPES = [
        "passport",
        "visa",
        "ead",
        "i94",
        "driver_license",
        "travel_document",
        "work_permit",
        "medical_exam",
        "police_clearance"
    ]

    def get_expiring_documents(self, db_session, days_threshold: int = 90, org_id: int = None) -> List[Dict]:
        """Get documents expiring within the specified days.

        Args:
            db_session: Database session
            days_threshold: Number of days to look ahead

        Returns:
            List of expiring documents with client/case info
        """
        from sqlalchemy import text

        threshold_date = datetime.now() + timedelta(days=days_threshold)

        query = """
            SELECT d.id, d.name, d.doc_type, d.expiration_date, d.file_path,
                   c.id as case_id, c.case_number, c.case_name,
                   cl.id as client_id, cl.first_name, cl.last_name, cl.email
            FROM documents d
            LEFT JOIN cases c ON d.case_id = c.id
            LEFT JOIN clients cl ON cl.id = COALESCE(d.client_id, c.client_id)
            WHERE d.expiration_date IS NOT NULL
              AND d.expiration_date <= :threshold
              AND d.expiration_date >= CURRENT_DATE
              AND (:org_id IS NULL OR d.org_id = :org_id)
            ORDER BY d.expiration_date ASC
        """

        try:
            result = db_session.execute(text(query), {"threshold": threshold_date, "org_id": org_id})
            documents = []

            for row in result.fetchall():
                days_until = (row.expiration_date - datetime.now().date()).days
                priority = self._get_priority_for_days(days_until)

                documents.append({
                    "id": row.id,
                    "name": row.name,
                    "type": row.doc_type,
                    "expiration_date": row.expiration_date.isoformat() if row.expiration_date else None,
                    "days_until_expiry": days_until,
                    "priority": priority,
                    "case_id": row.case_id,
                    "case_number": row.case_number,
                    "case_name": row.case_name,
                    "client_id": row.client_id,
                    "client_name": f"{row.first_name} {row.last_name}" if row.first_name else None,
                    "client_email": row.email
                })

            return documents
        except Exception as e:
            db_session.rollback()
            return []

    def get_expired_documents(self, db_session, org_id: int = None) -> List[Dict]:
        """Get documents that have already expired."""
        from sqlalchemy import text

        query = """
            SELECT d.id, d.name, d.doc_type, d.expiration_date,
                   c.id as case_id, c.case_number,
                   cl.id as client_id, cl.first_name, cl.last_name
            FROM documents d
            LEFT JOIN cases c ON d.case_id = c.id
            LEFT JOIN clients cl ON cl.id = COALESCE(d.client_id, c.client_id)
            WHERE d.expiration_date IS NOT NULL
              AND d.expiration_date < CURRENT_DATE
              AND (:org_id IS NULL OR d.org_id = :org_id)
            ORDER BY d.expiration_date DESC
            LIMIT 100
        """

        try:
            result = db_session.execute(text(query), {"org_id": org_id})
            documents = []

            for row in result.fetchall():
                days_expired = (datetime.now().date() - row.expiration_date).days

                documents.append({
                    "id": row.id,
                    "name": row.name,
                    "type": row.doc_type,
                    "expiration_date": row.expiration_date.isoformat() if row.expiration_date else None,
                    "days_expired": days_expired,
                    "priority": AlertPriority.CRITICAL,
                    "case_id": row.case_id,
                    "case_number": row.case_number,
                    "client_id": row.client_id,
                    "client_name": f"{row.first_name} {row.last_name}" if row.first_name else None
                })

            return documents
        except Exception as e:
            db_session.rollback()
            return []

    def get_upcoming_deadlines(self, db_session, days: int = 30, org_id: int = None) -> List[Dict]:
        """Get cases with upcoming deadlines."""
        from sqlalchemy import text

        threshold_date = datetime.now() + timedelta(days=days)

        query = """
            SELECT c.id, c.case_number, c.case_name, c.visa_type,
                   c.expiration_date,
                   cl.first_name, cl.last_name
            FROM cases c
            LEFT JOIN clients cl ON c.client_id = cl.id
            WHERE c.expiration_date IS NOT NULL
              AND c.expiration_date <= :threshold
              AND c.expiration_date >= CURRENT_DATE
              AND (:org_id IS NULL OR c.org_id = :org_id)
            ORDER BY c.expiration_date ASC
        """

        try:
            result = db_session.execute(text(query), {"threshold": threshold_date, "org_id": org_id})
            deadlines = []

            for row in result.fetchall():
                deadline_date = row.expiration_date
                days_until = (deadline_date - datetime.now().date()).days
                priority = self._get_priority_for_days(days_until)

                deadlines.append({
                    "case_id": row.id,
                    "case_number": row.case_number,
                    "case_name": row.case_name,
                    "visa_type": row.visa_type,
                    "deadline_date": deadline_date.isoformat() if deadline_date else None,
                    "deadline_type": "expiration",
                    "days_until": days_until,
                    "priority": priority,
                    "client_name": f"{row.first_name} {row.last_name}" if row.first_name else None
                })

            return deadlines
        except Exception as e:
            db_session.rollback()
            return []

    def get_overdue_tasks(self, db_session, org_id: int = None) -> List[Dict]:
        """Get overdue tasks."""
        from sqlalchemy import text

        query = """
            SELECT t.id, t.title, t.description, t.due_date, t.priority as task_priority,
                   c.id as case_id, c.case_number,
                   u.name as assigned_to_name
            FROM tasks t
            LEFT JOIN cases c ON t.case_id = c.id
            LEFT JOIN users u ON t.assigned_to = u.id
            WHERE t.due_date < CURRENT_DATE
              AND t.status NOT IN ('completed', 'cancelled')
              AND (:org_id IS NULL OR t.org_id = :org_id)
            ORDER BY t.due_date ASC
        """

        try:
            result = db_session.execute(text(query), {"org_id": org_id})
            tasks = []

            for row in result.fetchall():
                days_overdue = (datetime.now().date() - row.due_date).days

                tasks.append({
                    "id": row.id,
                    "title": row.title,
                    "description": row.description,
                    "deadline": row.due_date.isoformat() if row.due_date else None,
                    "days_overdue": days_overdue,
                    "priority": AlertPriority.HIGH if days_overdue > 7 else AlertPriority.MEDIUM,
                    "case_id": row.case_id,
                    "case_number": row.case_number,
                    "assigned_to": row.assigned_to_name
                })

            return tasks
        except Exception as e:
            db_session.rollback()
            return []

    def get_alerts_summary(self, db_session, org_id: int = None) -> Dict:
        """Get summary of all alerts."""
        expiring_docs = self.get_expiring_documents(db_session, 30, org_id)
        expired_docs = self.get_expired_documents(db_session, org_id)
        deadlines = self.get_upcoming_deadlines(db_session, 30, org_id)
        overdue_tasks = self.get_overdue_tasks(db_session, org_id)

        # Count by priority
        critical = len([d for d in expired_docs]) + len([d for d in expiring_docs if d["days_until_expiry"] <= 7])
        high = len([d for d in expiring_docs if 7 < d["days_until_expiry"] <= 14]) + len(overdue_tasks)
        medium = len([d for d in expiring_docs if 14 < d["days_until_expiry"] <= 30])

        return {
            "expiring_documents": {
                "count": len(expiring_docs),
                "items": expiring_docs[:10]
            },
            "expired_documents": {
                "count": len(expired_docs),
                "items": expired_docs[:10]
            },
            "upcoming_deadlines": {
                "count": len(deadlines),
                "items": deadlines[:10]
            },
            "overdue_tasks": {
                "count": len(overdue_tasks),
                "items": overdue_tasks[:10]
            },
            "priority_counts": {
                "critical": critical,
                "high": high,
                "medium": medium,
                "total": critical + high + medium
            }
        }

    def _get_priority_for_days(self, days: int) -> str:
        """Get priority level based on days until expiry."""
        if days <= 0:
            return AlertPriority.CRITICAL
        elif days <= 7:
            return AlertPriority.HIGH
        elif days <= 30:
            return AlertPriority.MEDIUM
        else:
            return AlertPriority.LOW

    def create_alert_notification(
        self,
        db_session,
        alert_type: AlertType,
        title: str,
        message: str,
        priority: AlertPriority = AlertPriority.MEDIUM,
        entity_type: str = None,
        entity_id: int = None,
        user_id: int = None
    ) -> Dict:
        """Create a new alert notification."""
        from sqlalchemy import text
        import uuid

        alert_id = str(uuid.uuid4())[:8]

        try:
            db_session.execute(text("""
                INSERT INTO alert_notifications
                (alert_id, alert_type, title, message, priority, entity_type, entity_id, user_id)
                VALUES (:aid, :type, :title, :msg, :priority, :etype, :eid, :uid)
            """), {
                "aid": alert_id,
                "type": alert_type,
                "title": title,
                "msg": message,
                "priority": priority,
                "etype": entity_type,
                "eid": entity_id,
                "uid": user_id
            })
            db_session.commit()

            return {"success": True, "alert_id": alert_id}
        except Exception as e:
            db_session.rollback()
            return {"success": False, "error": str(e)}


# SQL for alerts table
CREATE_ALERTS_TABLE = """
CREATE TABLE IF NOT EXISTS alert_notifications (
    id SERIAL PRIMARY KEY,
    alert_id VARCHAR(20) UNIQUE NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    message TEXT,
    priority VARCHAR(20) DEFAULT 'medium',
    entity_type VARCHAR(50),
    entity_id INTEGER,
    user_id INTEGER REFERENCES users(id),
    is_read BOOLEAN DEFAULT false,
    is_dismissed BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW(),
    read_at TIMESTAMP,
    dismissed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_alerts_type ON alert_notifications(alert_type);
CREATE INDEX IF NOT EXISTS idx_alerts_user ON alert_notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_read ON alert_notifications(is_read);
CREATE INDEX IF NOT EXISTS idx_alerts_priority ON alert_notifications(priority);
"""


# Singleton instance
alerts_service = AlertsService()
