"""
CaseHub - Email/IMAP Integration Routes
Main module: CRUD operations (list, view, search, mark read/unread, delete, move),
email accounts management, and linking.

Compose/send routes: see emails_compose.py
Sync/ingestion routes: see emails_sync.py
"""
from core.form_utils import form_int, form_float
from fastapi import APIRouter, Depends, Request, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, or_
from sqlalchemy.exc import OperationalError, ProgrammingError
from typing import Optional
import json
import base64
import logging
import os

logger = logging.getLogger(__name__)

from models import get_db, Client, Case
from auth import get_current_user
from models.tenant import tenant_query
from services.email_service import email_service
from services.credential_crypto import encrypt_credential
from config import settings
from core.template_config import templates, PREFIX, inject_org_context
from routes._email_gate import (
    require_email_access,
    require_email_access_api,
    file_email_access_request,
    is_email_manager,
)

# Sentinela T11: email attachments now live under
# uploads/org_<id>/email_attachments/. UPLOAD_DIR kept as the legacy fallback
# (read path) so existing rows whose file_path points at the flat location
# stay reachable through the auth-gated /uploads route.
UPLOADS_BASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
UPLOAD_DIR = os.path.join(UPLOADS_BASE, "email_attachments")


def email_attachments_dir(org_id) -> str:
    """Per-tenant attachments directory; falls back to legacy when org_id is None."""
    if org_id is None:
        return UPLOAD_DIR
    return os.path.join(UPLOADS_BASE, f"org_{org_id}", "email_attachments")


router = APIRouter(prefix="/emails", tags=["emails"])

# Ensure upload directory exists (wrapped for Docker permissions)
try:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
except PermissionError:
    pass  # Directory will be created by Dockerfile or at runtime

# ---------------------------------------------------------------------------
# Include sub-routers (compose & sync)
# ---------------------------------------------------------------------------
from routes.emails_compose import router as compose_router
from routes.emails_sync import router as sync_router

router.include_router(compose_router)
router.include_router(sync_router)

# Also re-export sync_emails_from_account so existing imports
# (services/sync_monitor.py, services/email_automation.py) keep working.
from routes.emails_sync import sync_emails_from_account  # noqa: F401

# ============================================
# EMAIL ACCOUNTS MANAGEMENT
# ============================================

@router.get("", response_class=HTMLResponse)
async def list_emails(
    request: Request,
    client_id: Optional[int] = None,
    case_id: Optional[int] = None,
    folder: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    show_archived: bool = False,
    show_autoreplies: bool = False,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """List emails with optional filters"""
    # Gestor-only gate: non-managers get the "request access" screen.
    user, blocked = require_email_access(request, db)
    if blocked is not None:
        return blocked

    # Validate page parameter
    page = max(1, page)

    # Sentinela T2: every email_messages query MUST scope by org_id.
    org_id = getattr(request.state, "org_id", None)
    if org_id is None:
        raise HTTPException(status_code=403, detail="No tenant context")

    # Option B (ruling 2026-06-03): when the org has connected its Google
    # account (Calendar) but has NO real IMAP account, opportunistically pull
    # the office INBOX via the same OAuth token (gmail.readonly). Best-effort,
    # manager-gated (already enforced above), org-scoped, on first page only.
    # A token without gmail.readonly (office not yet reconnected) is a no-op:
    # the helper returns 'needs_gmail_readonly_consent' and never raises.
    gmail_consent_needed = False
    gmail_connect_account = None
    if page == 1 and not search:
        try:
            from routes.emails_sync import sync_gmail_oauth_inbox
            from services.google_calendar import GoogleCalendarService

            has_imap = db.execute(
                text(
                    "SELECT 1 FROM email_accounts "
                    "WHERE org_id = :org_id AND enabled = TRUE "
                    "  AND imap_server IS NOT NULL AND imap_server <> 'google_oauth' "
                    "LIMIT 1"
                ),
                {"org_id": org_id},
            ).first()
            svc = GoogleCalendarService(db=db, org_id=org_id)
            write_account = svc.get_default_write_account()
            if not has_imap and write_account:
                if not svc._account_can_read_email(write_account):
                    gmail_consent_needed = True
                    gmail_connect_account = write_account
                else:
                    if background_tasks:
                        background_tasks.add_task(sync_gmail_oauth_inbox, db, org_id)
        except Exception as exc:
            logger.warning("[EMAIL LIST] Gmail OAuth opportunistic sync skipped: %s", exc)
            db.rollback()

    query = "SELECT em.*, ea.email_address as account_email, c.first_name as client_first_name, c.last_name as client_last_name, cs.case_number as case_number FROM email_messages em LEFT JOIN email_accounts ea ON em.account_id = ea.id LEFT JOIN clients c ON em.client_id = c.id LEFT JOIN cases cs ON em.case_id = cs.id"
    params = {"org_id": org_id}
    conditions = ["em.org_id = :org_id"]

    if client_id:
        conditions.append("em.client_id = :client_id")
        params["client_id"] = client_id
    if case_id:
        conditions.append("em.case_id = :case_id")
        params["case_id"] = case_id
    if folder:
        conditions.append("em.folder = :folder")
        params["folder"] = folder
    if search and len(search) > 255:
        search = search[:255]
    if search:
        conditions.append("(LOWER(em.subject) LIKE :search OR LOWER(em.sender) LIKE :search OR LOWER(em.recipients) LIKE :search OR LOWER(COALESCE(em.body_text,'')) LIKE :search)")
        params["search"] = f"%{search.lower()}%"

    # Auto-reply filter condition
    _org_email = (settings.ORG_EMAIL or settings.SMTP_USER or "").lower()
    auto_reply_condition = f"(LOWER(COALESCE(em.subject,'')) LIKE 'automatic reply%' OR (LOWER(em.sender) LIKE '%{_org_email}%' AND em.folder = '[Gmail]/Sent Mail'))"

    if show_autoreplies:
        # Show ONLY auto-replies
        conditions.append(auto_reply_condition)
    else:
        # Filter archived emails (show only non-archived by default)
        if not show_archived:
            conditions.append("(em.archived = false OR em.archived IS NULL)")
        else:
            conditions.append("em.archived = true")
        # Exclude auto-replies from Active/Archived views
        conditions.append(f"NOT {auto_reply_condition}")

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    per_page = 200
    query += f" ORDER BY em.received_at DESC LIMIT {per_page + 1} OFFSET :offset"
    params["offset"] = (page - 1) * per_page

    try:
        result = db.execute(text(query), params)
        emails = list(result.fetchall())
    except Exception as e:
        logger.error("[EMAIL LIST ERROR] Query failed: %s", e)
        db.rollback()
        emails = []

    # Check if there are more emails
    has_more = len(emails) > per_page
    if has_more:
        emails = emails[:per_page]

    # Get clients and cases for link modal
    clients = tenant_query(db, Client, request.state.org_id).filter(or_(Client.status == None, Client.status != 'deleted')).order_by(Client.first_name).all()
    cases = tenant_query(db, Case, request.state.org_id).order_by(Case.created_at.desc()).limit(100).all()

    # Get account IDs and info for sync.
    #
    # ``email_accounts`` + ``email_messages`` are raw-migration tables —
    # not declared as SQLAlchemy models. On a fresh deploy the migration
    # may not have run; the SELECTs raise UndefinedTable -> session
    # poisoned -> the rest of this handler 500s. Same defect class as
    # portal_access (PR #572) and unified_messages (PR #589).
    #
    # The email-list query above is already wrapped (PR #558). These
    # two sidecar queries needed the same treatment so the page renders
    # "no accounts" + "no synced folders" instead of crashing.
    accounts: list = []
    account_ids: list = []
    try:
        # Sentinela T2: scope account list to the current tenant. Older rows
        # without org_id (legacy single-tenant data) remain visible only when
        # the resolved tenant matches the default org.
        accounts_result = db.execute(
            text(
                "SELECT id, name, email_address FROM email_accounts "
                "WHERE enabled = TRUE AND (org_id = :org_id OR org_id IS NULL)"
            ),
            {"org_id": request.state.org_id},
        )
        accounts = accounts_result.fetchall()
        account_ids = [row[0] for row in accounts]
    except (OperationalError, ProgrammingError) as exc:
        logger.warning(
            "[EMAIL LIST] email_accounts unavailable (missing migration on "
            "this deploy?): %s", exc,
        )
        db.rollback()

    # Get distinct folders already synced (scoped to current tenant).
    synced_folders: list = []
    try:
        folders_result = db.execute(
            text(
                "SELECT DISTINCT folder FROM email_messages "
                "WHERE folder IS NOT NULL AND org_id = :org_id "
                "ORDER BY folder"
            ),
            {"org_id": org_id},
        )
        synced_folders = [row[0] for row in folders_result.fetchall()]
    except (OperationalError, ProgrammingError) as exc:
        logger.warning(
            "[EMAIL LIST] email_messages unavailable (missing migration on "
            "this deploy?): %s", exc,
        )
        db.rollback()

    # Get paralegal mapping for visual integration
    paralegal_mapping = get_paralegal_mapping()

    return templates.TemplateResponse("app/emails/list.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        **inject_org_context(request, user),
        "emails": emails,
        "clients": clients,
        "cases": cases,
        "has_more": has_more,
        "account_ids": account_ids,
        "accounts": accounts,
        "synced_folders": synced_folders,
        "client_id": client_id,
        "case_id": case_id,
        "folder": folder or "",
        "search": search or "",
        "page": page,
        "paralegal_mapping": paralegal_mapping,
        "get_domain_tag": get_domain_tag,
        "show_archived": show_archived,
        "show_autoreplies": show_autoreplies,
        "gmail_consent_needed": gmail_consent_needed,
        "gmail_connect_account": gmail_connect_account,
    })


@router.post("/request-access")
async def request_email_access(request: Request, db: Session = Depends(get_db)):
    """
    Non-manager users ask the org's managers for access to the Emails module.
    Files an idempotent in-app notification to each manager and re-renders the
    request-access screen with a confirmation. Managers never reach here (they
    already have access), so a manager hitting this just bounces to the inbox.
    """
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    if is_email_manager(user):
        # Already has access — send them straight to the inbox.
        return RedirectResponse(url=f"{PREFIX}/emails", status_code=303)

    created, already = file_email_access_request(request, db, user)
    ctx = {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        **inject_org_context(request, user),
        "already_requested": True,
        "just_requested": created,
        "was_pending": already,
    }
    return templates.TemplateResponse(
        "app/emails/request_access.html", ctx, status_code=200
    )


@router.get("/api/thread-siblings")
async def api_thread_siblings(request: Request, subject: str, client_id: Optional[int] = None, db: Session = Depends(get_db)):
    """API: Get all emails matching a normalized subject (for thread expansion)"""
    user, blocked = require_email_access_api(request, db)
    if blocked is not None:
        return blocked

    import re
    normalized = re.sub(r'^(re:\s*|fwd?:\s*|fw:\s*|re\[\d+\]:\s*)+', '', subject.strip(), flags=re.IGNORECASE).strip()
    if not normalized:
        return JSONResponse({"emails": []})

    # Sentinela T2: every email_messages query MUST scope by org_id.
    org_id = getattr(request.state, "org_id", None)
    if org_id is None:
        return JSONResponse({"emails": []})

    # Build query - optionally filter by client_id for accurate thread grouping
    where_extra = ""
    params = {"pattern": f"%{normalized}%", "org_id": org_id}
    if client_id:
        where_extra = " AND (em.client_id = :client_id OR em.client_id IS NULL)"
        params["client_id"] = client_id

    # Filter out auto-replies (both CaseHub and Gmail vacation) from threads
    _org_email_2 = (settings.ORG_EMAIL or settings.SMTP_USER or "").lower()
    params["org_email_pattern"] = f"%{_org_email_2}%"

    # Build the WHERE clause with parameterized values only
    client_filter_sql = " AND (em.client_id = :client_id OR em.client_id IS NULL)" if client_id else ""

    result = db.execute(
        text(f"""
            SELECT em.id, em.sender, em.subject, em.received_at, em.is_read, em.archived, em.folder,
                   SUBSTRING(em.body_text, 1, 80) as preview, em.client_id,
                   c.first_name as client_first_name, c.last_name as client_last_name
            FROM email_messages em
            LEFT JOIN clients c ON em.client_id = c.id
            WHERE em.org_id = :org_id
                  AND LOWER(REGEXP_REPLACE(COALESCE(em.subject,''), '^(Re:\\s*|Fwd?:\\s*|FW:\\s*|Re\\[\\d+\\]:\\s*)+', '', 'gi'))
                      ILIKE :pattern
                  {client_filter_sql}
                  AND NOT (
                      LOWER(COALESCE(em.subject,'')) LIKE 'automatic reply%%'
                      OR (LOWER(em.sender) LIKE :org_email_pattern AND em.folder = '[Gmail]/Sent Mail')
                  )
            ORDER BY em.received_at ASC
        """),
        params
    )
    rows = result.fetchall()
    emails = []
    for r in rows:
        emails.append({
            "id": r.id, "sender": r.sender, "subject": r.subject,
            "received_at": r.received_at.strftime('%m/%d %H:%M') if r.received_at else '-',
            "is_read": r.is_read, "archived": r.archived, "folder": r.folder or '',
            "preview": r.preview or '', "client_id": r.client_id,
            "client_name": f"{r.client_first_name} {r.client_last_name}" if r.client_first_name else None
        })
    return JSONResponse({"emails": emails, "count": len(emails)})


@router.get("/api/count")
async def api_email_count(request: Request, db: Session = Depends(get_db)):
    """API: Get email count for auto-sync check"""
    user, blocked = require_email_access_api(request, db)
    if blocked is not None:
        return blocked

    # Sentinela T2: scope to the current tenant.
    org_id = getattr(request.state, "org_id", None)
    if org_id is None:
        return JSONResponse({"count": 0})

    result = db.execute(
        text("SELECT COUNT(*) FROM email_messages WHERE org_id = :org_id"),
        {"org_id": org_id},
    )
    count = result.scalar()
    return JSONResponse({"count": count})


@router.post("/{email_id}/link")
async def link_email_to_client_case(
    request: Request,
    email_id: int,
    client_id: Optional[int] = Form(None),
    case_id: Optional[int] = Form(None),
    cc_email: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Link an email to a client and/or case"""
    user, blocked = require_email_access_api(request, db)
    if blocked is not None:
        return blocked

    # Sentinela T2: confine writes to the current tenant. Without the
    # org_id clause an attacker could re-link another tenant's email to
    # their own client (horizontal IDOR).
    org_id = getattr(request.state, "org_id", None)
    if org_id is None:
        return JSONResponse({"error": "No tenant context"}, status_code=403)

    # Build SET clause from whitelist of allowed columns
    allowed_columns = {"client_id", "case_id"}
    set_parts = []
    params = {"email_id": email_id, "org_id": org_id}

    if client_id:
        set_parts.append("client_id = :client_id")
        params["client_id"] = client_id
    if case_id:
        set_parts.append("case_id = :case_id")
        params["case_id"] = case_id

    if not set_parts:
        return JSONResponse({"error": "No client or case specified"}, status_code=400)

    set_clause = ", ".join(set_parts)
    result = db.execute(
        text(
            f"UPDATE email_messages SET {set_clause} "
            "WHERE id = :email_id AND org_id = :org_id"
        ),
        params,
    )
    db.commit()

    if getattr(result, "rowcount", 0) == 0:
        # Either the email doesn't exist or it belongs to another tenant.
        # Either way we surface a 404 to avoid leaking existence.
        return JSONResponse({"error": "Email not found"}, status_code=404)

    # Also update in unified_messages if it exists there.
    # unified_messages mirrors email_messages; scope by org_id when the column
    # exists (older deploys without the column fall back to source_table+source_id).
    try:
        db.execute(
            text(
                f"UPDATE unified_messages SET {set_clause} "
                "WHERE source_table = 'email_messages' "
                "  AND source_id = :email_id "
                "  AND (org_id = :org_id OR org_id IS NULL)"
            ),
            params,
        )
        db.commit()
    except Exception as e:
        logger.error("Failed to update unified_messages for email %s: %s", email_id, e)

    return JSONResponse({"success": True})

@router.get("/accounts", response_class=HTMLResponse)
async def list_accounts(request: Request, db: Session = Depends(get_db)):
    """List email accounts"""
    user, blocked = require_email_access(request, db)
    if blocked is not None:
        return blocked

    result = db.execute(text("SELECT * FROM email_accounts ORDER BY name"))
    accounts = result.fetchall()

    return templates.TemplateResponse("app/emails/accounts.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        **inject_org_context(request, user),
        "accounts": accounts
    })

@router.get("/accounts/new", response_class=HTMLResponse)
async def new_account(request: Request, db: Session = Depends(get_db)):
    user, blocked = require_email_access(request, db)
    if blocked is not None:
        return blocked

    return templates.TemplateResponse("app/emails/account_form.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        **inject_org_context(request, user),
        "account": None,
        "action": "Create"
    })

@router.post("/accounts/new")
async def create_account(
    request: Request,
    name: str = Form(...),
    email_address: str = Form(...),
    imap_server: str = Form(...),
    imap_port: int = Form(993),
    smtp_server: str = Form(None),
    smtp_port: int = Form(587),
    username: str = Form(...),
    password: str = Form(...),
    use_ssl: bool = Form(True),
    enabled: bool = Form(True),
    db: Session = Depends(get_db)
):
    user, blocked = require_email_access_api(request, db)
    if blocked is not None:
        return blocked

    # Council ruling 2026-06-03-casehub-email-credential-encryption:
    # real Fernet encryption (was plaintext-equivalent base64, CWE-312/CWE-261).
    password_encrypted = encrypt_credential(password)

    # Sentinela T2: stamp the new account with the current tenant.
    org_id_for_insert = getattr(request.state, "org_id", None)
    db.execute(
        text("""
            INSERT INTO email_accounts (name, email_address, imap_server, imap_port,
                smtp_server, smtp_port, username, password_encrypted, use_ssl, enabled, org_id)
            VALUES (:name, :email_address, :imap_server, :imap_port,
                :smtp_server, :smtp_port, :username, :password_encrypted, :use_ssl, :enabled, :org_id)
        """),
        {
            "name": name,
            "email_address": email_address,
            "imap_server": imap_server,
            "imap_port": imap_port,
            "smtp_server": smtp_server,
            "smtp_port": smtp_port,
            "username": username,
            "password_encrypted": password_encrypted,
            "use_ssl": use_ssl,
            "enabled": enabled,
            "org_id": org_id_for_insert,
        }
    )
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/emails/accounts", status_code=302)

@router.post("/accounts/{account_id}/delete")
async def delete_account(account_id: int, request: Request, db: Session = Depends(get_db)):
    user, blocked = require_email_access_api(request, db)
    if blocked is not None:
        return blocked

    # Sentinela T2: cross-tenant IDOR fix — only allow deleting accounts that
    # belong to the current tenant (or legacy rows where org_id is NULL).
    org_id = getattr(request.state, "org_id", None)
    db.execute(
        text(
            "DELETE FROM email_accounts "
            "WHERE id = :id AND (org_id = :org_id OR org_id IS NULL)"
        ),
        {"id": account_id, "org_id": org_id},
    )
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/emails/accounts", status_code=302)


# ============================================
# EMAIL MESSAGE OPERATIONS
# ============================================

@router.get("/{message_id}", response_class=HTMLResponse)
async def view_email(request: Request, message_id: int, db: Session = Depends(get_db)):
    """View a single email"""
    # Gestor-only gate: non-managers get the "request access" screen.
    user, blocked = require_email_access(request, db)
    if blocked is not None:
        return blocked

    # Sentinela T2: every email_messages access MUST scope by org_id.
    org_id = getattr(request.state, "org_id", None)
    if org_id is None:
        raise HTTPException(status_code=403, detail="No tenant context")

    result = db.execute(
        text("""
            SELECT em.*, ea.email_address as account_email, c.first_name, c.last_name, ca.case_name
            FROM email_messages em
            LEFT JOIN email_accounts ea ON em.account_id = ea.id
            LEFT JOIN clients c ON em.client_id = c.id
            LEFT JOIN cases ca ON em.case_id = ca.id
            WHERE em.id = :id AND em.org_id = :org_id
        """),
        {"id": message_id, "org_id": org_id}
    )
    email_msg = result.fetchone()

    if not email_msg:
        raise HTTPException(status_code=404, detail="Email not found")

    # Get attachments (joined through the already-scoped email_messages row).
    result = db.execute(
        text(
            "SELECT ea.* FROM email_attachments ea "
            "JOIN email_messages em ON em.id = ea.message_id "
            "WHERE ea.message_id = :message_id AND em.org_id = :org_id"
        ),
        {"message_id": message_id, "org_id": org_id}
    )
    attachments = result.fetchall()

    # Get clients for linking dropdown
    clients = tenant_query(db, Client, request.state.org_id).filter(or_(Client.status == None, Client.status != 'deleted')).order_by(Client.first_name).all()

    # Get cases for linking dropdown
    cases = tenant_query(db, Case, request.state.org_id).order_by(Case.created_at.desc()).limit(100).all()

    # Get conversation thread - emails with same sender or recipient (same tenant).
    sender_email = email_msg.sender.split('<')[-1].replace('>', '').strip() if email_msg.sender else ''
    thread_result = db.execute(
        text("""
            SELECT id, subject, sender, received_at, is_read,
                   SUBSTRING(body_text, 1, 100) as preview
            FROM email_messages
            WHERE org_id = :org_id
              AND (sender LIKE :sender_pattern OR recipients LIKE :sender_pattern)
              AND LOWER(COALESCE(subject,'')) NOT LIKE 'automatic reply%'
            ORDER BY received_at ASC
            LIMIT 20
        """),
        {"sender_pattern": f"%{sender_email}%", "org_id": org_id}
    )
    thread_emails = thread_result.fetchall()

    # Mark as read (scoped).
    db.execute(
        text("UPDATE email_messages SET is_read = true WHERE id = :id AND org_id = :org_id"),
        {"id": message_id, "org_id": org_id},
    )
    db.commit()

    return templates.TemplateResponse("app/emails/view.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        **inject_org_context(request, user),
        "email": email_msg,
        "attachments": attachments,
        "clients": clients,
        "cases": cases,
        "thread_emails": thread_emails
    }, headers={
        # Revalida o HTML a cada acesso → o navegador sempre busca a CSS/JS na
        # versão atual. Mata a defasagem em que o iOS servia a tela antiga do cache.
        "Cache-Control": "no-cache, must-revalidate",
    })

@router.post("/{message_id}/link")
async def link_email(
    message_id: int,
    request: Request,
    client_id: str = Form(None),
    case_id: str = Form(None),
    db: Session = Depends(get_db)
):
    """Link email to a client profile"""
    user, blocked = require_email_access_api(request, db)
    if blocked is not None:
        return blocked

    # Convert form strings to proper types
    client_id = form_int(client_id)
    case_id = form_int(case_id)

    # Sentinela T2: confine the UPDATE to the current tenant.
    org_id = getattr(request.state, "org_id", None)
    if org_id is None:
        return JSONResponse({"success": False, "error": "No tenant context"}, status_code=403)

    try:
        result = db.execute(
            text(
                "UPDATE email_messages "
                "SET client_id = :client_id, case_id = :case_id "
                "WHERE id = :id AND org_id = :org_id"
            ),
            {"id": message_id, "client_id": client_id, "case_id": case_id, "org_id": org_id},
        )
        db.commit()
        if getattr(result, "rowcount", 0) == 0:
            return JSONResponse({"success": False, "error": "Email not found"}, status_code=404)
        return JSONResponse({"success": True, "client_id": client_id, "message_id": message_id})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/quick-create-client")
async def quick_create_client(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(None),
    phone: str = Form(None),
    country_of_origin: str = Form(None),
    status: str = Form("lead"),
    db: Session = Depends(get_db)
):
    """Quick create a new client from email link modal"""
    user, blocked = require_email_access_api(request, db)
    if blocked is not None:
        return blocked

    try:
        # Check if client with same email already exists
        if email:
            existing = db.execute(
                text("SELECT id, first_name, last_name FROM clients WHERE email = :email"),
                {"email": email}
            ).fetchone()
            if existing:
                return JSONResponse({
                    "success": False,
                    "error": f"Client with email {email} already exists: {existing.first_name} {existing.last_name}",
                    "existing_client_id": existing.id
                })

        # Create new client
        result = db.execute(
            text("""
                INSERT INTO clients (first_name, last_name, email, phone, country_of_origin, status, created_at)
                VALUES (:first_name, :last_name, :email, :phone, :country_of_origin, :status, NOW())
                RETURNING id
            """),
            {
                "first_name": first_name,
                "last_name": last_name,
                "email": email if email else None,
                "phone": phone if phone else None,
                "country_of_origin": country_of_origin if country_of_origin else None,
                "status": status
            }
        )
        client_id = result.fetchone()[0]
        db.commit()

        return JSONResponse({
            "success": True,
            "client_id": client_id,
            "message": f"Client {first_name} {last_name} created successfully"
        })
    except Exception as e:
        db.rollback()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/auto-link")
async def auto_link_emails(
    request: Request,
    db: Session = Depends(get_db)
):
    """Auto-link all unlinked emails to clients using AI matching"""
    user, blocked = require_email_access_api(request, db)
    if blocked is not None:
        return blocked

    try:
        from services.smart_linker import get_smart_linker
        linker = get_smart_linker(db)
        results = await linker.auto_link_all_unlinked()

        return JSONResponse({
            "success": True,
            "total_unlinked": results["total_unlinked"],
            "linked_count": len(results["linked"]),
            "not_linked_count": results["not_linked"],
            "linked": results["linked"],
            "errors": results["errors"]
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ============================================
# PARALEGAL MAPPING FOR VISUAL INTEGRATION
# ============================================

def get_paralegal_mapping():
    """
    Load paralegal mapping from active-clients.json
    Returns dict: {email: paralegal_key}
    """
    try:
        active_clients_path = os.path.join(settings.BASE_DIR, '..', 'whatsapp-bot', 'client-followup', 'active-clients.json')
        with open(active_clients_path) as f:
            data = json.load(f)
            mapping = {}
            for client in data.get('clients', []):
                if client.get('email'):
                    email = client['email'].lower().strip()
                    paralegal = (client.get('paralegal') or '').lower()
                    if 'member_a' in paralegal or 'membro a' in paralegal:
                        mapping[email] = 'member_a'
                    elif 'member_b' in paralegal or 'membro b' in paralegal:
                        mapping[email] = 'member_b'
                    elif 'member_c' in paralegal or 'membro c' in paralegal:
                        mapping[email] = 'member_c'
                    elif 'member_d' in paralegal or 'membro d' in paralegal:
                        mapping[email] = 'member_d'
            return mapping
    except Exception as e:
        logger.error("Error loading paralegal mapping: %s", e)
        return {}


def get_domain_tag(sender: str) -> str:
    """
    Return domain tag based on sender email using PARTNER_DOMAINS config.
    Used for visual differentiation in email list.

    PARTNER_DOMAINS format: "iasuk.org,iasuk.co.uk:ias,ashoorilaw.com:ashoori"
    Each entry is "domain:tag" (tag defaults to domain prefix if omitted).
    """
    if not sender:
        return ""
    sender_lower = sender.lower()
    partner_domains = settings.PARTNER_DOMAINS
    if not partner_domains:
        return ""
    for entry in partner_domains.split(","):
        entry = entry.strip()
        if ":" in entry:
            domain, tag = entry.split(":", 1)
        else:
            domain = entry
            tag = domain.split(".")[0]
        if f"@{domain.lower()}" in sender_lower:
            return tag
    return ""
