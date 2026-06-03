"""
CaseHub - Contacts/Member Linking Routes
Manage contacts and relationships.
"""
from typing import Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, User, Client, Case
from auth import get_current_user
from models.tenant import tenant_query
from services.contacts_service import contacts_service, CREATE_CONTACTS_TABLE, ContactType

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/contacts", tags=["contacts"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py


def ensure_tables(db: Session):
    """Ensure contacts tables exist."""
    try:
        db.execute(text(CREATE_CONTACTS_TABLE))
        db.commit()
    except Exception as e:
        db.rollback()


@router.get("", response_class=HTMLResponse)
async def contacts_list(
    request: Request,
    contact_type: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all contacts."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    # Build query
    query = "SELECT * FROM contacts WHERE org_id = :org_id"
    params = {"org_id": request.state.org_id}

    if contact_type:
        query += " AND contact_type = :type"
        params["type"] = contact_type

    if search:
        query += " AND (name ILIKE :search OR company ILIKE :search OR email ILIKE :search)"
        params["search"] = f"%{search}%"

    query += " ORDER BY name"

    try:
        result = db.execute(text(query), params)
        contacts = result.fetchall()
    except Exception:
        db.rollback()
        contacts = []

    # Get type counts
    try:
        counts_result = db.execute(text("""
            SELECT contact_type, COUNT(*) as count
            FROM contacts
            WHERE org_id = :org_id
            GROUP BY contact_type
        """), {"org_id": request.state.org_id})
        type_counts = {row.contact_type: row.count for row in counts_result.fetchall()}
    except Exception:
        db.rollback()
        type_counts = {}

    return templates.TemplateResponse("app/contacts/list.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "contacts": contacts,
        "type_counts": type_counts,
        "selected_type": contact_type,
        "search": search,
        "contact_types": contacts_service.get_contact_types()
    })


@router.get("/new", response_class=HTMLResponse)
async def new_contact(
    request: Request,
    db: Session = Depends(get_db)
):
    """Create new contact form."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    return templates.TemplateResponse("app/contacts/create.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "contact_types": contacts_service.get_contact_types()
    })


@router.post("/create")
async def create_contact(
    request: Request,
    contact_type: str = Form(...),
    name: str = Form(...),
    company: str = Form(None),
    title: str = Form(None),
    email: str = Form(None),
    phone: str = Form(None),
    address: str = Form(None),
    city: str = Form(None),
    state: str = Form(None),
    zip_code: str = Form(None),
    country: str = Form("USA"),
    website: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Create a new contact."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ensure_tables(db)

    try:
        db.execute(text("""
            INSERT INTO contacts
            (contact_type, name, company, title, email, phone, address, city, state, zip_code, country, website, notes, created_by, org_id)
            VALUES (:type, :name, :company, :title, :email, :phone, :address, :city, :state, :zip, :country, :website, :notes, :uid, :org_id)
        """), {
            "type": contact_type,
            "name": name,
            "company": company,
            "title": title,
            "email": email,
            "phone": phone,
            "address": address,
            "city": city,
            "state": state,
            "zip": zip_code,
            "country": country,
            "website": website,
            "notes": notes,
            "uid": user.id,
            "org_id": request.state.org_id
        })
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/contacts", status_code=302)


@router.get("/{contact_id}/edit", response_class=HTMLResponse)
async def edit_contact_form(
    request: Request,
    contact_id: int,
    db: Session = Depends(get_db)
):
    """Edit contact form (pre-filled)."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    try:
        result = db.execute(
            text("SELECT * FROM contacts WHERE id = :id AND org_id = :org_id"),
            {"id": contact_id, "org_id": request.state.org_id}
        )
        contact = result.fetchone()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    return templates.TemplateResponse("app/contacts/create.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "contact": contact,
        "contact_types": contacts_service.get_contact_types()
    })


@router.post("/{contact_id}/edit")
async def update_contact(
    request: Request,
    contact_id: int,
    contact_type: str = Form(...),
    name: str = Form(...),
    company: str = Form(None),
    title: str = Form(None),
    email: str = Form(None),
    phone: str = Form(None),
    address: str = Form(None),
    city: str = Form(None),
    state: str = Form(None),
    zip_code: str = Form(None),
    country: str = Form("USA"),
    website: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Update an existing contact."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ensure_tables(db)

    # Ensure the contact exists and belongs to this tenant before updating.
    existing = db.execute(
        text("SELECT id FROM contacts WHERE id = :id AND org_id = :org_id"),
        {"id": contact_id, "org_id": request.state.org_id}
    ).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Contact not found")

    try:
        db.execute(text("""
            UPDATE contacts
            SET contact_type = :type,
                name = :name,
                company = :company,
                title = :title,
                email = :email,
                phone = :phone,
                address = :address,
                city = :city,
                state = :state,
                zip_code = :zip,
                country = :country,
                website = :website,
                notes = :notes,
                updated_at = NOW()
            WHERE id = :id AND org_id = :org_id
        """), {
            "type": contact_type,
            "name": name,
            "company": company,
            "title": title,
            "email": email,
            "phone": phone,
            "address": address,
            "city": city,
            "state": state,
            "zip": zip_code,
            "country": country,
            "website": website,
            "notes": notes,
            "id": contact_id,
            "org_id": request.state.org_id
        })
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/contacts/{contact_id}", status_code=302)


@router.get("/{contact_id}", response_class=HTMLResponse)
async def view_contact(
    request: Request,
    contact_id: int,
    db: Session = Depends(get_db)
):
    """View contact details and relationships."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    try:
        # Get contact
        result = db.execute(text("SELECT * FROM contacts WHERE id = :id AND org_id = :org_id"), {"id": contact_id, "org_id": request.state.org_id})
        contact = result.fetchone()

        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")

        # Get relationships where this contact is the "from"
        # Sentinela T4 (2026-05-28): cada subquery cross-entity precisa filtrar
        # por org_id. O WHERE externo escopa as rows de entity_relationships, mas
        # to_entity_id é user-controlled na criação (add_relationship não valida
        # ownership), então um relationship apontando pra client/contact/case de
        # outro tenant vazaria nome/case_name. CWE-639.
        rel_from = db.execute(text("""
            SELECT r.*,
                   CASE
                       WHEN r.to_entity_type = 'client' THEN (SELECT first_name || ' ' || last_name FROM clients WHERE id = r.to_entity_id AND org_id = :org_id)
                       WHEN r.to_entity_type = 'contact' THEN (SELECT name FROM contacts WHERE id = r.to_entity_id AND org_id = :org_id)
                       WHEN r.to_entity_type = 'case' THEN (SELECT case_name FROM cases WHERE id = r.to_entity_id AND org_id = :org_id)
                   END as to_name
            FROM entity_relationships r
            WHERE r.from_entity_id = :id AND r.from_entity_type = 'contact' AND r.org_id = :org_id
        """), {"id": contact_id, "org_id": request.state.org_id}).fetchall()

        # Get relationships where this contact is the "to"
        # Sentinela T4 (2026-05-28): mesmo fix do rel_from — subqueries
        # cross-entity escopadas por org_id pra evitar IDOR. CWE-639.
        rel_to = db.execute(text("""
            SELECT r.*,
                   CASE
                       WHEN r.from_entity_type = 'client' THEN (SELECT first_name || ' ' || last_name FROM clients WHERE id = r.from_entity_id AND org_id = :org_id)
                       WHEN r.from_entity_type = 'contact' THEN (SELECT name FROM contacts WHERE id = r.from_entity_id AND org_id = :org_id)
                       WHEN r.from_entity_type = 'case' THEN (SELECT case_name FROM cases WHERE id = r.from_entity_id AND org_id = :org_id)
                   END as from_name
            FROM entity_relationships r
            WHERE r.to_entity_id = :id AND r.to_entity_type = 'contact' AND r.org_id = :org_id
        """), {"id": contact_id, "org_id": request.state.org_id}).fetchall()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Get clients and cases for relationship creation
    clients = tenant_query(db, Client, request.state.org_id).order_by(Client.first_name).all()
    cases = tenant_query(db, Case, request.state.org_id).order_by(Case.created_at.desc()).limit(50).all()
    contacts_list = db.execute(text("SELECT id, name FROM contacts WHERE id != :id AND org_id = :org_id ORDER BY name"), {"id": contact_id, "org_id": request.state.org_id}).fetchall()

    return templates.TemplateResponse("contacts/view.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "contact": contact,
        "relationships_from": rel_from,
        "relationships_to": rel_to,
        "clients": clients,
        "cases": cases,
        "contacts": contacts_list,
        "relationship_types": contacts_service.get_relationship_types()
    })


@router.post("/{contact_id}/link")
async def create_relationship(
    request: Request,
    contact_id: int,
    to_entity_type: str = Form(...),
    to_entity_id: int = Form(...),
    relationship: str = Form(...),
    start_date: str = Form(None),
    end_date: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Create a relationship from this contact to another entity."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Parse dates
    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        except Exception:
            db.rollback()
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        except Exception:
            db.rollback()

    rel_data = contacts_service.create_relationship(
        from_id=contact_id,
        from_type="contact",
        to_id=to_entity_id,
        to_type=to_entity_type,
        relationship=relationship,
        start_date=start_dt,
        end_date=end_dt,
        notes=notes
    )

    try:
        db.execute(text("""
            INSERT INTO entity_relationships
            (from_entity_id, from_entity_type, to_entity_id, to_entity_type, relationship, inverse_relationship, category, start_date, end_date, notes, created_by, org_id)
            VALUES (:from_id, :from_type, :to_id, :to_type, :rel, :inv_rel, :cat, :start, :end, :notes, :uid, :org_id)
            ON CONFLICT DO NOTHING
        """), {
            "from_id": contact_id,
            "from_type": "contact",
            "to_id": to_entity_id,
            "to_type": to_entity_type,
            "rel": relationship,
            "inv_rel": rel_data["inverse_relationship"],
            "cat": rel_data["category"],
            "start": start_dt,
            "end": end_dt,
            "notes": notes,
            "uid": user.id,
            "org_id": request.state.org_id
        })
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/contacts/{contact_id}", status_code=302)


@router.post("/{contact_id}/delete")
async def delete_contact(
    request: Request,
    contact_id: int,
    db: Session = Depends(get_db)
):
    """Delete a contact."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        # Delete relationships first
        db.execute(text("""
            DELETE FROM entity_relationships
            WHERE ((from_entity_id = :id AND from_entity_type = 'contact')
               OR (to_entity_id = :id AND to_entity_type = 'contact'))
               AND org_id = :org_id
        """), {"id": contact_id, "org_id": request.state.org_id})

        db.execute(text("DELETE FROM contacts WHERE id = :id AND org_id = :org_id"), {"id": contact_id, "org_id": request.state.org_id})
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/contacts", status_code=302)


@router.post("/relationship/{rel_id}/delete")
async def delete_relationship(
    request: Request,
    rel_id: int,
    redirect_to: str = Form(None),
    db: Session = Depends(get_db)
):
    """Delete a relationship."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        db.execute(text("DELETE FROM entity_relationships WHERE id = :id AND org_id = :org_id"), {"id": rel_id, "org_id": request.state.org_id})
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    if redirect_to:
        return RedirectResponse(url=redirect_to, status_code=302)
    return RedirectResponse(url=f"{PREFIX}/contacts", status_code=302)


# === API Endpoints ===

@router.get("/api/search", response_class=JSONResponse)
async def search_contacts(
    request: Request,
    q: str,
    contact_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """API: Search contacts."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})

    query = """
        SELECT id, name, company, email, contact_type
        FROM contacts
        WHERE org_id = :org_id AND (name ILIKE :q OR company ILIKE :q OR email ILIKE :q)
    """
    params = {"q": f"%{q}%", "org_id": request.state.org_id}

    if contact_type:
        query += " AND contact_type = :type"
        params["type"] = contact_type

    query += " ORDER BY name LIMIT 20"

    try:
        result = db.execute(text(query), params)
        contacts = [dict(row._mapping) for row in result.fetchall()]
        return JSONResponse(content=contacts)
    except Exception as e:
        logger.error("Failed to search contacts: %s", e)
        return JSONResponse(content=[])


@router.get("/api/relationships/{entity_type}/{entity_id}", response_class=JSONResponse)
async def get_relationships(
    request: Request,
    entity_type: str,
    entity_id: int,
    db: Session = Depends(get_db)
):
    """API: Get all relationships for an entity."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})

    try:
        result = db.execute(text("""
            SELECT * FROM entity_relationships
            WHERE ((from_entity_id = :id AND from_entity_type = :type)
               OR (to_entity_id = :id AND to_entity_type = :type))
               AND org_id = :org_id
        """), {"id": entity_id, "type": entity_type, "org_id": request.state.org_id})
        relationships = [dict(row._mapping) for row in result.fetchall()]
        return JSONResponse(content=relationships)
    except Exception as e:
        logger.error("Failed to get relationships: %s", e)
        return JSONResponse(content=[])
