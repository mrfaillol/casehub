"""
Backward-compatible shim. Moved to services/notifications/in_app.py
"""
from services.notifications.in_app import (  # noqa: F401
    create_notification,
    create_notification_for_all_staff,
    _send_staff_email,
)
