"""
CaseHub — Template Archive
Serve versões arquivadas de templates em `templates/_archive/<path>/<version>.html`.
Alimenta o botão "versões anteriores" da titlebar (window-manager.js).
"""
import json
import os
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from models import get_db, User
from auth import get_current_user
from core.template_config import templates, PREFIX, mock_preview_context

router = APIRouter(prefix="/templates/_archive", tags=["template-archive"])

ARCHIVE_ROOT = os.path.join("templates", "_archive")


def require_superadmin(request: Request, db: Session) -> User:
    """Require superadmin user (issue #805 / T9). Returns user or None."""
    user = get_current_user(request, db)
    if not user or user.user_type != "superadmin":
        return None
    return user


def _safe_path(path: str) -> str:
    # Bloqueia traversal — joins e verifica que continua dentro de ARCHIVE_ROOT
    full = os.path.normpath(os.path.join(ARCHIVE_ROOT, path))
    if not full.startswith(ARCHIVE_ROOT + os.sep) and full != ARCHIVE_ROOT:
        raise HTTPException(status_code=400, detail="invalid path")
    return full


@router.get("/_index/{template_path:path}", response_class=JSONResponse)
async def list_versions(template_path: str, request: Request, db: Session = Depends(get_db)):
    """Lista versões disponíveis de um template. Ex: GET /templates/_archive/_index/login.html"""
    if not require_superadmin(request, db):
        raise HTTPException(status_code=403, detail="forbidden")
    folder = _safe_path(template_path)
    manifest = os.path.join(folder, "_versions.json")
    if not os.path.isfile(manifest):
        return {"template": template_path, "versions": []}
    with open(manifest, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return {"template": template_path, "versions": []}
    return {"template": template_path, "versions": data.get("versions", [])}


@router.get("/{template_path:path}", response_class=HTMLResponse)
async def serve_version(request: Request, template_path: str, v: str = "", db: Session = Depends(get_db)):
    """Renderiza versão arquivada. Ex: GET /templates/_archive/login.html?v=2024-sprint1"""
    if not require_superadmin(request, db):
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    if not v:
        raise HTTPException(status_code=400, detail="query param 'v' required")
    # CWE-22: `v` é concatenado no path do arquivo — bloqueia traversal
    # (Sentinela T9 C3). _safe_path só guarda template_path, não o `v`.
    if "/" in v or "\\" in v or ".." in v or v.startswith("."):
        raise HTTPException(status_code=400, detail="invalid version")
    folder = _safe_path(template_path)
    fname = f"{v}.html"
    full = os.path.join(folder, fname)
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail=f"version '{v}' not found for {template_path}")
    # Renderiza via Jinja compartilhado com contexto mock (archive é preview fora
    # do fluxo real — não tem user/org/sessão). Se o Jinja estourar por template
    # com sintaxe legada, fallback serve HTML bruto pra não quebrar o painel.
    rel = os.path.relpath(full, "templates")
    ctx = mock_preview_context(request)
    ctx["archived_version"] = v
    try:
        return templates.TemplateResponse(rel, ctx)
    except Exception as exc:
        with open(full, "r", encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
        return HTMLResponse(
            f"<!-- archive preview (raw, Jinja render falhou: {type(exc).__name__}: {exc}) -->\n"
            + raw,
            status_code=200,
        )
