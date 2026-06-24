"""
CaseHub - Unified Messaging Hub Service
Consolidates WhatsApp, Email, SMS, and Voice communications.
"""

import os
import re
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text, func, or_, and_
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError
from config import settings
from models import Client, Case
from models.tenant import tenant_query

logger = logging.getLogger(__name__)


class MessagingHubService:
    """
    Unified messaging service that aggregates communications from:
    - WhatsApp (via bot)
    - Email (IMAP/SMTP)
    - SMS (CallHippo)
    - Voice Calls (CallHippo)
    """

    def __init__(self, db: Session, org_id: int = None):
        self.db = db
        self.org_id = org_id

    # =========================================================================
    # SMART CLIENT/CASE LINKING
    # =========================================================================

    def find_client_by_identifier(self, identifier: str, channel: str) -> Optional[int]:
        """
        Intelligently find a client based on phone or email.
        Returns client_id if found.
        """
        if not identifier:
            return None

        identifier = identifier.strip().lower()

        # For phone-based channels (WhatsApp, SMS, Call)
        if channel in ('whatsapp', 'sms', 'call'):
            # Clean phone number - keep only digits
            phone_digits = re.sub(r'\D', '', identifier)
            if len(phone_digits) >= 10:
                # Match last 10 digits
                last_10 = phone_digits[-10:]
                client = tenant_query(self.db, Client, self.org_id).filter(
                    or_(
                        func.right(func.regexp_replace(Client.phone, r'\D', '', 'g'), 10) == last_10,
                        func.right(func.regexp_replace(Client.whatsapp, r'\D', '', 'g'), 10) == last_10
                    )
                ).first()
                if client:
                    return client.id

        # For email-based channels
        if channel == 'email':
            # Direct email match
            client = tenant_query(self.db, Client, self.org_id).filter(
                func.lower(Client.email) == identifier
            ).first()
            if client:
                return client.id

        return None

    def find_case_by_email_content(self, subject: str, body: str, client_id: int = None) -> Optional[int]:
        """
        Intelligently find a case based on email content.
        Looks for:
        - Case numbers in subject (e.g., "Re: Case #123", "CH-2024-001")
        - Receipt numbers (e.g., WAC2190123456)
        - Client name mentions
        - Visa type mentions
        """
        if not subject and not body:
            return None

        combined_text = f"{subject or ''} {body or ''}"

        # Pattern 1: Case ID pattern (PREFIX-YYYY-NNN or Case #NNN)
        case_patterns = [
            r'[A-Z]{2,5}-\d{4}-\d+',
            r'Case\s*#?\s*(\d+)',
            r'caso\s*#?\s*(\d+)',
        ]

        for pattern in case_patterns:
            match = re.search(pattern, combined_text, re.IGNORECASE)
            if match:
                case_ref = match.group(0)
                # Try to find case by case_number field
                case = tenant_query(self.db, Case, self.org_id).filter(
                    Case.case_number.ilike(f'%{case_ref}%')
                ).first()
                if case:
                    return case.id

        # Pattern 2: USCIS Receipt Number
        receipt_pattern = r'[A-Z]{3}\d{10}'
        receipt_match = re.search(receipt_pattern, combined_text)
        if receipt_match:
            receipt = receipt_match.group(0)
            case = tenant_query(self.db, Case, self.org_id).filter(
                Case.receipt_number == receipt
            ).first()
            if case:
                return case.id

        # Pattern 3: If we have a client, get their most recent active case
        if client_id:
            case = tenant_query(self.db, Case, self.org_id).filter(
                Case.client_id == client_id,
                Case.status.notin_(['approved', 'denied', 'closed', 'withdrawn'])
            ).order_by(Case.created_at.desc()).first()
            if case:
                return case.id

        return None

    def auto_link_message(self, channel: str, from_addr: str, to_addr: str,
                          subject: str = None, body: str = None) -> Dict[str, Optional[int]]:
        """
        Automatically determine client_id and case_id for a message.
        """
        result = {'client_id': None, 'case_id': None}

        # Determine which identifier to use (from for inbound, to for outbound check)
        identifier = from_addr

        # Find client
        client_id = self.find_client_by_identifier(identifier, channel)
        if not client_id:
            # Try the other direction
            client_id = self.find_client_by_identifier(to_addr, channel)

        result['client_id'] = client_id

        # Find case (especially for emails with content)
        if channel == 'email' and (subject or body):
            result['case_id'] = self.find_case_by_email_content(subject, body, client_id)
        elif client_id:
            # For non-email, just get most recent active case
            case = tenant_query(self.db, Case, self.org_id).filter(
                Case.client_id == client_id,
                Case.status.notin_(['approved', 'denied', 'closed', 'withdrawn'])
            ).order_by(Case.created_at.desc()).first()
            if case:
                result['case_id'] = case.id

        return result

    # =========================================================================
    # THREAD MANAGEMENT
    # =========================================================================

    def get_threads(self, channel: str = None, client_id: int = None,
                    search: str = None, unread_only: bool = False,
                    folder: str = None, limit: int = 50, offset: int = 0) -> List[Dict]:
        """
        Get conversation threads grouped by contact with preview of last message.
        """
        # Query with subquery to get last message preview
        # Join with email_messages for folder filtering when channel is email
        query = """
            WITH thread_summary AS (
                SELECT
                    um.channel,
                    COALESCE(
                        CASE WHEN um.direction = 'inbound' THEN um.from_identifier ELSE um.to_identifier END,
                        um.from_identifier
                    ) as contact,
                    um.client_id,
                    COUNT(*) as message_count,
                    SUM(CASE WHEN um.is_read = FALSE AND um.direction = 'inbound' THEN 1 ELSE 0 END) as unread_count,
                    MAX(um.message_at) as last_message_at
                FROM unified_messages um
        """

        # Add join for folder filtering
        if folder and channel == 'email':
            query += " LEFT JOIN email_messages em ON um.source_table = 'email_messages' AND um.source_id = em.id"

        query += " WHERE 1=1"

        params = {}

        if self.org_id:
            query += " AND um.org_id = :org_id"
            params['org_id'] = self.org_id

        if channel:
            query += " AND um.channel = :channel"
            params['channel'] = channel

        # Add folder filter for email channel
        if folder and channel == 'email':
            query += " AND em.folder = :folder"
            params['folder'] = folder

        if client_id:
            query += " AND um.client_id = :client_id"
            params['client_id'] = client_id

        if unread_only:
            query += " AND um.is_read = FALSE AND um.direction = 'inbound'"

        query += """
                GROUP BY um.channel, contact, um.client_id
            )
            SELECT
                ts.channel,
                ts.contact,
                ts.client_id,
                c.first_name || ' ' || c.last_name as client_name,
                cs.visa_type,
                ts.message_count,
                ts.unread_count,
                ts.last_message_at,
                COALESCE(lm.subject, LEFT(lm.preview, 100), '(No content)') as last_preview
            FROM thread_summary ts
            LEFT JOIN clients c ON c.id = ts.client_id
            LEFT JOIN cases cs ON cs.client_id = c.id AND cs.status NOT IN ('approved', 'denied', 'closed')
            LEFT JOIN LATERAL (
                SELECT subject, preview FROM unified_messages
                WHERE channel = ts.channel
                AND (from_identifier = ts.contact OR to_identifier = ts.contact)
                ORDER BY message_at DESC
                LIMIT 1
            ) lm ON TRUE
            ORDER BY ts.last_message_at DESC
            LIMIT :limit OFFSET :offset
        """
        params['limit'] = limit
        params['offset'] = offset

        # ``unified_messages`` / ``email_messages`` / ``thread_summary`` (CTE)
        # are not declared as SQLAlchemy models. They get created via
        # ALTER TABLE migrations that have not all run on a fresh deploy
        # (alpha remote runtime, in-memory test DBs). When the table is absent
        # Postgres raises ``UndefinedTable`` -> ``ProgrammingError`` and
        # SQLite raises ``OperationalError``. Both poison the session.
        # Same defect class as portal_access (PR #572): the route layer
        # used to 500; now we degrade to an empty thread list so the
        # messaging page can still render with "no conversations yet".
        try:
            result = self.db.execute(text(query), params)
            threads = []
            for row in result:
                threads.append({
                    'channel': row.channel,
                    'contact': row.contact,
                    'client_id': row.client_id,
                    'client_name': row.client_name,
                    'visa_type': row.visa_type,
                    'message_count': row.message_count,
                    'unread_count': row.unread_count,
                    'last_message_at': row.last_message_at,
                    'last_preview': row.last_preview
                })
            return threads
        except (OperationalError, ProgrammingError) as exc:
            logger.warning(
                "[MESSAGING get_threads] unified_messages table unavailable "
                "(likely missing migration on this deploy): %s",
                exc,
            )
            self.db.rollback()
            return []

    def get_thread_messages(self, channel: str, contact: str,
                            limit: int = 100, offset: int = 0) -> List[Dict]:
        """
        Get messages for a specific thread.
        """
        if not self.org_id:
            return []
        query = """
            SELECT
                um.*,
                c.first_name || ' ' || c.last_name as client_name
            FROM unified_messages um
            LEFT JOIN clients c ON c.id = um.client_id
            WHERE um.channel = :channel
            AND (um.from_identifier = :contact OR um.to_identifier = :contact)
            AND um.org_id = :org_id
            ORDER BY um.message_at ASC
            LIMIT :limit OFFSET :offset
        """

        try:
            result = self.db.execute(text(query), {
                'channel': channel,
                'contact': contact,
                'org_id': self.org_id,
                'limit': limit,
                'offset': offset
            }).fetchall()
        except SQLAlchemyError as exc:
            logger.warning("Messaging thread messages unavailable: %s", exc)
            self.db.rollback()
            return []

        messages = []
        for row in result:
            messages.append({
                'id': row.id,
                'channel': row.channel,
                'direction': row.direction,
                'from_identifier': row.from_identifier,
                'to_identifier': row.to_identifier,
                'subject': row.subject,
                'preview': row.preview,
                'status': row.status,
                'is_read': row.is_read,
                'is_starred': row.is_starred,
                'call_duration': row.call_duration,
                'message_at': row.message_at,
                'client_id': row.client_id,
                'client_name': row.client_name,
                'case_id': row.case_id
            })

        return messages

    # =========================================================================
    # CLIENT TIMELINE
    # =========================================================================

    def get_client_timeline(self, client_id: int, limit: int = 100) -> List[Dict]:
        """
        Get complete communication timeline for a client.
        """
        query = """
            SELECT
                id, channel, direction, from_identifier, to_identifier,
                subject, preview, status, call_duration, message_at, case_id
            FROM unified_messages
            WHERE client_id = :client_id
            ORDER BY message_at DESC
            LIMIT :limit
        """

        result = self.db.execute(text(query), {
            'client_id': client_id,
            'limit': limit
        })

        timeline = []
        for row in result:
            timeline.append({
                'id': row.id,
                'channel': row.channel,
                'direction': row.direction,
                'from': row.from_identifier,
                'to': row.to_identifier,
                'subject': row.subject,
                'preview': row.preview,
                'status': row.status,
                'call_duration': row.call_duration,
                'timestamp': row.message_at,
                'case_id': row.case_id
            })

        return timeline

    # =========================================================================
    # SYNC FROM EXISTING TABLES
    # =========================================================================

    def sync_whatsapp_messages(self):
        """Sync messages from whatsapp_messages table (outbound only - sent messages)."""
        # whatsapp_messages only has outbound sent messages
        query = """
            INSERT INTO unified_messages
            (channel, source_table, source_id, direction, from_identifier, to_identifier,
             preview, status, message_at, client_id)
            SELECT
                'whatsapp',
                'whatsapp_messages',
                id,
                'outbound',
                :org_email,
                phone,
                LEFT(message, 200),
                CASE WHEN success THEN 'sent' ELSE 'failed' END,
                sent_at,
                NULL
            FROM whatsapp_messages
            WHERE NOT EXISTS (
                SELECT 1 FROM unified_messages
                WHERE source_table = 'whatsapp_messages' AND source_id = whatsapp_messages.id
            )
        """
        self.db.execute(text(query), {'org_email': settings.ORG_EMAIL})
        self.db.commit()

        # Auto-link to clients
        self._auto_link_unlinked_messages('whatsapp')

    def sync_email_messages(self):
        """Sync messages from email_messages and sent_emails tables."""
        # Incoming emails
        query_incoming = """
            INSERT INTO unified_messages
            (channel, source_table, source_id, direction, from_identifier, to_identifier,
             subject, preview, status, message_at, client_id)
            SELECT
                'email',
                'email_messages',
                id,
                'inbound',
                sender,
                recipients,
                subject,
                LEFT(body_text, 200),
                'received',
                COALESCE(received_at, created_at),
                client_id
            FROM email_messages
            WHERE NOT EXISTS (
                SELECT 1 FROM unified_messages
                WHERE source_table = 'email_messages' AND source_id = email_messages.id
            )
        """
        self.db.execute(text(query_incoming))

        # Outgoing emails (sent_emails table may not exist)
        try:
            query_outgoing = """
                INSERT INTO unified_messages
                (channel, source_table, source_id, direction, from_identifier, to_identifier,
                 subject, preview, status, message_at, client_id)
                SELECT
                    'email',
                    'sent_emails',
                    id,
                    'outbound',
                    :org_email,
                    to_email,
                    subject,
                    LEFT(body, 200),
                    'sent',
                    COALESCE(sent_at, NOW()),
                    client_id
                FROM sent_emails
                WHERE NOT EXISTS (
                    SELECT 1 FROM unified_messages
                    WHERE source_table = 'sent_emails' AND source_id = sent_emails.id
                )
            """
            self.db.execute(text(query_outgoing), {'org_email': settings.ORG_EMAIL})
        except Exception:
            pass  # sent_emails table might not exist

        self.db.commit()

        # Auto-link to clients
        self._auto_link_unlinked_messages('email')

    def sync_callhippo_logs(self):
        """Sync messages from callhippo_logs table (if it exists)."""
        # Check if table exists
        check_table = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'callhippo_logs'
            )
        """
        result = self.db.execute(text(check_table))
        if not result.scalar():
            return  # Table doesn't exist yet

        query = """
            INSERT INTO unified_messages
            (channel, source_table, source_id, direction, from_identifier, to_identifier,
             preview, status, call_duration, message_at, client_id)
            SELECT
                CASE WHEN log_type = 'sms' THEN 'sms' ELSE 'call' END,
                'callhippo_logs',
                id,
                direction,
                from_number,
                to_number,
                LEFT(content, 200),
                status,
                duration,
                COALESCE(timestamp, created_at),
                NULL
            FROM callhippo_logs
            WHERE NOT EXISTS (
                SELECT 1 FROM unified_messages
                WHERE source_table = 'callhippo_logs' AND source_id = callhippo_logs.id
            )
        """
        self.db.execute(text(query))
        self.db.commit()

        # Auto-link to clients
        self._auto_link_unlinked_messages('sms')
        self._auto_link_unlinked_messages('call')

    def sync_all(self):
        """Sync all channels."""
        try:
            self.sync_whatsapp_messages()
        except Exception as e:
            logger.error(f"Error syncing WhatsApp: {e}")

        try:
            self.sync_email_messages()
        except Exception as e:
            logger.error(f"Error syncing Email: {e}")

        try:
            self.sync_callhippo_logs()
        except Exception as e:
            logger.error(f"Error syncing CallHippo: {e}")

    def _auto_link_unlinked_messages(self, channel: str):
        """Auto-link messages that don't have a client_id yet."""
        query = """
            SELECT id, from_identifier, to_identifier, subject, preview
            FROM unified_messages
            WHERE channel = :channel AND client_id IS NULL
        """
        result = self.db.execute(text(query), {'channel': channel})

        for row in result:
            links = self.auto_link_message(
                channel=channel,
                from_addr=row.from_identifier,
                to_addr=row.to_identifier,
                subject=row.subject,
                body=row.preview
            )

            if links['client_id'] or links['case_id']:
                update_query = """
                    UPDATE unified_messages
                    SET client_id = :client_id, case_id = :case_id
                    WHERE id = :id
                """
                self.db.execute(text(update_query), {
                    'id': row.id,
                    'client_id': links['client_id'],
                    'case_id': links['case_id']
                })

        self.db.commit()

    # =========================================================================
    # MESSAGE ACTIONS
    # =========================================================================

    def mark_as_read(self, message_id: int) -> bool:
        """Mark a message as read."""
        query = "UPDATE unified_messages SET is_read = TRUE WHERE id = :id AND org_id = :org_id"
        self.db.execute(text(query), {'id': message_id, 'org_id': self.org_id})
        self.db.commit()
        return True

    def mark_thread_as_read(self, channel: str, contact: str) -> int:
        """Mark all messages in a thread as read."""
        query = """
            UPDATE unified_messages
            SET is_read = TRUE
            WHERE channel = :channel
            AND (from_identifier = :contact OR to_identifier = :contact)
            AND is_read = FALSE
            AND org_id = :org_id
        """
        try:
            result = self.db.execute(text(query), {
                'channel': channel,
                'contact': contact,
                'org_id': self.org_id
            })
            self.db.commit()
        except SQLAlchemyError as exc:
            logger.warning("Messaging mark-thread-read unavailable: %s", exc)
            self.db.rollback()
            return 0
        return result.rowcount

    def toggle_star(self, message_id: int) -> bool:
        """Toggle starred status."""
        query = """
            UPDATE unified_messages
            SET is_starred = NOT is_starred
            WHERE id = :id AND org_id = :org_id
            RETURNING is_starred
        """
        result = self.db.execute(text(query), {'id': message_id, 'org_id': self.org_id})
        row = result.fetchone()
        self.db.commit()
        return row.is_starred if row else False

    def link_to_client(self, message_id: int, client_id: int) -> bool:
        """Manually link a message to a client."""
        query = """
            UPDATE unified_messages
            SET client_id = :client_id
            WHERE id = :id AND org_id = :org_id
        """
        self.db.execute(text(query), {
            'id': message_id,
            'client_id': client_id,
            'org_id': self.org_id
        })
        self.db.commit()
        return True

    def link_to_case(self, message_id: int, case_id: int) -> bool:
        """Manually link a message to a case."""
        query = """
            UPDATE unified_messages
            SET case_id = :case_id
            WHERE id = :id AND org_id = :org_id
        """
        self.db.execute(text(query), {
            'id': message_id,
            'case_id': case_id,
            'org_id': self.org_id
        })
        self.db.commit()
        return True

    # =========================================================================
    # STATISTICS
    # =========================================================================

    def get_unread_counts(self) -> Dict[str, int]:
        """Get unread message counts by channel.

        Returns zero-counts when ``unified_messages`` is unavailable on
        this deploy — same defensive degradation as get_threads. The
        ``total`` key is always present, so the caller (the messaging
        hub page header) can render a "0 unread" badge instead of 500."""
        zero_counts = {'whatsapp': 0, 'email': 0, 'sms': 0, 'call': 0, 'total': 0}
        try:
            query = """
                SELECT channel, COUNT(*) as count
                FROM unified_messages
                WHERE is_read = FALSE AND direction = 'inbound'
                GROUP BY channel
            """
            result = self.db.execute(text(query))
        except (OperationalError, ProgrammingError) as exc:
            logger.warning(
                "[MESSAGING get_unread_counts] unified_messages unavailable: %s",
                exc,
            )
            self.db.rollback()
            return dict(zero_counts)

        counts = dict(zero_counts)
        for row in result:
            # row.channel is uncontrolled DB data; assigning an unknown value
            # (NULL, a future channel) would pollute the result dict with keys
            # callers don't expect. Keep the returned shape to the whitelist;
            # unknown channels still contribute to the total.
            if row.channel in counts:
                counts[row.channel] = row.count
            counts['total'] += row.count

        return counts

    async def get_channel_status(self) -> Dict[str, Any]:
        """Get status of each communication channel."""
        # Check WhatsApp bot status. Awaited so the up-to-2s bot HTTP call
        # never blocks the event loop — this runs inside async route handlers.
        whatsapp_status = 'unknown'
        try:
            import httpx
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f'{settings.WHATSAPP_BOT_URL}/api/status')
                if response.status_code == 200:
                    data = response.json()
                    whatsapp_status = 'connected' if data.get('connected') else 'disconnected'
        except (httpx.HTTPError, Exception) as e:
            logger.error("Failed to call WhatsApp bot status: %s", e)
            whatsapp_status = 'offline'

        # Check email accounts. ``email_accounts`` is a raw-migration
        # table; on a fresh deploy without the migration applied, the
        # SELECT raises. Degrade to "0 accounts" so the status panel
        # still renders.
        email_count = 0
        try:
            email_count = self.db.execute(
                text("SELECT COUNT(*) FROM email_accounts WHERE enabled = TRUE")
            ).scalar() or 0
        except (OperationalError, ProgrammingError) as exc:
            logger.warning(
                "[MESSAGING get_channel_status] email_accounts unavailable: %s",
                exc,
            )
            self.db.rollback()

        return {
            'whatsapp': whatsapp_status,
            'email': f'{email_count} accounts',
            'sms': 'active',  # CallHippo is API-based
            'call': 'active'
        }
