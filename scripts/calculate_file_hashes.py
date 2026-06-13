#!/usr/bin/env python3
"""
Calculate SHA256 hashes for all existing documents in CaseHub.
Used for deduplication before Google Drive sync.
"""
import sys
import hashlib
from pathlib import Path

# Add casehub to path
sys.path.insert(0, '/var/www/immigrant.law/casehub')

from models import SessionLocal
from sqlalchemy import text

def calculate_sha256(file_path):
    """Calculate SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        print(f"Error hashing {file_path}: {e}")
        return None

def main():
    db = SessionLocal()

    # Get all documents
    result = db.execute(text("""
        SELECT id, file_path, name, local_path, client_id
        FROM documents
        WHERE file_hash IS NULL AND file_path IS NOT NULL
        ORDER BY id
    """))

    documents = result.fetchall()
    total = len(documents)

    print(f"Found {total} documents without hashes")
    print("=" * 60)

    hashed = 0
    skipped = 0
    errors = 0

    base_paths = [
        Path('/var/www/immigrant.law/documents/clients/'),
        Path('/var/www/immigrant.law/casehub/uploads/'),
        Path('/var/www/immigrant.law/casehub/data/uploads/'),
        Path('/var/www/immigrant.law/client-intake/uploads/'),
    ]

    for i, doc in enumerate(documents, 1):
        doc_id = doc.id
        file_path_rel = doc.file_path or doc.local_path
        filename = doc.name
        client_id = doc.client_id

        print(f"[{i}/{total}] Processing: {filename}...", end=' ')

        # Try different base paths
        file_found = False
        for base_path in base_paths:
            file_path = base_path / file_path_rel

            if file_path.exists():
                file_found = True

                # Calculate hash
                file_hash = calculate_sha256(file_path)

                if file_hash:
                    # Check if this hash already exists for this client
                    check = db.execute(text("""
                        SELECT id FROM documents
                        WHERE file_hash = :hash AND client_id = :client_id AND id != :doc_id
                        LIMIT 1
                    """), {"hash": file_hash, "client_id": client_id, "doc_id": doc_id})

                    existing = check.fetchone()

                    if existing:
                        # Skip - duplicate already exists for this client
                        print(f"⚠ Duplicate! (already exists: doc #{existing.id})")
                        skipped += 1
                    else:
                        # Update database
                        try:
                            db.execute(text("""
                                UPDATE documents
                                SET file_hash = :hash
                                WHERE id = :id
                            """), {"hash": file_hash, "id": doc_id})

                            db.commit()  # Commit immediately after each update
                            print(f"✓ {file_hash[:8]}...")
                            hashed += 1
                        except Exception as e:
                            print(f"✗ DB error: {e}")
                            errors += 1
                            db.rollback()
                else:
                    print(f"✗ Hash failed")
                    errors += 1

                break

        if not file_found:
            print(f"⊘ File not found")
            skipped += 1

        # Progress report every 100 files
        if i % 100 == 0:
            print(f"  → Progress: {i}/{total} ({hashed} hashed, {skipped} skipped, {errors} errors)")

    db.close()

    print("=" * 60)
    print(f"✅ Complete!")
    print(f"   Hashed: {hashed}")
    print(f"   Skipped (duplicates + not found): {skipped}")
    print(f"   Errors: {errors}")
    print(f"   Total: {total}")

    # Find duplicates
    print("\nChecking for duplicates...")
    db = SessionLocal()
    result = db.execute(text("""
        SELECT file_hash, COUNT(*) as count,
               STRING_AGG(name, ', ') as files
        FROM documents
        WHERE file_hash IS NOT NULL
        GROUP BY file_hash
        HAVING COUNT(*) > 1
        LIMIT 10
    """))

    duplicates = result.fetchall()
    if duplicates:
        print(f"\nFound {len(duplicates)} duplicate file hashes:")
        for dup in duplicates:
            print(f"  Hash {dup.file_hash[:8]}... ({dup.count} files): {dup.files[:100]}...")
    else:
        print("  No duplicates found!")

    db.close()

if __name__ == "__main__":
    main()
