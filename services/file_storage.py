"""
CaseHub - File Storage Service
Centralized file storage management - single source of truth for file paths.

Created: 2026-02-27
Purpose: Replace 5 scattered upload directories with unified storage system
"""
import os

from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import hashlib
import re
import shutil
import mimetypes
import logging
from config import settings

logger = logging.getLogger(__name__)


class FileStorageService:
    """
    Centralized file storage management.

    Replaces scattered upload directories with unified storage.
    Configure BASE_PATH via STORAGE_PATH env var.
    """

    BASE_PATH = Path(os.getenv("STORAGE_PATH", "/var/www/casehub/storage"))
    URL_PREFIX = f"{settings.PREFIX}/files"

    CATEGORIES = {
        "client_documents": "clients",
        "email_attachments": "emails",
        "portal_uploads": "portal",
        "signatures": "signatures",
        "temp": "temp"
    }

    def __init__(self):
        self.base_path = self.BASE_PATH
        self.base_path.mkdir(parents=True, exist_ok=True)

    def generate_slug(self, filename: str, client_name: Optional[str] = None) -> str:
        """
        Generate URL-friendly slug from filename.

        Args:
            filename: Original filename (e.g., "My Document.pdf")
            client_name: Optional client name to prefix (e.g., "John Doe")

        Returns:
            Slug like "john-doe-my-document-20260227" or "my-document-20260227"

        Examples:
            >>> service.generate_slug("Passport.pdf", "João Silva")
            "joao-silva-passport-20260227"

            >>> service.generate_slug("I-94 Form (Copy).pdf")
            "i-94-form-copy-20260227"
        """
        # Remove extension
        name = Path(filename).stem

        # Add client prefix if provided
        if client_name:
            # Normalize client name: remove accents, special chars
            import unicodedata
            client_normalized = unicodedata.normalize('NFKD', client_name)
            client_normalized = client_normalized.encode('ascii', 'ignore').decode('ascii')
            name = f"{client_normalized}-{name}"

        # Normalize: lowercase, replace spaces/special chars with hyphens
        slug = re.sub(r'[^a-z0-9]+', '-', name.lower())
        slug = re.sub(r'-+', '-', slug).strip('-')

        # Add timestamp to ensure uniqueness
        timestamp = datetime.now().strftime("%Y%m%d")
        slug = f"{slug}-{timestamp}"

        # Limit length (slugs shouldn't be too long for URLs)
        if len(slug) > 200:
            slug = slug[:200]

        return slug

    def calculate_hash(self, file_path: Path) -> str:
        """
        Calculate SHA256 hash of file content.

        Args:
            file_path: Path to file

        Returns:
            64-character SHA256 hash (hex)

        Example:
            >>> service.calculate_hash(Path("/tmp/document.pdf"))
            "a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c3d5e7f9a1b3c5d7e9f1a3b5"
        """
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256.update(chunk)
        return sha256.hexdigest()

    def store_file(
        self,
        source_path: Path,
        category: str,
        client_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Store a file and return storage metadata.

        Args:
            source_path: Path to source file (will be copied or moved)
            category: File category (client_documents, email_attachments, portal_uploads, signatures, temp)
            client_id: Optional client ID for organizing files
            metadata: Optional metadata dict with:
                - client_name: Client name for slug generation
                - preserve_name: If True, use original filename without slug

        Returns:
            Dictionary with:
                - storage_path: Absolute path where file is stored
                - public_slug: URL-friendly slug for the file
                - content_hash: SHA256 hash of file content
                - storage_backend: "local" (for now)
                - url: Public URL for accessing file
                - file_size: File size in bytes
                - mime_type: MIME type detected from extension

        Example:
            >>> result = service.store_file(
            ...     source_path=Path("/tmp/upload_abc123.pdf"),
            ...     category="client_documents",
            ...     client_id=42,
            ...     metadata={"client_name": "John Doe"}
            ... )
            >>> result['storage_path']
            '/var/www/casehub/storage/clients/client_42/john-doe-passport-20260227.pdf'
        """
        metadata = metadata or {}

        # Validate category
        if category not in self.CATEGORIES:
            logger.warning(f"Unknown category '{category}', using 'client_documents'")
            category = "client_documents"

        # Build destination folder path
        category_folder = self.CATEGORIES[category]
        dest_folder = self.base_path / category_folder

        if client_id:
            dest_folder = dest_folder / f"client_{client_id}"

        dest_folder.mkdir(parents=True, exist_ok=True)

        # Generate filename
        ext = source_path.suffix

        if metadata.get("preserve_name"):
            # Use original filename without modification
            filename = source_path.name
        else:
            # Generate slug
            slug = self.generate_slug(
                source_path.name,
                metadata.get("client_name")
            )
            filename = f"{slug}{ext}"

        dest_path = dest_folder / filename

        # Handle filename collision (rare, but possible if same client uploads same file twice in one day)
        if dest_path.exists():
            counter = 1
            while dest_path.exists():
                if metadata.get("preserve_name"):
                    stem = dest_path.stem
                    filename = f"{stem}_{counter}{ext}"
                else:
                    filename = f"{slug}_{counter}{ext}"
                dest_path = dest_folder / filename
                counter += 1
                if counter > 100:  # Safety limit
                    raise RuntimeError(f"Too many filename collisions for {filename}")

        # Calculate hash BEFORE moving (in case source is deleted)
        content_hash = self.calculate_hash(source_path)

        # Copy or move file
        if category == "temp":
            # Move temp files (no need to keep source)
            shutil.move(str(source_path), str(dest_path))
        else:
            # Copy other files (preserve source)
            shutil.copy2(str(source_path), str(dest_path))

        # Set permissions (readable by web server)
        dest_path.chmod(0o644)

        # Generate public URL
        relative_path = dest_path.relative_to(self.base_path)
        url = f"{self.URL_PREFIX}/{relative_path}"

        # Detect MIME type
        mime_type, _ = mimetypes.guess_type(str(dest_path))

        logger.info(
            f"Stored file: {filename} (category={category}, client_id={client_id}, "
            f"hash={content_hash[:16]}..., size={dest_path.stat().st_size})"
        )

        return {
            "storage_path": str(dest_path),
            "public_slug": slug if not metadata.get("preserve_name") else dest_path.stem,
            "content_hash": content_hash,
            "storage_backend": "local",
            "url": url,
            "file_size": dest_path.stat().st_size,
            "mime_type": mime_type or "application/octet-stream"
        }

    def find_duplicate(self, content_hash: str, db_session) -> Optional[int]:
        """
        Find existing document with same content hash.

        Args:
            content_hash: SHA256 hash to search for
            db_session: SQLAlchemy database session

        Returns:
            Document ID if duplicate found, None otherwise

        Example:
            >>> dup_id = service.find_duplicate("a3b5c7d9...", db_session)
            >>> if dup_id:
            ...     print(f"Duplicate of document {dup_id}")
        """
        from models.document import Document

        dup = db_session.query(Document).filter(
            Document.content_hash == content_hash,
            Document.duplicate_of == None  # Only find original documents
        ).first()

        return dup.id if dup else None

    def get_file_path(self, public_slug: str, client_id: Optional[int] = None) -> Optional[Path]:
        """
        Resolve public slug to actual file path.

        Args:
            public_slug: URL slug (e.g., "john-doe-passport-20260227")
            client_id: Optional client ID to narrow search

        Returns:
            Path to file if found, None otherwise
        """
        # Search in client_documents first
        if client_id:
            search_dir = self.base_path / "clients" / f"client_{client_id}"
        else:
            search_dir = self.base_path / "clients"

        if not search_dir.exists():
            return None

        # Search for files matching slug
        for file_path in search_dir.rglob(f"{public_slug}.*"):
            if file_path.is_file():
                return file_path

        return None

    def delete_file(self, storage_path: str) -> bool:
        """
        Delete a file from storage.

        Args:
            storage_path: Absolute path to file

        Returns:
            True if deleted, False if file didn't exist
        """
        file_path = Path(storage_path)

        if not file_path.exists():
            logger.warning(f"Cannot delete non-existent file: {storage_path}")
            return False

        # Security check: ensure path is within our storage directory
        if not str(file_path.resolve()).startswith(str(self.base_path.resolve())):
            logger.error(f"Security violation: attempted to delete file outside storage: {storage_path}")
            raise ValueError("Cannot delete file outside storage directory")

        file_path.unlink()
        logger.info(f"Deleted file: {storage_path}")
        return True

    def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics.

        Returns:
            Dictionary with:
                - total_files: Total number of files
                - total_size_bytes: Total storage used
                - categories: Dict of file counts per category
        """
        stats = {
            "total_files": 0,
            "total_size_bytes": 0,
            "categories": {}
        }

        for category, folder_name in self.CATEGORIES.items():
            category_path = self.base_path / folder_name
            if not category_path.exists():
                stats["categories"][category] = {"files": 0, "size_bytes": 0}
                continue

            files = list(category_path.rglob("*"))
            files = [f for f in files if f.is_file()]

            category_size = sum(f.stat().st_size for f in files)

            stats["categories"][category] = {
                "files": len(files),
                "size_bytes": category_size
            }

            stats["total_files"] += len(files)
            stats["total_size_bytes"] += category_size

        return stats
