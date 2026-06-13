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
from email.header import decode_header
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dotenv import load_dotenv
import argparse

load_dotenv()

# Import local modules
from attachment_handler import AttachmentHandler, classify_document_with_llm
from notion_notifier import NotionNotifier, NOTION_CONFIG
from attachment_metadata import add_attachment_metadata

logger = logging.getLogger(__name__)

# Configuration - uses existing env vars from communications.py
GMAIL_EMAIL = os.getenv("GMAIL_CENTER_EMAIL", "info@casehub.app")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_CENTER_APP_PASSWORD", "")

# Data directory
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Processed emails tracking
PROCESSED_EMAILS_FILE = DATA_DIR / "processed_emails.json"

# Client mapping (email -> client info)
# Fields: name, paralegal, case, case_type, timezone, language, phone, cc_always, spouse_name
CLIENT_MAPPING = {
    "felixmendozasuarez@gmail.com": {
        "name": "Felix Mendoza", "paralegal": "Juliana", "case": "33",
        "case_type": "EB-1A", "timezone": "CT", "language": "pt",
        "phone": "+13345910409",
        "cc_always": ["michelledt.press@gmail.com"],
        "spouse_name": "Michelle Ehrhardt"
    },
    "np.pratya@gmail.com": {
        "name": "Nuttapon Pratyapattanapong", "paralegal": "Ana Clara", "case": "66",
        "case_type": "EB-1A", "timezone": "ET", "language": "en"
    },
    "farokhi_fe@yahoo.com": {
        "name": "Fereshteh Farokhi", "paralegal": "Juliana", "case": "7",
        "case_type": "EB-1A", "timezone": "ET", "language": "en",
        "phone": "+15148803417"
    },
    "johanna8218@gmail.com": {
        "name": "Cindy Sambony", "paralegal": "Ana Clara", "case": "59",
        "case_type": "EB-2 NIW", "timezone": "CT", "language": "en",
        "phone": "+19133269587"
    },
    "abhishek.27d@gmail.com": {
        "name": "Abhishek Sahu", "paralegal": "Ana Clara", "case": "21",
        "case_type": "EB-2 NIW", "timezone": "ET", "language": "en",
        "phone": "+1518801277"
    },
    "umamartinez8@gmail.com": {
        "name": "Iuma Martinez Germano", "paralegal": "Juliana", "case": "19",
        "case_type": "O-1", "timezone": "ET", "language": "pt",
        "phone": "+14386806629"
    },
    "hhtaythaw@gmail.com": {
        "name": "Htay Htay Thaw", "paralegal": "Juliana", "case": "10",
        "case_type": "EB-2 NIW", "timezone": "PT", "language": "en",
        "phone": "+16266378627"
    },
    "jodieevans97@outlook.com": {
        "name": "Jodie Evans", "paralegal": "Juliana", "case": "39",
        "case_type": "EB-2 NIW", "timezone": "ET", "language": "en"
    },
    "sagarnishant1@gmail.com": {
        "name": "Nishant Sagar", "paralegal": "Ana Clara", "case": "63",
        "case_type": "EB-1A", "timezone": "ET", "language": "en"
    },
    "sakethram21@gmail.com": {
        "name": "Saketh Ram Gurumurthi", "paralegal": "Ana Clara", "case": "72",
        "case_type": "EB-2 NIW", "timezone": "ET", "language": "en"
    },
    "t.c.guven@optimumdigitalusa.com": {
        "name": "Taner Can Guven", "paralegal": "Ana Clara", "case": "",
        "case_type": "EB-2 NIW", "timezone": "ET", "language": "en"
    },
    "anna.bouveret@gmail.com": {
        "name": "Anna Bouveret", "paralegal": "Ana Clara", "case": "",
        "case_type": "B-1", "timezone": "GMT", "language": "en",
        "cc_always": ["anju.ambrose@iasuk.org"]
    },
    "claire.zhong@gmail.com": {
        "name": "Claire Zhong", "paralegal": "Juliana", "case": "",
        "case_type": "", "timezone": "ET", "language": "en"
    },
    "smoulana@gmail.com": {
        "name": "Seyed Muhammad Moulana", "paralegal": "Ana Clara", "case": "30",
        "case_type": "EB-2 NIW", "timezone": "ET", "language": "en",
        "phone": "+17164866458"
    },
    "nathan.snell@k-spipecontractors.co.uk": {
        "name": "Nathan Snell", "paralegal": "Ana Clara", "case": "78",
        "case_type": "B-1/B-2", "timezone": "GMT", "language": "en"
    },
    "santoshppatel@hotmail.com": {
        "name": "Santosh Patel", "paralegal": "Ana Clara", "case": "24",
        "case_type": "EB-2 NIW", "timezone": "ET", "language": "en",
        "phone": "+14379797679"
    },
    "anar@cyberoon.com": {
        "name": "Anar Israfilov", "paralegal": "Ana Clara", "case": "67",
        "case_type": "EB-1A", "timezone": "ET", "language": "en"
    },
    "gems2909@me.com": {
        "name": "Gemma Iruegas", "paralegal": "Ana Clara", "case": "54",
        "case_type": "EB-1A", "timezone": "ET", "language": "en"
    },
    "gemma.iruegas@cbes-us.com": {
        "name": "Gemma Iruegas", "paralegal": "Ana Clara", "case": "54",
        "case_type": "EB-1A", "timezone": "ET", "language": "en"
    },
    # Add more clients as needed from active-clients.json
}

# Partner firm domains (email domain -> firm name)
PARTNER_DOMAINS = {
    "ashoorilaw": "Ashoori Law",
    "iasuk.org": "IAS",
}


def get_partner_firm(email_address: str) -> Optional[str]:
    """Get partner firm name from email domain."""
    domain = email_address.lower().split("@")[-1] if "@" in email_address else ""
    for key, firm_name in PARTNER_DOMAINS.items():
        if key in domain:
            return firm_name
    return None


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
        # Keep only last 1000 message IDs
        data["processed"] = data["processed"][-1000:]
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
            except:
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
    """Get client info from email address."""
    email_lower = email_address.lower()
    return CLIENT_MAPPING.get(email_lower)


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
                    except:
                        body = payload.decode("latin-1", errors="ignore")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            try:
                body = payload.decode("utf-8", errors="ignore")
            except:
                body = payload.decode("latin-1", errors="ignore")

    return body[:2000]  # Limit preview


class EmailProcessor:
    """Main email processor class."""

    def __init__(self):
        self.attachment_handler = AttachmentHandler()
        self.notion_notifier = NotionNotifier()
        self.mail = None

    def connect(self) -> bool:
        """Connect to Gmail IMAP."""
        if not GMAIL_APP_PASSWORD:
            logger.error("GMAIL_INFO_APP_PASSWORD not configured")
            return False

        try:
            self.mail = imaplib.IMAP4_SSL("imap.gmail.com")
            self.mail.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
            self.mail.select("INBOX")
            logger.info(f"Connected to {GMAIL_EMAIL}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Gmail: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from Gmail."""
        if self.mail:
            try:
                self.mail.logout()
            except:
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
            except:
                email_date = datetime.now()

            # Get client info or partner firm
            client_info = get_client_info(from_email)
            partner_firm = get_partner_firm(from_email)

            if not client_info and not partner_firm:
                logger.debug(f"Email from unknown sender: {from_email}")
                return {"status": "skipped", "reason": "unknown_sender", "email": from_email}

            client_name = client_info["name"] if client_info else from_email
            paralegal = client_info["paralegal"] if client_info else None

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

            # Process attachments
            processed_attachments = []
            for filename, content in attachments:
                result = self.attachment_handler.save_attachment(
                    content=content,
                    filename=filename,
                    client_name=client_name,
                    email_date=email_date
                )
                if result.get("success"):
                    # Save attachment metadata for web interface access
                    attachment_id = add_attachment_metadata(
                        email_message_id=message_id,
                        client_email=from_email,
                        client_name=client_name,
                        original_filename=filename,
                        safe_filename=result.get("safe_name", filename),
                        document_type=result.get("type", "Outro"),
                        file_path=result.get("path"),
                        file_size=result.get("size", 0),
                        received_at=email_date.isoformat()
                    )
                    processed_attachments.append({
                        "id": attachment_id,
                        "name": filename,
                        "path": result.get("path"),
                        "type": result.get("type"),
                        "size": result.get("size")
                    })

            # Create Notion notifications
            notion_result = self.notion_notifier.process_email_notification(
                client_name=client_name,
                client_email=from_email,
                paralegal=paralegal,
                subject=subject,
                body_preview=body_preview,
                email_date=email_date,
                attachments=processed_attachments,
                linked_to=partner_firm,
                original_message_id=message_id
            )

            # Mark as processed
            mark_email_processed(message_id)

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
                        for msg_id in msg_ids[-5:]:  # Last 5 emails
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
        client_emails = list(CLIENT_MAPPING.keys())
        since_date = datetime.now() - timedelta(hours=48)

        print(f"\nChecking {len(client_emails)} clients for emails since {since_date}...\n")

        results = processor.check_specific_clients(
            client_emails=client_emails,
            since_date=since_date,
            dry_run=args.dry_run
        )

        print("=" * 60)
        print("CLIENTS CHECKED:")
        print("=" * 60)
        for client in results.get("checked", []):
            print(f"  - {client['name']} ({client['email']}) - Paralegal: {client['paralegal']}")

        print("\n" + "=" * 60)
        print("EMAILS FOUND:")
        print("=" * 60)
        for found in results.get("found", []):
            print(f"\n  Client: {found.get('client')}")
            print(f"  Subject: {found.get('subject')}")
            print(f"  Date: {found.get('date')}")
            print(f"  Attachments: {found.get('attachments', 0)}")

        if not results.get("found"):
            print("  No emails found from these clients since yesterday.")

        if results.get("errors"):
            print("\n" + "=" * 60)
            print("ERRORS:")
            print("=" * 60)
            for error in results["errors"]:
                print(f"  - {error['email']}: {error['error']}")

    else:
        # General processing
        since_date = None
        if args.check_since:
            try:
                since_date = datetime.strptime(args.check_since, "%Y-%m-%d %H:%M:%S")
            except:
                try:
                    since_date = datetime.strptime(args.check_since, "%Y-%m-%d")
                except:
                    print(f"Invalid date format: {args.check_since}")
                    sys.exit(1)

        results = processor.process_all(
            since_date=since_date,
            dry_run=args.dry_run,
            limit=args.limit
        )

        print(f"\nResults:")
        print(f"  Total emails: {results.get('total', 0)}")
        print(f"  Processed: {results.get('processed', 0)}")
        print(f"  Skipped: {results.get('skipped', 0)}")
        print(f"  Errors: {results.get('errors', 0)}")

        if args.verbose:
            print("\nDetails:")
            for detail in results.get("details", []):
                print(f"  - {detail}")


if __name__ == "__main__":
    main()
