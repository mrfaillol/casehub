"""
Backward-compatible shim. Moved to services/notifications/urgent.py
"""
from services.notifications.urgent import (  # noqa: F401
    ADMIN_ALERT_EMAIL,
    ADMIN_ALERT_WHATSAPP,
    GOOGLE_CHAT_WEBHOOK_ADMIN,
    PARALEGAL_EMAILS,
    notify_casehub_team_email,
    notify_paralegal_email,
    notify_casehub_team_whatsapp,
    notify_casehub_team_google_chat,
    notify_casehub_team_urgent,
)
