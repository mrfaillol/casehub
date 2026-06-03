"""
CaseHub - Questionnaire Routes
Manage questionnaire templates and responses
"""
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from typing import Optional
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

from models import get_db, QuestionnaireTemplate, QuestionnaireField, QuestionnaireResponse, QuestionnaireFieldResponse, Client, Case, User
from auth import get_current_user
from models.tenant import tenant_query

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/questionnaires", tags=["questionnaires"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py


# Helper to get context with translations
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


# ==========================================
# TEMPLATE MANAGEMENT (Admin)
# ==========================================

@router.get("", response_class=HTMLResponse)
async def list_questionnaires(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    questionnaires = tenant_query(db, QuestionnaireTemplate, request.state.org_id).order_by(QuestionnaireTemplate.created_at.desc()).all()

    # Get response counts
    for q in questionnaires:
        q.response_count = tenant_query(db, QuestionnaireResponse, request.state.org_id).filter(
            QuestionnaireResponse.template_id == q.id
        ).count()

    categories = db.query(QuestionnaireTemplate.category).distinct().all()
    categories = [c[0] for c in categories if c[0]]

    return templates.TemplateResponse("app/questionnaires/list.html", get_context(
        request, db,
        questionnaires=questionnaires,
        categories=categories
    ))


@router.get("/new", response_class=HTMLResponse)
async def new_questionnaire_form(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    return templates.TemplateResponse("app/questionnaires/form.html", get_context(
        request, db,
        questionnaire=None,
        action="Create"
    ))


@router.post("/new")
async def create_questionnaire(
    request: Request,
    name: str = Form(...),
    description: str = Form(None),
    category: str = Form(None),
    target_type: str = Form("client"),
    is_required: bool = Form(False),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    questionnaire = QuestionnaireTemplate(
        name=name,
        description=description,
        category=category,
        target_type=target_type,
        is_required=is_required == True or is_required == "true",
        created_by=user.id
    )
    db.add(questionnaire)
    db.commit()
    db.refresh(questionnaire)

    return RedirectResponse(url=f"{PREFIX}/questionnaires/{questionnaire.id}/edit", status_code=302)


@router.get("/{questionnaire_id}", response_class=HTMLResponse)
async def view_questionnaire(request: Request, questionnaire_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    questionnaire = tenant_query(db, QuestionnaireTemplate, request.state.org_id).filter(QuestionnaireTemplate.id == questionnaire_id).first()
    if not questionnaire:
        raise HTTPException(status_code=404, detail="Questionnaire not found")

    # Get recent responses
    responses = tenant_query(db, QuestionnaireResponse, request.state.org_id).filter(
        QuestionnaireResponse.template_id == questionnaire_id
    ).order_by(QuestionnaireResponse.created_at.desc()).limit(10).all()

    # Pre-fetch clients + cases in TWO batched queries instead of two N+1
    # loops. Same pattern as PRs #560 (checklist), #561 (calendar) — the
    # honest metric for an N+1 is SQL statement count, not wall time.
    # Old: 1 + 10*2 = 21 SELECTs for the typical 10-response page (one
    # client SELECT + one case SELECT per response). New: 1 + 2 = 3
    # SELECTs (constant regardless of response count).
    client_ids = {r.client_id for r in responses if r.client_id}
    case_ids = {r.case_id for r in responses if r.case_id}

    clients_by_id = {}
    if client_ids:
        clients_by_id = {
            c.id: c
            for c in tenant_query(db, Client, request.state.org_id)
            .filter(Client.id.in_(client_ids)).all()
        }
    cases_by_id = {}
    if case_ids:
        cases_by_id = {
            c.id: c
            for c in tenant_query(db, Case, request.state.org_id)
            .filter(Case.id.in_(case_ids)).all()
        }

    for r in responses:
        if r.client_id:
            r.client = clients_by_id.get(r.client_id)
        if r.case_id:
            r.case = cases_by_id.get(r.case_id)

    return templates.TemplateResponse("app/questionnaires/detail.html", get_context(
        request, db,
        questionnaire=questionnaire,
        responses=responses
    ))


@router.get("/{questionnaire_id}/edit", response_class=HTMLResponse)
async def edit_questionnaire_form(request: Request, questionnaire_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    questionnaire = tenant_query(db, QuestionnaireTemplate, request.state.org_id).filter(QuestionnaireTemplate.id == questionnaire_id).first()
    if not questionnaire:
        raise HTTPException(status_code=404, detail="Questionnaire not found")

    return templates.TemplateResponse("app/questionnaires/form.html", get_context(
        request, db,
        questionnaire=questionnaire,
        action="Update"
    ))


@router.post("/{questionnaire_id}/edit")
async def update_questionnaire(
    request: Request,
    questionnaire_id: int,
    name: str = Form(...),
    description: str = Form(None),
    category: str = Form(None),
    target_type: str = Form("client"),
    is_required: bool = Form(False),
    is_active: bool = Form(True),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    questionnaire = tenant_query(db, QuestionnaireTemplate, request.state.org_id).filter(QuestionnaireTemplate.id == questionnaire_id).first()
    if not questionnaire:
        raise HTTPException(status_code=404, detail="Questionnaire not found")

    questionnaire.name = name
    questionnaire.description = description
    questionnaire.category = category
    questionnaire.target_type = target_type
    questionnaire.is_required = is_required == True or is_required == "true"
    questionnaire.is_active = is_active == True or is_active == "true"
    questionnaire.updated_at = datetime.utcnow()

    db.commit()

    return RedirectResponse(url=f"{PREFIX}/questionnaires/{questionnaire_id}", status_code=302)


@router.post("/{questionnaire_id}/delete")
async def delete_questionnaire(request: Request, questionnaire_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    questionnaire = tenant_query(db, QuestionnaireTemplate, request.state.org_id).filter(QuestionnaireTemplate.id == questionnaire_id).first()
    if not questionnaire:
        raise HTTPException(status_code=404, detail="Questionnaire not found")

    # Delete related records
    tenant_query(db, QuestionnaireFieldResponse, request.state.org_id).filter(
        QuestionnaireFieldResponse.response_id.in_(
            db.query(QuestionnaireResponse.id).filter(QuestionnaireResponse.template_id == questionnaire_id)
        )
    ).delete(synchronize_session=False)

    tenant_query(db, QuestionnaireResponse, request.state.org_id).filter(QuestionnaireResponse.template_id == questionnaire_id).delete()
    tenant_query(db, QuestionnaireField, request.state.org_id).filter(QuestionnaireField.template_id == questionnaire_id).delete()
    db.delete(questionnaire)
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/questionnaires", status_code=302)


# ==========================================
# FIELD MANAGEMENT
# ==========================================

@router.post("/{questionnaire_id}/fields/add")
async def add_field(
    request: Request,
    questionnaire_id: int,
    field_name: str = Form(...),
    label: str = Form(...),
    label_pt: str = Form(None),
    field_type: str = Form("text"),
    is_required: bool = Form(False),
    options: str = Form(None),
    section: str = Form(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    questionnaire = tenant_query(db, QuestionnaireTemplate, request.state.org_id).filter(QuestionnaireTemplate.id == questionnaire_id).first()
    if not questionnaire:
        raise HTTPException(status_code=404, detail="Questionnaire not found")

    # Get max order
    max_order = tenant_query(db, QuestionnaireField, request.state.org_id).filter(
        QuestionnaireField.template_id == questionnaire_id
    ).count()

    # Parse options if provided
    options_json = None
    if options and field_type in ['select', 'multiselect', 'radio', 'checkbox']:
        try:
            options_json = json.loads(options)
        except Exception as e:
            logger.error("Failed to parse field options JSON, treating as CSV: %s", e)
            # Try to parse as comma-separated values
            opts = [o.strip() for o in options.split(',') if o.strip()]
            options_json = [{"value": o, "label": o} for o in opts]

    field = QuestionnaireField(
        template_id=questionnaire_id,
        field_name=field_name,
        label=label,
        label_pt=label_pt,
        field_type=field_type,
        is_required=is_required == True or is_required == "true",
        options=options_json,
        section=section,
        order=max_order
    )
    db.add(field)
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/questionnaires/{questionnaire_id}/edit", status_code=302)


@router.post("/{questionnaire_id}/fields/{field_id}/delete")
async def delete_field(request: Request, questionnaire_id: int, field_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    field = tenant_query(db, QuestionnaireField, request.state.org_id).filter(
        QuestionnaireField.id == field_id,
        QuestionnaireField.template_id == questionnaire_id
    ).first()

    if field:
        # Delete field responses
        tenant_query(db, QuestionnaireFieldResponse, request.state.org_id).filter(QuestionnaireFieldResponse.field_id == field_id).delete()
        db.delete(field)
        db.commit()

    return RedirectResponse(url=f"{PREFIX}/questionnaires/{questionnaire_id}/edit", status_code=302)


# ==========================================
# RESPONSE MANAGEMENT
# ==========================================

@router.get("/{questionnaire_id}/fill", response_class=HTMLResponse)
async def fill_questionnaire_form(
    request: Request,
    questionnaire_id: int,
    client_id: int = None,
    case_id: int = None,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    questionnaire = tenant_query(db, QuestionnaireTemplate, request.state.org_id).filter(QuestionnaireTemplate.id == questionnaire_id).first()
    if not questionnaire:
        raise HTTPException(status_code=404, detail="Questionnaire not found")

    # Get clients and cases for selection
    clients = tenant_query(db, Client, request.state.org_id).order_by(Client.last_name, Client.first_name).all()
    cases = tenant_query(db, Case, request.state.org_id).order_by(Case.created_at.desc()).all()

    client = None
    case = None
    if client_id:
        client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if case_id:
        case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
        if case and not client:
            client = tenant_query(db, Client, request.state.org_id).filter(Client.id == case.client_id).first()

    return templates.TemplateResponse("app/questionnaires/fill.html", get_context(
        request, db,
        questionnaire=questionnaire,
        clients=clients,
        cases=cases,
        client=client,
        case=case
    ))


@router.post("/{questionnaire_id}/fill")
async def submit_questionnaire(
    request: Request,
    questionnaire_id: int,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    questionnaire = tenant_query(db, QuestionnaireTemplate, request.state.org_id).filter(QuestionnaireTemplate.id == questionnaire_id).first()
    if not questionnaire:
        raise HTTPException(status_code=404, detail="Questionnaire not found")

    # Get form data
    form_data = await request.form()

    # Get client and case from form
    client_id = form_data.get("client_id")
    case_id = form_data.get("case_id")
    if client_id:
        client_id = int(client_id) if client_id else None
    if case_id:
        case_id = int(case_id) if case_id else None

    # Create response
    response = QuestionnaireResponse(
        template_id=questionnaire_id,
        client_id=client_id,
        case_id=case_id,
        status="submitted",
        submitted_by=user.id,
        submitted_at=datetime.utcnow()
    )

    db.add(response)
    db.flush()  # Get the response.id

    # Collect responses data
    responses_data = {}
    for field in questionnaire.fields:
        if field.field_type == 'section':
            continue

        form_key = f"field_{field.id}"
        value = form_data.get(form_key)

        if value:
            responses_data[field.field_name] = value

            # Create field response
            field_response = QuestionnaireFieldResponse(
                response_id=response.id,
                field_id=field.id,
                value=str(value)
            )
            db.add(field_response)

    response.responses_data = responses_data

    db.commit()
    db.refresh(response)

    # Redirect based on context
    if client_id:
        return RedirectResponse(url=f"{PREFIX}/clients/{client_id}", status_code=302)
    elif case_id:
        return RedirectResponse(url=f"{PREFIX}/cases/{case_id}", status_code=302)
    else:
        return RedirectResponse(url=f"{PREFIX}/questionnaires/{questionnaire_id}", status_code=302)


@router.get("/responses/{response_id}", response_class=HTMLResponse)
async def view_response(request: Request, response_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    response = tenant_query(db, QuestionnaireResponse, request.state.org_id).filter(QuestionnaireResponse.id == response_id).first()
    if not response:
        raise HTTPException(status_code=404, detail="Response not found")

    # Get the questionnaire template
    questionnaire = tenant_query(db, QuestionnaireTemplate, request.state.org_id).filter(
        QuestionnaireTemplate.id == response.template_id
    ).first()

    # Get client/case info
    if response.client_id:
        response.client = tenant_query(db, Client, request.state.org_id).filter(Client.id == response.client_id).first()
    if response.case_id:
        response.case = tenant_query(db, Case, request.state.org_id).filter(Case.id == response.case_id).first()

    # Get user who submitted
    if response.submitted_by:
        response.submitted_by_user = tenant_query(db, User, request.state.org_id).filter(User.id == response.submitted_by).first()

    # Build field responses dictionary {field_id: field_response}
    field_responses = {}
    for fr in response.field_responses:
        field_responses[fr.field_id] = fr

    return templates.TemplateResponse("app/questionnaires/response_view.html", get_context(
        request, db,
        response=response,
        questionnaire=questionnaire,
        field_responses=field_responses
    ))


@router.post("/responses/{response_id}/status")
async def update_response_status(
    request: Request,
    response_id: int,
    status: str = Form(...),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    response = tenant_query(db, QuestionnaireResponse, request.state.org_id).filter(QuestionnaireResponse.id == response_id).first()
    if not response:
        raise HTTPException(status_code=404, detail="Response not found")

    response.status = status
    response.updated_at = datetime.utcnow()

    if status == "reviewed":
        response.reviewed_by = user.id
        response.reviewed_at = datetime.utcnow()

    db.commit()

    return RedirectResponse(url=f"{PREFIX}/questionnaires/responses/{response_id}", status_code=302)


@router.post("/responses/{response_id}/delete")
async def delete_response(request: Request, response_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    response = tenant_query(db, QuestionnaireResponse, request.state.org_id).filter(QuestionnaireResponse.id == response_id).first()
    if not response:
        raise HTTPException(status_code=404, detail="Response not found")

    template_id = response.template_id

    # Delete field responses first
    tenant_query(db, QuestionnaireFieldResponse, request.state.org_id).filter(
        QuestionnaireFieldResponse.response_id == response_id
    ).delete()

    # Delete response
    db.delete(response)
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/questionnaires/{template_id}", status_code=302)
