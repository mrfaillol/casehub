"""
CaseHub - Smart Email Auto-Linker Service
Uses AI (Perplexity) to automatically link emails to client profiles
"""
from dotenv import load_dotenv
load_dotenv()

import os
import re
import httpx
from typing import Optional, List, Dict, Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
GOOGLE_CHAT_WEBHOOK_URL = os.getenv("GOOGLE_CHAT_WEBHOOK_URL", "")


class SmartEmailLinker:
    """Auto-links emails to clients using multiple matching strategies"""

    def __init__(self, db: Session):
        self.db = db
        self._clients_cache = None

    def get_all_clients(self) -> List[Dict]:
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

    def get_unlinked_emails(self) -> List[Dict]:
        """Get all emails that are not linked to a client"""
        result = self.db.execute(text("""
            SELECT id, sender, subject, body_text, received_at
            FROM email_messages
            WHERE client_id IS NULL
            ORDER BY received_at DESC
        """))
        return [dict(row._mapping) for row in result.fetchall()]

    def extract_email_address(self, sender: str) -> Optional[str]:
        """Extract email address from sender string like 'Name <email@example.com>'"""
        match = re.search(r'<([^>]+@[^>]+)>', sender)
        if match:
            return match.group(1).lower().strip()
        # Try direct email
        match = re.search(r'([^\s<>]+@[^\s<>]+)', sender)
        if match:
            return match.group(1).lower().strip()
        return None

    def extract_phone_numbers(self, text: str) -> List[str]:
        """Extract phone numbers from text"""
        if not text:
            return []
        # Various phone patterns
        patterns = [
            r'\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',  # US format
            r'\+?55[-.\s]?\d{2}[-.\s]?\d{4,5}[-.\s]?\d{4}',  # BR format
        ]
        phones = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            phones.extend(matches)
        # Normalize
        return [re.sub(r'[^\d+]', '', p) for p in phones]

    def normalize_phone(self, phone: str) -> str:
        """Normalize phone number for comparison"""
        if not phone:
            return ""
        return re.sub(r'[^\d]', '', phone)[-10:]  # Last 10 digits

    def match_by_email(self, sender: str) -> Optional[Dict]:
        """Try to match by email address (exact match)"""
        email = self.extract_email_address(sender)
        if not email:
            return None

        for client in self.get_all_clients():
            if client.get('email') and client['email'].lower().strip() == email:
                return client
        return None

    def match_by_phone_in_body(self, body_text: str) -> Optional[Dict]:
        """Try to match by phone number found in email body"""
        phones = self.extract_phone_numbers(body_text or "")
        if not phones:
            return None

        for phone in phones:
            normalized = self.normalize_phone(phone)
            if len(normalized) < 10:
                continue
            for client in self.get_all_clients():
                client_phone = self.normalize_phone(client.get('phone', ''))
                if client_phone and normalized.endswith(client_phone[-10:]):
                    return client
        return None

    def match_by_name_in_sender(self, sender: str) -> Optional[Dict]:
        """Try to match by name in sender"""
        # Extract name part (before <email>)
        name_match = re.match(r'^([^<]+)', sender)
        if not name_match:
            return None

        sender_name = name_match.group(1).strip().lower()
        if not sender_name or len(sender_name) < 3:
            return None

        # Check each client
        for client in self.get_all_clients():
            full_name = f"{client.get('first_name', '')} {client.get('last_name', '')}".lower().strip()
            first_name = (client.get('first_name') or '').lower()
            last_name = (client.get('last_name') or '').lower()

            # Exact match
            if sender_name == full_name:
                return client
            # First + Last anywhere in sender
            if first_name and last_name and first_name in sender_name and last_name in sender_name:
                return client

        return None

    async def match_by_ai(self, email: Dict) -> Optional[Dict]:
        """Use Perplexity AI to find the best matching client"""
        if not PERPLEXITY_API_KEY:
            logger.warning("PERPLEXITY_API_KEY not configured, skipping AI match")
            return None

        clients = self.get_all_clients()
        if not clients:
            return None

        # Format clients for AI
        clients_text = "\n".join([
            f"ID:{c['id']} - {c.get('first_name', '')} {c.get('last_name', '')} ({c.get('email', 'no email')})"
            for c in clients[:100]  # Limit to 100 clients for token efficiency
        ])

        prompt = f"""Analyze this email and find the matching client from the list.

EMAIL:
From: {email.get('sender', '')}
Subject: {email.get('subject', '')}
Body (first 300 chars): {(email.get('body_text') or '')[:300]}

CLIENTS LIST:
{clients_text}

INSTRUCTIONS:
- Find the client who most likely sent or is the subject of this email
- Consider name variations, email addresses, and context
- If the sender's name or email matches a client, return that client's ID
- If no clear match exists, return NONE

RESPOND WITH ONLY THE CLIENT ID NUMBER OR "NONE". Nothing else."""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    PERPLEXITY_API_URL,
                    headers={
                        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "sonar",
                        "messages": [
                            {"role": "system", "content": "You are a precise matching assistant. Respond only with a client ID number or NONE."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.1,
                        "max_tokens": 50
                    }
                )
                data = response.json()
                answer = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

                # Parse response
                if answer.upper() == "NONE":
                    return None

                # Extract ID
                id_match = re.search(r'\d+', answer)
                if id_match:
                    client_id = int(id_match.group())
                    # Find client
                    for c in clients:
                        if c['id'] == client_id:
                            return c
                return None

        except Exception as e:
            logger.error(f"AI match error: {e}")
            return None

    def link_email_to_client(self, email_id: int, client_id: int) -> bool:
        """Link an email to a client in the database"""
        try:
            self.db.execute(
                text("UPDATE email_messages SET client_id = :client_id WHERE id = :email_id"),
                {"client_id": client_id, "email_id": email_id}
            )
            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error linking email {email_id} to client {client_id}: {e}")
            self.db.rollback()
            return False

    def create_notification(self, email_id: int, client_id: int, client_name: str, match_type: str, sender: str):
        """Create an alert notification for the auto-link"""
        try:
            self.db.execute(text("""
                INSERT INTO alert_notifications
                (alert_type, title, message, entity_type, entity_id, priority, created_at)
                VALUES ('EMAIL_AUTO_LINKED', :title, :message, 'email', :email_id, 'low', NOW())
            """), {
                "title": "Email vinculado automaticamente",
                "message": f"Email de {sender[:50]} foi vinculado ao cliente {client_name} (via {match_type})",
                "email_id": email_id
            })
            self.db.commit()
        except Exception as e:
            logger.error(f"Error creating notification: {e}")
            self.db.rollback()

    async def auto_link_single_email(self, email: Dict) -> Optional[Tuple[int, str, str]]:
        """
        Try to auto-link a single email.
        Returns (client_id, client_name, match_type) or None
        """
        email_id = email['id']
        sender = email.get('sender', '')

        # Strategy 1: Email match
        client = self.match_by_email(sender)
        if client:
            match_type = "email_match"
            if self.link_email_to_client(email_id, client['id']):
                client_name = f"{client.get('first_name', '')} {client.get('last_name', '')}"
                self.create_notification(email_id, client['id'], client_name, match_type, sender)
                return (client['id'], client_name, match_type)

        # Strategy 2: Name match
        client = self.match_by_name_in_sender(sender)
        if client:
            match_type = "name_match"
            if self.link_email_to_client(email_id, client['id']):
                client_name = f"{client.get('first_name', '')} {client.get('last_name', '')}"
                self.create_notification(email_id, client['id'], client_name, match_type, sender)
                return (client['id'], client_name, match_type)

        # Strategy 3: Phone in body
        client = self.match_by_phone_in_body(email.get('body_text', ''))
        if client:
            match_type = "phone_match"
            if self.link_email_to_client(email_id, client['id']):
                client_name = f"{client.get('first_name', '')} {client.get('last_name', '')}"
                self.create_notification(email_id, client['id'], client_name, match_type, sender)
                return (client['id'], client_name, match_type)

        # Strategy 4: AI match (async)
        client = await self.match_by_ai(email)
        if client:
            match_type = "ai_match"
            if self.link_email_to_client(email_id, client['id']):
                client_name = f"{client.get('first_name', '')} {client.get('last_name', '')}"
                self.create_notification(email_id, client['id'], client_name, match_type, sender)
                return (client['id'], client_name, match_type)

        return None

    async def auto_link_all_unlinked(self) -> Dict:
        """
        Auto-link all unlinked emails.
        Returns summary of results.
        """
        unlinked = self.get_unlinked_emails()
        results = {
            "total_unlinked": len(unlinked),
            "linked": [],
            "not_linked": 0,
            "errors": []
        }

        for email in unlinked:
            try:
                result = await self.auto_link_single_email(email)
                if result:
                    client_id, client_name, match_type = result
                    results["linked"].append({
                        "email_id": email['id'],
                        "sender": email.get('sender', '')[:50],
                        "client_id": client_id,
                        "client_name": client_name,
                        "match_type": match_type
                    })
                else:
                    results["not_linked"] += 1
            except Exception as e:
                results["errors"].append({"email_id": email['id'], "error": str(e)})

        # Send Google Chat notification
        if results["linked"]:
            await self.notify_google_chat(results["linked"])

        return results

    async def notify_google_chat(self, linked_emails: List[Dict]):
        """Send notification to Google Chat"""
        if not GOOGLE_CHAT_WEBHOOK_URL:
            logger.info("GOOGLE_CHAT_WEBHOOK_URL not configured, skipping notification")
            return

        try:
            message_lines = [
                "🔗 *Auto-Link de Emails Concluído*\n",
                f"✅ *{len(linked_emails)} emails* foram vinculados automaticamente:\n"
            ]

            for e in linked_emails[:15]:  # Limit to 15
                match_icon = {
                    "email_match": "📧",
                    "name_match": "👤",
                    "phone_match": "📱",
                    "ai_match": "🤖"
                }.get(e['match_type'], "🔗")
                message_lines.append(f"{match_icon} {e['sender']} → *{e['client_name']}*")

            if len(linked_emails) > 15:
                message_lines.append(f"\n... e mais {len(linked_emails) - 15} emails")

            message = {"text": "\n".join(message_lines)}

            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(GOOGLE_CHAT_WEBHOOK_URL, json=message)
                logger.info(f"Google Chat notification sent for {len(linked_emails)} emails")

        except Exception as e:
            logger.error(f"Error sending Google Chat notification: {e}")


# Singleton instance helper
def get_smart_linker(db: Session) -> SmartEmailLinker:
    """Get a SmartEmailLinker instance"""
    return SmartEmailLinker(db)
