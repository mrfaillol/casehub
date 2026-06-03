#!/usr/bin/env python3
"""
Document Sync Service - CaseHub
Handles syncing approved documents to Google Drive.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy import or_
from sqlalchemy.orm import Session
from models.tenant import tenant_query

logger = logging.getLogger(__name__)

# Import Google Drive handler
try:
    from services.google_drive_handler import GoogleDriveHandler
    GOOGLE_DRIVE_AVAILABLE = True
except ImportError:
    logger.warning("Google Drive handler not available")
    GOOGLE_DRIVE_AVAILABLE = False


def _document_query(db: Session, model, org_id: int = None):
    """Use tenant scoping when org_id is known; background jobs may run globally."""
    if org_id is None:
        return db.query(model)
    return tenant_query(db, model, org_id)


def _as_org_id(value):
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _document_org_id(db: Session, doc, org_id: int = None):
    """Resolve tenant scope before duplicate, client, or case Drive lookups."""
    explicit_org_id = _as_org_id(org_id)
    if explicit_org_id is not None:
        return explicit_org_id

    doc_org_id = _as_org_id(getattr(doc, "org_id", None))
    if doc_org_id is not None:
        return doc_org_id

    try:
        from models import Client, Case

        related_sources = (
            (Client, getattr(doc, "client_id", None), "client"),
            (Case, getattr(doc, "case_id", None), "case"),
        )
        for model, related_id, label in related_sources:
            related_id = _as_org_id(related_id)
            if related_id is None:
                continue
            related = db.query(model).filter(model.id == related_id).first()
            related_org_id = _as_org_id(getattr(related, "org_id", None)) if related else None
            if related_org_id is not None:
                try:
                    doc.org_id = related_org_id
                except Exception:
                    pass
                logger.info(
                    "Resolved org_id %s for document %s from %s %s",
                    related_org_id,
                    getattr(doc, "id", "unknown"),
                    label,
                    related_id,
                )
                return related_org_id
    except Exception:
        logger.exception(
            "Unable to resolve org_id for document %s before Drive sync",
            getattr(doc, "id", "unknown"),
        )

    return None


def sync_to_google_drive(db: Session, document_id: int, org_id: int = None) -> Dict[str, Any]:
    """
    Sync an approved document to Google Drive.

    Args:
        db: Database session
        document_id: ID of the document to sync

    Returns:
        Dict with sync result:
        {
            "success": bool,
            "file_id": str (Google Drive file ID),
            "web_link": str (shareable link),
            "error": str (if failed)
        }
    """
    result = {
        "success": False,
        "file_id": None,
        "web_link": None,
        "error": None,
        "drive_sync_status": "failed"
    }

    if not GOOGLE_DRIVE_AVAILABLE:
        result["error"] = "Google Drive integration not configured"
        logger.error("Google Drive handler not available")
        return result

    try:
        # Import models
        from models import Document, Client, Case

        # Get document
        doc = _document_query(db, Document, org_id).filter(Document.id == document_id).first()
        if not doc:
            result["error"] = f"Document {document_id} not found"
            return result

        org_id = _document_org_id(db, doc, org_id)
        if org_id is None:
            result["error"] = "Document tenant scope could not be resolved"
            logger.error(
                "Refusing Drive sync for document %s without tenant scope",
                document_id,
            )
            return result

        # Check if already synced
        if getattr(doc, "drive_file_id", None):
            logger.info(f"Document {document_id} already synced to Drive: {doc.drive_file_id}")
            result["success"] = True
            result["file_id"] = doc.drive_file_id
            result["web_link"] = doc.drive_link
            result["drive_sync_status"] = "synced"
            return result

        # CRITICAL: Check for duplicates by content hash
        # This prevents uploading the same file multiple times to Drive
        if getattr(doc, "content_hash", None):
            existing = _document_query(db, Document, org_id).filter(
                Document.content_hash == doc.content_hash,
                Document.drive_file_id != None,
                Document.id != doc.id
            ).first()

            if existing:
                # Link to existing Drive file instead of uploading
                logger.info(
                    f"Document {document_id} is duplicate of {existing.id} "
                    f"(hash: {doc.content_hash[:16]}...). Linking to existing Drive file."
                )
                doc.drive_file_id = existing.drive_file_id
                doc.drive_link = existing.drive_link
                doc.drive_sync_status = "synced"
                doc.drive_synced_at = datetime.now()
                doc.duplicate_of = existing.id
                db.commit()

                result["success"] = True
                result["file_id"] = existing.drive_file_id
                result["web_link"] = existing.drive_link
                result["drive_sync_status"] = "synced"
                result["action"] = "linked_to_existing"
                result["duplicate_of"] = existing.id
                return result

        # Get client info
        if not doc.client_id:
            result["error"] = "Document has no associated client"
            return result

        client = _document_query(db, Client, org_id).filter(Client.id == doc.client_id).first()
        if not client:
            result["error"] = f"Client {doc.client_id} not found"
            return result

        # Build client name (LAST, First format for Active Clients matching)
        client_name = f"{client.last_name.upper()}, {client.first_name}".strip()
        if not client_name or client_name == ",":
            client_name = f"Client-{client.id}"

        # Get visa category from case
        visa_category = "General"
        if doc.case_id:
            case = _document_query(db, Case, org_id).filter(Case.id == doc.case_id).first()
            if case and case.visa_type:
                visa_category = case.visa_type

        # Check file exists
        file_path = Path(doc.file_path or doc.local_path)
        if not file_path.exists():
            result["error"] = f"File not found: {file_path}"
            # Mark as failed with error
            doc.drive_sync_status = "failed"
            doc.drive_sync_error = result["error"]
            db.commit()
            return result

        # Initialize Google Drive handler scoped to the resolved tenant.
        handler = GoogleDriveHandler(db, org_id=org_id)

        # Upload document - use saved drive_folder_id if available
        if getattr(client, "drive_folder_id", None):
            upload_result = handler.upload_to_folder(
                file_path=str(file_path),
                folder_id=client.drive_folder_id,
                document_title=doc.name,
                mime_type=doc.mime_type
            )
        else:
            upload_result = handler.upload_document(
                file_path=str(file_path),
                client_name=client_name,
                document_title=doc.name,
                visa_category=visa_category,
                document_type=doc.doc_type or "Other Document",  # Updated to English (was "Outro")
                mime_type=doc.mime_type
            )

        # Update result
        result["success"] = upload_result.get("success", False)
        result["file_id"] = upload_result.get("file_id")
        result["web_link"] = upload_result.get("web_link")
        result["error"] = upload_result.get("error")

        # Update document in database
        if result["success"]:
            doc.drive_file_id = result["file_id"]
            doc.drive_link = result["web_link"]
            doc.drive_sync_status = "synced"
            doc.drive_synced_at = datetime.now()
            doc.drive_sync_error = None
            doc.drive_retry_count = 0
            result["drive_sync_status"] = "synced"
            logger.info(f"Document {document_id} synced successfully: {result['file_id']}")
        else:
            doc.drive_sync_status = "failed"
            doc.drive_sync_error = result["error"]
            doc.drive_retry_count = (doc.drive_retry_count or 0) + 1
            logger.error(f"Failed to sync document {document_id}: {result['error']}")

        db.commit()

    except Exception as e:
        result["error"] = f"Sync error: {str(e)}"
        logger.exception(f"Error syncing document {document_id} to Drive")

        # Try to mark as failed in DB
        try:
            from models import Document
            doc = _document_query(db, Document, org_id).filter(Document.id == document_id).first()
            if doc:
                doc.drive_sync_status = "failed"
                doc.drive_sync_error = str(e)
                doc.drive_retry_count = (doc.drive_retry_count or 0) + 1
                db.commit()
        except:
            pass

    return result


def retry_failed_syncs(db: Session, max_retries: int = 3, org_id: int = None) -> Dict[str, Any]:
    """
    Retry all documents with failed Drive sync that haven't exceeded max retries.

    Args:
        db: Database session
        max_retries: Maximum retry attempts

    Returns:
        Dict with retry statistics
    """
    result = {
        "total_attempted": 0,
        "successful": 0,
        "failed": 0,
        "skipped": 0
    }

    try:
        from models import Document

        # Get failed documents under retry limit (any status with a valid file)
        failed_docs = _document_query(db, Document, org_id).filter(
            Document.drive_sync_status == "failed",
            or_(
                Document.drive_retry_count == None,
                Document.drive_retry_count < max_retries,
            ),
            Document.status.notin_(["REJECTED", "archived"])
        ).all()

        for doc in failed_docs:
            result["total_attempted"] += 1

            sync_result = sync_to_google_drive(db, doc.id, org_id=org_id)

            if sync_result["success"]:
                result["successful"] += 1
            else:
                result["failed"] += 1

        logger.info(f"Retry completed: {result}")

    except Exception as e:
        logger.exception("Error in retry_failed_syncs")
        result["error"] = str(e)

    return result