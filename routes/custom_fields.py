"""
CaseHub - Custom Fields Routes
Allows defining and managing custom fields for clients, cases, and documents
"""
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
import json
import logging

logger = logging.getLogger(__name__)

from models import get_db
from auth import get_current_user

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/custom-fields", tags=["custom_fields"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py

VALID_ENTITY_TYPES = {"client", "case", "document", "contact"}

# ============================================
# FIELD DEFINITIONS (Admin)
# ============================================

@router.get("", response_class=HTMLResponse)
async def list_definitions(
    request: Request,
    entity_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all custom field definitions"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    query = "SELECT * FROM custom_field_definitions WHERE org_id = :org_id"
    params = {"org_id": request.state.org_id}

    if entity_type:
        query += " AND entity_type = :entity_type"
        params["entity_type"] = entity_type

    query += " ORDER BY entity_type, display_order, field_name"
    
    result = db.execute(text(query), params)
    definitions = result.fetchall()
    
    return templates.TemplateResponse("app/custom_fields/list.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "definitions": definitions,
        "entity_type": entity_type or "",
        "entity_types": ["client", "case", "document"]
    })

@router.get("/new", response_class=HTMLResponse)
async def new_definition(request: Request, db: Session = Depends(get_db)):
    """Form to create new custom field definition"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    return templates.TemplateResponse("app/custom_fields/form.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "definition": None,
        "action": "Create",
        "entity_types": ["client", "case", "document"],
        "field_types": ["text", "textarea", "number", "date", "select", "checkbox", "file"]
    })

@router.post("/new")
async def create_definition(
    request: Request,
    entity_type: str = Form(...),
    field_name: str = Form(...),
    field_label: str = Form(...),
    field_type: str = Form("text"),
    options: str = Form(None),
    required: bool = Form(False),
    display_order: int = Form(0),
    db: Session = Depends(get_db)
):
    """Create a new custom field definition"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid entity type. Must be one of: {', '.join(VALID_ENTITY_TYPES)}")

    # Parse options JSON if provided
    options_json = None
    if options and options.strip():
        try:
            options_json = json.dumps(json.loads(options))
        except Exception as e:
            logger.error("Failed to parse options JSON, treating as CSV: %s", e)
            # If not valid JSON, treat as comma-separated values for select
            options_list = [o.strip() for o in options.split(",") if o.strip()]
            options_json = json.dumps(options_list)
    
    # Clean field_name (no spaces, lowercase)
    field_name_clean = field_name.lower().replace(" ", "_").replace("-", "_")
    
    query = text("""
        INSERT INTO custom_field_definitions
        (entity_type, field_name, field_label, field_type, options, required, display_order, org_id)
        VALUES (:entity_type, :field_name, :field_label, :field_type, :options, :required, :display_order, :org_id)
        ON CONFLICT (entity_type, field_name) DO UPDATE SET
            field_label = :field_label,
            field_type = :field_type,
            options = :options,
            required = :required,
            display_order = :display_order
    """)

    db.execute(query, {
        "entity_type": entity_type,
        "field_name": field_name_clean,
        "field_label": field_label,
        "field_type": field_type,
        "options": options_json,
        "required": required,
        "display_order": display_order,
        "org_id": request.state.org_id
    })
    db.commit()
    
    return RedirectResponse(url=f"{PREFIX}/custom-fields?entity_type={entity_type}", status_code=302)

@router.get("/{def_id}/edit", response_class=HTMLResponse)
async def edit_definition(def_id: int, request: Request, db: Session = Depends(get_db)):
    """Edit custom field definition"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    result = db.execute(text("SELECT * FROM custom_field_definitions WHERE id = :id AND org_id = :org_id"), {"id": def_id, "org_id": request.state.org_id})
    definition = result.fetchone()
    
    if not definition:
        raise HTTPException(status_code=404, detail="Definition not found")
    
    return templates.TemplateResponse("app/custom_fields/form.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "definition": definition,
        "action": "Update",
        "entity_types": ["client", "case", "document"],
        "field_types": ["text", "textarea", "number", "date", "select", "checkbox", "file"]
    })

@router.post("/{def_id}/edit")
async def update_definition(
    def_id: int,
    request: Request,
    entity_type: str = Form(...),
    field_name: str = Form(...),
    field_label: str = Form(...),
    field_type: str = Form("text"),
    options: str = Form(None),
    required: bool = Form(False),
    display_order: int = Form(0),
    db: Session = Depends(get_db)
):
    """Update custom field definition"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid entity type. Must be one of: {', '.join(VALID_ENTITY_TYPES)}")

    options_json = None
    if options and options.strip():
        try:
            options_json = json.dumps(json.loads(options))
        except Exception as e:
            logger.error("Failed to parse options JSON on update, treating as CSV: %s", e)
            options_list = [o.strip() for o in options.split(",") if o.strip()]
            options_json = json.dumps(options_list)

    field_name_clean = field_name.lower().replace(" ", "_").replace("-", "_")

    query = text("""
        UPDATE custom_field_definitions SET
            entity_type = :entity_type,
            field_name = :field_name,
            field_label = :field_label,
            field_type = :field_type,
            options = :options,
            required = :required,
            display_order = :display_order
        WHERE id = :id AND org_id = :org_id
    """)

    db.execute(query, {
        "id": def_id,
        "org_id": request.state.org_id,
        "entity_type": entity_type,
        "field_name": field_name_clean,
        "field_label": field_label,
        "field_type": field_type,
        "options": options_json,
        "required": required,
        "display_order": display_order
    })
    db.commit()
    
    return RedirectResponse(url=f"{PREFIX}/custom-fields?entity_type={entity_type}", status_code=302)

@router.post("/{def_id}/delete")
async def delete_definition(def_id: int, request: Request, db: Session = Depends(get_db)):
    """Delete custom field definition and all its values"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    db.execute(text("DELETE FROM custom_field_definitions WHERE id = :id AND org_id = :org_id"), {"id": def_id, "org_id": request.state.org_id})
    db.commit()
    
    return RedirectResponse(url=f"{PREFIX}/custom-fields", status_code=302)

# ============================================
# FIELD VALUES (API for forms)
# ============================================

@router.get("/api/definitions/{entity_type}")
async def api_get_definitions(entity_type: str, request: Request, db: Session = Depends(get_db)):
    """Get all custom field definitions for an entity type"""
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid entity type. Must be one of: {', '.join(VALID_ENTITY_TYPES)}")

    result = db.execute(
        text("SELECT * FROM custom_field_definitions WHERE entity_type = :entity_type AND org_id = :org_id ORDER BY display_order, field_name"),
        {"entity_type": entity_type, "org_id": request.state.org_id}
    )
    definitions = result.fetchall()
    
    return [{
        "id": d.id,
        "field_name": d.field_name,
        "field_label": d.field_label,
        "field_type": d.field_type,
        "options": json.loads(d.options) if d.options else None,
        "required": d.required,
        "display_order": d.display_order
    } for d in definitions]

@router.get("/api/values/{entity_type}/{entity_id}")
async def api_get_values(entity_type: str, entity_id: int, request: Request, db: Session = Depends(get_db)):
    """Get all custom field values for a specific entity"""
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid entity type. Must be one of: {', '.join(VALID_ENTITY_TYPES)}")

    result = db.execute(
        text("""
            SELECT cfv.*, cfd.field_name, cfd.field_label, cfd.field_type
            FROM custom_field_values cfv
            JOIN custom_field_definitions cfd ON cfv.definition_id = cfd.id
            WHERE cfv.entity_type = :entity_type AND cfv.entity_id = :entity_id
              AND cfd.org_id = :org_id
        """),
        {"entity_type": entity_type, "entity_id": entity_id, "org_id": request.state.org_id}
    )
    values = result.fetchall()
    
    return {v.field_name: json.loads(v.value) if v.value else None for v in values}

@router.post("/api/values/{entity_type}/{entity_id}")
async def api_save_values(
    entity_type: str,
    entity_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Save custom field values for an entity"""
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid entity type. Must be one of: {', '.join(VALID_ENTITY_TYPES)}")

    data = await request.json()
    
    for field_name, value in data.items():
        # Get definition ID
        result = db.execute(
            text("SELECT id FROM custom_field_definitions WHERE entity_type = :entity_type AND field_name = :field_name AND org_id = :org_id"),
            {"entity_type": entity_type, "field_name": field_name, "org_id": request.state.org_id}
        )
        definition = result.fetchone()

        if definition:
            value_json = json.dumps(value) if value is not None else None
            
            db.execute(
                text("""
                    INSERT INTO custom_field_values (definition_id, entity_id, entity_type, value, updated_at)
                    VALUES (:definition_id, :entity_id, :entity_type, :value, NOW())
                    ON CONFLICT (definition_id, entity_id, entity_type) DO UPDATE SET
                        value = :value,
                        updated_at = NOW()
                """),
                {
                    "definition_id": definition.id,
                    "entity_id": entity_id,
                    "entity_type": entity_type,
                    "value": value_json
                }
            )
    
    db.commit()
    return {"status": "saved"}

# Helper function to get custom fields for templates
def get_custom_fields_for_entity(db: Session, entity_type: str, entity_id: int = None):
    """Get custom field definitions and values for an entity"""
    try:
        # Get definitions
        result = db.execute(
            text("SELECT * FROM custom_field_definitions WHERE entity_type = :entity_type ORDER BY display_order, field_name"),
            {"entity_type": entity_type}
        )
        definitions = result.fetchall()
    except Exception as e:
        logger.warning("custom_field_definitions table may not exist: %s", e)
        try:
            db.rollback()
        except Exception:
            pass
        return []

    # Get values if entity_id provided
    values = {}
    if entity_id:
        try:
            result = db.execute(
                text("""
                    SELECT cfd.field_name, cfv.value
                    FROM custom_field_values cfv
                    JOIN custom_field_definitions cfd ON cfv.definition_id = cfd.id
                    WHERE cfv.entity_type = :entity_type AND cfv.entity_id = :entity_id
                """),
                {"entity_type": entity_type, "entity_id": entity_id}
            )
            for row in result.fetchall():
                try:
                    values[row.field_name] = json.loads(row.value) if row.value else None
                except (json.JSONDecodeError, TypeError):
                    values[row.field_name] = row.value
        except Exception as e:
            logger.warning("custom_field_values query failed: %s", e)
            try:
                db.rollback()
            except Exception:
                pass

    return [{
        "id": d.id,
        "field_name": d.field_name,
        "field_label": d.field_label,
        "field_type": d.field_type,
        "options": json.loads(d.options) if d.options else None,
        "required": d.required,
        "value": values.get(d.field_name)
    } for d in definitions]

def save_custom_fields_from_form(db: Session, entity_type: str, entity_id: int, form_data: dict):
    """Save custom field values from form submission"""
    try:
        # Get all definitions for this entity type
        result = db.execute(
            text("SELECT id, field_name FROM custom_field_definitions WHERE entity_type = :entity_type"),
            {"entity_type": entity_type}
        )
        definitions = {d.field_name: d.id for d in result.fetchall()}
    except Exception as e:
        logger.warning("custom_field_definitions table may not exist: %s", e)
        try:
            db.rollback()
        except Exception:
            pass
        return

    # Save each custom field value
    for field_name, def_id in definitions.items():
        form_key = f"cf_{field_name}"
        if form_key in form_data:
            value = form_data[form_key]
            value_json = json.dumps(value) if value else None

            try:
                db.execute(
                    text("""
                        INSERT INTO custom_field_values (definition_id, entity_id, entity_type, value, updated_at)
                        VALUES (:definition_id, :entity_id, :entity_type, :value, NOW())
                        ON CONFLICT (definition_id, entity_id, entity_type) DO UPDATE SET
                            value = :value,
                            updated_at = NOW()
                    """),
                    {
                        "definition_id": def_id,
                        "entity_id": entity_id,
                        "entity_type": entity_type,
                        "value": value_json
                    }
                )
            except Exception as e:
                logger.warning("Could not save custom field %s: %s", field_name, e)

    try:
        db.commit()
    except Exception:
        db.rollback()
