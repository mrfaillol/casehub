"""
CaseHub - Document API Routes
REST API endpoints for document management with Drive sync and approval workflow.
"""
from core.form_utils import form_int, form_float
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
import logging
import os
import uuid
import shutil

logger = logging.getLogger(__name__)

from models import get_db, Client, Case, Document, User
from auth import get_current_user_api, require_auth_api
from models.tenant import tenant_query
from services.document_sync import sync_to_google_drive, retry_failed_syncs
from services.notifications import notify_client_approval, notify_client_rejection
from config import settings

router = APIRouter(prefix="/api/documents", tags=["documents-api"], dependencies=[Depends(require_auth_api)])

UPLOAD_DIR = os.path.join(settings.BASE_DIR, "documents", "clients")
try:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
except PermissionError:
    pass

# Pydantic models for request/response
class DocumentResponse(BaseModel):
    id: int
    name: str
    doc_type: Optional[str]
    status: Optional[str]
    file_size: Optional[int]
    mime_type: Optional[str]
    client_id: Optional[int]
    case_id: Optional[int]
    drive_link: Optional[str]
    visa_category: Optional[str]
    llm_classified: Optional[bool]
    classification_confidence: Optional[float]
    uploaded_via: Optional[str]
    created_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class DocumentUpdate(BaseModel):
    name: Optional[str] = None
    doc_type: Optional[str] = None
    status: Optional[str] = None
    visa_category: Optional[str] = None
    notes: Optional[str] = None

class ApprovalRequest(BaseModel):
    approved: bool
    rejection_reason: Optional[str] = None


@router.get("", response_model=List[DocumentResponse])
async def list_documents(
    client_id: Optional[int] = None,
    case_id: Optional[int] = None,
    status: Optional[str] = None,
    doc_type: Optional[str] = None,
    visa_category: Optional[str] = None,
    uploaded_via: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """List documents with optional filters."""
    query = tenant_query(db, Document, request.state.org_id)
    
    if client_id:
        query = query.filter(Document.client_id == client_id)
    if case_id:
        query = query.filter(Document.case_id == case_id)
    if status:
        query = query.filter(Document.status == status)
    if doc_type:
        query = query.filter(Document.doc_type == doc_type)
    if visa_category:
        query = query.filter(Document.visa_category == visa_category)
    if uploaded_via:
        query = query.filter(Document.uploaded_via == uploaded_via)
    
    documents = query.order_by(Document.created_at.desc()).offset(offset).limit(limit).all()
    return documents


@router.get("/pending", response_model=List[DocumentResponse])
async def list_pending_documents(
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db)
):
    """List documents pending approval."""
    documents = tenant_query(db, Document, request.state.org_id).filter(
        Document.status == "PENDING_APPROVAL"
    ).order_by(Document.created_at.desc()).limit(limit).all()
    return documents


@router.get("/drive/status")
async def get_sync_status_v2(
    request: Request,
    db: Session = Depends(get_db)):
    """Get Google Drive sync statistics (specific route before /{doc_id})."""
    from sqlalchemy import func, text

    # Total documents
    total_docs = tenant_query(db, Document, request.state.org_id).with_entities(func.count(Document.id)).scalar()

    # Documents with Drive links (synced TO drive)
    synced_to_drive = tenant_query(db, Document, request.state.org_id).with_entities(func.count(Document.id)).filter(
        Document.drive_link.isnot(None)
    ).scalar()

    # Documents with file hashes (deduplicated)
    hashed_locally = tenant_query(db, Document, request.state.org_id).with_entities(func.count(Document.id)).filter(
        Document.file_hash.isnot(None)
    ).scalar()

    # Duplicate hashes
    duplicates_query = text("""
        SELECT COUNT(*) as dup_count
        FROM (
            SELECT file_hash, client_id
            FROM documents
            WHERE file_hash IS NOT NULL AND org_id = :org_id
            GROUP BY file_hash, client_id
            HAVING COUNT(*) > 1
        ) as dups
    """)
    duplicates_count = db.execute(duplicates_query, {"org_id": request.state.org_id}).scalar()

    # Storage by visa category
    storage_by_visa = db.execute(text("""
        SELECT visa_category,
               COUNT(*) as doc_count,
               SUM(file_size) as total_size
        FROM documents
        WHERE visa_category IS NOT NULL AND org_id = :org_id
        GROUP BY visa_category
        ORDER BY total_size DESC
    """), {"org_id": request.state.org_id}).fetchall()

    return {
        "total_documents": total_docs,
        "synced_to_drive": synced_to_drive,
        "hashed_locally": hashed_locally,
        "duplicates_detected": duplicates_count or 0,
        "storage_by_visa": [
            {
                "visa_category": row[0],
                "document_count": row[1],
                "total_size_mb": round((row[2] or 0) / 1024 / 1024, 2)
            }
            for row in storage_by_visa
        ]
    }


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: int, 
    request: Request,
    db: Session = Depends(get_db)):
    """Get document details by ID."""
    doc = tenant_query(db, Document, request.state.org_id).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.put("/{doc_id}")
async def update_document(
    doc_id: int,
    update: DocumentUpdate,
    
    request: Request,
    db: Session = Depends(get_db)
):
    """Update document metadata."""
    doc = tenant_query(db, Document, request.state.org_id).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    update_data = update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(doc, key, value)
    
    doc.updated_at = datetime.now()
    db.commit()
    db.refresh(doc)
    
    return {"success": True, "document_id": doc.id}


@router.post("/{doc_id}/approve")
async def approve_document(
    doc_id: int,
    request: Request,
    user_id: int = Query(..., description="ID of the reviewer"),
    db: Session = Depends(get_db)
):
    """Approve a pending document and sync to Google Drive."""
    doc = tenant_query(db, Document, request.state.org_id).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.status = "APPROVED"
    doc.client_visible = True
    doc.reviewed_by = user_id
    doc.reviewed_at = datetime.now()
    doc.updated_at = datetime.now()

    db.commit()

    # Sync to Google Drive (non-blocking, failures logged but don't block response)
    drive_result = {"success": False, "error": "Not attempted"}
    try:
        drive_result = sync_to_google_drive(db, doc.id, org_id=request.state.org_id)
    except Exception as e:
        drive_result["error"] = str(e)
        # Log but don't fail the approval
        import logging
        logging.error(f"Drive sync failed for document {doc.id}: {e}")

    # Send client notification email (non-blocking)
    email_result = {"success": False, "error": "Not attempted"}
    if doc.uploaded_via == "client_portal":
        try:
            email_result = notify_client_approval(db, doc.id, org_id=request.state.org_id)
        except Exception as e:
            email_result["error"] = str(e)
            import logging
            logging.error(f"Email notification failed for document {doc.id}: {e}")

    return {
        "success": True,
        "status": "APPROVED",
        "document_id": doc.id,
        "drive_sync": drive_result,
        "email_notification": email_result
    }


@router.post("/{doc_id}/reject")
async def reject_document(
    doc_id: int,
    request: Request,
    reason: str = Form(...),
    user_id: int = Query(..., description="ID of the reviewer"),
    db: Session = Depends(get_db)
):
    """Reject a pending document with reason."""
    doc = tenant_query(db, Document, request.state.org_id).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    doc.status = "REJECTED"
    doc.client_visible = False
    doc.reviewed_by = user_id
    doc.reviewed_at = datetime.now()
    doc.rejection_reason = reason
    doc.updated_at = datetime.now()

    db.commit()

    # Send client notification email (non-blocking)
    email_result = {"success": False, "error": "Not attempted"}
    if doc.uploaded_via == "client_portal":
        try:
            email_result = notify_client_rejection(db, doc.id, org_id=request.state.org_id)
        except Exception as e:
            email_result["error"] = str(e)
            import logging
            logging.error(f"Email notification failed for document {doc.id}: {e}")

    return {
        "success": True,
        "status": "REJECTED",
        "document_id": doc.id,
        "reason": reason,
        "email_notification": email_result
    }


@router.post("/batch-approve")
async def batch_approve_documents(
    request: Request,
    document_ids: List[int],
    user_id: int = Query(..., description="ID of the reviewer"),
    db: Session = Depends(get_db)
):
    """Approve multiple documents at once.

    `request: Request` was missing on main while the body referenced
    `request.state.org_id` — every call hit NameError -> HTTP 500. The
    per-id tenant_query inside the loop is also batched into one `.in_()`
    SELECT.
    """
    approved = []
    not_found = []

    # Batch the per-id lookup (N+1 -> 1 SELECT).
    docs_by_id = {
        d.id: d
        for d in tenant_query(db, Document, request.state.org_id)
        .filter(Document.id.in_(document_ids)).all()
    } if document_ids else {}

    for doc_id in document_ids:
        doc = docs_by_id.get(doc_id)
        if doc:
            doc.status = "APPROVED"
            doc.client_visible = True
            doc.reviewed_by = user_id
            doc.reviewed_at = datetime.now()
            approved.append(doc_id)
        else:
            not_found.append(doc_id)

    db.commit()
    
    return {
        "success": True,
        "approved": approved,
        "not_found": not_found,
        "total_approved": len(approved)
    }


@router.post("/upload-local")
async def upload_local_document(
    file: UploadFile = File(...),
    client_id: int = Form(...),
    doc_type: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Upload document to local storage for document-watcher to process.
    Files are saved to /documents/clients/_incoming/ and auto-classified by document-watcher.
    """
    try:
        # Verify client exists
        client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")

        # Create _incoming directory if doesn't exist
        incoming_dir = os.path.join(UPLOAD_DIR, "_incoming")
        os.makedirs(incoming_dir, exist_ok=True)

        # Generate unique filename
        file_ext = os.path.splitext(file.filename)[1]
        unique_filename = f"{client.first_name}_{client.last_name}_{uuid.uuid4().hex[:8]}{file_ext}"
        file_path = os.path.join(incoming_dir, unique_filename)

        # Save file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Create document record (document-watcher will update it later)
        new_doc = Document(
            name=file.filename,
            file_path=file_path,
            client_id=client_id,
            doc_type=doc_type or "Other Document",
            status="PENDING_APPROVAL",
            uploaded_via="staff_upload",
            created_at=datetime.now(),
        org_id=request.state.org_id)
        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)

        return {
            "success": True,
            "document_id": new_doc.id,
            "filename": unique_filename,
            "message": "File uploaded successfully. Document-watcher will process it shortly."
        }

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@router.get("/client/{client_id}", response_model=List[DocumentResponse])
async def get_client_documents(
    client_id: int,
    request: Request,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all documents for a specific client."""
    query = tenant_query(db, Document, request.state.org_id).filter(Document.client_id == client_id)
    
    if status:
        query = query.filter(Document.status == status)
    
    documents = query.order_by(Document.created_at.desc()).all()
    return documents


@router.get("/case/{case_id}", response_model=List[DocumentResponse])
async def get_case_documents(
    case_id: int,
    
    request: Request,
    db: Session = Depends(get_db)
):
    """Get all documents for a specific case."""
    documents = tenant_query(db, Document, request.state.org_id).filter(
        Document.case_id == case_id
    ).order_by(Document.created_at.desc()).all()
    return documents


@router.get("/stats/summary")
async def get_document_stats(
    request: Request,
    db: Session = Depends(get_db)):
    """Get document statistics summary."""
    total = tenant_query(db, Document, request.state.org_id).count()
    pending = tenant_query(db, Document, request.state.org_id).filter(Document.status == "PENDING_APPROVAL").count()
    approved = tenant_query(db, Document, request.state.org_id).filter(Document.status == "APPROVED").count()
    rejected = tenant_query(db, Document, request.state.org_id).filter(Document.status == "REJECTED").count()
    
    # By visa category
    eb1a = tenant_query(db, Document, request.state.org_id).filter(Document.visa_category == "EB1A").count()
    eb2_niw = tenant_query(db, Document, request.state.org_id).filter(Document.visa_category == "EB2-NIW").count()
    
    # With Drive link
    synced = tenant_query(db, Document, request.state.org_id).filter(Document.drive_link.isnot(None)).count()
    
    return {
        "total": total,
        "pending_approval": pending,
        "approved": approved,
        "rejected": rejected,
        "by_visa_category": {
            "EB1A": eb1a,
            "EB2-NIW": eb2_niw
        },
        "synced_to_drive": synced
    }


# ============================================================================
# GOOGLE DRIVE BIDIRECTIONAL SYNC ENDPOINTS
# ============================================================================

class SyncRequest(BaseModel):
    client_id: Optional[int] = None
    skip_existing: bool = True
    max_clients: Optional[int] = None


@router.post("/drive/sync")
async def sync_documents_from_drive(
    http_request: Request,
    request: SyncRequest,
    db: Session = Depends(get_db)
):
    """
    Sync documents FROM Google Drive TO VPS.

    - If client_id provided: sync that client only
    - If no client_id: sync all active clients (bulk operation)
    """
    try:
        from services.google_drive_handler import GoogleDriveHandler
        org_id = http_request.state.org_id
        handler = GoogleDriveHandler(db, org_id=org_id)

        if not handler.service:
            raise HTTPException(status_code=503, detail="Google Drive not connected")

        if request.client_id:
            # Sync specific client - use same logic as /drive/sync-client
            return await sync_client_documents(request.client_id, http_request, request.skip_existing, db)

        else:
            # Bulk sync all clients
            clients = tenant_query(db, Client, org_id).filter(Client.status != 'archived').all()

            if request.max_clients:
                clients = clients[:request.max_clients]

            total_downloaded = 0
            total_skipped = 0
            total_failed = 0
            synced_clients = 0
            client_results = []

            for client in clients:
                # Try multiple folder name formats for each client
                visa_type = None
                if client.cases:
                    for case in client.cases:
                        if case.status == 'active' and hasattr(case, 'visa_category'):
                            visa_type = case.visa_category
                            break

                possible_names = [
                    f"{client.last_name.upper()}, {client.first_name} - {visa_type}" if visa_type else None,
                    f"{client.last_name.upper()}, {client.first_name}",
                    f"{client.first_name} {client.last_name}",
                ]

                folder_found = False
                for name in possible_names:
                    if name and handler.get_client_folder(name):
                        try:
                            result = handler.download_client_folder(
                                name,
                                os.path.join(settings.BASE_DIR, "documents", "clients") + "/",
                                skip_existing=request.skip_existing
                            )

                            downloaded = result.get('downloaded', 0)
                            total_downloaded += downloaded
                            total_skipped += result.get('skipped', 0)
                            total_failed += result.get('failed', 0)

                            if downloaded > 0:
                                synced_clients += 1

                            client_results.append({
                                "client_id": client.id,
                                "client_name": name,
                                "downloaded": downloaded
                            })
                            folder_found = True
                            break

                        except Exception as e:
                            import logging
                            logging.error(f"Error syncing {name}: {e}")
                            total_failed += 1

                if not folder_found:
                    client_results.append({
                        "client_id": client.id,
                        "client_name": f"{client.first_name} {client.last_name}",
                        "error": "Folder not found in Drive"
                    })

            return {
                "success": True,
                "total_clients": len(clients),
                "synced_clients": synced_clients,
                "total_downloaded": total_downloaded,
                "total_skipped": total_skipped,
                "total_failed": total_failed,
                "clients": client_results
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.post("/drive/sync-client/{client_id}")
async def sync_client_documents(
    client_id: int,
    request: Request,
    skip_existing: bool = True,
    db: Session = Depends(get_db)
):
    """Sync documents for a specific client from Google Drive."""
    org_id = request.state.org_id
    client = tenant_query(db, Client, org_id).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    try:
        from services.google_drive_handler import GoogleDriveHandler
        handler = GoogleDriveHandler(db, org_id=org_id)

        if not handler.service:
            raise HTTPException(status_code=503, detail="Google Drive not connected")

        # Try multiple folder name formats
        # Get visa type from first active case if available
        visa_type = None
        if client.cases:
            for case in client.cases:
                if case.status == 'active' and hasattr(case, 'visa_category'):
                    visa_type = case.visa_category
                    break

        # Try different folder name variations
        possible_names = [
            f"{client.last_name.upper()}, {client.first_name} - {visa_type}" if visa_type else None,
            f"{client.last_name.upper()}, {client.first_name}",
            f"{client.first_name} {client.last_name}",
        ]

        folder_id = None
        client_name = None
        for name in possible_names:
            if name:
                folder_id = handler.get_client_folder(name)
                if folder_id:
                    client_name = name
                    break

        if not folder_id:
            raise HTTPException(
                status_code=404,
                detail=f"Drive folder not found. Tried: {[n for n in possible_names if n]}"
            )

        result = handler.download_client_folder(
            client_name,
            os.path.join(settings.BASE_DIR, "documents", "clients") + "/",
            skip_existing=skip_existing
        )

        return {
            "success": True,
            "client_id": client_id,
            "client_name": client_name,
            "downloaded": result.get('downloaded', 0),
            "skipped": result.get('skipped', 0),
            "failed": result.get('failed', 0),
            "total": result.get('total', 0),
            "files": result.get('files', [])
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.get("/drive/all-files")
async def list_all_drive_files(
    request: Request,
    db: Session = Depends(get_db)):
    """List all Google Drive files across all clients - reads directly from Drive."""
    try:
        from services.google_drive_handler import GoogleDriveHandler
        org_id = request.state.org_id
        handler = GoogleDriveHandler(db, org_id=org_id)
        if not handler.service:
            raise HTTPException(status_code=503, detail="Google Drive not connected")

        # Step 1: List ALL folders in this org's Active Clients root
        active_clients_folder_id = handler.get_root_folder_id()
        if not active_clients_folder_id:
            raise HTTPException(status_code=503, detail="Drive root folder not configured for this org")
        folders_result = handler.service.files().list(
            q=f"mimeType='application/vnd.google-apps.folder' and '{active_clients_folder_id}' in parents and trashed=false",
            fields="files(id, name)",
            pageSize=200
        ).execute()
        client_folders = folders_result.get("files", [])

        # Step 2: Build client name->id lookup from DB
        clients = tenant_query(db, Client, org_id).all()
        client_lookup = {}
        for c in clients:
            client_lookup[f"{c.last_name.upper()}, {c.first_name}".lower()] = c.id
            client_lookup[f"{c.first_name} {c.last_name}".lower()] = c.id
            client_lookup[f"{c.last_name}, {c.first_name}".lower()] = c.id

        # Step 3: For each folder, list files
        all_files = []
        for folder in client_folders:
            folder_name = folder["name"]
            folder_id = folder["id"]

            # Try to match to client in DB
            matched_client_id = None
            folder_lower = folder_name.lower()
            for key, cid in client_lookup.items():
                if key in folder_lower or folder_lower.startswith(key):
                    matched_client_id = cid
                    break

            # List files in this folder (1 API call)
            try:
                files_result = handler.service.files().list(
                    q=f"'{folder_id}' in parents and trashed=false and mimeType!='application/vnd.google-apps.folder'",
                    fields="files(id, name, mimeType, size, modifiedTime, webViewLink, iconLink)",
                    pageSize=100
                ).execute()
                files = files_result.get("files", [])

                for f in files:
                    f["client_id"] = matched_client_id
                    f["client_name"] = folder_name
                    f["client_folder_name"] = folder_name
                    f["folder_id"] = folder_id
                    all_files.append(f)
            except Exception as e:
                logger.error("Error listing files for folder %s: %s", folder_name, e)
                continue

        return {"success": True, "total_files": len(all_files), "files": all_files}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list Drive files: {str(e)}")



@router.post("/drive/download-to-casehub")
async def download_drive_file_to_casehub(
    request: Request,
    file_id: str = Form(...),
    client_id: int = Form(...),
    file_name: str = Form(...),
    mime_type: str = Form(None),
    file_size: str = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api)
):
    """Download a file from Google Drive and create a Document record in CaseHub."""
    # Convert form strings to proper types
    file_size = form_int(file_size)

    try:
        from services.google_drive_handler import GoogleDriveHandler
        import hashlib

        org_id = request.state.org_id
        handler = GoogleDriveHandler(db, org_id=org_id)

        if not handler.service:
            raise HTTPException(status_code=503, detail="Google Drive not connected")

        # Find client
        client = tenant_query(db, Client, org_id).filter(Client.id == client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")

        # Create download directory
        download_dir = os.path.join(settings.BASE_DIR, "documents", "clients", "drive_downloads", str(client_id))
        os.makedirs(download_dir, exist_ok=True)

        # Download file
        destination_path = os.path.join(download_dir, file_name)

        # Check if file already exists in DB (by drive_file_id)
        existing_doc = tenant_query(db, Document, request.state.org_id).filter(
            Document.drive_file_id == file_id,
            Document.client_id == client_id
        ).first()

        if existing_doc:
            return {
                "success": True,
                "message": "File already exists in CaseHub",
                "document_id": existing_doc.id,
                "skipped": True
            }

        # Download from Drive
        downloaded_path = handler.download_document(file_id, destination_path)

        if not downloaded_path or not os.path.exists(downloaded_path):
            raise HTTPException(status_code=500, detail="Download failed")

        # Calculate file hash
        file_hash = None
        try:
            with open(downloaded_path, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
        except Exception as e:
            logger.error("Error calculating hash: %s", e)

        # Get actual file size
        actual_size = os.path.getsize(downloaded_path) if os.path.exists(downloaded_path) else file_size

        # Detect doc_type from filename
        doc_type = "Other Document"
        filename_lower = file_name.lower()
        if 'passport' in filename_lower or 'passaporte' in filename_lower:
            doc_type = "Passport"
        elif 'resume' in filename_lower or 'cv' in filename_lower:
            doc_type = "Resume/CV"
        elif 'diploma' in filename_lower or 'transcript' in filename_lower:
            doc_type = "Diploma"
        elif 'tax' in filename_lower or 'w2' in filename_lower or '1040' in filename_lower:
            doc_type = "Tax Return"
        elif 'photo' in filename_lower or 'foto' in filename_lower:
            doc_type = "Photo"
        elif 'i-' in filename_lower or 'form' in filename_lower:
            doc_type = "USCIS Form"
        elif 'lor' in filename_lower or 'letter' in filename_lower or 'recommendation' in filename_lower:
            doc_type = "Letter of Recommendation"

        # Create Document record
        new_doc = Document(
            name=file_name,
            file_path=downloaded_path,
            drive_file_id=file_id,
            drive_link=f"https://drive.google.com/file/d/{file_id}/view",
            client_id=client_id,
            doc_type=doc_type,
            status="pending",
            uploaded_via="google_drive",
            file_size=actual_size,
            mime_type=mime_type,
            file_hash=file_hash,
            created_at=datetime.utcnow()
        )

        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)

        return {
            "success": True,
            "message": "File downloaded successfully",
            "document_id": new_doc.id,
            "document_name": new_doc.name,
            "file_size": actual_size,
            "doc_type": doc_type,
            "downloaded": True
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


# ============================================================================
# ADMIN: REPROCESS & RETRY ENDPOINTS
# ============================================================================

@router.post("/admin/reprocess-client-emails/{client_id}")
async def reprocess_client_emails(
    client_id: int,
    request: Request,
    days_back: int = Query(default=7, le=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_api)
):
    """
    Reprocess emails from a specific client.
    Clears processed email tracking for this client and re-runs the email processor.
    """
    if not current_user or getattr(current_user, 'user_type', '') != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")

        from services.email_processor import EmailProcessor
        from datetime import timedelta

        processor = EmailProcessor()
        since_date = datetime.now() - timedelta(days=days_back)

        results = processor.check_specific_clients(
            client_emails=[client.email],
            since_date=since_date,
            dry_run=False
        )

        return {
            "success": True,
            "client_id": client_id,
            "client_name": f"{client.first_name} {client.last_name}",
            "days_back": days_back,
            "results": results
        }

    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.exception(f"Reprocess failed for client {client_id}")
        raise HTTPException(status_code=500, detail=f"Reprocess failed: {str(e)}")


@router.post("/admin/retry-drive-sync")
async def retry_drive_sync_endpoint(
    request: Request,
    max_retries: int = Query(default=3, le=5),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_api)
):
    """Retry failed Google Drive syncs for all documents."""
    if not current_user or getattr(current_user, 'user_type', '') != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    result = retry_failed_syncs(db, max_retries=max_retries, org_id=request.state.org_id)
    return {"success": True, **result}


@router.post("/admin/sync-client-to-drive/{client_id}")
async def sync_client_to_drive(
    client_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_api)
):
    """Sync all unsynced documents for a client to Google Drive."""
    if not current_user or getattr(current_user, 'user_type', '') != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    unsynced_docs = tenant_query(db, Document, request.state.org_id).filter(
        Document.client_id == client_id,
        Document.drive_sync_status.notin_(["synced"]),
        Document.status.notin_(["REJECTED", "archived"]),
        Document.file_path.isnot(None)
    ).all()

    results = {"synced": 0, "failed": 0, "skipped": 0, "details": []}

    for doc in unsynced_docs:
        try:
            sync_result = sync_to_google_drive(db, doc.id, org_id=request.state.org_id)
            if sync_result.get("success"):
                results["synced"] += 1
            else:
                results["failed"] += 1
            results["details"].append({
                "doc_id": doc.id,
                "name": doc.name,
                "result": sync_result.get("drive_sync_status"),
                "link": sync_result.get("web_link")
            })
        except Exception as e:
            results["failed"] += 1
            results["details"].append({
                "doc_id": doc.id,
                "name": doc.name,
                "error": str(e)
            })

    return {
        "success": True,
        "client_id": client_id,
        "client_name": f"{client.first_name} {client.last_name}",
        "total_unsynced": len(unsynced_docs),
        **results
    }


class ShareFromDriveRequest(BaseModel):
    client_id: int
    drive_file_id: str
    file_name: str
    doc_type: str = "Other Document"
    mime_type: str = ""
    file_size: int = 0


@router.post("/share-from-drive")
async def share_drive_file_with_client(
    req: ShareFromDriveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_api),
):
    """Share a Google Drive file with a client via the portal.

    Creates a document record in the DB pointing to the Drive file,
    making it visible in the client's portal. The file stays in Drive
    (no download needed).
    """
    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == req.client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Check if already shared (avoid duplicates)
    existing = tenant_query(db, Document, request.state.org_id).filter(
        Document.drive_file_id == req.drive_file_id,
        Document.client_id == req.client_id,
    ).first()
    if existing:
        return {"success": True, "action": "already_shared", "doc_id": existing.id}

    # Find client's case
    case = tenant_query(db, Case, request.state.org_id).filter(Case.client_id == req.client_id).first()

    doc = Document(
        name=req.file_name,
        doc_type=req.doc_type,
        status="APPROVED",
        client_id=req.client_id,
        case_id=case.id if case else None,
        uploaded_via="drive_share",
        drive_file_id=req.drive_file_id,
        drive_link=f"https://drive.google.com/file/d/{req.drive_file_id}/view",
        mime_type=req.mime_type or None,
        file_size=req.file_size or None,
        client_visible=True,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return {
        "success": True,
        "action": "shared",
        "doc_id": doc.id,
        "client_name": f"{client.first_name} {client.last_name}",
    }
