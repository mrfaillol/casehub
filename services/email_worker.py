"""
CaseHub - Email Worker Service
Background worker that processes unlinked emails after 10 minutes
- Auto-links to client using SmartLinker
- Creates Notion task for the responsible paralegal
- Sends Google Chat notification
"""
from dotenv import load_dotenv
load_dotenv()

import os
import re
import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session
import httpx

from services.paralegal_assignment import get_paralegal_service
from services.notion_tasks import NotionTasksService
from services.notifications import send_task_notification_email
from services.llm_summarizer import summarize_thread_sync

logger = logging.getLogger(__name__)

def _get_base_subject(subject: str) -> str:
    """
    Remove Re:, Fwd:, etc. from subject to get the base conversation subject.
    """
    if not subject:
        return ''
    cleaned = subject
    prefixes = [r'^re:\s*', r'^fwd:\s*', r'^fw:\s*', r'^enc:\s*']
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            new_cleaned = re.sub(prefix, '', cleaned, flags=re.IGNORECASE)
            if new_cleaned != cleaned:
                cleaned = new_cleaned
                changed = True
    return cleaned.strip()



# Configuration
AUTO_LINK_DELAY_MINUTES = 10
GOOGLE_CHAT_WEBHOOK_MEMBER_A = os.getenv("GOOGLE_CHAT_WEBHOOK_MEMBER_A", "")
GOOGLE_CHAT_WEBHOOK_MEMBER_B = os.getenv("GOOGLE_CHAT_WEBHOOK_MEMBER_B", "")


class EmailWorker:
    """Processes emails automatically after timeout"""

    def __init__(self, db: Session):
        self.db = db
        self.paralegal_service = get_paralegal_service()
        self.notion_service = NotionTasksService()
        self._clients_cache: Optional[List[Dict]] = None


    def _has_existing_task_for_thread(self, email: Dict) -> Tuple[bool, Optional[str]]:
        """
        Check if there's already a Notion task for this conversation thread.
        Returns (has_task, existing_notion_task_id)
        """
        subject = email.get('subject', '')
        sender = email.get('sender', '')
        
        base_subject = _get_base_subject(subject)
        sender_email = self._extract_email_address(sender)
        
        if not base_subject or not sender_email:
            return False, None
        
        # Check last 7 days for similar emails with tasks
        cutoff = datetime.utcnow() - timedelta(days=7)
        
        result = self.db.execute(text("""
            SELECT notion_task_id
            FROM email_messages
            WHERE notion_task_id IS NOT NULL
              AND notion_task_id != 'NO_PARALEGAL'
              AND sender ILIKE :sender_pattern
              AND created_at > :cutoff
              AND (
                  LOWER(subject) = LOWER(:exact_subject)
                  OR LOWER(subject) LIKE LOWER(:re_pattern)
              )
            LIMIT 1
        """), {
            'sender_pattern': f'%{sender_email}%',
            'cutoff': cutoff,
            'exact_subject': base_subject,
            're_pattern': f'%Re:%{base_subject}%'
        })
        row = result.fetchone()
        if row:
            return True, row[0]
        return False, None

    def _get_all_clients(self) -> List[Dict]:
        """Get all clients from database"""
        if self._clients_cache is not None:
            return self._clients_cache

        result = self.db.execute(text("""
            SELECT id, first_name, last_name, email, phone
            FROM clients
            ORDER BY last_name, first_name
        """))
        self._clients_cache = [dict(row._mapping) for row in result.fetchall()]
        return self._clients_cache

    def get_emails_to_process(self) -> List[Dict]:
        """
        Get emails that:
        - Are not linked to a client (client_id IS NULL)
        - Were created more than 10 minutes ago
        - Have not been processed (notion_task_id IS NULL)
        - Are inbound emails (direction = 'inbound')
        """
        cutoff_time = datetime.utcnow() - timedelta(minutes=AUTO_LINK_DELAY_MINUTES)
        result = self.db.execute(text("""
            SELECT id, sender, subject, body_text, received_at, created_at, message_id, email_references
            FROM email_messages
            WHERE 1=1  -- FIXED: Removed client_id IS NULL (emails get auto-linked before worker runs)
              AND notion_task_id IS NULL
              AND direction = 'inbound'
              AND created_at < :cutoff
              AND sender NOT LIKE :org_email_filter
              AND subject NOT LIKE '%Nova tarefa:%'
            ORDER BY created_at ASC
            LIMIT 20
        """), {"cutoff": cutoff_time})
        return [dict(row._mapping) for row in result.fetchall()]

    def _extract_email_address(self, sender: str) -> Optional[str]:
        """Extract email address from sender string like 'Name <email@example.com>'"""
        if not sender:
            return None
        import re
        match = re.search(r'<([^>]+)>', sender)
        if match:
            return match.group(1).lower().strip()
        # If no angle brackets, assume the whole string is the email
        if '@' in sender:
            return sender.lower().strip()
        return None

    def _try_link_to_client(self, email: Dict) -> Tuple[Optional[int], Optional[str]]:
        """
        Try to link email to a client based on sender email.
        Returns (client_id, client_name) or (None, None)
        """
        sender = email.get("sender", "")
        sender_email = self._extract_email_address(sender)

        if not sender_email:
            return None, None

        clients = self._get_all_clients()

        for client in clients:
            client_email = (client.get("email") or "").lower().strip()
            if client_email and client_email == sender_email:
                client_name = f"{client.get('first_name', '')} {client.get('last_name', '')}".strip()
                return client["id"], client_name

        # Try partial match (sender_email contains client_email or vice versa)
        for client in clients:
            client_email = (client.get("email") or "").lower().strip()
            if client_email and (client_email in sender_email or sender_email in client_email):
                client_name = f"{client.get('first_name', '')} {client.get('last_name', '')}".strip()
                return client["id"], client_name

        return None, None

    def _build_email_task(self, email: Dict, client_name: Optional[str], client_info: Optional[Dict]) -> Dict:
        """Build task data for Notion with LLM thread summary"""
        subject = email.get("subject") or "(No subject)"
        body_preview = (email.get("body_text") or "")[:500]

        # Format date
        received_at = email.get("received_at")
        date_str = None
        if received_at:
            if isinstance(received_at, datetime):
                date_str = received_at.strftime("%Y-%m-%d")
            else:
                date_str = str(received_at)[:10]

        task_title = f"[CASEHUB] [EMAIL] {client_name or 'Unknown Client'}"
        
        # LLM Thread Summary - resume a conversa inteira
        sender = email.get("sender", "")
        sender_email = self._extract_email_address(sender)
        thread_summary = ""
        try:
            if sender_email:
                thread_summary = summarize_thread_sync(self.db, sender_email, subject)
                logger.info(f"LLM summary generated for thread: {subject[:50]}...")
        except Exception as e:
            logger.warning(f"LLM summarization failed: {e}")
            thread_summary = "(Resumo não disponível)"
        
        # Montar descrição com resumo + preview
        if thread_summary and thread_summary != "(Resumo não disponível)":
            description = f"**RESUMO DA CONVERSA:**\n{thread_summary}\n\n---\n\n**Assunto:** {subject}\n\n**Último email:**\n{body_preview}"
        else:
            description = f"Subject: {subject}\n\nPreview:\n{body_preview}"

        return {
            "title": task_title,
            "description": description,
            "client_names": [client_name] if client_name else [],
            "email_ref": subject,
            "date_received": date_str,
            "status": "Not started",
            "priority": "Medium",
            "due_date": date.today().isoformat(),
        }

    async def _notify_google_chat(self, paralegal_key: str, email: Dict, client_name: Optional[str], notion_task_id: Optional[str]):
        """Send notification to Google Chat"""
        webhook_url = GOOGLE_CHAT_WEBHOOK_MEMBER_A if paralegal_key == "member_a" else GOOGLE_CHAT_WEBHOOK_MEMBER_B

        if not webhook_url:
            logger.warning(f"No Google Chat webhook configured for {paralegal_key}")
            return False

        subject = email.get("subject") or "(No subject)"
        received_at = email.get("received_at")

        message_text = (
            f"📧 *New Client Email*\n\n"
            f"👤 *Client:* {client_name or 'Unknown'}\n"
            f"📋 *Subject:* {subject}\n"
            f"📅 *Received:* {received_at}\n"
        )

        if notion_task_id:
            message_text += f"✅ *Notion task created*"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(webhook_url, json={"text": message_text})
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to send Google Chat notification: {e}")
            return False

    async def process_single_email(self, email: Dict) -> Dict:
        """Process a single email: link, create task, notify"""
        result = {
            "email_id": email["id"],
            "subject": email.get("subject"),
            "linked": False,
            "notion_task_created": False,
            "notified": False,
            "error": None,
            "paralegal": None
        }

        try:
            # 1. Try to link to client
            client_id, client_name = self._try_link_to_client(email)

            if client_id:
                # Update email with client_id
                self.db.execute(text("""
                    UPDATE email_messages
                    SET client_id = :client_id, auto_linked = TRUE
                    WHERE id = :email_id
                """), {"client_id": client_id, "email_id": email["id"]})
                self.db.commit()
                result["linked"] = True
                result["client_id"] = client_id
                result["client_name"] = client_name

            # 2. Identify paralegal
            sender = email.get("sender", "")
            paralegal_key, client_info = self.paralegal_service.get_paralegal_for_email(sender)

            # If not found by email, try by client name
            if not paralegal_key and client_name:
                paralegal_key, client_info = self.paralegal_service.get_paralegal_for_client_name(client_name)

            result["paralegal"] = paralegal_key

            # 3. Create Notion task if paralegal identified
            if paralegal_key:
                # Check if task already exists for this thread
                has_existing, existing_task_id = self._has_existing_task_for_thread(email)
                if has_existing:
                    # Mark email as processed with existing task ID
                    self.db.execute(text("""
                        UPDATE email_messages
                        SET notion_task_id = :task_id, notion_task_created_at = NOW()
                        WHERE id = :email_id
                    """), {"task_id": existing_task_id, "email_id": email["id"]})
                    self.db.commit()
                    result["notion_task_created"] = False
                    result["notion_task_id"] = existing_task_id
                    result["skipped_duplicate"] = True
                    logger.info(f"Email {email['id']} - skipped task creation (thread already has task {existing_task_id})")
                    
                    # STILL send notification for new activity in existing thread
                    try:
                        notion_url = f"https://notion.so/{existing_task_id.replace('-', '')}"
                        email_preview = (email.get("body_text") or "")[:200]
                        email_notified = send_task_notification_email(
                            paralegal_key=paralegal_key,
                            client_name=client_name,
                            email_subject=email.get("subject", "(Sem assunto)"),
                            notion_task_url=notion_url,
                            email_preview=email_preview,
                            original_message_id=email.get("message_id"),
                            original_references=email.get("email_references")
                        )
                        result["email_notified"] = email_notified
                        if email_notified:
                            logger.info(f"Email {email['id']} - notification sent for existing thread")
                    except Exception as e:
                        logger.error(f"Failed to send thread notification: {e}")
                    
                    return result

                task_data = self._build_email_task(email, client_name, client_info)
                notion_result = self.notion_service.create_task_with_notification(paralegal_key, task_data, notify=True)

                # Handle new create_task_with_notification response structure
                task_response = notion_result.get("task", notion_result)
                if task_response.get("id"):
                    result["notion_task_created"] = True
                    result["notion_task_id"] = task_response["id"]
                    result["notifications_sent"] = notion_result.get("notifications", {})

                    # Update email with notion_task_id
                    self.db.execute(text("""
                        UPDATE email_messages
                        SET notion_task_id = :task_id, notion_task_created_at = NOW()
                        WHERE id = :email_id
                    """), {"task_id": task_response["id"], "email_id": email["id"]})
                    self.db.commit()
                    
                    # 4. Send email notification to paralegal
                    notion_url = task_response.get("url", f"https://notion.so/{task_response['id'].replace('-', '')}")
                    email_preview = (email.get("body_text") or "")[:200]
                    email_notified = send_task_notification_email(
                        paralegal_key=paralegal_key,
                        client_name=client_name,
                        email_subject=email.get("subject", "(Sem assunto)"),
                        notion_task_url=notion_url,
                        email_preview=email_preview,
                        original_message_id=email.get("message_id"),
                        original_references=email.get("email_references")
                    )
                    result["email_notified"] = email_notified
                else:
                    logger.error(f"Notion task creation failed: {task_response}")

                # 5. Notify Google Chat (DISABLED)
                # notified = await self._notify_google_chat(
                #     paralegal_key, email, client_name, result.get("notion_task_id")
                # )
                # result["notified"] = notified

            else:
                # No paralegal identified - mark as processed anyway to avoid reprocessing
                self.db.execute(text("""
                    UPDATE email_messages
                    SET notion_task_id = 'NO_PARALEGAL'
                    WHERE id = :email_id
                """), {"email_id": email["id"]})
                self.db.commit()
                logger.info(f"Email {email['id']} - no paralegal identified for sender: {sender}")

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Error processing email {email['id']}: {e}")

        return result

    async def run_once(self) -> Dict:
        """Execute one iteration of the worker"""
        emails = self.get_emails_to_process()
        results = {
            "processed": 0,
            "linked": 0,
            "tasks_created": 0,
            "notified": 0,
            "errors": [],
            "details": []
        }

        logger.info(f"Email worker found {len(emails)} emails to process")

        for email in emails:
            email_result = await self.process_single_email(email)
            results["processed"] += 1
            results["details"].append(email_result)

            if email_result.get("linked"):
                results["linked"] += 1
            if email_result.get("notion_task_created"):
                results["tasks_created"] += 1
            if email_result.get("notified"):
                results["notified"] += 1
            if email_result.get("error"):
                results["errors"].append({
                    "email_id": email_result["email_id"],
                    "error": email_result["error"]
                })

        return results


async def run_email_worker(db: Session) -> Dict:
    """Convenience function to run the email worker"""
    worker = EmailWorker(db)
    return await worker.run_once()
