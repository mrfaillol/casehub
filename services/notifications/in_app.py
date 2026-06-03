"""
CaseHub - Notification Service
Creates in-app notifications and optionally sends email alerts to staff.
"""
import logging
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from config import settings
from models.notification import Notification
from models.user import User
from models.tenant import tenant_query

logger = logging.getLogger(__name__)


def create_notification(
    db: Session,
    user_id: int,
    title: str,
    notification_type: str,
    message: str = "",
    severity: str = "info",
    client_id: int = None,
    case_id: int = None,
    document_id: int = None,
    task_id: int = None,
    action_url: str = None,
) -> Optional[Notification]:
    """Create a single in-app notification for a specific user."""
    try:
        notif = Notification(
            user_id=user_id,
            title=title[:255],
            message=message,
            notification_type=notification_type,
            severity=severity,
            client_id=client_id,
            case_id=case_id,
            document_id=document_id,
            task_id=task_id,
            action_url=action_url,
        )
        db.add(notif)
        db.flush()
        logger.info(f"Notification #{notif.id}: [{notification_type}] {title[:60]} for user {user_id}")
        return notif
    except Exception as e:
        logger.error(f"Failed to create notification: {e}")
        return None


def create_notification_for_all_staff(
    db: Session,
    title: str,
    notification_type: str,
    message: str = "",
    severity: str = "info",
    client_id: int = None,
    case_id: int = None,
    document_id: int = None,
    task_id: int = None,
    action_url: str = None,
    send_email_to: List[str] = None,
    org_id: int = None,
) -> List[Notification]:
    """Create notification for all enabled staff users. Optionally send email."""
    notifications = []
    try:
        users = tenant_query(db, User, org_id).filter(User.enabled == True).all()
        for user in users:
            notif = create_notification(
                db=db,
                user_id=user.id,
                title=title,
                notification_type=notification_type,
                message=message,
                severity=severity,
                client_id=client_id,
                case_id=case_id,
                document_id=document_id,
                task_id=task_id,
                action_url=action_url,
            )
            if notif:
                notifications.append(notif)

        if send_email_to:
            _send_staff_email(title, message, notification_type, action_url, send_email_to)
            for notif in notifications:
                notif.email_sent = True
                notif.email_sent_at = datetime.utcnow()

    except Exception as e:
        logger.error(f"Failed to create staff notifications: {e}")

    return notifications


def _send_staff_email(title: str, message: str, notif_type: str, action_url: str, recipients: List[str]):
    """Send notification email to staff addresses."""
    try:
        from services.notifications.email import send_email

        type_labels = {
            "document_received": "New Document",
            "document_approved": "Document Approved",
            "document_rejected": "Document Rejected",
            "task_created": "New Task",
            "deadline_approaching": "Deadline Alert",
            "client_email": "Client Email",
            "whatsapp_message": "WhatsApp Message",
        }
        type_label = type_labels.get(notif_type, "Notification")

        type_colors = {
            "document_received": "#3b82f6",
            "client_email": "#667eea",
            "task_created": "#10b981",
            "deadline_approaching": "#f59e0b",
            "document_approved": "#10b981",
            "document_rejected": "#ef4444",
            "whatsapp_message": "#25D366",
        }
        color = type_colors.get(notif_type, "#667eea")

        action_btn = ""
        if action_url:
            full_url = f"{settings.BASE_URL}{action_url}"
            action_btn = f'''
            <div style="text-align:center; margin:20px 0;">
                <a href="{full_url}"
                   style="display:inline-block; background:linear-gradient(135deg, #667eea, #764ba2);
                          color:white; padding:12px 30px; text-decoration:none; border-radius:25px;
                          font-weight:bold;">View in CaseHub</a>
            </div>'''

        html_body = f"""
        <div style="font-family:Arial,sans-serif; max-width:600px; margin:0 auto;">
            <div style="background:linear-gradient(135deg, {color} 0%, #764ba2 100%);
                        padding:20px; border-radius:10px 10px 0 0;">
                <h2 style="color:white; margin:0;">{type_label}</h2>
            </div>
            <div style="background:#f8f9fa; padding:20px; border:1px solid #e9ecef;">
                <h3 style="margin:0 0 10px 0; color:#333;">{title}</h3>
                <p style="color:#666; margin:0 0 15px 0;">{message}</p>
                {action_btn}
            </div>
            <div style="background:#343a40; color:#adb5bd; padding:15px; text-align:center;
                        border-radius:0 0 10px 10px; font-size:12px;">
                <p style="margin:0;">Automated notification from CaseHub</p>
                <p style="margin:5px 0 0 0;">{settings.ORG_NAME}</p>
            </div>
        </div>"""

        subject = f"CaseHub: {title[:80]}"
        for recipient in recipients:
            send_email(to_email=recipient, subject=subject, html_body=html_body)

        logger.info(f"Staff notification email sent to {recipients}")
    except Exception as e:
        logger.error(f"Failed to send staff notification email: {e}")
