"""Read-only Google Drive explorer for the CaseHub /api/drive REST surface.

This module is intentionally separate from ``services.google_drive_handler``
(which is upload-centric and stateful — caches folder IDs, owns the "Active
Clients" root, drops files into per-client folders). The explorer needs
none of that: it is a thin **read** wrapper that lists arbitrary folders,
fetches arbitrary file metadata and resolves breadcrumb paths.

Mounted by ``routes/drive_explorer.py`` (the Codex UI calls these endpoints
to render a Finder-style column view). The explorer reuses
``get_drive_service()`` so OAuth/token handling stays in one place.

Boundaries:
- **Read-only.** No create / update / delete / upload. Mutation lives in
  ``GoogleDriveHandler``.
- **No global state.** Each call constructs a fresh service via
  ``get_drive_service()``; pooling can be added later if profiling shows a
  hot path.
- **No credential at module level.** Same security contract as
  ``services/pdpj_client.py`` (PR #550).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from services.google_drive_handler import get_drive_service

logger = logging.getLogger(__name__)


# Fields requested from the Drive v3 API. Keeping the projection tight cuts
# response size and avoids ever requesting permissions / acl data the UI does
# not need.
_LIST_FIELDS = (
    "nextPageToken, "
    "files(id, name, mimeType, modifiedTime, size, "
    "iconLink, thumbnailLink, webViewLink, parents)"
)

_FILE_FIELDS = (
    "id, name, mimeType, modifiedTime, createdTime, size, "
    "iconLink, thumbnailLink, webViewLink, owners(emailAddress, displayName), "
    "parents, trashed"
)

_BREADCRUMB_FIELDS = "id, name, parents, mimeType"

DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"


def _serialize_file(item: Dict[str, Any]) -> Dict[str, Any]:
    """Shape one Drive API file payload for the explorer UI.

    Drive returns ``size`` only when present; we coerce to ``int`` (or
    ``None`` for folders / Google-native types) so the UI can render
    consistently without a separate type check.
    """
    raw_size = item.get("size")
    try:
        size = int(raw_size) if raw_size is not None else None
    except (TypeError, ValueError):
        size = None
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "mime_type": item.get("mimeType"),
        "is_folder": item.get("mimeType") == DRIVE_FOLDER_MIME,
        "modified_time": item.get("modifiedTime"),
        "created_time": item.get("createdTime"),
        "size": size,
        "icon_link": item.get("iconLink"),
        "thumbnail_link": item.get("thumbnailLink"),
        "web_view_link": item.get("webViewLink"),
        "parents": item.get("parents") or [],
    }


class DriveNotAvailable(RuntimeError):
    """Raised when ``get_drive_service()`` returns ``None`` — either the
    Google API libs are not installed, the credentials file is missing, or
    the OAuth flow never completed.

    The route layer catches this and converts to HTTP 503, **never** 500."""


def _ensure_service():
    """Resolve the Drive service or raise :class:`DriveNotAvailable`.

    Centralised so every endpoint produces a uniform 503 instead of
    sprinkling ``None`` checks across the route handlers.
    """
    service = get_drive_service()
    if service is None:
        raise DriveNotAvailable(
            "Google Drive service is unavailable on this deploy "
            "(missing credentials, missing google-api libs, or token "
            "exchange not completed)."
        )
    return service


def list_folder(
    folder_id: str,
    *,
    page_size: int = 50,
    page_token: Optional[str] = None,
    include_trashed: bool = False,
    order_by: str = "folder,name",
) -> Dict[str, Any]:
    """List the immediate children of ``folder_id``.

    Folders sort first (``order_by='folder,name'`` is the Drive v3 idiom for
    "directories before files, alphabetically inside each group"), matching
    the Finder column-view rendering.

    Returns ``{"items": [...], "next_page_token": str|None}``. The route
    handler is the one that wraps this into a ``JSONResponse``.
    """
    service = _ensure_service()

    query_parts = [f"'{folder_id}' in parents"]
    if not include_trashed:
        query_parts.append("trashed = false")
    query = " and ".join(query_parts)

    request = service.files().list(
        q=query,
        pageSize=max(1, min(int(page_size), 200)),
        pageToken=page_token,
        fields=_LIST_FIELDS,
        orderBy=order_by,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    )
    payload = request.execute()
    return {
        "items": [_serialize_file(f) for f in payload.get("files", [])],
        "next_page_token": payload.get("nextPageToken"),
    }


def get_file(file_id: str) -> Dict[str, Any]:
    """Fetch metadata for a single Drive object (file or folder).

    Owners are included so the UI can show "Owned by X". The full
    ``webViewLink`` is included so the UI can deep-link out to native
    Drive when needed (e.g. opening a Google Doc).
    """
    service = _ensure_service()
    payload = service.files().get(
        fileId=file_id,
        fields=_FILE_FIELDS,
        supportsAllDrives=True,
    ).execute()

    serialized = _serialize_file(payload)
    # Add owners + trashed flag — these are not on _serialize_file because
    # listing does not request them (saves bytes on the common path).
    owners = payload.get("owners") or []
    serialized["owners"] = [
        {
            "email": (o or {}).get("emailAddress"),
            "display_name": (o or {}).get("displayName"),
        }
        for o in owners
    ]
    serialized["trashed"] = bool(payload.get("trashed"))
    return serialized


def breadcrumb(file_id: str, *, max_depth: int = 12) -> List[Dict[str, str]]:
    """Walk parents up to the root, returning a breadcrumb trail.

    The trail is ordered **root → file**, so the UI can render
    ``Drive / Folder / Sub-folder / file.pdf`` left-to-right without
    reversing. The walk stops at the first item without ``parents`` (the
    Drive root) or at ``max_depth`` (defence against a pathological loop
    or a very deep tree — Drive UI itself caps display).

    Each crumb is ``{id, name, mime_type, is_folder}``.
    """
    service = _ensure_service()
    trail: List[Dict[str, str]] = []

    current_id: Optional[str] = file_id
    visited: set[str] = set()
    while current_id and len(trail) < max_depth:
        if current_id in visited:
            logger.warning(
                "[DRIVE BREADCRUMB] cycle detected at id=%s — aborting walk",
                current_id,
            )
            break
        visited.add(current_id)

        try:
            payload = service.files().get(
                fileId=current_id,
                fields=_BREADCRUMB_FIELDS,
                supportsAllDrives=True,
            ).execute()
        except Exception as exc:  # noqa: BLE001 — the route maps to 502/404
            logger.warning(
                "[DRIVE BREADCRUMB] failed to fetch id=%s: %s",
                current_id,
                exc,
            )
            break

        trail.append({
            "id": payload.get("id"),
            "name": payload.get("name"),
            "mime_type": payload.get("mimeType"),
            "is_folder": payload.get("mimeType") == DRIVE_FOLDER_MIME,
        })
        parents = payload.get("parents") or []
        current_id = parents[0] if parents else None

    # The walk built leaf → root; the UI expects root → leaf.
    return list(reversed(trail))
