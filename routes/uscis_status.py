"""
CaseHub - USCIS Status Routes
Check case status directly from USCIS
"""
import logging
from core.form_utils import form_int, form_float
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

logger = logging.getLogger(__name__)
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, Case
from auth import get_current_user
from models.tenant import tenant_query
from i18n import get_translations
from services.uscis_status import USCISStatusChecker

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/uscis-status", tags=["uscis-status"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py
checker = USCISStatusChecker()


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


@router.get("", response_class=HTMLResponse)
async def uscis_status_page(request: Request, db: Session = Depends(get_db)):
    """USCIS status checker page."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Get cases with receipt numbers
    try:
        cases_with_receipts = tenant_query(db, Case, request.state.org_id).filter(
            Case.receipt_number.isnot(None),
            Case.receipt_number != ""
        ).order_by(Case.created_at.desc()).all()
    except Exception as e:
        db.rollback()
        cases_with_receipts = []

    # Get recent status checks
    recent_checks = []
    try:
        result = db.execute(text("""
            SELECT * FROM uscis_status_checks
            ORDER BY checked_at DESC
            LIMIT 20
        """))
        recent_checks = result.fetchall()
    except Exception as e:
        db.rollback()

    return templates.TemplateResponse("app/uscis_status/index.html", {
        **get_context(request, db),
        "cases_with_receipts": cases_with_receipts,
        "recent_checks": recent_checks
    })


@router.post("/check")
async def check_uscis_status(
    request: Request,
    receipt_number: str = Form(...),
    case_id: str = Form(None),
    db: Session = Depends(get_db)
):
    """Check status and optionally update case."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # Convert form strings to proper types
    case_id = form_int(case_id)

    # Check status
    result = checker.check_status(receipt_number)

    # Log the check
    try:
        db.execute(text("""
            INSERT INTO uscis_status_checks
            (receipt_number, case_id, user_id, status_title, status_details, internal_status, checked_at, success)
            VALUES (:receipt, :case_id, :user_id, :title, :details, :internal, NOW(), :success)
        """), {
            "receipt": receipt_number,
            "case_id": case_id if case_id else None,
            "user_id": user.id,
            "title": result.get("status_title", ""),
            "details": result.get("status_details", "")[:1000] if result.get("status_details") else "",
            "internal": result.get("internal_status", ""),
            "success": result.get("success", False)
        })

        # Update case if requested and status changed
        if case_id and result.get("success"):
            case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
            if case:
                internal_status = result.get("internal_status")
                if internal_status in ["approved", "denied", "rfe"]:
                    case.status = internal_status

        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Error logging USCIS check: %s", e)

    return JSONResponse(result)


@router.get("/api/check/{receipt_number}")
async def api_check_status(receipt_number: str, db: Session = Depends(get_db)):
    """API endpoint to check status."""
    result = checker.check_status(receipt_number)
    return JSONResponse(result)


@router.post("/bulk-check")
async def bulk_check_status(request: Request, db: Session = Depends(get_db)):
    """Check status for all cases with receipt numbers."""
    user = get_current_user(request, db)
    if not user or user.user_type != "admin":
        return JSONResponse({"error": "Admin access required"}, status_code=403)

    try:
        cases = tenant_query(db, Case, request.state.org_id).filter(
            Case.receipt_number.isnot(None),
            Case.receipt_number != "",
            Case.status.notin_(["approved", "denied", "closed"])
        ).all()
    except Exception as e:
        db.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)

    results = []
    for case in cases:
        result = checker.check_status(case.receipt_number)
        result["case_id"] = case.id
        result["case_name"] = case.case_name or case.case_number
        results.append(result)

        # Update case if status changed
        if result.get("success"):
            internal_status = result.get("internal_status")
            if internal_status in ["approved", "denied", "rfe"] and case.status != internal_status:
                case.status = internal_status

    try:
        db.commit()
    except Exception as e:
        db.rollback()

    return JSONResponse({
        "checked": len(results),
        "results": results
    })
