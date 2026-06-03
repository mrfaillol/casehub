"""
CaseHub - Shipment Tracking Routes
Track USPS, FedEx, UPS shipments for cases.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, User, Case
from auth import get_current_user
from models.tenant import tenant_query
from services.shipment_service import shipment_service, CREATE_SHIPMENTS_TABLE, Carrier, ShipmentStatus

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/shipments", tags=["shipments"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py


def ensure_tables(db: Session):
    """Ensure shipments tables exist."""
    try:
        db.execute(text(CREATE_SHIPMENTS_TABLE))
        db.commit()
    except Exception as e:
        db.rollback()


@router.get("", response_class=HTMLResponse)
async def shipments_list(
    request: Request,
    status: Optional[str] = None,
    case_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """List all shipments."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    if case_id:
        shipments = shipment_service.get_shipments_for_case(db, case_id)
        selected_case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    else:
        shipments = shipment_service.get_all_shipments(db, status)
        selected_case = None

    # Get status counts
    try:
        counts_result = db.execute(text("""
            SELECT status, COUNT(*) as count FROM shipments WHERE org_id = :org_id GROUP BY status
        """), {"org_id": request.state.org_id})
        status_counts = {row.status: row.count for row in counts_result.fetchall()}
    except Exception:
        db.rollback()
        status_counts = {}

    cases = tenant_query(db, Case, request.state.org_id).order_by(Case.created_at.desc()).limit(50).all()

    return templates.TemplateResponse("app/shipments/list.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "shipments": shipments,
        "cases": cases,
        "selected_case": selected_case,
        "status_counts": status_counts,
        "selected_status": status,
        "carriers": [c.value for c in Carrier],
        "statuses": [s.value for s in ShipmentStatus]
    })


@router.get("/new", response_class=HTMLResponse)
async def new_shipment(
    request: Request,
    case_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Create new shipment form."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    cases = tenant_query(db, Case, request.state.org_id).order_by(Case.created_at.desc()).limit(50).all()
    selected_case = None
    if case_id:
        selected_case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()

    return templates.TemplateResponse("app/shipments/create.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "cases": cases,
        "selected_case": selected_case,
        "carriers": [{"value": c.value, "label": c.value.upper()} for c in Carrier]
    })


@router.post("/create")
async def create_shipment(
    request: Request,
    case_id: int = Form(...),
    tracking_number: str = Form(...),
    carrier: str = Form(None),
    direction: str = Form("outbound"),
    recipient: str = Form(None),
    description: str = Form(None),
    db: Session = Depends(get_db)
):
    """Create a new shipment."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ensure_tables(db)

    result = shipment_service.create_shipment(
        db, case_id, tracking_number, carrier, direction, recipient, description, user.id
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))

    return RedirectResponse(url=f"{PREFIX}/shipments?case_id={case_id}", status_code=302)


@router.post("/{shipment_id}/update-status")
async def update_status(
    request: Request,
    shipment_id: str,
    status: str = Form(...),
    location: str = Form(None),
    db: Session = Depends(get_db)
):
    """Update shipment status."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = shipment_service.update_status(db, shipment_id, status, location)

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))

    return RedirectResponse(url=f"{PREFIX}/shipments", status_code=302)


@router.post("/{shipment_id}/delete")
async def delete_shipment(request: Request, shipment_id: str, db: Session = Depends(get_db)):
    """Delete a shipment."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        db.execute(text("DELETE FROM shipments WHERE shipment_id = :sid AND org_id = :org_id"), {"sid": shipment_id, "org_id": request.state.org_id})
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/shipments", status_code=302)


@router.get("/api/detect-carrier/{tracking}", response_class=JSONResponse)
async def detect_carrier(request: Request, tracking: str, db: Session = Depends(get_db)):
    """API: Detect carrier from tracking number."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})

    carrier = shipment_service.detect_carrier(tracking)
    tracking_url = shipment_service.get_tracking_url(carrier, tracking)

    return JSONResponse(content={
        "carrier": carrier,
        "tracking_url": tracking_url
    })
