"""CaseHub.md — Drive sync (Fatia 5).

Reusa o `GoogleDriveHandler` existente (`services/google_drive_handler.py`)
para criar/atualizar arquivos markdown em `/CaseHubMD/<doc_id>.md` na raiz
do Drive. Sem ampliar scopes OAuth — usa o scope `drive` full-access que
o CaseHub já solicita.

Indexação: o filename é amigável (filename opcional ou `<doc_id>.md`), mas
a fonte canônica de identidade é `appProperties.casehub_md_doc_id`. Isso
permite renomear arquivos no Drive sem perder o link com o doc.

Race conditions: serializadas via lock por doc_id (in-process). Concurrency
cross-process não tratada — Fatia 5.2 / Fatia 8 (Yjs colab) cobre isso.
"""
from __future__ import annotations

import io
import logging
import threading
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

ROOT_FOLDER_NAME = "CaseHubMD"
MARKDOWN_MIME = "text/markdown"
HTML_MIME = "text/html"
GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
APP_PROP_DOC_ID = "casehub_md_doc_id"
APP_PROP_EXPORT_KIND = "casehub_md_export_kind"
MAX_MARKDOWN_BYTES = 4 * 1024 * 1024  # 4 MB — mais generoso que export DOCX


class DriveUnavailable(RuntimeError):
    """Drive service could not be instantiated (no token, no creds, network)."""


class MarkdownTooLarge(ValueError):
    pass


@dataclass(frozen=True)
class SaveResult:
    file_id: str
    drive_url: str
    updated_at: str  # ISO-8601 from Drive API
    was_created: bool


@dataclass(frozen=True)
class LoadResult:
    markdown: str
    file_id: str
    updated_at: str


@dataclass(frozen=True)
class DocSummary:
    doc_id: str
    file_id: str
    filename: str
    updated_at: str


class DriveSync:
    """Thin wrapper for CaseHub.md Drive operations.

    Lazy: only constructs the underlying Google Drive service when first used.
    Multi-tenant: ``__init__(org_id=...)`` scopes the service to one org's
    token. Default kept as ``DEFAULT_ORG_ID`` for legacy callers that
    haven't migrated yet (e.g. the ``default_sync()`` singleton).
    """

    def __init__(self, org_id: Optional[int] = None) -> None:
        # Lazy import to keep the module import-cheap on hosts without google libs.
        try:
            from services.per_org_credentials import DEFAULT_ORG_ID
        except ImportError:  # pragma: no cover — exercised only on broken installs
            DEFAULT_ORG_ID = 2
        self.org_id = int(org_id) if org_id else DEFAULT_ORG_ID
        self._service = None
        self._root_folder_id: Optional[str] = None
        self._doc_locks: dict[str, threading.Lock] = {}
        self._locks_mutex = threading.Lock()

    # ---- internals --------------------------------------------------------

    def _get_service(self):
        if self._service is not None:
            return self._service
        try:
            from services.google_drive_handler import get_drive_service
        except ImportError as e:
            raise DriveUnavailable(f"google_drive_handler import failed: {e}")
        svc = get_drive_service(self.org_id)
        if svc is None:
            raise DriveUnavailable(
                f"Drive service unavailable for org {self.org_id}: "
                "no token, missing libs, or refresh failure. "
                "Visit /casehub/integrations to connect."
            )
        self._service = svc
        return svc

    def _doc_lock(self, doc_id: str) -> threading.Lock:
        with self._locks_mutex:
            lock = self._doc_locks.get(doc_id)
            if lock is None:
                lock = threading.Lock()
                self._doc_locks[doc_id] = lock
            return lock

    # ---- public API -------------------------------------------------------

    def is_available(self) -> bool:
        """Cheap probe: True iff a Drive service is reachable. Caches result."""
        try:
            self._get_service()
            return True
        except DriveUnavailable:
            return False

    def ensure_root_folder(self) -> str:
        """Return the file ID of the `/CaseHubMD/` folder; create if missing."""
        if self._root_folder_id is not None:
            return self._root_folder_id
        svc = self._get_service()

        q = (
            f"mimeType='application/vnd.google-apps.folder' "
            f"and name='{ROOT_FOLDER_NAME}' and 'root' in parents and trashed=false"
        )
        resp = svc.files().list(q=q, fields="files(id, name)", pageSize=1).execute()
        files = resp.get("files", [])
        if files:
            self._root_folder_id = files[0]["id"]
            return self._root_folder_id

        # Create.
        body = {
            "name": ROOT_FOLDER_NAME,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": ["root"],
        }
        created = svc.files().create(body=body, fields="id").execute()
        self._root_folder_id = created["id"]
        return self._root_folder_id

    def _find_by_doc_id(self, doc_id: str) -> Optional[dict]:
        return self._find_by_doc_id_and_kind(doc_id, "markdown")

    def _find_by_doc_id_and_kind(self, doc_id: str, kind: str) -> Optional[dict]:
        svc = self._get_service()
        folder_id = self.ensure_root_folder()
        # We filter by appProperties (server-side); fall back to name match.
        q = (
            f"'{folder_id}' in parents and trashed=false "
            f"and appProperties has {{ key='{APP_PROP_DOC_ID}' and value='{doc_id}' }} "
            f"and appProperties has {{ key='{APP_PROP_EXPORT_KIND}' and value='{kind}' }}"
        )
        resp = svc.files().list(
            q=q,
            fields="files(id, name, modifiedTime, webViewLink, mimeType)",
            pageSize=1,
        ).execute()
        files = resp.get("files", [])
        if files:
            return files[0]

        # Fallback: legacy lookup by filename `<doc_id>.md`.
        q2 = f"'{folder_id}' in parents and trashed=false and name='{doc_id}.md'"
        resp2 = svc.files().list(
            q=q2,
            fields="files(id, name, modifiedTime, webViewLink, mimeType)",
            pageSize=1,
        ).execute()
        files2 = resp2.get("files", [])
        return files2[0] if files2 else None

    def save_markdown(
        self,
        doc_id: str,
        markdown: str,
        *,
        filename: Optional[str] = None,
    ) -> SaveResult:
        """Create-or-update `<doc_id>` markdown file. Returns SaveResult.

        Filename strategy:
            - if provided: sanitized, ensures `.md` suffix.
            - else: `<doc_id>.md`.
        """
        encoded = markdown.encode("utf-8")
        if len(encoded) > MAX_MARKDOWN_BYTES:
            raise MarkdownTooLarge(
                f"markdown is {len(encoded)} bytes; limit is {MAX_MARKDOWN_BYTES}"
            )

        # Postel: ensure .md suffix; sanitize chars.
        def _safe_name(raw: Optional[str]) -> str:
            base = (raw or doc_id).strip()
            cleaned = "".join(c for c in base if c.isalnum() or c in ("-", "_", ".", " "))
            cleaned = cleaned[:120].strip() or doc_id
            if not cleaned.lower().endswith(".md"):
                cleaned += ".md"
            return cleaned

        name = _safe_name(filename)

        # googleapiclient is imported lazily — kept off the module top-level for
        # callers that only probe `is_available()` on hosts without the package.
        from googleapiclient.http import MediaIoBaseUpload  # type: ignore[import-not-found]

        svc = self._get_service()
        folder_id = self.ensure_root_folder()
        media = MediaIoBaseUpload(io.BytesIO(encoded), mimetype=MARKDOWN_MIME, resumable=False)

        with self._doc_lock(doc_id):
            existing = self._find_by_doc_id(doc_id)
            if existing:
                updated = (
                    svc.files()
                    .update(
                        fileId=existing["id"],
                        body={
                            "name": name,
                            "appProperties": {
                                APP_PROP_DOC_ID: doc_id,
                                APP_PROP_EXPORT_KIND: "markdown",
                            },
                        },
                        media_body=media,
                        fields="id, modifiedTime, webViewLink",
                    )
                    .execute()
                )
                return SaveResult(
                    file_id=updated["id"],
                    drive_url=updated.get("webViewLink", ""),
                    updated_at=updated.get("modifiedTime", ""),
                    was_created=False,
                )

            created = (
                svc.files()
                .create(
                    body={
                        "name": name,
                        "mimeType": MARKDOWN_MIME,
                        "parents": [folder_id],
                        "appProperties": {
                            APP_PROP_DOC_ID: doc_id,
                            APP_PROP_EXPORT_KIND: "markdown",
                        },
                    },
                    media_body=media,
                    fields="id, modifiedTime, webViewLink",
                )
                .execute()
            )
            return SaveResult(
                file_id=created["id"],
                drive_url=created.get("webViewLink", ""),
                updated_at=created.get("modifiedTime", ""),
                was_created=True,
            )

    def save_google_doc(
        self,
        doc_id: str,
        html: str,
        *,
        filename: Optional[str] = None,
    ) -> SaveResult:
        """Create-or-update a Google Docs copy imported from HTML.

        The source of truth remains the markdown file; this method gives the
        user an editable native Google Docs export whenever Drive is connected.
        """
        encoded = html.encode("utf-8")
        if len(encoded) > MAX_MARKDOWN_BYTES:
            raise MarkdownTooLarge(
                f"html is {len(encoded)} bytes; limit is {MAX_MARKDOWN_BYTES}"
            )

        def _safe_name(raw: Optional[str]) -> str:
            base = (raw or doc_id).strip()
            cleaned = "".join(c for c in base if c.isalnum() or c in ("-", "_", ".", " "))
            return cleaned[:120].strip() or doc_id

        name = _safe_name(filename)

        from googleapiclient.http import MediaIoBaseUpload  # type: ignore[import-not-found]

        svc = self._get_service()
        folder_id = self.ensure_root_folder()
        media = MediaIoBaseUpload(io.BytesIO(encoded), mimetype=HTML_MIME, resumable=False)

        with self._doc_lock(f"{doc_id}:google-doc"):
            existing = self._find_by_doc_id_and_kind(doc_id, "google-doc")
            if existing:
                updated = (
                    svc.files()
                    .update(
                        fileId=existing["id"],
                        body={
                            "name": name,
                            "appProperties": {
                                APP_PROP_DOC_ID: doc_id,
                                APP_PROP_EXPORT_KIND: "google-doc",
                            },
                        },
                        media_body=media,
                        fields="id, modifiedTime, webViewLink",
                    )
                    .execute()
                )
                return SaveResult(
                    file_id=updated["id"],
                    drive_url=updated.get("webViewLink", ""),
                    updated_at=updated.get("modifiedTime", ""),
                    was_created=False,
                )

            created = (
                svc.files()
                .create(
                    body={
                        "name": name,
                        "mimeType": GOOGLE_DOC_MIME,
                        "parents": [folder_id],
                        "appProperties": {
                            APP_PROP_DOC_ID: doc_id,
                            APP_PROP_EXPORT_KIND: "google-doc",
                        },
                    },
                    media_body=media,
                    fields="id, modifiedTime, webViewLink",
                )
                .execute()
            )
            return SaveResult(
                file_id=created["id"],
                drive_url=created.get("webViewLink", ""),
                updated_at=created.get("modifiedTime", ""),
                was_created=True,
            )

    def load_markdown(self, doc_id: str) -> Optional[LoadResult]:
        """Fetch markdown content for `doc_id`, or None if not found."""
        svc = self._get_service()
        found = self._find_by_doc_id(doc_id)
        if not found:
            return None
        from googleapiclient.http import MediaIoBaseDownload  # type: ignore[import-not-found]

        request = svc.files().get_media(fileId=found["id"])
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return LoadResult(
            markdown=buffer.getvalue().decode("utf-8", errors="replace"),
            file_id=found["id"],
            updated_at=found.get("modifiedTime", ""),
        )

    def list_recent(self, limit: int = 100) -> list[DocSummary]:
        """List the N most-recently-modified docs in CaseHubMD/."""
        svc = self._get_service()
        folder_id = self.ensure_root_folder()
        q = f"'{folder_id}' in parents and trashed=false and mimeType='{MARKDOWN_MIME}'"
        resp = svc.files().list(
            q=q,
            fields="files(id, name, modifiedTime, appProperties)",
            orderBy="modifiedTime desc",
            pageSize=min(limit, 200),
        ).execute()
        out: list[DocSummary] = []
        for f in resp.get("files", []):
            app_props = f.get("appProperties") or {}
            doc_id = app_props.get(APP_PROP_DOC_ID) or f["name"].removesuffix(".md")
            out.append(
                DocSummary(
                    doc_id=doc_id,
                    file_id=f["id"],
                    filename=f["name"],
                    updated_at=f.get("modifiedTime", ""),
                )
            )
        return out


# Per-org cache so each tenant's DriveSync gets its own lazy service.
_sync_cache: dict[int, DriveSync] = {}


def default_sync(org_id: Optional[int] = None) -> DriveSync:
    """Return a per-org DriveSync (lazily constructed once per org id).

    ``org_id=None`` keeps the legacy single-tenant behavior, returning the
    ``DEFAULT_ORG_ID`` instance — required while callers in
    ``routes/casehub_md*`` are still being migrated.
    """
    try:
        from services.per_org_credentials import DEFAULT_ORG_ID
    except ImportError:  # pragma: no cover
        DEFAULT_ORG_ID = 2
    key = int(org_id) if org_id else DEFAULT_ORG_ID
    instance = _sync_cache.get(key)
    if instance is None:
        instance = DriveSync(org_id=key)
        _sync_cache[key] = instance
    return instance
