"""
CaseHub - Document Versioning Routes
View and manage document versions
"""
from fastapi import APIRouter, Depends, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
import os
import shutil

from models import get_db, Document
from auth import get_current_user
from models.tenant import tenant_query
from i18n import get_translations
from config import settings
from services.versioning import DocumentVersioningService

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/versions", tags=["versions"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py


def get_context(request: Request, db: Session, **kwargs):
    """Build template context."""
    lang = request.cookies.get("lang", "en")
    user = get_current_user(request, db)
    return {
        "request": request,
        "PREFIX": PREFIX,
        "lang": lang,
        "t": get_translations(lang),
        "user": user,
        **kwargs
    }


@router.get("/document/{document_id}", response_class=HTMLResponse)
async def document_versions(request: Request, document_id: int, db: Session = Depends(get_db)):
    """View versions of a document."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    document = tenant_query(db, Document, request.state.org_id).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    service = DocumentVersioningService(db)
    versions = service.get_versions(document_id)

    return templates.TemplateResponse("app/versions/document.html", {
        **get_context(request, db),
        "document": document,
        "versions": versions
    })


@router.post("/document/{document_id}/upload")
async def upload_new_version(
    request: Request,
    document_id: int,
    file: UploadFile = File(...),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Upload a new version of a document."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    document = tenant_query(db, Document, request.state.org_id).filter(Document.id == document_id).first()
    if not document:
        return JSONResponse({"error": "Document not found"}, status_code=404)

    # Save uploaded file temporarily
    upload_dir = os.path.join(settings.BASE_DIR, "uploads")
    temp_path = os.path.join(upload_dir, f"temp_{document_id}_{file.filename}")
    
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        service = DocumentVersioningService(db)
        result = service.create_version(document_id, temp_path, user.id, notes)

        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)

        return JSONResponse(result)
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.get("/document/{document_id}/version/{version_number}/download")
async def download_version(
    request: Request,
    document_id: int,
    version_number: int,
    db: Session = Depends(get_db)
):
    """Download a specific version of a document."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    service = DocumentVersioningService(db)
    version = service.get_version(document_id, version_number)
    
    if not version or not os.path.exists(version["file_path"]):
        raise HTTPException(status_code=404, detail="Version not found")

    document = tenant_query(db, Document, request.state.org_id).filter(Document.id == document_id).first()
    filename = f"{document.name}_v{version_number}" if document else f"document_v{version_number}"
    ext = os.path.splitext(version["file_path"])[1]
    
    return FileResponse(
        version["file_path"],
        filename=f"{filename}{ext}",
        media_type="application/octet-stream"
    )


@router.post("/document/{document_id}/restore/{version_number}")
async def restore_version(
    request: Request,
    document_id: int,
    version_number: int,
    db: Session = Depends(get_db)
):
    """Restore a document to a previous version."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    document = tenant_query(db, Document, request.state.org_id).filter(Document.id == document_id).first()
    if not document:
        return JSONResponse({"error": "Document not found"}, status_code=404)

    service = DocumentVersioningService(db)
    result = service.restore_version(document_id, version_number, user.id)
    
    if not result.get("success"):
        return JSONResponse(result, status_code=400)
    
    return JSONResponse(result)


@router.get("/api/document/{document_id}")
async def api_get_versions(request: Request, document_id: int, db: Session = Depends(get_db)):
    """API: Get all versions of a document."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = DocumentVersioningService(db)
    versions = service.get_versions(document_id)
    
    return JSONResponse(versions)


@router.get("/api/stats")
async def api_version_stats(request: Request, db: Session = Depends(get_db)):
    """API: Get versioning statistics."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = DocumentVersioningService(db)
    stats = service.get_version_stats()
    
    return JSONResponse(stats)
