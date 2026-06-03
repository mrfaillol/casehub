"""
CaseHub - User Theme API
Switch between UI themes. Lite defaults to neuromorphic Basic.
"""
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from auth import get_current_user
from models import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user", tags=["user_theme"])

VALID_THEMES = {"glass", "neuromorphic", "desktop"}


@router.get("/theme", response_class=JSONResponse)
async def get_theme(request: Request, db: Session = Depends(get_db)):
    """Get current user's UI theme preference."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    return JSONResponse(content={"theme": user.ui_theme or "neuromorphic"})


@router.post("/theme", response_class=JSONResponse)
async def set_theme(request: Request, db: Session = Depends(get_db)):
    """Set user's UI theme preference."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    theme = body.get("theme", "").strip().lower()
    if theme not in VALID_THEMES:
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid theme. Must be one of: {', '.join(sorted(VALID_THEMES))}"}
        )

    user.ui_theme = theme
    db.commit()

    logger.info("User %s switched theme to %s", user.email, theme)
    return JSONResponse(content={"theme": theme})
