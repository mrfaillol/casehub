"""
CaseHub - Global Alerts Service
System-wide alert banners for announcements, maintenance notices, etc.
"""
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from enum import Enum


class AlertType(str, Enum):
    INFO = "info"
    WARNING = "warning"
    DANGER = "danger"
    SUCCESS = "success"


class AlertTarget(str, Enum):
    ALL = "all"
    STAFF = "staff"
    CLIENTS = "clients"
    CASE = "case"
    CLIENT = "client"


class GlobalAlertsService:
    """Service for managing global alert banners."""

    def create_alert(
        self,
        title: str,
        message: str,
        alert_type: str = AlertType.INFO,
        target: str = AlertTarget.ALL,
        target_id: int = None,
        start_date: datetime = None,
        end_date: datetime = None,
        dismissible: bool = True,
        priority: int = 0
    ) -> dict:
        """Create a new global alert."""
        return {
            "title": title,
            "message": message,
            "alert_type": alert_type,
            "target": target,
            "target_id": target_id,
            "start_date": start_date or datetime.now(),
            "end_date": end_date,
            "dismissible": dismissible,
            "priority": priority,
            "is_active": True,
            "created_at": datetime.now()
        }

    def get_bootstrap_class(self, alert_type: str) -> str:
        """Get Bootstrap alert class for alert type."""
        classes = {
            AlertType.INFO: "alert-info",
            AlertType.WARNING: "alert-warning",
            AlertType.DANGER: "alert-danger",
            AlertType.SUCCESS: "alert-success"
        }
        return classes.get(alert_type, "alert-info")

    def get_icon(self, alert_type: str) -> str:
        """Get Font Awesome icon for alert type."""
        icons = {
            AlertType.INFO: "fa-info-circle",
            AlertType.WARNING: "fa-exclamation-triangle",
            AlertType.DANGER: "fa-exclamation-circle",
            AlertType.SUCCESS: "fa-check-circle"
        }
        return icons.get(alert_type, "fa-info-circle")

    def is_alert_active(self, alert: dict) -> bool:
        """Check if an alert is currently active."""
        now = datetime.now()

        if not alert.get("is_active"):
            return False

        start_date = alert.get("start_date")
        if start_date and isinstance(start_date, datetime) and start_date > now:
            return False

        end_date = alert.get("end_date")
        if end_date and isinstance(end_date, datetime) and end_date < now:
            return False

        return True

    def filter_alerts_for_user(
        self,
        alerts: List[dict],
        user_type: str = "staff",
        case_id: int = None,
        client_id: int = None,
        dismissed_ids: List[int] = None
    ) -> List[dict]:
        """Filter alerts based on user context."""
        dismissed_ids = dismissed_ids or []
        filtered = []

        for alert in alerts:
            # Skip dismissed alerts
            if alert.get("id") in dismissed_ids:
                continue

            # Check if alert is active
            if not self.is_alert_active(alert):
                continue

            target = alert.get("target", AlertTarget.ALL)

            # Check target matching
            if target == AlertTarget.ALL:
                filtered.append(alert)
            elif target == AlertTarget.STAFF and user_type == "staff":
                filtered.append(alert)
            elif target == AlertTarget.CLIENTS and user_type == "client":
                filtered.append(alert)
            elif target == AlertTarget.CASE and case_id and alert.get("target_id") == case_id:
                filtered.append(alert)
            elif target == AlertTarget.CLIENT and client_id and alert.get("target_id") == client_id:
                filtered.append(alert)

        # Sort by priority (higher first) then by created date (newer first)
        filtered.sort(key=lambda x: (x.get("priority", 0), x.get("created_at", datetime.min)), reverse=True)

        return filtered


# SQL for global alerts tables
CREATE_GLOBAL_ALERTS_TABLE = """
CREATE TABLE IF NOT EXISTS global_alerts (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    alert_type VARCHAR(20) DEFAULT 'info',
    target VARCHAR(20) DEFAULT 'all',
    target_id INTEGER,
    start_date TIMESTAMP DEFAULT NOW(),
    end_date TIMESTAMP,
    dismissible BOOLEAN DEFAULT true,
    priority INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by INTEGER REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_global_alerts_active ON global_alerts(is_active);
CREATE INDEX IF NOT EXISTS idx_global_alerts_target ON global_alerts(target, target_id);
CREATE INDEX IF NOT EXISTS idx_global_alerts_dates ON global_alerts(start_date, end_date);

CREATE TABLE IF NOT EXISTS dismissed_alerts (
    id SERIAL PRIMARY KEY,
    alert_id INTEGER REFERENCES global_alerts(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id),
    dismissed_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(alert_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_dismissed_alerts_user ON dismissed_alerts(user_id);
"""


# Singleton instance
global_alerts_service = GlobalAlertsService()
