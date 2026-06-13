#!/usr/bin/env python3
"""
Sync documents FROM Google Drive TO VPS for all clients.
Skips existing files (deduplication by file size).
"""
import sys
import argparse
from datetime import datetime

sys.path.insert(0, '/var/www/immigrant.law/casehub')

from services.google_drive_handler import GoogleDriveHandler
from models import SessionLocal, Client
from sqlalchemy import text

def main():
    parser = argparse.ArgumentParser(description='Sync client documents from Google Drive')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be synced without downloading')
    parser.add_argument('--client-id', type=int, help='Sync specific client only')
    parser.add_argument('--max-clients', type=int, help='Limit number of clients to sync')
    args = parser.parse_args()

    db = SessionLocal()
    handler = GoogleDriveHandler()

    if not handler.service:
        print("❌ Google Drive not connected")
        return 1

    # Get clients to sync
    query = db.query(Client)

    if args.client_id:
        query = query.filter(Client.id == args.client_id)
    else:
        query = query.filter(Client.status != 'archived')

    clients = query.all()

    if args.max_clients:
        clients = clients[:args.max_clients]

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Syncing {len(clients)} clients")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    total_downloaded = 0
    total_skipped = 0
    total_failed = 0
    synced_clients = 0
    errors_clients = []

    for i, client in enumerate(clients, 1):
        # Try multiple folder name formats
        visa_type = None
        if hasattr(client, 'cases') and client.cases:
            for case in client.cases:
                if case.status == 'active' and hasattr(case, 'visa_category'):
                    visa_type = case.visa_category
                    break

        possible_names = [
            f"{client.last_name.upper()}, {client.first_name} - {visa_type}" if visa_type else None,
            f"{client.last_name.upper()}, {client.first_name}",
            f"{client.first_name} {client.last_name}",
        ]

        print(f"\n[{i}/{len(clients)}] {client.first_name} {client.last_name} (ID: {client.id})")

        # Find which folder name works
        client_name = None
        for name in possible_names:
            if name and handler.get_client_folder(name):
                client_name = name
                print(f"  Found: {client_name}")
                break

        if not client_name:
            print(f"  ⊘ Folder not found in Drive (tried {len([n for n in possible_names if n])} variations)")
            total_failed += 1
            errors_clients.append((f"{client.first_name} {client.last_name}", "Folder not found"))
            continue

        if args.dry_run:
            # Just check if folder exists
            files = handler.list_client_files(client_name, max_results=10)
            print(f"  ✓ Would sync {len(files)}+ files")
            continue

        try:
            result = handler.download_client_folder(
                client_name,
                "/var/www/immigrant.law/documents/clients/",
                skip_existing=True
            )

            downloaded = result.get('downloaded', 0)
            skipped = result.get('skipped', 0)
            failed = result.get('failed', 0)
            total = result.get('total', 0)

            print(f"  Downloaded: {downloaded}, Skipped: {skipped}, Failed: {failed}, Total: {total}")

            total_downloaded += downloaded
            total_skipped += skipped
            total_failed += failed

            if downloaded > 0:
                synced_clients += 1

        except Exception as e:
            print(f"  ❌ Error: {e}")
            errors_clients.append((client_name, str(e)))
            total_failed += 1

    print("\n" + "=" * 80)
    print(f"✅ Sync complete!")
    print(f"   Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Clients synced: {synced_clients}/{len(clients)}")
    print(f"   Total downloaded: {total_downloaded} files")
    print(f"   Total skipped: {total_skipped} files")
    print(f"   Total failed: {total_failed} files")

    if errors_clients:
        print(f"\n⚠️  Errors occurred for {len(errors_clients)} clients:")
        for client_name, error in errors_clients[:10]:
            print(f"   - {client_name}: {error[:80]}")

    db.close()
    return 0 if total_failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
