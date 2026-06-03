"""
CaseHub - Email Compose & Send Routes
Handles email composition, sending (with/without attachments),
drafts, templates, and attachment download/preview.
"""
from fastapi import APIRouter, Depends, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
import json
import os
import re
import logging
import html as html_module

logger = logging.getLogger(__name__)

from models import get_db, Client, Case
from auth import get_current_user
from models.tenant import tenant_query
from services.email_service import email_service
from config import settings
from core.template_config import templates, PREFIX, inject_org_context

PREFIX = settings.PREFIX
# Sentinela T11: legacy flat dir kept as read-fallback; writes target per-tenant.
UPLOADS_BASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
UPLOAD_DIR = os.path.join(UPLOADS_BASE, "email_attachments")


def _attachments_dir(org_id) -> str:
    if org_id is None:
        return UPLOAD_DIR
    return os.path.join(UPLOADS_BASE, f"org_{org_id}", "email_attachments")

router = APIRouter(tags=["emails-compose"])


# === COMPOSE AND SEND ROUTES (moved before /{message_id} to avoid conflicts) ===
@router.get("/compose", response_class=HTMLResponse)
async def compose_email(
    request: Request,
    to_email: Optional[str] = None,
    subject: Optional[str] = None,
    client_id: Optional[int] = None,
    case_id: Optional[int] = None,
    reply_to: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Compose a new email"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    client = None
    case = None

    # Handle reply pre-fill
    if reply_to:
        import re
        original = db.execute(text(
            "SELECT sender, subject, cc, recipients FROM email_messages WHERE id = :id AND org_id = :org_id"
        ), {"id": reply_to, "org_id": request.state.org_id}).fetchone()
        if original:
            # Extract email from "Name <email>" format
            match = re.search(r'<([^>]+)>', original.sender)
            to_email = match.group(1) if match else original.sender.strip()
            # Add Re: prefix if not already present
            orig_subject = original.subject or ""
            if not orig_subject.lower().startswith("re:"):
                subject = f"Re: {orig_subject}"
            else:
                subject = orig_subject

    if client_id:
        client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
        if client and not to_email:
            to_email = client.email

    if case_id:
        result = db.execute(text("SELECT * FROM cases WHERE id = :id"), {"id": case_id})
        case = result.fetchone()
        if case and case.client_id and not client:
            client = tenant_query(db, Client, request.state.org_id).filter(Client.id == case.client_id).first()
            if client and not to_email:
                to_email = client.email

    return templates.TemplateResponse("app/emails/compose.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        **inject_org_context(request, user),
        "is_configured": email_service.is_configured(),
        "to_email": to_email,
        "subject": subject,
        "client_id": client_id,
        "case_id": case_id,
        "client": client,
        "case": case
    })




@router.get("/compose-v2", response_class=HTMLResponse)
async def compose_email_v2(
    request: Request,
    to_email: Optional[str] = None,
    subject: Optional[str] = None,
    client_id: Optional[int] = None,
    case_id: Optional[int] = None,
    reply_to: Optional[int] = None,
    forward_from: Optional[int] = None,
    reply_all: Optional[int] = None,
    cc_email: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Enhanced compose email with templates v2"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    client = None
    case = None

    # Handle reply pre-fill
    if reply_to:
        import re
        original = db.execute(text(
            "SELECT sender, subject, cc, recipients FROM email_messages WHERE id = :id AND org_id = :org_id"
        ), {"id": reply_to, "org_id": request.state.org_id}).fetchone()
        if original:
            match = re.search(r'<([^>]+)>', original.sender)
            to_email = match.group(1) if match else original.sender.strip()
            orig_subject = original.subject or ""
            if not orig_subject.lower().startswith("re:"):
                subject = f"Re: {orig_subject}"
            else:
                subject = orig_subject
            # Handle Reply All - add CC recipients
            if reply_all and original.cc:
                cc_email = original.cc

    # Handle forward pre-fill
    if forward_from:
        original = db.execute(text(
            "SELECT subject FROM email_messages WHERE id = :id AND org_id = :org_id"
        ), {"id": forward_from, "org_id": request.state.org_id}).fetchone()
        if original:
            orig_subject = original.subject or ""
            if not orig_subject.lower().startswith("fwd:"):
                subject = f"Fwd: {orig_subject}"
            else:
                subject = orig_subject

    if client_id:
        client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
        if client and not to_email:
            to_email = client.email

    if case_id:
        result = db.execute(text("SELECT * FROM cases WHERE id = :id"), {"id": case_id})
        case = result.fetchone()
        if case and case.client_id and not client:
            client = tenant_query(db, Client, request.state.org_id).filter(Client.id == case.client_id).first()
            if client and not to_email:
                to_email = client.email

    return templates.TemplateResponse("app/emails/compose_v2.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        **inject_org_context(request, user),
        "is_configured": email_service.is_configured(),
        "to_email": to_email,
        "subject": subject,
        "client_id": client_id,
        "case_id": case_id,
        "client": client,
        "case": case,
        "reply_to": reply_to,
        "forward_from": forward_from,
        "cc_email": cc_email
    })


@router.post("/send")
async def send_email(
    request: Request,
    to_email: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    client_id: Optional[int] = Form(None),
    case_id: Optional[int] = Form(None),
    cc_email: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Send an email"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    if not email_service.is_configured():
        return templates.TemplateResponse("app/emails/compose.html", {
            "request": request,
            "user": user,
            "PREFIX": PREFIX,
            **inject_org_context(request, user),
            "is_configured": False,
            "error": "SMTP is not configured. Please configure email settings.",
            "to_email": to_email,
            "subject": subject,
            "body": body
        })

    # Convert plain text to HTML
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .content {{ white-space: pre-wrap; }}
            .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="content">{html_module.escape(body)}</div>
            <div class="footer">
                <p>Sent via CaseHub</p>
                <p>{settings.ORG_NAME} | {settings.ORG_DOMAIN or settings.BASE_URL}</p>
            </div>
        </div>
    </body>
    </html>
    """

    # BCC info@ for tracking if not already a recipient
    bcc_for_tracking = None
    cc_addrs = [e.strip().lower() for e in (cc_email or "").split(",") if e.strip()]
    if email_service.from_email.lower() not in [to_email.lower()] + cc_addrs:
        bcc_for_tracking = email_service.from_email

    result = email_service.send_email(to_email, subject, html_body, body, cc_email=cc_email, bcc_email=bcc_for_tracking)

    if result.get("success"):
        # Log the sent email
        try:
            db.execute(
                text("""
                    INSERT INTO sent_emails (user_id, to_email, subject, body, client_id, case_id, sent_at)
                    VALUES (:user_id, :to_email, :subject, :body, :client_id, :case_id, NOW())
                """),
                {
                    "user_id": user.id,
                    "to_email": to_email,
                    "subject": subject,
                    "body": body,
                    "client_id": client_id,
                    "case_id": case_id
                }
            )
            db.commit()
        except Exception as e:
            # Table might not exist, create it
            try:
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS sent_emails (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER,
                        to_email VARCHAR(300),
                        subject VARCHAR(500),
                        body TEXT,
                        client_id INTEGER,
                        case_id INTEGER,
                        sent_at TIMESTAMP DEFAULT NOW()
                    )
                """))
                db.commit()
                db.execute(
                    text("""
                        INSERT INTO sent_emails (user_id, to_email, subject, body, client_id, case_id, sent_at)
                        VALUES (:user_id, :to_email, :subject, :body, :client_id, :case_id, NOW())
                    """),
                    {
                        "user_id": user.id,
                        "to_email": to_email,
                        "subject": subject,
                        "body": body,
                        "client_id": client_id,
                        "case_id": case_id
                    }
                )
                db.commit()
            except Exception as e:
                logger.error("Failed to log sent email to database: %s", e)

        # Redirect with success message
        return RedirectResponse(url=f"{PREFIX}/emails?sent=1", status_code=302)
    else:
        return templates.TemplateResponse("app/emails/compose.html", {
            "request": request,
            "user": user,
            "PREFIX": PREFIX,
            **inject_org_context(request, user),
            "is_configured": True,
            "error": f"Failed to send email: {result.get('error')}",
            "to_email": to_email,
            "subject": subject,
            "body": body
        })


@router.get("/api/sent")
async def get_sent_emails(
    request: Request,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """Get recently sent emails"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        result = db.execute(
            text("SELECT id, to_email, subject, sent_at FROM sent_emails ORDER BY sent_at DESC LIMIT :limit"),
            {"limit": limit}
        )
        emails = result.fetchall()
        return JSONResponse({
            "emails": [{
                "id": e.id,
                "to_email": e.to_email,
                "subject": e.subject,
                "sent_at": e.sent_at.strftime('%Y-%m-%d %H:%M') if e.sent_at else ''
            } for e in emails]
        })
    except Exception as e:
        logger.error("Failed to search sent emails: %s", e)
        return JSONResponse({"emails": []})


@router.post("/api/send-quick")
async def send_quick_email(
    request: Request,
    db: Session = Depends(get_db)
):
    """Quick send email via API"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    if not email_service.is_configured():
        return JSONResponse({"success": False, "error": "SMTP not configured"})

    try:
        data = await request.json()
        to_email = data.get("to_email")
        subject = data.get("subject")
        body = data.get("body")
        cc_email = data.get("cc_email")

        if not all([to_email, subject, body]):
            return JSONResponse({"success": False, "error": "Missing required fields"})

        # Simple HTML wrapper
        html_body = f"<div style='font-family: Arial, sans-serif; white-space: pre-wrap;'>{html_module.escape(body)}</div>"

        # BCC info@ for tracking if not already a recipient
        bcc_for_tracking = None
        cc_addrs = [e.strip().lower() for e in (cc_email or "").split(",") if e.strip()]
        if email_service.from_email.lower() not in [to_email.lower()] + cc_addrs:
            bcc_for_tracking = email_service.from_email

        result = email_service.send_email(to_email, subject, html_body, body, cc_email=cc_email, bcc_email=bcc_for_tracking)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


# =============================================================================
# COMPOSE V2 AND ATTACHMENTS
# =============================================================================


def markdown_to_email_html(text: str) -> str:
    """Convert markdown-like syntax to email-safe inline HTML."""
    # Escape HTML entities first (XSS protection)
    text = html_module.escape(text)

    # Horizontal rules
    text = re.sub(
        r'^---$',
        '<hr style="border:none;border-top:1px solid #ddd;margin:15px 0;">',
        text, flags=re.MULTILINE
    )

    # Headings: ### text
    text = re.sub(
        r'^### (.+)$',
        r'<h3 style="font-size:16px;font-weight:bold;color:#333;margin:15px 0 8px;">\1</h3>',
        text, flags=re.MULTILINE
    )

    # Bold: **text**
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)

    # Underline: __text__
    text = re.sub(r'__([^_]+)__', r'<u>\1</u>', text)

    # Italic: *text* (after bold to avoid ** conflict)
    text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', text)

    # Links: [text](url) - only http/https for safety
    text = re.sub(
        r'\[([^\]]+)\]\((https?://[^)]+)\)',
        r'<a href="\2" style="color:#0066cc;text-decoration:underline;">\1</a>',
        text
    )

    # Unordered lists: consecutive lines starting with "- "
    def _replace_ul(match):
        items = match.group(0).strip().split('\n')
        li_items = ''.join(
            f'<li style="margin-bottom:4px;">{item.strip()[2:]}</li>'
            for item in items if item.strip()
        )
        return f'<ul style="padding-left:20px;margin:8px 0;">{li_items}</ul>'

    text = re.sub(r'(?:^- .+\n?)+', _replace_ul, text, flags=re.MULTILINE)

    # Ordered lists: consecutive lines starting with "N. "
    def _replace_ol(match):
        items = match.group(0).strip().split('\n')
        li_items = ''.join(
            '<li style="margin-bottom:4px;">{}</li>'.format(re.sub(r'^\d+\.\s*', '', item.strip()))
            for item in items if item.strip()
        )
        return f'<ol style="padding-left:20px;margin:8px 0;">{li_items}</ol>'

    text = re.sub(r'(?:^\d+\. .+\n?)+', _replace_ol, text, flags=re.MULTILINE)

    # Convert remaining newlines to <br>
    text = text.replace('\n', '<br>')
    # Clean up <br> around block elements
    text = re.sub(r'(</(?:h3|ul|ol|li|hr)>)<br>', r'\1', text)
    text = re.sub(r'<br>(<(?:h3|ul|ol|hr))', r'\1', text)

    return text


def markdown_to_plain_text(text: str) -> str:
    """Strip markdown syntax for clean plain text MIME part."""
    # Bold
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    # Italic
    text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'\1', text)
    # Underline
    text = re.sub(r'__([^_]+)__', r'\1', text)
    # Links: [text](url) -> text (url)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', text)
    # Headings: remove ### prefix
    text = re.sub(r'^### ', '', text, flags=re.MULTILINE)
    return text


@router.post("/send-with-attachments")
async def send_email_with_attachments(
    request: Request,
    to_email: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    client_id: Optional[int] = Form(None),
    case_id: Optional[int] = Form(None),
    cc_email: Optional[str] = Form(None),
    bcc_email: Optional[str] = Form(None),
    signature_id: Optional[str] = Form(None),
    attachments: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_db)
):
    """Send an email with attachments"""
    import smtplib
    import ssl
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email import encoders

    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    if not email_service.is_configured():
        return templates.TemplateResponse("app/emails/compose_v2.html", {
            "request": request,
            "user": user,
            "PREFIX": PREFIX,
            **inject_org_context(request, user),
            "is_configured": False,
            "error": "SMTP is not configured.",
            "to_email": to_email,
            "subject": subject,
            "body": body
        })

    try:
        # Build email with attachments
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = f"{email_service.from_name} <{email_service.from_email}>"
        msg["To"] = to_email
        msg["Reply-To"] = to_email

        # CC: only user-specified recipients (NOT info@ which is the FROM sender)
        cc_list = []
        if cc_email:
            cc_list = [e.strip() for e in cc_email.replace(";", ",").split(",") if e.strip()]
            # Strip info@ from CC if user added it manually (avoids Reply All confusion)
            cc_list = [e for e in cc_list if e.lower() != email_service.from_email.lower()]
        if cc_list:
            msg["Cc"] = ", ".join(cc_list)

        # BCC: info@ for tracking + user-specified BCC recipients
        bcc_list = []
        if bcc_email:
            bcc_list = [e.strip() for e in bcc_email.replace(";", ",").split(",") if e.strip()]
        # Add info@ as BCC so shared inbox receives a copy (invisible in headers)
        if email_service.from_email.lower() not in [e.lower() for e in [to_email] + bcc_list]:
            bcc_list.append(email_service.from_email)

        # Get signature if selected
        signature_html = ""
        signature_text = ""
        if signature_id:
            from routes.email_templates_v2 import EMAIL_SIGNATURES
            sig = EMAIL_SIGNATURES.get(signature_id)
            if sig:
                signature_html = sig["html"]
                signature_text = sig["text"]

        # Convert markdown body to email-safe HTML
        body_html_content = markdown_to_email_html(body)
        body_plain_content = markdown_to_plain_text(body)

        html_body = f"""<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <div>{body_html_content}</div>
        {signature_html}
    </div>
</body>
</html>"""

        msg.attach(MIMEText(body_plain_content + signature_text, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        # Process attachments (Sentinela T11: write to tenant-scoped dir)
        org_id_for_upload = getattr(request.state, "org_id", None)
        upload_dir = _attachments_dir(org_id_for_upload)
        os.makedirs(upload_dir, exist_ok=True)
        attachment_info = []
        for attachment in attachments:
            if attachment.filename:
                content = await attachment.read()
                if len(content) > 10 * 1024 * 1024:  # 10MB limit
                    continue

                # Save to disk
                import uuid
                filename = f"{uuid.uuid4()}_{attachment.filename}"
                filepath = os.path.join(upload_dir, filename)
                with open(filepath, "wb") as f:
                    f.write(content)

                # Add to email with proper MIME type
                import mimetypes
                mime_type = mimetypes.guess_type(attachment.filename)[0] or "application/octet-stream"
                maintype, subtype = mime_type.split("/", 1)
                part = MIMEBase(maintype, subtype)
                part.set_payload(content)
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=attachment.filename
                )
                msg.attach(part)
                attachment_info.append({
                    "filename": attachment.filename,
                    "size": len(content),
                    "path": filepath
                })

        # Send email to all recipients (to + cc + bcc)
        all_recipients = [to_email] + cc_list + bcc_list
        context = ssl.create_default_context()
        with smtplib.SMTP(email_service.host, email_service.port) as server:
            server.starttls(context=context)
            server.login(email_service.user, email_service.password)
            server.sendmail(
                email_service.from_email,
                all_recipients,
                msg.as_string()
            )

        # Log the sent email
        try:
            db.execute(
                text("""
                    INSERT INTO sent_emails (user_id, to_email, subject, body, client_id, case_id, sent_at, attachments)
                    VALUES (:user_id, :to_email, :subject, :body, :client_id, :case_id, NOW(), :attachments)
                """),
                {
                    "user_id": user.id,
                    "to_email": to_email,
                    "subject": subject,
                    "body": body,
                    "client_id": client_id,
                    "case_id": case_id,
                    "attachments": json.dumps(attachment_info) if attachment_info else None
                }
            )
            db.commit()
        except Exception as log_err:
            logger.error("Error logging sent email: %s", log_err)
            try:
                db.rollback()
            except Exception as e:
                logger.error("Failed to rollback after email logging error: %s", e)

        return RedirectResponse(url=f"{PREFIX}/emails?sent=1", status_code=302)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return templates.TemplateResponse("app/emails/compose_v2.html", {
            "request": request,
            "user": user,
            "PREFIX": PREFIX,
            **inject_org_context(request, user),
            "is_configured": True,
            "error": f"Failed to send email: {str(e)}",
            "to_email": to_email,
            "subject": subject,
            "body": body
        })


# ========== ATTACHMENT DOWNLOAD/PREVIEW ==========
@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: int,
    request: Request,
    db=Depends(get_db)
):
    """Download an email attachment"""
    from fastapi.responses import FileResponse

    # Sentinela C1: require auth + scope attachment by tenant (org_id) via
    # email_messages join. email_attachments has no org_id column; the tenant
    # link is email_attachments.message_id -> email_messages.org_id.
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    org_id = getattr(request.state, "org_id", None)
    if org_id is None:
        raise HTTPException(status_code=403, detail="No tenant context")

    # Get attachment info (scoped to the caller's tenant)
    result = db.execute(
        text(
            "SELECT ea.* FROM email_attachments ea "
            "JOIN email_messages em ON em.id = ea.message_id "
            "WHERE ea.id = :id AND em.org_id = :org_id"
        ),
        {"id": attachment_id, "org_id": org_id}
    )
    attachment = result.fetchone()

    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    file_path = attachment.file_path

    # Security: ensure path is within uploads directory
    uploads_base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
    full_path = os.path.abspath(file_path if file_path.startswith('/') else os.path.join(uploads_base, file_path))

    if not full_path.startswith(os.path.abspath(uploads_base)):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=full_path,
        filename=attachment.filename,
        media_type=attachment.mime_type or "application/octet-stream"
    )


@router.get("/attachments/{attachment_id}/preview")
async def preview_attachment(
    attachment_id: int,
    request: Request,
    db=Depends(get_db)
):
    """Preview an email attachment inline (for PDFs and images)"""
    from fastapi.responses import FileResponse

    # Sentinela C1: require auth + scope attachment by tenant (org_id) via
    # email_messages join. email_attachments has no org_id column; the tenant
    # link is email_attachments.message_id -> email_messages.org_id.
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    org_id = getattr(request.state, "org_id", None)
    if org_id is None:
        raise HTTPException(status_code=403, detail="No tenant context")

    # Get attachment info (scoped to the caller's tenant)
    result = db.execute(
        text(
            "SELECT ea.* FROM email_attachments ea "
            "JOIN email_messages em ON em.id = ea.message_id "
            "WHERE ea.id = :id AND em.org_id = :org_id"
        ),
        {"id": attachment_id, "org_id": org_id}
    )
    attachment = result.fetchone()

    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    file_path = attachment.file_path

    # Security: ensure path is within uploads directory
    uploads_base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
    full_path = os.path.abspath(file_path if file_path.startswith('/') else os.path.join(uploads_base, file_path))

    if not full_path.startswith(os.path.abspath(uploads_base)):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    # Return with inline disposition for preview
    return FileResponse(
        path=full_path,
        media_type=attachment.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f"inline; filename=\"{attachment.filename}\""}
    )
