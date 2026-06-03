"""
CaseHub - Document Packet Routes
Create and manage document packets.
"""
from datetime import datetime
from typing import Optional, List
import json
import logging

logger = logging.getLogger(__name__)

from core.form_utils import form_int, form_float
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, User, Case, Document
from auth import get_current_user
from models.tenant import tenant_query
from services.packet_service import packet_service, CREATE_PACKETS_TABLE

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/packets", tags=["packets"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py


def ensure_tables(db: Session):
    """Ensure packet tables exist."""
    try:
        db.execute(text(CREATE_PACKETS_TABLE))
        db.commit()
    except Exception as e:
        db.rollback()


@router.get("", response_class=HTMLResponse)
async def packets_list(request: Request, db: Session = Depends(get_db)):
    """List all document packets."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    # Get packets
    try:
        result = db.execute(text("""
            SELECT p.*, c.case_name, c.case_number
            FROM document_packets p
            LEFT JOIN cases c ON p.case_id = c.id
            WHERE p.org_id = :org_id
            ORDER BY p.created_at DESC
        """), {"org_id": request.state.org_id})
        packets = result.fetchall()
    except Exception:
        db.rollback()
        packets = []

    return templates.TemplateResponse("app/packets/list.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "packets": packets
    })


@router.get("/new", response_class=HTMLResponse)
async def new_packet(request: Request, case_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Create new packet page."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    # Get cases
    cases = tenant_query(db, Case, request.state.org_id).order_by(Case.created_at.desc()).all()

    # Get documents for selected case
    documents = []
    selected_case = None
    if case_id:
        selected_case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
        documents = tenant_query(db, Document, request.state.org_id).filter(Document.case_id == case_id).order_by(Document.name).all()

    return templates.TemplateResponse("app/packets/create.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "cases": cases,
        "documents": documents,
        "selected_case": selected_case
    })


@router.get("/case/{case_id}/documents", response_class=JSONResponse)
async def get_case_documents(case_id: int, request: Request, db: Session = Depends(get_db)):
    """API: Get documents for a case."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})

    documents = tenant_query(db, Document, request.state.org_id).filter(Document.case_id == case_id).order_by(Document.name).all()

    return JSONResponse(content=[
        {
            "id": doc.id,
            "name": doc.name,
            "file_path": doc.file_path,
            "type": doc.type,
            "created_at": doc.created_at.isoformat() if doc.created_at else None
        }
        for doc in documents
    ])


@router.post("/create")
async def create_packet(
    request: Request,
    case_id: str = Form(None),
    title: str = Form(...),
    document_ids: str = Form(...),  # JSON array of document IDs in order
    include_toc: bool = Form(True),
    include_cover: bool = Form(True),
    db: Session = Depends(get_db)
):
    """Create a new document packet."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Convert form strings to proper types
    case_id = form_int(case_id)

    ensure_tables(db)

    # Parse document IDs
    try:
        doc_ids = json.loads(document_ids)
        if not isinstance(doc_ids, list):
            doc_ids = [doc_ids]
    except Exception as e:
        logger.error("Failed to parse document IDs: %s", e)
        raise HTTPException(status_code=400, detail="Invalid document IDs")

    if not doc_ids:
        raise HTTPException(status_code=400, detail="No documents selected")

    # Get documents in order
    documents = []
    for doc_id in doc_ids:
        doc = tenant_query(db, Document, request.state.org_id).filter(Document.id == doc_id).first()
        if doc and doc.file_path:
            documents.append({
                "id": doc.id,
                "name": doc.name,
                "filepath": doc.file_path
            })

    if not documents:
        raise HTTPException(status_code=400, detail="No valid documents found")

    # Get case info if provided
    case_info = None
    if case_id:
        case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
        if case:
            from models import Client
            client = tenant_query(db, Client, request.state.org_id).filter(Client.id == case.client_id).first()
            case_info = {
                "case_number": case.case_number,
                "case_name": case.case_name,
                "client_name": f"{client.first_name} {client.last_name}" if client else None
            }

    # Create the packet
    result = packet_service.create_packet(
        documents=documents,
        title=title,
        include_toc=include_toc,
        include_cover=include_cover,
        case_info=case_info
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to create packet"))

    # Save to database
    try:
        db.execute(text("""
            INSERT INTO document_packets (packet_id, case_id, title, filepath, document_count, total_pages, include_toc, include_cover, created_by, org_id)
            VALUES (:pid, :case_id, :title, :filepath, :doc_count, :pages, :toc, :cover, :uid, :org_id)
            RETURNING id
        """), {
            "pid": result["packet_id"],
            "case_id": case_id,
            "title": title,
            "filepath": result["filepath"],
            "doc_count": result["document_count"],
            "pages": result.get("total_pages", 0),
            "toc": include_toc,
            "cover": include_cover,
            "uid": user.id,
            "org_id": request.state.org_id
        })

        # Save document order
        packet_result = db.execute(text("SELECT id FROM document_packets WHERE packet_id = :pid"), {"pid": result["packet_id"]})
        packet_row = packet_result.fetchone()

        if packet_row:
            for i, doc in enumerate(documents):
                db.execute(text("""
                    INSERT INTO packet_documents (packet_id, document_id, document_name, sort_order)
                    VALUES (:packet_id, :doc_id, :name, :order)
                """), {
                    "packet_id": packet_row.id,
                    "doc_id": doc["id"],
                    "name": doc["name"],
                    "order": i
                })

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    return RedirectResponse(url=f"{PREFIX}/packets/{result['packet_id']}", status_code=302)


@router.get("/{packet_id}", response_class=HTMLResponse)
async def view_packet(request: Request, packet_id: str, db: Session = Depends(get_db)):
    """View packet details."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    try:
        result = db.execute(text("""
            SELECT p.*, c.case_name, c.case_number, u.name as creator_name
            FROM document_packets p
            LEFT JOIN cases c ON p.case_id = c.id
            LEFT JOIN users u ON p.created_by = u.id
            WHERE p.packet_id = :pid AND p.org_id = :org_id
        """), {"pid": packet_id, "org_id": request.state.org_id})
        packet = result.fetchone()

        if not packet:
            raise HTTPException(status_code=404, detail="Packet not found")

        # Get included documents
        docs_result = db.execute(text("""
            SELECT pd.*, d.file_path
            FROM packet_documents pd
            LEFT JOIN documents d ON pd.document_id = d.id
            WHERE pd.packet_id = :pid
            ORDER BY pd.sort_order
        """), {"pid": packet.id})
        documents = docs_result.fetchall()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return templates.TemplateResponse("app/packets/view.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "packet": packet,
        "documents": documents
    })


@router.get("/{packet_id}/download")
async def download_packet(request: Request, packet_id: str, db: Session = Depends(get_db)):
    """Download packet PDF."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        result = db.execute(text("SELECT filepath, title FROM document_packets WHERE packet_id = :pid AND org_id = :org_id"),
                            {"pid": packet_id, "org_id": request.state.org_id})
        packet = result.fetchone()

        if not packet:
            raise HTTPException(status_code=404, detail="Packet not found")

        return FileResponse(
            packet.filepath,
            media_type="application/pdf",
            filename=f"{packet.title.replace(' ', '_')}.pdf"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{packet_id}/delete")
async def delete_packet(request: Request, packet_id: str, db: Session = Depends(get_db)):
    """Delete a packet."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        result = db.execute(text("SELECT filepath FROM document_packets WHERE packet_id = :pid AND org_id = :org_id"),
                            {"pid": packet_id, "org_id": request.state.org_id})
        packet = result.fetchone()

        if not packet:
            raise HTTPException(status_code=404, detail="Packet not found")

        # Delete file
        packet_service.delete_packet(packet.filepath)

        # Delete from database
        db.execute(text("DELETE FROM document_packets WHERE packet_id = :pid AND org_id = :org_id"), {"pid": packet_id, "org_id": request.state.org_id})
        db.commit()

        return RedirectResponse(url=f"{PREFIX}/packets", status_code=302)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
