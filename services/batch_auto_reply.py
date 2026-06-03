"""
CaseHub - Batch Auto-Reply Processor

*** DISABLED AS OF 02/02/2026 ***
This module is no longer active. Auto-reply emails to clients have been disabled.

"""

# ============================================
# THIS ENTIRE MODULE IS DISABLED
# ============================================
raise ImportError("batch_auto_reply is DISABLED - auto-reply feature has been turned off")

# Original code below (disabled):

import os
import json
import re
import logging
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Load active clients with proper email handling
def load_active_clients() -> Dict[str, Dict]:
    """Load active clients and index by email (handles comma-separated emails)"""
    clients_by_email = {}
    try:
        with open('/var/www/casehub/whatsapp-bot/client-followup/active-clients.json', 'r') as f:
            data = json.load(f)
            for client in data.get('clients', []):
                email_field = client.get('email', '')
                if email_field:
                    # Handle comma-separated emails
                    emails = [e.strip().lower() for e in email_field.split(',')]
                    for email in emails:
                        if email:
                            clients_by_email[email] = client
    except Exception as e:
        logger.error(f"Error loading active clients: {e}")
    return clients_by_email


def is_client_email(sender: str, clients_by_email: Dict) -> Tuple[bool, Optional[str]]:
    """Check if sender is a known client"""
    # Extract email from "Name <email>" format
    match = re.search(r'<([^>]+)>', sender)
    email = (match.group(1) if match else sender).lower().strip()
    
    # Skip our own domain
    org_domain = os.getenv("ORG_DOMAIN", "")
    if org_domain and f'@{org_domain}' in email:
        return (False, None)
    
    # Check in active clients
    if email in clients_by_email:
        return (True, clients_by_email[email].get('name', ''))
    
    return (False, None)


def classify_email_with_keywords(subject: str, body: str) -> str:
    """Classify email: SKIP, REPLY, or URGENT"""
    text_content = f"{subject} {body}".lower()
    
    # URGENT keywords
    urgent_keywords = [
        'urgente', 'urgent', 'asap', 'emergency', 'deportation',
        'detention', 'arrested', 'court date', 'hearing', 'deadline'
    ]
    for kw in urgent_keywords:
        if kw in text_content:
            return 'URGENT'
    
    # SKIP keywords (only if email is short)
    skip_keywords = [
        'thank', 'thanks', 'obrigado', 'obrigada', 'gracias',
        'ok', 'okay', 'got it', 'received', 'perfect'
    ]
    if len(body.strip()) < 150:
        for kw in skip_keywords:
            if kw in text_content:
                return 'SKIP'
    
    return 'REPLY'


def send_auto_reply(db: Session, email_id: int, to_email: str, subject: str) -> bool:
    """Send the auto-reply email"""
    try:
        from services.email_service import EmailService
        email_service = EmailService()
        
        reply_subject = f"Re: {subject}" if not subject.startswith('Re:') else subject
        
        html_content = """
        <div style="font-family: Arial, sans-serif;">
            <p>Hello!</p>
            <p><span style="color: #B8860B;">Your message</span> has been sent to our legal team for review. 
            We will get back to <span style="color: #B8860B;">you</span> with an update as soon as possible.</p>
            <p>Please don't hesitate to let us know in case <span style="color: #B8860B;">you</span> have any questions.</p>
            <br>
            <p>Respectfully,</p>
            <p>Our Team.</p>
        </div>
        """
        
        text_content = """Hello!

Your message has been sent to our legal team for review.
We will get back to you with an update as soon as possible.

Please don't hesitate to let us know in case you have any questions.

Respectfully,
Our Team."""
        
        result = email_service.send_email(to_email, reply_subject, html_content, text_content)
        
        if result.get('success'):
            db.execute(text(
                "UPDATE email_messages SET auto_reply_sent = TRUE WHERE id = :id"
            ), {"id": email_id})
            db.commit()
            return True
        return False
    except Exception as e:
        logger.error(f"Error sending auto-reply: {e}")
        return False


def process_batch_auto_replies(db: Session, start_date: str, end_date: str, dry_run: bool = True) -> Dict:
    """
    Process all client emails between dates and send auto-replies.
    
    Args:
        db: Database session
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        dry_run: If True, don't send emails, just report what would be done
    
    Returns:
        Summary of processing
    """
    results = {
        'total_emails': 0,
        'client_emails': 0,
        'to_reply': [],
        'to_skip': [],
        'urgent': [],
        'already_replied': 0,
        'not_client': 0,
        'sent': 0,
        'errors': []
    }
    
    # Load active clients
    clients_by_email = load_active_clients()
    logger.info("Loaded %s client emails", len(clients_by_email))
    
    # Get emails in date range (inbound only)
    query = """
        SELECT id, sender, subject, body_text, received_at, auto_reply_sent
        FROM email_messages 
        WHERE received_at >= :start_date 
        AND received_at < CAST(:end_date AS DATE) + interval '1 day'
        AND sender NOT LIKE :domain_filter
        ORDER BY received_at DESC
    """
    
    emails = db.execute(text(query), {
        'start_date': start_date,
        'end_date': end_date
    }).fetchall()
    
    results['total_emails'] = len(emails)
    logger.info("Found %s emails in date range", len(emails))
    
    for email in emails:
        email_id = email.id
        sender = email.sender or ''
        subject = email.subject or ''
        body = email.body_text or ''
        
        # Check if already replied
        if email.auto_reply_sent:
            results['already_replied'] += 1
            continue
        
        # Check if known client
        is_client, client_name = is_client_email(sender, clients_by_email)
        if not is_client:
            results['not_client'] += 1
            continue
        
        results['client_emails'] += 1
        
        # Classify email
        classification = classify_email_with_keywords(subject, body)
        
        # Extract email address
        match = re.search(r'<([^>]+)>', sender)
        to_email = match.group(1) if match else sender
        
        email_info = {
            'id': email_id,
            'client': client_name,
            'subject': subject[:50],
            'to': to_email,
            'received': str(email.received_at)
        }
        
        if classification == 'SKIP':
            results['to_skip'].append(email_info)
            # Mark as skipped
            if not dry_run:
                db.execute(text(
                    "UPDATE email_messages SET auto_reply_skipped = TRUE WHERE id = :id"
                ), {"id": email_id})
                db.commit()
        elif classification == 'URGENT':
            results['urgent'].append(email_info)
            results['to_reply'].append(email_info)
            if not dry_run:
                if send_auto_reply(db, email_id, to_email, subject):
                    results['sent'] += 1
                else:
                    results['errors'].append(f"Failed to send to {to_email}")
        else:  # REPLY
            results['to_reply'].append(email_info)
            if not dry_run:
                if send_auto_reply(db, email_id, to_email, subject):
                    results['sent'] += 1
                else:
                    results['errors'].append(f"Failed to send to {to_email}")
    
    return results


if __name__ == '__main__':
    from models import SessionLocal
    db = SessionLocal()
    
    # Dry run first
    logger.info("=== DRY RUN (não envia emails) ===")
    results = process_batch_auto_replies(db, '2026-01-31', '2026-02-02', dry_run=True)

    logger.info("Total emails: %s", results['total_emails'])
    logger.info("Client emails: %s", results['client_emails'])
    logger.info("Not clients: %s", results['not_client'])
    logger.info("Already replied: %s", results['already_replied'])

    logger.info("To REPLY (%s):", len(results['to_reply']))
    for e in results['to_reply']:
        logger.info("  - %s: %s", e['client'], e['subject'])

    logger.info("To SKIP (%s):", len(results['to_skip']))
    for e in results['to_skip']:
        logger.info("  - %s: %s", e['client'], e['subject'])

    logger.info("URGENT (%s):", len(results['urgent']))
    for e in results['urgent']:
        logger.info("  - %s: %s", e['client'], e['subject'])

    db.close()
