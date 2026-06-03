"""
CaseHub - Template Notes (notion-edit.js backend)

Persistência dos blocos editáveis inline (data-editable-block) em templates.
Escopo: org × user × page × block.

Storage: arquivos JSON em data/notes/<org_id>/<user_id>/<page_key>.json
Trade-off: simples, versionável, sem migração. DB-backed v2 se volume crescer.
"""
import json
import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from core.template_config import PREFIX
from models import get_db
from auth import get_current_user

router = APIRouter(prefix="/api/notes", tags=["template-notes"])

# storage root (fora de templates/ pra não poluir o jinja loader)
NOTES_ROOT = Path(os.environ.get("CASEHUB_NOTES_ROOT", "data/notes"))
NOTES_ROOT.mkdir(parents=True, exist_ok=True)

SAFE_KEY = re.compile(r"^[a-zA-Z0-9_\-]{1,120}$")


def _page_file(org_id: int, user_id: int, page_key: str) -> Path:
    if not SAFE_KEY.match(page_key):
        raise HTTPException(status_code=400, detail="page_key inválida")
    p = NOTES_ROOT / str(org_id) / str(user_id) / f"{page_key}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load(page_file: Path) -> dict:
    if not page_file.exists():
        return {}
    try:
        return json.loads(page_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(page_file: Path, data: dict) -> None:
    tmp = page_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(page_file)


@router.get("/{page_key}")
async def get_page_notes(page_key: str, request: Request, db: Session = Depends(get_db)):
    """Retorna todos os blocos persistidos da página pro user atual."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"blocks": {}}, status_code=200)  # best-effort, não bloqueia
    org_id = getattr(user, "organization_id", 0) or 0
    pf = _page_file(org_id, user.id, page_key)
    return {"blocks": _load(pf)}


@router.post("/{page_key}/{block_key}")
async def save_block(page_key: str, block_key: str, request: Request, db: Session = Depends(get_db)):
    """Persiste conteúdo HTML de um bloco editável."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="unauthorized")
    if not SAFE_KEY.match(block_key):
        raise HTTPException(status_code=400, detail="block_key inválida")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="json inválido")
    content = (payload or {}).get("content", "")
    if not isinstance(content, str):
        raise HTTPException(status_code=400, detail="content deve ser string")
    # Limite de 256KB por bloco — proteção básica
    if len(content) > 262144:
        raise HTTPException(status_code=413, detail="bloco excede 256KB")

    org_id = getattr(user, "organization_id", 0) or 0
    pf = _page_file(org_id, user.id, page_key)
    data = _load(pf)
    data[block_key] = content
    _save(pf, data)
    return {"ok": True, "page": page_key, "block": block_key, "size": len(content)}


@router.delete("/{page_key}/{block_key}")
async def delete_block(page_key: str, block_key: str, request: Request, db: Session = Depends(get_db)):
    """Remove bloco persistido (volta pro default do template)."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="unauthorized")
    org_id = getattr(user, "organization_id", 0) or 0
    pf = _page_file(org_id, user.id, page_key)
    data = _load(pf)
    if block_key in data:
        del data[block_key]
        _save(pf, data)
    return {"ok": True}
