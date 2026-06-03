"""
Backward-compatible shim. Moved to services/notifications/staff.py
"""
from services.notifications.staff import (  # noqa: F401
    PARALEGAL_EMAILS,
    send_task_notification_email,
)
