"""
CaseHub - Hub Tabs Routes
CRUD for user/org tab configurations (browser-within-browser).
"""
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from models import get_db, User
from auth import get_current_user
from models.tenant import Organization, tenant_query

router = APIRouter(prefix="/api/hub", tags=["hub-tabs"])


def _get_user_or_401(request: Request, db: Session) -> User:
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@router.get("/tabs")
async def get_user_tabs(request: Request, db: Session = Depends(get_db)):
    """Get saved tabs for the current user."""
    user = _get_user_or_401(request, db)

    # User tabs stored in user settings JSON or separate field
    # For now, use org_id scoped approach via Organization.settings
    org = db.query(Organization).filter(Organization.id == request.state.org_id).first()

    user_tabs = []
    if org and org.settings and "hub_tabs" in org.settings:
        user_tabs = org.settings["hub_tabs"]

    return JSONResponse({"tabs": user_tabs})


@router.post("/tabs")
async def save_user_tabs(request: Request, db: Session = Depends(get_db)):
    """Save/update tabs for the current user."""
    user = _get_user_or_401(request, db)
    body = await request.json()

    tabs = body.get("tabs", [])

    # Validate each tab
    for tab in tabs:
        if not tab.get("url") or not tab.get("title"):
            raise HTTPException(status_code=400, detail="Each tab must have url and title")

    # Store in org settings (shared across org users for now)
    org = db.query(Organization).filter(Organization.id == request.state.org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    settings = dict(org.settings) if org.settings else {}
    settings["hub_tabs"] = tabs
    org.settings = settings
    db.commit()

    return JSONResponse({"status": "ok", "tabs": tabs})


@router.delete("/tabs/{tab_index}")
async def delete_tab(tab_index: int, request: Request, db: Session = Depends(get_db)):
    """Delete a specific tab by index."""
    user = _get_user_or_401(request, db)

    org = db.query(Organization).filter(Organization.id == request.state.org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    settings = dict(org.settings) if org.settings else {}
    tabs = settings.get("hub_tabs", [])

    if tab_index < 0 or tab_index >= len(tabs):
        raise HTTPException(status_code=404, detail="Tab not found")

    tabs.pop(tab_index)
    settings["hub_tabs"] = tabs
    org.settings = settings
    db.commit()

    return JSONResponse({"status": "ok", "tabs": tabs})


@router.get("/org-tabs")
async def get_org_tabs(request: Request, db: Session = Depends(get_db)):
    """Get org-wide pinned tabs (configured by admin)."""
    user = _get_user_or_401(request, db)

    org = db.query(Organization).filter(Organization.id == request.state.org_id).first()
    if not org:
        return JSONResponse({"tabs": []})

    settings = org.settings or {}
    pinned = settings.get("pinned_tabs", [])

    return JSONResponse({"tabs": pinned})


@router.post("/org-tabs")
async def save_org_tabs(request: Request, db: Session = Depends(get_db)):
    """Save org-wide pinned tabs (admin only)."""
    user = _get_user_or_401(request, db)
    if user.user_type not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Admin only")

    body = await request.json()
    tabs = body.get("tabs", [])

    for tab in tabs:
        if not tab.get("url") or not tab.get("title"):
            raise HTTPException(status_code=400, detail="Each tab must have url and title")

    org = db.query(Organization).filter(Organization.id == request.state.org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    settings = dict(org.settings) if org.settings else {}
    settings["pinned_tabs"] = tabs
    org.settings = settings
    db.commit()

    return JSONResponse({"status": "ok", "tabs": tabs})
