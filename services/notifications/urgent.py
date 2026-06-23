"""
CaseHub - Urgent Email Notifier
Sends notifications to admin and paralegals for urgent emails
"""
import os
import httpx
import logging
import html
from typing import Dict, Optional

from config import settings

logger = logging.getLogger(__name__)

# Admin notification
ADMIN_ALERT_EMAIL = settings.ADMIN_EMAIL or os.getenv("ALERT_EMAIL", "")
ADMIN_ALERT_WHATSAPP = settings.ALERT_WHATSAPP or os.getenv("ALERT_WHATSAPP_NUMBER", "")
GOOGLE_CHAT_WEBHOOK_ADMIN = os.getenv("GOOGLE_CHAT_WEBHOOK_ADMIN", "")

# Paralegal emails - loaded from TEAM_EMAILS config or defaults
def _load_paralegal_emails():
    import json
    raw = settings.TEAM_EMAILS
    if raw:
        try:
            team = json.loads(raw)
            return {k: v.get("email", "") for k, v in team.items() if v.get("email")}
        except (json.JSONDecodeError, AttributeError):
            pass
    return {}

PARALEGAL_EMAILS = _load_paralegal_emails()


async def notify_casehub_team_email(email_service, client_name: str, subject: str, body_preview: str):
    """Send email notification to Equipe CaseHub"""
    html_content = f"""
    <div style="font-family: Arial; padding: 20px; border-left: 4px solid red;">
        <h2 style="color: red;">⚠️ EMAIL URGENTE RECEBIDO</h2>
        <p><strong>Cliente:</strong> {html.escape(str(client_name or "Desconhecido"))}</p>
        <p><strong>Assunto:</strong> {html.escape(str(subject))}</p>
        <hr>
        <p><strong>Preview:</strong></p>
        <p style="background: #f5f5f5; padding: 10px;">{html.escape(str(body_preview[:500]))}</p>
        <hr>
        <p><a href="{settings.BASE_URL}{settings.PREFIX}/emails">Ver no CaseHub</a></p>
    </div>
    """
    
    text_content = f"EMAIL URGENTE\\nCliente: {client_name}\\nAssunto: {subject}\\n\\n{body_preview[:500]}"
    
    try:
        result = email_service.send_email(
            to_email=ADMIN_ALERT_EMAIL,
            subject=f"🚨 URGENTE: {subject}",
            html_content=html_content,
            text_content=text_content
        )
        if result.get("success"):
            logger.info(f"Urgent notification sent to admin at {ADMIN_ALERT_EMAIL}")
            return True
    except Exception as e:
        logger.error(f"Failed to send email to Equipe CaseHub: {e}")
    
    return False


async def notify_paralegal_email(email_service, paralegal_key: str, client_name: str, subject: str, body_preview: str):
    """Send email notification to the responsible paralegal for urgent emails"""
    paralegal_email = PARALEGAL_EMAILS.get(paralegal_key)
    if not paralegal_email:
        logger.warning(f"No email configured for paralegal: {paralegal_key}")
        return False
    
    html_content = f"""
    <div style="font-family: Arial; padding: 20px; border-left: 4px solid orange;">
        <h2 style="color: #ff6600;">📧 EMAIL URGENTE - Ação Necessária</h2>
        <p><strong>Cliente:</strong> {html.escape(str(client_name or "Desconhecido"))}</p>
        <p><strong>Assunto:</strong> {html.escape(str(subject))}</p>
        <hr>
        <p><strong>Preview:</strong></p>
        <p style="background: #f5f5f5; padding: 10px;">{html.escape(str(body_preview[:500]))}</p>
        <hr>
        <p>Uma tarefa foi criada no Notion para este email.</p>
        <p><a href="{settings.BASE_URL}{settings.PREFIX}/emails">Ver no CaseHub</a></p>
    </div>
    """
    
    text_content = f"EMAIL URGENTE\\nCliente: {client_name}\\nAssunto: {subject}\\n\\n{body_preview[:500]}\\n\\nUma tarefa foi criada no Notion."
    
    try:
        result = email_service.send_email(
            to_email=paralegal_email,
            subject=f"⚠️ URGENTE: {subject} - {client_name}",
            html_content=html_content,
            text_content=text_content
        )
        if result.get("success"):
            logger.info(f"Urgent notification sent to paralegal {paralegal_key} at {paralegal_email}")
            return True
    except Exception as e:
        logger.error(f"Failed to send email to paralegal {paralegal_email}: {e}")
    
    return False


async def notify_casehub_team_whatsapp(client_name: str, subject: str):
    """Send WhatsApp notification to Equipe CaseHub via existing bot API"""
    if not ADMIN_ALERT_WHATSAPP:
        logger.warning("ALERT_WHATSAPP_NUMBER not configured")
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{settings.WHATSAPP_BOT_URL}/api/send",
                json={
                    "phone": ADMIN_ALERT_WHATSAPP,
                    "message": f"🚨 *EMAIL URGENTE*\\n\\n👤 Cliente: {client_name or Desconhecido}\\n📧 Assunto: {subject}\\n\\n➡️ {settings.BASE_URL}{settings.PREFIX}/emails"
                }
            )
            return response.status_code == 200 and response.json().get("success", False)
    except Exception as e:
        logger.error(f"Failed to send WhatsApp to Equipe CaseHub: {e}")
        return False


async def notify_casehub_team_google_chat(client_name: str, subject: str, body_preview: str):
    """Send Google Chat notification to Equipe CaseHub"""
    if not GOOGLE_CHAT_WEBHOOK_ADMIN:
        logger.warning("GOOGLE_CHAT_WEBHOOK_ADMIN not configured")
        return False

    try:
        message = {
            "text": f"🚨 *EMAIL URGENTE RECEBIDO*\\n\\n👤 *Cliente:* {client_name or Desconhecido}\\n📧 *Assunto:* {subject}\\n\\n📝 *Preview:*\\n{body_preview[:300]}\\n\\n➡️ {settings.BASE_URL}{settings.PREFIX}/emails"
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(GOOGLE_CHAT_WEBHOOK_ADMIN, json=message)
            return response.status_code == 200
    except Exception as e:
        logger.error(f"Failed to send Google Chat to Equipe CaseHub: {e}")
        return False


async def notify_casehub_team_urgent(
    email_service,
    client_name: str,
    subject: str,
    body_preview: str,
    paralegal_key: Optional[str] = None
) -> Dict[str, bool]:
    """
    Send urgent email notification to Equipe CaseHub via ALL channels.
    Also notify the responsible paralegal if provided.

    Returns dict with success status for each channel.
    """
    import asyncio

    results = {
        "email_casehub_team": False,
        "email_paralegal": False,
        "whatsapp": False,
        "google_chat": False
    }

    # Send to all channels in parallel
    tasks = [
        notify_casehub_team_email(email_service, client_name, subject, body_preview),
        notify_casehub_team_whatsapp(client_name, subject),
        notify_casehub_team_google_chat(client_name, subject, body_preview)
    ]
    
    # Add paralegal notification if we know who is responsible
    if paralegal_key:
        tasks.append(notify_paralegal_email(email_service, paralegal_key, client_name, subject, body_preview))
    else:
        tasks.append(asyncio.coroutine(lambda: False)())  # placeholder

    email_result, whatsapp_result, gchat_result, paralegal_result = await asyncio.gather(
        *tasks,
        return_exceptions=True
    )

    results["email_casehub_team"] = email_result is True
    results["whatsapp"] = whatsapp_result is True
    results["google_chat"] = gchat_result is True
    results["email_paralegal"] = paralegal_result is True if paralegal_key else False

    logger.info(f"Urgent notification results: {results}")
    logger.info(f"URGENT NOTIFICATION: Equipe CaseHub={results['email_casehub_team']}, Paralegal={results['email_paralegal']}, WhatsApp={results['whatsapp']}")
    return results
