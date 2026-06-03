"""
CaseHub - E-Filing Routes
Manage e-filing submissions to USCIS.
"""
from typing import Optional, List
import json

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, User, Case, Client, Document
from auth import get_current_user
from models.tenant import tenant_query
from services.efiling_service import efiling_service, CREATE_EFILING_TABLE, EFilingStatus
from config import settings

PREFIX = settings.PREFIX

router = APIRouter(prefix="/efiling", tags=["efiling"])
templates = Jinja2Templates(directory="templates")


def ensure_tables(db: Session):
    """Ensure e-filing tables exist."""
    try:
        db.execute(text(CREATE_EFILING_TABLE))
        db.commit()
    except Exception as e:
        db.rollback()


@router.get("", response_class=HTMLResponse)
async def efiling_dashboard(
    request: Request,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """E-Filing dashboard showing all submissions."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    # Get submissions with filters
    query = """
        SELECT e.*, c.case_number, c.case_name, c.visa_type,
               cl.first_name, cl.last_name
        FROM efiling_submissions e
        LEFT JOIN cases c ON e.case_id = c.id
        LEFT JOIN clients cl ON c.client_id = cl.id
    """
    params = {}

    if status:
        query += " WHERE e.status = :status"
        params["status"] = status

    query += " ORDER BY e.created_at DESC"

    try:
        result = db.execute(text(query), params)
        submissions = result.fetchall()
    except Exception:
        db.rollback()
        submissions = []

    # Get status counts
    try:
        counts_result = db.execute(text("""
            SELECT status, COUNT(*) as count
            FROM efiling_submissions
            GROUP BY status
        """))
        status_counts = {row.status: row.count for row in counts_result.fetchall()}
    except Exception:
        db.rollback()
        status_counts = {}

    return templates.TemplateResponse("app/efiling/dashboard.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "submissions": submissions,
        "status_counts": status_counts,
        "selected_status": status,
        "statuses": [s.value for s in EFilingStatus]
    })


@router.get("/new", response_class=HTMLResponse)
async def new_submission(
    request: Request,
    case_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Create new e-filing submission."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    # Get cases
    cases = tenant_query(db, Case, request.state.org_id).order_by(Case.created_at.desc()).all()

    # Get selected case and its documents
    selected_case = None
    documents = []
    client = None

    if case_id:
        selected_case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
        if selected_case:
            client = tenant_query(db, Client, request.state.org_id).filter(Client.id == selected_case.client_id).first()
            documents = tenant_query(db, Document, request.state.org_id).filter(Document.case_id == case_id).all()

    # Get service centers and filing types
    service_centers = efiling_service.get_service_centers()
    filing_types = efiling_service.get_filing_types()

    return templates.TemplateResponse("app/efiling/create.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "cases": cases,
        "selected_case": selected_case,
        "client": client,
        "documents": documents,
        "service_centers": service_centers,
        "filing_types": filing_types
    })


@router.post("/create")
async def create_submission(
    request: Request,
    case_id: int = Form(...),
    form_number: str = Form(...),
    filing_type: str = Form("initial"),
    service_center: str = Form(None),
    document_ids: str = Form("[]"),
    premium_processing: bool = Form(False),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Create a new e-filing submission."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ensure_tables(db)

    # Parse document IDs
    try:
        doc_ids = json.loads(document_ids)
    except Exception:
        db.rollback()
        doc_ids = []

    # Get documents — batch the per-id lookup (N+1 -> 1 SELECT) but iterate
    # `doc_ids` so the resulting list preserves the submission order the user
    # picked. `docs_by_id.get(...)` quietly drops ids that don't resolve, same
    # as the original `if doc:` skip.
    docs_by_id = {
        d.id: d
        for d in tenant_query(db, Document, request.state.org_id)
        .filter(Document.id.in_(doc_ids)).all()
    } if doc_ids else {}
    documents_list = []
    for doc_id in doc_ids:
        doc = docs_by_id.get(doc_id)
        if doc:
            documents_list.append({
                "id": doc.id,
                "name": doc.name,
                # The Document model has `doc_type`, not `type` — accessing
                # `.type` raised AttributeError -> HTTP 500 on every hit
                # whenever the loop found at least one matching document.
                "type": doc.doc_type,
                "file_path": doc.file_path
            })

    # Calculate fees
    fees = efiling_service.calculate_fees(form_number, premium_processing, True)

    # Create submission
    submission = efiling_service.create_submission(
        case_id=case_id,
        form_number=form_number,
        filing_type=filing_type,
        service_center=service_center,
        documents=documents_list,
        notes=notes
    )

    try:
        db.execute(text("""
            INSERT INTO efiling_submissions
            (submission_id, case_id, form_number, filing_type, service_center, status, documents, fees, notes, created_by)
            VALUES (:sid, :case_id, :form, :type, :center, :status, :docs, :fees, :notes, :uid)
        """), {
            "sid": submission["submission_id"],
            "case_id": case_id,
            "form": form_number.upper(),
            "type": filing_type,
            "center": service_center,
            "status": EFilingStatus.DRAFT,
            "docs": json.dumps(documents_list),
            "fees": json.dumps(fees),
            "notes": notes,
            "uid": user.id
        })
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/efiling/{submission['submission_id']}", status_code=302)


@router.get("/{submission_id}", response_class=HTMLResponse)
async def view_submission(
    request: Request,
    submission_id: str,
    db: Session = Depends(get_db)
):
    """View e-filing submission details."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    try:
        result = db.execute(text("""
            SELECT e.*, c.case_number, c.case_name, c.visa_type,
                   cl.first_name, cl.last_name, cl.email,
                   u.name as creator_name
            FROM efiling_submissions e
            LEFT JOIN cases c ON e.case_id = c.id
            LEFT JOIN clients cl ON c.client_id = cl.id
            LEFT JOIN users u ON e.created_by = u.id
            WHERE e.submission_id = :sid
        """), {"sid": submission_id})
        submission = result.fetchone()

        if not submission:
            raise HTTPException(status_code=404, detail="Submission not found")

        # Get history
        history_result = db.execute(text("""
            SELECT h.*, u.name as user_name
            FROM efiling_history h
            LEFT JOIN users u ON h.created_by = u.id
            WHERE h.submission_id = (SELECT id FROM efiling_submissions WHERE submission_id = :sid)
            ORDER BY h.created_at DESC
        """), {"sid": submission_id})
        history = history_result.fetchall()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Parse JSON fields
    documents = json.loads(submission.documents) if submission.documents else []
    fees = json.loads(submission.fees) if submission.fees else {}

    # Get validation
    validation = efiling_service.validate_submission({
        "form_number": submission.form_number,
        "case_id": submission.case_id,
        "documents": documents,
        "service_center": submission.service_center
    })

    # Get processing time estimate
    processing_time = efiling_service.get_estimated_processing_time(submission.form_number)

    return templates.TemplateResponse("app/efiling/view.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "submission": submission,
        "documents": documents,
        "fees": fees,
        "history": history,
        "validation": validation,
        "processing_time": processing_time,
        "service_centers": efiling_service.get_service_centers()
    })


@router.post("/{submission_id}/update-status")
async def update_status(
    request: Request,
    submission_id: str,
    status: str = Form(...),
    receipt_number: str = Form(None),
    confirmation_number: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Update submission status."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ensure_tables(db)

    try:
        # Get current status
        result = db.execute(text("SELECT id, status FROM efiling_submissions WHERE submission_id = :sid"),
                           {"sid": submission_id})
        current = result.fetchone()

        if not current:
            raise HTTPException(status_code=404, detail="Submission not found")

        old_status = current.status

        # Update status -- use explicit conditional SQL branches instead of dynamic f-string
        params = {
            "sid": submission_id,
            "status": status,
            "receipt": receipt_number or None,
            "confirm": confirmation_number or None,
        }

        if status == EFilingStatus.SUBMITTED:
            db.execute(text("""
                UPDATE efiling_submissions
                SET status = :status, updated_at = NOW(), submitted_at = NOW(),
                    receipt_number = COALESCE(:receipt, receipt_number),
                    confirmation_number = COALESCE(:confirm, confirmation_number)
                WHERE submission_id = :sid
            """), params)
        elif status == EFilingStatus.ACCEPTED:
            db.execute(text("""
                UPDATE efiling_submissions
                SET status = :status, updated_at = NOW(), accepted_at = NOW(),
                    receipt_number = COALESCE(:receipt, receipt_number),
                    confirmation_number = COALESCE(:confirm, confirmation_number)
                WHERE submission_id = :sid
            """), params)
        else:
            db.execute(text("""
                UPDATE efiling_submissions
                SET status = :status, updated_at = NOW(),
                    receipt_number = COALESCE(:receipt, receipt_number),
                    confirmation_number = COALESCE(:confirm, confirmation_number)
                WHERE submission_id = :sid
            """), params)

        # Add history entry
        db.execute(text("""
            INSERT INTO efiling_history (submission_id, action, old_status, new_status, details, created_by)
            VALUES (:sub_id, :action, :old, :new, :details, :uid)
        """), {
            "sub_id": current.id,
            "action": f"Status changed from {old_status} to {status}",
            "old": old_status,
            "new": status,
            "details": notes,
            "uid": user.id
        })

        db.commit()

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/efiling/{submission_id}", status_code=302)


@router.get("/{submission_id}/cover-letter")
async def generate_cover_letter(
    request: Request,
    submission_id: str,
    db: Session = Depends(get_db)
):
    """Generate cover letter for submission."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        result = db.execute(text("""
            SELECT e.*, c.case_number, c.case_name, c.visa_type,
                   cl.first_name, cl.last_name
            FROM efiling_submissions e
            LEFT JOIN cases c ON e.case_id = c.id
            LEFT JOIN clients cl ON c.client_id = cl.id
            WHERE e.submission_id = :sid
        """), {"sid": submission_id})
        submission = result.fetchone()

        if not submission:
            raise HTTPException(status_code=404, detail="Submission not found")

        documents = json.loads(submission.documents) if submission.documents else []

        submission_dict = {
            "submission_id": submission.submission_id,
            "form_number": submission.form_number,
            "filing_type": submission.filing_type,
            "service_center": submission.service_center,
            "documents": documents
        }

        case_data = {
            "case_number": submission.case_number,
            "case_name": submission.case_name,
            "visa_type": submission.visa_type,
            "employer_name": getattr(submission, 'employer_name', None)
        }

        client_data = {
            "first_name": submission.first_name,
            "last_name": submission.last_name
        }

        letter = efiling_service.generate_cover_letter(submission_dict, case_data, client_data)

        return Response(
            content=letter,
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename=cover_letter_{submission_id}.txt"}
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{submission_id}/delete")
async def delete_submission(
    request: Request,
    submission_id: str,
    db: Session = Depends(get_db)
):
    """Delete a submission."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        db.execute(text("DELETE FROM efiling_submissions WHERE submission_id = :sid"),
                   {"sid": submission_id})
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/efiling", status_code=302)


@router.get("/api/fees/{form_number}", response_class=JSONResponse)
async def get_fees(
    request: Request,
    form_number: str,
    premium: bool = False,
    biometric: bool = True,
    db: Session = Depends(get_db)
):
    """API: Get filing fees for a form."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})

    fees = efiling_service.calculate_fees(form_number, premium, biometric)
    return JSONResponse(content=fees)


@router.get("/api/processing-time/{form_number}", response_class=JSONResponse)
async def get_processing_time(
    request: Request,
    form_number: str,
    db: Session = Depends(get_db)
):
    """API: Get processing time estimates."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})

    times = efiling_service.get_estimated_processing_time(form_number)
    return JSONResponse(content=times)
