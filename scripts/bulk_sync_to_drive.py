#!/usr/bin/env python3
"""
CaseHub - Bulk Sync Documents to Google Drive

Syncs VPS documents to Google Drive with dedup:
1. Inventories existing Drive files (prevents duplicate uploads)
2. Links DB records to existing Drive files when found
3. Uploads truly new files to correct client/visa/doctype folders

Usage:
    python bulk_sync_to_drive.py --inventory              # Phase B1: inventory only
    python bulk_sync_to_drive.py --sync --limit 10        # Phase B3: sync 10 docs
    python bulk_sync_to_drive.py --sync --client-id 42    # Sync specific client
    python bulk_sync_to_drive.py --sync --dry-run         # Show what would be synced
    python bulk_sync_to_drive.py --all                    # Full pipeline

Created: 2026-03-04
"""

import asyncio
import argparse
import sys
import os
import logging
import json
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from sqlalchemy import func

try:
    from models.base import get_db
    from models.document import Document
    from models.client import Client
    from models.case import Case
    from services.google_drive_handler import GoogleDriveHandler
    from services.document_sync import sync_to_google_drive
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure you're running this from the casehub directory")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bulk_drive_sync.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class BulkDriveSync:
    """Bulk sync documents to Google Drive with deduplication."""

    def __init__(self, db: Session):
        self.db = db
        self.handler = GoogleDriveHandler()
        self.drive_inventory = {}  # {client_folder_id: [{name, size, id}, ...]}
        self.stats = Counter()
        self.start_time = datetime.now()

    def inventory_drive_files(self):
        """
        Phase B1: Inventory all existing files in Drive client folders.
        Returns dict: {client_folder_name: [{name, size, id, parents}, ...]}
        """
        logger.info("=" * 80)
        logger.info("PHASE B1: INVENTORY EXISTING DRIVE FILES")
        logger.info("=" * 80)

        active_clients_id = os.getenv(
            "GOOGLE_DRIVE_ACTIVE_CLIENTS_ID",
            "1QrKRWyblX4aQHMuO4HIoazxHf1QeTU1l"
        )

        # List all client folders
        result = self.handler.service.files().list(
            q=f"'{active_clients_id}' in parents and mimeType='application/vnd.google-apps.folder'",
            fields='files(id, name)',
            pageSize=200
        ).execute()
        client_folders = result.get('files', [])
        logger.info(f"Found {len(client_folders)} client folders in Drive")

        total_files = 0
        for idx, folder in enumerate(client_folders, 1):
            folder_name = folder['name']
            folder_id = folder['id']

            # Recursively list all files in this client folder
            files = self._list_files_recursive(folder_id)
            self.drive_inventory[folder_name] = {
                'folder_id': folder_id,
                'files': files
            }
            total_files += len(files)

            if len(files) > 0:
                logger.info(f"[{idx}/{len(client_folders)}] {folder_name}: {len(files)} files")

        logger.info(f"Total files in Drive: {total_files}")
        logger.info(f"Inventory complete in {(datetime.now() - self.start_time).total_seconds():.1f}s")

        # Save inventory to file for debugging
        inventory_summary = {
            name: {
                'folder_id': data['folder_id'],
                'file_count': len(data['files']),
                'filenames': [f['name'] for f in data['files'][:10]]  # first 10 for preview
            }
            for name, data in self.drive_inventory.items()
        }
        with open('/tmp/drive_inventory.json', 'w') as f:
            json.dump(inventory_summary, f, indent=2)
        logger.info("Inventory saved to /tmp/drive_inventory.json")

        return self.drive_inventory

    def _list_files_recursive(self, folder_id, depth=0):
        """Recursively list all non-folder files under a folder."""
        if depth > 5:  # Safety limit
            return []

        files = []
        try:
            result = self.handler.service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields='files(id, name, mimeType, size, md5Checksum)',
                pageSize=500
            ).execute()
            items = result.get('files', [])

            for item in items:
                if item['mimeType'] == 'application/vnd.google-apps.folder':
                    # Recurse into subfolder
                    sub_files = self._list_files_recursive(item['id'], depth + 1)
                    files.extend(sub_files)
                else:
                    files.append({
                        'name': item['name'],
                        'size': int(item.get('size', 0)),
                        'id': item['id'],
                        'md5': item.get('md5Checksum', ''),
                        'parent_id': folder_id
                    })
        except Exception as e:
            logger.warning(f"Error listing folder {folder_id}: {e}")

        return files

    def find_in_drive_inventory(self, filename, file_size, client_name):
        """Check if a file already exists in Drive by name+size matching."""
        # Normalize filename for comparison
        filename_lower = filename.lower().strip()

        # Search through client folders that match the client name
        for folder_name, data in self.drive_inventory.items():
            # Check if this folder belongs to the client
            folder_lower = folder_name.lower()
            client_parts = client_name.lower().split()

            # Match if client last name is in folder name
            if not any(part in folder_lower for part in client_parts if len(part) > 2):
                continue

            for drive_file in data['files']:
                drive_name = drive_file['name'].lower().strip()
                drive_size = drive_file.get('size', 0)

                # Match by exact filename
                if drive_name == filename_lower:
                    return drive_file

                # Match by filename + size (handles renamed files)
                if file_size > 0 and drive_size > 0 and abs(drive_size - file_size) < 100:
                    # Size within 100 bytes - likely same file
                    if drive_name == filename_lower:
                        return drive_file

        return None

    def link_existing_drive_files(self):
        """
        Phase B1b: Link DB records to existing Drive files found in inventory.
        For documents where the file already exists in Drive, set drive_file_id
        without re-uploading.
        """
        logger.info("=" * 80)
        logger.info("PHASE B1b: LINK EXISTING DRIVE FILES")
        logger.info("=" * 80)

        # Get all documents with files that aren't synced yet
        docs = self.db.query(Document).filter(
            Document.drive_sync_status.in_(['not_synced', None]),
            Document.drive_file_id == None,
            Document.status != 'file_missing',
            Document.duplicate_of == None
        ).all()

        logger.info(f"Checking {len(docs)} documents against Drive inventory...")

        linked = 0
        for doc in docs:
            if not doc.file_path:
                continue

            filename = Path(doc.file_path).name
            file_size = 0
            try:
                if os.path.exists(doc.file_path):
                    file_size = os.path.getsize(doc.file_path)
            except OSError:
                pass

            # Get client name
            client = self.db.query(Client).filter(Client.id == doc.client_id).first()
            if not client:
                continue
            client_name = f"{client.last_name} {client.first_name}"

            # Check Drive inventory
            drive_file = self.find_in_drive_inventory(filename, file_size, client_name)
            if drive_file:
                doc.drive_file_id = drive_file['id']
                doc.drive_link = f"https://drive.google.com/file/d/{drive_file['id']}/view"
                doc.drive_sync_status = 'synced'
                doc.drive_synced_at = datetime.now()
                linked += 1

                if linked % 50 == 0:
                    self.db.commit()
                    logger.info(f"  Linked {linked} documents so far...")

        self.db.commit()
        self.stats['linked'] = linked
        logger.info(f"Linked {linked} documents to existing Drive files")

    def sync_documents(self, limit=None, client_id=None, dry_run=False):
        """
        Phase B3: Upload new documents to Drive.
        Only uploads files not already in Drive (checked via inventory + content_hash).
        """
        logger.info("=" * 80)
        logger.info(f"PHASE B3: SYNC DOCUMENTS TO DRIVE {'(DRY RUN)' if dry_run else ''}")
        logger.info("=" * 80)

        # Build query for syncable documents
        query = self.db.query(Document).filter(
            Document.drive_sync_status.in_(['not_synced', None]),
            Document.drive_file_id == None,
            Document.status != 'file_missing',
            Document.duplicate_of == None
        )

        if client_id:
            query = query.filter(Document.client_id == client_id)

        # Order by client_id for efficient Drive folder lookup
        query = query.order_by(Document.client_id, Document.id)

        if limit:
            query = query.limit(limit)

        docs = query.all()
        total = len(docs)

        if total == 0:
            logger.info("No documents to sync")
            return

        logger.info(f"Syncing {total} documents...")

        current_client_id = None
        for idx, doc in enumerate(docs, 1):
            try:
                # Log client change
                if doc.client_id != current_client_id:
                    current_client_id = doc.client_id
                    client = self.db.query(Client).filter(Client.id == doc.client_id).first()
                    client_name = f"{client.last_name}, {client.first_name}" if client else "Unknown"
                    logger.info(f"--- Client: {client_name} (ID: {doc.client_id}) ---")

                filename = Path(doc.file_path).name if doc.file_path else doc.name
                logger.info(f"[{idx}/{total}] Doc {doc.id}: {filename} ({doc.doc_type})")

                if dry_run:
                    self.stats['dry_run'] += 1
                    continue

                # Check file exists
                if not doc.file_path or not os.path.exists(doc.file_path):
                    logger.warning(f"  File not found: {doc.file_path}")
                    self.stats['file_missing'] += 1
                    continue

                # Check content_hash dedup (another doc already synced with same hash)
                if doc.content_hash:
                    existing = self.db.query(Document).filter(
                        Document.content_hash == doc.content_hash,
                        Document.drive_file_id != None,
                        Document.id != doc.id
                    ).first()
                    if existing:
                        doc.drive_file_id = existing.drive_file_id
                        doc.drive_link = existing.drive_link
                        doc.drive_sync_status = 'synced'
                        doc.drive_synced_at = datetime.now()
                        doc.duplicate_of = existing.id
                        self.db.commit()
                        logger.info(f"  Linked to existing (hash dedup, dup of doc {existing.id})")
                        self.stats['hash_dedup'] += 1
                        continue

                # Upload to Drive
                result = sync_to_google_drive(self.db, doc.id)

                if result.get('success'):
                    action = result.get('action', 'synced')
                    self.stats['uploaded'] += 1
                    logger.info(f"  Synced: {result.get('web_link', 'OK')}")
                else:
                    self.stats['failed'] += 1
                    error = result.get('error', 'Unknown error')
                    logger.error(f"  Failed: {error}")

                # Progress update every 50 docs
                if idx % 50 == 0:
                    elapsed = (datetime.now() - self.start_time).total_seconds()
                    rate = idx / elapsed if elapsed > 0 else 0
                    eta = (total - idx) / rate if rate > 0 else 0
                    logger.info(
                        f"Progress: {idx}/{total} ({idx/total*100:.1f}%) | "
                        f"Rate: {rate:.1f} docs/s | ETA: {eta/60:.1f} min"
                    )

            except Exception as e:
                logger.exception(f"Error syncing doc {doc.id}: {e}")
                self.stats['errors'] += 1
                self.db.rollback()

        logger.info("Sync phase complete")

    def print_statistics(self):
        """Print final statistics."""
        elapsed = (datetime.now() - self.start_time).total_seconds()

        logger.info("=" * 80)
        logger.info("FINAL STATISTICS")
        logger.info("=" * 80)
        for key, count in sorted(self.stats.items(), key=lambda x: -x[1]):
            logger.info(f"  {key}: {count}")
        logger.info(f"Total time: {elapsed/60:.1f} minutes")
        logger.info("=" * 80)

        # Query current sync status
        sync_stats = self.db.query(
            Document.drive_sync_status,
            func.count(Document.id)
        ).group_by(Document.drive_sync_status).all()
        logger.info("Current drive_sync_status distribution:")
        for status, count in sync_stats:
            logger.info(f"  {status or 'NULL'}: {count}")


def main():
    parser = argparse.ArgumentParser(
        description="Bulk sync CaseHub documents to Google Drive"
    )
    parser.add_argument(
        "--inventory", action="store_true",
        help="Phase B1: Inventory existing Drive files only"
    )
    parser.add_argument(
        "--sync", action="store_true",
        help="Phase B3: Sync documents to Drive"
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Run full pipeline: inventory → link → sync"
    )
    parser.add_argument("--limit", type=int, help="Limit documents to sync")
    parser.add_argument("--client-id", type=int, help="Sync specific client only")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be synced")

    args = parser.parse_args()

    if not (args.inventory or args.sync or args.all):
        parser.print_help()
        sys.exit(1)

    db = next(get_db())
    syncer = BulkDriveSync(db)

    try:
        if args.inventory or args.all:
            syncer.inventory_drive_files()
            syncer.link_existing_drive_files()

        if args.sync or args.all:
            if not syncer.drive_inventory and not args.sync:
                logger.warning("No inventory loaded. Run with --inventory first or --all")
            syncer.sync_documents(
                limit=args.limit,
                client_id=args.client_id,
                dry_run=args.dry_run
            )

        syncer.print_statistics()

    except KeyboardInterrupt:
        logger.warning("\nInterrupted by user")
        syncer.print_statistics()
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        syncer.print_statistics()
        sys.exit(1)

    logger.info("Bulk sync complete!")


if __name__ == "__main__":
    main()
