"""
CaseHub - Alerts Routes
Document expiration alerts and notifications.
"""
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, User
from auth import get_current_user
from services.alerts_service import alerts_service, CREATE_ALERTS_TABLE

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/alerts", tags=["alerts"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py


def ensure_tables(db: Session):
    """Ensure alerts tables exist."""
    try:
        db.execute(text(CREATE_ALERTS_TABLE))
        db.commit()
    except Exception as e:
        db.rollback()


def _redirect_to_alerts_tab(tab: str, **params):
    """Send legacy deep links to the consolidated alerts dashboard."""
    redirect_params = {"tab": tab}
    redirect_params.update({k: v for k, v in params.items() if v is not None})
    return RedirectResponse(url=f"{PREFIX}/alerts?{urlencode(redirect_params)}", status_code=302)


@router.get("", response_class=HTMLResponse)
async def alerts_dashboard(
    request: Request,
    tab: Optional[str] = "expiring",
    db: Session = Depends(get_db)
):
    """Alerts dashboard showing all alerts."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    org_id = getattr(request.state, "org_id", None)
    # Get alerts summary
    summary = alerts_service.get_alerts_summary(db, org_id)

    # Get detailed list based on tab
    if tab == "expiring":
        items = alerts_service.get_expiring_documents(db, 90, org_id)
    elif tab == "expired":
        items = alerts_service.get_expired_documents(db, org_id)
    elif tab == "deadlines":
        items = alerts_service.get_upcoming_deadlines(db, 30, org_id)
    elif tab == "tasks":
        items = alerts_service.get_overdue_tasks(db, org_id)
    else:
        items = []

    return templates.TemplateResponse("app/alerts/dashboard.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "summary": summary,
        "items": items,
        "active_tab": tab
    })


@router.get("/expiring-documents", response_class=HTMLResponse)
async def expiring_documents(
    request: Request,
    days: int = 90,
    db: Session = Depends(get_db)
):
    """View all expiring documents."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    return _redirect_to_alerts_tab("expiring", days=days)


@router.get("/expired-documents", response_class=HTMLResponse)
async def expired_documents(request: Request, db: Session = Depends(get_db)):
    """View all expired documents."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    return _redirect_to_alerts_tab("expired")


@router.get("/deadlines", response_class=HTMLResponse)
async def upcoming_deadlines(
    request: Request,
    days: int = 30,
    db: Session = Depends(get_db)
):
    """View upcoming case deadlines."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    return _redirect_to_alerts_tab("deadlines", days=days)


@router.get("/overdue-tasks", response_class=HTMLResponse)
async def overdue_tasks(request: Request, db: Session = Depends(get_db)):
    """View overdue tasks."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    return _redirect_to_alerts_tab("tasks")


@router.get("/api/summary", response_class=JSONResponse)
async def api_alerts_summary(request: Request, db: Session = Depends(get_db)):
    """API: Get alerts summary for dashboard widget."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})

    summary = alerts_service.get_alerts_summary(db)
    return JSONResponse(content=summary)


@router.get("/api/expiring/{days}", response_class=JSONResponse)
async def api_expiring_documents(
    request: Request,
    days: int,
    db: Session = Depends(get_db)
):
    """API: Get expiring documents."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})

    documents = alerts_service.get_expiring_documents(db, days)
    return JSONResponse(content=documents)


@router.get("/api/count", response_class=JSONResponse)
async def api_alerts_count(request: Request, db: Session = Depends(get_db)):
    """API: Get total alerts count for navbar badge."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})

    summary = alerts_service.get_alerts_summary(db)
    total = summary["priority_counts"]["total"]

    return JSONResponse(content={
        "total": total,
        "critical": summary["priority_counts"]["critical"],
        "high": summary["priority_counts"]["high"]
    })
