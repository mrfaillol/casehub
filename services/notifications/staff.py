"""
CaseHub - Paralegal Email Notifier
Sends email notifications to paralegals when new tasks are created.
Emails are sent in the same thread as the original client email (Re: subject).
"""
import os
import json
import logging
import html
from typing import Optional, Dict

from config import settings

logger = logging.getLogger(__name__)


# Paralegal email addresses - loaded from TEAM_EMAILS config
def _load_paralegal_emails():
    raw = settings.TEAM_EMAILS
    if raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, AttributeError):
            pass
    return {}

PARALEGAL_EMAILS = _load_paralegal_emails()


def send_task_notification_email(
    paralegal_key: str,
    client_name: str,
    email_subject: str,
    notion_task_url: str,
    email_preview: str = "",
    original_message_id: str = None,
    original_references: str = None
) -> bool:
    """
    Send email notification to paralegal about new task.
    Email is sent as a reply (Re:) to maintain thread with original client email.

    Args:
        paralegal_key: 'member_a' or 'member_b'
        client_name: Name of the client
        email_subject: Subject of the ORIGINAL client email
        notion_task_url: Direct URL to the Notion task
        email_preview: Preview of the email body
        original_message_id: Message-ID of original email for threading
        original_references: References header from original email for threading

    Returns:
        True if email sent successfully
    """
    logger.info(f"📧 Preparing notification for {paralegal_key}: {email_subject[:50]}")
    from services.email_service import EmailService

    paralegal = PARALEGAL_EMAILS.get(paralegal_key)
    if not paralegal:
        logger.warning(f"Unknown paralegal key: {paralegal_key}")
        return False

    to_email = paralegal["email"]
    paralegal_name = paralegal["name"]

    # Subject as reply to maintain thread (Re: original subject)
    # Remove existing Re: prefix if present to avoid Re: Re: Re:
    clean_subject = email_subject
    while clean_subject.lower().startswith("re: "):
        clean_subject = clean_subject[4:]
    subject = f"Re: {clean_subject}"
    
    _esc_paralegal = html.escape(str(paralegal_name or ""))
    _esc_client = html.escape(str(client_name)) if client_name else "Não identificado"
    _esc_subject = html.escape(str(email_subject or ""))
    _esc_preview = html.escape(str(email_preview[:200])) if email_preview else ""
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 10px 10px 0 0;">
            <h2 style="color: white; margin: 0;">📧 Nova Tarefa de Email</h2>
        </div>
        
        <div style="background: #f8f9fa; padding: 20px; border: 1px solid #e9ecef;">
            <p style="margin: 0 0 15px 0;">Olá <strong>{_esc_paralegal}</strong>,</p>
            
            <p style="margin: 0 0 20px 0;">Uma nova tarefa foi criada automaticamente a partir do email abaixo:</p>
            
            <div style="background: white; border-left: 4px solid #667eea; padding: 15px; margin: 20px 0;">
                <p style="margin: 0 0 10px 0;"><strong>👤 Cliente:</strong> {_esc_client}</p>
                <p style="margin: 0 0 10px 0;"><strong>📋 Assunto:</strong> {_esc_subject}</p>
                {f'<p style="margin: 0; color: #666;"><strong>Preview:</strong> {_esc_preview}...</p>' if email_preview else ''}
            </div>
            
            <div style="text-align: center; margin: 25px 0;">
                <a href="{notion_task_url}" 
                   style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                          color: white; padding: 12px 30px; text-decoration: none; border-radius: 25px;
                          font-weight: bold;">
                    📝 Ver Tarefa no Notion
                </a>
            </div>
        </div>
        
        <div style="background: #343a40; color: #adb5bd; padding: 15px; text-align: center; border-radius: 0 0 10px 10px; font-size: 12px;">
            <p style="margin: 0;">Enviado automaticamente pelo CaseHub</p>
            <p style="margin: 5px 0 0 0;">CaseHub</p>
        </div>
    </div>
    """
    
    text_content = f"""
Nova Tarefa de Email

Olá {_esc_paralegal},

Uma nova tarefa foi criada automaticamente a partir do email abaixo:

👤 Cliente: {_esc_client}
📋 Assunto: {email_subject}

Ver tarefa: {notion_task_url}

Respectfully,
CaseHub - CaseHub
"""
    
    try:
        email_service = EmailService()
        # CC center@ so the operations lead has visibility without polluting the public inbox.
        center_email = os.getenv("ORG_CENTER_EMAIL", "")
        cc = center_email if to_email != center_email and center_email else None
        result = email_service.send_email(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            cc_email=cc,
            in_reply_to=original_message_id,
            references=original_references
        )
        
        if result.get("success"):
            logger.info(f"✅ NOTIFICATION SENT: Task notification sent to {_esc_paralegal} ({to_email}) - Subject: {subject}")
            return True
        else:
            logger.error(f"Failed to send notification to {to_email}: {result.get('error')}")
            return False
            
    except Exception as e:
        logger.error(f"Error sending notification to {to_email}: {e}")
        return False
