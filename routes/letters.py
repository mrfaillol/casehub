"""
CaseHub - Letter Templates Routes
Generate customized letters from templates
"""
from datetime import datetime
import json
import logging
import re

logger = logging.getLogger(__name__)

from core.form_utils import form_int, form_float
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, Client, Case
from auth import get_current_user
from models.tenant import tenant_query
from i18n import get_translations
from config import settings

router = APIRouter(prefix="/letters", tags=["letters"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py
# PREFIX = "/casehub"  # Imported from template_config.py

def get_context(request: Request, db: Session, **kwargs):
    lang = request.cookies.get("lang", "pt-BR")
    t = get_translations(lang)
    user = get_current_user(request, db)
    return {"request": request, "PREFIX": PREFIX, "lang": lang, "t": t, "user": user, **kwargs}

# ==================== LETTER TEMPLATES ====================

@router.get("", response_class=HTMLResponse)
async def list_templates(request: Request, db: Session = Depends(get_db)):
    """List all letter templates"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    letter_templates_raw = db.execute(text("""
        SELECT lt.*, u.name as created_by_name,
               (SELECT COUNT(*) FROM generated_letters WHERE template_id = lt.id) as use_count
        FROM letter_templates lt
        LEFT JOIN users u ON u.id = lt.created_by
        WHERE lt.org_id = :org_id
        ORDER BY lt.category, lt.name
    """), {"org_id": request.state.org_id}).fetchall()

    # Parse variables JSON for each template
    letter_templates = []
    for lt in letter_templates_raw:
        lt_dict = dict(lt._mapping)
        if lt_dict.get('variables'):
            try:
                lt_dict['variables_list'] = json.loads(lt_dict['variables'])
            except Exception as e:
                logger.error("Failed to parse letter template variables JSON: %s", e)
                lt_dict['variables_list'] = []
        else:
            lt_dict['variables_list'] = []
        letter_templates.append(lt_dict)

    categories = db.execute(text("""
        SELECT DISTINCT category FROM letter_templates WHERE category IS NOT NULL AND org_id = :org_id ORDER BY category
    """), {"org_id": request.state.org_id}).fetchall()

    return templates.TemplateResponse("app/letters/list.html", get_context(
        request, db,
        letter_templates=letter_templates,
        categories=[c.category for c in categories]
    ))

@router.get("/new", response_class=HTMLResponse)
async def new_template_form(request: Request, db: Session = Depends(get_db)):
    """Show form to create new template"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    return templates.TemplateResponse("app/letters/form.html", get_context(request, db, template=None))

@router.post("/new")
async def create_template(
    request: Request,
    name: str = Form(...),
    description: str = Form(None),
    category: str = Form(None),
    subject: str = Form(None),
    body: str = Form(...),
    db: Session = Depends(get_db)
):
    """Create a new letter template"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Extract variables from body ({{variable_name}})
    variables = list(set(re.findall(r'\{\{(\w+)\}\}', body + (subject or ''))))
    variables_json = json.dumps(variables)

    db.execute(text("""
        INSERT INTO letter_templates (name, description, category, subject, body, variables, created_by, org_id)
        VALUES (:name, :description, :category, :subject, :body, :variables, :created_by, :org_id)
    """), {
        "name": name,
        "description": description,
        "category": category,
        "subject": subject,
        "body": body,
        "variables": variables_json,
        "created_by": user.id,
        "org_id": request.state.org_id
    })
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/letters", status_code=302)

@router.get("/{template_id}", response_class=HTMLResponse)
async def view_template(template_id: int, request: Request, db: Session = Depends(get_db)):
    """View a template"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    template_row = db.execute(text("""
        SELECT lt.*, u.name as created_by_name
        FROM letter_templates lt
        LEFT JOIN users u ON u.id = lt.created_by
        WHERE lt.id = :id AND lt.org_id = :org_id
    """), {"id": template_id, "org_id": request.state.org_id}).fetchone()

    if not template_row:
        raise HTTPException(status_code=404, detail="Template not found")

    # Convert to dict and parse variables JSON
    template = dict(template_row._mapping)
    if template.get('variables'):
        try:
            template['variables_list'] = json.loads(template['variables'])
        except Exception as e:
            logger.error("Failed to parse template variables JSON: %s", e)
            template['variables_list'] = []
    else:
        template['variables_list'] = []

    return templates.TemplateResponse("app/letters/detail.html", get_context(request, db, template=template))

@router.get("/{template_id}/edit", response_class=HTMLResponse)
async def edit_template_form(template_id: int, request: Request, db: Session = Depends(get_db)):
    """Show form to edit template"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    template = db.execute(text("SELECT * FROM letter_templates WHERE id = :id AND org_id = :org_id"), {"id": template_id, "org_id": request.state.org_id}).fetchone()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return templates.TemplateResponse("app/letters/form.html", get_context(request, db, template=template))

@router.post("/{template_id}/edit")
async def update_template(
    template_id: int,
    request: Request,
    name: str = Form(...),
    description: str = Form(None),
    category: str = Form(None),
    subject: str = Form(None),
    body: str = Form(...),
    is_active: bool = Form(True),
    db: Session = Depends(get_db)
):
    """Update a template"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    variables = list(set(re.findall(r'\{\{(\w+)\}\}', body + (subject or ''))))
    variables_json = json.dumps(variables)

    db.execute(text("""
        UPDATE letter_templates
        SET name = :name, description = :description, category = :category,
            subject = :subject, body = :body, variables = :variables,
            is_active = :is_active, updated_at = NOW()
        WHERE id = :id AND org_id = :org_id
    """), {
        "id": template_id,
        "org_id": request.state.org_id,
        "name": name,
        "description": description,
        "category": category,
        "subject": subject,
        "body": body,
        "variables": variables_json,
        "is_active": is_active
    })
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/letters/{template_id}", status_code=302)

@router.post("/{template_id}/delete")
async def delete_template(template_id: int, request: Request, db: Session = Depends(get_db)):
    """Delete a template"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    db.execute(text("DELETE FROM letter_templates WHERE id = :id AND org_id = :org_id"), {"id": template_id, "org_id": request.state.org_id})
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/letters", status_code=302)

# ==================== GENERATE LETTERS ====================

@router.get("/{template_id}/generate", response_class=HTMLResponse)
async def generate_form(
    template_id: int,
    request: Request,
    case_id: int = None,
    client_id: int = None,
    db: Session = Depends(get_db)
):
    """Show form to generate letter from template"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    template = db.execute(text("SELECT * FROM letter_templates WHERE id = :id AND org_id = :org_id"), {"id": template_id, "org_id": request.state.org_id}).fetchone()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Pre-fill variables if case or client provided
    prefill = {}
    case = None
    client = None

    if case_id:
        case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
        if case:
            client = tenant_query(db, Client, request.state.org_id).filter(Client.id == case.client_id).first()
            prefill['case_number'] = case.case_number or ''
            prefill['receipt_number'] = case.receipt_number or ''
            prefill['visa_type'] = case.visa_type or ''
            prefill['case_name'] = case.case_name or ''

    if client_id and not client:
        client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()

    if client:
        prefill['client_name'] = f"{client.first_name} {client.last_name}"
        prefill['beneficiary_name'] = f"{client.first_name} {client.last_name}"
        prefill['client_email'] = client.email or ''
        prefill['client_phone'] = client.phone or ''

    # Common prefills
    prefill['firm_name'] = settings.ORG_NAME
    prefill['attorney_name'] = user.name
    prefill['firm_phone'] = ''
    prefill['firm_email'] = settings.ORG_EMAIL or settings.SMTP_USER

    return templates.TemplateResponse("letters/generate.html", get_context(
        request, db,
        template=template,
        case=case,
        client=client,
        prefill=prefill
    ))

@router.post("/{template_id}/generate")
async def generate_letter(
    template_id: int,
    request: Request,
    case_id: str = Form(None),
    client_id: str = Form(None),
    db: Session = Depends(get_db)
):
    """Generate letter from template with submitted values"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Convert form strings to proper types
    case_id = form_int(case_id)
    client_id = form_int(client_id)

    template = db.execute(text("SELECT * FROM letter_templates WHERE id = :id AND org_id = :org_id"), {"id": template_id, "org_id": request.state.org_id}).fetchone()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Get form data
    form_data = await request.form()
    variables = json.loads(template.variables) if template.variables else []

    # Replace variables in subject and body
    subject = template.subject or ''
    body = template.body

    for var in variables:
        value = form_data.get(var, '')
        subject = subject.replace(f'{{{{{var}}}}}', value)
        body = body.replace(f'{{{{{var}}}}}', value)

    # Save generated letter
    result = db.execute(text("""
        INSERT INTO generated_letters (template_id, case_id, client_id, subject, body, generated_by, org_id)
        VALUES (:template_id, :case_id, :client_id, :subject, :body, :generated_by, :org_id)
        RETURNING id
    """), {
        "template_id": template_id,
        "case_id": case_id,
        "client_id": client_id,
        "subject": subject,
        "body": body,
        "generated_by": user.id,
        "org_id": request.state.org_id
    })
    letter_id = result.fetchone()[0]
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/letters/generated/{letter_id}", status_code=302)

@router.get("/generated/{letter_id}", response_class=HTMLResponse)
async def view_generated_letter(letter_id: int, request: Request, db: Session = Depends(get_db)):
    """View a generated letter"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    letter = db.execute(text("""
        SELECT gl.*, lt.name as template_name,
               c.case_name, c.case_number,
               cl.first_name || ' ' || cl.last_name as client_name,
               u.name as generated_by_name
        FROM generated_letters gl
        LEFT JOIN letter_templates lt ON lt.id = gl.template_id
        LEFT JOIN cases c ON c.id = gl.case_id
        LEFT JOIN clients cl ON cl.id = gl.client_id
        LEFT JOIN users u ON u.id = gl.generated_by
        WHERE gl.id = :id AND gl.org_id = :org_id
    """), {"id": letter_id, "org_id": request.state.org_id}).fetchone()

    if not letter:
        raise HTTPException(status_code=404, detail="Letter not found")

    return templates.TemplateResponse("app/letters/generated_view.html", get_context(request, db, letter=letter))
