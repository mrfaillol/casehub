"""REST endpoints for the Maestro Learning Space (user-scoped corpus).

Five endpoints under ``/casehub/maestro/learn``:

- ``POST /``              create entry
- ``GET  /``              list current user's entries (paginated)
- ``GET  /{id}``          fetch one
- ``PUT  /{id}``          update content / title / tags / enabled
- ``DELETE /{id}``        soft-aware delete (true delete; the *enabled*
                          flag is the soft toggle)

Feature-flagged on ``CASEHUB_MAESTRO_LEARNING_ENABLED`` so the surface
ships in alpha with the **table created** (via ``Base.metadata.create_all``)
but the routes return ``503`` until Council greenlights the pipeline.
This matches ``docs/casehub-alpha/primeiros-passos.md`` ("Maestro pipeline
infra pronta, coletor de treinamento desligado por padrão") without
deferring the backend code itself.

Ownership contract (audit-#514 red line: never leak across users):
- Every read/write filters by ``user_id == current_user.id`` AND
  ``org_id == request.state.org_id``. A user from org A can never
  see/edit/delete an entry from org B even by guessing the integer id.

Boundaries:
- No mutation of the Maestro chat behaviour in this PR. The chat will
  read entries in a follow-up once the flag flips on.
- No new dependency, no migration SQL — the SQLAlchemy model is enough
  because ``Base.metadata.create_all`` runs on app startup.
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import get_current_user
from config import settings
from models import MaestroLearningEntry, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/maestro/learn", tags=["maestro-learn"])

PREFIX = settings.PREFIX

# Hard cap so a single user cannot bloat the corpus. The chat flow
# concatenates content into the system prompt — keeping a per-user cap
# protects the token budget. 200 entries × ~1KB content = ~200KB max
# per user, comfortable below any model's context window.
MAX_ENTRIES_PER_USER = 200

# Per-entry content cap. 16KB is enough for a long SOP / glossary block
# but stops a user pasting a whole codebase as one entry.
MAX_CONTENT_BYTES = 16 * 1024


def _feature_enabled() -> bool:
    """Resolve the feature flag.

    Read order: explicit ``CASEHUB_MAESTRO_LEARNING_ENABLED`` env var, then
    the ``settings`` attribute of the same name (config.py default). The
    flag defaults to **off** — see module docstring.
    """
    raw = os.getenv("CASEHUB_MAESTRO_LEARNING_ENABLED")
    if raw is None:
        raw = getattr(settings, "CASEHUB_MAESTRO_LEARNING_ENABLED", "")
    return (raw or "").lower() in {"1", "true", "yes", "on"}


def _flag_guard() -> Optional[JSONResponse]:
    """Common 503 short-circuit when the feature is off.

    Routes call this before any DB work so a disabled feature never
    exercises the model layer (keeps logs clean, no false N+1 alarms).
    """
    if not _feature_enabled():
        return JSONResponse(
            {
                "error": "feature_disabled",
                "detail": (
                    "Maestro learning space is gated behind "
                    "CASEHUB_MAESTRO_LEARNING_ENABLED — Council ruling "
                    "needed before activation per "
                    "docs/casehub-alpha/primeiros-passos.md."
                ),
            },
            status_code=503,
        )
    return None


def _auth_guard(request: Request, db: Session):
    """Resolve the current user or return a ``JSONResponse(401)``.

    Returns ``(user, None)`` on success, ``(None, response)`` on failure.
    """
    user = get_current_user(request, db)
    if not user:
        return None, JSONResponse(
            {"error": "Not authenticated", "redirect": f"{PREFIX}/login"},
            status_code=401,
        )
    return user, None


def _own_entry(db: Session, entry_id: int, user_id: int, org_id: int):
    """Fetch one entry **owned by this user in this org**.

    Returns the model or ``None``. The route layer converts ``None`` to
    HTTP 404 so a user cannot enumerate other users' entry ids by status
    code (403 vs 404 would leak existence).
    """
    return (
        db.query(MaestroLearningEntry)
        .filter(
            MaestroLearningEntry.id == entry_id,
            MaestroLearningEntry.user_id == user_id,
            MaestroLearningEntry.org_id == org_id,
        )
        .first()
    )


# ---------------------------------------------------------------------------
# Pydantic schemas — pinned so the OpenAPI surface is stable.
# ---------------------------------------------------------------------------


class LearningEntryCreate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    content: str = Field(min_length=1, max_length=MAX_CONTENT_BYTES)
    source: Optional[str] = Field(default="manual", max_length=40)
    tags: Optional[List[str]] = None
    enabled: bool = True


class LearningEntryUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    content: Optional[str] = Field(default=None, max_length=MAX_CONTENT_BYTES)
    source: Optional[str] = Field(default=None, max_length=40)
    tags: Optional[List[str]] = None
    enabled: Optional[bool] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("")
async def create_learning_entry(
    request: Request,
    payload: LearningEntryCreate,
    db: Session = Depends(get_db),
):
    """Create a new learning entry for the authenticated user."""
    if (resp := _flag_guard()) is not None:
        return resp
    user, err = _auth_guard(request, db)
    if err is not None:
        return err

    org_id = getattr(request.state, "org_id", None)

    # Per-user cap protects the token budget the chat flow burns.
    existing = (
        db.query(MaestroLearningEntry)
        .filter(
            MaestroLearningEntry.user_id == user.id,
            MaestroLearningEntry.org_id == org_id,
        )
        .count()
    )
    if existing >= MAX_ENTRIES_PER_USER:
        return JSONResponse(
            {
                "error": "quota_exceeded",
                "detail": (
                    f"Maximum {MAX_ENTRIES_PER_USER} learning entries per "
                    f"user reached. Delete or disable older entries first."
                ),
            },
            status_code=409,
        )

    entry = MaestroLearningEntry(
        org_id=org_id,
        user_id=user.id,
        title=payload.title,
        content=payload.content,
        source=payload.source or "manual",
        tags=payload.tags or [],
        enabled=payload.enabled,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    logger.info(
        "[MAESTRO LEARN] user_id=%s created entry id=%s (%s bytes)",
        user.id,
        entry.id,
        len(payload.content),
    )
    return JSONResponse(entry.to_dict(), status_code=201)


@router.get("")
async def list_learning_entries(
    request: Request,
    enabled_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """List the current user's learning entries (most recent first).

    ``enabled_only`` filters out soft-disabled entries — useful for the
    chat-context preview. ``limit`` is clamped to [1, 200].
    """
    if (resp := _flag_guard()) is not None:
        return resp
    user, err = _auth_guard(request, db)
    if err is not None:
        return err

    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

    org_id = getattr(request.state, "org_id", None)
    q = (
        db.query(MaestroLearningEntry)
        .filter(
            MaestroLearningEntry.user_id == user.id,
            MaestroLearningEntry.org_id == org_id,
        )
        .order_by(MaestroLearningEntry.created_at.desc())
    )
    if enabled_only:
        q = q.filter(MaestroLearningEntry.enabled.is_(True))

    total = q.count()
    items = q.offset(offset).limit(limit).all()

    return JSONResponse({
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [e.to_dict() for e in items],
    })


@router.get("/{entry_id}")
async def get_learning_entry(
    request: Request,
    entry_id: int,
    db: Session = Depends(get_db),
):
    """Fetch a single entry **owned by the current user**."""
    if (resp := _flag_guard()) is not None:
        return resp
    user, err = _auth_guard(request, db)
    if err is not None:
        return err

    org_id = getattr(request.state, "org_id", None)
    entry = _own_entry(db, entry_id, user.id, org_id)
    if not entry:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return JSONResponse(entry.to_dict())


@router.put("/{entry_id}")
async def update_learning_entry(
    request: Request,
    entry_id: int,
    payload: LearningEntryUpdate,
    db: Session = Depends(get_db),
):
    """Partial-update a learning entry. Only owner may update.

    Fields left ``None`` in the payload keep their stored value — this is
    a PATCH semantically (we route it under PUT to keep one endpoint).
    """
    if (resp := _flag_guard()) is not None:
        return resp
    user, err = _auth_guard(request, db)
    if err is not None:
        return err

    org_id = getattr(request.state, "org_id", None)
    entry = _own_entry(db, entry_id, user.id, org_id)
    if not entry:
        return JSONResponse({"error": "not_found"}, status_code=404)

    if payload.title is not None:
        entry.title = payload.title
    if payload.content is not None:
        entry.content = payload.content
    if payload.source is not None:
        entry.source = payload.source
    if payload.tags is not None:
        entry.tags = list(payload.tags)
    if payload.enabled is not None:
        entry.enabled = bool(payload.enabled)

    db.commit()
    db.refresh(entry)
    return JSONResponse(entry.to_dict())


@router.delete("/{entry_id}")
async def delete_learning_entry(
    request: Request,
    entry_id: int,
    db: Session = Depends(get_db),
):
    """Hard-delete a learning entry. Only owner may delete.

    The soft-toggle is ``enabled=false`` (set via PUT) — DELETE is the
    explicit hard removal path. Returns 204 on success, 404 if the entry
    does not belong to the caller (no 403 to avoid id enumeration).
    """
    if (resp := _flag_guard()) is not None:
        return resp
    user, err = _auth_guard(request, db)
    if err is not None:
        return err

    org_id = getattr(request.state, "org_id", None)
    entry = _own_entry(db, entry_id, user.id, org_id)
    if not entry:
        return JSONResponse({"error": "not_found"}, status_code=404)

    db.delete(entry)
    db.commit()
    logger.info("[MAESTRO LEARN] user_id=%s deleted entry id=%s", user.id, entry_id)
    return JSONResponse({"deleted": True, "id": entry_id})
