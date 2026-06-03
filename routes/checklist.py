"""
CaseHub - Document Checklist Routes
Provides document checklist generation, classification, and export for immigration cases.
"""
from fastapi import APIRouter, Depends, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional
from pydantic import BaseModel
import os
import io
import logging

from models import get_db, Client, Case, Document
from auth import get_current_user
from models.tenant import tenant_query
from config import settings
from core.template_config import templates, PREFIX, inject_org_context

logger = logging.getLogger(__name__)

UPLOAD_DIR = os.path.join(settings.BASE_DIR, "data", "uploads")

router = APIRouter(tags=["checklist"])


# ============================================================
# CHECKLISTS LIST PAGE
# ============================================================

@router.get("/checklists", response_class=HTMLResponse)
async def list_checklists(
    request: Request,
    visa_type: Optional[str] = None,
    progress_status: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all cases with their checklist progress summary."""
    user = get_current_user(request, db)
    if not user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    from services.checklist_generator import generate_checklist, normalize_visa_type, get_supported_visa_types
    from sqlalchemy import or_

    query = tenant_query(db, Case, request.state.org_id)
    if search:
        sf = f"%{search}%"
        query = query.join(Client, Case.client_id == Client.id).filter(
            or_(Case.case_number.ilike(sf), Case.case_name.ilike(sf),
                Client.first_name.ilike(sf), Client.last_name.ilike(sf))
        )
    if visa_type:
        query = query.filter(Case.visa_type == visa_type)

    cases = query.order_by(Case.created_at.desc()).all()

    # Pre-fetch all documents in one query
    case_ids = [c.id for c in cases]
    all_docs = tenant_query(db, Document, request.state.org_id).filter(Document.case_id.in_(case_ids)).all() if case_ids else []
    docs_by_case = {}
    for doc in all_docs:
        docs_by_case.setdefault(doc.case_id, []).append(doc)

    # Pre-fetch clients in one query (mirrors docs_by_case) — avoids an N+1
    # client lookup inside the loop below.
    client_ids = {c.client_id for c in cases if c.client_id}
    clients_by_id = {
        cl.id: cl
        for cl in tenant_query(db, Client, request.state.org_id)
        .filter(Client.id.in_(client_ids)).all()
    } if client_ids else {}

    checklists = []
    for case in cases:
        vt = normalize_visa_type(case.visa_type)
        if not vt:
            continue
        client = clients_by_id.get(case.client_id)
        checklist = generate_checklist(case.id, vt, docs_by_case.get(case.id, []))
        pct = checklist.progress_percent
        status = "complete" if pct >= 100 else "in_progress" if pct > 0 else "not_started"

        if progress_status and status != progress_status:
            continue

        case_docs = docs_by_case.get(case.id, [])
        docs_with_dates = [d for d in case_docs if d.created_at]
        latest = max(docs_with_dates, key=lambda d: d.created_at) if docs_with_dates else None

        checklists.append({
            "case": case, "client": client, "visa_type": vt,
            "visa_label": checklist.visa_label,
            "progress_percent": pct,
            "total_present": checklist.total_present,
            "total_required": checklist.total_required,
            "status": status,
            "last_updated": latest.created_at if latest else case.created_at,
        })

    return templates.TemplateResponse("app/checklists/list.html", {
        "request": request, "user": user, "PREFIX": PREFIX,
        **inject_org_context(request, user),
        "checklists": checklists, "total": len(checklists),
        "search": search or "", "visa_type": visa_type or "",
        "progress_status": progress_status or "",
        "supported_visa_types": get_supported_visa_types()
    })


@router.get("/checklists/new", response_class=HTMLResponse)
async def select_case_for_checklist(
    request: Request,
    client_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Wizard: Step 1 = select client, Step 2 = select/create case for that client."""
    user = get_current_user(request, db)
    if not user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    from services.checklist_generator import normalize_visa_type, get_supported_visa_types

    selected_client = None
    client_cases = []

    if client_id:
        # Step 2: show cases for this client
        selected_client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
        if selected_client:
            cases = tenant_query(db, Case, request.state.org_id).filter(Case.client_id == client_id).order_by(Case.created_at.desc()).all()
            for case in cases:
                vt = normalize_visa_type(case.visa_type)
                client_cases.append({"case": case, "has_checklist": vt is not None})

    # Step 1: load all clients for selection
    clients = tenant_query(db, Client, request.state.org_id).order_by(Client.first_name.asc(), Client.last_name.asc()).all()

    return templates.TemplateResponse("app/checklists/select_case.html", {
        "request": request, "user": user, "PREFIX": PREFIX,
        **inject_org_context(request, user),
        "clients": clients,
        "selected_client": selected_client,
        "client_cases": client_cases,
        "supported_visa_types": get_supported_visa_types()
    })


# ============================================================
# QUICK CHECKLIST (auto-create case from client)
# ============================================================

class QuickChecklistRequest(BaseModel):
    visa_type: str


@router.post("/api/clients/{client_id}/quick-checklist")
async def quick_checklist(
    request: Request, client_id: int,
    data: QuickChecklistRequest,
    db: Session = Depends(get_db)
):
    """Create a case automatically and redirect to its checklist."""
    try:
        user = get_current_user(request, db)
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")

        client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")

        from services.checklist_generator import normalize_visa_type
        vt = normalize_visa_type(data.visa_type)
        if not vt:
            return JSONResponse({"error": f"Unsupported visa type: {data.visa_type}"}, status_code=400)

        # Check if case with this visa type already exists for client
        existing = tenant_query(db, Case, request.state.org_id).filter(
            Case.client_id == client_id, Case.visa_type == vt
        ).first()
        if existing:
            return JSONResponse({
                "case_id": existing.id,
                "existing": True,
                "redirect": f"{PREFIX}/cases/{existing.id}/checklist"
            })

        # Auto-generate case number
        last_case = tenant_query(db, Case, request.state.org_id).order_by(Case.id.desc()).first()
        next_num = (last_case.id + 1) if last_case else 1
        case_number = f"{settings.CASE_PREFIX}-{next_num:04d}"
        while tenant_query(db, Case, request.state.org_id).filter(Case.case_number == case_number).first():
            next_num += 1
            case_number = f"{settings.CASE_PREFIX}-{next_num:04d}"

        case = Case(
            client_id=client_id,
            case_number=case_number,
            case_name=f"{client.first_name} {client.last_name} - {vt} case",
            visa_type=vt,
            status="intake",
            priority="medium",
        org_id=request.state.org_id)

        # Try to commit - catch race condition on case_number UNIQUE constraint
        try:
            db.add(case)
            db.commit()
            db.refresh(case)

            return JSONResponse({
                "case_id": case.id,
                "case_number": case_number,
                "existing": False,
                "redirect": f"{PREFIX}/cases/{case.id}/checklist"
            })
        except IntegrityError as e:
            db.rollback()
            logger.error(f"Case number conflict for client {client_id}, visa {vt}: {e}")

            # Retry once with incremented number
            next_num += 1
            case_number = f"{settings.CASE_PREFIX}-{next_num:04d}"

            # Create NEW object instead of reusing detached one
            new_case = Case(
                client_id=client_id,
                case_number=case_number,
                case_name=f"{client.first_name} {client.last_name} - {vt} case",
                visa_type=vt,
                status="intake",
                priority="medium"
            )

            try:
                db.add(new_case)
                db.commit()
                db.refresh(new_case)
                logger.info(f"Case number retry successful: {case_number} for client {client_id}")
                return JSONResponse({
                    "case_id": new_case.id,
                    "case_number": case_number,
                    "existing": False,
                    "redirect": f"{PREFIX}/cases/{new_case.id}/checklist"
                })
            except IntegrityError as retry_error:
                db.rollback()
                logger.error(f"Case number conflict retry failed for client {client_id}: {retry_error}")
                return JSONResponse({
                    "error": "Unable to generate unique case number. Please try again."
                }, status_code=500)

    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Unexpected error in quick_checklist for client {client_id}: {e}")
        db.rollback()
        return JSONResponse({
            "error": "An unexpected error occurred. Please try again or contact support."
        }, status_code=500)


# ============================================================
# CASE CHECKLIST HTML PAGE
# ============================================================

@router.get("/cases/{case_id}/checklist", response_class=HTMLResponse)
async def checklist_page(request: Request, case_id: int, db: Session = Depends(get_db)):
    """Render the document checklist page for a case."""
    user = get_current_user(request, db)
    if not user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == case.client_id).first()

    # Generate checklist
    from services.checklist_generator import generate_checklist, normalize_visa_type, get_supported_visa_types
    documents = tenant_query(db, Document, request.state.org_id).filter(Document.case_id == case_id).all()
    visa_type = normalize_visa_type(case.visa_type)
    checklist = generate_checklist(case_id, visa_type, documents)

    return templates.TemplateResponse("app/cases/checklist.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        **inject_org_context(request, user),
        "case": case,
        "client": client,
        "checklist": checklist.to_dict(),
        "supported_visa_types": get_supported_visa_types()
    })


# ============================================================
# API ENDPOINTS
# ============================================================

@router.get("/api/cases/{case_id}/checklist")
async def get_checklist_json(request: Request, case_id: int, db: Session = Depends(get_db)):
    """Return checklist data as JSON."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    from services.checklist_generator import generate_checklist, normalize_visa_type
    documents = tenant_query(db, Document, request.state.org_id).filter(Document.case_id == case_id).all()
    visa_type = normalize_visa_type(case.visa_type)
    checklist = generate_checklist(case_id, visa_type, documents)

    return JSONResponse(checklist.to_dict())


@router.post("/api/cases/{case_id}/checklist/classify")
async def classify_all_documents(request: Request, case_id: int, db: Session = Depends(get_db)):
    """Classify all unclassified documents in a case using multi-LLM chain."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    from services.document_classifier import classify_document, get_exhibit_for_type

    documents = tenant_query(db, Document, request.state.org_id).filter(Document.case_id == case_id).all()
    classified_count = 0
    results = []

    for doc in documents:
        # Classify if no doc_type or doc_type is "other"/"Other Document"
        if not doc.doc_type or doc.doc_type.lower() in ("other", "other document", "outro", ""):
            classification = await classify_document(doc.name or doc.original_filename or "")

            doc.doc_type = classification["doc_type"]
            doc.classification_confidence = classification["confidence"]
            doc.suggested_exhibit = classification["suggested_exhibit"]
            doc.llm_classified = True
            classified_count += 1

            results.append({
                "doc_id": doc.id,
                "name": doc.name,
                "doc_type": classification["doc_type"],
                "confidence": classification["confidence"],
                "method": classification["method"],
                "exhibit": classification["suggested_exhibit"]
            })

    db.commit()

    return JSONResponse({
        "success": True,
        "classified_count": classified_count,
        "total_documents": len(documents),
        "results": results
    })


class ReclassifyRequest(BaseModel):
    doc_type: Optional[str] = None  # If provided, set manually; if None, use LLM


@router.post("/api/documents/{doc_id}/reclassify")
async def reclassify_document(
    request: Request,
    doc_id: int,
    data: ReclassifyRequest = None,
    db: Session = Depends(get_db)
):
    """Reclassify a single document, either manually or via LLM."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    doc = tenant_query(db, Document, request.state.org_id).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if data and data.doc_type:
        # Manual classification
        from services.document_classifier import get_exhibit_for_type
        doc.doc_type = data.doc_type
        doc.suggested_exhibit = get_exhibit_for_type(data.doc_type)
        doc.llm_classified = False
        doc.classification_confidence = 1.0
        method = "manual"
    else:
        # LLM classification
        from services.document_classifier import classify_document
        classification = await classify_document(doc.name or doc.original_filename or "")
        doc.doc_type = classification["doc_type"]
        doc.classification_confidence = classification["confidence"]
        doc.suggested_exhibit = classification["suggested_exhibit"]
        doc.llm_classified = True
        method = classification["method"]

    db.commit()

    return JSONResponse({
        "success": True,
        "doc_id": doc.id,
        "doc_type": doc.doc_type,
        "confidence": doc.classification_confidence,
        "exhibit": doc.suggested_exhibit,
        "method": method
    })


class ExhibitUpdateRequest(BaseModel):
    exhibit: str


@router.patch("/api/documents/{doc_id}/exhibit")
async def update_document_exhibit(
    request: Request,
    doc_id: int,
    data: ExhibitUpdateRequest,
    db: Session = Depends(get_db)
):
    """Manually update the exhibit assignment for a document."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    doc = tenant_query(db, Document, request.state.org_id).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.suggested_exhibit = data.exhibit.upper().strip()
    db.commit()

    return JSONResponse({
        "success": True,
        "doc_id": doc.id,
        "exhibit": doc.suggested_exhibit
    })


@router.post("/api/cases/{case_id}/checklist/upload")
async def upload_to_checklist(
    request: Request,
    case_id: int,
    file: UploadFile = File(...),
    exhibit: str = Form(""),
    doc_type: str = Form(""),
    db: Session = Depends(get_db)
):
    """Upload a document directly from the checklist page with auto-classification."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    import uuid
    ext = os.path.splitext(file.filename)[1] if file.filename else ""
    unique_filename = f"{uuid.uuid4()}{ext}"
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # Auto-classify if no doc_type provided
    classified_type = doc_type
    classified_exhibit = exhibit
    confidence = 1.0
    method = "manual"
    llm_classified = False

    if not doc_type or doc_type.lower() in ("other", "other document", "outro", ""):
        from services.document_classifier import classify_document as classify_doc
        classification = await classify_doc(file.filename or "")
        classified_type = classification["doc_type"]
        classified_exhibit = classification["suggested_exhibit"] or exhibit
        confidence = classification["confidence"]
        method = classification["method"]
        llm_classified = True

    doc = Document(
        name=file.filename or unique_filename,
        doc_type=classified_type,
        status="received",
        file_path=file_path,
        file_size=len(content),
        mime_type=file.content_type,
        client_id=case.client_id,
        case_id=case_id,
        uploaded_by=user.id,
        suggested_exhibit=classified_exhibit.upper() if classified_exhibit else None,
        llm_classified=llm_classified,
        classification_confidence=confidence,
        org_id=request.state.org_id)
    db.add(doc)
    db.commit()

    return JSONResponse({
        "success": True,
        "doc_id": doc.id,
        "name": doc.name,
        "doc_type": classified_type,
        "exhibit": classified_exhibit,
        "confidence": confidence,
        "method": method
    })


@router.post("/api/cases/{case_id}/checklist/export")
async def export_checklist_pdf(request: Request, case_id: int, db: Session = Depends(get_db)):
    """Export checklist as a PDF document."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == case.client_id).first()

    from services.checklist_generator import generate_checklist, normalize_visa_type, EXHIBIT_NAMES
    documents = tenant_query(db, Document, request.state.org_id).filter(Document.case_id == case_id).all()
    visa_type = normalize_visa_type(case.visa_type)
    checklist = generate_checklist(case_id, visa_type, documents)

    # Generate PDF using ReportLab
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from datetime import datetime

        buffer = io.BytesIO()
        doc_pdf = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.75*inch, bottomMargin=0.75*inch)
        styles = getSampleStyleSheet()
        elements = []

        # Title
        title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=16, spaceAfter=6)
        elements.append(Paragraph("Document Checklist", title_style))

        # Case info
        info_style = ParagraphStyle('Info', parent=styles['Normal'], fontSize=10, textColor=colors.grey)
        client_name = f"{client.first_name} {client.last_name}" if client else "Unknown"
        elements.append(Paragraph(f"Client: {client_name} | Case: {case.case_number or case.id} | Visa: {checklist.visa_label}", info_style))
        elements.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Progress: {checklist.progress_percent}%", info_style))
        elements.append(Spacer(1, 12))

        # Status symbols
        STATUS_SYMBOLS = {"present": "YES", "missing": "---", "needs_review": "(?)", "insufficient": "LOW"}

        # Table per exhibit
        checklist_dict = checklist.to_dict()
        for letter_key in sorted(checklist_dict["exhibits"].keys()):
            exhibit = checklist_dict["exhibits"][letter_key]
            if not exhibit["items"]:
                continue

            # Exhibit header
            header_style = ParagraphStyle('ExhibitHeader', parent=styles['Heading3'], fontSize=11, spaceAfter=4)
            elements.append(Paragraph(
                f"Exhibit {letter_key}: {exhibit['name']} ({exhibit['present_count']}/{exhibit['total_count']})",
                header_style
            ))

            # Table data
            table_data = [["Status", "Document", "Type", "Section"]]
            for item in exhibit["items"]:
                status_text = STATUS_SYMBOLS.get(item["status"], "?")
                section_text = item.get("criterion_label", item.get("section", ""))
                table_data.append([status_text, item["label"], item["doc_type"], section_text])

            table = Table(table_data, colWidths=[0.6*inch, 3.2*inch, 1.3*inch, 2.0*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.15, 0.15, 0.15)),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.Color(0.3, 0.3, 0.3)),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.Color(0.95, 0.95, 0.95), colors.white]),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 8))

        # Footer
        footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.grey, alignment=1)
        elements.append(Spacer(1, 20))
        elements.append(Paragraph("Provisional document generated automatically - requires human review", footer_style))
        elements.append(Paragraph(f"{settings.ORG_NAME} - CaseHub", footer_style))

        doc_pdf.build(elements)
        buffer.seek(0)

        filename = f"checklist_{case.case_number or case_id}_{visa_type or 'unknown'}.pdf"
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    except ImportError:
        # Fallback: return JSON if ReportLab not available
        return JSONResponse({
            "error": "ReportLab not installed. PDF export unavailable.",
            "checklist": checklist.to_dict()
        }, status_code=501)
