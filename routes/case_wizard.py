"""
CaseHub - Case Creation Wizard Routes
4-step guided case creation flow.
"""
from core.form_utils import form_int, form_float
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)

from models import get_db, Client, Case, User
from auth import get_current_user
from models.tenant import tenant_query
from services.numbering import NumberingService
from core.template_config import templates, PREFIX

router = APIRouter(prefix="/wizard", tags=["wizard"])

# Visa type configurations with workflow info
VISA_TYPES = {
    "EB-1A": {
        "name": "EB-1A Extraordinary Ability",
        "category": "Employment-Based",
        "process": "eb1a_process",
        "estimated_days": 180,
        "premium_available": True
    },
    "EB-1B": {
        "name": "EB-1B Outstanding Professor/Researcher",
        "category": "Employment-Based",
        "process": "eb1b_process",
        "estimated_days": 180,
        "premium_available": True
    },
    "EB-2 NIW": {
        "name": "EB-2 National Interest Waiver",
        "category": "Employment-Based",
        "process": "eb2niw_process",
        "estimated_days": 270,
        "premium_available": True
    },
    "H-1B": {
        "name": "H-1B Specialty Occupation",
        "category": "Non-Immigrant",
        "process": "h1b_process",
        "estimated_days": 90,
        "premium_available": True
    },
    "H-1B Transfer": {
        "name": "H-1B Transfer",
        "category": "Non-Immigrant",
        "process": "h1b_transfer_process",
        "estimated_days": 60,
        "premium_available": True
    },
    "L-1A": {
        "name": "L-1A Intracompany Transfer (Manager)",
        "category": "Non-Immigrant",
        "process": "l1a_process",
        "estimated_days": 90,
        "premium_available": True
    },
    "L-1B": {
        "name": "L-1B Intracompany Transfer (Specialized Knowledge)",
        "category": "Non-Immigrant",
        "process": "l1b_process",
        "estimated_days": 90,
        "premium_available": True
    },
    "O-1A": {
        "name": "O-1A Extraordinary Ability (Sciences/Business)",
        "category": "Non-Immigrant",
        "process": "o1a_process",
        "estimated_days": 60,
        "premium_available": True
    },
    "O-1B": {
        "name": "O-1B Extraordinary Ability (Arts)",
        "category": "Non-Immigrant",
        "process": "o1b_process",
        "estimated_days": 60,
        "premium_available": True
    },
    "I-140": {
        "name": "I-140 Immigrant Petition",
        "category": "Employment-Based",
        "process": "i140_process",
        "estimated_days": 180,
        "premium_available": True
    },
    "I-485": {
        "name": "I-485 Adjustment of Status",
        "category": "Employment-Based",
        "process": "i485_process",
        "estimated_days": 365,
        "premium_available": False
    },
    "N-400": {
        "name": "N-400 Naturalization",
        "category": "Citizenship",
        "process": "n400_process",
        "estimated_days": 180,
        "premium_available": False
    },
    "Family-Based": {
        "name": "Family-Based Green Card",
        "category": "Family-Based",
        "process": "family_process",
        "estimated_days": 365,
        "premium_available": False
    },
    "Other": {
        "name": "Other Immigration Matter",
        "category": "Other",
        "process": "general_process",
        "estimated_days": 90,
        "premium_available": False
    }
}


def get_session_data(request: Request) -> dict:
    """Get wizard session data from cookie."""
    try:
        data = request.cookies.get("wizard_data", "{}")
        return json.loads(data)
    except Exception as e:
        logger.error("Failed to parse wizard session data: %s", e)
        return {}


def clear_session_data(response):
    """Clear wizard session data."""
    response.delete_cookie("wizard_data", path="/")
    return response


@router.get("", response_class=HTMLResponse)
async def wizard_start(request: Request, db: Session = Depends(get_db)):
    """Start the case creation wizard."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Clear any previous wizard data
    response = templates.TemplateResponse("app/wizard/step1_client.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "step": 1,
        "total_steps": 4
    })
    return clear_session_data(response)


@router.get("/step1", response_class=HTMLResponse)
async def wizard_step1(request: Request, db: Session = Depends(get_db)):
    """Step 1: Select or create client."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    clients = tenant_query(db, Client, request.state.org_id).order_by(Client.first_name).all()
    session_data = get_session_data(request)

    return templates.TemplateResponse("app/wizard/step1_client.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "step": 1,
        "total_steps": 4,
        "clients": clients,
        "session_data": session_data
    })


@router.post("/step1")
async def wizard_step1_submit(
    request: Request,
    action: str = Form(...),
    client_id: Optional[int] = Form(None),
    first_name: str = Form(None),
    middle_name: str = Form(None),
    last_name: str = Form(None),
    email: str = Form(None),
    phone: str = Form(None),
    country_of_origin: str = Form(None),
    db: Session = Depends(get_db)
):
    """Process Step 1: Client selection or creation."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    session_data = get_session_data(request)

    if action == "select" and client_id:
        # Using existing client
        client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
        if not client:
            return RedirectResponse(url=f"{PREFIX}/wizard/step1?error=client_not_found", status_code=302)
        session_data["client_id"] = client.id
        session_data["client_name"] = f"{client.first_name} {client.last_name}"
        session_data["client_email"] = client.email
        session_data["is_new_client"] = False

    elif action == "create":
        # Create new client
        if not first_name or not last_name:
            return RedirectResponse(url=f"{PREFIX}/wizard/step1?error=name_required", status_code=302)

        # Generate client number
        numbering = NumberingService(db)
        client_number = numbering.generate_client_number()

        client = Client(
            client_number=client_number,
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            email=email,
            phone=phone,
            country_of_origin=country_of_origin,
            status="active",
        org_id=request.state.org_id)
        db.add(client)
        db.commit()
        db.refresh(client)

        session_data["client_id"] = client.id
        session_data["client_name"] = f"{first_name} {last_name}"
        session_data["client_email"] = email
        session_data["is_new_client"] = True

    # Save session and redirect to step 2
    response = RedirectResponse(url=f"{PREFIX}/wizard/step2", status_code=302)
    response.set_cookie(
        key="wizard_data",
        value=json.dumps(session_data),
        httponly=True,
        max_age=3600,
        path="/"
    )
    return response


@router.get("/step2", response_class=HTMLResponse)
async def wizard_step2(request: Request, db: Session = Depends(get_db)):
    """Step 2: Select visa type and case details."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    session_data = get_session_data(request)
    if not session_data.get("client_id"):
        return RedirectResponse(url=f"{PREFIX}/wizard/step1?error=no_client", status_code=302)

    # Group visa types by category
    visa_categories = {}
    for code, info in VISA_TYPES.items():
        cat = info["category"]
        if cat not in visa_categories:
            visa_categories[cat] = []
        visa_categories[cat].append({"code": code, **info})

    return templates.TemplateResponse("app/wizard/step2_case_type.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "step": 2,
        "total_steps": 4,
        "visa_categories": visa_categories,
        "session_data": session_data
    })


@router.post("/step2")
async def wizard_step2_submit(
    request: Request,
    visa_type: str = Form(...),
    case_name: str = Form(None),
    priority: str = Form("medium"),
    premium_processing: bool = Form(False),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Process Step 2: Case type selection."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    session_data = get_session_data(request)
    if not session_data.get("client_id"):
        return RedirectResponse(url=f"{PREFIX}/wizard/step1?error=no_client", status_code=302)

    visa_info = VISA_TYPES.get(visa_type, VISA_TYPES["Other"])

    session_data["visa_type"] = visa_type
    session_data["visa_info"] = visa_info
    session_data["case_name"] = case_name or f"{session_data.get('client_name', 'Client')} - {visa_type}"
    session_data["priority"] = priority
    session_data["premium_processing"] = premium_processing
    session_data["notes"] = notes

    response = RedirectResponse(url=f"{PREFIX}/wizard/step3", status_code=302)
    response.set_cookie(
        key="wizard_data",
        value=json.dumps(session_data),
        httponly=True,
        max_age=3600,
        path="/"
    )
    return response


@router.get("/step3", response_class=HTMLResponse)
async def wizard_step3(request: Request, db: Session = Depends(get_db)):
    """Step 3: Add related parties (employer, petitioner, attorney)."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    session_data = get_session_data(request)
    if not session_data.get("visa_type"):
        return RedirectResponse(url=f"{PREFIX}/wizard/step2?error=no_visa_type", status_code=302)

    # Get attorneys/users
    attorneys = tenant_query(db, User, request.state.org_id).filter(User.user_type.in_(["admin", "attorney"])).all()

    return templates.TemplateResponse("app/wizard/step3_parties.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "step": 3,
        "total_steps": 4,
        "attorneys": attorneys,
        "session_data": session_data
    })


@router.post("/step3")
async def wizard_step3_submit(
    request: Request,
    employer_name: str = Form(None),
    employer_address: str = Form(None),
    employer_ein: str = Form(None),
    petitioner_name: str = Form(None),
    petitioner_title: str = Form(None),
    assigned_attorney: str = Form(None),
    db: Session = Depends(get_db)
):
    """Process Step 3: Related parties."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Convert form strings to proper types
    assigned_attorney = form_int(assigned_attorney)

    session_data = get_session_data(request)
    if not session_data.get("visa_type"):
        return RedirectResponse(url=f"{PREFIX}/wizard/step2?error=no_visa_type", status_code=302)

    session_data["employer"] = {
        "name": employer_name,
        "address": employer_address,
        "ein": employer_ein
    } if employer_name else None

    session_data["petitioner"] = {
        "name": petitioner_name,
        "title": petitioner_title
    } if petitioner_name else None

    session_data["assigned_attorney"] = assigned_attorney

    response = RedirectResponse(url=f"{PREFIX}/wizard/step4", status_code=302)
    response.set_cookie(
        key="wizard_data",
        value=json.dumps(session_data),
        httponly=True,
        max_age=3600,
        path="/"
    )
    return response


@router.get("/step4", response_class=HTMLResponse)
async def wizard_step4(request: Request, db: Session = Depends(get_db)):
    """Step 4: Review and create case."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    session_data = get_session_data(request)
    if not session_data.get("visa_type"):
        return RedirectResponse(url=f"{PREFIX}/wizard/step2?error=no_visa_type", status_code=302)

    # Get client details
    client = None
    if session_data.get("client_id"):
        client = tenant_query(db, Client, request.state.org_id).filter(Client.id == session_data["client_id"]).first()

    # Get attorney details
    attorney = None
    if session_data.get("assigned_attorney"):
        attorney = tenant_query(db, User, request.state.org_id).filter(User.id == session_data["assigned_attorney"]).first()

    # Preview case number
    numbering = NumberingService(db)
    preview_number = numbering.preview_format(
        numbering.get_settings().get("case_format", numbering.DEFAULT_CASE_FORMAT),
        "case"
    )

    return templates.TemplateResponse("app/wizard/step4_review.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "step": 4,
        "total_steps": 4,
        "session_data": session_data,
        "client": client,
        "attorney": attorney,
        "preview_number": preview_number
    })


@router.post("/create")
async def wizard_create_case(request: Request, db: Session = Depends(get_db)):
    """Create the case from wizard data."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    session_data = get_session_data(request)
    if not session_data.get("client_id") or not session_data.get("visa_type"):
        return RedirectResponse(url=f"{PREFIX}/wizard?error=incomplete", status_code=302)

    # Generate case number
    numbering = NumberingService(db)
    case_number = numbering.generate_case_number(visa_type=session_data.get("visa_type"))

    # Build standardized case name
    wizard_client = tenant_query(db, Client, request.state.org_id).filter(Client.id == session_data["client_id"]).first()
    vt = session_data.get("visa_type", "Unknown")
    if wizard_client:
        standard_case_name = f"{wizard_client.first_name} {wizard_client.last_name} - {vt} case"
    else:
        standard_case_name = session_data.get("case_name") or f"Case - {vt} case"

    # Create the case
    case = Case(
        client_id=session_data["client_id"],
        case_number=case_number,
        case_name=standard_case_name,
        visa_type=session_data.get("visa_type"),
        status="intake",
        priority=session_data.get("priority", "medium"),
        notes=session_data.get("notes"),
        org_id=request.state.org_id)

    # Store extra data in notes or custom fields
    extra_data = []
    if session_data.get("employer"):
        extra_data.append(f"Employer: {session_data['employer'].get('name', '')}")
    if session_data.get("petitioner"):
        extra_data.append(f"Petitioner: {session_data['petitioner'].get('name', '')}")
    if session_data.get("premium_processing"):
        extra_data.append("Premium Processing: Yes")

    if extra_data and case.notes:
        case.notes = case.notes + "\n\n" + "\n".join(extra_data)
    elif extra_data:
        case.notes = "\n".join(extra_data)

    db.add(case)
    db.commit()
    db.refresh(case)

    # Clear wizard data and redirect to case
    response = RedirectResponse(url=f"{PREFIX}/cases/{case.id}?created=wizard", status_code=302)
    return clear_session_data(response)


@router.get("/api/visa-types", response_class=JSONResponse)
async def get_visa_types(request: Request, db: Session = Depends(get_db)):
    """API: Get available visa types."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    return JSONResponse(content=VISA_TYPES)


@router.get("/api/client/{client_id}", response_class=JSONResponse)
async def get_client_info(client_id: int, request: Request, db: Session = Depends(get_db)):
    """API: Get client information for wizard."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        return JSONResponse(status_code=404, content={"error": "Client not found"})

    return JSONResponse(content={
        "id": client.id,
        "name": f"{client.first_name} {client.last_name}",
        "email": client.email,
        "phone": client.phone,
        "country_of_origin": client.country_of_origin
    })
