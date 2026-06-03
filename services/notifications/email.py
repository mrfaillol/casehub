#!/usr/bin/env python3
"""
Email Notifications Service - CaseHub
Sends email notifications to clients about document status changes.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from jinja2 import Template
from sqlalchemy.orm import Session
from models.tenant import tenant_query
from config import settings

logger = logging.getLogger(__name__)

# Email configuration
SMTP_HOST = os.getenv("SMTP_HOST", settings.SMTP_HOST)
SMTP_PORT = int(os.getenv("SMTP_PORT", str(settings.SMTP_PORT)))
SMTP_USER = os.getenv("SMTP_USER", settings.SMTP_USER)
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL = settings.from_email
CC_EMAIL = settings.ORG_EMAIL

# Templates directory
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates" / "emails"


def _notification_query(db: Session, model, org_id: int = None):
    """Use tenant scoping when org_id is known; background jobs may run globally."""
    if org_id is None:
        return db.query(model)
    return tenant_query(db, model, org_id)


def load_email_template(template_name: str) -> str:
    """Load an email template from file."""
    template_path = TEMPLATES_DIR / template_name
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Email template not found: {template_path}")
        return ""


def send_email(to_email: str, subject: str, html_body: str, cc: str = None) -> bool:
    """
    Send an HTML email using SMTP.

    Args:
        to_email: Recipient email address
        subject: Email subject
        html_body: HTML content
        cc: Optional CC email address

    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        # Create message
        msg = MIMEMultipart('alternative')
        msg['From'] = FROM_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject

        if cc:
            msg['Cc'] = cc

        # Attach HTML body
        html_part = MIMEText(html_body, 'html', 'utf-8')
        msg.attach(html_part)

        # Send email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            if SMTP_PASSWORD:
                server.login(SMTP_USER, SMTP_PASSWORD)

            recipients = [to_email]
            if cc:
                recipients.append(cc)

            server.sendmail(FROM_EMAIL, recipients, msg.as_string())

        logger.info(f"Email sent successfully to {to_email}: {subject}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


def notify_client_approval(db: Session, document_id: int, org_id: int = None) -> Dict[str, Any]:
    """
    Send approval notification email to client.

    Args:
        db: Database session
        document_id: ID of the approved document

    Returns:
        Dict with notification result
    """
    result = {
        "success": False,
        "email_sent": False,
        "error": None
    }

    try:
        from models import Document, Client

        # Get document
        doc = _notification_query(db, Document, org_id).filter(Document.id == document_id).first()
        if not doc:
            result["error"] = f"Document {document_id} not found"
            return result

        # Get client
        if not doc.client_id:
            result["error"] = "Document has no associated client"
            return result

        client = _notification_query(db, Client, org_id).filter(Client.id == doc.client_id).first()
        if not client:
            result["error"] = f"Client {doc.client_id} not found"
            return result

        # Check if client has email
        if not client.email:
            result["error"] = "Client has no email address"
            logger.warning(f"Cannot notify client {client.id}: no email")
            return result

        # Get portal link if document came from intake
        portal_link = None
        intake_package_id = getattr(doc, "intake_package_id", None)
        if isinstance(intake_package_id, int) and intake_package_id > 0:
            from sqlalchemy import text
            package = db.execute(
                text("SELECT package_id, access_token FROM intake_packages WHERE id = :id"),
                {"id": intake_package_id},
            ).mappings().first()
            if package:
                base_url = (settings.BASE_URL or "").rstrip("/")
                portal_link = f"{base_url}/intake/{package['package_id']}?token={package['access_token']}"

        # Load template
        template_html = load_email_template("document_approved.html")
        if not template_html:
            result["error"] = "Email template not found"
            return result

        # Render template
        template = Template(template_html)
        html_body = template.render(
            client_name=f"{client.first_name} {client.last_name}".strip() or "Client",
            document_name=doc.name,
            document_type=doc.doc_type or "Document",
            upload_date=doc.created_at.strftime("%B %d, %Y") if doc.created_at else "N/A",
            review_date=doc.reviewed_at.strftime("%B %d, %Y") if doc.reviewed_at else "Today",
            portal_link=portal_link,
            additional_docs_needed=False,  # TODO: Check if package has pending items
            current_year=datetime.now().year
        )

        # Send email
        subject = f"Document Approved: {doc.name}"
        email_sent = send_email(
            to_email=client.email,
            subject=subject,
            html_body=html_body,
            cc=CC_EMAIL
        )

        result["email_sent"] = email_sent
        result["success"] = email_sent

        # Update database
        if email_sent:
            doc.approval_notification_sent = True
            doc.client_notified_at = datetime.now()
            db.commit()

    except Exception as e:
        result["error"] = f"Notification error: {str(e)}"
        logger.exception(f"Error sending approval notification for document {document_id}")

    return result


def notify_client_rejection(db: Session, document_id: int, org_id: int = None) -> Dict[str, Any]:
    """
    Send rejection notification email to client.

    Args:
        db: Database session
        document_id: ID of the rejected document

    Returns:
        Dict with notification result
    """
    result = {
        "success": False,
        "email_sent": False,
        "error": None
    }

    try:
        from models import Document, Client

        # Get document
        doc = _notification_query(db, Document, org_id).filter(Document.id == document_id).first()
        if not doc:
            result["error"] = f"Document {document_id} not found"
            return result

        # Get client
        if not doc.client_id:
            result["error"] = "Document has no associated client"
            return result

        client = _notification_query(db, Client, org_id).filter(Client.id == doc.client_id).first()
        if not client:
            result["error"] = f"Client {doc.client_id} not found"
            return result

        # Check if client has email
        if not client.email:
            result["error"] = "Client has no email address"
            logger.warning(f"Cannot notify client {client.id}: no email")
            return result

        # Get portal link if document came from intake
        portal_link = None
        intake_package_id = getattr(doc, "intake_package_id", None)
        if isinstance(intake_package_id, int) and intake_package_id > 0:
            from sqlalchemy import text
            package = db.execute(
                text("SELECT package_id, access_token FROM intake_packages WHERE id = :id"),
                {"id": intake_package_id},
            ).mappings().first()
            if package:
                base_url = (settings.BASE_URL or "").rstrip("/")
                portal_link = f"{base_url}/intake/{package['package_id']}?token={package['access_token']}"

        # Load template
        template_html = load_email_template("document_rejected.html")
        if not template_html:
            result["error"] = "Email template not found"
            return result

        # Render template
        template = Template(template_html)
        html_body = template.render(
            client_name=f"{client.first_name} {client.last_name}".strip() or "Client",
            document_name=doc.name,
            document_type=doc.doc_type or "Document",
            upload_date=doc.created_at.strftime("%B %d, %Y") if doc.created_at else "N/A",
            review_date=doc.reviewed_at.strftime("%B %d, %Y") if doc.reviewed_at else "Today",
            rejection_reason=doc.rejection_reason or "The document does not meet our requirements. Please contact us for details.",
            portal_link=portal_link,
            current_year=datetime.now().year
        )

        # Send email
        subject = f"Document Needs Attention: {doc.name}"
        email_sent = send_email(
            to_email=client.email,
            subject=subject,
            html_body=html_body,
            cc=CC_EMAIL
        )

        result["email_sent"] = email_sent
        result["success"] = email_sent

        # Update database
        if email_sent:
            doc.rejection_notification_sent = True
            doc.client_notified_at = datetime.now()
            db.commit()

    except Exception as e:
        result["error"] = f"Notification error: {str(e)}"
        logger.exception(f"Error sending rejection notification for document {document_id}")

    return result
