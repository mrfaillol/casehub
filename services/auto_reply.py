"""
CaseHub - Smart Auto-Reply Service
Processes incoming emails and classifies them.
Auto-reply sends response in the SAME thread (using In-Reply-To headers).
Reply is NOT saved to email_messages table (won't appear as new msg in CaseHub).
"""
import os
import re
import asyncio
import logging
from typing import Tuple, Optional, Dict
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def is_known_client(db: Session, sender_email: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Check if sender is a known client.
    Returns (is_known, client_name, paralegal_key)
    """
    match = re.search(r'<([^>]+)>', sender_email)
    email_addr = (match.group(1) if match else sender_email).lower().strip()

    org_domain = os.getenv("ORG_DOMAIN", "")
    if org_domain and f'@{org_domain}' in email_addr:
        return (False, None, None)

    paralegal_key = None
    try:
        from services.paralegal_assignment import get_paralegal_service
        paralegal_service = get_paralegal_service()
        paralegal_key, client_info = paralegal_service.get_paralegal_for_email(email_addr)
        if client_info:
            return (True, client_info.get("name", ""), paralegal_key)
    except Exception as e:
        logger.warning(f"Could not check paralegal service: {e}")

    try:
        result = db.execute(text(
            "SELECT id, first_name, last_name FROM clients WHERE LOWER(email) = :email LIMIT 1"
        ), {"email": email_addr}).fetchone()

        if result:
            name = f"{result.first_name or ''} {result.last_name or ''}".strip()
            return (True, name, None)
    except Exception as e:
        logger.error(f"Error checking clients table: {e}")

    return (False, None, None)


async def process_auto_reply_async(db: Session, email_id: int, sender: str, subject: str, body: str):
    """
    Process incoming email with smart content analysis.
    Auto-reply is sent in the same thread using In-Reply-To headers.
    """
    from services.email_analyzer import analyze_email, EmailClassification
    from services.notifications.urgent import notify_casehub_team_urgent
    from services.email_service import EmailService

    match = re.search(r'<([^>]+)>', sender)
    recipient = match.group(1) if match else sender.strip()

    is_known, client_name, paralegal_key = is_known_client(db, sender)
    if not is_known:
        logger.info(f"AUTO-REPLY: Email {email_id} - sender not a known client: {sender}")
        return {"action": "ignored", "reason": "unknown_sender"}
    
    logger.info(f"AUTO-REPLY: Email {email_id} - client: {client_name}, paralegal: {paralegal_key}")

    result = db.execute(text(
        "SELECT auto_reply_sent FROM email_messages WHERE id = :id"
    ), {"id": email_id}).fetchone()
    if result and result.auto_reply_sent:
        return {"action": "skipped", "reason": "already_processed"}

    classification, reason = await analyze_email(subject, body or "")
    logger.info(f"AUTO-REPLY: Email {email_id} classified as {classification.value} ({reason})")

    if classification == EmailClassification.SKIP:
        db.execute(text(
            "UPDATE email_messages SET auto_reply_sent = TRUE, auto_reply_skipped = TRUE WHERE id = :id"
        ), {"id": email_id})
        db.commit()
        return {"action": "skipped", "classification": classification.value}

    if classification == EmailClassification.REPLY:
        # Gmail vacation auto-reply already handles acknowledgment.
        # Just mark as processed without sending duplicate email.
        logger.info(f"AUTO-REPLY: Email {email_id} - REPLY classified, skipping send (Gmail vacation auto-reply active)")
        db.execute(text(
            "UPDATE email_messages SET auto_reply_sent = TRUE, auto_reply_skipped = TRUE WHERE id = :id"
        ), {"id": email_id})
        db.commit()
        return {"action": "processed", "classification": "REPLY", "email_sent": False, "reason": "gmail_vacation_active"}

    if classification == EmailClassification.URGENT:
        result_data = {"action": "urgent_processed", "classification": "URGENT", "email_sent": False}
        
        try:
            from services.notion_tasks import NotionTasksService
            from datetime import date
            notion_svc = NotionTasksService()
            task_key = paralegal_key or "ana"
            urgent_task = notion_svc.create_task_with_notification(
                task_key,
                {
                    "title": f"🚨 [URGENTE] [EMAIL] {client_name or 'Cliente'}",
                    "description": f"URGENTE - Acao imediata necessaria\n\nAssunto: {subject}\n\nPreview: {body[:500] if body else ''}",
                    "status": "Not started",
                    "priority": "Urgente",
                    "due_date": date.today().isoformat()
                },
                notify=True
            )
            result_data["notion_task_created"] = urgent_task.get("task", {}).get("id") is not None
            logger.info(f"AUTO-REPLY: Created URGENT Notion task for {task_key}")
        except Exception as notion_err:
            logger.error(f"Failed to create urgent Notion task: {notion_err}")
            result_data["notion_task_created"] = False
        
        try:
            email_service = EmailService()
            notification_results = await notify_casehub_team_urgent(
                email_service,
                client_name,
                subject,
                body[:500] if body else "",
                paralegal_key=paralegal_key
            )
            result_data["casehub_team_notified"] = notification_results
            logger.info(f"AUTO-REPLY: URGENT - Equipe CaseHub and paralegal ({paralegal_key}) notified")
        except Exception as notify_err:
            logger.error(f"Failed to send urgent notifications: {notify_err}")
        
        db.execute(text(
            "UPDATE email_messages SET auto_reply_sent = TRUE WHERE id = :id"
        ), {"id": email_id})
        db.commit()
        
        return result_data

    return {"action": "processed", "classification": classification.value}


def process_auto_reply_sync(db: Session, email_id: int, sender: str, subject: str, body: str):
    logger.info(f"AUTO-REPLY: Processing email {email_id} from {sender[:50]}...")
    try:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(process_auto_reply_async(db, email_id, sender, subject, body))
                return {"action": "scheduled", "reason": "async_scheduled"}
        except RuntimeError:
            pass

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(process_auto_reply_async(db, email_id, sender, subject, body))
            return result
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Error processing auto-reply for email {email_id}: {e}")
        return {"action": "error", "error": str(e)}
