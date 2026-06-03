"""
CaseHub - Visual Component Editor (Design System Playground)
Admin-only page for previewing, editing, and exporting UI components.
"""
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db
from auth import get_current_user
from core.template_config import templates, PREFIX
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/design-editor", tags=["design_editor"])

SNIPPETS_DIR = Path(settings.BASE_DIR) / "static" / "design-system-snippets"

VALID_CATEGORIES = {
    "tokens", "surfaces", "buttons", "forms",
    "navigation", "feedback", "data",
}


def require_admin(request: Request, db: Session):
    """Require authenticated admin user."""
    user = get_current_user(request, db)
    if not user or user.user_type != "admin":
        return None
    return user


@router.get("", response_class=HTMLResponse)
async def design_editor_page(request: Request, db: Session = Depends(get_db)):
    """Render the visual component editor."""
    user = require_admin(request, db)
    if not user:
        return HTMLResponse(status_code=302, headers={"Location": f"{PREFIX}/login"})

    return templates.TemplateResponse("app/admin/design_editor.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
    })


@router.get("/snippets/{category}", response_class=HTMLResponse)
async def get_snippet(request: Request, category: str, db: Session = Depends(get_db)):
    """Serve a design-system snippet HTML file."""
    user = require_admin(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=404, detail="Category not found")

    snippet_path = SNIPPETS_DIR / f"{category}.html"
    if not snippet_path.exists():
        raise HTTPException(status_code=404, detail="Snippet file not found")

    return HTMLResponse(content=snippet_path.read_text(encoding="utf-8"))


@router.get("/tokens", response_class=JSONResponse)
async def get_design_tokens(request: Request, db: Session = Depends(get_db)):
    """Return the current org's design tokens as JSON."""
    user = require_admin(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    org_id = getattr(getattr(request, "state", None), "org_id", None)
    tokens = {}

    if org_id:
        result = db.execute(
            text("SELECT settings, primary_color, secondary_color FROM organizations WHERE id = :id"),
            {"id": org_id},
        ).mappings().first()
        if result:
            tokens["primary_color"] = result.get("primary_color", "#ffffff")
            tokens["secondary_color"] = result.get("secondary_color", "#1a1a1a")
            org_settings = result.get("settings") or {}
            if isinstance(org_settings, str):
                org_settings = json.loads(org_settings)
            tokens.update({
                "accent_color": org_settings.get("accent_color", ""),
                "font_family": org_settings.get("font_family", ""),
                "theme_bg": org_settings.get("theme_bg", "#0f0f0f"),
                "design_tokens": org_settings.get("design_tokens", {}),
            })

    return JSONResponse(content=tokens)


@router.post("/tokens", response_class=JSONResponse)
async def save_design_tokens(request: Request, db: Session = Depends(get_db)):
    """Save customized design tokens to org settings."""
    user = require_admin(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    org_id = getattr(getattr(request, "state", None), "org_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization context")

    body = await request.json()
    design_tokens = body.get("design_tokens", {})

    try:
        db.execute(
            text("""
                UPDATE organizations
                SET settings = COALESCE(settings, '{}'::jsonb) || jsonb_build_object('design_tokens', :tokens::jsonb),
                    updated_at = NOW()
                WHERE id = :org_id
            """),
            {"tokens": json.dumps(design_tokens), "org_id": org_id},
        )
        db.commit()
        logger.info(f"Design tokens saved for org_id={org_id} by user={user.email}")
        return JSONResponse(content={"ok": True})
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving design tokens for org_id={org_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to save tokens")
