"""
CaseHub - Referral Management Routes
Track referral sources and manage referral commissions.
"""
import logging
from typing import Optional
from datetime import datetime
from decimal import Decimal

from core.form_utils import form_int, form_float
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.request_utils import get_request_org_id
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, User, Client, Case
from auth import get_current_user
from models.tenant import tenant_query
from services.referral_service import referral_service, CREATE_REFERRAL_TABLE, ReferralStatus

# PREFIX = "/casehub"  # Imported from template_config.py

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/referrals", tags=["referrals"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py


def ensure_tables(db: Session):
    """Ensure referral tables exist."""
    try:
        db.execute(text(CREATE_REFERRAL_TABLE))
        db.commit()
    except Exception as e:
        db.rollback()


@router.get("", response_class=HTMLResponse)
async def referrals_list(
    request: Request,
    source_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all referrals."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    # Build query
    query = """
        SELECT r.*, rs.name as source_name, rs.source_type,
               c.first_name, c.last_name,
               ca.case_number, ca.case_name
        FROM referrals r
        LEFT JOIN referral_sources rs ON r.source_id = rs.id
        LEFT JOIN clients c ON r.client_id = c.id
        LEFT JOIN cases ca ON r.case_id = ca.id
        WHERE r.org_id = :org_id
    """
    params = {"org_id": get_request_org_id(request)}

    if source_id:
        query += " AND r.source_id = :source_id"
        params["source_id"] = source_id

    if status:
        query += " AND r.status = :status"
        params["status"] = status

    query += " ORDER BY r.created_at DESC"

    try:
        result = db.execute(text(query), params)
        referrals = result.fetchall()
    except Exception as e:
        logger.error("Failed to fetch referrals list: %s", e)
        db.rollback()
        referrals = []

    # Get sources for filter
    try:
        sources = db.execute(text("SELECT id, name, source_type FROM referral_sources WHERE org_id = :org_id ORDER BY name"), {"org_id": get_request_org_id(request)}).fetchall()
    except Exception as e:
        logger.error("Failed to fetch referral sources filter: %s", e)
        db.rollback()
        sources = []

    # Get stats
    try:
        stats_result = db.execute(text("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status IN ('converted', 'paid') THEN 1 ELSE 0 END) as converted,
                SUM(case_value) as total_value,
                SUM(commission_amount) as total_commission
            FROM referrals
            WHERE org_id = :org_id
        """), {"org_id": get_request_org_id(request)})
        stats = stats_result.fetchone()
    except Exception as e:
        logger.error("Failed to fetch referral stats: %s", e)
        db.rollback()
        stats = None

    return templates.TemplateResponse("app/referrals/list.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "referrals": referrals,
        "sources": sources,
        "selected_source": source_id,
        "selected_status": status,
        "stats": stats,
        "statuses": [s.value for s in ReferralStatus]
    })


@router.get("/sources", response_class=HTMLResponse)
async def sources_list(
    request: Request,
    db: Session = Depends(get_db)
):
    """List all referral sources."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    try:
        result = db.execute(text("""
            SELECT rs.*,
                   (SELECT COUNT(*) FROM referrals WHERE source_id = rs.id AND org_id = :org_id) as referral_count,
                   (SELECT COUNT(*) FROM referrals WHERE source_id = rs.id AND org_id = :org_id AND status IN ('converted', 'paid')) as converted_count
            FROM referral_sources rs
            WHERE rs.org_id = :org_id
            ORDER BY rs.name
        """), {"org_id": get_request_org_id(request)})
        sources = result.fetchall()
    except Exception as e:
        logger.error("Failed to fetch referral sources list: %s", e)
        db.rollback()
        sources = []

    return templates.TemplateResponse("app/referrals/sources.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "sources": sources,
        "source_types": referral_service.get_referral_sources()
    })


@router.get("/sources/new", response_class=HTMLResponse)
async def new_source(
    request: Request,
    db: Session = Depends(get_db)
):
    """Create new referral source form."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    return templates.TemplateResponse("app/referrals/create_source.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "source_types": referral_service.get_referral_sources()
    })


@router.post("/sources/create")
async def create_source(
    request: Request,
    name: str = Form(...),
    source_type: str = Form(...),
    contact_name: str = Form(None),
    contact_email: str = Form(None),
    contact_phone: str = Form(None),
    company: str = Form(None),
    commission_type: str = Form("percentage"),
    commission_rate: float = Form(5.0),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Create a new referral source."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ensure_tables(db)

    try:
        db.execute(text("""
            INSERT INTO referral_sources
            (name, source_type, contact_name, contact_email, contact_phone, company, commission_type, commission_rate, notes, created_by, org_id)
            VALUES (:name, :type, :contact, :email, :phone, :company, :ctype, :rate, :notes, :uid, :org_id)
        """), {
            "name": name,
            "type": source_type,
            "contact": contact_name,
            "email": contact_email,
            "phone": contact_phone,
            "company": company,
            "ctype": commission_type,
            "rate": commission_rate,
            "notes": notes,
            "uid": user.id,
            "org_id": request.state.org_id
        })
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/referrals/sources", status_code=302)


@router.get("/new", response_class=HTMLResponse)
async def new_referral(
    request: Request,
    client_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Create new referral form."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    org_id = get_request_org_id(request)

    try:
        sources = db.execute(text("SELECT id, name FROM referral_sources WHERE is_active = true AND org_id = :org_id ORDER BY name"), {"org_id": org_id}).fetchall()
    except Exception as e:
        logger.error("Failed to fetch active referral sources: %s", e)
        db.rollback()
        sources = []

    clients = []
    cases = []
    if org_id is not None:
        try:
            clients = tenant_query(db, Client, org_id).order_by(Client.first_name).all()
            cases = tenant_query(db, Case, org_id).order_by(Case.created_at.desc()).limit(100).all()
        except Exception as e:
            logger.error("Failed to fetch referral clients/cases: %s", e)
            db.rollback()

    selected_client = None
    if client_id and org_id is not None:
        try:
            selected_client = tenant_query(db, Client, org_id).filter(Client.id == client_id).first()
        except Exception as e:
            logger.error("Failed to fetch selected referral client: %s", e)
            db.rollback()
            selected_client = None

    return templates.TemplateResponse("app/referrals/create.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "sources": sources,
        "clients": clients,
        "cases": cases,
        "selected_client": selected_client
    })


@router.post("/create")
async def create_referral(
    request: Request,
    source_id: int = Form(...),
    client_id: int = Form(...),
    case_id: str = Form(None),
    referral_date: str = Form(None),
    case_value: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Create a new referral."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Convert form strings to proper types
    case_id = form_int(case_id)
    case_value = form_float(case_value)

    ensure_tables(db)

    # Get source commission rate
    source = db.execute(text("SELECT commission_type, commission_rate FROM referral_sources WHERE id = :id AND org_id = :org_id"),
                       {"id": source_id, "org_id": request.state.org_id}).fetchone()

    commission = 0
    if source and case_value:
        commission = referral_service.calculate_commission(
            Decimal(str(case_value)),
            source.commission_type,
            float(source.commission_rate)
        )

    ref_date = None
    if referral_date:
        try:
            ref_date = datetime.strptime(referral_date, "%Y-%m-%d").date()
        except Exception:
            ref_date = datetime.now().date()

    try:
        db.execute(text("""
            INSERT INTO referrals
            (source_id, client_id, case_id, referral_date, case_value, commission_amount, notes, created_by, org_id)
            VALUES (:source, :client, :case, :date, :value, :commission, :notes, :uid, :org_id)
        """), {
            "source": source_id,
            "client": client_id,
            "case": case_id if case_id else None,
            "date": ref_date,
            "value": case_value,
            "commission": float(commission),
            "notes": notes,
            "uid": user.id,
            "org_id": request.state.org_id
        })

        # Update source stats
        db.execute(text("""
            UPDATE referral_sources
            SET total_referrals = total_referrals + 1, updated_at = NOW()
            WHERE id = :id AND org_id = :org_id
        """), {"id": source_id, "org_id": request.state.org_id})

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/referrals", status_code=302)


@router.post("/{referral_id}/status")
async def update_status(
    request: Request,
    referral_id: int,
    status: str = Form(...),
    db: Session = Depends(get_db)
):
    """Update referral status."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        # Get current referral
        ref = db.execute(text("SELECT * FROM referrals WHERE id = :id AND org_id = :org_id"), {"id": referral_id, "org_id": request.state.org_id}).fetchone()

        if status == "paid":
            db.execute(text("""
                UPDATE referrals
                SET status = :status, updated_at = NOW(), commission_paid_date = CURRENT_DATE
                WHERE id = :id AND org_id = :org_id
            """), {"id": referral_id, "status": status, "org_id": request.state.org_id})
        else:
            db.execute(text("""
                UPDATE referrals
                SET status = :status, updated_at = NOW()
                WHERE id = :id AND org_id = :org_id
            """), {"id": referral_id, "status": status, "org_id": request.state.org_id})

        # Update source stats if converted
        if status in ["converted", "paid"] and ref.status == "pending":
            db.execute(text("""
                UPDATE referral_sources
                SET total_conversions = total_conversions + 1
                WHERE id = :id AND org_id = :org_id
            """), {"id": ref.source_id, "org_id": request.state.org_id})

        if status == "paid":
            db.execute(text("""
                UPDATE referral_sources
                SET total_commission_paid = total_commission_paid + :amount
                WHERE id = :id AND org_id = :org_id
            """), {"id": ref.source_id, "amount": ref.commission_amount or 0, "org_id": request.state.org_id})

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/referrals", status_code=302)


@router.post("/{referral_id}/delete")
async def delete_referral(
    request: Request,
    referral_id: int,
    db: Session = Depends(get_db)
):
    """Delete a referral."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        db.execute(text("DELETE FROM referrals WHERE id = :id AND org_id = :org_id"), {"id": referral_id, "org_id": request.state.org_id})
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/referrals", status_code=302)
