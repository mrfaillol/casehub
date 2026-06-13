"""REST endpoints powering the /casehub/drive Finder-style explorer.

Three read-only endpoints — list, file, breadcrumb — exposed under
``/api/drive`` so a Codex-owned front-end (the column-view UI) can drive
the experience without dragging in the upload-centric
``GoogleDriveHandler`` surface.

Auth is **session-only** (browser cookie via ``get_current_user``) — these
endpoints never accept a Bearer token. The Drive service is resolved with
``request.state.org_id``, so tenant subdomains use their own OAuth token
instead of falling back to the default organization.

Error contract — exhaustive on purpose:
- 401: not authenticated (missing/invalid session cookie).
- 503: Google Drive not configured on this deploy (no creds, no libs,
       OAuth never completed). Surfaced as ``DriveNotAvailable``.
- 502: Drive returned an error (network, quota, API error). Never 500.
- 404: file not found (Drive returns ``HttpError 404``).
- 200: ok with payload.

Boundaries:
- Read-only — no POST/PUT/DELETE in this router.
- No mutation of CaseHub state — purely a pass-through.
- No new dependency.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from auth import get_current_user
from config import settings
from models import get_db
from services.drive_explorer import (
    DriveNotAvailable,
    breadcrumb,
    get_file,
    list_folder,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/drive", tags=["drive-explorer"])

PREFIX = settings.PREFIX


def _ensure_auth(request: Request, db: Session):
    """Return the current user or a ``JSONResponse(401)``.

    Centralised because every endpoint here needs the same guard, and a
    helper keeps the route bodies focused on the Drive call.
    """
    user = get_current_user(request, db)
    if not user:
        return None, JSONResponse(
            {"error": "Not authenticated", "redirect": f"{PREFIX}/login"},
            status_code=401,
        )
    return user, None


def _drive_error_response(exc: Exception, *, action: str) -> JSONResponse:
    """Map a Drive API exception to an HTTP response.

    HttpError carries a status code on ``.resp.status``; everything else
    (network, JSON decode, etc.) becomes a 502 with a sanitized message so
    we never leak Drive internals or credentials in error payloads.
    """
    try:
        from googleapiclient.errors import HttpError  # noqa: WPS433 — lazy
    except ImportError:
        HttpError = None  # type: ignore[assignment]

    status = 502
    if HttpError is not None and isinstance(exc, HttpError):
        # exc.resp.status is the HTTP code Drive returned (404, 403, 429...)
        try:
            status = int(getattr(getattr(exc, "resp", None), "status", 502))
        except (TypeError, ValueError):
            status = 502

    logger.warning("[DRIVE %s] upstream error (status=%s): %s", action, status, exc)
    return JSONResponse(
        {
            "error": "drive_upstream_error",
            "action": action,
            "status": status,
        },
        status_code=status if status in (401, 403, 404, 429) else 502,
    )


@router.get("/list")
async def list_drive_folder(
    request: Request,
    folder_id: str,
    page_size: int = 50,
    page_token: Optional[str] = None,
    include_trashed: bool = False,
    db: Session = Depends(get_db),
):
    """List the immediate children of ``folder_id`` (folders first, A→Z).

    The Codex column-view UI calls this once per visible column. Pagination
    is opaque to the caller — ``next_page_token`` is round-tripped back.
    """
    user, err = _ensure_auth(request, db)
    if err is not None:
        return err
    org_id = getattr(request.state, "org_id", None)

    try:
        result = list_folder(
            folder_id,
            page_size=page_size,
            page_token=page_token,
            include_trashed=include_trashed,
            org_id=org_id,
        )
    except DriveNotAvailable as exc:
        logger.warning("[DRIVE LIST] service unavailable: %s", exc)
        return JSONResponse(
            {"error": "drive_unavailable", "detail": str(exc)},
            status_code=503,
        )
    except Exception as exc:  # noqa: BLE001 — mapped to 4xx/502, never 500
        return _drive_error_response(exc, action="list")

    return JSONResponse({
        "folder_id": folder_id,
        **result,
    })


@router.get("/file/{file_id}")
async def get_drive_file(
    request: Request,
    file_id: str,
    db: Session = Depends(get_db),
):
    """Fetch full metadata for one Drive object (file or folder)."""
    user, err = _ensure_auth(request, db)
    if err is not None:
        return err
    org_id = getattr(request.state, "org_id", None)

    try:
        payload = get_file(file_id, org_id=org_id)
    except DriveNotAvailable as exc:
        return JSONResponse(
            {"error": "drive_unavailable", "detail": str(exc)},
            status_code=503,
        )
    except Exception as exc:  # noqa: BLE001
        return _drive_error_response(exc, action="file")

    return JSONResponse(payload)


@router.get("/breadcrumb")
async def drive_breadcrumb(
    request: Request,
    file_id: str,
    max_depth: int = 12,
    db: Session = Depends(get_db),
):
    """Return the breadcrumb trail (root → file) for ``file_id``."""
    user, err = _ensure_auth(request, db)
    if err is not None:
        return err
    org_id = getattr(request.state, "org_id", None)

    try:
        trail = breadcrumb(file_id, max_depth=max_depth, org_id=org_id)
    except DriveNotAvailable as exc:
        return JSONResponse(
            {"error": "drive_unavailable", "detail": str(exc)},
            status_code=503,
        )
    except Exception as exc:  # noqa: BLE001
        return _drive_error_response(exc, action="breadcrumb")

    return JSONResponse({"file_id": file_id, "trail": trail})
