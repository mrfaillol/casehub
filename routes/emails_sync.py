"""
CaseHub - Email Sync & Ingestion Routes
Handles Gmail/IMAP sync, email linking, inbox monitoring,
bulk operations, and sync health monitoring.
"""
from fastapi import APIRouter, Depends, Request, Form, BackgroundTasks
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
import json
import imaplib
import email
from email.header import decode_header
from datetime import datetime
import base64
import logging
import os

logger = logging.getLogger(__name__)

from models import get_db
from auth import get_current_user
from services.auto_reply import process_auto_reply_sync
from services.credential_crypto import decrypt_credential
from config import settings
from routes._email_gate import require_email_access_api

PREFIX = settings.PREFIX
# Sentinela T11: per-tenant attachments dir; flat dir kept as read-fallback.
UPLOADS_BASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
UPLOAD_DIR = os.path.join(UPLOADS_BASE, "email_attachments")


def _attachments_dir(org_id) -> str:
    if org_id is None:
        return UPLOAD_DIR
    return os.path.join(UPLOADS_BASE, f"org_{org_id}", "email_attachments")

router = APIRouter(tags=["emails-sync"])


# ============================================
# ACCOUNT SYNC ENDPOINTS
# ============================================

@router.post("/accounts/{account_id}/sync")
async def sync_account(
    account_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    folder: str = "INBOX",
    db: Session = Depends(get_db)
):
    """Trigger email sync for an account"""
    user, blocked = require_email_access_api(request, db)
    if blocked is not None:
        return blocked

    org_id = getattr(request.state, "org_id", None)
    result = db.execute(text("SELECT * FROM email_accounts WHERE id = :id AND org_id = :org_id"), {"id": account_id, "org_id": org_id})
    account = result.fetchone()

    if not account:
        return JSONResponse({"error": "Account not found"}, status_code=404)

    # Note: sync_emails_from_account creates its own db session
    # (passing the request session fails because it's closed when the request ends)
    background_tasks.add_task(sync_emails_from_account, account_id, folder)

    return JSONResponse({"status": "Sync started", "account": account.name, "folder": folder})


@router.get("/api/folders/{account_id}")
async def get_imap_folders(account_id: int, request: Request, db: Session = Depends(get_db)):
    """Get list of IMAP folders for an account"""
    user, blocked = require_email_access_api(request, db)
    if blocked is not None:
        return blocked

    org_id = getattr(request.state, "org_id", None)
    result = db.execute(text("SELECT * FROM email_accounts WHERE id = :id AND org_id = :org_id"), {"id": account_id, "org_id": org_id})
    account = result.fetchone()

    if not account:
        return JSONResponse({"error": "Account not found"}, status_code=404)

    try:
        # Council ruling 2026-06-03-casehub-email-credential-encryption: Fernet.
        password = decrypt_credential(account.password_encrypted)

        if account.use_ssl:
            mail = imaplib.IMAP4_SSL(account.imap_server, account.imap_port)
        else:
            mail = imaplib.IMAP4(account.imap_server, account.imap_port)

        mail.login(account.username, password)

        # List all folders
        _, folder_data = mail.list()
        folders = []

        for folder_info in folder_data:
            if isinstance(folder_info, bytes):
                # Parse folder name from IMAP response
                # Format: (\\HasNoChildren) "/" "INBOX"
                decoded = folder_info.decode('utf-8', errors='replace')
                # Extract folder name (last part in quotes or after last space)
                if '"' in decoded:
                    parts = decoded.split('"')
                    if len(parts) >= 2:
                        folder_name = parts[-2]
                        folders.append(folder_name)
                else:
                    parts = decoded.split()
                    if parts:
                        folders.append(parts[-1])

        mail.logout()

        # Sort with INBOX first, then alphabetically
        folders = sorted(set(folders), key=lambda x: (x != 'INBOX', x.lower()))

        return JSONResponse({"folders": folders, "account": account.name})

    except Exception as e:
        return JSONResponse({"error": str(e), "folders": []}, status_code=500)


# ============================================
# GMAIL OAUTH INBOX SYNC (Option B — no app password)
# ============================================
#
# Reads the office mailbox via the SAME Google OAuth token the org already
# connected for Calendar (gmail.readonly scope), and upserts the messages
# into email_messages so the existing /emails inbox renders them with zero
# IMAP credentials (ruling 2026-06-03-casehub-email-credential-encryption,
# Option B). Org-scoped, dedupe by Gmail id (stored in message_id), best-effort.
# NEVER stores a password and NEVER logs token material.

GMAIL_OAUTH_ACCOUNT_NAME = "Google (OAuth)"


def _ensure_google_oauth_account(db: Session, org_id, email_address: str) -> Optional[int]:
    """Return the id of the logical 'google_oauth' email account for this org.

    Creates a password-less placeholder row so email_messages.account_id can
    point at it (the inbox list LEFT JOINs email_accounts for the address
    label). Option B never stores a Gmail password — password_encrypted is
    an empty string, and this account is disabled for IMAP polling so the
    IMAP sync loop never tries to log in with it.
    """
    if org_id is None:
        return None
    try:
        existing = db.execute(
            text(
                "SELECT id FROM email_accounts "
                "WHERE org_id = :org_id AND imap_server = 'google_oauth' LIMIT 1"
            ),
            {"org_id": org_id},
        ).fetchone()
        if existing:
            # Keep the displayed address fresh if Google reported a different one.
            if email_address:
                db.execute(
                    text("UPDATE email_accounts SET email_address = :addr WHERE id = :id"),
                    {"addr": email_address[:300], "id": existing[0]},
                )
                db.commit()
            return existing[0]
        row = db.execute(
            text(
                """
                INSERT INTO email_accounts
                    (name, email_address, imap_server, imap_port, smtp_server,
                     smtp_port, username, password_encrypted, use_ssl, enabled, org_id)
                VALUES
                    (:name, :addr, 'google_oauth', 0, NULL,
                     0, :addr, '', TRUE, FALSE, :org_id)
                RETURNING id
                """
            ),
            {
                "name": GMAIL_OAUTH_ACCOUNT_NAME,
                "addr": (email_address or "")[:300],
                "org_id": org_id,
            },
        ).fetchone()
        db.commit()
        return row[0] if row else None
    except Exception as exc:
        logger.warning("[GMAIL OAUTH] could not ensure logical account: %s", exc)
        db.rollback()
        return None


def sync_gmail_oauth_inbox(db: Session, org_id, max_results: int = 50) -> dict:
    """Pull the office INBOX via OAuth and upsert into email_messages.

    Returns a status dict mirroring the service:
      {'status': 'ok', 'imported': N, 'skipped': M, 'email': '<addr>'}
      {'status': 'needs_gmail_readonly_consent'}  # office must reconnect
      {'status': 'not_connected'} | {'status': 'error', 'error': '...'}
    Best-effort: never raises to the request handler.
    """
    if org_id is None:
        return {"status": "error", "error": "no_tenant", "imported": 0, "skipped": 0}

    from services.google_calendar import GoogleCalendarService

    svc = GoogleCalendarService(db=db, org_id=org_id)
    result = svc.fetch_inbox_messages(max_results=max_results)
    status = result.get("status")
    if status != "ok":
        # 'needs_gmail_readonly_consent' / 'not_connected' / 'error' pass through.
        return {"status": status, "error": result.get("error", ""),
                "imported": 0, "skipped": 0}

    account_id = _ensure_google_oauth_account(db, org_id, result.get("email", ""))
    imported = 0
    skipped = 0
    for msg in result.get("messages", []):
        # Dedupe key: prefer the RFC822 Message-ID; fall back to the Gmail id.
        # Both are stored in message_id so the IMAP UNIQUE-ish lookup matches.
        dedupe_id = (msg.get("message_id") or "").strip() or f"gmail:{msg.get('gmail_id')}"
        try:
            existing = db.execute(
                text(
                    "SELECT id FROM email_messages "
                    "WHERE org_id = :org_id AND message_id = :mid LIMIT 1"
                ),
                {"org_id": org_id, "mid": dedupe_id[:500]},
            ).fetchone()
            if existing:
                skipped += 1
                continue
            db.execute(
                text(
                    """
                    INSERT INTO email_messages
                        (account_id, message_id, subject, sender, recipients, cc,
                         body_text, body_html, folder, received_at, org_id)
                    VALUES
                        (:account_id, :message_id, :subject, :sender, :recipients, :cc,
                         :body_text, :body_html, 'INBOX', :received_at, :org_id)
                    """
                ),
                {
                    "account_id": account_id,
                    "message_id": dedupe_id[:500],
                    "subject": (msg.get("subject") or "")[:500],
                    "sender": (msg.get("sender") or "")[:300],
                    "recipients": msg.get("recipients") or "",
                    "cc": msg.get("cc") or "",
                    "body_text": (msg.get("body_text") or msg.get("snippet") or "")[:50000],
                    "body_html": (msg.get("body_html") or "")[:100000],
                    "received_at": msg.get("received_at"),
                    "org_id": org_id,
                },
            )
            imported += 1
        except Exception as exc:
            logger.warning("[GMAIL OAUTH] upsert failed for one message: %s", exc)
            db.rollback()
            continue
    try:
        db.commit()
    except Exception:
        db.rollback()
    return {"status": "ok", "imported": imported, "skipped": skipped,
            "email": result.get("email", "")}


@router.post("/api/gmail-oauth-sync")
async def api_gmail_oauth_sync(request: Request, db: Session = Depends(get_db)):
    """Manager-triggered pull of the office INBOX via OAuth (no app password)."""
    user, blocked = require_email_access_api(request, db)
    if blocked is not None:
        return blocked
    org_id = getattr(request.state, "org_id", None)
    if org_id is None:
        return JSONResponse({"success": False, "error": "no_tenant"}, status_code=403)
    res = sync_gmail_oauth_inbox(db, org_id)
    ok = res.get("status") == "ok"
    return JSONResponse({"success": ok, **res})


# ============================================
# IMAP SYNC FUNCTIONS
# ============================================

def decode_email_header(header):
    """Decode email header"""
    if not header:
        return ""
    decoded_parts = []
    for part, charset in decode_header(header):
        if isinstance(part, bytes):
            decoded_parts.append(part.decode(charset or 'utf-8', errors='replace'))
        else:
            decoded_parts.append(part)
    return ' '.join(decoded_parts)

def sync_emails_from_account(account_id: int, folder: str = "INBOX", limit: int = 500):
    """Sync emails from IMAP account"""
    from models import SessionLocal

    # Create a NEW database session for this background task
    # (The request session is closed by the time this runs)
    db = SessionLocal()

    # Validate folder parameter - fix for "None" string bug
    if not folder or folder == "None" or folder.strip() == "":
        folder = "INBOX"

    try:
        result = db.execute(text("SELECT * FROM email_accounts WHERE id = :id"), {"id": account_id})
        account = result.fetchone()

        if not account or not account.enabled:
            return

        # Decode password (Council ruling 2026-06-03-casehub-email-credential-encryption).
        password = decrypt_credential(account.password_encrypted)

        # Connect to IMAP
        if account.use_ssl:
            mail = imaplib.IMAP4_SSL(account.imap_server, account.imap_port)
        else:
            mail = imaplib.IMAP4(account.imap_server, account.imap_port)

        mail.login(account.username, password)

        # Properly handle IMAP folder selection with error handling
        try:
            # Para pastas especiais como [Gmail]/All Mail, usar aspas
            if '[' in folder or '/' in folder:
                status, data = mail.select(f'"{folder}"')
            else:
                status, data = mail.select(folder)

            if status != "OK":
                logger.warning("IMAP SELECT failed for folder %s: %s", folder, data)
                raise Exception(f"Cannot select folder: {data}")
        except imaplib.IMAP4.error as e:
            logger.error("IMAP SELECT error for %s: %s", folder, e)
            if folder != "INBOX":
                # Fallback to INBOX
                status, data = mail.select("INBOX")
                folder = "INBOX"
            else:
                mail.logout()
                return

        # Search for recent emails
        _, message_nums = mail.search(None, 'ALL')
        message_list = message_nums[0].split()

        # Get last N messages
        for num in message_list[-limit:]:
          try:
              _, msg_data = mail.fetch(num, '(RFC822)')

              for response_part in msg_data:
                  if isinstance(response_part, tuple):
                      msg = email.message_from_bytes(response_part[1])

                      # Extract headers
                      msg_id = msg.get('Message-ID', '')
                      subject = decode_email_header(msg.get('Subject', ''))
                      sender = decode_email_header(msg.get('From', ''))
                      recipients = decode_email_header(msg.get('To', ''))
                      cc = decode_email_header(msg.get('Cc', ''))
                      email_refs = msg.get('References', '')
                      date_str = msg.get('Date', '')

                      # Parse date
                      try:
                          received_at = email.utils.parsedate_to_datetime(date_str)
                      except Exception as e:
                          logger.error("Failed to parse email date '%s': %s", date_str, e)
                          received_at = datetime.now()

                      # Extract body and attachments
                      body_text = ''
                      body_html = ''
                      attachments_found = []  # Collect attachments during parsing

                      if msg.is_multipart():
                          for part in msg.walk():
                              content_type = part.get_content_type()
                              content_disposition = str(part.get('Content-Disposition', '')).lower()

                              # Check if this part is an attachment
                              if 'attachment' in content_disposition or (part.get_filename() and content_type not in ['text/plain', 'text/html', 'multipart/alternative', 'multipart/mixed', 'multipart/related']):
                                  filename = part.get_filename()
                                  if filename:
                                      try:
                                          if isinstance(filename, bytes):
                                              filename = filename.decode('utf-8', errors='replace')
                                      except Exception as e:
                                          logger.error("Failed to decode attachment filename: %s", e)
                                      payload_data = part.get_payload(decode=True)
                                      if payload_data:
                                          attachments_found.append({
                                              'filename': filename,
                                              'content_type': content_type,
                                              'data': payload_data
                                          })
                              elif content_type == 'text/plain' and 'attachment' not in content_disposition:
                                  try:
                                      body_text = part.get_payload(decode=True).decode('utf-8', errors='replace')
                                  except Exception as e:
                                      logger.error("Failed to decode text/plain part: %s", e)
                              elif content_type == 'text/html' and 'attachment' not in content_disposition:
                                  try:
                                      body_html = part.get_payload(decode=True).decode('utf-8', errors='replace')
                                  except Exception as e:
                                      logger.error("Failed to decode text/html part: %s", e)
                      else:
                          content_type = msg.get_content_type()
                          try:
                              payload = msg.get_payload(decode=True).decode('utf-8', errors='replace')
                              if content_type == 'text/plain':
                                  body_text = payload
                              else:
                                  body_html = payload
                          except Exception as e:
                              logger.error("Failed to decode email payload: %s", e)

                      # Check if email already exists
                      existing = db.execute(
                          text("SELECT id FROM email_messages WHERE account_id = :account_id AND message_id = :message_id"),
                          {"account_id": account_id, "message_id": msg_id}
                      ).fetchone()

                      if not existing:
                          # Insert email
                          insert_result = db.execute(
                              text("""
                                  INSERT INTO email_messages
                                  (account_id, message_id, subject, sender, recipients, cc, body_text, body_html, folder, received_at, email_references)
                                  VALUES (:account_id, :message_id, :subject, :sender, :recipients, :cc, :body_text, :body_html, :folder, :received_at, :email_references)
                                  RETURNING id
                              """),
                              {
                                  "account_id": account_id,
                                  "message_id": msg_id,
                                  "subject": subject[:500] if subject else '',
                                  "sender": sender[:300] if sender else '',
                                  "recipients": recipients,
                                  "cc": cc,
                                  "body_text": body_text[:50000] if body_text else '',
                                  "body_html": body_html[:100000] if body_html else '',
                                  "folder": folder or "",
                                  "received_at": received_at,
                                  "email_references": email_refs[:2000] if email_refs else None
                              }
                          )

                          # Get the new email ID and trigger smart auto-reply
                          new_email_row = insert_result.fetchone()
                          if new_email_row:
                              new_email_id = new_email_row[0]

                              # Save attachments if any were found
                              if attachments_found:
                                  import uuid as uuid_module
                                  # Sentinela T11: per-tenant attachments dir.
                                  # account is the email_accounts row loaded above (has org_id column).
                                  account_org_id = getattr(account, "org_id", None)
                                  att_dir = _attachments_dir(account_org_id)
                                  os.makedirs(att_dir, exist_ok=True)
                                  for att in attachments_found:
                                      try:
                                          safe_filename = f"{uuid_module.uuid4()}_{att['filename']}"
                                          att_path = os.path.join(att_dir, safe_filename)
                                          with open(att_path, 'wb') as f:
                                              f.write(att['data'])
                                          db.execute(
                                              text("""INSERT INTO email_attachments
                                                  (message_id, filename, mime_type, file_size, file_path)
                                                  VALUES (:message_id, :filename, :mime_type, :file_size, :file_path)"""),
                                              {
                                                  "message_id": new_email_id,
                                                  "filename": att['filename'][:300],
                                                  "mime_type": att['content_type'][:100] if att['content_type'] else 'application/octet-stream',
                                                  "file_size": len(att['data']),
                                                  "file_path": att_path
                                              }
                                          )
                                          logger.info("Saved attachment: %s for email %s", att['filename'], new_email_id)
                                      except Exception as att_err:
                                          logger.error("Error saving attachment %s: %s", att['filename'], att_err)
                                  db.commit()

                              # Process auto-reply for inbound emails only
                              if folder == "INBOX":
                                  try:
                                      process_auto_reply_sync(db, new_email_id, sender, subject, body_text or "")
                                  except Exception as ar_err:
                                      logger.error("Auto-reply error for email %s: %s", new_email_id, ar_err)

                          db.commit()
          except Exception as email_err:
              logger.error("[SYNC ERROR] Falha ao processar email num=%s: %s", num, email_err)
              try:
                  db.rollback()
              except Exception as e:
                  logger.error("Failed to rollback after sync error: %s", e)
              continue

        mail.logout()

        # Update last sync time
        db.execute(
            text("UPDATE email_accounts SET last_sync_at = NOW(), last_error = NULL WHERE id = :id"),
            {"id": account_id}
        )
        db.commit()

        # Auto-sync to Messaging Hub (unified_messages table)
        try:
            sync_query = """
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
            db.execute(text(sync_query))
            db.commit()
        except Exception as hub_error:
            logger.error("Error syncing to Messaging Hub: %s", hub_error)

    except Exception as e:
        try:
            db.execute(
                text("UPDATE email_accounts SET last_error = :error WHERE id = :id"),
                {"id": account_id, "error": str(e)[:500]}
            )
            db.commit()
        except Exception as e:
            logger.error("Failed to update email account error status: %s", e)
    finally:
        # Always close the session we created
        db.close()


# ============================================
# BULK OPERATIONS
# ============================================

@router.post("/bulk")
async def bulk_email_action(
    request: Request,
    operation: str = Form(...),
    email_ids: str = Form(...),
    bulk_client_id: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    """Execute bulk operations on emails"""
    user, blocked = require_email_access_api(request, db)
    if blocked is not None:
        return blocked

    try:
        ids = json.loads(email_ids)
    except Exception as e:
        logger.error("Failed to parse email IDs JSON: %s", e)
        ids = []

    if not ids:
        return RedirectResponse(url=f"{PREFIX}/emails?error=No+emails+selected", status_code=302)

    success_count = 0

    org_id = getattr(request.state, "org_id", None)
    try:
        if operation == "mark_read":
            for email_id in ids:
                db.execute(text("UPDATE email_messages SET is_read = true WHERE id = :id AND org_id = :org_id"), {"id": email_id, "org_id": org_id})
                success_count += 1

        elif operation == "mark_unread":
            for email_id in ids:
                db.execute(text("UPDATE email_messages SET is_read = false WHERE id = :id AND org_id = :org_id"), {"id": email_id, "org_id": org_id})
                success_count += 1

        elif operation == "link_client" and bulk_client_id:
            for email_id in ids:
                db.execute(
                    text("UPDATE email_messages SET client_id = :client_id WHERE id = :id AND org_id = :org_id"),
                    {"client_id": bulk_client_id, "id": email_id, "org_id": org_id}
                )
                success_count += 1

        elif operation == "archive":
            for email_id in ids:
                db.execute(
                    text("""
                        UPDATE email_messages
                        SET archived = true,
                            archived_at = NOW(),
                            archived_by = :user_email
                        WHERE id = :id AND org_id = :org_id
                    """),
                    {"id": email_id, "user_email": user.email, "org_id": org_id}
                )
                success_count += 1

        elif operation == "unarchive":
            for email_id in ids:
                db.execute(
                    text("""
                        UPDATE email_messages
                        SET archived = false,
                            archived_at = NULL,
                            archived_by = NULL
                        WHERE id = :id AND org_id = :org_id
                    """),
                    {"id": email_id, "org_id": org_id}
                )
                success_count += 1

        elif operation == "delete":
            for email_id in ids:
                db.execute(text("DELETE FROM email_messages WHERE id = :id AND org_id = :org_id"), {"id": email_id, "org_id": org_id})
                success_count += 1

        db.commit()

    except Exception as e:
        db.rollback()
        return RedirectResponse(url=f"{PREFIX}/emails?error={str(e)}", status_code=302)

    return RedirectResponse(url=f"{PREFIX}/emails?bulk_success={success_count}", status_code=302)


# ============================================
# PENDING EMAIL PROCESSING
# ============================================

@router.post("/process-pending")
async def process_pending_emails(request: Request, db: Session = Depends(get_db)):
    """
    Process pending emails manually (trigger the background worker).
    Processes emails that:
    - Are not linked to a client
    - Were created more than 10 minutes ago
    - Have not been processed (no notion_task_id)
    """
    user, blocked = require_email_access_api(request, db)
    if blocked is not None:
        return blocked

    try:
        from services.email_worker import run_email_worker
        results = await run_email_worker(db)

        return JSONResponse({
            "success": True,
            "message": f"Processed {results['processed']} emails",
            "results": results
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)


@router.get("/api/pending-count")
async def get_pending_emails_count(request: Request, db: Session = Depends(get_db)):
    """Get count of emails waiting to be processed by the worker"""
    user, blocked = require_email_access_api(request, db)
    if blocked is not None:
        return blocked

    from datetime import datetime, timedelta
    cutoff_time = datetime.utcnow() - timedelta(minutes=10)

    result = db.execute(text("""
        SELECT COUNT(*) as count
        FROM email_messages
        WHERE client_id IS NULL
          AND notion_task_id IS NULL
          AND direction = 'inbound'
          AND created_at < :cutoff
    """), {"cutoff": cutoff_time})

    count = result.fetchone()[0]

    return JSONResponse({
        "success": True,
        "pending_count": count
    })


# =============================================================================
# SYNC MONITOR ENDPOINTS
# =============================================================================

@router.get("/api/sync-health")
async def api_sync_health(request: Request, db: Session = Depends(get_db)):
    """Get email sync health status"""
    user, blocked = require_email_access_api(request, db)
    if blocked is not None:
        return blocked

    from services.sync_monitor import get_sync_status
    return JSONResponse(get_sync_status(db))


@router.post("/api/sync-recover")
async def api_sync_recover(request: Request, db: Session = Depends(get_db)):
    """Trigger auto-recovery if issues detected"""
    user, blocked = require_email_access_api(request, db)
    if blocked is not None:
        return blocked

    from services.sync_monitor import check_and_recover
    return JSONResponse(check_and_recover(db))
