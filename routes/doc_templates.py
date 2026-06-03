"""
CaseHub - Document Templates Routes
Create and manage document templates
"""
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.request_utils import get_request_org_id
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, Client, Case, User
from auth import get_current_user
from models.tenant import tenant_query
from i18n import get_translations
from services.templates_service import DocumentTemplateService, DEFAULT_TEMPLATES, get_template_service

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/templates", tags=["templates"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py


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
async def template_list(
    request: Request,
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all document templates."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Get templates from database
    query = "SELECT * FROM document_templates WHERE 1=1"
    params = {}

    if category:
        query += " AND category = :category"
        params["category"] = category

    query += " ORDER BY category, name"

    try:
        db_templates = db.execute(text(query), params).fetchall()
    except Exception as e:
        logger.error("Failed to fetch document templates: %s", e)
        db.rollback()
        db_templates = []

    # Get categories
    try:
        categories = db.execute(text("SELECT DISTINCT category FROM document_templates ORDER BY category")).fetchall()
        categories = [c[0] for c in categories]
    except Exception as e:
        logger.error("Failed to fetch template categories: %s", e)
        db.rollback()
        categories = ["contracts", "uscis", "client_communication", "billing"]

    return templates.TemplateResponse("app/doc_templates/list.html", {
        **get_context(request, db),
        "templates_list": db_templates,
        "default_templates": DEFAULT_TEMPLATES,
        "categories": categories,
        "selected_category": category
    })


@router.get("/new", response_class=HTMLResponse)
async def new_template_form(request: Request, db: Session = Depends(get_db)):
    """Form to create new template."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    service = get_template_service(db)

    return templates.TemplateResponse("app/doc_templates/edit.html", {
        **get_context(request, db),
        "template_data": None,
        "placeholders": service.PLACEHOLDERS,
        "action": "Create"
    })


@router.post("/new")
async def create_template(
    request: Request,
    name: str = Form(...),
    category: str = Form(...),
    description: str = Form(""),
    content: str = Form(...),
    db: Session = Depends(get_db)
):
    """Create a new template."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    db.execute(text("""
        INSERT INTO document_templates (name, category, description, content, created_by, created_at)
        VALUES (:name, :category, :description, :content, :created_by, NOW())
    """), {
        "name": name,
        "category": category,
        "description": description,
        "content": content,
        "created_by": user.id
    })
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/templates", status_code=302)


@router.get("/{template_id}/edit", response_class=HTMLResponse)
async def edit_template_form(request: Request, template_id: int, db: Session = Depends(get_db)):
    """Form to edit existing template."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # IDOR C4: scope template lookup by tenant. A tenant may open its own
    # templates or read-only global templates (org_id IS NULL). Wrapped in
    # try/except because document_templates is not a managed model (see
    # docs/audit/raw-sql-defect-class-2026-05-23.md).
    org_id = get_request_org_id(request)
    try:
        template_data = db.execute(
            text(
                "SELECT * FROM document_templates "
                "WHERE id = :id AND (org_id = :org_id OR org_id IS NULL)"
            ),
            {"id": template_id, "org_id": org_id},
        ).fetchone()
    except Exception as e:
        logger.error("Failed to fetch template %s for edit: %s", template_id, e)
        db.rollback()
        template_data = None
    if not template_data:
        raise HTTPException(status_code=404, detail="Template not found")

    service = get_template_service(db)

    return templates.TemplateResponse("app/doc_templates/edit.html", {
        **get_context(request, db),
        "template_data": template_data,
        "placeholders": service.PLACEHOLDERS,
        "action": "Update"
    })


@router.post("/{template_id}/edit")
async def update_template(
    request: Request,
    template_id: int,
    name: str = Form(...),
    category: str = Form(...),
    description: str = Form(""),
    content: str = Form(...),
    db: Session = Depends(get_db)
):
    """Update an existing template."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # IDOR C4: only the owning tenant may mutate a template. Global templates
    # (org_id IS NULL) are read-only and cross-tenant writes are blocked by the
    # org_id predicate. 404 if no row matched.
    org_id = get_request_org_id(request)
    if org_id is None:
        raise HTTPException(status_code=404, detail="Template not found")
    try:
        result = db.execute(text("""
            UPDATE document_templates
            SET name = :name, category = :category, description = :description,
                content = :content, updated_at = NOW()
            WHERE id = :id AND org_id = :org_id
        """), {
            "id": template_id,
            "org_id": org_id,
            "name": name,
            "category": category,
            "description": description,
            "content": content
        })
        db.commit()
    except Exception as e:
        logger.error("Failed to update template %s: %s", template_id, e)
        db.rollback()
        raise HTTPException(status_code=404, detail="Template not found")

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Template not found")

    return RedirectResponse(url=f"{PREFIX}/templates", status_code=302)


@router.post("/{template_id}/delete")
async def delete_template(request: Request, template_id: int, db: Session = Depends(get_db)):
    """Delete a template."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # IDOR C4: only the owning tenant may delete a template. Global templates
    # (org_id IS NULL) are protected by the org_id predicate. 404 if no match.
    org_id = get_request_org_id(request)
    if org_id is None:
        raise HTTPException(status_code=404, detail="Template not found")
    try:
        result = db.execute(
            text("DELETE FROM document_templates WHERE id = :id AND org_id = :org_id"),
            {"id": template_id, "org_id": org_id},
        )
        db.commit()
    except Exception as e:
        logger.error("Failed to delete template %s: %s", template_id, e)
        db.rollback()
        raise HTTPException(status_code=404, detail="Template not found")

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Template not found")

    return RedirectResponse(url=f"{PREFIX}/templates", status_code=302)


@router.get("/generate", response_class=HTMLResponse)
async def generate_document_form(
    request: Request,
    template_id: Optional[int] = None,
    case_id: Optional[int] = None,
    client_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Form to generate a document from a template."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Get all templates
    try:
        db_templates = db.execute(text("SELECT * FROM document_templates ORDER BY category, name")).fetchall()
    except Exception as e:
        logger.error("Failed to fetch document templates for generation: %s", e)
        db.rollback()
        db_templates = []

    # Get clients and cases for selection
    org_id = get_request_org_id(request)
    clients = []
    cases = []
    if org_id is not None:
        try:
            clients = tenant_query(db, Client, org_id).order_by(Client.last_name).all()
            cases = tenant_query(db, Case, org_id).order_by(Case.created_at.desc()).all()
        except Exception as e:
            logger.error("Failed to fetch generation clients/cases: %s", e)
            db.rollback()

    # Get selected template if provided.
    # IDOR C4: scope by tenant — own templates or read-only global (org_id NULL).
    selected_template = None
    if template_id:
        try:
            selected_template = db.execute(
                text(
                    "SELECT * FROM document_templates "
                    "WHERE id = :id AND (org_id = :org_id OR org_id IS NULL)"
                ),
                {"id": template_id, "org_id": org_id},
            ).fetchone()
        except Exception as e:
            logger.error("Failed to fetch selected document template: %s", e)
            db.rollback()
            selected_template = None

    return templates.TemplateResponse("app/doc_templates/generate.html", {
        **get_context(request, db),
        "templates_list": db_templates,
        "default_templates": DEFAULT_TEMPLATES,
        "clients": clients,
        "cases": cases,
        "selected_template": selected_template,
        "selected_case_id": case_id,
        "selected_client_id": client_id
    })


@router.post("/generate")
async def generate_document(
    request: Request,
    template_id: Optional[int] = Form(None),
    default_template: Optional[str] = Form(None),
    case_id: Optional[int] = Form(None),
    client_id: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    """Generate document from template."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Get template content.
    # IDOR C4: scope by tenant — own templates or read-only global (org_id NULL).
    template_content = None

    if template_id:
        org_id = get_request_org_id(request)
        try:
            template_data = db.execute(
                text(
                    "SELECT content FROM document_templates "
                    "WHERE id = :id AND (org_id = :org_id OR org_id IS NULL)"
                ),
                {"id": template_id, "org_id": org_id},
            ).fetchone()
        except Exception as e:
            logger.error("Failed to fetch template %s content: %s", template_id, e)
            db.rollback()
            template_data = None
        if template_data:
            template_content = template_data.content
    elif default_template:
        for t in DEFAULT_TEMPLATES:
            if t["name"] == default_template:
                template_content = t["content"]
                break

    if not template_content:
        raise HTTPException(status_code=400, detail="Template not found")

    # Render template
    service = get_template_service(db)
    rendered = service.preview_template(template_content, client_id, case_id)

    return templates.TemplateResponse("app/doc_templates/preview.html", {
        **get_context(request, db),
        "rendered_content": rendered,
        "template_id": template_id,
        "case_id": case_id,
        "client_id": client_id
    })


@router.post("/preview")
async def preview_template(
    request: Request,
    content: str = Form(...),
    case_id: Optional[int] = Form(None),
    client_id: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    """Preview template with data."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = get_template_service(db)
    rendered = service.preview_template(content, client_id, case_id)

    return JSONResponse({"rendered": rendered})


@router.post("/install-defaults")
async def install_default_templates(request: Request, db: Session = Depends(get_db)):
    """Install default templates to database."""
    user = get_current_user(request, db)
    if not user or user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    for t in DEFAULT_TEMPLATES:
        # Check if exists
        existing = db.execute(text("SELECT id FROM document_templates WHERE name = :name"),
                              {"name": t["name"]}).fetchone()
        if not existing:
            db.execute(text("""
                INSERT INTO document_templates (name, category, description, content, created_by, created_at)
                VALUES (:name, :category, :description, :content, :created_by, NOW())
            """), {
                "name": t["name"],
                "category": t["category"],
                "description": t["description"],
                "content": t["content"],
                "created_by": user.id
            })

    db.commit()

    return RedirectResponse(url=f"{PREFIX}/templates?installed=true", status_code=302)
