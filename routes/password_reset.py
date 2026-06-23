"""
CaseHub - Password Reset Routes
Forgot-password / reset-password flow with secure token.
"""
import uuid
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, User
from models.password_reset import PasswordResetToken
from core.template_config import templates, PREFIX
from config import settings
from services.audit import log_action

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

TOKEN_EXPIRY_HOURS = 1


def _send_reset_email(to_email: str, reset_url: str, org_id=None, org_name: str = None):
    """Send a password-reset link (best-effort) through the org's transport.

    Routes via the shared EmailService singleton: SMTP when configured,
    otherwise the org's connected Google office account (Gmail API/OAuth) — the
    same channel the welcome e-mail uses. Degrades to a logged failure
    (e.g. 'needs_gmail_consent' / 'no_transport') without ever raising, so the
    caller keeps the enumeration-safe response. (The previous `from send_email
    import send_email` pointed at a module that does not exist — every reset
    silently failed.)
    """
    try:
        from services.email_service import email_service
        result = email_service.send_password_reset(
            to_email=to_email,
            reset_url=reset_url,
            org_name=org_name,
            org_id=org_id,
            expiry_hours=TOKEN_EXPIRY_HOURS,
        )
        if not result.get("success"):
            logger.warning(
                "Password reset e-mail not sent to %s: %s", to_email, result.get("error")
            )
    except Exception as e:
        logger.error("Password reset e-mail crashed for %s: %s", to_email, type(e).__name__)


# -------------------------------------------------------------------------
# Forgot Password
# -------------------------------------------------------------------------
@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse("forgot_password.html", {
        "request": request,
        "PREFIX": PREFIX,
        "org_name": "CaseHub",
        "product": "lite",
    })


@router.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password_submit(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db),
):
    """Generate a reset token and send the email."""
    # Always show the same message to prevent user enumeration
    success_msg = "Se houver uma conta com esse e-mail, enviaremos um link de redefinição."

    user = db.query(User).filter(User.email == email).first()
    if user and user.enabled:
        # Invalidate any existing unused tokens for this user
        db.execute(text("""
            UPDATE password_reset_tokens
            SET used = true
            WHERE user_id = :uid AND used = false
        """), {"uid": user.id})

        # Create new token
        token_str = str(uuid.uuid4())
        expires = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS)
        reset_token = PasswordResetToken(
            user_id=user.id,
            token=token_str,
            expires_at=expires,
        )
        db.add(reset_token)
        db.commit()

        # Build a host-derived reset URL (the tenant subdomain) and send it
        # through the org's transport. Host-derived — never settings.BASE_URL —
        # so a reset requested on tenanta.casehub.legal links back to that
        # exact host instead of a global/blank default.
        scheme = request.url.scheme or "https"
        host = request.headers.get("host") or request.url.netloc
        reset_url = f"{scheme}://{host}{PREFIX}/reset-password/{token_str}"
        org_id = getattr(user, "org_id", None) or getattr(request.state, "org_id", None)
        org_name = getattr(getattr(request.state, "org", None), "name", None)
        _send_reset_email(user.email, reset_url, org_id=org_id, org_name=org_name)

        log_action(
            db=db,
            action="password_reset_requested",
            entity_type="user",
            entity_id=user.id,
            user_id=user.id,
            user_email=user.email,
            description="Password reset requested",
            request=request,
        )

    return templates.TemplateResponse("forgot_password.html", {
        "request": request,
        "PREFIX": PREFIX,
        "org_name": "CaseHub",
        "product": "lite",
        "success": success_msg,
    })


# -------------------------------------------------------------------------
# Reset Password
# -------------------------------------------------------------------------
@router.get("/reset-password/{token}", response_class=HTMLResponse)
async def reset_password_page(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
):
    reset_token = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token == token,
            PasswordResetToken.used == False,
            PasswordResetToken.expires_at > datetime.utcnow(),
        )
        .first()
    )
    if not reset_token:
        return templates.TemplateResponse("reset_password.html", {
            "request": request,
            "PREFIX": PREFIX,
            "org_name": settings.ORG_NAME,
            "error": "This reset link is invalid or has expired. Please request a new one.",
            "token": None,
        })

    return templates.TemplateResponse("reset_password.html", {
        "request": request,
        "PREFIX": PREFIX,
        "org_name": settings.ORG_NAME,
        "token": token,
    })


@router.post("/reset-password/{token}", response_class=HTMLResponse)
async def reset_password_submit(
    request: Request,
    token: str,
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    reset_token = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token == token,
            PasswordResetToken.used == False,
            PasswordResetToken.expires_at > datetime.utcnow(),
        )
        .first()
    )

    if not reset_token:
        return templates.TemplateResponse("reset_password.html", {
            "request": request,
            "PREFIX": PREFIX,
            "org_name": settings.ORG_NAME,
            "error": "This reset link is invalid or has expired. Please request a new one.",
            "token": None,
        })

    if password != password_confirm:
        return templates.TemplateResponse("reset_password.html", {
            "request": request,
            "PREFIX": PREFIX,
            "org_name": settings.ORG_NAME,
            "error": "Passwords do not match.",
            "token": token,
        })

    if len(password) < 8:
        return templates.TemplateResponse("reset_password.html", {
            "request": request,
            "PREFIX": PREFIX,
            "org_name": settings.ORG_NAME,
            "error": "Password must be at least 8 characters.",
            "token": token,
        })

    # Update password
    user = db.query(User).filter(User.id == reset_token.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password_hash = User.hash_password(password)
    user.must_change_password = False
    user.last_password_change = datetime.utcnow()

    # Invalidate the token
    reset_token.used = True
    db.commit()

    log_action(
        db=db,
        action="password_reset_completed",
        entity_type="user",
        entity_id=user.id,
        user_id=user.id,
        user_email=user.email,
        description="Password reset completed via token",
        request=request,
    )

    return templates.TemplateResponse("reset_password.html", {
        "request": request,
        "PREFIX": PREFIX,
        "org_name": settings.ORG_NAME,
        "success": "Your password has been reset. You can now log in.",
        "token": None,
    })
