"""
Backward-compatible shim. Moved to services/notifications/email.py
"""
from services.notifications.email import (  # noqa: F401
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    FROM_EMAIL,
    CC_EMAIL,
    TEMPLATES_DIR,
    load_email_template,
    send_email,
    notify_client_approval,
    notify_client_rejection,
)
