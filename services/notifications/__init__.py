"""
CaseHub - Unified Notifications Package
Re-exports all notification functions from submodules for a single import point.

Usage:
    from services.notifications import create_notification, send_email
    from services.notifications import notify_client_approval, notify_client_rejection
    from services.notifications import send_task_notification_email
    from services.notifications import notify_victor_urgent
"""

# In-app notifications (DB-backed Notification model)
from services.notifications.in_app import (
    create_notification,
    create_notification_for_all_staff,
)

# Email notifications to clients (SMTP, document status changes)
from services.notifications.email import (
    send_email,
    load_email_template,
    notify_client_approval,
    notify_client_rejection,
    CC_EMAIL,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    FROM_EMAIL,
    TEMPLATES_DIR,
)

# Staff/paralegal task notification emails
from services.notifications.staff import (
    send_task_notification_email,
    PARALEGAL_EMAILS,
)

# Urgent multi-channel notifications (email, WhatsApp, Google Chat)
from services.notifications.urgent import (
    notify_victor_urgent,
    notify_victor_email,
    notify_paralegal_email,
    notify_victor_whatsapp,
    notify_victor_google_chat,
)

__all__ = [
    # in_app
    "create_notification",
    "create_notification_for_all_staff",
    # email
    "send_email",
    "load_email_template",
    "notify_client_approval",
    "notify_client_rejection",
    "CC_EMAIL",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "FROM_EMAIL",
    "TEMPLATES_DIR",
    # staff
    "send_task_notification_email",
    "PARALEGAL_EMAILS",
    # urgent
    "notify_victor_urgent",
    "notify_victor_email",
    "notify_paralegal_email",
    "notify_victor_whatsapp",
    "notify_victor_google_chat",
]
