#!/usr/bin/env python3
"""
CaseHub - Retroactive Email Document Backfill
Scans Gmail history to rescue lost documents from client and relative emails.

Phases:
  --discover    B0: Scan all emails, find unknown senders (READ-ONLY)
  --inventory   B2: Count emails/attachments per client (READ-ONLY)
  --process     B3: Extract, classify, save documents
  --verify      B4: Verify integrity of created documents

Usage:
    python backfill_emails_from_gmail.py --discover
    python backfill_emails_from_gmail.py --inventory
    python backfill_emails_from_gmail.py --process --client-id 51 --dry-run
    python backfill_emails_from_gmail.py --process --since 2025-01-01 --limit 200
    python backfill_emails_from_gmail.py --process --relatives-only --dry-run
    python backfill_emails_from_gmail.py --verify
"""
import os
import sys
import json
import re
import time
import email
import email.utils
import imaplib
import hashlib
import logging
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

# Add CaseHub root to path
CASEHUB_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(CASEHUB_ROOT))

from dotenv import load_dotenv
load_dotenv(CASEHUB_ROOT / ".env")

from sqlalchemy.orm import Session
from models.base import SessionLocal
from models.document import Document
from models.client import Client

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────
GMAIL_EMAIL = os.getenv("GMAIL_CENTER_EMAIL", "info@immigrant.law")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_CENTER_APP_PASSWORD", "")

DATA_DIR = CASEHUB_ROOT / "data"
PROGRESS_FILE = DATA_DIR / "backfill_progress.json"
ALIASES_FILE = DATA_DIR / "client_email_aliases.json"

# Non-client senders to skip
SKIP_SENDER_PATTERNS = [
    'noreply@', 'no-reply@', 'mailer-daemon@',
    'drive-shares-dm-noreply@google.com',
    '@lists.aila.org', '@uscis.dhs.gov',
    'noreply@timetap.com', 'noreply@calendly.com',
    'info@immigrant.law', 'center@immigrant.law',
    'notification@', 'notifications@',
    '@googlemail.com', '@facebookmail.com',
    'noreply@github.com', 'noreply@google.com',
    'calendar-notification@google.com',
    'forwarding-noreply@google.com',
    '@bounce.', 'postmaster@',
    'support@', 'billing@', 'receipt@',
    '@paypal.com', '@stripe.com', '@square.com',
    '@mailchimp.com', '@sendgrid.net',
    'donotreply@', 'do-not-reply@',
    'automated@', 'auto@',
]

# File extensions to process
ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".gif",
    ".tiff", ".tif", ".bmp", ".xls", ".xlsx", ".txt", ".rtf",
    ".zip", ".rar",
}


def should_skip_sender(sender_email: str) -> bool:
    """Check if sender is automated/system email."""
    if not sender_email:
        return True
    s = sender_email.lower()
    return any(pattern in s for pattern in SKIP_SENDER_PATTERNS)


def extract_email_addr(header: str) -> str:
    """Extract email address from 'Name <email>' format."""
    if not header:
        return ""
    if "<" in header and ">" in header:
        return header.split("<")[1].split(">")[0].lower().strip()
    if "@" in header:
        return header.lower().strip()
    return ""


def decode_mime_header(header_value: str) -> str:
    """Decode MIME-encoded header."""
    if not header_value:
        return ""
    from email.header import decode_header
    parts = decode_header(header_value)
    result = []
    for content, charset in parts:
        if isinstance(content, bytes):
            try:
                result.append(content.decode(charset or "utf-8", errors="ignore"))
            except Exception:
                result.append(content.decode("utf-8", errors="ignore"))
        else:
            result.append(content)
    return "".join(result)


def has_attachments_from_structure(msg_data: bytes) -> bool:
    """Quick check if email has attachments from BODYSTRUCTURE."""
    # Simple heuristic: check Content-Disposition in headers
    return b"attachment" in msg_data.lower() if msg_data else False


class EmailBackfiller:
    """Retroactive email document rescue from Gmail."""

    def __init__(self, db: Session):
        self.db = db
        self.mail = None
        self.stats = Counter()
        self.aliases = self._load_aliases()
        self.progress = self._load_progress()
        self._client_cache: Dict[str, Optional[Dict]] = {}
        self._known_hashes: set = set()

    # ── Helpers ──────────────────────────────────────────────────────────

    def _load_aliases(self) -> Dict[str, Dict]:
        """Load client email aliases."""
        if ALIASES_FILE.exists():
            try:
                with open(ALIASES_FILE, "r") as f:
                    data = json.load(f)
                    result = {}
                    for alias_email, info in data.get("aliases", {}).items():
                        result[alias_email.lower()] = {
                            "name": info.get("client_name", ""),
                            "paralegal": info.get("paralegal", "Ana Clara"),
                            "case": str(info.get("client_id", "")),
                            "relationship": info.get("relationship", "unknown"),
                        }
                    return result
            except Exception as e:
                logger.warning(f"Could not load aliases: {e}")
        return {}

    def _load_progress(self) -> Dict:
        """Load backfill progress for resume."""
        if PROGRESS_FILE.exists():
            try:
                with open(PROGRESS_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "started_at": None,
            "last_processed_date": None,
            "last_message_id": None,
            "stats": {
                "emails_scanned": 0,
                "attachments_found": 0,
                "documents_created": 0,
                "duplicates_skipped": 0,
                "errors": 0,
            },
            "errors_log": [],
        }

    def _save_progress(self):
        """Save backfill progress."""
        self.progress["stats"] = dict(self.stats)
        with open(PROGRESS_FILE, "w") as f:
            json.dump(self.progress, f, indent=2, default=str)

    def _load_known_hashes(self):
        """Pre-load all content hashes from DB for fast dedup."""
        if not self._known_hashes:
            rows = self.db.query(Document.content_hash).filter(
                Document.content_hash.isnot(None)
            ).all()
            self._known_hashes = {r[0] for r in rows}
            logger.info(f"Loaded {len(self._known_hashes)} known content hashes")

    def get_client_info_extended(self, email_address: str) -> Optional[Dict]:
        """Lookup with 4 levels: CLIENT_MAPPING → active-clients → DB → aliases.

        Caches results per email for performance.
        Sanitizes 'case' field to avoid int('None') errors in create_document_record.
        """
        email_lower = email_address.lower()
        if email_lower in self._client_cache:
            return self._client_cache[email_lower]

        # Import from email_processor (same lookup chain)
        from services.email_processor import get_client_info
        result = get_client_info(email_lower)

        # Sanitize: ensure 'case' is a valid int string or None
        if result and result.get("case"):
            case_val = result["case"]
            if case_val in ("None", "null", ""):
                result["case"] = None
            else:
                try:
                    int(case_val)
                except (ValueError, TypeError):
                    # Try to look up client_id from DB by name
                    try:
                        client = self.db.query(Client).filter(
                            Client.email.ilike(email_lower)
                        ).first()
                        if client:
                            result["case"] = str(client.id)
                        else:
                            result["case"] = None
                    except Exception:
                        result["case"] = None

        self._client_cache[email_lower] = result
        return result

    # ── IMAP Connection ──────────────────────────────────────────────────

    def connect(self) -> bool:
        """Connect to Gmail IMAP."""
        if not GMAIL_APP_PASSWORD:
            logger.error("GMAIL_CENTER_APP_PASSWORD not configured")
            return False
        try:
            self.mail = imaplib.IMAP4_SSL("imap.gmail.com")
            self.mail.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
            self.mail.select('"[Gmail]/All Mail"')
            logger.info(f"Connected to {GMAIL_EMAIL} [Gmail]/All Mail")
            return True
        except Exception as e:
            logger.error(f"IMAP connection failed: {e}")
            return False

    def disconnect(self):
        """Disconnect from Gmail."""
        if self.mail:
            try:
                self.mail.logout()
            except Exception:
                pass

    # ── B0: Discovery ────────────────────────────────────────────────────

    def discover_unknown_senders(self, since: datetime = None) -> Dict:
        """Scan all emails to find unknown senders with attachments.

        Returns discovery report with candidate relatives.
        """
        if since is None:
            since = datetime(2024, 1, 1)

        if not self.connect():
            return {"error": "Connection failed"}

        try:
            date_str = since.strftime("%d-%b-%Y")
            _, messages = self.mail.search(None, f'SINCE "{date_str}"')
            msg_ids = messages[0].split()
            total = len(msg_ids)
            logger.info(f"Discovery: scanning {total} emails since {since.date()}")

            senders = defaultdict(lambda: {
                "count": 0,
                "has_attachments": 0,
                "subjects": [],
                "dates": [],
                "cc_with": set(),
                "to_with": set(),
            })
            known_count = 0
            system_count = 0
            unknown_count = 0

            for idx, msg_id in enumerate(msg_ids, 1):
                if idx % 500 == 0:
                    logger.info(f"Discovery progress: {idx}/{total}")

                try:
                    # Fetch headers only (fast)
                    _, data = self.mail.fetch(msg_id, "(BODY.PEEK[HEADER])")
                    if not data or not data[0]:
                        continue
                    header_data = data[0][1]
                    msg = email.message_from_bytes(header_data)

                    from_header = msg.get("From", "")
                    from_addr = extract_email_addr(from_header)
                    if not from_addr:
                        continue

                    subject = decode_mime_header(msg.get("Subject", ""))
                    date_str_val = msg.get("Date", "")

                    # Check CC and To for cross-referencing
                    to_header = msg.get("To", "")
                    cc_header = msg.get("Cc", "")
                    content_type = msg.get("Content-Type", "")

                    # Quick attachment detection from headers
                    has_att = "multipart/mixed" in content_type.lower()

                    info = senders[from_addr]
                    info["count"] += 1
                    if has_att:
                        info["has_attachments"] += 1
                    if subject and len(info["subjects"]) < 5:
                        info["subjects"].append(subject[:100])
                    if date_str_val:
                        try:
                            dt = email.utils.parsedate_to_datetime(date_str_val)
                            info["dates"].append(dt.isoformat()[:10])
                        except Exception:
                            pass

                    # Track CC/To for relative discovery
                    for addr_str in [to_header, cc_header]:
                        if addr_str:
                            for part in addr_str.split(","):
                                addr = extract_email_addr(part.strip())
                                if addr and addr != from_addr:
                                    client = self.get_client_info_extended(addr)
                                    if client:
                                        info["cc_with"].add(client["name"])

                except Exception as e:
                    logger.debug(f"Error scanning msg {msg_id}: {e}")
                    continue

            # Classify senders
            known_senders = {}
            system_senders = {}
            unknown_senders = {}
            candidate_relatives = []

            for sender_email, info in senders.items():
                # Convert sets to lists for JSON
                info["cc_with"] = list(info["cc_with"])
                info["to_with"] = list(info.get("to_with", set()))

                if should_skip_sender(sender_email):
                    system_senders[sender_email] = info
                    system_count += info["count"]
                elif self.get_client_info_extended(sender_email):
                    known_senders[sender_email] = info
                    known_count += info["count"]
                else:
                    unknown_senders[sender_email] = info
                    unknown_count += info["count"]

                    # Candidate relative: unknown sender with attachments
                    # or appears in threads with known clients
                    if info["has_attachments"] > 0 or info["cc_with"]:
                        date_range = sorted(info["dates"]) if info["dates"] else []
                        candidate_relatives.append({
                            "email": sender_email,
                            "count": info["count"],
                            "has_attachments": info["has_attachments"],
                            "thread_with_clients": info["cc_with"],
                            "subjects_sample": info["subjects"][:3],
                            "date_range": [date_range[0], date_range[-1]] if len(date_range) >= 2 else date_range,
                        })

            # Sort candidates by attachment count (most docs first)
            candidate_relatives.sort(key=lambda x: x["has_attachments"], reverse=True)

            report = {
                "scan_date": datetime.now().isoformat(),
                "since": since.isoformat(),
                "total_emails_scanned": total,
                "unique_senders": len(senders),
                "known_senders_count": len(known_senders),
                "known_emails_count": known_count,
                "system_senders_count": len(system_senders),
                "system_emails_count": system_count,
                "unknown_senders_count": len(unknown_senders),
                "unknown_emails_count": unknown_count,
                "candidate_relatives": candidate_relatives,
                "known_senders": {k: {"count": v["count"], "name": self.get_client_info_extended(k).get("name", "")}
                                  for k, v in known_senders.items()},
            }

            # Save report
            report_path = "/tmp/email_discovery_report.json"
            with open(report_path, "w") as f:
                json.dump(report, f, indent=2, default=str)

            logger.info(f"Discovery complete. Report: {report_path}")
            logger.info(f"  Total emails: {total}")
            logger.info(f"  Known senders: {len(known_senders)} ({known_count} emails)")
            logger.info(f"  System senders: {len(system_senders)} ({system_count} emails)")
            logger.info(f"  Unknown senders: {len(unknown_senders)} ({unknown_count} emails)")
            logger.info(f"  Candidate relatives (with attachments or CC): {len(candidate_relatives)}")

            # Print top candidates for quick review
            print("\n" + "=" * 70)
            print("TOP CANDIDATE RELATIVES (unknown senders with attachments)")
            print("=" * 70)
            for c in candidate_relatives[:30]:
                clients_str = ", ".join(c["thread_with_clients"]) if c["thread_with_clients"] else "no thread link"
                print(f"  {c['email']:<45} att={c['has_attachments']:>3}  emails={c['count']:>3}  linked_to=[{clients_str}]")
                if c["subjects_sample"]:
                    print(f"    subjects: {c['subjects_sample'][0][:80]}")

            return report

        finally:
            self.disconnect()

    # ── B2: Inventory ────────────────────────────────────────────────────

    def _fetch_batch_headers(self, msg_ids: list, batch_size: int = 50) -> list:
        """Fetch headers using batch IMAP FETCH to avoid OVERQUOTA.

        Uses FETCH ranges (e.g. '1:50') to fetch multiple headers in one command,
        dramatically reducing IMAP command count.

        Returns list of (msg_id, from_addr, client_info) for matched emails.
        """
        matched = []
        total = len(msg_ids)

        for batch_start in range(0, total, batch_size):
            batch = msg_ids[batch_start:batch_start + batch_size]
            batch_end = min(batch_start + batch_size, total)
            logger.info(f"  Header batch {batch_start+1}-{batch_end}/{total} (matched: {len(matched)})")

            # Build comma-separated ID list for single FETCH command
            id_set = b",".join(batch)

            try:
                _, data = self.mail.fetch(id_set, "(BODY.PEEK[HEADER])")
                if not data:
                    continue

                # Parse multi-message response
                for i in range(0, len(data)):
                    item = data[i]
                    if isinstance(item, tuple) and len(item) == 2:
                        try:
                            msg = email.message_from_bytes(item[1])
                            from_addr = extract_email_addr(msg.get("From", ""))
                            if not from_addr or should_skip_sender(from_addr):
                                continue
                            client_info = self.get_client_info_extended(from_addr)
                            if client_info:
                                # Extract msg_id from response (e.g. b'123 (BODY...')
                                resp_line = item[0]
                                mid = resp_line.split(b" ")[0] if resp_line else None
                                if mid:
                                    matched.append((mid, from_addr, client_info))
                        except Exception as e:
                            logger.debug(f"Parse error in batch: {e}")
                            continue

            except Exception as e:
                err_str = str(e)
                if "OVERQUOTA" in err_str:
                    logger.warning(f"OVERQUOTA at batch {batch_start}, sleeping 30s then reconnecting...")
                    self.disconnect()
                    time.sleep(30)
                else:
                    logger.warning(f"Batch fetch error at {batch_start}: {e}, reconnecting...")
                    self.disconnect()
                    time.sleep(5)

                if not self.connect():
                    logger.error("Reconnection failed, returning partial results")
                    return matched
                continue

            # Brief pause between batches
            time.sleep(1)

        return matched

    def _fetch_batch_full(self, matched_ids: list, batch_size: int = 10) -> Dict:
        """Fetch full RFC822 one at a time with reconnection on OVERQUOTA.

        Full RFC822 fetches are heavy so we use smaller batches and more pauses.
        """
        by_client = defaultdict(lambda: {"emails": 0, "attachments": 0, "new": 0, "size_bytes": 0})
        by_relative = defaultdict(lambda: {"emails": 0, "attachments": 0})
        already_in_db = 0
        new_to_process = 0
        total_attachments = 0
        total_size = 0
        total = len(matched_ids)
        consecutive_errors = 0
        fetched_count = 0

        for idx, (msg_id, from_addr, client_info) in enumerate(matched_ids, 1):
            if idx % 25 == 0:
                logger.info(f"  Full fetch: {idx}/{total} (att={total_attachments}, size={total_size/(1024*1024):.1f}MB)")

            try:
                _, data = self.mail.fetch(msg_id, "(RFC822)")
                if not data or not data[0]:
                    continue
                msg = email.message_from_bytes(data[0][1])
                client_name = client_info["name"]
                is_relative = "relationship" in client_info

                attachments = self._extract_attachments(msg)
                if not attachments:
                    continue

                by_client[client_name]["emails"] += 1
                for filename, file_content in attachments:
                    ext = Path(filename).suffix.lower()
                    if ext not in ALLOWED_EXTENSIONS:
                        continue
                    file_size = len(file_content)
                    total_attachments += 1
                    total_size += file_size
                    by_client[client_name]["attachments"] += 1
                    by_client[client_name]["size_bytes"] += file_size
                    content_hash = hashlib.sha256(file_content).hexdigest()
                    if content_hash in self._known_hashes:
                        already_in_db += 1
                    else:
                        new_to_process += 1
                        by_client[client_name]["new"] += 1
                    if is_relative:
                        rel_key = f"{from_addr} -> {client_name}"
                        by_relative[rel_key]["emails"] += 1
                        by_relative[rel_key]["attachments"] += 1
                consecutive_errors = 0
                fetched_count += 1

                # Pace: 1 fetch per second to stay under rate limits
                if fetched_count % 5 == 0:
                    time.sleep(1)

            except Exception as e:
                consecutive_errors += 1
                err_str = str(e)
                if "OVERQUOTA" in err_str:
                    logger.warning(f"OVERQUOTA at full fetch {idx}, sleeping 30s...")
                    self.disconnect()
                    time.sleep(30)
                elif consecutive_errors >= 3:
                    logger.warning(f"Multiple errors at full fetch {idx}, reconnecting...")
                    self.disconnect()
                    time.sleep(5)
                else:
                    logger.debug(f"Full fetch error {msg_id}: {e}")
                    continue

                if not self.connect():
                    logger.error("Reconnection failed during full fetch")
                    break
                consecutive_errors = 0

        # Add human-readable sizes
        for name in by_client:
            by_client[name]["size_mb"] = round(by_client[name]["size_bytes"] / (1024 * 1024), 2)

        return {
            "by_client": dict(by_client),
            "by_relative": dict(by_relative),
            "already_in_db": already_in_db,
            "new_to_process": new_to_process,
            "total_attachments": total_attachments,
            "total_size": total_size,
        }

    def inventory(self, since: datetime = None) -> Dict:
        """Count emails and attachments per client before processing.

        Two-pass approach with batch reconnection:
        1. Fetch headers in batches → filter to known senders
        2. Fetch full RFC822 in batches → count attachments and sizes
        """
        if since is None:
            since = datetime(2024, 1, 1)

        if not self.connect():
            return {"error": "Connection failed"}

        self._load_known_hashes()

        try:
            date_str = since.strftime("%d-%b-%Y")
            _, messages = self.mail.search(None, f'SINCE "{date_str}"')
            msg_ids = messages[0].split()
            total = len(msg_ids)
            logger.info(f"Inventory: scanning {total} emails since {since.date()}")

            # PASS 1: Headers in batches
            logger.info("Pass 1: Scanning headers to find client emails...")
            matched_ids = self._fetch_batch_headers(msg_ids)
            logger.info(f"Pass 1 complete: {len(matched_ids)} client emails out of {total}")

            # PASS 2: Full fetch in batches (reconnect first)
            self.disconnect()
            time.sleep(1)
            if not self.connect():
                return {"error": "Reconnection failed for pass 2"}

            logger.info(f"Pass 2: Fetching {len(matched_ids)} full emails for attachment analysis...")
            inv = self._fetch_batch_full(matched_ids)

            report = {
                "scan_date": datetime.now().isoformat(),
                "date_range": [since.isoformat()[:10], datetime.now().isoformat()[:10]],
                "total_emails_scanned": total,
                "client_emails_found": len(matched_ids),
                "total_matchable_emails": sum(c["emails"] for c in inv["by_client"].values()),
                "total_attachments": inv["total_attachments"],
                "total_size_bytes": inv["total_size"],
                "total_size_mb": round(inv["total_size"] / (1024 * 1024), 2) if inv["total_size"] else 0,
                "total_size_gb": round(inv["total_size"] / (1024 * 1024 * 1024), 2) if inv["total_size"] else 0,
                "already_in_db": inv["already_in_db"],
                "new_to_process": inv["new_to_process"],
                "by_client": inv["by_client"],
                "by_relative": inv["by_relative"],
            }

            report_path = "/tmp/backfill_inventory.json"
            with open(report_path, "w") as f:
                json.dump(report, f, indent=2, default=str)

            logger.info(f"Inventory complete. Report: {report_path}")
            logger.info(f"  Matchable emails: {report['total_matchable_emails']}")
            logger.info(f"  Total attachments: {inv['total_attachments']}")
            logger.info(f"  Total size: {report['total_size_mb']} MB ({report['total_size_gb']} GB)")
            logger.info(f"  Already in DB: {inv['already_in_db']}")
            logger.info(f"  New to process: {inv['new_to_process']}")

            print("\n" + "=" * 70)
            print("INVENTORY BY CLIENT")
            print("=" * 70)
            for name, info in sorted(inv["by_client"].items(), key=lambda x: x[1]["new"], reverse=True):
                if info["new"] > 0:
                    size_str = f"{info['size_mb']:.1f}MB" if info.get("size_mb", 0) >= 1 else f"{info.get('size_bytes', 0)/1024:.0f}KB"
                    print(f"  {name:<40} emails={info['emails']:>3}  att={info['attachments']:>3}  new={info['new']:>3}  size={size_str}")

            print(f"\n  TOTAL: {inv['total_attachments']} attachments, {report['total_size_mb']} MB ({report['total_size_gb']} GB)")
            print(f"  Already in DB: {inv['already_in_db']}  |  New to process: {inv['new_to_process']}")

            return report

        finally:
            self.disconnect()

    # ── B3: Process Backfill ─────────────────────────────────────────────

    def process_backfill(
        self,
        since: datetime = None,
        limit: int = None,
        client_id: int = None,
        relatives_only: bool = False,
        dry_run: bool = False,
    ) -> Dict:
        """Main backfill: extract attachments from historical emails.

        Uses two-pass approach with OVERQUOTA handling:
        1. Batch header scan -> find client emails
        2. Full RFC822 fetch with reconnection -> process attachments
        """
        if since is None:
            since = datetime(2024, 1, 1)

        if not self.connect():
            return {"error": "Connection failed"}

        self._load_known_hashes()

        # Import processing functions
        from services.email_processor import create_document_record
        from services.attachment_handler import AttachmentHandler
        from scripts.attachment_to_client import save_to_client_folder, classify_by_filename as classify_simple
        from services.document_sync import sync_to_google_drive

        handler = AttachmentHandler()

        if not self.progress["started_at"]:
            self.progress["started_at"] = datetime.now().isoformat()

        try:
            date_str = since.strftime("%d-%b-%Y")

            # Build search query
            search_str = f'SINCE "{date_str}"'
            if client_id:
                client = self.db.query(Client).filter(Client.id == client_id).first()
                if client and client.email:
                    search_str = f'FROM "{client.email}" SINCE "{date_str}"'
                    logger.info(f"Filtering for client {client.full_name} ({client.email})")
                else:
                    logger.error(f"Client {client_id} not found or has no email")
                    return {"error": f"Client {client_id} not found"}

            _, messages = self.mail.search(None, search_str)
            msg_ids = messages[0].split()
            total = len(msg_ids)
            logger.info(f"Backfill: {total} emails to scan since {since.date()}" +
                        (f" (limit={limit})" if limit else "") +
                        (" [DRY RUN]" if dry_run else ""))

            # PASS 1: Find client emails via batch header scan
            logger.info("Pass 1: Scanning headers to find client emails...")
            matched_ids = self._fetch_batch_headers(msg_ids)

            # Filter for relatives-only if requested
            if relatives_only:
                matched_ids = [(m, f, c) for m, f, c in matched_ids if "relationship" in c]

            # Apply limit
            if limit and len(matched_ids) > limit:
                matched_ids = matched_ids[:limit]

            logger.info(f"Pass 1 complete: {len(matched_ids)} client emails to process")

            # PASS 2: Full fetch + process attachments
            self.disconnect()
            time.sleep(1)
            if not self.connect():
                return {"error": "Reconnection failed for pass 2"}

            logger.info(f"Pass 2: Processing {len(matched_ids)} emails...")
            processed = 0
            created = 0
            skipped_dedup = 0
            skipped_no_att = 0
            errors = 0
            consecutive_errors = 0
            total_matched = len(matched_ids)

            for idx, (msg_id, from_addr, client_info) in enumerate(matched_ids, 1):
                if idx % 25 == 0:
                    logger.info(f"  Process: {idx}/{total_matched} (created={created}, dedup={skipped_dedup}, err={errors})")
                    if not dry_run:
                        self._save_progress()

                try:
                    _, data = self.mail.fetch(msg_id, "(RFC822)")
                    if not data or not data[0]:
                        continue
                    msg = email.message_from_bytes(data[0][1])

                    message_id = msg.get("Message-ID", "")
                    client_name = client_info["name"]
                    is_relative = "relationship" in client_info

                    date_str_val = msg.get("Date", "")
                    try:
                        email_date = email.utils.parsedate_to_datetime(date_str_val)
                    except Exception:
                        email_date = datetime.now()

                    attachments = self._extract_attachments(msg)
                    if not attachments:
                        skipped_no_att += 1
                        continue

                    processed += 1

                    for filename, file_content in attachments:
                        ext = Path(filename).suffix.lower()
                        if ext not in ALLOWED_EXTENSIONS:
                            continue

                        content_hash = hashlib.sha256(file_content).hexdigest()
                        if content_hash in self._known_hashes:
                            skipped_dedup += 1
                            continue

                        rel_tag = f" (via {client_info.get('relationship', '')})" if is_relative else ""

                        if dry_run:
                            print(f"  [DRY RUN] Would process: {filename} -> {client_name}{rel_tag} ({len(file_content)} bytes)")
                            created += 1
                            continue

                        try:
                            result = handler.save_attachment(
                                content=file_content,
                                filename=filename,
                                client_name=client_name,
                                email_date=email_date,
                            )

                            doc_type = result.get("type", classify_simple(filename))
                            client_folder_result = None
                            try:
                                client_folder_result = save_to_client_folder(
                                    file_content, filename, client_name, doc_type, from_addr
                                )
                            except Exception as e:
                                logger.warning(f"Could not save to client folder: {e}")

                            doc_id = create_document_record(
                                result=result,
                                client_folder_result=client_folder_result,
                                client_name=client_name,
                                client_info=client_info,
                                from_email=from_addr,
                                filename=filename,
                                file_content=file_content,
                            )

                            if doc_id:
                                self._known_hashes.add(content_hash)
                                created += 1
                                try:
                                    sync_db = SessionLocal()
                                    sync_to_google_drive(sync_db, doc_id)
                                    sync_db.close()
                                except Exception as e:
                                    logger.warning(f"Drive sync error for {filename}: {e}")
                                logger.info(f"[{idx}/{total_matched}] CREATED doc #{doc_id}: {filename} -> {client_name}{rel_tag}")
                            else:
                                skipped_dedup += 1

                        except Exception as e:
                            errors += 1
                            logger.error(f"Error processing {filename}: {e}")
                            self.progress["errors_log"].append({
                                "message_id": message_id,
                                "filename": filename,
                                "error": str(e),
                                "timestamp": datetime.now().isoformat(),
                            })

                    self.progress["last_processed_date"] = email_date.isoformat()
                    self.progress["last_message_id"] = message_id
                    consecutive_errors = 0

                    # Pace fetches to stay under Gmail rate limits
                    if idx % 5 == 0:
                        time.sleep(1)

                except Exception as e:
                    consecutive_errors += 1
                    err_str = str(e)
                    if "OVERQUOTA" in err_str:
                        logger.warning(f"OVERQUOTA at process {idx}, sleeping 30s...")
                        self.disconnect()
                        time.sleep(30)
                    elif consecutive_errors >= 3:
                        logger.warning(f"Multiple errors at process {idx}, reconnecting...")
                        self.disconnect()
                        time.sleep(5)
                    else:
                        errors += 1
                        logger.error(f"Error with email {msg_id}: {e}")
                        continue

                    if not self.connect():
                        logger.error("Reconnection failed during processing")
                        break
                    consecutive_errors = 0

            # Update stats
            self.stats["emails_scanned"] = total
            self.stats["attachments_found"] = processed
            self.stats["documents_created"] = created
            self.stats["duplicates_skipped"] = skipped_dedup
            self.stats["errors"] = errors

            if not dry_run:
                self._save_progress()

            result = {
                "mode": "dry_run" if dry_run else "live",
                "total_emails_scanned": total,
                "matched_client_emails": total_matched,
                "emails_with_attachments": processed,
                "documents_created": created,
                "duplicates_skipped": skipped_dedup,
                "no_attachments": skipped_no_att,
                "errors": errors,
            }

            logger.info(f"Backfill complete: {result}")

            print("\n" + "=" * 70)
            print(f"BACKFILL {'(DRY RUN) ' if dry_run else ''}RESULTS")
            print("=" * 70)
            print(f"  Emails scanned:      {total}")
            print(f"  Client matches:      {total_matched}")
            print(f"  With attachments:    {processed}")
            print(f"  Documents created:   {created}")
            print(f"  Duplicates skipped:  {skipped_dedup}")
            print(f"  No attachments:      {skipped_no_att}")
            print(f"  Errors:              {errors}")

            return result

        finally:
            self.disconnect()

    # ── B4: Verify ───────────────────────────────────────────────────────

    def verify_integrity(self, sample_size: int = 50) -> Dict:
        """Verify integrity of recently created documents."""
        # Find recent backfill documents
        docs = self.db.query(Document).filter(
            Document.uploaded_via == "email",
        ).order_by(Document.id.desc()).limit(sample_size).all()

        if not docs:
            logger.info("No email-uploaded documents found to verify")
            return {"total": 0, "ok": 0, "missing": 0, "hash_mismatch": 0}

        ok = 0
        missing = 0
        hash_mismatch = 0
        results = []

        for doc in docs:
            path = doc.file_path
            status = "ok"

            if not path or not os.path.exists(path):
                missing += 1
                status = "missing"
            elif doc.content_hash:
                actual_hash = hashlib.sha256(open(path, "rb").read()).hexdigest()
                if actual_hash != doc.content_hash:
                    hash_mismatch += 1
                    status = "hash_mismatch"
                else:
                    ok += 1
            else:
                ok += 1

            results.append({
                "id": doc.id,
                "name": doc.name,
                "status": status,
                "path": path,
            })

        report = {
            "total": len(docs),
            "ok": ok,
            "missing": missing,
            "hash_mismatch": hash_mismatch,
            "details": results,
        }

        # Also get overall stats
        from sqlalchemy import func, text
        total_email_docs = self.db.query(func.count(Document.id)).filter(
            Document.uploaded_via == "email"
        ).scalar()

        report["total_email_documents_in_db"] = total_email_docs

        logger.info(f"Verify: {ok}/{len(docs)} OK, {missing} missing, {hash_mismatch} hash_mismatch")
        logger.info(f"Total email documents in DB: {total_email_docs}")

        print("\n" + "=" * 70)
        print("INTEGRITY VERIFICATION")
        print("=" * 70)
        print(f"  Sample size: {len(docs)}")
        print(f"  OK:          {ok}")
        print(f"  Missing:     {missing}")
        print(f"  Hash error:  {hash_mismatch}")
        print(f"  Total email docs in DB: {total_email_docs}")

        return report

    # ── Internal Helpers ─────────────────────────────────────────────────

    def _extract_attachments(self, msg) -> List[tuple]:
        """Extract attachments from email message."""
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


# ── CLI ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CaseHub Email Backfill")
    parser.add_argument("--discover", action="store_true", help="B0: Discover unknown senders (read-only)")
    parser.add_argument("--inventory", action="store_true", help="B2: Count emails/attachments per client (read-only)")
    parser.add_argument("--process", action="store_true", help="B3: Process backfill")
    parser.add_argument("--verify", action="store_true", help="B4: Verify integrity")

    parser.add_argument("--since", help="Start date (YYYY-MM-DD), default 2024-01-01")
    parser.add_argument("--limit", type=int, help="Max emails to process")
    parser.add_argument("--client-id", type=int, help="Filter by client ID")
    parser.add_argument("--relatives-only", action="store_true", help="Only process relative emails")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(str(CASEHUB_ROOT / "backfill_emails.log")),
        ],
    )

    since = None
    if args.since:
        since = datetime.strptime(args.since, "%Y-%m-%d")

    db = SessionLocal()

    try:
        backfiller = EmailBackfiller(db)

        if args.discover:
            backfiller.discover_unknown_senders(since=since)
        elif args.inventory:
            backfiller.inventory(since=since)
        elif args.process:
            backfiller.process_backfill(
                since=since,
                limit=args.limit,
                client_id=args.client_id,
                relatives_only=args.relatives_only,
                dry_run=args.dry_run,
            )
        elif args.verify:
            backfiller.verify_integrity()
        else:
            parser.print_help()
    finally:
        db.close()


if __name__ == "__main__":
    main()
