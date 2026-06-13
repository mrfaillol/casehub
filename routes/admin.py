"""
CaseHub - Admin Routes
"""
from urllib.parse import quote_plus

import secrets
import logging

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional

from models import get_db, User, Client, Case, Document
from auth import get_current_user
from models.tenant import tenant_query


def _ensure_welcome_schema(db: Session) -> None:
    """Garante (idempotente) a coluna do flag de convite pendente.

    Usada SOMENTE via SQL cru — de propósito não entra no ORM model User, para
    não fazer toda query de User selecioná-la (evita o 500 de coluna inexistente
    em deploy/ambiente onde o ALTER ainda não rodou). ADD COLUMN IF NOT EXISTS
    é no-op quando já existe."""
    try:
        db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS welcome_email_pending BOOLEAN DEFAULT FALSE"))
        db.commit()
    except Exception:
        db.rollback()

# PREFIX = "/casehub"  # Imported from template_config.py

# Valid roles a user can be assigned. "email" is globally unique, so creation
# must guard against duplicates BEFORE flushing to avoid an unhandled
# IntegrityError (which surfaced as a 500 / broken "invite member" flow).
VALID_USER_TYPES = {
    "superadmin", "admin", "attorney", "paralegal", "case_worker", "staff", "assistant",
}

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

    # Convites de boas-vindas pendentes (e-mail não entregue) — alimenta o banner de reenvio.
    _ensure_welcome_schema(db)
    try:
        pending_welcome = db.execute(
            text("SELECT COUNT(*) FROM users WHERE org_id = :org AND welcome_email_pending = TRUE AND last_activity IS NULL"),
            {"org": request.state.org_id},
        ).scalar() or 0
    except Exception:
        db.rollback()
        pending_welcome = 0

    return templates.TemplateResponse("app/admin/users.html", {
        "request": request,
        "user": user,
        "pending_welcome": pending_welcome,
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
        "action": "Create",
        "error": request.query_params.get("error"),
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

    # Only admins / superadmins may create users (matches the menu gate).
    if user.user_type not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Forbidden")

    email = (email or "").strip().lower()
    name = (name or "").strip()
    if user_type not in VALID_USER_TYPES:
        user_type = "case_worker"

    # email is GLOBALLY unique — duplicate insert raises IntegrityError -> 500.
    # Check first and return a friendly error to the form instead of crashing.
    if not email or "@" not in email:
        msg = quote_plus("E-mail inválido.")
        return RedirectResponse(url=f"{PREFIX}/admin/users/new?error={msg}", status_code=302)

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        msg = quote_plus(f"Já existe um usuário com o e-mail {email}.")
        return RedirectResponse(url=f"{PREFIX}/admin/users/new?error={msg}", status_code=302)

    new_user = User(
        name=name,
        email=email,
        password_hash=User.hash_password(password),
        user_type=user_type,
        enabled=True,
        # New member inherits the inviter's organization (multi-tenant scope).
        org_id=request.state.org_id)
    db.add(new_user)
    try:
        db.commit()
    except Exception:
        # Defensive: race on the unique email between check and commit.
        db.rollback()
        msg = quote_plus(f"Já existe um usuário com o e-mail {email}.")
        return RedirectResponse(url=f"{PREFIX}/admin/users/new?error={msg}", status_code=302)

    # Welcome e-mail with login + password to the new user. Org-scoped login
    # URL is derived from the request host (the tenant subdomain), never
    # hardcoded — so a user created on sampletenant.casehub.legal receives that
    # exact login URL. Sending failures must NOT break user creation; the user
    # already exists in the DB, the e-mail is a best-effort courtesy channel.
    try:
        from services.email_service import email_service
        scheme = request.url.scheme or "https"
        host = request.headers.get("host") or request.url.netloc
        login_url = f"{scheme}://{host}{PREFIX}/login"
        org_name = getattr(getattr(request.state, "org", None), "name", None)
        result = email_service.send_welcome_credentials(
            to_email=new_user.email,
            user_name=new_user.name,
            login_email=new_user.email,
            password=password,
            login_url=login_url,
            org_name=org_name,
            # org_id routes the send through the org's connected Google office
            # account (Gmail API/OAuth) when SMTP is not configured. Degrades to
            # a logged 'needs_gmail_consent' without breaking user creation.
            org_id=request.state.org_id,
        )
        if not result.get("success"):
            # Log the failure reason but never the password.
            logging.getLogger(__name__).warning(
                "Welcome e-mail not sent to user %s: %s",
                new_user.id, result.get("error"),
            )
            # Marca o convite como pendente para reenvio (ex.: conta Google do
            # escritório ainda sem gmail.send). NÃO guarda a senha (PII): no
            # reenvio uma nova senha temporária é gerada.
            try:
                _ensure_welcome_schema(db)
                db.execute(text("UPDATE users SET welcome_email_pending = TRUE WHERE id = :id"), {"id": new_user.id})
                db.commit()
            except Exception:
                db.rollback()
    except Exception:
        logging.getLogger(__name__).exception(
            "Welcome e-mail crashed for new user %s", new_user.id,
        )

    return RedirectResponse(url=f"{PREFIX}/admin/users", status_code=302)


@router.post("/users/retry-welcome")
async def retry_welcome_emails(request: Request, db: Session = Depends(get_db)):
    """Reenvia os e-mails de boas-vindas pendentes (que falharam na criação, ex.:
    Google do escritório sem gmail.send). Para cada usuário pendente, gera uma
    NOVA senha temporária (a original nunca foi entregue e não é guardada),
    reseta o hash + must_change_password, e dispara o welcome. Limpa o flag só
    no sucesso. Manager-only, org-scoped."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    if user.user_type not in ("admin", "superadmin"):
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    org_id = request.state.org_id
    _ensure_welcome_schema(db)
    try:
        # last_activity IS NULL: nunca rotacionar a senha de quem já usou o sistema
        # (pode ter recebido a senha por outro canal e já logado). Sentinela 5b.
        rows = db.execute(
            text("SELECT id FROM users WHERE org_id = :org AND welcome_email_pending = TRUE AND last_activity IS NULL"),
            {"org": org_id},
        ).fetchall()
    except Exception:
        db.rollback()
        return JSONResponse({"error": "schema"}, status_code=500)
    pending_ids = [r[0] for r in rows]

    from services.email_service import email_service
    scheme = request.url.scheme or "https"
    host = request.headers.get("host") or request.url.netloc
    login_url = f"{scheme}://{host}{PREFIX}/login"
    org_name = getattr(getattr(request.state, "org", None), "name", None)

    sent = 0
    failed = 0
    for uid in pending_ids:
        # Org-scope guard + nunca-logado (defesa em profundidade da query acima).
        u = tenant_query(db, User, org_id).filter(
            User.id == uid, User.last_activity.is_(None)
        ).first()
        if not u:
            continue
        # Sentinela 5a: ENVIA primeiro; só persiste a nova senha (hash) + limpa o
        # flag se o envio funcionar. Um envio que falha NÃO invalida a senha —
        # evita rotação destrutiva a cada retry com o Google ainda sem gmail.send.
        new_pwd = secrets.token_urlsafe(9)
        new_hash = User.hash_password(new_pwd)
        try:
            result = email_service.send_welcome_credentials(
                to_email=u.email,
                user_name=u.name,
                login_email=u.email,
                password=new_pwd,
                login_url=login_url,
                org_name=org_name,
                org_id=org_id,
            )
        except Exception:
            result = {"success": False, "error": "crash"}
        if result.get("success"):
            u.password_hash = new_hash
            u.must_change_password = True
            db.execute(text("UPDATE users SET welcome_email_pending = FALSE WHERE id = :id"), {"id": uid})
            db.commit()
            sent += 1
        else:
            db.rollback()  # nada muda: senha intacta
            failed += 1
            logging.getLogger(__name__).warning(
                "Retry welcome ainda falhou p/ user %s: %s", uid, result.get("error")
            )

    # Trilha de auditoria (sem senha) — rotação de credencial em massa num SaaS jurídico.
    try:
        from services.audit import log_action
        log_action(
            db=db, action="welcome_emails_retried", entity_type="user", entity_id=user.id,
            user_id=user.id, user_email=user.email,
            description=f"Reenvio de convites de acesso: {sent} enviados, {failed} falharam (de {len(pending_ids)} pendentes).",
            request=request,
        )
        db.commit()
    except Exception:
        db.rollback()

    return JSONResponse({"success": True, "sent": sent, "failed": failed, "pending": len(pending_ids)})


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
        "action": "Update",
        "error": request.query_params.get("error"),
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
    
    if user.user_type not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Forbidden")

    edit_user = tenant_query(db, User, request.state.org_id).filter(User.id == user_id).first()
    if not edit_user:
        raise HTTPException(status_code=404, detail="User not found")

    email = (email or "").strip().lower()
    if user_type not in VALID_USER_TYPES:
        user_type = edit_user.user_type

    # Guard the globally-unique email before committing (avoids IntegrityError 500).
    if email and email != edit_user.email:
        clash = db.query(User).filter(User.email == email, User.id != edit_user.id).first()
        if clash:
            msg = quote_plus(f"Já existe um usuário com o e-mail {email}.")
            return RedirectResponse(
                url=f"{PREFIX}/admin/users/{user_id}/edit?error={msg}", status_code=302)

    edit_user.name = (name or "").strip()
    if email:
        edit_user.email = email
    edit_user.user_type = user_type
    edit_user.enabled = enabled

    if password:
        edit_user.password_hash = User.hash_password(password)

    try:
        db.commit()
    except Exception:
        db.rollback()
        msg = quote_plus("Não foi possível salvar (e-mail duplicado?).")
        return RedirectResponse(
            url=f"{PREFIX}/admin/users/{user_id}/edit?error={msg}", status_code=302)

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
