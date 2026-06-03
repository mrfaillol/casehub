"""
CaseHub - REST API Endpoints
Comprehensive API for React/Frontend consumption
"""
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from pydantic import BaseModel

from models import get_db, User, Client, Case, Document, Task, Reminder, BillingItem, TimeEntry
from auth import get_current_user_api, require_auth_api
from models.tenant import tenant_query
from services.encryption import encrypt_value, decrypt_value, encrypt_client_pii

router = APIRouter(prefix="/api/v1", tags=["api"], dependencies=[Depends(require_auth_api)])

# Pydantic Models for API
class ClientCreate(BaseModel):
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    date_of_birth: Optional[date] = None
    country_of_origin: Optional[str] = None
    ssn: Optional[str] = None
    alien_number: Optional[str] = None
    passport_number: Optional[str] = None
    address: Optional[str] = None
    status: Optional[str] = "active"
    notes: Optional[str] = None

class ClientUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    date_of_birth: Optional[date] = None
    country_of_origin: Optional[str] = None
    ssn: Optional[str] = None
    alien_number: Optional[str] = None
    passport_number: Optional[str] = None
    address: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None

class CaseCreate(BaseModel):
    client_id: int
    case_number: Optional[str] = None
    case_name: Optional[str] = None
    receipt_number: Optional[str] = None
    visa_type: Optional[str] = None
    status: Optional[str] = "intake"
    priority: Optional[str] = "medium"
    application_date: Optional[date] = None
    processing_date: Optional[date] = None
    expiration_date: Optional[date] = None
    case_value: Optional[float] = None
    notes: Optional[str] = None

class CaseUpdate(BaseModel):
    case_number: Optional[str] = None
    case_name: Optional[str] = None
    receipt_number: Optional[str] = None
    visa_type: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    application_date: Optional[date] = None
    processing_date: Optional[date] = None
    expiration_date: Optional[date] = None
    case_value: Optional[float] = None
    amount_paid: Optional[float] = None
    notes: Optional[str] = None

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    case_id: Optional[int] = None
    client_id: Optional[int] = None
    task_type: Optional[str] = None
    status: Optional[str] = "todo"
    priority: Optional[str] = "medium"
    assigned_to: Optional[int] = None
    due_date: Optional[date] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_to: Optional[int] = None
    due_date: Optional[date] = None

# API Response helpers
def client_to_dict(client: Client) -> dict:
    return {
        "id": client.id,
        "first_name": client.first_name,
        "last_name": client.last_name,
        "full_name": f"{client.first_name} {client.last_name}",
        "email": client.email,
        "phone": client.phone,
        "whatsapp": client.whatsapp,
        "date_of_birth": client.date_of_birth.isoformat() if client.date_of_birth else None,
        "country_of_origin": client.country_of_origin,
        "ssn": client.decrypted_ssn,
        "alien_number": client.decrypted_alien_number,
        "passport_number": client.decrypted_passport_number,
        "address": client.address,
        "status": client.status,
        "notes": client.notes,
        "created_at": client.created_at.isoformat() if client.created_at else None,
        "updated_at": client.updated_at.isoformat() if client.updated_at else None
    }

def case_to_dict(case: Case) -> dict:
    application_date = getattr(case, "application_date", None)
    processing_date = getattr(case, "processing_date", None)
    expiration_date = getattr(case, "expiration_date", None)
    return {
        "id": case.id,
        "client_id": case.client_id,
        "case_number": case.case_number,
        "case_name": case.case_name,
        "receipt_number": case.receipt_number,
        "visa_type": case.visa_type,
        "status": case.status,
        "priority": case.priority,
        "application_date": application_date.isoformat() if application_date else None,
        "processing_date": processing_date.isoformat() if processing_date else None,
        "expiration_date": expiration_date.isoformat() if expiration_date else None,
        "case_value": float(case.case_value) if case.case_value else None,
        "amount_paid": float(case.amount_paid) if case.amount_paid else None,
        "notes": case.notes,
        "created_at": case.created_at.isoformat() if case.created_at else None,
        "updated_at": case.updated_at.isoformat() if case.updated_at else None
    }

def task_to_dict(task: Task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "case_id": task.case_id,
        "client_id": task.client_id,
        "task_type": task.task_type,
        "status": task.status,
        "priority": task.priority,
        "assigned_to": task.assigned_to,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else None
    }

def document_to_dict(doc: Document) -> dict:
    return {
        "id": doc.id,
        "client_id": doc.client_id,
        "case_id": doc.case_id,
        "name": doc.name,
        "document_type": getattr(doc, "document_type", None) or getattr(doc, "doc_type", None),
        "status": doc.status,
        "file_path": doc.file_path,
        "file_size": doc.file_size,
        "mime_type": doc.mime_type,
        "expiration_date": doc.expiration_date.isoformat() if doc.expiration_date else None,
        "notes": doc.notes,
        "uploaded_by": doc.uploaded_by,
        "created_at": doc.created_at.isoformat() if doc.created_at else None
    }

# ==================== DASHBOARD ====================

@router.get("/dashboard/stats")
async def get_dashboard_stats(
    request: Request,
    db: Session = Depends(get_db)):
    """Get dashboard statistics"""
    total_clients = tenant_query(db, Client, request.state.org_id).count()
    total_cases = tenant_query(db, Case, request.state.org_id).count()
    active_cases = tenant_query(db, Case, request.state.org_id).filter(Case.status.notin_(["approved", "denied", "closed"])).count()
    total_documents = tenant_query(db, Document, request.state.org_id).count()
    pending_tasks = tenant_query(db, Task, request.state.org_id).filter(Task.status != "completed").count()
    overdue_tasks = tenant_query(db, Task, request.state.org_id).filter(
        Task.status != "completed",
        Task.due_date < date.today()
    ).count()

    # Cases by status
    case_status_query = tenant_query(db, Case, request.state.org_id).with_entities(Case.status, func.count(Case.id)).group_by(Case.status).all()
    cases_by_status = {status: count for status, count in case_status_query}

    # Cases by visa type
    visa_type_query = tenant_query(db, Case, request.state.org_id).with_entities(Case.visa_type, func.count(Case.id)).filter(
        Case.visa_type.isnot(None),
        Case.visa_type != ""
    ).group_by(Case.visa_type).order_by(func.count(Case.id).desc()).limit(10).all()
    cases_by_visa = {vt[0]: vt[1] for vt in visa_type_query}

    return {
        "stats": {
            "total_clients": total_clients,
            "total_cases": total_cases,
            "active_cases": active_cases,
            "total_documents": total_documents,
            "pending_tasks": pending_tasks,
            "overdue_tasks": overdue_tasks
        },
        "charts": {
            "cases_by_status": cases_by_status,
            "cases_by_visa_type": cases_by_visa
        }
    }

# ==================== CLIENTS ====================

@router.get("/clients")
async def list_clients(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all clients with pagination and search"""
    query = tenant_query(db, Client, request.state.org_id)

    if search:
        search_filter = f"%{search}%"
        query = query.filter(or_(
            Client.first_name.ilike(search_filter),
            Client.last_name.ilike(search_filter),
            Client.email.ilike(search_filter),
            Client.phone.ilike(search_filter)
        ))

    if status:
        query = query.filter(Client.status == status)

    total = query.count()
    clients = query.order_by(Client.created_at.desc()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": [client_to_dict(c) for c in clients]
    }

@router.get("/clients/{client_id}")
async def get_client(client_id: int, 
    request: Request,
    db: Session = Depends(get_db)):
    """Get a single client by ID"""
    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Include related data
    cases = tenant_query(db, Case, request.state.org_id).filter(Case.client_id == client_id).all()
    documents = tenant_query(db, Document, request.state.org_id).filter(Document.client_id == client_id).all()
    tasks = tenant_query(db, Task, request.state.org_id).filter(Task.client_id == client_id).all()

    return {
        **client_to_dict(client),
        "cases": [case_to_dict(c) for c in cases],
        "documents": [document_to_dict(d) for d in documents],
        "tasks": [task_to_dict(t) for t in tasks]
    }

@router.post("/clients")
async def create_client(client_data: ClientCreate, 
    request: Request,
    db: Session = Depends(get_db)):
    """Create a new client"""
    data = client_data.model_dump()
    encrypt_client_pii(data)
    client = Client(**data, org_id=request.state.org_id)
    db.add(client)
    db.commit()
    db.refresh(client)
    return client_to_dict(client)

@router.put("/clients/{client_id}")
async def update_client(client_id: int, client_data: ClientUpdate, 
    request: Request,
    db: Session = Depends(get_db)):
    """Update an existing client"""
    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    update_data = client_data.model_dump(exclude_unset=True)
    encrypt_client_pii(update_data)
    for key, value in update_data.items():
        setattr(client, key, value)

    client.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(client)
    return client_to_dict(client)

@router.delete("/clients/{client_id}")
async def delete_client(client_id: int, 
    request: Request,
    db: Session = Depends(get_db)):
    """Delete a client"""
    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    db.delete(client)
    db.commit()
    return {"message": "Client deleted successfully"}

# ==================== CASES ====================

@router.get("/cases")
async def list_cases(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = None,
    status: Optional[str] = None,
    client_id: Optional[int] = None,
    visa_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all cases with pagination and filters"""
    query = tenant_query(db, Case, request.state.org_id)

    if search:
        search_filter = f"%{search}%"
        query = query.filter(or_(
            Case.case_number.ilike(search_filter),
            Case.case_name.ilike(search_filter),
            Case.receipt_number.ilike(search_filter)
        ))

    if status:
        query = query.filter(Case.status == status)
    if client_id:
        query = query.filter(Case.client_id == client_id)
    if visa_type:
        query = query.filter(Case.visa_type == visa_type)

    total = query.count()
    cases = query.order_by(Case.created_at.desc()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": [case_to_dict(c) for c in cases]
    }

@router.get("/cases/{case_id}")
async def get_case(case_id: int, 
    request: Request,
    db: Session = Depends(get_db)):
    """Get a single case by ID"""
    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Include client info
    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == case.client_id).first()
    documents = tenant_query(db, Document, request.state.org_id).filter(Document.case_id == case_id).all()
    tasks = tenant_query(db, Task, request.state.org_id).filter(Task.case_id == case_id).all()
    billing = tenant_query(db, BillingItem, request.state.org_id).filter(BillingItem.case_id == case_id).all()

    return {
        **case_to_dict(case),
        "client": client_to_dict(client) if client else None,
        "documents": [document_to_dict(d) for d in documents],
        "tasks": [task_to_dict(t) for t in tasks],
        "billing_items": [{
            "id": b.id,
            "description": b.description,
            "amount": float(b.amount) if b.amount else 0,
            "item_type": b.item_type,
            "status": b.status,
            "due_date": b.due_date.isoformat() if b.due_date else None
        } for b in billing]
    }

@router.post("/cases")
async def create_case(case_data: CaseCreate, 
    request: Request,
    db: Session = Depends(get_db)):
    """Create a new case"""
    # Verify client exists
    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == case_data.client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    case = Case(**case_data.model_dump(), org_id=request.state.org_id)
    db.add(case)
    db.commit()
    db.refresh(case)
    return case_to_dict(case)

@router.put("/cases/{case_id}")
async def update_case(case_id: int, case_data: CaseUpdate, 
    request: Request,
    db: Session = Depends(get_db)):
    """Update an existing case"""
    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    update_data = case_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(case, key, value)

    case.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(case)
    return case_to_dict(case)

@router.delete("/cases/{case_id}")
async def delete_case(case_id: int, 
    request: Request,
    db: Session = Depends(get_db)):
    """Delete a case"""
    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    db.delete(case)
    db.commit()
    return {"message": "Case deleted successfully"}

# ==================== TASKS ====================

@router.get("/tasks")
async def list_tasks(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = None,
    case_id: Optional[int] = None,
    client_id: Optional[int] = None,
    assigned_to: Optional[int] = None,
    priority: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all tasks with pagination and filters"""
    query = tenant_query(db, Task, request.state.org_id)

    if status:
        query = query.filter(Task.status == status)
    if case_id:
        query = query.filter(Task.case_id == case_id)
    if client_id:
        query = query.filter(Task.client_id == client_id)
    if assigned_to:
        query = query.filter(Task.assigned_to == assigned_to)
    if priority:
        query = query.filter(Task.priority == priority)

    total = query.count()
    tasks = query.order_by(Task.due_date.asc().nullslast()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": [task_to_dict(t) for t in tasks]
    }

@router.get("/tasks/{task_id}")
async def get_task(task_id: int, 
    request: Request,
    db: Session = Depends(get_db)):
    """Get a single task by ID"""
    task = tenant_query(db, Task, request.state.org_id).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task_to_dict(task)

@router.post("/tasks")
async def create_task(task_data: TaskCreate, 
    request: Request,
    db: Session = Depends(get_db)):
    """Create a new task"""
    task = Task(**task_data.model_dump(), org_id=request.state.org_id)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task_to_dict(task)

@router.put("/tasks/{task_id}")
async def update_task(task_id: int, task_data: TaskUpdate, 
    request: Request,
    db: Session = Depends(get_db)):
    """Update an existing task"""
    task = tenant_query(db, Task, request.state.org_id).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    update_data = task_data.model_dump(exclude_unset=True)

    # Handle completion
    if update_data.get("status") == "completed" and task.status != "completed":
        task.completed_at = datetime.utcnow()

    for key, value in update_data.items():
        setattr(task, key, value)

    db.commit()
    db.refresh(task)
    return task_to_dict(task)

@router.delete("/tasks/{task_id}")
async def delete_task(task_id: int, 
    request: Request,
    db: Session = Depends(get_db)):
    """Delete a task"""
    task = tenant_query(db, Task, request.state.org_id).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    db.delete(task)
    db.commit()
    return {"message": "Task deleted successfully"}

# ==================== DOCUMENTS ====================

@router.get("/documents")
async def list_documents(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    case_id: Optional[int] = None,
    client_id: Optional[int] = None,
    document_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all documents with pagination and filters"""
    query = tenant_query(db, Document, request.state.org_id)

    if case_id:
        query = query.filter(Document.case_id == case_id)
    if client_id:
        query = query.filter(Document.client_id == client_id)
    if document_type:
        query = query.filter(Document.document_type == document_type)

    total = query.count()
    documents = query.order_by(Document.created_at.desc()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": [document_to_dict(d) for d in documents]
    }

@router.get("/documents/{document_id}")
async def get_document(document_id: int, 
    request: Request,
    db: Session = Depends(get_db)):
    """Get a single document by ID"""
    doc = tenant_query(db, Document, request.state.org_id).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return document_to_dict(doc)

# ==================== USERS ====================

@router.get("/users")
async def list_users(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """List all users"""
    query = tenant_query(db, User, request.state.org_id)
    total = query.count()
    users = query.offset(skip).limit(limit).all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": [{
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "user_type": u.user_type,
            "enabled": u.enabled,
            "created_at": u.created_at.isoformat() if u.created_at else None
        } for u in users]
    }

# ==================== LOOKUP / REFERENCE DATA ====================

@router.get("/lookup/visa-types")
async def get_visa_types():
    """Get list of common visa types"""
    return {
        "visa_types": [
            "EB-1A", "EB-1B", "EB-1C", "EB-2", "EB-2 NIW", "EB-3",
            "H-1B", "H-2A", "H-2B", "L-1A", "L-1B", "O-1A", "O-1B",
            "F-1", "J-1", "K-1", "K-3",
            "IR-1", "IR-2", "CR-1", "F2A", "F2B",
            "Asylum", "TPS", "DACA", "U Visa", "T Visa",
            "Naturalization", "Green Card Renewal",
            "Other"
        ]
    }

@router.get("/lookup/case-statuses")
async def get_case_statuses():
    """Get list of case statuses"""
    return {
        "statuses": [
            {"value": "intake", "label": "Intake", "color": "secondary"},
            {"value": "document_collection", "label": "Document Collection", "color": "info"},
            {"value": "drafting", "label": "Drafting", "color": "primary"},
            {"value": "review", "label": "Review", "color": "warning"},
            {"value": "filed", "label": "Filed", "color": "primary"},
            {"value": "rfe", "label": "RFE", "color": "warning"},
            {"value": "approved", "label": "Approved", "color": "success"},
            {"value": "denied", "label": "Denied", "color": "danger"},
            {"value": "closed", "label": "Closed", "color": "secondary"}
        ]
    }

@router.get("/lookup/task-priorities")
async def get_task_priorities():
    """Get list of task priorities"""
    return {
        "priorities": [
            {"value": "low", "label": "Low", "color": "secondary"},
            {"value": "medium", "label": "Medium", "color": "primary"},
            {"value": "high", "label": "High", "color": "warning"},
            {"value": "urgent", "label": "Urgent", "color": "danger"}
        ]
    }

@router.get("/lookup/document-types")
async def get_document_types():
    """Get list of document types"""
    return {
        "document_types": [
            "Passport", "I-94", "Visa", "Birth Certificate", "Marriage Certificate",
            "Diploma", "Transcript", "Employment Letter", "Recommendation Letter",
            "Tax Returns", "W-2", "Pay Stubs", "Bank Statement",
            "Photos", "Medical Exam", "Police Clearance",
            "USCIS Form", "Receipt Notice", "Approval Notice", "RFE Response",
            "Other"
        ]
    }

# API Documentation Page
@router.get("/docs-page")
async def api_docs_page(request: Request, db: Session = Depends(get_db)):
    """API Documentation Page.

    Renders ``templates/api/docs.html`` (extends ``base.html``). The template
    relies on Jinja2 globals injected by ``core/template_config.py`` —
    ``product``, ``PREFIX``, ``asset_url``, ``org_name``, ``org_logo``,
    ``org_theme_*``, ``brand_kit_fallback_favicon_url`` — and on per-request
    org overrides from ``inject_org_context(request)``. The previous version
    of this handler built its own ``Jinja2Templates(directory="templates")``
    instance, which had **no globals configured**, so ``base.html`` rendered
    with undefined ``product``/``org_name``/etc. and raised on a missing
    callable (``asset_url`` is invoked as a function in ``base.html``). That
    pattern is the audit-#514 ``HTTP 500`` family for ``/casehub/api/v1/docs-page``.

    This handler now uses the **shared** ``templates`` instance from
    ``core.template_config`` and merges ``inject_org_context`` into the
    response context — the same pattern every other HTML route in the app
    already uses.
    """
    from auth import get_current_user
    from fastapi.responses import RedirectResponse
    from config import settings
    from core.template_config import templates, inject_org_context

    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{settings.PREFIX}/login", status_code=302)

    ctx = {
        "request": request,
        "user": user,
        "PREFIX": settings.PREFIX,
    }
    # Org-level overrides + ui_theme. Safe when no org is resolved (returns
    # just {"ui_theme": ...}, falling back to the Jinja2 globals defaults).
    ctx.update(inject_org_context(request, user))
    return templates.TemplateResponse("app/api/docs.html", ctx)
