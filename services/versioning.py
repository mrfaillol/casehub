"""
CaseHub - Document Versioning Service
Track and manage document versions
"""
import os
import shutil
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import text


class DocumentVersioningService:
    """Service for managing document versions."""

    def __init__(self, db: Session):
        self.db = db
        from config import settings
        self.upload_dir = settings.upload_path
        self.versions_dir = os.path.join(self.upload_dir, "versions")
        os.makedirs(self.versions_dir, exist_ok=True)

    def _calculate_checksum(self, file_path: str) -> str:
        """Calculate MD5 checksum of a file."""
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except:
            return ""

    def create_version(self, document_id: int, file_path: str, user_id: int, notes: str = None) -> Dict[str, Any]:
        """
        Create a new version of a document.
        
        Args:
            document_id: ID of the document
            file_path: Path to the new file
            user_id: ID of the user uploading
            notes: Optional notes about this version
        
        Returns:
            Dict with version info
        """
        from models import Document
        
        document = self.db.query(Document).filter(Document.id == document_id).first()
        if not document:
            return {"success": False, "error": "Document not found"}

        # Get current version number
        current_max = self.db.execute(text("""
            SELECT COALESCE(MAX(version_number), 0) FROM document_versions
            WHERE document_id = :doc_id
        """), {"doc_id": document_id}).scalar()
        
        new_version = current_max + 1

        # If this is the first version, archive the current file
        if new_version == 1 and document.file_path:
            current_file = os.path.join(self.upload_dir, document.file_path) if not document.file_path.startswith('/') else document.file_path
            if os.path.exists(current_file):
                # Create version 1 from current file
                self._archive_version(document_id, 1, current_file, user_id, "Initial version")
                new_version = 2

        # Archive the new file
        checksum = self._calculate_checksum(file_path)
        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        
        # Copy to versions directory
        ext = os.path.splitext(file_path)[1]
        version_filename = f"doc_{document_id}_v{new_version}{ext}"
        version_path = os.path.join(self.versions_dir, version_filename)
        
        try:
            shutil.copy2(file_path, version_path)
        except Exception as e:
            return {"success": False, "error": f"Failed to copy file: {str(e)}"}

        # Create version record
        self.db.execute(text("""
            INSERT INTO document_versions 
            (document_id, version_number, file_path, file_size, checksum, uploaded_by, notes, created_at)
            VALUES (:doc_id, :version, :path, :size, :checksum, :user_id, :notes, NOW())
        """), {
            "doc_id": document_id,
            "version": new_version,
            "path": version_path,
            "size": file_size,
            "checksum": checksum,
            "user_id": user_id,
            "notes": notes
        })

        # Update document
        document.current_version = new_version
        document.total_versions = new_version
        document.file_path = file_path  # Update to new file
        document.updated_at = datetime.now()
        
        self.db.commit()

        return {
            "success": True,
            "version_number": new_version,
            "file_path": version_path,
            "checksum": checksum
        }

    def _archive_version(self, document_id: int, version: int, file_path: str, user_id: int, notes: str = None):
        """Archive an existing file as a version."""
        if not os.path.exists(file_path):
            return
        
        checksum = self._calculate_checksum(file_path)
        file_size = os.path.getsize(file_path)
        
        # Copy to versions directory
        ext = os.path.splitext(file_path)[1]
        version_filename = f"doc_{document_id}_v{version}{ext}"
        version_path = os.path.join(self.versions_dir, version_filename)
        
        shutil.copy2(file_path, version_path)
        
        self.db.execute(text("""
            INSERT INTO document_versions 
            (document_id, version_number, file_path, file_size, checksum, uploaded_by, notes, created_at)
            VALUES (:doc_id, :version, :path, :size, :checksum, :user_id, :notes, NOW())
        """), {
            "doc_id": document_id,
            "version": version,
            "path": version_path,
            "size": file_size,
            "checksum": checksum,
            "user_id": user_id,
            "notes": notes
        })

    def get_versions(self, document_id: int) -> List[Dict]:
        """Get all versions of a document."""
        versions = self.db.execute(text("""
            SELECT dv.*, u.name as uploader_name
            FROM document_versions dv
            LEFT JOIN users u ON dv.uploaded_by = u.id
            WHERE dv.document_id = :doc_id
            ORDER BY dv.version_number DESC
        """), {"doc_id": document_id}).fetchall()

        return [{
            "id": v.id,
            "version_number": v.version_number,
            "file_path": v.file_path,
            "file_size": v.file_size,
            "checksum": v.checksum,
            "uploaded_by": v.uploader_name,
            "notes": v.notes,
            "created_at": v.created_at.isoformat() if v.created_at else None
        } for v in versions]

    def get_version(self, document_id: int, version_number: int) -> Optional[Dict]:
        """Get a specific version of a document."""
        version = self.db.execute(text("""
            SELECT dv.*, u.name as uploader_name
            FROM document_versions dv
            LEFT JOIN users u ON dv.uploaded_by = u.id
            WHERE dv.document_id = :doc_id AND dv.version_number = :version
        """), {"doc_id": document_id, "version": version_number}).fetchone()

        if not version:
            return None

        return {
            "id": version.id,
            "version_number": version.version_number,
            "file_path": version.file_path,
            "file_size": version.file_size,
            "checksum": version.checksum,
            "uploaded_by": version.uploader_name,
            "notes": version.notes,
            "created_at": version.created_at.isoformat() if version.created_at else None
        }

    def restore_version(self, document_id: int, version_number: int, user_id: int) -> Dict[str, Any]:
        """Restore a document to a previous version."""
        from models import Document
        
        document = self.db.query(Document).filter(Document.id == document_id).first()
        if not document:
            return {"success": False, "error": "Document not found"}

        version = self.get_version(document_id, version_number)
        if not version:
            return {"success": False, "error": "Version not found"}

        if not os.path.exists(version["file_path"]):
            return {"success": False, "error": "Version file not found"}

        # Create a new version from the old version (restoration)
        result = self.create_version(
            document_id,
            version["file_path"],
            user_id,
            f"Restored from version {version_number}"
        )

        if result.get("success"):
            result["restored_from"] = version_number

        return result

    def compare_versions(self, document_id: int, version1: int, version2: int) -> Dict[str, Any]:
        """Compare two versions of a document."""
        v1 = self.get_version(document_id, version1)
        v2 = self.get_version(document_id, version2)

        if not v1 or not v2:
            return {"error": "One or both versions not found"}

        return {
            "version1": v1,
            "version2": v2,
            "same_content": v1["checksum"] == v2["checksum"],
            "size_diff": (v2["file_size"] or 0) - (v1["file_size"] or 0)
        }

    def get_version_stats(self) -> Dict[str, Any]:
        """Get versioning statistics."""
        stats = {}
        
        stats["total_versions"] = self.db.execute(text(
            "SELECT COUNT(*) FROM document_versions"
        )).scalar() or 0
        
        stats["documents_with_versions"] = self.db.execute(text(
            "SELECT COUNT(DISTINCT document_id) FROM document_versions"
        )).scalar() or 0
        
        stats["storage_used"] = self.db.execute(text(
            "SELECT COALESCE(SUM(file_size), 0) FROM document_versions"
        )).scalar() or 0
        
        return stats
