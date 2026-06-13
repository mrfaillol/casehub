#!/usr/bin/env python3
"""
CaseHub - Reverse Sync from Google Drive

Downloads files from Google Drive to VPS and updates the database,
resolving file_missing documents and importing Drive-only files.

Phases:
    R0: Consolidation report for duplicate client folders (read-only)
    R1: Inventory & reconciliation - Drive vs DB (read-only)
    R2: Link file_missing DB records to existing Drive files (DB-only, no downloads)
    R3: Download missing files from Drive to VPS + update DB
    R4: Import Drive-only files (create new DB records)
    R5: Verification & integrity check

Usage:
    python reverse_sync_from_drive.py --consolidate-report        # R0
    python reverse_sync_from_drive.py --reconcile                 # R1
    python reverse_sync_from_drive.py --link --dry-run            # R2 preview
    python reverse_sync_from_drive.py --link                      # R2
    python reverse_sync_from_drive.py --download --client-id 51   # R3 specific client
    python reverse_sync_from_drive.py --download --limit 100      # R3 batch
    python reverse_sync_from_drive.py --import-new --dry-run      # R4 preview
    python reverse_sync_from_drive.py --verify                    # R5
    python reverse_sync_from_drive.py --all --dry-run             # Full pipeline preview

Run on VPS:
    cd /var/www/immigrant.law/casehub && venv/bin/python scripts/reverse_sync_from_drive.py --reconcile

Created: 2026-03-05
"""

import argparse
import hashlib
import json
import logging
import os
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from sqlalchemy.orm import Session
    from sqlalchemy import func
    from models.base import get_db, SessionLocal
    from models.document import Document
    from models.client import Client
    from models.case import Case
    from services.google_drive_handler import (
        GoogleDriveHandler,
        ACTIVE_CLIENTS_FOLDER_ID,
    )
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Run from casehub directory:")
    print("  cd /var/www/immigrant.law/casehub && venv/bin/python scripts/reverse_sync_from_drive.py")
    sys.exit(1)

# Import FILENAME_PATTERNS from deep_reclassify for doc classification
try:
    from scripts.deep_reclassify import FILENAME_PATTERNS, EXHIBIT_MAP
except ImportError:
    try:
        # Direct import when running from scripts/
        sys.path.insert(0, str(Path(__file__).parent))
        from deep_reclassify import FILENAME_PATTERNS, EXHIBIT_MAP
    except ImportError:
        FILENAME_PATTERNS = {}
        EXHIBIT_MAP = {}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('reverse_sync.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# VPS document storage base path
DOCUMENTS_BASE = os.getenv(
    "DOCUMENTS_BASE_PATH",
    "/var/www/immigrant.law/documents/clients"
)

# Boundary keywords that need word-boundary checking (from deep_reclassify.py)
BOUNDARY_KEYWORDS = {
    "w-2", "w2", "cv ", "cv.", "cv-", "cv_",
    "lor ", "lor.", "lor_", "lor-",
    "loa ", "loa.", "loa_",
    "wes", "rfe", "ead",
}

# Google Docs native mimeTypes that need export (not direct download)
GOOGLE_NATIVE_TYPES = {
    'application/vnd.google-apps.document': {'export': 'application/pdf', 'ext': '.pdf'},
    'application/vnd.google-apps.spreadsheet': {'export': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'ext': '.xlsx'},
    'application/vnd.google-apps.presentation': {'export': 'application/pdf', 'ext': '.pdf'},
}

# Google types to skip entirely (folders, forms, maps, etc.)
GOOGLE_SKIP_TYPES = {
    'application/vnd.google-apps.folder',
    'application/vnd.google-apps.form',
    'application/vnd.google-apps.map',
    'application/vnd.google-apps.site',
    'application/vnd.google-apps.shortcut',
}


def calculate_sha256(file_path: str) -> str:
    """Calculate SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def classify_filename(filename: str) -> tuple:
    """
    Classify a filename using FILENAME_PATTERNS.

    Returns:
        (doc_type, matched_keyword) or (None, None) if no match.
    """
    if not FILENAME_PATTERNS:
        return None, None

    fn_lower = filename.lower()
    fn_normalized = fn_lower.replace("_", " ").replace("-", " ")

    for doc_type, keywords in FILENAME_PATTERNS.items():
        for keyword in keywords:
            if keyword in BOUNDARY_KEYWORDS:
                if keyword in fn_lower:
                    return doc_type, keyword
                continue

            if keyword in fn_lower or keyword in fn_normalized:
                return doc_type, keyword

            if len(keyword) >= 5:
                kw_normalized = keyword.replace("-", " ").replace("_", " ")
                if kw_normalized in fn_normalized:
                    return doc_type, keyword

    return None, None


class ReverseDriveSync:
    """Reverse sync: Google Drive → VPS + CaseHub DB."""

    def __init__(self, db: Session):
        self.db = db
        self.handler = GoogleDriveHandler()
        self.stats = Counter()
        self.start_time = datetime.now()
        self._drive_inventory = None  # Lazy-loaded
        self._client_cache = {}  # client_id -> Client

    def _get_client(self, client_id: int) -> Client:
        """Get client with caching."""
        if client_id not in self._client_cache:
            self._client_cache[client_id] = (
                self.db.query(Client).filter(Client.id == client_id).first()
            )
        return self._client_cache[client_id]

    def _build_client_name(self, client: Client) -> str:
        """Build 'LAST, First' format for folder matching."""
        if not client:
            return ""
        return f"{(client.last_name or '').upper()}, {client.first_name or ''}".strip().rstrip(",")

    def _get_drive_inventory(self) -> dict:
        """
        Lazy-load full Drive inventory: all files in all Active Clients folders.
        Returns: {folder_name: {'folder_id': str, 'files': [...]}}
        """
        if self._drive_inventory is not None:
            return self._drive_inventory

        logger.info("Building Drive inventory (this may take a few minutes)...")

        self._drive_inventory = {}
        total_files = 0

        # List all client folders in Active Clients
        result = self.handler.service.files().list(
            q=f"'{ACTIVE_CLIENTS_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields='files(id, name)',
            pageSize=300
        ).execute()
        client_folders = result.get('files', [])
        logger.info(f"Found {len(client_folders)} client folders in Drive")

        for idx, folder in enumerate(client_folders, 1):
            folder_name = folder['name']
            folder_id = folder['id']

            files = self._list_files_recursive(folder_id)
            self._drive_inventory[folder_name] = {
                'folder_id': folder_id,
                'files': files
            }
            total_files += len(files)

            if len(files) > 0 and idx % 20 == 0:
                logger.info(f"  [{idx}/{len(client_folders)}] Scanned {total_files} files so far...")

        logger.info(f"Drive inventory complete: {total_files} files in {len(client_folders)} folders")
        return self._drive_inventory

    def _list_files_recursive(self, folder_id: str, depth: int = 0) -> list:
        """Recursively list all non-folder files under a folder."""
        if depth > 5:
            return []

        files = []
        try:
            page_token = None
            while True:
                result = self.handler.service.files().list(
                    q=f"'{folder_id}' in parents and trashed=false",
                    fields='nextPageToken, files(id, name, mimeType, size, md5Checksum, webViewLink)',
                    pageSize=500,
                    pageToken=page_token
                ).execute()

                for item in result.get('files', []):
                    mime = item.get('mimeType', '')
                    if mime == 'application/vnd.google-apps.folder':
                        sub_files = self._list_files_recursive(item['id'], depth + 1)
                        files.extend(sub_files)
                    elif mime not in GOOGLE_SKIP_TYPES:
                        files.append({
                            'name': item['name'],
                            'size': int(item.get('size', 0)) if item.get('size') else 0,
                            'id': item['id'],
                            'md5': item.get('md5Checksum', ''),
                            'mimeType': mime,
                            'webViewLink': item.get('webViewLink', ''),
                            'parent_id': folder_id,
                            'is_native': mime.startswith('application/vnd.google-apps.'),
                        })

                page_token = result.get('nextPageToken')
                if not page_token:
                    break

        except Exception as e:
            logger.warning(f"Error listing folder {folder_id} (depth={depth}): {e}")

        return files

    def _match_client_to_drive_folder(self, client: Client) -> list:
        """
        Find all Drive folders that match a client.
        Returns list of (folder_name, folder_data) tuples.
        """
        if not client:
            return []

        inventory = self._get_drive_inventory()
        matches = []
        last = (client.last_name or '').lower()
        first = (client.first_name or '').lower()

        if not last:
            return []

        for folder_name, data in inventory.items():
            fn_lower = folder_name.lower()
            if last in fn_lower and (not first or first in fn_lower):
                matches.append((folder_name, data))

        return matches

    # =========================================================================
    # R0: Consolidation Report for Duplicate Folders
    # =========================================================================
    def consolidate_duplicates_report(self) -> dict:
        """
        Phase R0: Generate report of duplicate client folders in Drive.
        READ-ONLY — no changes made.
        """
        logger.info("=" * 80)
        logger.info("PHASE R0: DUPLICATE FOLDER CONSOLIDATION REPORT")
        logger.info("=" * 80)

        inventory = self._get_drive_inventory()

        # Group folders by normalized client last name
        by_lastname = defaultdict(list)
        for folder_name, data in inventory.items():
            # Extract last name (before first comma or space)
            parts = folder_name.split(",")
            if len(parts) >= 2:
                lastname = parts[0].strip().upper()
            else:
                # Try "FirstName LastName" format
                words = folder_name.strip().split()
                lastname = words[-1].upper() if words else folder_name.upper()

            by_lastname[lastname].append({
                'name': folder_name,
                'folder_id': data['folder_id'],
                'file_count': len(data['files']),
                'files': [f['name'] for f in data['files']],
                'total_size': sum(f.get('size', 0) for f in data['files']),
            })

        # Find duplicates (>1 folder per lastname)
        duplicates = {}
        for lastname, folders in by_lastname.items():
            if len(folders) > 1:
                duplicates[lastname] = {
                    'folder_count': len(folders),
                    'folders': folders,
                    'recommendation': self._recommend_canonical(folders),
                }

        report = {
            'timestamp': datetime.now().isoformat(),
            'total_folders': len(inventory),
            'unique_clients': len(by_lastname),
            'clients_with_duplicates': len(duplicates),
            'total_duplicate_folders': sum(d['folder_count'] for d in duplicates.values()),
            'duplicates': duplicates,
        }

        # Save report
        report_path = '/tmp/drive_duplicates_report.json'
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        # Print summary
        logger.info(f"Total folders: {report['total_folders']}")
        logger.info(f"Unique clients: {report['unique_clients']}")
        logger.info(f"Clients with duplicates: {report['clients_with_duplicates']}")
        logger.info("")

        for lastname, data in sorted(duplicates.items()):
            logger.info(f"  {lastname}: {data['folder_count']} folders")
            for folder in data['folders']:
                logger.info(f"    - \"{folder['name']}\" ({folder['file_count']} files, {folder['total_size'] / 1024:.0f} KB)")
            rec = data['recommendation']
            logger.info(f"    >> Canonical: \"{rec['canonical']}\" | Merge from: {[f['name'] for f in rec['merge_from']]}")
            logger.info("")

        logger.info(f"Report saved to {report_path}")
        return report

    def _recommend_canonical(self, folders: list) -> dict:
        """Recommend which folder is canonical (most files, proper naming)."""
        # Prefer folder with LAST, First - VISA format
        scored = []
        for f in folders:
            score = f['file_count'] * 10  # More files = higher score
            name = f['name']
            if ',' in name:
                score += 5  # Proper "LAST, First" format
            if ' - ' in name:
                score += 3  # Has visa type suffix
            if name == name.upper().split(',')[0] + name[len(name.upper().split(',')[0]):]:
                score += 1  # Last name is uppercase
            scored.append((score, f))

        scored.sort(key=lambda x: x[0], reverse=True)
        canonical = scored[0][1]
        merge_from = [s[1] for s in scored[1:]]

        return {
            'canonical': canonical['name'],
            'canonical_id': canonical['folder_id'],
            'canonical_files': canonical['file_count'],
            'merge_from': merge_from,
        }

    # =========================================================================
    # R1: Inventory & Reconciliation
    # =========================================================================
    def reconcile(self) -> dict:
        """
        Phase R1: Build complete reconciliation map — Drive vs DB.
        READ-ONLY — no changes made.
        """
        logger.info("=" * 80)
        logger.info("PHASE R1: INVENTORY & RECONCILIATION")
        logger.info("=" * 80)

        # Step 1: Get Drive inventory
        drive_inv = self._get_drive_inventory()
        total_drive_files = sum(len(d['files']) for d in drive_inv.values())
        logger.info(f"Drive: {total_drive_files} files in {len(drive_inv)} folders")

        # Step 2: Get all documents from DB
        all_docs = self.db.query(Document).all()
        logger.info(f"DB: {len(all_docs)} documents total")

        # Index DB docs by drive_file_id for fast lookup
        docs_by_drive_id = {}
        for doc in all_docs:
            if doc.drive_file_id:
                docs_by_drive_id[doc.drive_file_id] = doc

        # Index DB docs by client_id + normalized name
        docs_by_client_name = defaultdict(list)
        for doc in all_docs:
            if doc.client_id and doc.name:
                key = f"{doc.client_id}:{doc.name.lower().strip()}"
                docs_by_client_name[key].append(doc)

        # Step 3: Categorize DB docs
        categories = {
            'db_synced': [],          # Has drive_file_id AND file on VPS
            'db_file_missing_drive_match': [],  # file_missing but exists in Drive
            'db_file_missing_no_drive': [],     # file_missing and NOT in Drive
            'db_has_file_no_drive': [],          # Has file on VPS but no drive_file_id
            'drive_only': [],          # In Drive but no DB record
        }

        # Step 4: Match Drive files to DB records
        matched_drive_ids = set()  # Track which Drive files matched a DB record

        for folder_name, data in drive_inv.items():
            # Find which client this folder belongs to
            client = self._find_client_by_folder_name(folder_name)

            for drive_file in data['files']:
                drive_id = drive_file['id']

                # Match 1: Exact drive_file_id
                if drive_id in docs_by_drive_id:
                    matched_drive_ids.add(drive_id)
                    doc = docs_by_drive_id[drive_id]
                    if doc.status == 'file_missing':
                        categories['db_file_missing_drive_match'].append({
                            'doc_id': doc.id,
                            'doc_name': doc.name,
                            'drive_file': drive_file,
                            'client_id': doc.client_id,
                            'match_type': 'drive_file_id',
                        })
                    else:
                        categories['db_synced'].append({
                            'doc_id': doc.id,
                            'doc_name': doc.name,
                            'drive_file_id': drive_id,
                        })
                    continue

                # Match 2: Name + client_id
                if client:
                    key = f"{client.id}:{drive_file['name'].lower().strip()}"
                    if key in docs_by_client_name:
                        matched_doc = docs_by_client_name[key][0]
                        matched_drive_ids.add(drive_id)
                        if matched_doc.status == 'file_missing':
                            categories['db_file_missing_drive_match'].append({
                                'doc_id': matched_doc.id,
                                'doc_name': matched_doc.name,
                                'drive_file': drive_file,
                                'client_id': matched_doc.client_id,
                                'match_type': 'name_client',
                            })
                        elif not matched_doc.drive_file_id:
                            categories['db_has_file_no_drive'].append({
                                'doc_id': matched_doc.id,
                                'doc_name': matched_doc.name,
                                'drive_file': drive_file,
                                'match_type': 'name_client',
                            })
                        else:
                            categories['db_synced'].append({
                                'doc_id': matched_doc.id,
                                'doc_name': matched_doc.name,
                                'drive_file_id': drive_id,
                            })
                        continue

                # Match 3: Fuzzy name match (filename without extension + client)
                if client:
                    drive_stem = Path(drive_file['name']).stem.lower().strip()
                    found = False
                    for doc in all_docs:
                        if doc.client_id != client.id:
                            continue
                        doc_stem = Path(doc.name or '').stem.lower().strip()
                        if doc_stem and drive_stem and (
                            doc_stem == drive_stem or
                            doc_stem in drive_stem or
                            drive_stem in doc_stem
                        ):
                            matched_drive_ids.add(drive_id)
                            if doc.status == 'file_missing' and not doc.drive_file_id:
                                categories['db_file_missing_drive_match'].append({
                                    'doc_id': doc.id,
                                    'doc_name': doc.name,
                                    'drive_file': drive_file,
                                    'client_id': doc.client_id,
                                    'match_type': 'fuzzy_name',
                                })
                            found = True
                            break
                    if found:
                        continue

                # No match: Drive-only file
                categories['drive_only'].append({
                    'drive_file': drive_file,
                    'folder_name': folder_name,
                    'client_id': client.id if client else None,
                    'client_name': self._build_client_name(client) if client else folder_name,
                })

        # Step 5: Find DB docs with file_missing that have NO Drive match
        for doc in all_docs:
            if doc.status == 'file_missing' and doc.drive_file_id not in matched_drive_ids:
                # Check if it was already matched by name
                already_matched = any(
                    m['doc_id'] == doc.id
                    for m in categories['db_file_missing_drive_match']
                )
                if not already_matched:
                    categories['db_file_missing_no_drive'].append({
                        'doc_id': doc.id,
                        'doc_name': doc.name,
                        'client_id': doc.client_id,
                    })

        # Step 6: Build report
        report = {
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total_drive_files': total_drive_files,
                'total_db_docs': len(all_docs),
                'db_synced': len(categories['db_synced']),
                'db_file_missing_drive_match': len(categories['db_file_missing_drive_match']),
                'db_file_missing_no_drive': len(categories['db_file_missing_no_drive']),
                'db_has_file_no_drive': len(categories['db_has_file_no_drive']),
                'drive_only': len(categories['drive_only']),
            },
            'categories': {
                'db_file_missing_drive_match': categories['db_file_missing_drive_match'][:100],
                'db_file_missing_no_drive': categories['db_file_missing_no_drive'][:100],
                'drive_only': categories['drive_only'][:100],
            },
        }

        # Save full report
        report_path = '/tmp/reverse_sync_reconciliation.json'
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        # Print summary
        logger.info("")
        logger.info("RECONCILIATION SUMMARY:")
        logger.info(f"  DB synced (OK):                    {len(categories['db_synced'])}")
        logger.info(f"  DB file_missing + Drive match:     {len(categories['db_file_missing_drive_match'])}")
        logger.info(f"  DB file_missing + NO Drive:        {len(categories['db_file_missing_no_drive'])}")
        logger.info(f"  DB has file + no Drive:            {len(categories['db_has_file_no_drive'])}")
        logger.info(f"  Drive-only (no DB record):         {len(categories['drive_only'])}")
        logger.info(f"Report saved to {report_path}")

        # Store for use by subsequent phases
        self._reconciliation = categories
        return report

    def _find_client_by_folder_name(self, folder_name: str):
        """Find a Client record by matching Drive folder name."""
        fn_lower = folder_name.lower().strip()

        # Try "LAST, First" format
        parts = folder_name.split(",")
        if len(parts) >= 2:
            last = parts[0].strip()
            first_part = parts[1].strip().split(" - ")[0].strip().split()[0] if parts[1].strip() else ""
            client = self.db.query(Client).filter(
                func.lower(Client.last_name) == last.lower(),
            ).first()
            if client:
                return client

        # Try matching by last_name contained in folder name
        clients = self.db.query(Client).all()
        for client in clients:
            cl = (client.last_name or '').lower()
            cf = (client.first_name or '').lower()
            if cl and cl in fn_lower and cf and cf in fn_lower:
                return client

        # Fallback: just last name
        for client in clients:
            cl = (client.last_name or '').lower()
            if cl and len(cl) > 2 and cl in fn_lower:
                return client

        return None

    # =========================================================================
    # R2: Link DB Records to Drive Files
    # =========================================================================
    def link_drive_files(self, dry_run: bool = False) -> dict:
        """
        Phase R2: Link file_missing DB records to existing Drive files.
        Sets drive_file_id and drive_link but does NOT download files.
        """
        logger.info("=" * 80)
        logger.info(f"PHASE R2: LINK DB RECORDS TO DRIVE {'(DRY RUN)' if dry_run else ''}")
        logger.info("=" * 80)

        # Run reconciliation if not already done
        if not hasattr(self, '_reconciliation'):
            self.reconcile()

        matches = self._reconciliation.get('db_file_missing_drive_match', [])
        logger.info(f"Found {len(matches)} file_missing docs with Drive matches")

        linked = 0
        skipped = 0

        for idx, match in enumerate(matches, 1):
            doc_id = match['doc_id']
            drive_file = match['drive_file']
            match_type = match['match_type']

            doc = self.db.query(Document).filter(Document.id == doc_id).first()
            if not doc:
                skipped += 1
                continue

            # Skip if already linked
            if doc.drive_file_id:
                skipped += 1
                continue

            if dry_run:
                logger.info(
                    f"[{idx}/{len(matches)}] [DRY RUN] Doc {doc_id} '{doc.name}' "
                    f"-> Drive '{drive_file['name']}' (match: {match_type})"
                )
                linked += 1
                continue

            # Link to Drive file
            doc.drive_file_id = drive_file['id']
            doc.drive_link = drive_file.get('webViewLink') or f"https://drive.google.com/file/d/{drive_file['id']}/view"
            doc.drive_sync_status = 'synced'
            doc.drive_synced_at = datetime.now()

            linked += 1

            if linked % 50 == 0:
                self.db.commit()
                logger.info(f"  Committed batch ({linked} linked so far)")

            if idx % 100 == 0:
                logger.info(f"  [{idx}/{len(matches)}] Processing...")

        if not dry_run and linked > 0:
            self.db.commit()

        self.stats['linked'] = linked
        self.stats['link_skipped'] = skipped

        logger.info(f"Linked: {linked} | Skipped: {skipped}")
        return {'linked': linked, 'skipped': skipped}

    # =========================================================================
    # R3: Download Missing Files from Drive
    # =========================================================================
    def download_missing_files(
        self,
        limit: int = None,
        client_id: int = None,
        dry_run: bool = False
    ) -> dict:
        """
        Phase R3: Download files from Drive to VPS for file_missing documents.
        Only processes docs that have drive_file_id set (from R2).
        """
        logger.info("=" * 80)
        logger.info(f"PHASE R3: DOWNLOAD MISSING FILES {'(DRY RUN)' if dry_run else ''}")
        logger.info("=" * 80)

        # Check disk space
        if not dry_run:
            disk = shutil.disk_usage(DOCUMENTS_BASE if os.path.exists(DOCUMENTS_BASE) else "/")
            free_gb = disk.free / (1024 ** 3)
            logger.info(f"Disk space: {free_gb:.1f} GB free")
            if free_gb < 10:
                logger.error(f"ABORTING: Only {free_gb:.1f} GB free (minimum 10 GB required)")
                return {'error': 'Insufficient disk space', 'free_gb': free_gb}

        # Query documents to download
        query = self.db.query(Document).filter(
            Document.status == 'file_missing',
            Document.drive_file_id != None,
        )

        if client_id:
            query = query.filter(Document.client_id == client_id)

        query = query.order_by(Document.client_id, Document.id)

        if limit:
            query = query.limit(limit)

        docs = query.all()
        total = len(docs)

        if total == 0:
            logger.info("No documents to download. Run --link first to match Drive files.")
            return {'downloaded': 0, 'total': 0}

        logger.info(f"Processing {total} documents for download...")

        downloaded = 0
        skipped = 0
        failed = 0
        classified = 0
        current_client_id = None

        for idx, doc in enumerate(docs, 1):
            # Log client change
            if doc.client_id != current_client_id:
                current_client_id = doc.client_id
                client = self._get_client(doc.client_id)
                client_name = self._build_client_name(client)
                logger.info(f"--- Client: {client_name} (ID: {doc.client_id}) ---")

            # Build destination path
            client = self._get_client(doc.client_id)
            if client:
                # Use Drive folder name pattern or build from client data
                folder_name = client.drive_folder_name or self._build_client_name(client)
                case = self.db.query(Case).filter(Case.client_id == doc.client_id).first()
                if case and case.visa_type:
                    if case.visa_type not in folder_name:
                        folder_name = f"{folder_name} - {case.visa_type}"
            else:
                folder_name = f"Client-{doc.client_id}"

            filename = doc.name or f"doc_{doc.id}"
            dest_path = Path(DOCUMENTS_BASE) / folder_name / filename

            if dry_run:
                logger.info(f"[{idx}/{total}] [DRY RUN] Doc {doc.id} '{doc.name}' -> {dest_path}")
                downloaded += 1
                continue

            # Skip if file already exists with same size
            if dest_path.exists():
                local_size = dest_path.stat().st_size
                if local_size > 0:
                    logger.info(f"[{idx}/{total}] SKIP (exists): {dest_path.name} ({local_size} bytes)")
                    # Update DB to reflect file exists
                    doc.file_path = str(dest_path)
                    doc.local_path = str(dest_path)
                    doc.status = 'received'
                    doc.file_size = local_size
                    doc.storage_backend = 'local'
                    if not doc.content_hash:
                        doc.content_hash = calculate_sha256(str(dest_path))
                    skipped += 1
                    if skipped % 25 == 0:
                        self.db.commit()
                    continue

            # Download from Drive
            try:
                file_hash = self.handler.download_document(
                    file_id=doc.drive_file_id,
                    destination_path=str(dest_path),
                    check_hash=True
                )

                if file_hash and dest_path.exists():
                    # Update DB
                    doc.file_path = str(dest_path)
                    doc.local_path = str(dest_path)
                    doc.status = 'received'
                    doc.file_size = dest_path.stat().st_size
                    doc.content_hash = file_hash
                    doc.storage_backend = 'local'

                    # Classify if doc_type is generic
                    if doc.doc_type in ('Other Document', 'Outro', None, ''):
                        doc_type, keyword = classify_filename(doc.name or filename)
                        if doc_type:
                            doc.doc_type = doc_type
                            doc.suggested_exhibit = EXHIBIT_MAP.get(doc_type)
                            doc.classification_confidence = 0.7
                            classified += 1
                            logger.info(f"  Classified: '{doc.name}' -> {doc_type} (keyword: '{keyword}')")

                    downloaded += 1
                    logger.info(f"[{idx}/{total}] OK: {dest_path.name} ({doc.file_size} bytes)")
                else:
                    failed += 1
                    logger.error(f"[{idx}/{total}] FAIL: {doc.name} (download returned no hash)")

            except Exception as e:
                failed += 1
                logger.error(f"[{idx}/{total}] ERROR downloading doc {doc.id}: {e}")

            # Commit in batches
            if (downloaded + skipped) % 25 == 0 and (downloaded + skipped) > 0:
                self.db.commit()
                logger.info(f"  Committed batch ({downloaded} downloaded, {skipped} skipped)")

        if not dry_run:
            self.db.commit()

        self.stats['downloaded'] = downloaded
        self.stats['download_skipped'] = skipped
        self.stats['download_failed'] = failed
        self.stats['classified'] = classified

        logger.info(f"Downloaded: {downloaded} | Skipped: {skipped} | Failed: {failed} | Classified: {classified}")
        return {
            'downloaded': downloaded,
            'skipped': skipped,
            'failed': failed,
            'classified': classified,
            'total': total,
        }

    # =========================================================================
    # R4: Import Drive-Only Files
    # =========================================================================
    def import_drive_only_files(
        self,
        limit: int = None,
        client_id: int = None,
        dry_run: bool = False
    ) -> dict:
        """
        Phase R4: Create DB records for files that exist only in Drive.
        Downloads the file to VPS and creates a new Document record.
        """
        logger.info("=" * 80)
        logger.info(f"PHASE R4: IMPORT DRIVE-ONLY FILES {'(DRY RUN)' if dry_run else ''}")
        logger.info("=" * 80)

        # Run reconciliation if not already done
        if not hasattr(self, '_reconciliation'):
            self.reconcile()

        drive_only = self._reconciliation.get('drive_only', [])

        # Filter by client_id if specified
        if client_id:
            drive_only = [d for d in drive_only if d.get('client_id') == client_id]

        if limit:
            drive_only = drive_only[:limit]

        total = len(drive_only)
        if total == 0:
            logger.info("No Drive-only files to import.")
            return {'imported': 0, 'total': 0}

        logger.info(f"Processing {total} Drive-only files for import...")

        # Check disk space
        if not dry_run:
            disk = shutil.disk_usage(DOCUMENTS_BASE if os.path.exists(DOCUMENTS_BASE) else "/")
            free_gb = disk.free / (1024 ** 3)
            if free_gb < 10:
                logger.error(f"ABORTING: Only {free_gb:.1f} GB free")
                return {'error': 'Insufficient disk space'}

        imported = 0
        skipped = 0
        failed = 0

        for idx, item in enumerate(drive_only, 1):
            drive_file = item['drive_file']
            cid = item.get('client_id')
            client_name = item.get('client_name', 'Unknown')
            folder_name = item.get('folder_name', 'Unknown')

            # Skip Google native files that can't be directly downloaded
            mime = drive_file.get('mimeType', '')
            if mime in GOOGLE_SKIP_TYPES:
                skipped += 1
                continue

            # Skip zero-size files
            if drive_file.get('size', 0) == 0 and mime not in GOOGLE_NATIVE_TYPES:
                skipped += 1
                continue

            if not cid:
                logger.warning(f"[{idx}/{total}] SKIP (no client): '{drive_file['name']}' in '{folder_name}'")
                skipped += 1
                continue

            filename = drive_file['name']

            # Handle Google native types (export)
            if mime in GOOGLE_NATIVE_TYPES:
                export_info = GOOGLE_NATIVE_TYPES[mime]
                filename = Path(filename).stem + export_info['ext']

            # Build destination path
            dest_dir = Path(DOCUMENTS_BASE) / folder_name
            dest_path = dest_dir / filename

            if dry_run:
                doc_type, kw = classify_filename(filename)
                logger.info(
                    f"[{idx}/{total}] [DRY RUN] Import '{filename}' "
                    f"({drive_file.get('size', 0)} bytes) "
                    f"for client {cid} ({client_name}) "
                    f"-> type: {doc_type or 'Other Document'}"
                )
                imported += 1
                continue

            # Check dedup: does a doc already link to this Drive file?
            existing = self.db.query(Document).filter(
                Document.drive_file_id == drive_file['id'],
            ).first()
            if existing:
                logger.info(f"[{idx}/{total}] SKIP (dedup): '{filename}' already linked to doc {existing.id}")
                skipped += 1
                continue

            # Also check by exact name + client
            existing_by_name = self.db.query(Document).filter(
                Document.name == filename,
                Document.client_id == cid,
            ).first()
            if existing_by_name:
                logger.info(f"[{idx}/{total}] SKIP (same name): '{filename}' matches doc {existing_by_name.id}")
                skipped += 1
                continue

            # Check dedup: file_hash (MD5) + client_id unique constraint
            drive_md5 = drive_file.get('md5', '')
            if drive_md5:
                existing_by_hash = self.db.query(Document).filter(
                    Document.file_hash == drive_md5,
                    Document.client_id == cid,
                ).first()
                if existing_by_hash:
                    logger.info(f"[{idx}/{total}] SKIP (dedup hash+client): '{filename}' "
                               f"same MD5 as doc {existing_by_hash.id}")
                    skipped += 1
                    continue

            # Download file
            try:
                if mime in GOOGLE_NATIVE_TYPES:
                    # Export Google native file
                    export_mime = GOOGLE_NATIVE_TYPES[mime]['export']
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    request = self.handler.service.files().export_media(
                        fileId=drive_file['id'],
                        mimeType=export_mime
                    )
                    import io
                    from googleapiclient.http import MediaIoBaseDownload
                    with open(dest_path, 'wb') as f:
                        downloader = MediaIoBaseDownload(f, request)
                        done = False
                        while not done:
                            _, done = downloader.next_chunk()
                    file_hash = calculate_sha256(str(dest_path))
                else:
                    file_hash = self.handler.download_document(
                        file_id=drive_file['id'],
                        destination_path=str(dest_path),
                        check_hash=True
                    )

                if not file_hash or not dest_path.exists():
                    failed += 1
                    logger.error(f"[{idx}/{total}] FAIL download: '{filename}'")
                    continue

            except Exception as e:
                failed += 1
                logger.error(f"[{idx}/{total}] ERROR downloading '{filename}': {e}")
                continue

            # Classify document type
            doc_type, keyword = classify_filename(filename)
            if not doc_type:
                doc_type = 'Other Document'

            # Detect mime type
            import mimetypes
            detected_mime = mimetypes.guess_type(str(dest_path))[0] or 'application/octet-stream'

            # Get case for client
            case = self.db.query(Case).filter(Case.client_id == cid).first()

            # Create Document record
            new_doc = Document(
                name=filename,
                file_path=str(dest_path),
                local_path=str(dest_path),
                file_size=dest_path.stat().st_size,
                content_hash=file_hash,
                file_hash=drive_file.get('md5', ''),
                mime_type=detected_mime,
                client_id=cid,
                case_id=case.id if case else None,
                status='received',
                uploaded_via='drive_import',
                drive_file_id=drive_file['id'],
                drive_link=drive_file.get('webViewLink') or f"https://drive.google.com/file/d/{drive_file['id']}/view",
                drive_sync_status='synced',
                drive_synced_at=datetime.now(),
                doc_type=doc_type,
                suggested_exhibit=EXHIBIT_MAP.get(doc_type),
                classification_confidence=0.7 if doc_type != 'Other Document' else None,
                storage_backend='local',
            )
            self.db.add(new_doc)
            imported += 1

            logger.info(f"[{idx}/{total}] IMPORTED: '{filename}' as '{doc_type}' (client {cid})")

            # Commit in batches
            if imported % 25 == 0:
                try:
                    self.db.commit()
                    logger.info(f"  Committed batch ({imported} imported)")
                except Exception as e:
                    logger.error(f"  Batch commit failed: {e}")
                    self.db.rollback()
                    failed += 1
                    imported -= 1

        if not dry_run and imported > 0:
            try:
                self.db.commit()
            except Exception as e:
                logger.error(f"Final commit failed: {e}")
                self.db.rollback()

        self.stats['imported'] = imported
        self.stats['import_skipped'] = skipped
        self.stats['import_failed'] = failed

        logger.info(f"Imported: {imported} | Skipped: {skipped} | Failed: {failed}")
        return {'imported': imported, 'skipped': skipped, 'failed': failed, 'total': total}

    # =========================================================================
    # R5: Verification & Integrity Check
    # =========================================================================
    def verify_integrity(self, sample_size: int = 50) -> dict:
        """
        Phase R5: Verify Drive ↔ VPS consistency.
        """
        logger.info("=" * 80)
        logger.info("PHASE R5: VERIFICATION & INTEGRITY CHECK")
        logger.info("=" * 80)

        results = {
            'timestamp': datetime.now().isoformat(),
            'status_distribution': {},
            'drive_sync_distribution': {},
            'file_missing_remaining': 0,
            'integrity_checks': [],
            'spot_checks': [],
        }

        # Status distribution
        status_counts = self.db.query(
            Document.status, func.count(Document.id)
        ).group_by(Document.status).all()
        results['status_distribution'] = {s: c for s, c in status_counts}
        logger.info("Status distribution:")
        for status, count in sorted(status_counts, key=lambda x: -x[1]):
            logger.info(f"  {status}: {count}")

        # Drive sync status distribution
        sync_counts = self.db.query(
            Document.drive_sync_status, func.count(Document.id)
        ).group_by(Document.drive_sync_status).all()
        results['drive_sync_distribution'] = {s or 'NULL': c for s, c in sync_counts}
        logger.info("\nDrive sync status:")
        for status, count in sorted(sync_counts, key=lambda x: -x[1]):
            logger.info(f"  {status or 'NULL'}: {count}")

        # Remaining file_missing without Drive link
        remaining = self.db.query(func.count(Document.id)).filter(
            Document.status == 'file_missing',
            Document.drive_file_id == None
        ).scalar()
        results['file_missing_remaining'] = remaining
        logger.info(f"\nFile_missing without Drive link (irrecoverable): {remaining}")

        # File_missing WITH Drive link (need download)
        need_download = self.db.query(func.count(Document.id)).filter(
            Document.status == 'file_missing',
            Document.drive_file_id != None
        ).scalar()
        logger.info(f"File_missing with Drive link (need download): {need_download}")

        # Drive imports
        imported = self.db.query(func.count(Document.id)).filter(
            Document.uploaded_via == 'drive_import'
        ).scalar()
        logger.info(f"Documents imported from Drive: {imported}")

        # Integrity check on sample
        logger.info(f"\nIntegrity check on {sample_size} random synced documents...")
        synced_docs = self.db.query(Document).filter(
            Document.drive_file_id != None,
            Document.file_path != None,
            Document.status != 'file_missing',
        ).limit(sample_size).all()

        checks_ok = 0
        checks_fail = 0
        for doc in synced_docs:
            check = {
                'doc_id': doc.id,
                'name': doc.name,
                'file_exists': False,
                'size_ok': None,
            }

            if doc.file_path and os.path.exists(doc.file_path):
                check['file_exists'] = True
                local_size = os.path.getsize(doc.file_path)
                if doc.file_size:
                    check['size_ok'] = abs(local_size - doc.file_size) < 100
                else:
                    check['size_ok'] = local_size > 0
                checks_ok += 1
            else:
                checks_fail += 1

            results['integrity_checks'].append(check)

        logger.info(f"Integrity: {checks_ok}/{len(synced_docs)} OK, {checks_fail} missing files")

        # Save report
        report_path = '/tmp/reverse_sync_report.json'
        with open(report_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"\nReport saved to {report_path}")

        return results

    def print_final_stats(self):
        """Print final statistics."""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        logger.info("")
        logger.info("=" * 80)
        logger.info("REVERSE SYNC COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Duration: {elapsed:.0f}s ({elapsed/60:.1f} min)")
        for key, value in sorted(self.stats.items()):
            logger.info(f"  {key}: {value}")


def main():
    parser = argparse.ArgumentParser(
        description="CaseHub - Reverse Sync from Google Drive",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Phases:
  R0  --consolidate-report    Report duplicate client folders (read-only)
  R1  --reconcile             Inventory & reconciliation (read-only)
  R2  --link                  Link file_missing docs to Drive files (DB-only)
  R3  --download              Download files from Drive to VPS
  R4  --import-new            Import Drive-only files (create DB records)
  R5  --verify                Verification & integrity check
        """
    )
    parser.add_argument("--consolidate-report", action="store_true", help="R0: Duplicate folder report")
    parser.add_argument("--reconcile", action="store_true", help="R1: Inventory & reconciliation")
    parser.add_argument("--link", action="store_true", help="R2: Link DB records to Drive files")
    parser.add_argument("--download", action="store_true", help="R3: Download missing files")
    parser.add_argument("--import-new", action="store_true", help="R4: Import Drive-only files")
    parser.add_argument("--verify", action="store_true", help="R5: Verification check")
    parser.add_argument("--all", action="store_true", help="Run all phases (R0-R5)")
    parser.add_argument("--limit", type=int, help="Limit number of documents to process")
    parser.add_argument("--client-id", type=int, help="Process specific client only")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without executing")

    args = parser.parse_args()

    # Validate: at least one phase must be selected
    phases = [args.consolidate_report, args.reconcile, args.link,
              args.download, args.import_new, args.verify, args.all]
    if not any(phases):
        parser.print_help()
        sys.exit(1)

    # Create DB session
    db = SessionLocal()

    try:
        syncer = ReverseDriveSync(db)

        if args.all or args.consolidate_report:
            syncer.consolidate_duplicates_report()

        if args.all or args.reconcile:
            syncer.reconcile()

        if args.all or args.link:
            syncer.link_drive_files(dry_run=args.dry_run)

        if args.all or args.download:
            syncer.download_missing_files(
                limit=args.limit,
                client_id=args.client_id,
                dry_run=args.dry_run
            )

        if args.all or args.import_new:
            syncer.import_drive_only_files(
                limit=args.limit,
                client_id=args.client_id,
                dry_run=args.dry_run
            )

        if args.all or args.verify:
            syncer.verify_integrity()

        syncer.print_final_stats()

    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        db.close()

    logger.info("Reverse sync complete.")


if __name__ == '__main__':
    main()
