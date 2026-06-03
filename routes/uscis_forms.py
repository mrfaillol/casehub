"""
CaseHub - USCIS Forms Routes
Library of USCIS forms with pre-population capabilities.
"""
from typing import Optional, List

from core.form_utils import form_int, form_float
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, User, Case, Client
from auth import get_current_user
from models.tenant import tenant_query
from services.uscis_forms_service import uscis_forms_service, FORM_CATEGORIES, FORM_FIELD_MAPPINGS, CREATE_USCIS_FORMS_TABLE

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/uscis-forms", tags=["uscis-forms"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py


def ensure_tables(db: Session):
    """Ensure USCIS forms tables exist."""
    try:
        db.execute(text(CREATE_USCIS_FORMS_TABLE))
        db.commit()
    except Exception as e:
        db.rollback()


@router.get("", response_class=HTMLResponse)
async def forms_library(
    request: Request,
    category: Optional[str] = None,
    visa_type: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """USCIS Forms Library."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Get forms based on filters
    if search:
        forms = uscis_forms_service.search_forms(search)
    elif category:
        forms = uscis_forms_service.get_forms_by_category(category)
    elif visa_type:
        forms = uscis_forms_service.get_forms_by_visa_type(visa_type)
    else:
        forms = uscis_forms_service.get_all_forms()

    # Get categories for filter
    categories = uscis_forms_service.get_categories()

    # Get grouped categories for library view
    grouped_categories = uscis_forms_service.get_forms_grouped_by_category()

    return templates.TemplateResponse("app/uscis_forms/library.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "forms": forms,
        "categories": categories,
        "grouped_categories": grouped_categories,
        "field_mappings": FORM_FIELD_MAPPINGS,
        "selected_category": category,
        "selected_visa_type": visa_type,
        "search_query": search
    })


@router.get("/{form_number}", response_class=HTMLResponse)
async def view_form(request: Request, form_number: str, db: Session = Depends(get_db)):
    """View form details and pre-population options."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    form = uscis_forms_service.get_form(form_number)
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")

    # Get related forms
    related_forms = uscis_forms_service.get_forms_by_category(form["category"])
    related_forms = [f for f in related_forms if f["form_number"] != form_number][:5]

    # Get cases for pre-population dropdown
    cases = tenant_query(db, Case, request.state.org_id).order_by(Case.created_at.desc()).limit(50).all()

    # Get form field mappings
    field_mappings = uscis_forms_service.get_form_fields(form_number)

    return templates.TemplateResponse("app/uscis_forms/view.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "form": form,
        "related_forms": related_forms,
        "cases": cases,
        "field_mappings": field_mappings
    })


@router.get("/{form_number}/fill", response_class=HTMLResponse)
async def fill_form(
    request: Request,
    form_number: str,
    case_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Fill form with pre-populated data."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    form = uscis_forms_service.get_form(form_number)
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")

    ensure_tables(db)

    # Pre-populate if case selected
    populated_data = None
    case = None
    client = None

    if case_id:
        case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
        if case:
            client = tenant_query(db, Client, request.state.org_id).filter(Client.id == case.client_id).first()

            client_data = {}
            if client:
                client_data = {
                    "first_name": client.first_name,
                    "last_name": client.last_name,
                    "date_of_birth": str(client.date_of_birth) if client.date_of_birth else None,
                    "country_of_origin": client.country_of_origin,
                    "alien_number": client.alien_number,
                    "ssn": client.ssn,
                    "address": client.address
                }

            case_data = {
                "visa_type": case.visa_type,
                "employer_name": getattr(case, 'employer_name', None),
                "employer_address": getattr(case, 'employer_address', None)
            }

            populated_data = uscis_forms_service.pre_populate_form(
                form_number, client_data, case_data
            )

    # Get cases for dropdown
    cases = tenant_query(db, Case, request.state.org_id).order_by(Case.created_at.desc()).limit(50).all()

    return templates.TemplateResponse("app/uscis_forms/fill.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "form": form,
        "cases": cases,
        "selected_case": case,
        "client": client,
        "populated_data": populated_data
    })


@router.post("/{form_number}/save")
async def save_form_submission(
    request: Request,
    form_number: str,
    case_id: str = Form(None),
    status: str = Form("draft"),
    notes: str = Form(None),
    receipt_number: str = Form(None),
    db: Session = Depends(get_db)
):
    """Save form submission record."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Convert form strings to proper types
    case_id = form_int(case_id)

    ensure_tables(db)

    # Get populated data
    populated_data = {}
    if case_id:
        case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
        if case:
            client = tenant_query(db, Client, request.state.org_id).filter(Client.id == case.client_id).first()
            client_data = {}
            if client:
                client_data = {
                    "first_name": client.first_name,
                    "last_name": client.last_name,
                    "date_of_birth": str(client.date_of_birth) if client.date_of_birth else None,
                    "country_of_origin": client.country_of_origin,
                    "alien_number": client.alien_number
                }
            populated_data = uscis_forms_service.pre_populate_form(form_number, client_data)

    try:
        import json
        db.execute(text("""
            INSERT INTO uscis_form_submissions (case_id, form_number, status, populated_data, receipt_number, notes, created_by)
            VALUES (:case_id, :form_number, :status, :data, :receipt, :notes, :uid)
        """), {
            "case_id": case_id,
            "form_number": form_number.upper(),
            "status": status,
            "data": json.dumps(populated_data) if populated_data else None,
            "receipt": receipt_number,
            "notes": notes,
            "uid": user.id
        })
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/uscis-forms/{form_number}?saved=1", status_code=302)


@router.get("/{form_number}/summary-pdf")
async def generate_summary_pdf(
    request: Request,
    form_number: str,
    case_id: int,
    db: Session = Depends(get_db)
):
    """Generate PDF summary of pre-populated form data."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    form = uscis_forms_service.get_form(form_number)
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")

    # Get case and client data
    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == case.client_id).first()

    client_data = {}
    if client:
        client_data = {
            "first_name": client.first_name,
            "last_name": client.last_name,
            "date_of_birth": str(client.date_of_birth) if client.date_of_birth else None,
            "country_of_origin": client.country_of_origin,
            "alien_number": client.alien_number,
            "ssn": client.ssn,
            "address": client.address
        }

    populated_data = uscis_forms_service.pre_populate_form(form_number, client_data)
    pdf_bytes = uscis_forms_service.generate_form_summary_pdf(form_number, populated_data)

    if not pdf_bytes:
        raise HTTPException(status_code=500, detail="Failed to generate PDF")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={form_number}_summary.pdf"}
    )


@router.get("/api/fee-calculator", response_class=JSONResponse)
async def calculate_fees(
    request: Request,
    forms: str,
    premium: bool = False,
    db: Session = Depends(get_db)
):
    """API: Calculate total fees for selected forms."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})

    form_list = [f.strip() for f in forms.split(",") if f.strip()]
    result = uscis_forms_service.calculate_total_fees(form_list, premium)

    return JSONResponse(content=result)


@router.get("/api/search", response_class=JSONResponse)
async def search_forms(
    request: Request,
    q: str,
    db: Session = Depends(get_db)
):
    """API: Search forms."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})

    results = uscis_forms_service.search_forms(q)
    return JSONResponse(content=results)
