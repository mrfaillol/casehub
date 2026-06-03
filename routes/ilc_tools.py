"""
CaseHub - Document Generator Tools Integration Routes
Integration with LOR Generator, PS Generator, and other tools.
"""
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from typing import Optional
import logging

logger = logging.getLogger(__name__)
import os
import requests
import json

from config import settings
from models import get_db, Client, Case, Document
from auth import get_current_user
from models.tenant import tenant_query

# PREFIX = "/casehub"  # Imported from template_config.py

# Tools service base URL (running on same server)
TOOLS_BASE_URL = settings.ILC_TOOLS_URL

router = APIRouter(prefix="/ilc-tools", tags=["ilc-tools"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py


def get_context(request: Request, db: Session, **kwargs):
    from i18n import get_translations
    lang = request.cookies.get("lang", "pt-BR")
    t = get_translations(lang)
    user = get_current_user(request, db)
    return {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "t": t,
        "lang": lang,
        **kwargs
    }


@router.get("", response_class=HTMLResponse)
def tools_dashboard(request: Request, db: Session = Depends(get_db)):
    """Tools dashboard.

    Sync handler: it makes a blocking requests.get() to the tools service, so
    FastAPI runs it in a threadpool — the blocking call never stalls the event
    loop. Awaits nothing.
    """
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Check tools service availability
    tools_status = {"online": False, "version": "unknown"}
    try:
        response = requests.get(f"{TOOLS_BASE_URL}/api/health", timeout=5)
        if response.status_code == 200:
            tools_status = {"online": True, **response.json()}
    except Exception as e:
        logger.error("Failed to check tools health status: %s", e)

    return templates.TemplateResponse("app/ilc_tools/dashboard.html", get_context(
        request, db,
        tools_status=tools_status
    ))


# ==========================================
# LOR Generator Integration
# ==========================================

@router.get("/lor", response_class=HTMLResponse)
async def lor_form(
    request: Request,
    case_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """LOR Generator form - pre-filled from case data"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    case = None
    client = None
    if case_id:
        case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
        if case and case.client_id:
            client = tenant_query(db, Client, request.state.org_id).filter(Client.id == case.client_id).first()

    # Get all cases for dropdown
    cases = tenant_query(db, Case, request.state.org_id).order_by(Case.created_at.desc()).all()

    return templates.TemplateResponse("app/ilc_tools/lor_form.html", get_context(
        request, db,
        case=case,
        client=client,
        cases=cases
    ))


@router.post("/lor/generate")
def generate_lor(
    request: Request,
    case_id: Optional[int] = Form(None),
    beneficiary_name: str = Form(...),
    field_of_expertise: str = Form(...),
    writer_name: str = Form(...),
    writer_title: str = Form(...),
    writer_institution: str = Form(...),
    relationship: str = Form(...),
    years_known: int = Form(...),
    achievements: str = Form(""),
    national_importance: str = Form(""),
    additional_context: str = Form(""),
    db: Session = Depends(get_db)
):
    """Generate LOR using tools service"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Prepare data for LOR generator
    lor_data = {
        "beneficiary_name": beneficiary_name,
        "field": field_of_expertise,
        "writer_name": writer_name,
        "writer_title": writer_title,
        "writer_institution": writer_institution,
        "relationship": relationship,
        "years_known": years_known,
        "achievements": achievements,
        "national_importance": national_importance,
        "additional_context": additional_context
    }

    try:
        # Call tools service LOR API
        response = requests.post(
            f"{TOOLS_BASE_URL}/api/lor/generate",
            data=lor_data,
            timeout=60
        )

        if response.status_code == 200:
            result = response.json()

            # If case_id provided, create a document record
            if case_id:
                case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
                if case:
                    doc = Document(
                        case_id=case_id,
                        client_id=case.client_id,
                        name=f"LOR - {writer_name} for {beneficiary_name}",
                        type="lor",
                        status="generated",
                        notes=f"Generated via tools service. Writer: {writer_name} ({writer_institution})",
        org_id=request.state.org_id)
                    db.add(doc)
                    db.commit()

            return templates.TemplateResponse("app/ilc_tools/lor_result.html", get_context(
                request, db,
                result=result,
                lor_data=lor_data,
                case_id=case_id
            ))
        else:
            error = f"Error from tools service: {response.text}"
            return templates.TemplateResponse("app/ilc_tools/lor_form.html", get_context(
                request, db,
                error=error,
                lor_data=lor_data
            ))

    except requests.exceptions.Timeout:
        return templates.TemplateResponse("app/ilc_tools/lor_form.html", get_context(
            request, db,
            error="Request timed out. Please try again.",
            lor_data=lor_data
        ))
    except Exception as e:
        return templates.TemplateResponse("app/ilc_tools/lor_form.html", get_context(
            request, db,
            error=f"Error connecting to tools service: {str(e)}",
            lor_data=lor_data
        ))


# ==========================================
# Personal Statement Generator Integration
# ==========================================

@router.get("/ps", response_class=HTMLResponse)
async def ps_form(
    request: Request,
    case_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Personal Statement Generator form"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    case = None
    client = None
    if case_id:
        case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
        if case and case.client_id:
            client = tenant_query(db, Client, request.state.org_id).filter(Client.id == case.client_id).first()

    cases = tenant_query(db, Case, request.state.org_id).order_by(Case.created_at.desc()).all()

    return templates.TemplateResponse("app/ilc_tools/ps_form.html", get_context(
        request, db,
        case=case,
        client=client,
        cases=cases
    ))


@router.post("/ps/generate")
def generate_ps(
    request: Request,
    case_id: Optional[int] = Form(None),
    beneficiary_name: str = Form(...),
    field_of_expertise: str = Form(...),
    country_of_origin: str = Form(...),
    current_position: str = Form(""),
    education_background: str = Form(""),
    key_achievements: str = Form(""),
    proposed_endeavor: str = Form(""),
    national_importance: str = Form(""),
    future_plans: str = Form(""),
    db: Session = Depends(get_db)
):
    """Generate Personal Statement using tools service"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ps_data = {
        "beneficiary_name": beneficiary_name,
        "field": field_of_expertise,
        "country": country_of_origin,
        "current_position": current_position,
        "education": education_background,
        "achievements": key_achievements,
        "proposed_endeavor": proposed_endeavor,
        "national_importance": national_importance,
        "future_plans": future_plans
    }

    try:
        response = requests.post(
            f"{TOOLS_BASE_URL}/api/ps/generate",
            data=ps_data,
            timeout=60
        )

        if response.status_code == 200:
            result = response.json()

            if case_id:
                case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
                if case:
                    doc = Document(
                        case_id=case_id,
                        client_id=case.client_id,
                        name=f"Personal Statement - {beneficiary_name}",
                        type="personal_statement",
                        status="generated",
                        notes="Generated via tools service"
                    )
                    db.add(doc)
                    db.commit()

            return templates.TemplateResponse("app/ilc_tools/ps_result.html", get_context(
                request, db,
                result=result,
                ps_data=ps_data,
                case_id=case_id
            ))
        else:
            return templates.TemplateResponse("app/ilc_tools/ps_form.html", get_context(
                request, db,
                error=f"Error from tools service: {response.text}",
                ps_data=ps_data
            ))

    except Exception as e:
        return templates.TemplateResponse("app/ilc_tools/ps_form.html", get_context(
            request, db,
            error=f"Error connecting to tools service: {str(e)}",
            ps_data=ps_data
        ))


# ==========================================
# API Endpoints for AJAX
# ==========================================

@router.get("/api/status")
def tools_status(request: Request, db: Session = Depends(get_db)):
    """Check tools service status.

    Sync handler (blocking requests.get to the tools service) — FastAPI
    threadpools it so the event loop is not stalled. Awaits nothing.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        response = requests.get(f"{TOOLS_BASE_URL}/api/health", timeout=5)
        if response.status_code == 200:
            return JSONResponse({"online": True, **response.json()})
        return JSONResponse({"online": False, "error": "Non-200 response"})
    except Exception as e:
        return JSONResponse({"online": False, "error": str(e)})


@router.post("/api/lor/preview")
async def lor_preview(
    request: Request,
    beneficiary_name: str = Form(...),
    field_of_expertise: str = Form(...),
    writer_name: str = Form(...),
    db: Session = Depends(get_db)
):
    """Preview LOR structure before generation"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # Generate preview structure
    preview = {
        "title": f"Letter of Recommendation for {beneficiary_name}",
        "sections": [
            f"Introduction and relationship to {beneficiary_name}",
            f"Overview of {beneficiary_name}'s expertise in {field_of_expertise}",
            "Key achievements and contributions",
            "National/international significance of work",
            f"Strong endorsement from {writer_name}"
        ]
    }

    return JSONResponse(preview)
