"""
CaseHub - WhatsApp Notification Service
Send notifications via WhatsApp using the existing WhatsApp bot
"""
import requests
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import text

from config import settings


class WhatsAppService:
    """Service for sending WhatsApp notifications."""

    def __init__(self, db: Session = None, org_id: int = None):
        self.db = db
        self.org_id = org_id
        # The WhatsApp bot runs on the same server
        self.bot_url = settings.WHATSAPP_BOT_URL
        self.enabled = True

    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self.org_id is not None:
            h["X-Org-Id"] = str(self.org_id)
        return h

    def format_phone(self, phone: str) -> str:
        """Format phone number for WhatsApp (E.164 format without +)."""
        if not phone:
            return None
        
        # Remove all non-digit characters
        digits = ''.join(filter(str.isdigit, phone))
        
        # Add country code if missing (assume US +1)
        if len(digits) == 10:
            digits = '1' + digits
        
        return digits

    def send_message(self, phone: str, message: str, template: str = None) -> Dict[str, Any]:
        """
        Send a WhatsApp message.
        
        Args:
            phone: Phone number (with or without country code)
            message: Message text
            template: Optional template name for tracking
        
        Returns:
            Dict with success status and details
        """
        formatted_phone = self.format_phone(phone)
        if not formatted_phone:
            return {"success": False, "error": "Invalid phone number"}

        try:
            # Try to send via the WhatsApp bot's API
            response = requests.post(
                f"{self.bot_url}/api/send-message",
                json={
                    "phone": formatted_phone,
                    "message": message,
                    "source": "casehub"
                },
                headers=self._headers(),
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                self._log_message(formatted_phone, message, template, True)
                return {"success": True, "message_id": result.get("id")}
            else:
                self._log_message(formatted_phone, message, template, False, response.text)
                return {"success": False, "error": f"Bot returned {response.status_code}"}
                
        except requests.exceptions.ConnectionError:
            # Bot not available, queue the message
            self._queue_message(formatted_phone, message, template)
            return {"success": False, "error": "WhatsApp bot not available, message queued"}
        except Exception as e:
            self._log_message(formatted_phone, message, template, False, str(e))
            return {"success": False, "error": str(e)}

    def send_case_update(self, client_phone: str, case_number: str, status: str, details: str = None) -> Dict:
        """Send a case status update notification."""
        message = f"📋 *CaseHub Case Update*\n\n"
        message += f"Case: {case_number}\n"
        message += f"Status: {status.replace('_', ' ').title()}\n"
        if details:
            message += f"\n{details}\n"
        message += f"\nFor questions, contact our office."
        
        return self.send_message(client_phone, message, "case_update")

    def send_task_reminder(self, client_phone: str, task_title: str, due_date: str) -> Dict:
        """Send a task reminder notification."""
        message = f"⏰ *Reminder from CaseHub*\n\n"
        message += f"Task: {task_title}\n"
        message += f"Due: {due_date}\n"
        message += f"\nPlease complete this task as soon as possible."
        
        return self.send_message(client_phone, message, "task_reminder")

    def send_document_request(self, client_phone: str, documents: List[str], case_number: str = None) -> Dict:
        """Send a document request notification."""
        message = f"📄 *Document Request from CaseHub*\n\n"
        if case_number:
            message += f"Case: {case_number}\n\n"
        message += f"We need the following documents:\n"
        for doc in documents:
            message += f"• {doc}\n"
        message += f"\nPlease upload via our portal or reply to this message with the documents."
        
        return self.send_message(client_phone, message, "document_request")

    def send_appointment_reminder(self, client_phone: str, appointment_type: str, date: str, time: str, location: str = None) -> Dict:
        """Send an appointment reminder notification."""
        message = f"📅 *Appointment Reminder*\n\n"
        message += f"Type: {appointment_type}\n"
        message += f"Date: {date}\n"
        message += f"Time: {time}\n"
        if location:
            message += f"Location: {location}\n"
        message += f"\nPlease confirm your attendance by replying to this message."
        
        return self.send_message(client_phone, message, "appointment_reminder")

    def send_rfe_notification(self, client_phone: str, case_number: str, deadline: str) -> Dict:
        """Send RFE notification."""
        message = f"⚠️ *URGENT: Request for Evidence*\n\n"
        message += f"Case: {case_number}\n"
        message += f"Response Deadline: {deadline}\n\n"
        message += f"USCIS has requested additional evidence for your case. "
        message += f"Please contact our office immediately to discuss the required documents."
        
        return self.send_message(client_phone, message, "rfe_notification")

    def send_approval_notification(self, client_phone: str, case_number: str, visa_type: str) -> Dict:
        """Send case approval notification."""
        message = f"🎉 *Congratulations!*\n\n"
        message += f"Great news! Your {visa_type} case has been APPROVED!\n\n"
        message += f"Case: {case_number}\n\n"
        message += f"Our team will contact you shortly with next steps."
        
        return self.send_message(client_phone, message, "approval_notification")

    def _log_message(self, phone: str, message: str, template: str, success: bool, error: str = None):
        """Log message to database."""
        if not self.db:
            return
        
        try:
            self.db.execute(text("""
                INSERT INTO whatsapp_messages 
                (phone, message, template, success, error, sent_at)
                VALUES (:phone, :message, :template, :success, :error, NOW())
            """), {
                "phone": phone,
                "message": message[:1000],
                "template": template,
                "success": success,
                "error": error
            })
            self.db.commit()
        except:
            pass  # Table might not exist yet

    def _queue_message(self, phone: str, message: str, template: str):
        """Queue message for later delivery."""
        if not self.db:
            return
        
        try:
            self.db.execute(text("""
                INSERT INTO whatsapp_queue 
                (phone, message, template, status, created_at)
                VALUES (:phone, :message, :template, 'pending', NOW())
            """), {
                "phone": phone,
                "message": message[:1000],
                "template": template
            })
            self.db.commit()
        except:
            pass

    def process_queue(self) -> int:
        """Process queued messages. Returns number of messages processed."""
        if not self.db:
            return 0
        
        try:
            pending = self.db.execute(text("""
                SELECT id, phone, message, template FROM whatsapp_queue
                WHERE status = 'pending'
                ORDER BY created_at
                LIMIT 50
            """)).fetchall()
            
            processed = 0
            for msg in pending:
                result = self.send_message(msg.phone, msg.message, msg.template)
                
                status = 'sent' if result.get("success") else 'failed'
                self.db.execute(text("""
                    UPDATE whatsapp_queue SET status = :status, processed_at = NOW()
                    WHERE id = :id
                """), {"status": status, "id": msg.id})
                
                if result.get("success"):
                    processed += 1
            
            self.db.commit()
            return processed
        except:
            return 0

    def get_message_stats(self, days: int = 30) -> Dict:
        """Get message statistics."""
        if not self.db:
            return {}
        
        try:
            stats = {}
            stats["total"] = self.db.execute(text("""
                SELECT COUNT(*) FROM whatsapp_messages 
                WHERE sent_at >= NOW() - INTERVAL ':days days'
            """.replace(":days", str(days)))).scalar() or 0
            
            stats["successful"] = self.db.execute(text("""
                SELECT COUNT(*) FROM whatsapp_messages 
                WHERE sent_at >= NOW() - INTERVAL ':days days' AND success = true
            """.replace(":days", str(days)))).scalar() or 0
            
            stats["failed"] = stats["total"] - stats["successful"]
            stats["queued"] = self.db.execute(text("""
                SELECT COUNT(*) FROM whatsapp_queue WHERE status = 'pending'
            """)).scalar() or 0
            
            return stats
        except:
            return {}
