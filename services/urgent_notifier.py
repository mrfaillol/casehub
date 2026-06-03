"""
Backward-compatible shim. Moved to services/notifications/urgent.py
"""
from services.notifications.urgent import (  # noqa: F401
    VICTOR_EMAIL,
    VICTOR_WHATSAPP,
    GOOGLE_CHAT_WEBHOOK_VICTOR,
    PARALEGAL_EMAILS,
    notify_victor_email,
    notify_paralegal_email,
    notify_victor_whatsapp,
    notify_victor_google_chat,
    notify_victor_urgent,
)
