#!/usr/bin/env python3
"""
Email Processor - CaseHub
Monitors Gmail inbox for client emails, processes attachments, and creates Notion notifications.
"""

import os
import sys
import json
import logging
import imaplib
import email
import hashlib
from email.header import decode_header
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dotenv import load_dotenv
import argparse

load_dotenv()

from config import settings

# Import local modules
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Database connection for client lookup
DATABASE_URL = settings.DATABASE_URL
_db_engine = None
def get_db_engine():
    global _db_engine
    if _db_engine is None:
        _db_engine = create_engine(DATABASE_URL)
    return _db_engine

def get_client_from_db(email_address: str):
    """Query the database for client info by email."""
    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT c.id, c.first_name, c.last_name, c.email, 
                       COALESCE(cs.paralegal, 'Ana Clara') as paralegal
                FROM clients c
                LEFT JOIN cases cs ON cs.client_id = c.id
                WHERE LOWER(c.email) = LOWER(:email)
                LIMIT 1
            """), {"email": email_address})
            row = result.fetchone()
            if row:
                return {
                    "name": f"{row[1]} {row[2]}",
                    "paralegal": row[4] if row[4] else "Ana Clara",
                    "case": str(row[0])
                }
    except Exception as e:
        logger.warning(f"DB lookup failed for {email_address}: {e}")
    return None

from services.attachment_handler import AttachmentHandler, classify_document_with_llm
from scripts.attachment_to_client import save_to_client_folder, find_client_folder, classify_by_filename as classify_simple
from notion_notifier import NotionNotifier, NOTION_CONFIG
from scripts.attachment_metadata import add_attachment_metadata
from models import SessionLocal
from models.document import Document
from services.notifications import create_notification_for_all_staff
from services.document_sync import sync_to_google_drive

logger = logging.getLogger(__name__)


def create_document_record(result, client_folder_result, client_name, client_info, from_email, filename, file_content):
    """Create Document record in CaseHub PostgreSQL DB after saving email attachment."""
    db = None
    try:
        db = SessionLocal()

        # PRIORITY 1: Always resolve client_id from DB by email (most reliable)
        client_id_val = None
        if from_email:
            db_client = get_client_from_db(from_email)
            if db_client:
                client_id_val = int(db_client["case"])  # get_client_from_db returns clients.id

        # PRIORITY 2: Use client_info["case"] (already enriched by get_client_info)
        if not client_id_val and client_info.get("case"):
            try:
                candidate = int(client_info["case"])
                from models.client import Client
                if db.query(Client).filter(Client.id == candidate).first():
                    client_id_val = candidate
                else:
                    logger.warning(f"Client ID {candidate} from mapping not found in DB for {filename}")
            except (ValueError, TypeError):
                pass

        if not client_id_val:
            logger.warning(f"No valid client_id resolved for {filename} (from={from_email})")

        # Look up actual case_id from cases table via client_id
        case_id = None
        if client_id_val:
            from models.case import Case
            case = db.query(Case).filter(Case.client_id == client_id_val).first()
            if case:
                case_id = case.id

        content_hash = hashlib.sha256(file_content).hexdigest()

        # Dedup by content_hash
        existing = db.query(Document).filter(Document.content_hash == content_hash).first()
        if existing:
            logger.info(f"Duplicate document skipped: {filename} (matches doc #{existing.id})")
            return existing.id

        file_path = (client_folder_result.get("path") if client_folder_result and client_folder_result.get("success")
                     else result.get("path"))

        doc = Document(
            name=filename,
            doc_type=result.get("type", "Other Document"),
            status="pending_review",
            file_path=file_path,
            file_size=result.get("size", 0),
            file_hash=content_hash,
            content_hash=content_hash,
            client_id=client_id_val,
            case_id=case_id,
            uploaded_via="email",
            workflow_state="pending_review",
            llm_classified=bool(result.get("type") != "Other Document"),
            storage_backend="local",
            client_visible=False,
        )
        db.add(doc)
        db.commit()
        doc_id = doc.id
        logger.info(f"Document record #{doc_id} created: {filename} ({result.get('type')}) [client={client_id_val}, case={case_id}]")
        return doc_id
    except Exception as e:
        logger.error(f"Failed to create Document record for {filename}: {e}")
        if db:
            db.rollback()
        return None
    finally:
        if db:
            db.close()


# Keywords para detectar expansion/testimonial (deadline de 5 dias)
EXPANSION_KEYWORDS = {
    "expansion", "carta", "carta de expansao", "prong",
    "extraordinary ability", "habilidade extraordinaria",
    "testimonial", "personal statement", "declaracao pessoal",
    "questionnaire", "ps questionnaire", "prong 1", "prong 2", "prong 3",
    "expansion questionnaire", "expansao"
}

def detect_expansion_testimonial(subject: str, body: str, attachment_types: list) -> bool:
    """Detecta se email contem documentos de expansion/testimonial para deadline de 5 dias."""
    text = f"{subject} {body}".lower()
    
    # Verifica keywords no texto
    for kw in EXPANSION_KEYWORDS:
        if kw in text:
            return True
    
    # Verifica tipos de anexo
    expansion_doc_types = {"Expansion", "Testimonial"}
    for attach_type in attachment_types:
        if attach_type in expansion_doc_types:
            return True
    
    return False



# Configuration
GMAIL_EMAIL = settings.GMAIL_CENTER_EMAIL or settings.ORG_EMAIL
GMAIL_APP_PASSWORD = settings.GMAIL_CENTER_APP_PASSWORD

# Data directory
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Processed emails tracking
PROCESSED_EMAILS_FILE = DATA_DIR / "processed_emails.json"

# Active clients JSON file (master list)
ACTIVE_CLIENTS_FILE = Path(os.environ.get("ACTIVE_CLIENTS_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "whatsapp-bot", "client-followup", "active-clients.json")))

def _get_client_mapping(db=None):
    """Load client email-to-ID mapping from database instead of hardcoded dict."""
    if db is None:
        from models import SessionLocal
        db = SessionLocal()
        should_close = True
    else:
        should_close = False
    try:
        from models import Client
        mapping = {}
        clients = db.query(Client).filter(Client.email.isnot(None)).all()
        for c in clients:
            if c.email:
                mapping[c.email.lower()] = c.id
        return mapping
    finally:
        if should_close:
            db.close()


# Lazy-loaded cache for CLIENT_MAPPING (replaces hardcoded dict)
_client_mapping_cache = None

def _get_cached_client_mapping():
    """Get client mapping with simple caching."""
    global _client_mapping_cache
    if _client_mapping_cache is None:
        try:
            _client_mapping_cache = _get_client_mapping()
        except Exception as e:
            logger.warning(f"Failed to load client mapping from DB: {e}")
            _client_mapping_cache = {}
    return _client_mapping_cache

# For backward compatibility - code that references CLIENT_MAPPING directly
CLIENT_MAPPING = {}  # Empty dict - use _get_cached_client_mapping() instead


def load_active_clients() -> Dict[str, Dict]:
    """Load active clients from JSON file for fallback lookup.
    
    Handles multiple emails per client (comma-separated).
    """
    if ACTIVE_CLIENTS_FILE.exists():
        try:
            with open(ACTIVE_CLIENTS_FILE, "r") as f:
                data = json.load(f)
                result = {}
                for c in data.get("clients", []):
                    emails_str = c.get("email", "")
                    if not emails_str:
                        continue
                    
                    client_info = {
                        "name": c.get("name", ""),
                        "paralegal": c.get("paralegal", "Ana Clara"),
                        "case": str(c.get("caseNumber", "")),
                    }
                    
                    # Handle multiple emails (comma-separated)
                    for email in emails_str.split(","):
                        email = email.strip().lower()
                        if email:
                            result[email] = client_info
                
                return result
        except Exception as e:
            logger.warning(f"Could not load active-clients.json: {e}")
    return {}



def load_processed_emails() -> Dict[str, Any]:
    """Load the list of processed email IDs."""
    if PROCESSED_EMAILS_FILE.exists():
        with open(PROCESSED_EMAILS_FILE, "r") as f:
            return json.load(f)
    return {"processed": [], "last_check": None}


def save_processed_emails(data: Dict[str, Any]) -> None:
    """Save the list of processed email IDs."""
    data["last_check"] = datetime.now().isoformat()
    with open(PROCESSED_EMAILS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def mark_email_processed(message_id: str) -> None:
    """Mark an email as processed."""
    data = load_processed_emails()
    if message_id not in data["processed"]:
        data["processed"].append(message_id)
        # Keep only last 5000 message IDs
        data["processed"] = data["processed"][-5000:]
    save_processed_emails(data)


def is_email_processed(message_id: str) -> bool:
    """Check if an email has already been processed."""
    data = load_processed_emails()
    return message_id in data.get("processed", [])


def decode_mime_header(header_value: str) -> str:
    """Decode a MIME-encoded header."""
    if not header_value:
        return ""
    decoded_parts = decode_header(header_value)
    result = []
    for content, charset in decoded_parts:
        if isinstance(content, bytes):
            try:
                result.append(content.decode(charset or "utf-8", errors="ignore"))
            except (UnicodeDecodeError, LookupError):
                result.append(content.decode("utf-8", errors="ignore"))
        else:
            result.append(content)
    return "".join(result)


def extract_email_address(from_header: str) -> str:
    """Extract email address from From header."""
    if "<" in from_header and ">" in from_header:
        return from_header.split("<")[1].split(">")[0].lower().strip()
    return from_header.lower().strip()


def get_client_info(email_address: str) -> Optional[Dict[str, Any]]:
    """Get client info from email address.

    ALWAYS resolves client_id from the database to prevent misassociation.
    CLIENT_MAPPING and active-clients.json are used for name/paralegal info only.
    """
    email_lower = email_address.lower()

    result = None

    # 1. Check database-backed CLIENT_MAPPING first
    client_mapping = _get_cached_client_mapping()
    if email_lower in client_mapping:
        result = {"case": str(client_mapping[email_lower])}

    # 2. Fall back to active-clients.json
    if not result:
        active_clients = load_active_clients()
        if email_lower in active_clients:
            result = active_clients.get(email_lower)
            if result:
                result = result.copy()

    # 3. Query database directly
    if not result:
        db_client = get_client_from_db(email_lower)
        if db_client:
            logger.info(f"Found client in database: {db_client['name']}")
            return db_client

    # CRITICAL: Always enrich/override client_id from DB to prevent misassociation.
    # The "case" field in CLIENT_MAPPING/active-clients.json may be stale or wrong.
    if result:
        db_client = get_client_from_db(email_lower)
        if db_client:
            result["case"] = db_client["case"]  # DB returns clients.id as "case"
        else:
            # DB lookup failed - log warning but still use static mapping as fallback
            logger.warning(
                f"DB lookup failed for {email_lower}, using static mapping "
                f"case={result.get('case')} — verify this is a valid client_id"
            )

    return result


def extract_attachments(msg: email.message.Message) -> List[Tuple[str, bytes]]:
    """Extract all attachments from an email message."""
    attachments = []

    for part in msg.walk():
        content_disposition = str(part.get("Content-Disposition", ""))

        if "attachment" in content_disposition or part.get_filename():
            filename = part.get_filename()
            if filename:
                filename = decode_mime_header(filename)
                payload = part.get_payload(decode=True)
                if payload:
                    attachments.append((filename, payload))

    return attachments


def get_email_body(msg: email.message.Message) -> str:
    """Extract the text body from an email."""
    body = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))

            if content_type == "text/plain" and "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    try:
                        body = payload.decode("utf-8", errors="ignore")
                    except (UnicodeDecodeError, LookupError):
                        body = payload.decode("latin-1", errors="ignore")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            try:
                body = payload.decode("utf-8", errors="ignore")
            except (UnicodeDecodeError, LookupError):
                body = payload.decode("latin-1", errors="ignore")

    return body[:2000]  # Limit preview


class EmailProcessor:
    """Main email processor class."""

    def __init__(self):
        self.attachment_handler = AttachmentHandler()
        self.notion_notifier = NotionNotifier()
        self.mail = None

    def connect(self, mailbox: str = '"[Gmail]/All Mail"') -> bool:
        """Connect to Gmail IMAP.

        Uses [Gmail]/All Mail by default to catch auto-archived emails.
        Gmail filters can skip INBOX, so searching All Mail ensures no emails are missed.
        """
        if not GMAIL_APP_PASSWORD:
            logger.error("GMAIL_INFO_APP_PASSWORD not configured")
            return False

        try:
            self.mail = imaplib.IMAP4_SSL("imap.gmail.com")
            self.mail.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
            self.mail.select(mailbox)
            logger.info(f"Connected to {GMAIL_EMAIL} (mailbox: {mailbox})")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Gmail: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from Gmail."""
        if self.mail:
            try:
                self.mail.logout()
            except Exception:
                pass

    def search_emails(
        self,
        since_date: datetime = None,
        from_addresses: List[str] = None,
        unseen_only: bool = True
    ) -> List[bytes]:
        """Search for emails matching criteria."""
        criteria = []

        if unseen_only:
            criteria.append("UNSEEN")

        if since_date:
            date_str = since_date.strftime("%d-%b-%Y")
            criteria.append(f'SINCE "{date_str}"')

        # Build search string
        if criteria:
            search_str = " ".join(criteria)
        else:
            search_str = "ALL"

        try:
            _, messages = self.mail.search(None, search_str)
            msg_ids = messages[0].split()
            logger.info(f"Found {len(msg_ids)} emails matching criteria")
            return msg_ids
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []

    def process_email(self, msg_id: bytes, dry_run: bool = False) -> Dict[str, Any]:
        """Process a single email."""
        try:
            _, msg_data = self.mail.fetch(msg_id, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])

            # Get message ID for tracking
            message_id = msg.get("Message-ID", str(msg_id))

            # Check if already processed
            if is_email_processed(message_id):
                return {"status": "skipped", "reason": "already_processed"}

            # Extract email details
            from_header = msg.get("From", "")
            from_email = extract_email_address(from_header)
            subject = decode_mime_header(msg.get("Subject", ""))
            date_str = msg.get("Date", "")

            # Parse date
            try:
                email_date = email.utils.parsedate_to_datetime(date_str)
            except (ValueError, TypeError):
                email_date = datetime.now()

            # Get client info
            client_info = get_client_info(from_email)

            if not client_info:
                logger.debug(f"Email from unknown sender: {from_email}")
                return {"status": "skipped", "reason": "unknown_sender", "email": from_email}

            client_name = client_info["name"]
            paralegal = client_info["paralegal"]

            # Extract body
            body_preview = get_email_body(msg)

            # Extract attachments
            attachments = extract_attachments(msg)

            logger.info(f"Processing email from {client_name}: {subject} ({len(attachments)} attachments)")

            if dry_run:
                return {
                    "status": "dry_run",
                    "client": client_name,
                    "email": from_email,
                    "subject": subject,
                    "date": email_date.isoformat(),
                    "attachments": len(attachments),
                    "paralegal": paralegal
                }

            # Process attachments - save to BOTH /data/attachments AND client folder
            processed_attachments = []
            for filename, file_content in attachments:
                # 1. Save to /data/attachments (legacy backup)
                result = self.attachment_handler.save_attachment(
                    content=file_content,
                    filename=filename,
                    client_name=client_name,
                    email_date=email_date
                )
                
                # 2. NEW: Also save to client folder
                doc_type = result.get('type', classify_simple(filename))
                client_email = from_email
                client_folder_result = None
                try:
                    client_folder_result = save_to_client_folder(
                        file_content, filename, client_name, doc_type, client_email
                    )
                    if client_folder_result.get('success'):
                        logger.info(f"Saved to client folder: {client_folder_result.get('path')}")
                        result['client_folder_path'] = client_folder_result.get('path')
                except Exception as e:
                    logger.warning(f"Could not save to client folder: {e}")
                if result.get("success"):
                    # Save attachment metadata for web interface access
                    attachment_id = add_attachment_metadata(
                        email_message_id=message_id,
                        client_email=from_email,
                        client_name=client_name,
                        original_filename=filename,
                        safe_filename=result.get("safe_name", filename),
                        document_type=result.get("type", "Other Document"),
                        file_path=result.get("path"),
                        file_size=result.get("size", 0),
                        received_at=email_date.isoformat()
                    )
                    # 3. NEW: Create Document record in CaseHub PostgreSQL DB
                    doc_id = create_document_record(
                        result=result,
                        client_folder_result=client_folder_result,
                        client_name=client_name,
                        client_info=client_info,
                        from_email=from_email,
                        filename=filename,
                        file_content=file_content
                    )
                    # Auto-sync to Google Drive (no approval needed)
                    if doc_id:
                        try:
                            sync_db = SessionLocal()
                            drive_result = sync_to_google_drive(sync_db, doc_id)
                            if drive_result.get("success"):
                                logger.info(f"Auto-synced to Drive: {filename} -> {drive_result.get('web_link', 'N/A')}")
                            else:
                                logger.warning(f"Drive sync failed for {filename}: {drive_result.get('error')}")
                            sync_db.close()
                        except Exception as e:
                            logger.error(f"Drive auto-sync error for {filename}: {e}")

                    processed_attachments.append({
                        "id": attachment_id,
                        "doc_id": doc_id,
                        "name": filename,
                        "path": result.get("path"),
                        "type": result.get("type"),
                        "size": result.get("size")
                    })

            # Detect expansion/testimonial content for 5-day deadline
            attachment_types = [a.get("type", "") for a in processed_attachments]
            is_expansion = detect_expansion_testimonial(subject, body_preview, attachment_types)
            
            # Set deadline based on content type (5 days for expansion, 1 day for others)
            deadline_days = 5 if is_expansion else 1
            task_prefix = "[EXPANSION] " if is_expansion else ""
            
            if is_expansion:
                logger.info(f"Expansion/Testimonial detected for {client_name} - using 5-day deadline")
            
            # Create Notion notifications
            try:
                notion_result = self.notion_notifier.process_email_notification(
                    client_name=client_name,
                    client_email=from_email,
                    paralegal=paralegal,
                    subject=f"{task_prefix}{subject}" if is_expansion else subject,
                    body_preview=body_preview,
                    email_date=email_date,
                    attachments=processed_attachments,
                    deadline_days=deadline_days
                )
            except TypeError:
                # Fallback for VPS version without deadline_days param
                notion_result = self.notion_notifier.process_email_notification(
                    client_name=client_name,
                    client_email=from_email,
                    paralegal=paralegal,
                    subject=f"{task_prefix}{subject}" if is_expansion else subject,
                    body_preview=body_preview,
                    email_date=email_date,
                    attachments=processed_attachments
                )

            # Mark as processed
            mark_email_processed(message_id)

            # Create in-app notifications for CaseHub staff
            try:
                notif_db = SessionLocal()
                client_id_for_notif = int(client_info.get("case", 0)) if client_info.get("case") else None
                att_count = len(processed_attachments)
                create_notification_for_all_staff(
                    db=notif_db,
                    title=f"Email from {client_name}: {subject[:60]}",
                    notification_type="client_email",
                    message=f"{att_count} attachment(s). Paralegal: {paralegal}",
                    severity="info",
                    client_id=client_id_for_notif,
                    action_url=f"{settings.PREFIX}/clients/{client_id_for_notif}" if client_id_for_notif else None,
                    send_email_to=[settings.ORG_EMAIL, settings.ORG_CENTER_EMAIL],
                )
                for att in processed_attachments:
                    doc_id = att.get("doc_id")
                    if doc_id:
                        create_notification_for_all_staff(
                            db=notif_db,
                            title=f"Document received: {att.get('filename', 'unknown')[:60]}",
                            notification_type="document_received",
                            message=f"From {client_name}. Type: {att.get('type', 'Unknown')}",
                            severity="info",
                            client_id=client_id_for_notif,
                            document_id=doc_id,
                            action_url=f"{settings.PREFIX}/documents/{doc_id}",
                        )
                notif_db.commit()
                notif_db.close()
                logger.info(f"In-app notifications created for email from {client_name}")
            except Exception as e:
                logger.warning(f"Failed to create in-app notifications: {e}")
                try:
                    notif_db.close()
                except Exception:
                    pass

            return {
                "status": "processed",
                "client": client_name,
                "email": from_email,
                "subject": subject,
                "date": email_date.isoformat(),
                "attachments_saved": len(processed_attachments),
                "notion_task": notion_result.get("task", {}).get("success"),
                "notion_comm": notion_result.get("communication", {}).get("success")
            }

        except Exception as e:
            logger.error(f"Error processing email {msg_id}: {e}")
            return {"status": "error", "error": str(e)}

    def process_all(
        self,
        since_date: datetime = None,
        dry_run: bool = False,
        limit: int = 50
    ) -> Dict[str, Any]:
        """Process all matching emails."""
        if not self.connect():
            return {"success": False, "error": "Failed to connect"}

        try:
            if since_date is None:
                since_date = datetime.now() - timedelta(hours=24)

            msg_ids = self.search_emails(since_date=since_date, unseen_only=False)

            results = {
                "total": len(msg_ids),
                "processed": 0,
                "skipped": 0,
                "errors": 0,
                "details": []
            }

            for msg_id in msg_ids[:limit]:
                result = self.process_email(msg_id, dry_run=dry_run)
                results["details"].append(result)

                if result.get("status") == "processed":
                    results["processed"] += 1
                elif result.get("status") == "skipped":
                    results["skipped"] += 1
                elif result.get("status") == "error":
                    results["errors"] += 1

            logger.info(f"Processing complete: {results['processed']} processed, {results['skipped']} skipped, {results['errors']} errors")
            return results

        finally:
            self.disconnect()

    def check_specific_clients(
        self,
        client_emails: List[str],
        since_date: datetime = None,
        dry_run: bool = True
    ) -> Dict[str, Any]:
        """Check emails from specific client addresses."""
        if not self.connect():
            return {"success": False, "error": "Failed to connect"}

        try:
            if since_date is None:
                since_date = datetime.now() - timedelta(hours=48)

            results = {
                "checked": [],
                "found": [],
                "errors": []
            }

            for client_email in client_emails:
                client_info = get_client_info(client_email)
                client_name = client_info["name"] if client_info else client_email

                results["checked"].append({
                    "email": client_email,
                    "name": client_name,
                    "paralegal": client_info.get("paralegal") if client_info else "Unknown"
                })

                try:
                    # Search for emails from this client
                    date_str = since_date.strftime("%d-%b-%Y")
                    _, messages = self.mail.search(None, f'FROM "{client_email}" SINCE "{date_str}"')
                    msg_ids = messages[0].split()

                    if msg_ids:
                        for msg_id in msg_ids[-10:]:  # Last 10 emails
                            result = self.process_email(msg_id, dry_run=dry_run)
                            if result.get("status") in ["processed", "dry_run"]:
                                results["found"].append({
                                    "client": client_name,
                                    "email": client_email,
                                    **result
                                })

                except Exception as e:
                    results["errors"].append({
                        "email": client_email,
                        "error": str(e)
                    })

            return results

        finally:
            self.disconnect()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="CaseHub Email Processor")
    parser.add_argument("--check-since", help="Check emails since date (YYYY-MM-DD HH:MM:SS)")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually process, just show what would be done")
    parser.add_argument("--check-clients", action="store_true", help="Check specific client list from yesterday")
    parser.add_argument("--limit", type=int, default=50, help="Maximum emails to process")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    processor = EmailProcessor()

    if args.check_clients:
        # Check the specific clients mentioned
        client_emails = list(_get_cached_client_mapping().keys())
        since_date = datetime.now() - timedelta(hours=48)

        logger.info("Checking %s clients for emails since %s...", len(client_emails), since_date)

        results = processor.check_specific_clients(
            client_emails=client_emails,
            since_date=since_date,
            dry_run=args.dry_run
        )

        logger.info("=" * 60)
        logger.info("CLIENTS CHECKED:")
        logger.info("=" * 60)
        for client in results.get("checked", []):
            logger.info("  - %s (%s) - Paralegal: %s", client['name'], client['email'], client['paralegal'])

        logger.info("=" * 60)
        logger.info("EMAILS FOUND:")
        logger.info("=" * 60)
        for found in results.get("found", []):
            logger.info("  Client: %s", found.get('client'))
            logger.info("  Subject: %s", found.get('subject'))
            logger.info("  Date: %s", found.get('date'))
            logger.info("  Attachments: %s", found.get('attachments', 0))

        if not results.get("found"):
            logger.info("  No emails found from these clients since yesterday.")

        if results.get("errors"):
            logger.info("=" * 60)
            logger.error("ERRORS:")
            logger.info("=" * 60)
            for error in results["errors"]:
                logger.error("  - %s: %s", error['email'], error['error'])

    else:
        # General processing
        since_date = None
        if args.check_since:
            try:
                since_date = datetime.strptime(args.check_since, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    since_date = datetime.strptime(args.check_since, "%Y-%m-%d")
                except ValueError:
                    logger.error("Invalid date format: %s", args.check_since)
                    sys.exit(1)

        results = processor.process_all(
            since_date=since_date,
            dry_run=args.dry_run,
            limit=args.limit
        )

        logger.info("Results:")
        logger.info("  Total emails: %s", results.get('total', 0))
        logger.info("  Processed: %s", results.get('processed', 0))
        logger.info("  Skipped: %s", results.get('skipped', 0))
        logger.info("  Errors: %s", results.get('errors', 0))

        if args.verbose:
            logger.debug("Details:")
            for detail in results.get("details", []):
                logger.debug("  - %s", detail)


if __name__ == "__main__":
    main()
