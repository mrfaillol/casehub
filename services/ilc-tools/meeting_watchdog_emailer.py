"""
Meeting Watchdog - Threaded Email Sender
Sends confirmation emails that thread into the original conversation.
Uses In-Reply-To and References headers for Gmail threading.
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict
from dotenv import load_dotenv

from meeting_watchdog_timezone import format_for_client
from meeting_watchdog_templates import get_confirmation_body

load_dotenv()

logger = logging.getLogger(__name__)

GMAIL_EMAIL = os.getenv("GMAIL_CENTER_EMAIL", "info@casehub.app")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_CENTER_APP_PASSWORD", "")


def _get_auto_cc(client_info: dict) -> list:
    """Get automatic CC recipients from client info."""
    cc = [os.getenv("ORG_EMAIL", "info@casehub.app")]
    if client_info.get("cc_always"):
        for addr in client_info["cc_always"]:
            if addr.lower() not in [c.lower() for c in cc]:
                cc.append(addr)
    return cc


def _clean_subject(subject: str) -> str:
    """Ensure subject starts with Re: (for threading)."""
    # Remove existing Re: prefixes
    clean = subject
    while clean.lower().startswith("re:"):
        clean = clean[3:].strip()
    return f"Re: {clean}"


def send_confirmation_email(
    client_email: str,
    client_info: dict,
    confirmed_dt_est,
    meet_link: str,
    meeting_type: str = "attorney",
    original_subject: str = "",
    in_reply_to: str = "",
    references: str = "",
) -> Dict:
    """
    Send a meeting confirmation email threaded into the original conversation.

    Args:
        client_email: Client's email address
        client_info: CLIENT_MAPPING entry
        confirmed_dt_est: Confirmed datetime in EST
        meet_link: Google Meet link
        meeting_type: "attorney" or "paralegal"
        original_subject: Subject of the original email thread
        in_reply_to: Message-ID of the email being replied to
        references: References header for threading

    Returns:
        {success: bool, error: str or None}
    """
    if not GMAIL_APP_PASSWORD:
        return {"success": False, "error": "GMAIL_CENTER_APP_PASSWORD not configured"}

    try:
        # Get client timezone and language
        client_tz = client_info.get("timezone", "ET")
        language = client_info.get("language", "en")
        client_name = client_info.get("name", "")

        # Convert time to client timezone
        display = format_for_client(confirmed_dt_est, client_tz, language)

        # Build email body
        body = get_confirmation_body(
            client_name=client_name,
            weekday=display["weekday"],
            date=display["date"],
            time=display["time"],
            timezone=display["timezone_abbrev"],
            meet_link=meet_link,
            duration="60",
            meeting_type=meeting_type,
            language=language,
        )

        # Build CC list
        cc = _get_auto_cc(client_info)

        # Subject: threaded reply
        subject = _clean_subject(original_subject) if original_subject else f"Meeting Confirmation - {client_name}"

        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"CaseHub <{GMAIL_EMAIL}>"
        msg["To"] = client_email
        msg["Cc"] = ", ".join(cc)

        # Threading headers
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references
        elif in_reply_to:
            msg["References"] = in_reply_to

        # Plain text
        msg.attach(MIMEText(body, "plain"))

        # HTML version
        body_html = body.replace("\n", "<br>\n")
        body_html = f"<div style='font-family: Arial, sans-serif; font-size: 14px;'>{body_html}</div>"
        msg.attach(MIMEText(body_html, "html"))

        # All recipients
        all_recipients = [client_email] + cc

        # Send
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_EMAIL, all_recipients, msg.as_string())

        logger.info(
            f"Confirmation email sent to {client_email} | "
            f"Time: {display['full_display']} | CC: {', '.join(cc)}"
        )

        return {"success": True}

    except Exception as e:
        logger.error(f"Error sending confirmation email: {e}")
        return {"success": False, "error": str(e)}
