"""
CaseHub - Profile Routes
User profile management: view/edit profile, avatar upload, password change.
"""
import os
import uuid
import logging

from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from core.template_config import templates, PREFIX, inject_org_context
from auth import get_current_user
from models import get_db, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profile", tags=["profile"])

# Sentinela T11: avatars live under uploads/org_<id>/avatars/ so the
# auth-gated /uploads route can enforce tenant binding by path prefix.
UPLOADS_BASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
LEGACY_AVATAR_DIR = os.path.join(UPLOADS_BASE, "avatars")
MAX_AVATAR_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}


def _avatar_dir_for(org_id) -> str:
    return os.path.join(UPLOADS_BASE, f"org_{org_id}", "avatars")


@router.get("", response_class=HTMLResponse)
async def profile_page(request: Request, db: Session = Depends(get_db)):
    """Render profile page."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    org_ctx = inject_org_context(request)
    return templates.TemplateResponse("app/profile/index.html", {
        "request": request,
        "PREFIX": PREFIX,
        "user": user,
        "success": request.query_params.get("success"),
        "error": request.query_params.get("error"),
        **org_ctx,
    })


@router.post("", response_class=HTMLResponse)
async def update_profile(
    request: Request,
    name: str = Form(...),
    phone: str = Form(None),
    department: str = Form(None),
    oab_number: str = Form(None),
    bio: str = Form(None),
    db: Session = Depends(get_db),
):
    """Save profile changes."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    user.name = name.strip()
    user.phone = (phone or "").strip() or None
    user.department = (department or "").strip() or None
    user.oab_number = (oab_number or "").strip() or None
    user.bio = (bio or "").strip() or None

    db.commit()
    return RedirectResponse(url=f"{PREFIX}/profile?success=Perfil+atualizado+com+sucesso", status_code=302)


@router.post("/avatar")
async def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Handle photo upload (max 5MB, jpg/png only)."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Validate extension
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        return RedirectResponse(
            url=f"{PREFIX}/profile?error=Formato+invalido.+Use+JPG+ou+PNG", status_code=302
        )

    # Read and validate size
    content = await file.read()
    if len(content) > MAX_AVATAR_SIZE:
        return RedirectResponse(
            url=f"{PREFIX}/profile?error=Arquivo+muito+grande.+Maximo+5MB", status_code=302
        )

    # Save file (Sentinela T11: per-tenant subdirectory)
    org_id = user.org_id if user.org_id is not None else getattr(request.state, "org_id", None)
    avatar_dir = _avatar_dir_for(org_id) if org_id is not None else LEGACY_AVATAR_DIR
    os.makedirs(avatar_dir, exist_ok=True)
    filename = f"{user.id}_{uuid.uuid4().hex[:8]}.{ext}"
    filepath = os.path.join(avatar_dir, filename)

    # Remove old avatar if exists (check both new + legacy locations)
    if user.photo_url:
        old_name = os.path.basename(user.photo_url)
        for candidate in (
            os.path.join(avatar_dir, old_name),
            os.path.join(LEGACY_AVATAR_DIR, old_name),
        ):
            if os.path.exists(candidate):
                try:
                    os.remove(candidate)
                except Exception:
                    pass

    with open(filepath, "wb") as f:
        f.write(content)

    # A URL usa o esquema /uploads/<kind>/<filename> (kind=avatars). A rota
    # serve_upload (routes/uploads.py) resolve o subdir per-tenant
    # uploads/org_<id>/avatars/ INTERNAMENTE (_tenant_candidate). NÃO embutir
    # org_<id> na URL: a rota é /uploads/{kind}/{filename:path} → 'org_N' viraria
    # 'kind' (inválido → 404) e o filename conteria '/' (→ 400 Invalid filename).
    # Era o bug do upload de foto do Victor (03/06): imagem sempre quebrada.
    user.photo_url = f"/uploads/avatars/{filename}"
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/profile?success=Foto+atualizada", status_code=302)


@router.post("/password")
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    """Change password with current password verification."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    if not user.verify_password(current_password):
        return RedirectResponse(
            url=f"{PREFIX}/profile?error=Senha+atual+incorreta", status_code=302
        )

    if new_password != confirm_password:
        return RedirectResponse(
            url=f"{PREFIX}/profile?error=As+senhas+nao+coincidem", status_code=302
        )

    if len(new_password) < 8:
        return RedirectResponse(
            url=f"{PREFIX}/profile?error=Senha+deve+ter+no+minimo+8+caracteres", status_code=302
        )

    user.password_hash = User.hash_password(new_password)
    user.must_change_password = False
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/profile?success=Senha+alterada+com+sucesso", status_code=302)
