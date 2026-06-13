"""Upload a CaseHub document to Google Drive from its stored local file.

POST /drive/upload-from-document  {document_id: int}
Returns JSON {success, drive_link, file_id, error}

On success, updates Document.drive_file_id and Document.drive_link.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from auth import get_current_user
from core.template_config import PREFIX
from models import get_db
from models.document import Document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/drive", tags=["drive-upload"])


@router.post("/upload-from-document")
async def upload_from_document(request: Request, db: Session = Depends(get_db)):
    """Upload a locally-stored Document to the org's Google Drive."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"success": False, "error": "unauthenticated"}, status_code=401)

    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        return JSONResponse({"success": False, "error": "no_org_context"}, status_code=400)

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "invalid_json"}, status_code=400)

    document_id = payload.get("document_id")
    if not document_id:
        return JSONResponse({"success": False, "error": "missing_document_id"}, status_code=400)

    doc = db.query(Document).filter(
        Document.id == int(document_id),
        Document.org_id == org_id,
    ).first()
    if not doc:
        return JSONResponse({"success": False, "error": "document_not_found"}, status_code=404)

    if not doc.file_path or not os.path.exists(doc.file_path):
        return JSONResponse({"success": False, "error": "local_file_missing"}, status_code=422)

    from services.google_drive_handler import GoogleDriveHandler

    handler = GoogleDriveHandler(db=db, org_id=org_id)
    if not handler.is_connected():
        return JSONResponse({"success": False, "error": "drive_not_connected"}, status_code=503)

    client_name = ""
    if doc.client:
        client_name = f"{doc.client.first_name} {doc.client.last_name}".strip()

    try:
        result = await run_in_threadpool(
            handler.upload_document,
            doc.file_path,
            client_name or "Sem cliente",
            doc.title or os.path.basename(doc.file_path),
        )
    except Exception as e:
        logger.error("Drive upload failed for document %s: %s", document_id, e)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    if result.get("success"):
        doc.drive_file_id = result.get("file_id")
        doc.drive_link = result.get("web_link")
        try:
            db.commit()
        except Exception as e:
            logger.warning("Failed to persist drive_file_id for doc %s: %s", document_id, e)
            db.rollback()

    return JSONResponse({
        "success": result.get("success", False),
        "drive_link": result.get("web_link"),
        "file_id": result.get("file_id"),
        "error": result.get("error"),
    })
