"""
Client Portal Admin Routes
Staff-facing management: provision portal access, send emails, batch operations.
Client-facing portal is served by client-intake service (port 8003).
"""
import secrets
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError

from models import get_db, Client, Case
from auth import get_current_user
from models.tenant import tenant_query
from services.notifications import send_email, CC_EMAIL
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portal", tags=["portal"])
PREFIX = settings.PREFIX
PORTAL_BASE_URL = f"{settings.BASE_URL}/intake/portal"


def generate_portal_token() -> str:
    """Generate a secure portal access token."""
    return secrets.token_urlsafe(32)


def get_portal_access(db: Session, client_id: int):
    """Get existing portal access for a client."""
    result = db.execute(text("""
        SELECT * FROM portal_access WHERE client_id = :cid
    """), {"cid": client_id})
    return result.fetchone()


def send_portal_email(client_email: str, client_name: str, portal_link: str, org: dict = None) -> bool:
    """Send portal access email to client. Accepts optional org dict for branding."""
    org_name = (org or {}).get("name") or settings.ORG_NAME
    org_email = (org or {}).get("email") or settings.ORG_EMAIL or settings.SMTP_USER
    primary_color = (org or {}).get("primary_color") or "#2c5aa0"
    secondary_color = (org or {}).get("secondary_color") or "#1a3d6e"
    from datetime import date
    year = date.today().year

    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, {secondary_color} 0%, {primary_color} 100%);
                    padding: 25px; border-radius: 10px 10px 0 0; text-align: center;">
            <h2 style="color: white; margin: 0;">Your Client Portal</h2>
            <p style="color: rgba(255,255,255,0.8); margin: 5px 0 0 0;">{org_name}</p>
        </div>
        <div style="background: #f8f9fa; padding: 25px; border: 1px solid #e9ecef;">
            <p>Dear {client_name},</p>
            <p>Your personal client portal is ready. Use the link below to access your forms and upload documents:</p>
            <div style="text-align: center; margin: 25px 0;">
                <a href="{portal_link}"
                   style="display: inline-block; background: linear-gradient(135deg, {primary_color}, {secondary_color});
                          color: white; padding: 14px 35px; text-decoration: none; border-radius: 25px;
                          font-weight: bold; font-size: 16px;">
                    Access My Portal
                </a>
            </div>
            <p style="color: #666; font-size: 14px;">
                <strong>What you can do:</strong>
            </p>
            <ul style="color: #666; font-size: 14px;">
                <li>Fill out immigration forms and questionnaires</li>
                <li>Upload required documents (passport, certificates, etc.)</li>
                <li>Track the status of your submitted documents</li>
            </ul>
            <p style="color: #666; font-size: 14px;">
                This link is unique to you. Please do not share it with others.
                You can use it anytime &mdash; it does not expire.
            </p>
            <p style="color: #666; font-size: 14px;">
                If you have any questions, reply to this email or contact us at
                <a href="mailto:{org_email}">{org_email}</a>.
            </p>
            <p>Respectfully,<br><strong>{org_name}</strong></p>
        </div>
        <div style="background: #343a40; color: #adb5bd; padding: 15px; text-align: center;
                    border-radius: 0 0 10px 10px; font-size: 12px;">
            <p style="margin: 0;">&copy; {year} {org_name}. All rights reserved. | Powered by CaseHub</p>
        </div>
    </div>
    """
    try:
        result = send_email(
            to_email=client_email,
            subject=f"Your Client Portal - {org_name}",
            html_body=html_body,
            cc=CC_EMAIL
        )
        return result
    except Exception as e:
        logger.error(f"Failed to send portal email to {client_email}: {e}")
        return False


# --- Grant Access ---

@router.post("/grant-access/{client_id}")
async def grant_portal_access(
    request: Request,
    client_id: int,
    send_email_flag: bool = Form(True),
    db: Session = Depends(get_db)
):
    """Grant portal access to a client (creates token + optionally sends email)."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(f"{PREFIX}/login", status_code=302)

    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        return JSONResponse({"error": "Client not found"}, status_code=404)

    # Check if already has access
    existing = get_portal_access(db, client_id)
    if existing:
        portal_link = f"{PORTAL_BASE_URL}/{existing.access_token}"
        # Resend email if requested
        if send_email_flag and client.email:
            client_name = f"{client.first_name} {client.last_name}".strip()
            send_portal_email(client.email, client_name, portal_link)
            db.execute(text("""
                UPDATE portal_access SET email_sent_at = NOW() WHERE client_id = :cid
            """), {"cid": client_id})
            db.commit()
        return RedirectResponse(
            f"{PREFIX}/clients/{client_id}?success=portal_access_resent",
            status_code=302
        )

    # Create new access
    token = generate_portal_token()
    db.execute(text("""
        INSERT INTO portal_access (client_id, access_token, created_by)
        VALUES (:cid, :token, :uid)
    """), {"cid": client_id, "token": token, "uid": user.id})

    portal_link = f"{PORTAL_BASE_URL}/{token}"

    # Send email
    if send_email_flag and client.email:
        client_name = f"{client.first_name} {client.last_name}".strip()
        email_sent = send_portal_email(client.email, client_name, portal_link)
        if email_sent:
            db.execute(text("""
                UPDATE portal_access SET email_sent_at = NOW() WHERE client_id = :cid
            """), {"cid": client_id})

    db.commit()
    logger.info(f"Portal access granted: client_id={client_id}, token={token[:8]}...")

    return RedirectResponse(
        f"{PREFIX}/clients/{client_id}?success=portal_access_created",
        status_code=302
    )


# --- Batch Provision ---

@router.post("/batch-provision")
async def batch_provision_portal(
    request: Request,
    send_emails: bool = Form(False),
    db: Session = Depends(get_db)
):
    """Batch provision portal access for all clients without access."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    # Get clients without portal access who have an email
    result = db.execute(text("""
        SELECT c.id, c.first_name, c.last_name, c.email
        FROM clients c
        LEFT JOIN portal_access pa ON pa.client_id = c.id
        WHERE pa.id IS NULL AND c.email IS NOT NULL AND c.email != ''
        AND c.status = 'active' AND c.org_id = :org_id
    """), {"org_id": request.state.org_id})
    clients_without_access = result.fetchall()

    created = 0
    emails_sent = 0
    errors = []

    for client in clients_without_access:
        try:
            token = generate_portal_token()
            db.execute(text("""
                INSERT INTO portal_access (client_id, access_token, created_by)
                VALUES (:cid, :token, :uid)
            """), {"cid": client.id, "token": token, "uid": user.id})
            created += 1

            if send_emails and client.email:
                portal_link = f"{PORTAL_BASE_URL}/{token}"
                client_name = f"{client.first_name} {client.last_name}".strip()
                if send_portal_email(client.email, client_name, portal_link):
                    db.execute(text("""
                        UPDATE portal_access SET email_sent_at = NOW() WHERE client_id = :cid
                    """), {"cid": client.id})
                    emails_sent += 1
        except Exception as e:
            errors.append(f"Client {client.id}: {str(e)}")

    db.commit()
    logger.info(f"Batch provision: {created} created, {emails_sent} emails sent")

    # Get count of already-existing
    existing_count = db.execute(text("""
        SELECT COUNT(*) FROM portal_access pa
        JOIN clients c ON pa.client_id = c.id
        WHERE c.org_id = :org_id
    """), {"org_id": request.state.org_id}).fetchone()[0]

    return JSONResponse({
        "success": True,
        "created": created,
        "emails_sent": emails_sent,
        "already_existing": existing_count - created,
        "errors": errors
    })


# --- Manage Portal Access ---

@router.get("/manage", response_class=HTMLResponse)
async def manage_portal_access(request: Request, db: Session = Depends(get_db)):
    """List all portal access records for staff management.

    The portal_access table is currently provisioned only on long-lived
    production databases — fresh deploys (e.g. alpha Mumbai 2026-05) do not
    have it because no migration creates it. Querying a missing table on
    Postgres raises ``UndefinedTable`` (``ProgrammingError``) and poisons the
    transaction, turning this route into a 500 family for any caller. Same
    defect class as the whatsapp_lite / emails rollback fixes
    (PRs #551 / #552 / #558).

    This handler degrades gracefully: when the table is absent we roll back
    the session and return an empty result with ``table_missing=true``, so
    the route is safe to expose without enabling the portal feature itself.
    Once a migration creates ``portal_access`` the route will start returning
    real data automatically — no follow-up patch needed here.
    """
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(f"{PREFIX}/login", status_code=302)

    try:
        result = db.execute(text("""
            SELECT pa.*, c.first_name, c.last_name, c.email,
                   u.name as created_by_name
            FROM portal_access pa
            JOIN clients c ON pa.client_id = c.id
            LEFT JOIN users u ON pa.created_by = u.id
            WHERE c.org_id = :org_id
            ORDER BY pa.created_at DESC
        """), {"org_id": request.state.org_id})
        accesses = result.fetchall()
    except (OperationalError, ProgrammingError) as exc:
        # Postgres aborts the transaction on a failed statement — clear it
        # so subsequent ORM queries on this session do not raise
        # PendingRollbackError.
        db.rollback()
        logger.warning(
            "[PORTAL MANAGE] portal_access table unavailable (likely "
            "missing migration on this deploy): %s",
            exc,
        )
        return JSONResponse({
            "total": 0,
            "active": 0,
            "emails_sent": 0,
            "accesses": [],
            "table_missing": True,
        })

    # Count stats
    total = len(accesses)
    active = sum(1 for a in accesses if a.is_active)
    with_email = sum(1 for a in accesses if a.email_sent_at)

    return JSONResponse({
        "total": total,
        "active": active,
        "emails_sent": with_email,
        "accesses": [
            {
                "id": a.id,
                "client_id": a.client_id,
                "client_name": f"{a.first_name} {a.last_name}".strip(),
                "email": a.email,
                "is_active": a.is_active,
                "access_count": a.access_count,
                "last_accessed": a.last_accessed.isoformat() if a.last_accessed else None,
                "email_sent_at": a.email_sent_at.isoformat() if a.email_sent_at else None,
                "portal_link": f"{PORTAL_BASE_URL}/{a.access_token}",
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in accesses
        ]
    })


# --- Revoke/Toggle Access ---

@router.post("/toggle/{client_id}")
async def toggle_portal_access(
    request: Request,
    client_id: int,
    db: Session = Depends(get_db)
):
    """Toggle portal access active/inactive."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    access = get_portal_access(db, client_id)
    if not access:
        return JSONResponse({"error": "No portal access found"}, status_code=404)

    new_status = not access.is_active
    db.execute(text("""
        UPDATE portal_access SET is_active = :active WHERE client_id = :cid
    """), {"active": new_status, "cid": client_id})
    db.commit()

    return JSONResponse({"success": True, "is_active": new_status})


# --- API: Get portal status for a client ---

@router.get("/status/{client_id}")
async def get_portal_status(
    request: Request,
    client_id: int,
    db: Session = Depends(get_db)
):
    """Get portal access status for a client (used by client detail page)."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    access = get_portal_access(db, client_id)
    if not access:
        return JSONResponse({"has_access": False})

    return JSONResponse({
        "has_access": True,
        "is_active": access.is_active,
        "portal_link": f"{PORTAL_BASE_URL}/{access.access_token}",
        "access_count": access.access_count,
        "last_accessed": access.last_accessed.isoformat() if access.last_accessed else None,
        "email_sent_at": access.email_sent_at.isoformat() if access.email_sent_at else None,
    })
