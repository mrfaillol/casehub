#!/usr/bin/env python3
"""
Google Drive Handler - CaseHub
Handles uploading documents to Google Drive with organized folder structure.

Multi-tenant: tokens are scoped to `credentials/org_{org_id}/drive_token.json`
via `services.per_org_credentials.get_org_drive_token_path`. Each
`GoogleDriveHandler(db, org_id=...)` reads only the tenant's own token.

Legacy single-tenant pickle (`credentials/google_drive_token.pickle`) is
migrated to org_{DEFAULT_ORG_ID}/ on first instantiation, then converted
from pickle to JSON one-shot inside `_load_credentials`.
"""

import os
import re
import json
import pickle
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

from config import settings
from services.per_org_credentials import (
    DEFAULT_ORG_ID,
    get_org_credentials_dir,
    get_org_drive_token_path,
    get_org_drive_legacy_pickle_path,
    migrate_legacy_credentials_to_org,
)

logger = logging.getLogger(__name__)

# OAuth client secrets path (still global — same Google Cloud client across orgs).
CREDENTIALS_PATH = (
    settings.GOOGLE_DRIVE_CREDENTIALS_PATH
    or os.path.join(settings.BASE_DIR, "credentials", "google_drive_credentials.json")
)
ROOT_FOLDER_NAME = os.getenv("GOOGLE_DRIVE_ROOT_FOLDER", "Active Clients")

# Tasks folder ID in Google Drive (per-paralegal work folders).
# Legacy global — TODO multi-tenant: move to org column/feature alongside drive_root.
TASKS_FOLDER_ID = settings.GOOGLE_DRIVE_TASKS_ID

# Paralegal configuration loaded from Organization.features["paralegal_config"]
# at runtime via `_load_paralegal_config`. Kept module-level for legacy compat
# only — empty dict when no instance has been built yet.
TASK_PARALEGALS_WITH_CLIENTS: Dict[str, Dict[str, Any]] = {}
TASK_ARCHIVED_WITH_CLIENTS: Dict[str, Dict[str, Any]] = {}

# Admin folder names inside paralegal folders to skip during client matching.
ADMIN_FOLDER_NAMES = {
    "templates", "folha de ponto", "ponto mensal", "consultations",
    "miscellaneous", "team red", "checklists templates", "docs - onboarding",
    "ps e cartas pendentes", "freelance", "manual ilc", "administrative",
    "forms to sign", "timesheet", "uscis online", "checklists templates with rfe comments",
}

# Google Drive API scopes
# Changed from 'drive.file' to 'drive' to access ALL folders (including Active Clients)
# 'drive.file' only allows access to files created by the app
SCOPES = ['https://www.googleapis.com/auth/drive']

# Legacy Portuguese → English folder name mapping (for backward compatibility)
# When looking for a folder, check English name first, then fall back to Portuguese
LEGACY_FOLDER_NAMES = {
    "Documentos Pessoais": "Personal Docs",
    "Diplomas e Certificados": "Education",
    "Evidencias": "Evidence",
    "Cartas de Recomendacao": "Recommendation Letters",
    "Premios e Reconhecimentos": "Awards",
    "Publicacoes": "Authorship",
    "Citacoes": "Citations",
    "Midia": "Press",
    "Lideranca": "Critical Role",
    "Contribuicoes Originais": "Original Contributions",
    "Plano de Trabalho": "NIW",
    "Outros": "Other",
}
# Reverse mapping: English → Portuguese (for fallback lookups)
_ENGLISH_TO_PORTUGUESE = {v: k for k, v in LEGACY_FOLDER_NAMES.items()}

# Folder structure by visa category - English names (per Daniel's instructions 2026-03-10)
VISA_FOLDER_STRUCTURE = {
    "EB1A": [
        "Personal Docs",
        "Education",
        "Awards",
        "Authorship",
        "Citations",
        "Press",
        "Associations",
        "Critical Role",
        "Judging",
        "Original Contributions",
        "High Salary",
        "Recommendation Letters",
        "Personal Statement",
        "USCIS Notices",
        "Package"
    ],
    "EB2-NIW": [
        "Personal Docs",
        "Education",
        "Advanced Degree",
        "Exceptional Ability",
        "Comparable Evidence",
        "NIW",
        "Recommendation Letters",
        "Personal Statement",
        "USCIS Notices",
        "Package"
    ],
    "I-130": [
        "Petitioner Docs",
        "Beneficiary Docs",
        "Evidence of Relationship",
        "Forms",
        "USCIS Notices",
        "Package"
    ],
    "General": [
        "Personal Docs",
        "Other"
    ]
}

# Internal folder structure (same for all visa types)
INTERNAL_FOLDER_STRUCTURE = [
    "Meetings",
    "Initial Docs",
    "Drafts",
    "Case Admin"
]

# Map document types to English subfolder names
# Updated: 2026-03-11 - Folder names now in English (per Daniel's instructions)
DOCUMENT_TYPE_TO_FOLDER = {
    # Personal Documents
    "Passport": "Personal Docs",
    "I-94 Travel Record": "Personal Docs",
    "Visa": "Personal Docs",
    "EAD Card": "Personal Docs",
    "Green Card": "Personal Docs",
    "Birth Certificate": "Personal Docs",
    "Marriage Certificate": "Personal Docs",
    "Photo": "Personal Docs",
    "Medical Records": "Personal Docs",
    "Police Certificate": "Personal Docs",

    # Educational
    "Diploma": "Education",
    "Academic Transcript": "Education",

    # Professional/Evidence
    "Employment Letter": "Evidence",
    "Employment Contract": "Evidence",
    "Resume/CV": "Evidence",
    "Tax Return": "Evidence",
    "Pay Stub": "Evidence",
    "Financial Statement": "Evidence",
    "Supporting Evidence": "Evidence",
    "Personal Statement": "Personal Statement",
    "Portfolio/Work Samples": "Original Contributions",
    "Award/Recognition": "Awards",
    "Professional Membership": "Associations",
    "Publication": "Authorship",

    # Recommendations
    "Letter of Recommendation": "Recommendation Letters",

    # Immigration
    "USCIS Form": "USCIS Notices",
    "Receipt Notice": "USCIS Notices",
    "Approval Notice": "USCIS Notices",
    "Request for Evidence": "USCIS Notices",

    # Fallback
    "Other Document": "Other"
}

# EB1A specific mappings - doc types that go to EB1A-specific folders
EB1A_DOCUMENT_FOLDERS = {
    "Award/Recognition": "Awards",
    "Publication": "Authorship",
    "Citation": "Citations",
    "Media": "Press",
    "Professional Membership": "Associations",
    "Leadership": "Critical Role",
    "Contribution": "Original Contributions",
    "Portfolio/Work Samples": "Original Contributions"
}


def _write_private_json(path: Path, content: str) -> None:
    """Write OAuth material atomically with 0o600 permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None
            handle.write(content)
    finally:
        if fd is not None:
            os.close(fd)
    os.chmod(path, 0o600)


def get_drive_service(org_id: Optional[int] = None):
    """Return a per-org Google Drive service, or ``None`` if no token.

    Legacy callers (``services/drive_explorer.py``, ``services/casehub_md/
    drive_sync.py``) invoke this without arguments — they receive the
    ``DEFAULT_ORG_ID`` service so the legacy single-tenant deploy keeps
    working until they migrate to per-org instantiation.

    **Never** spawns a local OAuth server: web-based consent runs in
    ``routes/integrations.py``. If no valid token exists, returns ``None``
    so the caller can surface a "connect Drive" error to the user.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        logger.error(
            "Google API packages not installed. "
            "Run: pip install google-api-python-client google-auth-oauthlib"
        )
        return None

    resolved_org = int(org_id) if org_id else DEFAULT_ORG_ID
    creds = _load_credentials_for_org(resolved_org)
    if not creds:
        return None

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                # Persist refreshed token.
                _write_private_json(get_org_drive_token_path(resolved_org), creds.to_json())
            except Exception as e:
                logger.warning("Drive token refresh failed for org %s: %s", resolved_org, e)
                return None
        else:
            return None

    return build('drive', 'v3', credentials=creds)


def _load_credentials_for_org(org_id: int):
    """Load credentials for an org from the per-org JSON token, migrating
    legacy pickle → JSON one-shot if needed.

    Migration order:
      1. If ``credentials/org_{DEFAULT_ORG_ID}/drive_token.json`` does not
         exist and ``org_id == DEFAULT_ORG_ID``: try ``migrate_legacy_credentials_to_org``
         which copies legacy ``credentials/google_drive_token.pickle`` to
         the org dir as ``drive_token.pickle``.
      2. If org_dir contains ``drive_token.pickle`` but no ``drive_token.json``:
         unpickle, write ``creds.to_json()``, then delete the pickle.
      3. Load ``drive_token.json`` via ``Credentials.from_authorized_user_file``.
    """
    try:
        from google.oauth2.credentials import Credentials
    except ImportError:
        return None

    token_path = get_org_drive_token_path(org_id)
    legacy_pickle = get_org_drive_legacy_pickle_path(org_id)

    # Step 1: migrate legacy single-tenant tokens into org_{DEFAULT_ORG_ID}/.
    if not token_path.exists() and not legacy_pickle.exists():
        migration = migrate_legacy_credentials_to_org(org_id)
        if migration.get("migrated"):
            logger.info("Legacy Drive migration for org %s: %s", org_id, migration["migrated"])

    # Step 2: one-shot pickle → JSON conversion.
    if not token_path.exists() and legacy_pickle.exists():
        try:
            with open(legacy_pickle, "rb") as fh:
                pickled_creds = pickle.load(fh)
            json_payload = pickled_creds.to_json()
            _write_private_json(token_path, json_payload)
            try:
                legacy_pickle.unlink()
            except OSError:
                logger.warning("Could not delete legacy pickle %s after JSON migration", legacy_pickle)
            logger.info("Migrated Drive token pickle → JSON for org %s", org_id)
        except Exception as e:
            logger.warning(
                "Pickle→JSON migration failed for org %s (%s): %s",
                org_id, legacy_pickle, e,
            )

    # Step 3: load JSON token.
    if not token_path.exists():
        return None

    try:
        return Credentials.from_authorized_user_file(str(token_path), SCOPES)
    except Exception as e:
        logger.warning("Could not load Drive token for org %s: %s", org_id, e)
        return None


class GoogleDriveHandler:
    """Handles Google Drive operations for document management.

    Multi-tenant: ``__init__`` requires (db, org_id). The token path is
    ``credentials/org_{org_id}/drive_token.json``. The handler **never**
    writes a token from a local OAuth flow — connection consent lives in
    ``routes/integrations.py`` (web OAuth callback).

    Args:
        db: SQLAlchemy session for resolving Organization features
            (paralegal config, root folder id). May be ``None`` for
            background jobs that pre-resolve org context elsewhere.
        org_id: Tenant id from ``request.state.org_id``. If falsy, defaults
            to ``DEFAULT_ORG_ID`` so legacy single-tenant flows keep working.
    """

    def __init__(self, db=None, org_id: Optional[int] = None):
        self.db = db
        self.org_id = int(org_id) if org_id else DEFAULT_ORG_ID
        self._token_path = get_org_drive_token_path(self.org_id)
        self.service = get_drive_service(self.org_id)
        self._folder_cache: Dict[str, str] = {}  # path -> folder_id
        self._root_folder_id: Optional[str] = None
        self._org_root_id: Optional[str] = None
        self._org_loaded: bool = False
        # Best-effort load of paralegal config (no-op if db is None).
        self._load_paralegal_config(db)

    def is_connected(self) -> bool:
        """Check if Drive service is available."""
        return self.service is not None

    def _ensure_org_loaded(self) -> None:
        """Lazy-load Organization row for per-org settings (root folder, features).

        Falls back to global ``settings.GOOGLE_DRIVE_ROOT_ID`` when the
        db session is missing or the org has no override.
        """
        if self._org_loaded:
            return
        self._org_loaded = True
        if self.db is None:
            self._org_root_id = settings.GOOGLE_DRIVE_ROOT_ID
            return
        try:
            from models import Organization

            org = self.db.query(Organization).filter(Organization.id == self.org_id).first()
            if org is not None:
                root_override = getattr(org, "google_drive_root_id", None)
                self._org_root_id = root_override or settings.GOOGLE_DRIVE_ROOT_ID
            else:
                self._org_root_id = settings.GOOGLE_DRIVE_ROOT_ID
        except Exception as e:
            logger.warning("Could not load Organization %s for Drive root: %s", self.org_id, e)
            self._org_root_id = settings.GOOGLE_DRIVE_ROOT_ID

    def _load_paralegal_config(self, db) -> None:
        """Read paralegal folder config from ``Organization.features``.

        Schema expected::

            {
              "paralegal_config": {
                "active": {"Juliana": {"has_clientes_subfolder": true}, ...},
                "archived": {"Maria": {"has_clientes_subfolder": false}, ...}
              }
            }

        Populates ``self.task_paralegals`` and ``self.task_archived``. Also
        updates module-level legacy dicts so older callers that read
        ``TASK_PARALEGALS_WITH_CLIENTS`` see the same data for this org's
        request lifetime (best-effort — not thread-safe across orgs).
        """
        self.task_paralegals: Dict[str, Dict[str, Any]] = {}
        self.task_archived: Dict[str, Dict[str, Any]] = {}
        if db is None:
            return
        try:
            from models import Organization

            org = db.query(Organization).filter(Organization.id == self.org_id).first()
            if org is None:
                return
            features = getattr(org, "features", None) or {}
            cfg = features.get("paralegal_config") or {}
            self.task_paralegals = dict(cfg.get("active", {}) or {})
            self.task_archived = dict(cfg.get("archived", {}) or {})
            # Legacy compatibility hook — module-level dicts.
            global TASK_PARALEGALS_WITH_CLIENTS, TASK_ARCHIVED_WITH_CLIENTS
            TASK_PARALEGALS_WITH_CLIENTS = self.task_paralegals
            TASK_ARCHIVED_WITH_CLIENTS = self.task_archived
        except Exception as e:
            logger.warning("Could not load paralegal config for org %s: %s", self.org_id, e)

    def get_root_folder_id(self) -> Optional[str]:
        """Get the Active Clients root folder ID for this org."""
        if self._root_folder_id:
            return self._root_folder_id
        if not self.service:
            return None
        self._ensure_org_loaded()
        self._root_folder_id = self._org_root_id
        return self._root_folder_id

    def list_active_clients_folders(self) -> List[Dict[str, str]]:
        """
        List all client folders in the Active Clients root.

        Returns:
            List of dicts with 'id' and 'name' keys, sorted by name.
        """
        if not self.service:
            return []

        root_id = self.get_root_folder_id()
        if not root_id:
            return []

        try:
            folders = []
            page_token = None
            while True:
                resp = self.service.files().list(
                    q=f"mimeType='application/vnd.google-apps.folder' and '{root_id}' in parents and trashed=false",
                    fields="nextPageToken, files(id, name)",
                    pageSize=200,
                    pageToken=page_token
                ).execute()
                for f in resp.get("files", []):
                    folders.append({"id": f["id"], "name": f["name"]})
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
            folders.sort(key=lambda x: x["name"])
            return folders
        except Exception as e:
            logger.error(f"Error listing Active Clients folders: {e}")
            return []

    @staticmethod
    def _matches_client(folder_name: str, last: str, first: str) -> bool:
        """
        Word-boundary match to prevent cross-contamination.

        Uses regex \\b anchors so that e.g. last='LI' does NOT match 'LIANG'.
        Only matches when the name part is a full word in the folder name.
        """
        fn = folder_name.lower()
        last_pattern = r'\b' + re.escape(last.lower()) + r'\b'
        first_pattern = r'\b' + re.escape(first.lower()) + r'\b'
        return bool(re.search(last_pattern, fn) and re.search(first_pattern, fn))

    def find_client_folder(self, last_name: str, first_name: str) -> Optional[Dict[str, str]]:
        """
        Find a client's folder in Active Clients by matching name parts.
        Active Clients naming: "LAST, First - CaseType"

        Uses word-boundary regex to prevent cross-contamination
        (e.g. 'LI' won't match 'LIANG', 'RAJ' won't match 'RAJA').

        Returns:
            Dict with 'id' and 'name' keys, or None if not found.
        """
        folders = self.list_active_clients_folders()
        if not folders:
            return None

        last = last_name.strip()
        first = first_name.strip()

        # Priority 1: both last_name AND first_name match on word boundaries
        for f in folders:
            if self._matches_client(f["name"], last, first):
                return f

        # Priority 2: just last_name on word boundary
        last_pattern = r'\b' + re.escape(last.lower()) + r'\b'
        for f in folders:
            if re.search(last_pattern, f["name"].lower()):
                return f

        return None

    def _list_subfolders(self, parent_id: str) -> List[Dict[str, str]]:
        """List immediate subfolders of a folder. Returns [{id, name}, ...]."""
        if not self.service:
            return []
        try:
            folders = []
            page_token = None
            while True:
                resp = self.service.files().list(
                    q=f"mimeType='application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed=false",
                    fields="nextPageToken, files(id, name)",
                    pageSize=200,
                    pageToken=page_token
                ).execute()
                for f in resp.get("files", []):
                    folders.append({"id": f["id"], "name": f["name"]})
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
            return folders
        except Exception as e:
            logger.warning(f"Error listing subfolders of {parent_id}: {e}")
            return []

    def find_client_in_tasks(self, last_name: str, first_name: str) -> List[Dict[str, Any]]:
        """
        Find a client's folders in the Tasks hierarchy.
        Searches active paralegals and archived paralegals for matching client folders.

        Returns:
            List of dicts: [{"id": "...", "name": "...", "paralegal": "Juliana", "archived": False}, ...]
        """
        if not self.service:
            return []

        matches = []
        last = last_name.lower().strip()
        first = first_name.lower().strip()

        if not last:
            return []

        # Step 1: List top-level folders in Tasks to find paralegal folders
        top_folders = self._list_subfolders(TASKS_FOLDER_ID)
        top_map = {f["name"]: f["id"] for f in top_folders}

        # Step 2: Search active paralegals
        for paralegal_name, config in self.task_paralegals.items():
            if paralegal_name not in top_map:
                # Try partial match (some names have trailing spaces)
                found_id = None
                for fn, fid in top_map.items():
                    if fn.strip() == paralegal_name:
                        found_id = fid
                        break
                if not found_id:
                    continue
            else:
                found_id = top_map[paralegal_name]

            # Get the folder to search in
            if config.get("has_clientes_subfolder"):
                # Look for "Clientes" subfolder
                subs = self._list_subfolders(found_id)
                search_folder_id = None
                for s in subs:
                    if s["name"].lower().strip() == "clientes":
                        search_folder_id = s["id"]
                        break
                if not search_folder_id:
                    continue
            else:
                search_folder_id = found_id

            # List folders and match by name
            client_folders = self._list_subfolders(search_folder_id)
            for cf in client_folders:
                cf_lower = cf["name"].lower()
                # Skip admin folders
                if cf_lower.strip() in ADMIN_FOLDER_NAMES:
                    continue
                if last in cf_lower and first in cf_lower:
                    matches.append({
                        "id": cf["id"],
                        "name": cf["name"],
                        "paralegal": paralegal_name,
                        "archived": False
                    })
                elif last in cf_lower and len(last) >= 3:
                    # Fallback: last name only (weaker match)
                    matches.append({
                        "id": cf["id"],
                        "name": cf["name"],
                        "paralegal": paralegal_name,
                        "archived": False
                    })

        # Step 3: Search archived paralegals
        arquivado_id = top_map.get("Arquivado")
        if arquivado_id:
            archived_folders = self._list_subfolders(arquivado_id)
            archived_map = {f["name"]: f["id"] for f in archived_folders}

            for paralegal_name, config in self.task_archived.items():
                if paralegal_name not in archived_map:
                    found_id = None
                    for fn, fid in archived_map.items():
                        if fn.strip() == paralegal_name:
                            found_id = fid
                            break
                    if not found_id:
                        continue
                else:
                    found_id = archived_map[paralegal_name]

                client_folders = self._list_subfolders(found_id)
                for cf in client_folders:
                    cf_lower = cf["name"].lower()
                    if cf_lower.strip() in ADMIN_FOLDER_NAMES:
                        continue
                    if last in cf_lower and first in cf_lower:
                        matches.append({
                            "id": cf["id"],
                            "name": cf["name"],
                            "paralegal": f"Arquivado/{paralegal_name}",
                            "archived": True
                        })
                    elif last in cf_lower and len(last) >= 3:
                        matches.append({
                            "id": cf["id"],
                            "name": cf["name"],
                            "paralegal": f"Arquivado/{paralegal_name}",
                            "archived": True
                        })

        return matches

    def get_or_create_folder(self, folder_name: str, parent_id: str) -> Optional[str]:
        """
        Get existing folder or create new one.
        Checks for legacy Portuguese folder names as fallback.

        Args:
            folder_name: Name of the folder (English)
            parent_id: Parent folder ID

        Returns:
            Folder ID or None on error
        """
        cache_key = f"{parent_id}/{folder_name}"
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]

        if not self.service:
            return None

        try:
            # Search for existing folder by English name
            query = f"name='{folder_name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()

            files = results.get('files', [])

            if files:
                folder_id = files[0]['id']
            else:
                # Fallback: check for legacy Portuguese name
                legacy_name = _ENGLISH_TO_PORTUGUESE.get(folder_name)
                if legacy_name:
                    legacy_query = f"name='{legacy_name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
                    legacy_results = self.service.files().list(
                        q=legacy_query,
                        spaces='drive',
                        fields='files(id, name)'
                    ).execute()
                    legacy_files = legacy_results.get('files', [])
                    if legacy_files:
                        folder_id = legacy_files[0]['id']
                        logger.info(f"Found legacy folder '{legacy_name}', using as '{folder_name}'")
                        self._folder_cache[cache_key] = folder_id
                        return folder_id

                # Create folder with English name
                file_metadata = {
                    'name': folder_name,
                    'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [parent_id]
                }
                folder = self.service.files().create(
                    body=file_metadata,
                    fields='id'
                ).execute()
                folder_id = folder.get('id')
                logger.info(f"Created folder: {folder_name}")

            self._folder_cache[cache_key] = folder_id
            return folder_id

        except Exception as e:
            logger.error(f"Error creating folder {folder_name}: {e}")
            return None

    def get_client_folder(self, client_name: str) -> Optional[str]:
        """
        Get or create client's main folder.

        Args:
            client_name: Client's full name

        Returns:
            Folder ID or None
        """
        root_id = self.get_root_folder_id()
        if not root_id:
            return None

        return self.get_or_create_folder(client_name, root_id)

    def get_client_folder_web_link(self, client_name: str) -> Optional[str]:
        """
        Get Google Drive web link for client's root folder.

        Args:
            client_name: Client's full name

        Returns:
            Web link to Drive folder or None if folder doesn't exist
        """
        folder_id = self.get_client_folder(client_name)
        if folder_id:
            return f"https://drive.google.com/drive/folders/{folder_id}"
        return None

    def list_files_recursive(self, folder_id: str, max_results: int = 500) -> List[Dict[str, Any]]:
        """
        List all files in a Drive folder recursively, including folder path context.

        Args:
            folder_id: Google Drive folder ID to list
            max_results: Maximum number of files to return

        Returns:
            List of file metadata dicts with id, name, mimeType, size, modifiedTime,
            webViewLink, folder_path
        """
        if not self.service:
            return []

        all_files = []

        def _recurse(fid, path="", depth=0):
            if depth > 5 or len(all_files) >= max_results:
                return
            try:
                page_token = None
                while len(all_files) < max_results:
                    resp = self.service.files().list(
                        q=f"'{fid}' in parents and trashed=false",
                        pageSize=200,
                        fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, webViewLink)",
                        pageToken=page_token
                    ).execute()
                    for item in resp.get("files", []):
                        if item.get("mimeType") == "application/vnd.google-apps.folder":
                            sub = f"{path}/{item['name']}" if path else item["name"]
                            _recurse(item["id"], sub, depth + 1)
                        else:
                            item["folder_path"] = path
                            all_files.append(item)
                            if len(all_files) >= max_results:
                                return
                    page_token = resp.get("nextPageToken")
                    if not page_token:
                        break
            except Exception as e:
                logger.warning(f"Error listing folder {path}: {e}")

        _recurse(folder_id)

        formatted = []
        for f in all_files:
            formatted.append({
                'id': f.get('id'),
                'name': f.get('name'),
                'mimeType': f.get('mimeType', 'unknown'),
                'size': int(f.get('size', 0)) if f.get('size') else 0,
                'modifiedTime': f.get('modifiedTime'),
                'webViewLink': f.get('webViewLink'),
                'folder_path': f.get('folder_path', '')
            })
        return formatted

    def list_client_files(self, client_name: str, max_results: int = 500) -> List[Dict[str, Any]]:
        """
        List all files in client's Drive folder (recursively).
        Wrapper that finds the client folder first, then calls list_files_recursive.
        """
        if not self.service:
            return []

        folder_id = self.get_client_folder(client_name)
        if not folder_id:
            logger.warning(f"Client folder not found for {client_name}")
            return []

        return self.list_files_recursive(folder_id, max_results)

    def get_document_folder(
        self,
        client_name: str,
        visa_category: str = "General",
        document_type: str = "Other Document"
    ) -> Optional[str]:
        """
        Get the appropriate folder for a document based on client, visa category, and document type.

        New structure (2026-03-11):
          ClientName / Shared with Client / {Subfolder}
        Legacy fallback:
          ClientName / {VisaCategory} / {Subfolder}

        Internal documents (Case Admin, Meeting notes) go to:
          ClientName / Internal / {Subfolder}

        Args:
            client_name: Client's full name
            visa_category: "EB1A", "EB2-NIW", or "General"
            document_type: Document type for subfolder selection

        Returns:
            Folder ID where document should be uploaded
        """
        # Get client folder
        client_folder_id = self.get_client_folder(client_name)
        if not client_folder_id:
            return None

        # Determine subfolder based on document type
        # Check EB1A-specific mappings first
        if visa_category in ("EB1A", "EB-1A") and document_type in EB1A_DOCUMENT_FOLDERS:
            subfolder_name = EB1A_DOCUMENT_FOLDERS[document_type]
        else:
            subfolder_name = DOCUMENT_TYPE_TO_FOLDER.get(document_type, "Other")

        # Try new structure: Shared with Client / subfolder
        shared_folder_id = self.get_or_create_folder("Shared with Client", client_folder_id)
        if shared_folder_id:
            subfolder_id = self.get_or_create_folder(subfolder_name, shared_folder_id)
            if subfolder_id:
                return subfolder_id

        # Fallback to legacy structure: visa_category / subfolder
        visa_folder_id = self.get_or_create_folder(visa_category, client_folder_id)
        if not visa_folder_id:
            return client_folder_id

        subfolder_id = self.get_or_create_folder(subfolder_name, visa_folder_id)

        return subfolder_id or visa_folder_id

    def upload_document(
        self,
        file_path: str,
        client_name: str,
        document_title: str = None,
        visa_category: str = "General",
        document_type: str = "Other Document",
        mime_type: str = None
    ) -> Dict[str, Any]:
        """
        Upload a document to Google Drive with proper folder organization.

        Args:
            file_path: Local path to the file
            client_name: Client's name for folder structure
            document_title: Title for the file (defaults to original filename)
            visa_category: "EB1A", "EB2-NIW", or "General"
            document_type: Document type for subfolder
            mime_type: MIME type of the file

        Returns:
            Dict with upload result including file ID and web link
        """
        result = {
            "success": False,
            "file_id": None,
            "web_link": None,
            "error": None
        }

        if not self.service:
            result["error"] = "Google Drive service not connected"
            return result

        file_path = Path(file_path)
        if not file_path.exists():
            result["error"] = f"File not found: {file_path}"
            return result

        # Get destination folder
        folder_id = self.get_document_folder(client_name, visa_category, document_type)
        if not folder_id:
            result["error"] = "Could not determine destination folder"
            return result

        # Prepare file metadata
        file_name = document_title or file_path.name
        if not file_name.endswith(file_path.suffix):
            file_name += file_path.suffix

        # Detect MIME type if not provided
        if not mime_type:
            mime_types = {
                '.pdf': 'application/pdf',
                '.doc': 'application/msword',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.txt': 'text/plain'
            }
            mime_type = mime_types.get(file_path.suffix.lower(), 'application/octet-stream')

        try:
            from googleapiclient.http import MediaFileUpload

            file_metadata = {
                'name': file_name,
                'parents': [folder_id]
            }

            media = MediaFileUpload(
                str(file_path),
                mimetype=mime_type,
                resumable=True
            )

            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink, webContentLink'
            ).execute()

            result["success"] = True
            result["file_id"] = file.get('id')
            result["web_link"] = file.get('webViewLink')
            result["download_link"] = file.get('webContentLink')

            logger.info(f"Uploaded to Drive: {file_name} -> {result['web_link']}")

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Upload failed: {e}")

        return result

    def upload_to_folder(
        self,
        file_path: str,
        folder_id: str,
        document_title: str = None,
        mime_type: str = None
    ) -> Dict[str, Any]:
        """
        Upload a document directly to a specific Drive folder by ID.
        Used when client.drive_folder_id is known.
        """
        result = {"success": False, "file_id": None, "web_link": None, "error": None}

        if not self.service:
            result["error"] = "Google Drive service not connected"
            return result

        file_path = Path(file_path)
        if not file_path.exists():
            result["error"] = f"File not found: {file_path}"
            return result

        file_name = document_title or file_path.name
        if not file_name.endswith(file_path.suffix):
            file_name += file_path.suffix

        if not mime_type:
            mime_types = {
                '.pdf': 'application/pdf',
                '.doc': 'application/msword',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.png': 'image/png', '.gif': 'image/gif', '.txt': 'text/plain'
            }
            mime_type = mime_types.get(file_path.suffix.lower(), 'application/octet-stream')

        try:
            from googleapiclient.http import MediaFileUpload
            media = MediaFileUpload(str(file_path), mimetype=mime_type, resumable=True)
            file = self.service.files().create(
                body={'name': file_name, 'parents': [folder_id]},
                media_body=media,
                fields='id, webViewLink, webContentLink'
            ).execute()
            result["success"] = True
            result["file_id"] = file.get('id')
            result["web_link"] = file.get('webViewLink')
            logger.info(f"Uploaded to Drive folder {folder_id}: {file_name}")
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Upload to folder failed: {e}")

        return result

    def create_client_folder_structure(
        self,
        client_name: str,
        visa_category: str = "EB2-NIW"
    ) -> Dict[str, str]:
        """
        Create complete folder structure for a new client.
        Structure per Daniel's requirements (2026-03-10):
          ClientName/
          ├── Internal/
          │   ├── Meetings/
          │   ├── Initial Docs/
          │   ├── Drafts/
          │   └── Case Admin/
          └── Shared with Client/
              ├── Personal Docs/
              ├── Education/
              └── [visa-specific subfolders]

        Args:
            client_name: Client's full name
            visa_category: Primary visa category

        Returns:
            Dict mapping folder names to their IDs
        """
        folders = {}

        client_folder_id = self.get_client_folder(client_name)
        if not client_folder_id:
            return folders

        folders["root"] = client_folder_id

        # Create Internal folder structure
        internal_id = self.get_or_create_folder("Internal", client_folder_id)
        if internal_id:
            folders["Internal"] = internal_id
            for subfolder_name in INTERNAL_FOLDER_STRUCTURE:
                subfolder_id = self.get_or_create_folder(subfolder_name, internal_id)
                if subfolder_id:
                    folders[f"Internal/{subfolder_name}"] = subfolder_id

        # Create Shared with Client folder structure
        shared_id = self.get_or_create_folder("Shared with Client", client_folder_id)
        if shared_id:
            folders["Shared with Client"] = shared_id

            # Create visa-specific subfolders under Shared with Client
            subfolders = VISA_FOLDER_STRUCTURE.get(visa_category, VISA_FOLDER_STRUCTURE["General"])
            for subfolder_name in subfolders:
                subfolder_id = self.get_or_create_folder(subfolder_name, shared_id)
                if subfolder_id:
                    folders[f"Shared with Client/{subfolder_name}"] = subfolder_id

            # Create Recommendation Letters sub-structure if applicable
            if "Recommendation Letters" in subfolders:
                rec_id = folders.get("Shared with Client/Recommendation Letters")
                if rec_id:
                    for sub in ["Signed", "Drafts"]:
                        sub_id = self.get_or_create_folder(sub, rec_id)
                        if sub_id:
                            folders[f"Shared with Client/Recommendation Letters/{sub}"] = sub_id

            # Create Personal Statement sub-structure if applicable
            if "Personal Statement" in subfolders:
                ps_id = folders.get("Shared with Client/Personal Statement")
                if ps_id:
                    drafts_id = self.get_or_create_folder("Drafts", ps_id)
                    if drafts_id:
                        folders["Shared with Client/Personal Statement/Drafts"] = drafts_id

        return folders

    def list_client_documents(self, client_name: str) -> List[Dict[str, Any]]:
        """
        List all documents for a client.

        Args:
            client_name: Client's full name

        Returns:
            List of document metadata dicts
        """
        documents = []

        client_folder_id = self.get_client_folder(client_name)
        if not client_folder_id or not self.service:
            return documents

        try:
            # Recursive search in client folder
            query = f"'{client_folder_id}' in parents and trashed=false"
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name, mimeType, webViewLink, createdTime, size)'
            ).execute()

            for file in results.get('files', []):
                documents.append({
                    "id": file['id'],
                    "name": file['name'],
                    "mime_type": file['mimeType'],
                    "link": file.get('webViewLink'),
                    "created": file.get('createdTime'),
                    "size": file.get('size')
                })

        except Exception as e:
            logger.error(f"Error listing documents: {e}")

        return documents

    def _calculate_file_hash(self, file_path: Path) -> str:
        """
        Calculate SHA256 hash of a file.

        Args:
            file_path: Path to file

        Returns:
            SHA256 hex digest
        """
        import hashlib

        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256.update(chunk)
        return sha256.hexdigest()

    def download_document(
        self,
        file_id: str,
        destination_path: str,
        check_hash: bool = True
    ) -> Optional[str]:
        """
        Download a document from Google Drive.

        Args:
            file_id: Google Drive file ID
            destination_path: Local path to save file
            check_hash: If True, skip download if file already exists with same hash

        Returns:
            SHA256 hash of downloaded file, or None if skipped or failed
        """
        if not self.service:
            logger.error("Google Drive service not connected")
            return None

        try:
            from googleapiclient.http import MediaIoBaseDownload
            import io

            # Get file metadata
            file_metadata = self.service.files().get(
                fileId=file_id,
                fields='name,size,md5Checksum'
            ).execute()

            file_name = file_metadata.get('name', 'unknown')
            dest = Path(destination_path)

            # Check if exists locally and skip if hash matches
            if check_hash and dest.exists():
                local_hash = self._calculate_file_hash(dest)
                drive_md5 = file_metadata.get('md5Checksum')

                # Note: Google Drive MD5 is different from SHA256
                # We skip only if file size matches (simple check)
                file_size = int(file_metadata.get('size', 0))
                local_size = dest.stat().st_size

                if file_size == local_size:
                    logger.info(f"Skipping {file_name} - already exists with same size")
                    return local_hash

            # Download file
            request = self.service.files().get_media(fileId=file_id)
            dest.parent.mkdir(parents=True, exist_ok=True)

            with open(dest, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        progress = int(status.progress() * 100)
                        logger.info(f"Downloading {file_name}: {progress}%")

            # Calculate and return hash
            file_hash = self._calculate_file_hash(dest)
            logger.info(f"Downloaded: {file_name} -> {dest} (hash: {file_hash[:8]}...)")

            return file_hash

        except Exception as e:
            logger.error(f"Download failed for {file_id}: {e}")
            return None

    def download_client_folder(
        self,
        client_name: str,
        destination_base: str,
        skip_existing: bool = True
    ) -> Dict[str, Any]:
        """
        Download entire client folder from Google Drive.

        Args:
            client_name: Client's full name (format: "LAST, First - VISA_TYPE")
            destination_base: Base directory to save files
            skip_existing: If True, skip files that already exist

        Returns:
            Dict with download statistics:
            {
                'downloaded': int,
                'skipped': int,
                'failed': int,
                'total': int,
                'files': [{'name': str, 'hash': str, 'path': str}, ...]
            }
        """
        results = {
            'downloaded': 0,
            'skipped': 0,
            'failed': 0,
            'total': 0,
            'files': []
        }

        if not self.service:
            logger.error("Google Drive service not connected")
            return results

        # Get client folder ID
        folder_id = self.get_client_folder(client_name)
        if not folder_id:
            logger.warning(f"No Drive folder found for client: {client_name}")
            return results

        # List all files in client folder (recursively)
        files = self.list_client_files(client_name, max_results=1000)
        results['total'] = len(files)

        logger.info(f"Found {len(files)} files in Drive for {client_name}")

        for file in files:
            file_id = file['id']
            file_name = file['name']

            # Build destination path
            # Structure: destination_base/client_name/filename
            dest_path = Path(destination_base) / client_name / file_name

            # Download
            file_hash = self.download_document(
                file_id,
                str(dest_path),
                check_hash=skip_existing
            )

            if file_hash:
                if dest_path.exists():
                    results['downloaded'] += 1
                    logger.info(f"✓ Downloaded: {file_name}")
                else:
                    results['skipped'] += 1
                    logger.info(f"⊙ Skipped: {file_name}")
            else:
                results['failed'] += 1
                logger.error(f"✗ Failed: {file_name}")

            results['files'].append({
                'name': file_name,
                'hash': file_hash,
                'path': str(dest_path),
                'status': 'downloaded' if file_hash and dest_path.exists() else ('skipped' if file_hash else 'failed')
            })

        logger.info(f"Download complete for {client_name}: {results['downloaded']} downloaded, {results['skipped']} skipped, {results['failed']} failed")

        return results

    def disconnect_drive_account(self) -> Dict[str, Any]:
        """Revoke the OAuth refresh token on Google and delete the per-org token file.

        Returns:
            Dict with::

                {
                  "revoked": bool,    # True iff Google /revoke returned 2xx
                  "removed_file": bool,  # True iff the per-org json was deleted
                  "org_id": int,
                }

        Idempotent: returns ``revoked=False, removed_file=False`` when no
        token exists, without raising. Network failure surfaces as
        ``revoked=False``; the file is removed locally regardless so the
        org's "connect Drive" UI gets a clean slate.
        """
        from urllib import error as urlerror, parse as urlparse, request as urlrequest

        result = {"revoked": False, "removed_file": False, "org_id": self.org_id}
        token_path = self._token_path

        if not token_path.exists():
            return result

        # Best-effort: load creds purely to get the refresh token for revoke.
        token_to_revoke: Optional[str] = None
        try:
            from google.oauth2.credentials import Credentials

            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
            token_to_revoke = (
                getattr(creds, "refresh_token", None)
                or getattr(creds, "token", None)
            )
        except Exception as e:
            logger.warning("Could not load Drive token for revocation (org %s): %s", self.org_id, e)

        if token_to_revoke:
            try:
                body = urlparse.urlencode({"token": token_to_revoke}).encode("utf-8")
                req = urlrequest.Request(
                    "https://oauth2.googleapis.com/revoke",
                    data=body,
                    method="POST",
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                with urlrequest.urlopen(req, timeout=10) as response:
                    status = getattr(response, "status", response.getcode())
                    result["revoked"] = 200 <= status < 300
            except urlerror.HTTPError as e:
                logger.warning("Drive token revoke returned HTTP %s for org %s", e.code, self.org_id)
            except Exception as e:
                logger.warning("Drive token revoke failed for org %s: %s", self.org_id, e)

        # Always remove the local file so the org card flips to "not connected".
        try:
            token_path.unlink()
            result["removed_file"] = True
        except OSError as e:
            logger.warning("Could not delete Drive token file %s: %s", token_path, e)

        # Drop the cached service so subsequent calls re-check.
        self.service = None
        return result


def check_drive_connection(org_id: Optional[int] = None) -> Dict[str, Any]:
    """Check Google Drive connection status for an org (defaults to DEFAULT_ORG_ID)."""
    resolved_org = int(org_id) if org_id else DEFAULT_ORG_ID
    token_path = get_org_drive_token_path(resolved_org)
    result = {
        "connected": False,
        "credentials_path": CREDENTIALS_PATH,
        "token_path": str(token_path),
        "credentials_exist": os.path.exists(CREDENTIALS_PATH),
        "token_exist": token_path.exists(),
        "org_id": resolved_org,
        "error": None,
    }

    handler = GoogleDriveHandler(db=None, org_id=resolved_org)

    if handler.is_connected():
        result["connected"] = True
        root_id = handler.get_root_folder_id()
        result["root_folder_id"] = root_id
    else:
        result["error"] = (
            "Drive not connected for this org. "
            f"Visit /casehub/integrations to connect (org_id={resolved_org})."
        )

    return result


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    logger.info("Google Drive Handler - CaseHub")
    logger.info("=" * 50)

    # CLI smoke uses DEFAULT_ORG_ID; pass --org=N to target a different tenant.
    org_arg = DEFAULT_ORG_ID
    for arg in sys.argv[1:]:
        if arg.startswith("--org="):
            try:
                org_arg = int(arg.split("=", 1)[1])
            except ValueError:
                pass

    logger.info("Checking Google Drive connection (org=%s)...", org_arg)
    status = check_drive_connection(org_id=org_arg)

    logger.info("  Credentials file: %s", status['credentials_path'])
    logger.info("    Exists: %s", status['credentials_exist'])
    logger.info("  Token file: %s", status['token_path'])
    logger.info("    Exists: %s", status['token_exist'])
    logger.info("  Connected: %s", status['connected'])

    if status['connected']:
        logger.info("  Root folder ID: %s", status.get('root_folder_id'))
    else:
        logger.error("  Error: %s", status.get('error'))

        if not status['credentials_exist']:
            logger.info("To setup Google Drive:")
            logger.info("1. Ativar Google Drive API no Google Cloud.")
            logger.info("2. Salvar credentials/google_drive_credentials.json (OAuth Web).")
            logger.info("3. Conectar pelo CaseHub em /casehub/integrations (NUNCA usar run_local_server).")

    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(positional) >= 2 and status['connected']:
        test_file, client_name = positional[0], positional[1]
        logger.info("Uploading test file: %s (client: %s, org: %s)", test_file, client_name, org_arg)

        handler = GoogleDriveHandler(db=None, org_id=org_arg)
        result = handler.upload_document(
            file_path=test_file,
            client_name=client_name,
            visa_category="EB2-NIW",
            document_type="Evidence",
        )

        if result["success"]:
            logger.info("Success! Link: %s", result['web_link'])
        else:
            logger.error("Failed: %s", result['error'])
    elif len(positional) == 0:
        logger.info("Usage: python google_drive_handler.py [--org=N] [file_path] [client_name]")
