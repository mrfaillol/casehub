"""
CaseHub - Two-Factor Authentication Routes
Setup and manage 2FA for users
"""
import logging

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from models import get_db, User
from auth import get_current_user
from i18n import get_translations
from services.two_factor import TwoFactorService
from config import settings
from core.stepup import (
    STEPUP_COOKIE_NAME,
    STEPUP_TTL_SECONDS,
    issue_token,
)

# PREFIX = "/casehub"  # Imported from template_config.py

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/2fa", tags=["two-factor"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py


def get_context(request: Request, db: Session, **kwargs):
    """Build template context."""
    lang = request.cookies.get("lang", "en")
    user = get_current_user(request, db)
    return {
        "request": request,
        "PREFIX": PREFIX,
        "lang": lang,
        "t": get_translations(lang),
        "user": user,
        **kwargs
    }


def unavailable_status():
    return {
        "enabled": False,
        "setup_at": None,
        "verified_at": None,
        "backup_codes_remaining": 0,
        "unavailable": True,
    }


def unavailable_response(db: Session):
    db.rollback()
    return JSONResponse({
        "success": False,
        "error": "Two-factor authentication is temporarily unavailable."
    }, status_code=503)


@router.get("/setup", response_class=HTMLResponse)
async def setup_2fa_page(request: Request, db: Session = Depends(get_db)):
    """2FA setup page."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    service = TwoFactorService(db)
    try:
        status = service.get_2fa_status(user.id)
    except SQLAlchemyError as exc:
        logger.warning("2FA status unavailable for user %s: %s", user.id, exc)
        db.rollback()
        status = unavailable_status()

    return templates.TemplateResponse("app/two_factor/setup.html", {
        **get_context(request, db),
        "status": status
    })


@router.post("/setup/generate")
async def generate_2fa_secret(request: Request, db: Session = Depends(get_db)):
    """Generate new 2FA secret and QR code."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = TwoFactorService(db)
    try:
        result = service.generate_secret(user.id)
    except SQLAlchemyError as exc:
        logger.warning("2FA secret generation unavailable for user %s: %s", user.id, exc)
        return unavailable_response(db)
    
    return JSONResponse(result)


@router.post("/setup/verify")
async def verify_and_enable_2fa(
    request: Request,
    code: str = Form(...),
    db: Session = Depends(get_db)
):
    """Verify code and enable 2FA."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = TwoFactorService(db)
    try:
        result = service.verify_and_enable(user.id, code)
    except SQLAlchemyError as exc:
        logger.warning("2FA verification unavailable for user %s: %s", user.id, exc)
        return unavailable_response(db)
    
    if not result.get("success"):
        return JSONResponse(result, status_code=400)
    
    return JSONResponse(result)


@router.post("/disable")
async def disable_2fa(
    request: Request,
    code: str = Form(...),
    db: Session = Depends(get_db)
):
    """Disable 2FA (requires valid code)."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = TwoFactorService(db)
    try:
        result = service.disable_2fa(user.id, code)
    except SQLAlchemyError as exc:
        logger.warning("2FA disable unavailable for user %s: %s", user.id, exc)
        return unavailable_response(db)
    
    if not result.get("success"):
        return JSONResponse(result, status_code=400)
    
    return JSONResponse(result)


@router.get("/status")
async def get_2fa_status(request: Request, db: Session = Depends(get_db)):
    """Get current 2FA status."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = TwoFactorService(db)
    try:
        status = service.get_2fa_status(user.id)
    except SQLAlchemyError as exc:
        logger.warning("2FA status API unavailable for user %s: %s", user.id, exc)
        return unavailable_response(db)
    
    return JSONResponse(status)


@router.post("/regenerate-backup-codes")
async def regenerate_backup_codes(
    request: Request,
    code: str = Form(...),
    db: Session = Depends(get_db)
):
    """Regenerate backup codes (requires valid 2FA code)."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = TwoFactorService(db)
    
    # Verify current code first
    try:
        valid_code = service.verify_code(user.id, code)
    except SQLAlchemyError as exc:
        logger.warning("2FA backup code regeneration unavailable for user %s: %s", user.id, exc)
        return unavailable_response(db)

    if not valid_code:
        return JSONResponse({"success": False, "error": "Invalid verification code"}, status_code=400)
    
    # Generate new backup codes
    try:
        codes = service._generate_backup_codes(user.id)
    except SQLAlchemyError as exc:
        logger.warning("2FA backup code generation unavailable for user %s: %s", user.id, exc)
        return unavailable_response(db)
    
    return JSONResponse({
        "success": True,
        "backup_codes": codes
    })


# =========================================================================
# Step-up verification (T10 / #805, CWE-308)
#
# Proves a FRESH TOTP verification at the moment of a sensitive superadmin
# action. On success we set a short-lived, signed, user-bound cookie
# (core.stepup). routes.superadmin.enforce_superadmin_2fa requires that cookie
# when the default-OFF flag is ON.
#
# SAFETY: these two endpoints must NEVER be gated by enforce_superadmin_2fa
# (that would be a chicken-and-egg lockout: you'd need step-up to reach the
# page that grants step-up). They only require a logged-in user.
# =========================================================================

def _stepup_cookie_kwargs() -> dict:
    """Cookie flags for the step-up marker.

    Mirrors the existing auth cookies in core/app_factory.py (HttpOnly + SameSite
    lax + path=/). ``Secure`` is added in non-DEBUG (prod over HTTPS) but left
    off under DEBUG so local HTTP dev still works.
    """
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": not settings.DEBUG,
        "max_age": STEPUP_TTL_SECONDS,
        "path": "/",
    }


@router.get("/step-up", response_class=HTMLResponse)
async def step_up_challenge_page(request: Request, db: Session = Depends(get_db)):
    """Render the step-up TOTP challenge form.

    ``next`` carries the original sensitive URL to bounce back to after a
    successful verification (validated to be a local path to avoid open-redirect).
    """
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    next_url = request.query_params.get("next", "")
    # Open-redirect guard: only allow same-app relative paths.
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = f"{PREFIX}/superadmin"

    return templates.TemplateResponse("app/two_factor/step_up.html", {
        **get_context(request, db),
        "next_url": next_url,
    })


@router.post("/step-up")
async def step_up_verify(
    request: Request,
    code: str = Form(...),
    next: str = Form(""),
    db: Session = Depends(get_db),
):
    """Validate a TOTP ``code`` and, on success, set the signed step-up cookie."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = TwoFactorService(db)
    try:
        valid = service.verify_code(user.id, code)
    except SQLAlchemyError as exc:
        logger.warning("2FA step-up unavailable for user %s: %s", user.id, exc)
        return unavailable_response(db)

    if not valid:
        return JSONResponse(
            {"success": False, "error": "Invalid verification code"},
            status_code=400,
        )

    # Open-redirect guard (same as the GET page).
    next_url = next if (next.startswith("/") and not next.startswith("//")) else f"{PREFIX}/superadmin"

    response = RedirectResponse(url=next_url, status_code=302)
    response.set_cookie(
        key=STEPUP_COOKIE_NAME,
        value=issue_token(user.id),
        **_stepup_cookie_kwargs(),
    )
    logger.info("Superadmin step-up 2FA verified for user id=%s", user.id)
    return response
