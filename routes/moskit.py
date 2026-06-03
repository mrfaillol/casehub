"""
CaseHub - Moskit CRM Routes
View and manage Moskit contacts, deals, and activities
"""
from datetime import datetime
from typing import Optional

from core.form_utils import form_int, form_float
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session

from models import get_db, Client
from auth import get_current_user
from models.tenant import tenant_query
from middleware.features import require_feature
from i18n import get_translations
from services.moskit import moskit_service

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/moskit", tags=["moskit"])
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
async def moskit_dashboard(request: Request, db: Session = Depends(get_db), _feature=Depends(require_feature("crm"))):
    """Moskit CRM dashboard."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    return templates.TemplateResponse("app/moskit/dashboard.html", {
        **get_context(request, db),
        "is_configured": moskit_service.is_configured()
    })


@router.get("/api/status")
async def api_get_status(request: Request, db: Session = Depends(get_db)):
    """Get Moskit configuration status."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    return JSONResponse({
        "configured": moskit_service.is_configured(),
        "base_url": moskit_service.base_url
    })


@router.get("/api/contacts")
async def api_get_contacts(
    request: Request,
    limit: int = 50,
    page: int = 1,
    search: str = None,
    leads_only: bool = True,  # Default to only show leads
    refresh: bool = False,  # Force refresh cache
    db: Session = Depends(get_db)
):
    """Get contacts from Moskit. By default, only shows leads with [LEAD] prefix.
    Uses caching to avoid fetching 2000+ contacts every time (10 min TTL).
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    if leads_only:
        # Use the search_leads method which paginates through ALL contacts
        # and filters for [LEAD prefix (handles 2000+ contacts)
        # Results are cached for 10 minutes
        result = await moskit_service.search_leads(prefix="[LEAD", force_refresh=refresh)

        # Apply additional search filter if provided
        if search and result.get("success") and result.get("data"):
            search_lower = search.lower()
            result["data"] = [
                lead for lead in result["data"]
                if search_lower in lead.get("name", "").lower() or
                   search_lower in lead.get("clean_name", "").lower()
            ]

        # Apply limit for display
        if result.get("success") and result.get("data"):
            result["total"] = len(result["data"])
            result["data"] = result["data"][:limit]
    else:
        # Get all contacts without lead filter
        result = await moskit_service.get_contacts(limit=limit, page=page, search=search)

    return JSONResponse(result)


@router.get("/api/contacts/{contact_id}")
async def api_get_contact(
    contact_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get a single contact from Moskit."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    result = await moskit_service.get_contact(contact_id)
    return JSONResponse(result)


@router.get("/api/contacts/search/phone/{phone}")
async def api_search_contact_by_phone(
    phone: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Search contact by phone number."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    result = await moskit_service.search_contact_by_phone(phone)
    return JSONResponse(result)


@router.post("/api/contacts")
async def api_create_contact(
    request: Request,
    name: str = Form(...),
    email: str = Form(None),
    phone: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Create a new contact in Moskit."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    result = await moskit_service.create_contact({
        "name": name,
        "email": email,
        "phone": phone,
        "notes": notes
    })
    return JSONResponse(result)


@router.get("/api/deals")
async def api_get_deals(
    request: Request,
    limit: int = 50,
    page: int = 1,
    status: str = None,
    db: Session = Depends(get_db)
):
    """Get deals from Moskit."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    result = await moskit_service.get_deals(limit=limit, page=page, status=status)
    return JSONResponse(result)


@router.get("/api/deals/{deal_id}")
async def api_get_deal(
    deal_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get a single deal from Moskit."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    result = await moskit_service.get_deal(deal_id)
    return JSONResponse(result)


@router.post("/api/deals")
async def api_create_deal(
    request: Request,
    name: str = Form(...),
    contact_id: str = Form(None),
    value: str = Form(None),
    stage_id: str = Form(None),
    db: Session = Depends(get_db)
):
    """Create a new deal in Moskit."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # Convert form strings to proper types
    contact_id = form_int(contact_id)
    stage_id = form_int(stage_id)
    value = form_float(value)

    result = await moskit_service.create_deal({
        "name": name,
        "contact_id": contact_id,
        "value": value,
        "stage_id": stage_id
    })
    return JSONResponse(result)


@router.get("/api/activities")
async def api_get_activities(
    request: Request,
    contact_id: int = None,
    deal_id: int = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get activities from Moskit."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    result = await moskit_service.get_activities(contact_id=contact_id, deal_id=deal_id, limit=limit)
    return JSONResponse(result)


@router.post("/api/activities")
async def api_create_activity(
    request: Request,
    title: str = Form(...),
    description: str = Form(None),
    contact_id: str = Form(None),
    deal_id: str = Form(None),
    db: Session = Depends(get_db)
):
    """Create an activity in Moskit."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # Convert form strings to proper types
    contact_id = form_int(contact_id)
    deal_id = form_int(deal_id)

    result = await moskit_service.create_activity({
        "title": title,
        "description": description,
        "contact_id": contact_id,
        "deal_id": deal_id
    })
    return JSONResponse(result)


@router.get("/api/pipelines")
async def api_get_pipelines(request: Request, db: Session = Depends(get_db)):
    """Get pipelines/stages from Moskit."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    result = await moskit_service.get_pipelines()
    return JSONResponse(result)


@router.post("/api/sync-client/{client_id}")
async def api_sync_client_to_moskit(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Sync a CaseHub client to Moskit."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        return JSONResponse({"error": "Client not found"}, status_code=404)

    # Check if client already exists in Moskit by phone
    phone = client.phone or client.whatsapp
    if phone:
        existing = await moskit_service.search_contact_by_phone(phone)
        if existing.get("found"):
            return JSONResponse({
                "success": True,
                "message": "Contact already exists in Moskit",
                "moskit_id": existing["data"]["id"]
            })

    # Create new contact in Moskit
    result = await moskit_service.create_contact({
        "name": f"{client.first_name} {client.last_name}".strip(),
        "email": client.email,
        "phone": phone,
        "notes": f"CaseHub Client ID: {client.id}"
    })

    return JSONResponse(result)
