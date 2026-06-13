"""
CaseHub - Client Relationships Routes
Manages relationships between clients (spouse, employer, etc.)
"""
from core.form_utils import form_int, form_float
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from datetime import datetime

from models import get_db, Client, User
from auth import get_current_user
from models.tenant import tenant_query

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/client-relationships", tags=["client-relationships"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py


def get_relationship_types(db: Session):
    """Get all relationship types from lookup table"""
    result = db.execute(text("""
        SELECT id, code, label, reverse_label, category, sort_order
        FROM relationship_types
        ORDER BY sort_order, label
    """))
    return [dict(row._mapping) for row in result]


def get_client_relationships(db: Session, client_id: int):
    """Get all relationships for a client"""
    result = db.execute(text("""
        SELECT
            cr.id,
            cr.client_id,
            cr.related_client_id,
            cr.relationship_type,
            cr.relationship_label,
            cr.is_primary,
            cr.notes,
            cr.created_at,
            rt.label as type_label,
            rt.reverse_label,
            rt.category,
            c.first_name || ' ' || COALESCE(c.last_name, '') as related_client_name,
            c.email as related_client_email,
            c.phone as related_client_phone
        FROM client_relationships cr
        LEFT JOIN relationship_types rt ON rt.code = cr.relationship_type
        LEFT JOIN clients c ON c.id = cr.related_client_id
        WHERE cr.client_id = :client_id
        ORDER BY cr.is_primary DESC, rt.sort_order, cr.created_at DESC
    """), {"client_id": client_id})
    return [dict(row._mapping) for row in result]


def get_reverse_relationships(db: Session, client_id: int):
    """Get relationships where this client is the related party"""
    result = db.execute(text("""
        SELECT
            cr.id,
            cr.client_id as source_client_id,
            cr.relationship_type,
            cr.relationship_label,
            cr.notes,
            cr.created_at,
            rt.label as type_label,
            rt.reverse_label,
            rt.category,
            c.first_name || ' ' || COALESCE(c.last_name, '') as source_client_name,
            c.email as source_client_email
        FROM client_relationships cr
        LEFT JOIN relationship_types rt ON rt.code = cr.relationship_type
        LEFT JOIN clients c ON c.id = cr.client_id
        WHERE cr.related_client_id = :client_id
        ORDER BY cr.created_at DESC
    """), {"client_id": client_id})
    return [dict(row._mapping) for row in result]


@router.get("/client/{client_id}", response_class=HTMLResponse)
async def view_client_relationships(
    request: Request,
    client_id: int,
    db: Session = Depends(get_db)
):
    """View all relationships for a client (Members tab)"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    relationships = get_client_relationships(db, client_id)
    reverse_relationships = get_reverse_relationships(db, client_id)
    relationship_types = get_relationship_types(db)

    # Get all clients for the add relationship form (exclude current client)
    all_clients = tenant_query(db, Client, request.state.org_id).filter(Client.id != client_id).order_by(Client.first_name).all()

    return templates.TemplateResponse("app/clients/relationships.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "client": client,
        "relationships": relationships,
        "reverse_relationships": reverse_relationships,
        "relationship_types": relationship_types,
        "all_clients": all_clients
    })


@router.post("/client/{client_id}/add")
async def add_relationship(
    request: Request,
    client_id: int,
    related_client_id: str = Form(None),
    relationship_type: str = Form(...),
    relationship_label: str = Form(None),
    is_primary: bool = Form(False),
    notes: str = Form(None),
    create_reverse: bool = Form(False),
    db: Session = Depends(get_db)
):
    """Add a new relationship for a client"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Convert form strings to proper types
    related_client_id = form_int(related_client_id)

    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Insert the relationship
    db.execute(text("""
        INSERT INTO client_relationships
        (client_id, related_client_id, relationship_type, relationship_label, is_primary, notes, created_by)
        VALUES (:client_id, :related_client_id, :relationship_type, :relationship_label, :is_primary, :notes, :created_by)
    """), {
        "client_id": client_id,
        "related_client_id": related_client_id,
        "relationship_type": relationship_type,
        "relationship_label": relationship_label or None,
        "is_primary": is_primary,
        "notes": notes or None,
        "created_by": user.id
    })

    # Optionally create reverse relationship
    if create_reverse and related_client_id:
        # Get the reverse label for this relationship type
        rt = db.execute(text("""
            SELECT reverse_label FROM relationship_types WHERE code = :code
        """), {"code": relationship_type}).fetchone()

        reverse_type = relationship_type
        # Some relationships have natural reverses
        reverse_mapping = {
            "employer": "employee",
            "employee": "employer",
            "parent": "child",
            "child": "parent",
            "petitioner": "beneficiary",
            "beneficiary": "petitioner"
        }
        if relationship_type in reverse_mapping:
            reverse_type = reverse_mapping[relationship_type]

        db.execute(text("""
            INSERT INTO client_relationships
            (client_id, related_client_id, relationship_type, relationship_label, is_primary, notes, created_by)
            VALUES (:client_id, :related_client_id, :relationship_type, :relationship_label, :is_primary, :notes, :created_by)
        """), {
            "client_id": related_client_id,
            "related_client_id": client_id,
            "relationship_type": reverse_type,
            "relationship_label": None,
            "is_primary": False,
            "notes": f"Auto-created reverse of {relationship_type}",
            "created_by": user.id
        })

    db.commit()

    return RedirectResponse(url=f"{PREFIX}/clients/{client_id}#members", status_code=302)


@router.post("/{relationship_id}/delete")
async def delete_relationship(
    request: Request,
    relationship_id: int,
    db: Session = Depends(get_db)
):
    """Delete a relationship"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Get the relationship to find the client_id for redirect
    result = db.execute(text("""
        SELECT cr.client_id FROM client_relationships cr
        JOIN clients cl ON cr.client_id = cl.id
        WHERE cr.id = :id AND cl.org_id = :org_id
    """), {"id": relationship_id, "org_id": user.org_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Relationship not found")

    client_id = result[0]

    db.execute(text("""
        DELETE FROM client_relationships
        WHERE id = :id
          AND client_id IN (SELECT id FROM clients WHERE org_id = :org_id)
    """), {"id": relationship_id, "org_id": user.org_id})
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/clients/{client_id}#members", status_code=302)


@router.post("/{relationship_id}/set-primary")
async def set_primary_relationship(
    request: Request,
    relationship_id: int,
    db: Session = Depends(get_db)
):
    """Set a relationship as primary"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Get the relationship
    result = db.execute(text("""
        SELECT cr.client_id, cr.relationship_type FROM client_relationships cr
        JOIN clients cl ON cr.client_id = cl.id
        WHERE cr.id = :id AND cl.org_id = :org_id
    """), {"id": relationship_id, "org_id": user.org_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Relationship not found")

    client_id, rel_type = result

    # Unset other primaries of same type for this client
    db.execute(text("""
        UPDATE client_relationships
        SET is_primary = false
        WHERE client_id = :client_id AND relationship_type = :rel_type
    """), {"client_id": client_id, "rel_type": rel_type})

    # Set this one as primary
    db.execute(text("""
        UPDATE client_relationships
        SET is_primary = true
        WHERE id = :id
    """), {"id": relationship_id})

    db.commit()

    return RedirectResponse(url=f"{PREFIX}/clients/{client_id}#members", status_code=302)


# API Endpoints
@router.get("/api/client/{client_id}")
async def api_get_relationships(
    request: Request,
    client_id: int,
    db: Session = Depends(get_db)
):
    """API: Get all relationships for a client"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    relationships = get_client_relationships(db, client_id)
    reverse_relationships = get_reverse_relationships(db, client_id)

    return JSONResponse({
        "client_id": client_id,
        "relationships": relationships,
        "reverse_relationships": reverse_relationships
    })


@router.get("/api/types")
async def api_get_relationship_types(
    request: Request,
    db: Session = Depends(get_db)
):
    """API: Get all relationship types"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    types = get_relationship_types(db)
    return JSONResponse({"types": types})


@router.post("/api/client/{client_id}/add")
async def api_add_relationship(
    request: Request,
    client_id: int,
    db: Session = Depends(get_db)
):
    """API: Add a relationship"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    data = await request.json()

    db.execute(text("""
        INSERT INTO client_relationships
        (client_id, related_client_id, relationship_type, relationship_label, is_primary, notes, created_by)
        VALUES (:client_id, :related_client_id, :relationship_type, :relationship_label, :is_primary, :notes, :created_by)
    """), {
        "client_id": client_id,
        "related_client_id": data.get("related_client_id"),
        "relationship_type": data.get("relationship_type"),
        "relationship_label": data.get("relationship_label"),
        "is_primary": data.get("is_primary", False),
        "notes": data.get("notes"),
        "created_by": user.id
    })
    db.commit()

    return JSONResponse({"success": True, "message": "Relationship added"})
