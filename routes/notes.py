"""
CaseHub - Case Notes Routes
Manage case notes with @mentions
"""
from core.form_utils import form_int, form_float
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session

from models import get_db, Case, User
from auth import get_current_user
from models.tenant import tenant_query
from i18n import get_translations
from services.notes import CaseNotesService

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/notes", tags=["notes"])
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


@router.get("/case/{case_id}", response_class=HTMLResponse)
async def case_notes_page(request: Request, case_id: int, db: Session = Depends(get_db)):
    """View notes for a case."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    service = CaseNotesService(db, org_id=request.state.org_id)
    notes = service.get_notes(case_id)
    
    # Get users for @mention autocomplete
    users = tenant_query(db, User, request.state.org_id).filter(User.enabled == True).all()

    return templates.TemplateResponse("app/notes/case.html", {
        **get_context(request, db),
        "case": case,
        "notes": notes,
        "users": users
    })


@router.post("/case/{case_id}")
async def create_note(
    request: Request,
    case_id: int,
    content: str = Form(...),
    is_internal: bool = Form(True),
    parent_id: str = Form(None),
    db: Session = Depends(get_db)
):
    """Create a new note."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # Convert form strings to proper types
    parent_id = form_int(parent_id)

    service = CaseNotesService(db, org_id=request.state.org_id)
    result = service.create_note(case_id, user.id, content, is_internal, parent_id)
    
    if not result.get("success"):
        return JSONResponse(result, status_code=400)
    
    return JSONResponse(result)


@router.put("/{note_id}")
async def update_note(
    request: Request,
    note_id: int,
    content: str = Form(...),
    db: Session = Depends(get_db)
):
    """Update a note."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = CaseNotesService(db, org_id=request.state.org_id)
    result = service.update_note(note_id, user.id, content)
    
    return JSONResponse(result)


@router.delete("/{note_id}")
async def delete_note(
    request: Request,
    note_id: int,
    db: Session = Depends(get_db)
):
    """Delete a note."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = CaseNotesService(db, org_id=request.state.org_id)
    result = service.delete_note(note_id, user.id)
    
    return JSONResponse(result)


@router.get("/mentions")
async def my_mentions(request: Request, unread: bool = False, db: Session = Depends(get_db)):
    """Get current user's mentions."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = CaseNotesService(db, org_id=request.state.org_id)
    mentions = service.get_mentions_for_user(user.id, unread)
    
    return JSONResponse(mentions)


@router.post("/mentions/{mention_id}/read")
async def mark_mention_read(request: Request, mention_id: int, db: Session = Depends(get_db)):
    """Mark a mention as read."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = CaseNotesService(db, org_id=request.state.org_id)
    service.mark_mention_read(mention_id, user.id)
    
    return JSONResponse({"success": True})


@router.get("/api/case/{case_id}")
async def api_get_notes(request: Request, case_id: int, db: Session = Depends(get_db)):
    """API: Get notes for a case."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = CaseNotesService(db, org_id=request.state.org_id)
    notes = service.get_notes(case_id)
    
    return JSONResponse(notes)


@router.get("/api/unread-count")
async def api_unread_count(request: Request, db: Session = Depends(get_db)):
    """API: Get unread mention count."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = CaseNotesService(db, org_id=request.state.org_id)
    count = service.get_unread_count(user.id)
    
    return JSONResponse({"count": count})
