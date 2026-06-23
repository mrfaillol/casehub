"""Work Intelligence routes.

Default-off observability for aggregate workflow friction. The browser endpoint
accepts only sanitized semantic events; admin and MCP endpoints expose summaries,
not raw logs.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from auth import get_current_user
from core.template_config import PREFIX, inject_org_context, templates
from models import get_db
from services import work_intelligence as wi


router = APIRouter(prefix="/work-intelligence", tags=["work-intelligence"])


def _require_user(request: Request, db: Session):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Nao autenticado")
    return user


def _require_admin(user):
    if getattr(user, "user_type", None) not in {"admin", "superadmin"}:
        raise HTTPException(status_code=403, detail="Acesso restrito")


def _org_id(request: Request) -> int:
    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="org_id ausente")
    return int(org_id)


@router.post("/api/events")
async def ingest_client_events(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    org_id = _org_id(request)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    events = payload.get("events") if isinstance(payload, dict) else []
    if not isinstance(events, list):
        events = []
    result = wi.record_client_events(db, org_id=org_id, user=user, events=events)
    return JSONResponse(result)


@router.get("", response_class=HTMLResponse)
async def admin_panel(request: Request, days: int = 7, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    _require_admin(user)
    org_id = _org_id(request)
    summary = wi.build_summary(db, org_id=org_id, days=days, user=user, include_disabled=True)
    org_ctx = inject_org_context(request, user)
    return templates.TemplateResponse(
        "app/work_intelligence/overview.html",
        {
            "request": request,
            "PREFIX": PREFIX,
            "user": user,
            "summary": summary,
            "days": max(1, min(int(days or 7), 31)),
            "active_module": "work-intelligence",
            **org_ctx,
        },
    )


@router.get("/me", response_class=HTMLResponse)
async def my_transparency_page(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    org_id = _org_id(request)
    payload = wi.user_transparency_payload(db, org_id=org_id, user=user)
    org_ctx = inject_org_context(request, user)
    return templates.TemplateResponse(
        "app/work_intelligence/me.html",
        {
            "request": request,
            "PREFIX": PREFIX,
            "user": user,
            "payload": payload,
            "active_module": "work-intelligence",
            **org_ctx,
        },
    )


@router.get("/api/summary")
async def summary_api(request: Request, days: int = 7, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    _require_admin(user)
    org_id = _org_id(request)
    return JSONResponse(wi.mcp_summary_payload(db, org_id=org_id, days=days))


@router.post("/api/backfill-current-week")
async def backfill_current_week(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    _require_admin(user)
    org_id = _org_id(request)
    if not wi.is_work_intelligence_enabled(db, org_id):
        return JSONResponse({"status": "disabled", "stored_days": 0})
    return JSONResponse({"status": "ok", **wi.backfill_current_week(db, org_id=org_id)})


@router.post("/api/feedback")
async def feedback(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    org_id = _org_id(request)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    result = wi.record_feedback(
        db,
        org_id=org_id,
        user_id=getattr(user, "id", None),
        insight_id=payload.get("insight_id") if isinstance(payload, dict) else None,
        feedback_type=(payload.get("feedback_type") if isinstance(payload, dict) else "") or "comment",
        usefulness=payload.get("usefulness") if isinstance(payload, dict) else None,
        comment=(payload.get("comment") if isinstance(payload, dict) else "") or "",
    )
    return JSONResponse(result)
