"""
CaseHub - Application Settings Routes
Manage numbering formats and other system settings.
"""
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
import json
import logging

logger = logging.getLogger(__name__)

from models import get_db, User
from auth import get_current_user
from services.numbering import NumberingService, CREATE_SETTINGS_TABLE

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/settings", tags=["settings"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py


def ensure_settings_table(db: Session):
    """Ensure the app_settings table exists."""
    try:
        db.execute(text(CREATE_SETTINGS_TABLE))
        db.commit()
    except Exception as e:
        db.rollback()


@router.get("", response_class=HTMLResponse)
async def settings_page(request: Request, db: Session = Depends(get_db)):
    """Main settings page."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    if user.user_type != "admin":
        return RedirectResponse(url=f"{PREFIX}/dashboard", status_code=302)

    ensure_settings_table(db)
    numbering = NumberingService(db)
    numbering_settings = numbering.get_settings()

    return templates.TemplateResponse("app/settings/index.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "numbering": numbering_settings,
        "preview_case": numbering.preview_format(numbering_settings.get("case_format", numbering.DEFAULT_CASE_FORMAT), "case"),
        "preview_client": numbering.preview_format(numbering_settings.get("client_format", numbering.DEFAULT_CLIENT_FORMAT), "client")
    })


@router.get("/numbering", response_class=HTMLResponse)
async def numbering_settings_page(request: Request, db: Session = Depends(get_db)):
    """Numbering settings page."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    if user.user_type != "admin":
        return RedirectResponse(url=f"{PREFIX}/dashboard", status_code=302)

    ensure_settings_table(db)
    numbering = NumberingService(db)
    settings = numbering.get_settings()

    return templates.TemplateResponse("app/settings/numbering.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "settings": settings,
        "preview_case": numbering.preview_format(settings.get("case_format", numbering.DEFAULT_CASE_FORMAT), "case"),
        "preview_client": numbering.preview_format(settings.get("client_format", numbering.DEFAULT_CLIENT_FORMAT), "client")
    })


@router.post("/numbering")
async def save_numbering_settings(
    request: Request,
    case_format: str = Form(...),
    client_format: str = Form(...),
    reset_annually: bool = Form(False),
    reset_case_counter: bool = Form(False),
    reset_client_counter: bool = Form(False),
    db: Session = Depends(get_db)
):
    """Save numbering settings."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    if user.user_type != "admin":
        return RedirectResponse(url=f"{PREFIX}/dashboard", status_code=302)

    ensure_settings_table(db)
    numbering = NumberingService(db)
    settings = numbering.get_settings()

    # Update formats
    settings["case_format"] = case_format
    settings["client_format"] = client_format
    settings["reset_annually"] = reset_annually

    # Reset counters if requested
    if reset_case_counter:
        settings["case_counter"] = 1
    if reset_client_counter:
        settings["client_counter"] = 1

    numbering.save_settings(settings)

    return RedirectResponse(url=f"{PREFIX}/settings/numbering?saved=true", status_code=302)


@router.get("/numbering/preview", response_class=JSONResponse)
async def preview_numbering(
    request: Request,
    format: str,
    type: str = "case",
    db: Session = Depends(get_db)
):
    """API: Preview numbering format."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    ensure_settings_table(db)
    numbering = NumberingService(db)
    preview = numbering.preview_format(format, type)

    return JSONResponse(content={"preview": preview})


@router.get("/api/all", response_class=JSONResponse)
async def get_all_settings(request: Request, db: Session = Depends(get_db)):
    """API: Get all settings."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    ensure_settings_table(db)

    try:
        result = db.execute(text("SELECT config_key, config_value FROM app_settings"))
        rows = result.fetchall()
        settings = {}
        for row in rows:
            try:
                settings[row[0]] = json.loads(row[1])
            except Exception as e:
                logger.error("Failed to parse setting '%s' as JSON: %s", row[0], e)
                settings[row[0]] = row[1]
        return JSONResponse(content=settings)
    except Exception as e:
        return JSONResponse(content={})
