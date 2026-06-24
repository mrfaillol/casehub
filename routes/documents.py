"""
CaseHub - Document Routes
Updated Feb 8, 2026 - Added all_clients query for Tree View
"""
from core.form_utils import form_int, form_float
from core.template_config import templates
from fastapi import APIRouter, Depends, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, text, func
from typing import Optional, List
import os
import uuid
from datetime import datetime

from models import get_db, Client, Case, Document, User, Organization
from auth import get_current_user
from models.tenant import tenant_query
from config import settings
from services.drive_explorer import DriveNotAvailable, create_blank_doc

import logging

logger = logging.getLogger(__name__)

PREFIX = settings.PREFIX
UPLOAD_DIR = os.path.join(settings.BASE_DIR, "data", "uploads")

router = APIRouter(prefix="/documents", tags=["documents"])

try:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
except PermissionError:
    pass


def _document_type_options(product: str):
    immigration_labels = {
        "other": "Other",
        "passport": "Passport",
        "visa": "Visa",
        "i94": "I-94",
        "diploma": "Diploma/Degree",
        "transcript": "Transcript",
        "lor": "Letter of Recommendation",
        "cv": "CV/Resume",
        "contract": "Employment Contract",
        "paystub": "Pay Stub",
        "tax": "Tax Document",
    }
    lite_labels = {
        "other": "Outro",
        "passport": "Documento de identidade",
        "visa": "Documento processual",
        "i94": "Registro / protocolo",
        "diploma": "Diploma / certificado",
        "transcript": "Histórico / certidão",
        "lor": "Declaração / recomendação",
        "cv": "Currículo",
        "contract": "Contrato",
        "paystub": "Comprovante",
        "tax": "Documento fiscal",
    }
    labels = lite_labels if product == "lite" else immigration_labels
    return [{"value": value, "label": labels[value]} for value in immigration_labels]


def _drive_root_id_for_org(
    db: Session,
    org_id: Optional[int],
    client_id: Optional[int] = None,
) -> str:
    """Resolve the Drive folder the document explorer should open for a tenant."""
    if org_id is not None and client_id is not None:
        client = (
            tenant_query(db, Client, org_id)
            .filter(Client.id == client_id)
            .first()
        )
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        if client.drive_folder_id:
            return client.drive_folder_id

    root_id = ""
    if org_id is not None:
        try:
            org = db.query(Organization).filter(Organization.id == org_id).first()
            root_id = getattr(org, "google_drive_root_id", None) or ""
        except Exception:
            root_id = ""
    return root_id or settings.GOOGLE_DRIVE_ROOT_ID or "root"


@router.get("", response_class=HTMLResponse)
async def list_documents(
    request: Request,
    search: Optional[str] = None,
    doc_type: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
    client_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    query = tenant_query(db, Document, request.state.org_id)

    if search:
        query = query.filter(Document.name.ilike(f"%{search}%"))
    if doc_type:
        query = query.filter(Document.doc_type == doc_type)
    if status:
        query = query.filter(Document.status == status)

    total = query.count()
    documents = query.order_by(Document.created_at.desc()).offset((page-1)*per_page).limit(per_page).all()

    # ========== NEW: Query ALL clients with document counts ==========
    all_clients_result = db.execute(text("""
        SELECT
            c.id,
            c.first_name,
            c.last_name,
            COUNT(d.id) as doc_count
        FROM clients c
        LEFT JOIN documents d ON d.client_id = c.id
        WHERE c.org_id = :org_id
        GROUP BY c.id, c.first_name, c.last_name
        HAVING COUNT(d.id) > 0
        ORDER BY c.last_name, c.first_name
    """), {"org_id": request.state.org_id})
    all_clients = [
        {"id": r[0], "first_name": r[1], "last_name": r[2], "doc_count": r[3]}
        for r in all_clients_result.fetchall()
    ]

    # Count documents without client
    unlinked_count = tenant_query(db, Document, request.state.org_id).with_entities(func.count(Document.id)).filter(Document.client_id == None).scalar() or 0
    # =================================================================

    return templates.TemplateResponse("app/documents/list.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "documents": documents,
        "total": total,
        "page": page,
        "per_page": per_page,
        "search": search or "",
        "doc_type": doc_type or "",
        "status": status or "",
        "drive_root_id": _drive_root_id_for_org(
            db,
            getattr(request.state, "org_id", None),
            client_id=client_id,
        ),
        "selected_client_id": client_id,
        # NEW: Pass to template
        "all_clients": all_clients,
        "unlinked_count": unlinked_count
    })


# ========== NEW: API endpoint for lazy loading documents by client ==========
@router.get("/api/by-client/{client_id}")
async def get_documents_by_client(
    request: Request,
    client_id: int,
    db: Session = Depends(get_db)
):
    """Returns documents for a specific client for lazy loading in Tree View."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if client_id == 0:
        # Documents without client
        docs = tenant_query(db, Document, request.state.org_id).filter(Document.client_id == None).order_by(Document.created_at.desc()).limit(200).all()
    else:
        docs = tenant_query(db, Document, request.state.org_id).filter(Document.client_id == client_id).order_by(Document.created_at.desc()).limit(200).all()

    return JSONResponse([
        {
            "id": d.id,
            "name": d.name,
            "doc_type": d.doc_type or "",
            "mime_type": d.mime_type or "",
            "created_at": d.created_at.strftime("%d/%m/%Y") if d.created_at else ""
        }
        for d in docs
    ])
# =============================================================================


# ========== NEW: Create a blank Google Doc in the explorer's current folder ===
from pydantic import BaseModel as _BaseModel

class CreateDocRequest(_BaseModel):
    parent_id: Optional[str] = None
    name: Optional[str] = None


@router.post("/api/drive/create-doc")
async def create_drive_doc(
    request: Request,
    data: CreateDocRequest,
    db: Session = Depends(get_db),
):
    """Create an empty native Google Doc in the folder the user is browsing.

    Lives here (router prefix ``/documents``) so ``routes/drive_explorer.py``
    stays 100% read-only. Tenant-scoped via ``request.state.org_id`` and the
    org's already-connected OAuth token — no fresh auth prompt. Error contract
    mirrors the read endpoints: 401 unauthenticated, 503 drive_unavailable,
    502 on any Drive upstream error (never 500).
    """
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    org_id = getattr(request.state, "org_id", None)

    try:
        created = create_blank_doc(data.parent_id, data.name, org_id=org_id)
    except DriveNotAvailable as exc:
        logger.warning("[DRIVE CREATE-DOC] service unavailable: %s", exc)
        return JSONResponse(
            {"error": "drive_unavailable", "detail": str(exc)},
            status_code=503,
        )
    except Exception as exc:  # noqa: BLE001 — mapped to 502, never 500
        logger.warning("[DRIVE CREATE-DOC] upstream error: %s", exc)
        return JSONResponse(
            {"error": "drive_upstream_error", "action": "create-doc"},
            status_code=502,
        )

    return JSONResponse({
        "id": created.get("id"),
        "name": created.get("name"),
        "webViewLink": created.get("web_view_link"),
    })
# =============================================================================


@router.get("/upload", response_class=HTMLResponse)
async def upload_form(
    request: Request,
    client_id: Optional[int] = None,
    case_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    clients = tenant_query(db, Client, request.state.org_id).order_by(Client.first_name).all()
    cases = tenant_query(db, Case, request.state.org_id).order_by(Case.created_at.desc()).all()
    product = getattr(request.app.state, "product", "lite")

    return templates.TemplateResponse("app/documents/upload.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "clients": clients,
        "cases": cases,
        "product": product,
        "selected_client_id": client_id,
        "selected_case_id": case_id,
        "document_type_options": _document_type_options(product)
    })

@router.post("/upload")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(None),
    doc_type: str = Form("other"),
    client_id: str = Form(None),
    case_id: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Convert form strings to proper types
    client_id = form_int(client_id)
    case_id = form_int(case_id)

    # Validate file extension
    ALLOWED_EXTENSIONS = {'.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.gif',
                          '.tiff', '.tif', '.bmp', '.xls', '.xlsx', '.txt', '.rtf',
                          '.csv', '.zip', '.rar', '.msg', '.eml'}
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

    # --- Security: sanitize filename (prevent path traversal) ---
    import re
    safe_filename = os.path.basename(file.filename or "upload")
    safe_filename = re.sub(r'[^\w\s\-\.]', '_', safe_filename)  # strip suspicious chars
    if '..' in safe_filename or '/' in safe_filename or '\\' in safe_filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    ext = os.path.splitext(safe_filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type '{ext}' not allowed")

    # Generate unique filename
    unique_filename = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    # Read and validate size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 50MB)")

    # --- Security: MIME type validation (content sniffing) ---
    ALLOWED_MIMES = {
        'application/pdf', 'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'image/jpeg', 'image/png', 'image/gif', 'image/tiff', 'image/bmp',
        'text/plain', 'text/csv', 'application/rtf',
        'application/zip', 'application/x-rar-compressed',
        'application/vnd.ms-outlook', 'message/rfc822',
    }
    try:
        import magic
        detected_mime = magic.from_buffer(content[:2048], mime=True)
        if detected_mime not in ALLOWED_MIMES:
            raise HTTPException(
                status_code=400,
                detail=f"File content type '{detected_mime}' not allowed (extension was '{ext}')"
            )
    except ImportError:
        pass  # python-magic not installed; fall back to extension-only check

    # Save file
    with open(file_path, "wb") as f:
        f.write(content)

    # Create document record
    doc = Document(
        name=name or file.filename,
        doc_type=doc_type,
        status="received",
        file_path=file_path,
        file_size=len(content),
        mime_type=file.content_type,
        client_id=client_id,
        case_id=case_id,
        uploaded_by=user.id,
        notes=notes,
        org_id=request.state.org_id)
    db.add(doc)
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/documents/{doc.id}", status_code=302)

@router.get("/{doc_id}", response_class=HTMLResponse)
async def view_document(request: Request, doc_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    doc = tenant_query(db, Document, request.state.org_id).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == doc.client_id).first() if doc.client_id else None
    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == doc.case_id).first() if doc.case_id else None

    return templates.TemplateResponse("app/documents/detail.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "document": doc,
        "client": client,
        "case": case
    })

@router.get("/{doc_id}/download")
async def download_document(request: Request, doc_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    doc = tenant_query(db, Document, request.state.org_id).filter(Document.id == doc_id).first()
    if not doc or not doc.file_path or not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="File not found")

    # Prevent path traversal: ensure resolved path is within allowed upload directory
    resolved_path = os.path.realpath(doc.file_path)
    allowed_dir = os.path.realpath(UPLOAD_DIR)
    if not resolved_path.startswith(allowed_dir + os.sep) and resolved_path != allowed_dir:
        raise HTTPException(status_code=403, detail="Access denied")

    return FileResponse(resolved_path, filename=doc.name, media_type=doc.mime_type)


@router.get("/{doc_id}/preview")
async def preview_document(request: Request, doc_id: int, db: Session = Depends(get_db)):
    """Retorna arquivo para preview inline (PDF/imagem)"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    doc = tenant_query(db, Document, request.state.org_id).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = doc.file_path
    if not file_path or not os.path.exists(file_path):
        # Try local_path
        file_path = doc.local_path if doc.local_path else None
        if not file_path or not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")

    # Prevent path traversal: ensure resolved path is within allowed upload directory
    resolved_path = os.path.realpath(file_path)
    allowed_dir = os.path.realpath(UPLOAD_DIR)
    if not resolved_path.startswith(allowed_dir + os.sep) and resolved_path != allowed_dir:
        raise HTTPException(status_code=403, detail="Access denied")

    import mimetypes
    mime_type = doc.mime_type or mimetypes.guess_type(file_path)[0] or "application/octet-stream"

    return FileResponse(
        path=resolved_path,
        media_type=mime_type,
        headers={"Content-Disposition": "inline"}
    )

@router.post("/{doc_id}/delete")
async def delete_document(request: Request, doc_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    doc = tenant_query(db, Document, request.state.org_id).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete file
    if doc.file_path and os.path.exists(doc.file_path):
        os.remove(doc.file_path)

    db.delete(doc)
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/documents", status_code=302)


# ==================== BULK OPERATIONS ====================
from pydantic import BaseModel

class BulkDeleteRequest(BaseModel):
    ids: List[int]

class BulkMoveRequest(BaseModel):
    ids: List[int]
    client_id: int

class BulkUpdateTypeRequest(BaseModel):
    ids: List[int]
    doc_type: str


MAX_BULK_ITEMS = 500

@router.post("/bulk/delete")
async def bulk_delete(request: Request, data: BulkDeleteRequest, db: Session = Depends(get_db)):
    """Delete multiple documents at once."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if len(data.ids) > MAX_BULK_ITEMS:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_BULK_ITEMS} items per bulk operation")

    # Batch the per-id lookup that ran inside the loop (N+1 -> 1 SELECT).
    # The pre-fix `.first()` per id avoided double-counting duplicate ids by
    # accident (SA autoflush would DELETE the row before the next .first(),
    # making the second lookup return None); `.in_` makes that de-duping
    # explicit at the query level rather than relying on flush side effects.
    docs = tenant_query(db, Document, request.state.org_id).filter(
        Document.id.in_(data.ids)
    ).all()
    deleted = 0
    for doc in docs:
        # Delete physical file if exists
        if doc.file_path and os.path.exists(doc.file_path):
            try:
                os.remove(doc.file_path)
            except OSError:
                pass
        db.delete(doc)
        deleted += 1

    db.commit()
    return {"deleted": deleted}


@router.post("/bulk/move")
async def bulk_move(request: Request, data: BulkMoveRequest, db: Session = Depends(get_db)):
    """Move multiple documents to a different client."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Verify target client exists
    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == data.client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    updated = tenant_query(db, Document, request.state.org_id).filter(Document.id.in_(data.ids)).update(
        {Document.client_id: data.client_id},
        synchronize_session=False
    )
    db.commit()
    return {"moved": updated}


@router.post("/bulk/update-type")
async def bulk_update_type(request: Request, data: BulkUpdateTypeRequest, db: Session = Depends(get_db)):
    """Update document type for multiple documents."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    updated = tenant_query(db, Document, request.state.org_id).filter(Document.id.in_(data.ids)).update(
        {Document.doc_type: data.doc_type},
        synchronize_session=False
    )
    db.commit()
    return {"updated": updated}


# ==================== RENAME DOCUMENT ====================
class RenameRequest(BaseModel):
    new_name: str

@router.post("/{doc_id}/rename")
async def rename_document(request: Request, doc_id: int, data: RenameRequest, db: Session = Depends(get_db)):
    """Rename a document."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    doc = tenant_query(db, Document, request.state.org_id).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Validate new name
    new_name = data.new_name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")

    # Preserve extension if not provided
    import os as os_module
    old_ext = os_module.path.splitext(doc.name)[1] if doc.name else ""
    new_ext = os_module.path.splitext(new_name)[1]
    if not new_ext and old_ext:
        new_name = new_name + old_ext

    # Update document name
    doc.name = new_name
    db.commit()

    return {"success": True, "new_name": new_name}
