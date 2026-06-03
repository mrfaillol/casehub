"""
CaseHub - Admin Routes
"""
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from typing import Optional

from models import get_db, User, Client, Case, Document
from auth import get_current_user
from models.tenant import tenant_query

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/admin", tags=["admin"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py

def require_admin(request: Request, db: Session):
    user = get_current_user(request, db)
    if not user or user.user_type != "admin":
        return None
    return user

@router.get("", response_class=HTMLResponse)
async def admin_home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    stats = {
        "users": tenant_query(db, User, request.state.org_id).count(),
        "clients": tenant_query(db, Client, request.state.org_id).count(),
        "cases": tenant_query(db, Case, request.state.org_id).count(),
        "documents": tenant_query(db, Document, request.state.org_id).count()
    }
    
    return templates.TemplateResponse("app/admin/home.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "stats": stats
    })

# User Management
@router.get("/users", response_class=HTMLResponse)
async def list_users(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    users = tenant_query(db, User, request.state.org_id).order_by(User.name).all()
    
    return templates.TemplateResponse("app/admin/users.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "users": users
    })

@router.get("/users/new", response_class=HTMLResponse)
async def new_user_form(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    return templates.TemplateResponse("app/admin/user_form.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "edit_user": None,
        "action": "Create"
    })

@router.post("/users/new")
async def create_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    user_type: str = Form("case_worker"),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    new_user = User(
        name=name,
        email=email,
        password_hash=User.hash_password(password),
        user_type=user_type,
        org_id=request.state.org_id)
    db.add(new_user)
    db.commit()
    
    return RedirectResponse(url=f"{PREFIX}/admin/users", status_code=302)

@router.get("/users/{user_id}/edit", response_class=HTMLResponse)
async def edit_user_form(request: Request, user_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    edit_user = tenant_query(db, User, request.state.org_id).filter(User.id == user_id).first()
    if not edit_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return templates.TemplateResponse("app/admin/user_form.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "edit_user": edit_user,
        "action": "Update"
    })

@router.post("/users/{user_id}/edit")
async def update_user(
    request: Request,
    user_id: int,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(None),
    user_type: str = Form("case_worker"),
    enabled: bool = Form(True),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    edit_user = tenant_query(db, User, request.state.org_id).filter(User.id == user_id).first()
    if not edit_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    edit_user.name = name
    edit_user.email = email
    edit_user.user_type = user_type
    edit_user.enabled = enabled
    
    if password:
        edit_user.password_hash = User.hash_password(password)
    
    db.commit()
    
    return RedirectResponse(url=f"{PREFIX}/admin/users", status_code=302)

@router.post("/users/{user_id}/delete")
async def delete_user(request: Request, user_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    del_user = tenant_query(db, User, request.state.org_id).filter(User.id == user_id).first()
    if del_user and del_user.id != user.id:
        db.delete(del_user)
        db.commit()
    
    return RedirectResponse(url=f"{PREFIX}/admin/users", status_code=302)

# Settings
@router.get("/settings", response_class=HTMLResponse)
async def settings(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    return templates.TemplateResponse("app/admin/settings.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX
    })


def _gdrive_auto_sync_available(request: Request) -> bool:
    route_paths = {getattr(route, "path", "") for route in request.app.routes}
    auto_sync_paths = {
        "/admin/gdrive-sync/api/auto-sync-status",
        "/admin/gdrive-sync/api/auto-sync-toggle",
    }
    prefixed_paths = {f"{PREFIX.rstrip('/')}{path}" for path in auto_sync_paths}
    return auto_sync_paths.issubset(route_paths) or prefixed_paths.issubset(route_paths)


# Google Drive Sync Admin
@router.get("/gdrive-sync", response_class=HTMLResponse)
async def gdrive_sync_admin(request: Request, db: Session = Depends(get_db)):
    """Google Drive Sync administration page."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    from sqlalchemy import func, text
    
    # Get sync statistics
    total_docs = tenant_query(db, Document, request.state.org_id).with_entities(func.count(Document.id)).scalar()
    synced = tenant_query(db, Document, request.state.org_id).with_entities(func.count(Document.id)).filter(
        Document.drive_link.isnot(None)
    ).scalar()
    hashed = tenant_query(db, Document, request.state.org_id).with_entities(func.count(Document.id)).filter(
        Document.file_hash.isnot(None)
    ).scalar()
    
    stats = {
        "total_documents": total_docs or 0,
        "synced_to_drive": synced or 0,
        "hashed_locally": hashed or 0,
        "sync_percentage": round((synced / total_docs * 100) if total_docs > 0 else 0, 1)
    }
    
    return templates.TemplateResponse("gdrive_sync_admin.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "stats": stats,
        "auto_sync_available": _gdrive_auto_sync_available(request)
    })
