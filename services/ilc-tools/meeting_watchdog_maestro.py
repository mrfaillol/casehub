"""
Meeting Watchdog - Maestro Notifications
Sends notifications to admin via WhatsApp (Maestro on VPS) or email fallback.
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

MAESTRO_VPS_URL = os.getenv("MAESTRO_VPS_URL", "http://localhost:3001")
ADMIN_PHONE = os.getenv("MAESTRO_ADMIN_PHONE", "5532991513405")
GMAIL_EMAIL = os.getenv("GMAIL_CENTER_EMAIL", "info@casehub.app")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_CENTER_APP_PASSWORD", "")

# Admin email for fallback notifications
ADMIN_EMAIL = os.getenv("WATCHDOG_ADMIN_EMAIL", "info@casehub.app")


def _send_whatsapp(message: str) -> bool:
    """Send WhatsApp message via Maestro VPS."""
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(
                f"{MAESTRO_VPS_URL}/api/send-message",
                json={
                    "phone": ADMIN_PHONE,
                    "message": message,
                },
            )
            if response.status_code == 200:
                logger.info("WhatsApp notification sent via Maestro")
                return True
            else:
                logger.warning(f"Maestro response {response.status_code}: {response.text[:200]}")
                return False
    except Exception as e:
        logger.warning(f"Maestro WhatsApp failed: {e}")
        return False


def _send_email_fallback(subject: str, body: str) -> bool:
    """Send email notification as fallback when WhatsApp is unavailable."""
    if not GMAIL_APP_PASSWORD:
        return False

    try:
        msg = MIMEText(body, "plain")
        msg["Subject"] = subject
        msg["From"] = f"Meeting Watchdog <{GMAIL_EMAIL}>"
        msg["To"] = ADMIN_EMAIL

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_EMAIL, [ADMIN_EMAIL], msg.as_string())

        logger.info(f"Fallback email notification sent to {ADMIN_EMAIL}")
        return True
    except Exception as e:
        logger.error(f"Email fallback also failed: {e}")
        return False


def notify_meeting_confirmed(
    client_name: str,
    meeting_time_display: str,
    meeting_type: str,
    meet_link: str,
    paralegal: str,
    case_number: str = "",
) -> bool:
    """
    Notify admin that a meeting was auto-confirmed and scheduled.
    Tries WhatsApp first, falls back to email.
    """
    message = (
        f"[WATCHDOG] Reuniao Agendada\n\n"
        f"Cliente: {client_name}\n"
        f"Horario: {meeting_time_display}\n"
        f"Tipo: {'Attorney' if meeting_type == 'attorney' else 'Paralegal'}\n"
        f"Meet: {meet_link}\n"
    )
    if case_number:
        message += f"Case #{case_number}\n"
    message += f"Paralegal: {paralegal}\n"
    message += "\nEvento criado no Calendar. Email de confirmacao enviado ao cliente."

    if _send_whatsapp(message):
        return True

    return _send_email_fallback(
        subject=f"[WATCHDOG] Reuniao agendada: {client_name}",
        body=message,
    )


def notify_review_needed(
    client_name: str,
    possible_time: str,
    confidence: float,
    email_preview: str,
    meeting_type: str = "unknown",
) -> bool:
    """
    Notify admin that a possible meeting confirmation was detected
    but confidence is not high enough for auto-action.
    """
    message = (
        f"[WATCHDOG] Possivel Confirmacao (Revisar)\n\n"
        f"Cliente: {client_name}\n"
        f"Horario possivel: {possible_time}\n"
        f"Confianca: {confidence:.0%}\n"
        f"Tipo: {meeting_type}\n\n"
        f"Email do cliente:\n{email_preview[:300]}\n\n"
        f"Acao necessaria: verificar e agendar manualmente se confirmado."
    )

    if _send_whatsapp(message):
        return True

    return _send_email_fallback(
        subject=f"[WATCHDOG] Revisar: possivel confirmacao de {client_name}",
        body=message,
    )


def notify_conflict(
    client_name: str,
    requested_time: str,
    conflict_event: str,
) -> bool:
    """Notify admin about a calendar conflict."""
    message = (
        f"[WATCHDOG] Conflito no Calendar\n\n"
        f"Cliente: {client_name}\n"
        f"Horario confirmado: {requested_time}\n"
        f"Conflito com: {conflict_event}\n\n"
        f"Acao necessaria: resolver conflito e reagendar."
    )

    if _send_whatsapp(message):
        return True

    return _send_email_fallback(
        subject=f"[WATCHDOG] Conflito: {client_name} - {requested_time}",
        body=message,
    )


def notify_error(error_message: str) -> bool:
    """Notify admin about a system error."""
    message = f"[WATCHDOG] Erro no sistema\n\n{error_message}"

    if _send_whatsapp(message):
        return True

    return _send_email_fallback(
        subject="[WATCHDOG] Erro no sistema",
        body=message,
    )
