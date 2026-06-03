"""
CaseHub - Case Archive/Close Routes
Handle closing and archiving of cases with pre-defined reasons.
"""
from typing import Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, User, Case
from auth import get_current_user
from models.tenant import tenant_query
from services.case_archive_service import case_archive_service, CREATE_ARCHIVE_TABLES, ArchiveAction

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/case-archive", tags=["case-archive"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py


def ensure_tables(db: Session):
    """Ensure archive tables exist."""
    try:
        db.execute(text(CREATE_ARCHIVE_TABLES))
        db.commit()
    except Exception as e:
        db.rollback()


@router.get("/close/{case_id}", response_class=HTMLResponse)
async def close_case_form(
    request: Request,
    case_id: int,
    db: Session = Depends(get_db)
):
    """Form to close a case."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    return templates.TemplateResponse("app/cases/close.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "case": case,
        "reasons": case_archive_service.get_close_reasons(),
        "action": "close"
    })


@router.post("/close/{case_id}")
async def close_case(
    request: Request,
    case_id: int,
    reason: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Close a case with reason."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ensure_tables(db)

    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    previous_status = case.status
    reason_label = case_archive_service.get_reason_label(reason, "close")

    try:
        db.execute(text("""
            UPDATE cases 
            SET status = 'closed', closed_at = NOW(), closed_reason = :reason, updated_at = NOW()
            WHERE id = :id
        """), {"id": case_id, "reason": reason})

        db.execute(text("""
            INSERT INTO case_archive_history 
            (case_id, action, reason_id, reason_label, notes, previous_status, new_status, created_by)
            VALUES (:case_id, 'close', :reason, :label, :notes, :prev, 'closed', :uid)
        """), {
            "case_id": case_id,
            "reason": reason,
            "label": reason_label,
            "notes": notes,
            "prev": previous_status,
            "uid": user.id
        })

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/cases/{case_id}?message=Case+closed+successfully", status_code=302)


@router.get("/archive/{case_id}", response_class=HTMLResponse)
async def archive_case_form(
    request: Request,
    case_id: int,
    db: Session = Depends(get_db)
):
    """Form to archive a case."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    return templates.TemplateResponse("app/cases/archive.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "case": case,
        "reasons": case_archive_service.get_archive_reasons(),
        "action": "archive"
    })


@router.post("/archive/{case_id}")
async def archive_case(
    request: Request,
    case_id: int,
    reason: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Archive a case with reason."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ensure_tables(db)

    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    previous_status = case.status
    reason_label = case_archive_service.get_reason_label(reason, "archive")

    try:
        db.execute(text("""
            UPDATE cases 
            SET is_archived = true, archived_at = NOW(), archived_reason = :reason, updated_at = NOW()
            WHERE id = :id
        """), {"id": case_id, "reason": reason})

        db.execute(text("""
            INSERT INTO case_archive_history 
            (case_id, action, reason_id, reason_label, notes, previous_status, new_status, created_by)
            VALUES (:case_id, 'archive', :reason, :label, :notes, :prev, :prev, :uid)
        """), {
            "case_id": case_id,
            "reason": reason,
            "label": reason_label,
            "notes": notes,
            "prev": previous_status,
            "uid": user.id
        })

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/cases/{case_id}?message=Case+archived+successfully", status_code=302)


@router.post("/reopen/{case_id}")
async def reopen_case(
    request: Request,
    case_id: int,
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Reopen a closed or archived case."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ensure_tables(db)

    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    previous_status = case.status

    try:
        db.execute(text("""
            UPDATE cases 
            SET status = 'intake', is_archived = false, closed_at = NULL, 
                closed_reason = NULL, archived_at = NULL, archived_reason = NULL,
                updated_at = NOW()
            WHERE id = :id
        """), {"id": case_id})

        db.execute(text("""
            INSERT INTO case_archive_history 
            (case_id, action, reason_id, reason_label, notes, previous_status, new_status, created_by)
            VALUES (:case_id, 'reopen', NULL, 'Case Reopened', :notes, :prev, 'intake', :uid)
        """), {
            "case_id": case_id,
            "notes": notes,
            "prev": previous_status,
            "uid": user.id
        })

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/cases/{case_id}?message=Case+reopened+successfully", status_code=302)


@router.get("/history/{case_id}", response_class=HTMLResponse)
async def case_archive_history(
    request: Request,
    case_id: int,
    db: Session = Depends(get_db)
):
    """View archive/close history for a case."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    try:
        result = db.execute(text("""
            SELECT h.*, u.name as user_name
            FROM case_archive_history h
            LEFT JOIN users u ON h.created_by = u.id
            WHERE h.case_id = :case_id
              AND h.case_id IN (SELECT id FROM cases WHERE org_id = :org_id)
            ORDER BY h.created_at DESC
        """), {"case_id": case_id, "org_id": request.state.org_id})
        history = result.fetchall()
    except Exception as e:
        logger.error("Failed to fetch archive history for case %s: %s", case_id, e)
        history = []

    return templates.TemplateResponse("app/cases/archive_history.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "case": case,
        "history": history
    })


@router.get("/archived", response_class=HTMLResponse)
async def archived_cases(
    request: Request,
    db: Session = Depends(get_db)
):
    """List all archived cases."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    try:
        result = db.execute(text("""
            SELECT c.*, cl.first_name, cl.last_name
            FROM cases c
            LEFT JOIN clients cl ON c.client_id = cl.id
            WHERE c.is_archived = true
            ORDER BY c.archived_at DESC
        """))
        cases = result.fetchall()
    except Exception as e:
        logger.error("Failed to fetch archived cases: %s", e)
        cases = []

    return templates.TemplateResponse("app/cases/archived_list.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "cases": cases,
        "archive_reasons": case_archive_service.get_archive_reasons()
    })


@router.get("/closed", response_class=HTMLResponse)
async def closed_cases(
    request: Request,
    db: Session = Depends(get_db)
):
    """List all closed cases."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    try:
        result = db.execute(text("""
            SELECT c.*, cl.first_name, cl.last_name
            FROM cases c
            LEFT JOIN clients cl ON c.client_id = cl.id
            WHERE c.status = 'closed'
            ORDER BY c.closed_at DESC
        """))
        cases = result.fetchall()
    except Exception as e:
        logger.error("Failed to fetch closed cases: %s", e)
        cases = []

    return templates.TemplateResponse("app/cases/closed_list.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "cases": cases,
        "close_reasons": case_archive_service.get_close_reasons()
    })
