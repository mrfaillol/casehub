"""
CaseHub - Auth-gated /uploads endpoint (Sentinela T11 fix, 2026-05-27).

Replaces the public ``app.mount("/uploads", StaticFiles(directory="uploads"))``
hook that exposed every tenant's avatars, logos, email attachments, and AI
knowledge-base files to anonymous clients.

The new contract:

* Every URL requires an authenticated user (cookie or Bearer token).
* The middleware-resolved tenant (``request.state.org_id``) gates access.
* Filesystem layout is ``uploads/org_<org_id>/<kind>/<filename>`` so the
  filter is enforceable both at the path level (writes) and the lookup
  level (reads with DB cross-checks).
* For ``kind=email_attachments`` we additionally cross-check the
  ``email_attachments`` row against ``email_messages.org_id``.
* For ``kind=avatars`` we cross-check ``User.org_id``.
* ``kind`` is whitelisted to refuse traversal-style values.

Refs:
- Sentinela audit ``security-audit-multitenant-2026-05-27.md`` T11.
- Writers updated in the same patch series:
  routes/customizacao.py, routes/profile.py, routes/emails.py,
  routes/emails_compose.py, routes/emails_sync.py, routes/assistente.py.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth import get_current_user
from models import User, get_db

logger = logging.getLogger(__name__)

# Note: this router intentionally has NO prefix. It is registered with the
# top-level prefix in core/app_factory so the URLs look like ``/uploads/...``
# rather than ``/casehub/uploads/...`` — mirrors the previous public mount.
router = APIRouter(tags=["uploads"])


UPLOADS_ROOT = Path(
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
).resolve()

# Whitelisted upload kinds. Anything outside this set is treated as path
# traversal regardless of payload contents.
ALLOWED_KINDS = {
    "avatars",
    "logos",
    "email_attachments",
    "ai_sources",
    "team_chat",  # midia do chat de equipe — gated por MEMBERSHIP do canal (DM privado)
    "appointment_attachments",
}


def _resolved_inside(base: Path, candidate: Path) -> bool:
    """True when ``candidate`` is a descendant of ``base`` after resolution."""
    try:
        base_r = base.resolve()
        candidate_r = candidate.resolve()
    except (OSError, RuntimeError):
        return False
    try:
        candidate_r.relative_to(base_r)
        return True
    except ValueError:
        return False


def _legacy_candidate(kind: str, filename: str) -> Path:
    """Pre-migration layout (uploads/<kind>/<filename>) for backward compat."""
    return (UPLOADS_ROOT / kind / filename).resolve()


def _tenant_candidate(org_id: int, kind: str, filename: str) -> Path:
    return (UPLOADS_ROOT / f"org_{org_id}" / kind / filename).resolve()


def _check_email_attachment(db: Session, org_id: int, filename: str) -> bool:
    """Confirm the attachment row joins through email_messages.org_id."""
    try:
        row = db.execute(
            text(
                """
                SELECT 1
                FROM email_attachments ea
                JOIN email_messages em ON em.id = ea.message_id
                WHERE em.org_id = :org_id
                  AND (
                      ea.file_path LIKE :suffix
                      OR ea.filename = :filename
                  )
                LIMIT 1
                """
            ),
            {
                "org_id": org_id,
                "filename": filename,
                "suffix": f"%/{filename}",
            },
        ).first()
        return row is not None
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("email_attachments check failed: %s", exc)
        return False


def _check_avatar(db: Session, user: User, filename: str) -> bool:
    # Avatares são visíveis para colegas do MESMO tenant (topbar, kanban, chat de
    # equipe) — não são secretos dentro da org. Autoriza se QUALQUER usuário da org
    # do requester usa este arquivo como foto. O isolamento entre orgs continua
    # garantido pelo serve_upload, que resolve o arquivo só em uploads/org_<requester>/.
    if not user or not getattr(user, "org_id", None):
        return False
    from sqlalchemy import text as _text
    row = db.execute(
        _text("SELECT 1 FROM users WHERE org_id = :o AND photo_url LIKE :suf LIMIT 1"),
        {"o": user.org_id, "suf": "%/" + filename},
    ).first()
    return row is not None


def _check_logo(db: Session, org_id: int, filename: str) -> bool:
    """Logos use a deterministic per-org filename (``org_<id>.<ext>``)."""
    return filename.startswith(f"org_{org_id}.")


def _check_ai_source(db: Session, org_id: int, filename: str) -> bool:
    try:
        row = db.execute(
            text(
                """
                SELECT 1
                FROM ai_knowledge_sources
                WHERE org_id = :org_id
                  AND (
                      file_path LIKE :suffix
                      OR file_path = :legacy_path
                  )
                LIMIT 1
                """
            ),
            {
                "org_id": org_id,
                "suffix": f"%/{filename}",
                "legacy_path": str(UPLOADS_ROOT / "ai_sources" / filename),
            },
        ).first()
        return row is not None
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("ai_knowledge_sources check failed: %s", exc)
        return False


def _check_team_chat(db: Session, org_id: int, user_id: int, filename: str) -> bool:
    """Midia do chat de equipe: o arquivo so e' servido se pertencer a uma mensagem
    de um canal de que o caller E MEMBRO. Isso estende a privacidade de DM a' midia —
    um colega da mesma org NAO baixa o anexo de um DM alheio (red line)."""
    try:
        row = db.execute(
            text(
                """
                SELECT 1
                FROM team_messages m
                JOIN team_channel_members mm
                  ON mm.channel_id = m.channel_id AND mm.user_id = :uid
                WHERE m.org_id = :org_id
                  AND m.attachment_path LIKE :suffix
                LIMIT 1
                """
            ),
            {"org_id": org_id, "uid": user_id, "suffix": f"%/{filename}"},
        ).first()
        return row is not None
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("team_chat upload check failed: %s", exc)
        return False


def _appointment_attachment_name(db: Session, org_id: int, filename: str) -> Optional[str]:
    try:
        row = db.execute(
            text(
                """
                SELECT filename
                FROM appointment_attachments
                WHERE org_id = :org_id
                  AND file_path LIKE :suffix
                LIMIT 1
                """
            ),
            {"org_id": org_id, "suffix": f"%/{filename}"},
        ).first()
        return row[0] if row else None
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("appointment_attachments check failed: %s", exc)
        return None


@router.get("/uploads/{kind}/{filename:path}")
async def serve_upload(
    kind: str,
    filename: str,
    request: Request,
    db: Session = Depends(get_db),
) -> FileResponse:
    """Serve an uploaded file iff the caller is authorized for that tenant.

    Path resolution prefers the per-org subdirectory
    (``uploads/org_<org_id>/<kind>/<filename>``) but falls back to the legacy
    flat layout (``uploads/<kind>/<filename>``) so existing files keep
    working through the migration period.
    """

    if kind not in ALLOWED_KINDS:
        raise HTTPException(status_code=404, detail="Not found")

    # Refuse any traversal-looking filename eagerly.
    if "/" in filename or "\\" in filename or filename in {"", ".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")

    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    org_id: Optional[int] = getattr(request.state, "org_id", None)
    if org_id is None:
        # Superadmin or no-tenant flow — let the user.org_id stand in.
        org_id = user.org_id
    if org_id is None:
        raise HTTPException(status_code=403, detail="No tenant context")

    candidates = [
        _tenant_candidate(org_id, kind, filename),
        _legacy_candidate(kind, filename),
    ]

    real_path: Optional[Path] = None
    for candidate in candidates:
        if not _resolved_inside(UPLOADS_ROOT, candidate):
            continue
        if candidate.is_file():
            real_path = candidate
            break

    if real_path is None:
        raise HTTPException(status_code=404, detail="Not found")

    # Per-kind tenancy check.
    authorized = False
    download_filename: Optional[str] = None
    if kind == "email_attachments":
        authorized = _check_email_attachment(db, org_id, filename)
    elif kind == "avatars":
        # Avatars belong to one user; we still confirm same-tenant.
        if (user.org_id or 0) == org_id:
            authorized = _check_avatar(db, user, filename)
    elif kind == "logos":
        authorized = _check_logo(db, org_id, filename)
    elif kind == "ai_sources":
        authorized = _check_ai_source(db, org_id, filename)
    elif kind == "team_chat":
        authorized = _check_team_chat(db, org_id, user.id, filename)
    elif kind == "appointment_attachments":
        download_filename = _appointment_attachment_name(db, org_id, filename)
        authorized = download_filename is not None

    if not authorized:
        logger.warning(
            "Upload denied: user=%s org_id=%s kind=%s filename=%s",
            getattr(user, "email", "?"),
            org_id,
            kind,
            filename,
        )
        raise HTTPException(status_code=404, detail="Not found")

    # nosniff: impede o browser de reinterpretar o conteudo (ex.: svg-em-png) como HTML
    # e executar — Sentinela 2026-05-29-team-chat-media. Aplica a todos os kinds.
    response_kwargs = {"headers": {"X-Content-Type-Options": "nosniff"}}
    if kind == "appointment_attachments" and download_filename:
        response_kwargs["filename"] = download_filename
        response_kwargs["content_disposition_type"] = "attachment"
    return FileResponse(str(real_path), **response_kwargs)
