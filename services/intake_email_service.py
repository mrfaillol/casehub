#!/usr/bin/env python3
"""
Intake Email Service - CaseHub
Sends intake package invitations to clients with link validation.
"""

import os
import logging
import html
import requests
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from jinja2 import Template
from config import settings

# Import send_email from notifications package
from services.notifications import send_email, load_email_template, CC_EMAIL

logger = logging.getLogger(__name__)

# Log file for intake emails
INTAKE_LOG_DIR = Path(__file__).parent.parent / "logs"
INTAKE_LOG_FILE = INTAKE_LOG_DIR / "intake_emails.log"


def setup_intake_logger():
    """Setup dedicated logger for intake email operations."""
    # Ensure log directory exists
    INTAKE_LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Create file handler
    file_handler = logging.FileHandler(INTAKE_LOG_FILE, encoding='utf-8')
    file_handler.setLevel(logging.INFO)

    # Create formatter
    formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(formatter)

    # Add handler to logger
    intake_logger = logging.getLogger('intake_emails')
    intake_logger.setLevel(logging.INFO)

    # Avoid duplicate handlers
    if not intake_logger.handlers:
        intake_logger.addHandler(file_handler)

    return intake_logger


# Initialize intake logger
intake_logger = setup_intake_logger()


def validate_link_before_sending(link: str, timeout: int = 10) -> Dict[str, Any]:
    """
    Validate that an intake link is accessible before sending it to a client.

    Makes an HTTP HEAD request to verify the link returns HTTP 200.
    This prevents sending broken links to clients.

    Args:
        link: The intake link URL to validate
        timeout: Request timeout in seconds (default: 10)

    Returns:
        Dict with validation result:
        {
            "valid": bool,
            "status_code": int or None,
            "error": str or None
        }
    """
    result = {
        "valid": False,
        "status_code": None,
        "error": None
    }

    try:
        # Make HEAD request (faster than GET, doesn't download full page)
        response = requests.get(link, timeout=timeout, allow_redirects=True, stream=True)
        result["status_code"] = response.status_code

        # Consider 200 OK and 302/301 redirects as valid
        if response.status_code in [200, 301, 302]:
            result["valid"] = True
            intake_logger.info(f"LINK_VALIDATION | link={link} | status={response.status_code} | valid=TRUE")
        else:
            result["error"] = f"HTTP {response.status_code}"
            intake_logger.warning(f"LINK_VALIDATION | link={link} | status={response.status_code} | valid=FALSE")

    except requests.exceptions.Timeout:
        result["error"] = "Request timeout"
        intake_logger.error(f"LINK_VALIDATION | link={link} | error=TIMEOUT")

    except requests.exceptions.ConnectionError:
        result["error"] = "Connection error"
        intake_logger.error(f"LINK_VALIDATION | link={link} | error=CONNECTION_ERROR")

    except Exception as e:
        result["error"] = str(e)
        intake_logger.error(f"LINK_VALIDATION | link={link} | error={str(e)}")

    return result


def send_intake_email(
    client_email: str,
    client_name: str,
    package_name: str,
    intake_link: str,
    expires_at: Optional[datetime] = None,
    package_id: str = "",
    case_number: str = "",
    validate_link: bool = True
) -> Dict[str, Any]:
    """
    Send intake package invitation email to client.

    Args:
        client_email: Client's email address
        client_name: Client's full name
        package_name: Name of the intake package
        intake_link: The secure intake form link
        expires_at: Link expiration date (optional)
        package_id: Package ID for logging
        case_number: Case number for email context
        validate_link: Whether to validate link before sending (default: True)

    Returns:
        Dict with send result:
        {
            "success": bool,
            "email_sent": bool,
            "link_validated": bool,
            "error": str or None
        }
    """
    result = {
        "success": False,
        "email_sent": False,
        "link_validated": False,
        "validation_error": None,
        "send_error": None
    }

    intake_logger.info(f"SEND_ATTEMPT | package_id={package_id} | client_email={client_email}")

    try:
        # Step 1: Validate link if requested
        if validate_link:
            validation = validate_link_before_sending(intake_link)
            result["link_validated"] = validation["valid"]

            if not validation["valid"]:
                result["validation_error"] = validation["error"]
                intake_logger.error(
                    f"SEND_ABORTED | package_id={package_id} | reason=INVALID_LINK | "
                    f"error={validation['error']}"
                )
                return result
        else:
            result["link_validated"] = True  # Skipped validation

        # Step 2: Load and render email template
        template_html = load_email_template("intake_invitation.html")
        if not template_html:
            result["send_error"] = "Email template not found"
            intake_logger.error(
                f"SEND_FAILED | package_id={package_id} | reason=TEMPLATE_NOT_FOUND"
            )
            return result

        # Prepare template variables
        expires_text = (
            expires_at.strftime("%B %d, %Y")
            if expires_at
            else "Not specified"
        )

        template = Template(template_html)
        html_body = template.render(
            client_name=client_name,
            package_name=package_name,
            intake_link=intake_link,
            expires_at=expires_text,
            case_number=case_number or "N/A",
            current_year=datetime.now().year
        )

        # Step 3: Send email
        subject = f"Complete Your Immigration Forms - {package_name}"

        email_sent = send_email(
            to_email=client_email,
            subject=subject,
            html_body=html_body,
            cc=CC_EMAIL
        )

        result["email_sent"] = email_sent
        result["success"] = email_sent

        if email_sent:
            intake_logger.info(
                f"EMAIL_SENT | package_id={package_id} | client_email={client_email} | "
                f"subject={subject}"
            )
        else:
            result["send_error"] = "SMTP send failed"
            intake_logger.error(
                f"SEND_FAILED | package_id={package_id} | reason=SMTP_ERROR"
            )

    except Exception as e:
        result["send_error"] = str(e)
        intake_logger.exception(
            f"SEND_EXCEPTION | package_id={package_id} | error={str(e)}"
        )

    return result


def send_custom_message(
    client_email: str,
    client_name: str,
    message: str,
    package_id: str = "",
    send_via_email: bool = True,
    send_via_whatsapp: bool = False
) -> Dict[str, Any]:
    """
    Send a custom message to client about their intake package.

    Args:
        client_email: Client's email address
        client_name: Client's full name
        message: Custom message text
        package_id: Package ID for logging
        send_via_email: Whether to send via email
        send_via_whatsapp: Whether to send via WhatsApp (future implementation)

    Returns:
        Dict with send result
    """
    result = {
        "success": False,
        "email_sent": False,
        "whatsapp_sent": False,
        "error": None
    }

    intake_logger.info(
        f"CUSTOM_MESSAGE | package_id={package_id} | client_email={client_email} | "
        f"via_email={send_via_email} | via_whatsapp={send_via_whatsapp}"
    )

    try:
        if send_via_email:
            # Simple text-based email for custom messages
            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
            </head>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #2c5282;">Message from {settings.ORG_NAME}</h2>

                    <p>Dear {html.escape(client_name)},</p>

                    <div style="background: #f7fafc; padding: 15px; border-left: 4px solid #4299e1; margin: 20px 0;">
                        {html.escape(message).replace(chr(10), '<br>')}
                    </div>

                    <p>If you have any questions, please don't hesitate to reply to this email.</p>

                    <p style="margin-top: 30px;">
                        Respectfully,<br>
                        <strong>{settings.ORG_NAME}</strong>
                    </p>

                    <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 30px 0;">

                    <p style="font-size: 12px; color: #718096; text-align: center;">
                        © {datetime.now().year} {settings.ORG_NAME}. All rights reserved.
                    </p>
                </div>
            </body>
            </html>
            """

            subject = "Message About Your Immigration Case"

            email_sent = send_email(
                to_email=client_email,
                subject=subject,
                html_body=html_body,
                cc=CC_EMAIL
            )

            result["email_sent"] = email_sent

            if email_sent:
                intake_logger.info(
                    f"CUSTOM_MESSAGE_SENT | package_id={package_id} | via=EMAIL"
                )

        # WhatsApp integration (future implementation)
        if send_via_whatsapp:
            # TODO: Integrate with WhatsApp Bot API
            intake_logger.info(
                f"CUSTOM_MESSAGE_SKIPPED | package_id={package_id} | via=WHATSAPP | "
                f"reason=NOT_IMPLEMENTED"
            )

        result["success"] = result["email_sent"] or result["whatsapp_sent"]

    except Exception as e:
        result["error"] = str(e)
        intake_logger.exception(
            f"CUSTOM_MESSAGE_EXCEPTION | package_id={package_id} | error={str(e)}"
        )

    return result
