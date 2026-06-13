"""
CaseHub - Case Routes
Enhanced with Case Activities (Trigger Automation)
"""
from core.form_utils import form_int, form_float
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import or_, text
from typing import Optional
from datetime import datetime, date, timedelta
import logging

logger = logging.getLogger(__name__)

from models import get_db, Client, Case, User
from auth import get_current_user
from models.tenant import tenant_query
from routes.custom_fields import get_custom_fields_for_entity, save_custom_fields_from_form
try:
    from services.encryption import encrypt_value
except ImportError:  # encryption is optional on some builds
    def encrypt_value(v):
        return v

# Roles allowed to edit deadline/date fields inline (vencimento de prazos).
# Cargos: ADMIN e ATTORNEY (advogado). case_worker/paralegal são read-only nessas células.
DEADLINE_ROLES = {"admin", "attorney"}
# Date-typed fields on Case that count as "prazos" (deadline-gated).
DEADLINE_FIELDS = {"expiration_date", "priority_date", "filing_date"}
# Fields editable inline from the list view (whitelist — no arbitrary column writes).
INLINE_EDITABLE_FIELDS = {
    "case_number", "case_name", "receipt_number", "visa_type",
    "status", "priority", "numero_processo", "tipo_acao",
    "filing_date", "priority_date", "expiration_date",
}

# Import triggers service for automation
try:
    from services.triggers_service import triggers_service, TriggerEvent
    TRIGGERS_ENABLED = True
except ImportError:
    TRIGGERS_ENABLED = False

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/cases", tags=["cases"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py

def parse_date(date_str: str):
    """Parse date string to date object"""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None

def fire_triggers(db: Session, case_id: int, event: str, event_data: dict):
    """Fire triggers for a case event"""
    if not TRIGGERS_ENABLED:
        return []
    try:
        executed = triggers_service.evaluate_triggers(db, case_id, event, event_data)
        return executed
    except Exception as e:
        logger.error("Trigger error: %s", e)
        return []

@router.get("", response_class=HTMLResponse)
async def list_cases(
    request: Request,
    search: Optional[str] = None,
    status: Optional[str] = None,
    visa_type: Optional[str] = None,
    page: int = 1,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    query = tenant_query(db, Case, request.state.org_id)
    
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            or_(
                Case.case_number.ilike(search_filter),
                Case.case_name.ilike(search_filter),
                Case.receipt_number.ilike(search_filter)
            )
        )
    
    if status:
        query = query.filter(Case.status == status)
    if visa_type:
        query = query.filter(Case.visa_type == visa_type)
    
    total = query.count()
    per_page = 20
    cases = query.order_by(Case.created_at.desc()).offset((page-1)*per_page).limit(per_page).all()
    
    return templates.TemplateResponse("app/cases/list.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "cases": cases,
        "total": total,
        "page": page,
        "per_page": per_page,
        "search": search or "",
        "status": status or "",
        "visa_type": visa_type or ""
    })

@router.get("/new", response_class=HTMLResponse)
async def new_case(request: Request, client_id: Optional[int] = None, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    clients = tenant_query(db, Client, request.state.org_id).order_by(Client.first_name).all()
    selected_client = None
    if client_id:
        selected_client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    
    try:
        custom_fields = get_custom_fields_for_entity(db, "case")
    except Exception as e:
        logger.warning("Could not load custom field definitions: %s", e)
        db.rollback()
        custom_fields = []

    return templates.TemplateResponse("app/cases/form.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "case": None,
        "clients": clients,
        "selected_client": selected_client,
        "action": "Create",
        "custom_fields": custom_fields
    })

@router.post("/new")
async def create_case(
    request: Request,
    client_id: int = Form(...),
    case_number: str = Form(None),
    case_name: str = Form(None),
    receipt_number: str = Form(None),
    visa_type: str = Form(None),
    status: str = Form("intake"),
    priority: str = Form("medium"),
    filing_date: str = Form(None),
    priority_date: str = Form(None),
    expiration_date: str = Form(None),
    case_value: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Convert form strings to proper types
    case_value = form_float(case_value)

    case = Case(
        client_id=client_id,
        case_number=case_number,
        case_name=case_name,
        receipt_number=receipt_number,
        visa_type=visa_type,
        status=status,
        priority=priority,
        filing_date=parse_date(filing_date),
        priority_date=parse_date(priority_date),
        expiration_date=parse_date(expiration_date),
        case_value=case_value,
        notes=notes,
        org_id=request.state.org_id)
    db.add(case)
    db.commit()
    db.refresh(case)

    # Save custom fields
    form_data = await request.form()
    save_custom_fields_from_form(db, "case", case.id, dict(form_data))
    
    # Fire CASE_CREATED trigger
    fire_triggers(db, case.id, "case_created", {
        "status": status,
        "visa_type": visa_type,
        "priority": priority
    })
    
    return RedirectResponse(url=f"{PREFIX}/cases/{case.id}", status_code=302)

@router.get("/{case_id}", response_class=HTMLResponse)
async def view_case(request: Request, case_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    try:
        return await _view_case_impl(request, case_id, db, user)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error("Case detail error for case %d: %s\n%s", case_id, e, tb)
        return HTMLResponse(
            f"<h2>Erro ao carregar processo #{case_id}</h2><pre>{tb}</pre>",
            status_code=500
        )


async def _view_case_impl(request: Request, case_id: int, db: Session, user):
    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == case.client_id).first()
    try:
        custom_fields = get_custom_fields_for_entity(db, "case", case_id)
    except Exception as e:
        logger.warning("Could not load custom fields for case %d: %s", case_id, e)
        db.rollback()
        custom_fields = []

    # --- Extra context for Lite product ---
    product = getattr(getattr(request, "app", None), "state", None)
    product = getattr(product, "product", "immigration") if product else "immigration"

    extra_ctx = {}
    if product == "lite":
        org_id = request.state.org_id
        hoje = date.today()

        # 1. Prazos linked to this case
        try:
            prazos_rows = db.execute(text("""
                SELECT p.id, p.tipo, p.data_vencimento, p.status, p.responsavel,
                       p.data_intimacao, p.descricao
                FROM prazos_processuais p
                WHERE p.case_id = :case_id AND p.org_id = :org_id
                ORDER BY p.data_vencimento ASC
            """), {"case_id": case_id, "org_id": org_id}).fetchall()

            alerta_7dias = hoje + timedelta(days=7)
            prazos = []
            for row in prazos_rows:
                venc = row.data_vencimento
                urgencia = ""
                if row.status not in ("concluido", "perdido") and isinstance(venc, date):
                    if venc < hoje:
                        urgencia = "vencido"
                    elif venc <= alerta_7dias:
                        urgencia = "proximo"
                prazos.append({
                    "id": row.id,
                    "tipo": row.tipo,
                    "data_vencimento": venc,
                    "status": row.status,
                    "responsavel": row.responsavel or "-",
                    "descricao": row.descricao or "",
                    "urgencia": urgencia,
                })
            extra_ctx["prazos"] = prazos
        except Exception as e:
            logger.warning("Could not load prazos for case %d: %s", case_id, e)
            extra_ctx["prazos"] = []

        # 2. Financial summary (billing_items + invoices)
        try:
            fin = db.execute(text("""
                SELECT
                    COALESCE(SUM(CASE WHEN item_type != 'payment' THEN amount ELSE 0 END), 0) AS total_honorarios,
                    COALESCE(SUM(CASE WHEN item_type = 'payment' THEN amount ELSE 0 END), 0) AS total_pagamentos
                FROM billing_items
                WHERE case_id = :case_id AND org_id = :org_id
            """), {"case_id": case_id, "org_id": org_id}).fetchone()

            recent_items = db.execute(text("""
                SELECT description, amount, item_type, status, created_at
                FROM billing_items
                WHERE case_id = :case_id AND org_id = :org_id
                ORDER BY created_at DESC
                LIMIT 10
            """), {"case_id": case_id, "org_id": org_id}).fetchall()

            total_h = float(fin.total_honorarios) if fin else 0
            total_p = float(fin.total_pagamentos) if fin else 0
            extra_ctx["financeiro"] = {
                "total_honorarios": total_h,
                "total_pagamentos": total_p,
                "saldo": total_h - total_p,
                "items": [{
                    "description": r.description,
                    "amount": float(r.amount),
                    "item_type": r.item_type,
                    "status": r.status,
                    "created_at": r.created_at,
                } for r in recent_items]
            }
        except Exception as e:
            logger.warning("Could not load financeiro for case %d: %s", case_id, e)
            extra_ctx["financeiro"] = {"total_honorarios": 0, "total_pagamentos": 0, "saldo": 0, "items": []}

        # 3. Document checklist progress
        if case.tipo_acao:
            try:
                from services.checklists_br import get_checklist
                checklist = get_checklist(case.tipo_acao)
                total_docs = len(checklist.get("documentos", []))

                # Count received/approved documents for this case
                docs_count = db.execute(text("""
                    SELECT COUNT(*) FROM documents
                    WHERE case_id = :case_id AND org_id = :org_id
                      AND status IN ('received', 'approved', 'reviewed')
                """), {"case_id": case_id, "org_id": org_id}).scalar() or 0

                extra_ctx["checklist_progress"] = {
                    "entregues": min(docs_count, total_docs),
                    "total": total_docs,
                    "percent": round(min(docs_count, total_docs) / total_docs * 100) if total_docs > 0 else 0,
                    "tipo_acao_nome": checklist.get("nome", case.tipo_acao),
                }
            except Exception as e:
                logger.warning("Could not load checklist progress for case %d: %s", case_id, e)
                extra_ctx["checklist_progress"] = None
        else:
            extra_ctx["checklist_progress"] = None

        # 4. Timeline events
        timeline = []

        # Case creation
        if case.created_at:
            timeline.append({
                "date": case.created_at,
                "type": "criacao",
                "icon": "fas fa-plus-circle",
                "color": "primary",
                "description": "Processo criado",
            })

        # Filing date
        if case.filing_date:
            timeline.append({
                "date": datetime.combine(case.filing_date, datetime.min.time()),
                "type": "protocolo",
                "icon": "fas fa-gavel",
                "color": "info",
                "description": "Processo protocolado",
            })

        # Documents
        try:
            doc_rows = db.execute(text("""
                SELECT name, created_at FROM documents
                WHERE case_id = :case_id AND org_id = :org_id
                ORDER BY created_at DESC LIMIT 20
            """), {"case_id": case_id, "org_id": org_id}).fetchall()
            for dr in doc_rows:
                if dr.created_at:
                    timeline.append({
                        "date": dr.created_at,
                        "type": "documento",
                        "icon": "fas fa-file-alt",
                        "color": "success",
                        "description": f"Documento adicionado: {dr.name}",
                    })
        except Exception:
            pass

        # Tasks / deadlines
        try:
            task_rows = db.execute(text("""
                SELECT title, due_date, created_at FROM tasks
                WHERE case_id = :case_id AND org_id = :org_id
                ORDER BY created_at DESC LIMIT 20
            """), {"case_id": case_id, "org_id": org_id}).fetchall()
            for tr in task_rows:
                if tr.created_at:
                    timeline.append({
                        "date": tr.created_at,
                        "type": "tarefa",
                        "icon": "fas fa-tasks",
                        "color": "warning",
                        "description": f"Prazo cadastrado: {tr.title}",
                    })
        except Exception:
            pass

        # Prazos processuais as timeline events
        for p in extra_ctx.get("prazos", []):
            if p.get("data_vencimento"):
                timeline.append({
                    "date": datetime.combine(p["data_vencimento"], datetime.min.time()) if isinstance(p["data_vencimento"], date) else p["data_vencimento"],
                    "type": "prazo",
                    "icon": "fas fa-clock",
                    "color": "danger" if p.get("urgencia") == "vencido" else "warning",
                    "description": f"Prazo: {p['tipo']} — vence {p['data_vencimento'].strftime('%d/%m/%Y') if isinstance(p['data_vencimento'], date) else p['data_vencimento']}",
                })

        def _sort_date(x):
            d = x.get("date")
            if not d:
                return datetime.min
            if hasattr(d, 'tzinfo') and d.tzinfo is not None:
                return d.replace(tzinfo=None)
            if isinstance(d, date) and not isinstance(d, datetime):
                return datetime.combine(d, datetime.min.time())
            return d
        timeline.sort(key=_sort_date, reverse=True)
        extra_ctx["timeline"] = timeline

    try:
        from services.google_drive_handler import GoogleDriveHandler
        _dh = GoogleDriveHandler(db=db, org_id=getattr(request.state, "org_id", None))
        drive_connected = _dh.is_connected()
    except Exception:
        drive_connected = False

    return templates.TemplateResponse("app/cases/detail.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "case": case,
        "client": client,
        "custom_fields": custom_fields,
        "drive_connected": drive_connected,
        **extra_ctx,
    })

@router.get("/{case_id}/edit", response_class=HTMLResponse)
async def edit_case_form(request: Request, case_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    clients = tenant_query(db, Client, request.state.org_id).order_by(Client.first_name).all()
    try:
        custom_fields = get_custom_fields_for_entity(db, "case", case_id)
    except Exception as e:
        logger.warning("Could not load custom fields for case edit %d: %s", case_id, e)
        db.rollback()
        custom_fields = []

    return templates.TemplateResponse("app/cases/form.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "case": case,
        "clients": clients,
        "selected_client": None,
        "action": "Update",
        "custom_fields": custom_fields
    })

@router.post("/{case_id}/edit")
async def update_case(
    request: Request,
    case_id: int,
    client_id: int = Form(...),
    case_number: str = Form(None),
    case_name: str = Form(None),
    receipt_number: str = Form(None),
    visa_type: str = Form(None),
    status: str = Form("intake"),
    priority: str = Form("medium"),
    filing_date: str = Form(None),
    priority_date: str = Form(None),
    expiration_date: str = Form(None),
    case_value: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Convert form strings to proper types
    case_value = form_float(case_value)

    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Capture old status for trigger evaluation
    old_status = case.status

    case.client_id = client_id
    case.case_number = case_number
    case.case_name = case_name
    case.receipt_number = receipt_number
    case.visa_type = visa_type
    case.status = status
    case.priority = priority
    case.filing_date = parse_date(filing_date)
    case.priority_date = parse_date(priority_date)
    case.expiration_date = parse_date(expiration_date)
    case.case_value = case_value
    case.notes = notes
    
    db.commit()
    
    # Save custom fields
    form_data = await request.form()
    save_custom_fields_from_form(db, "case", case_id, dict(form_data))
    
    # Fire STATUS_CHANGED trigger if status actually changed
    if old_status != status:
        fire_triggers(db, case_id, "status_changed", {
            "from_status": old_status,
            "to_status": status,
            "visa_type": visa_type,
            "priority": priority
        })
    
    return RedirectResponse(url=f"{PREFIX}/cases/{case_id}", status_code=302)

@router.post("/{case_id}/delete")
async def delete_case(request: Request, case_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    db.delete(case)
    db.commit()
    
    return RedirectResponse(url=f"{PREFIX}/cases", status_code=302)

# ==================== QUICK STATUS UPDATE ====================

@router.post("/{case_id}/status")
async def quick_status_update(
    request: Request,
    case_id: int,
    new_status: str = Form(...),
    db: Session = Depends(get_db)
):
    """Quick status update endpoint - fires triggers automatically"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    old_status = case.status
    case.status = new_status
    db.commit()
    
    # Fire STATUS_CHANGED trigger
    if old_status != new_status:
        fire_triggers(db, case_id, "status_changed", {
            "from_status": old_status,
            "to_status": new_status,
            "visa_type": case.visa_type,
            "priority": case.priority
        })
    
    # Check if this came from AJAX or form
    accept = request.headers.get("Accept", "")
    if "application/json" in accept:
        return {"success": True, "old_status": old_status, "new_status": new_status}

    return RedirectResponse(url=f"{PREFIX}/cases/{case_id}", status_code=302)

# ==================== INLINE FIELD EDIT (list view) ====================

@router.patch("/{case_id}/field")
async def update_case_field(
    request: Request,
    case_id: int,
    db: Session = Depends(get_db),
):
    """Update a single Case field inline from the list view.

    Body (JSON): {"field": "<name>", "value": "<str|null>"}
    Returns JSON: {"success": True, "field", "value", "display"}.

    Deadline fields (vencimento/prazos) só podem ser editados por ADMIN ou
    ATTORNEY (advogado). Outros cargos recebem 403.
    """
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    field = (body.get("field") or "").strip()
    value = body.get("value")
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            value = None

    if field not in INLINE_EDITABLE_FIELDS:
        raise HTTPException(status_code=400, detail=f"Field '{field}' is not inline-editable")

    # Role gate: deadlines (prazos) only for admin/attorney.
    if field in DEADLINE_FIELDS and user.user_type not in DEADLINE_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Apenas administradores e advogados podem alterar prazos.",
        )

    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    old_status = case.status

    # Coerce / validate by field.
    if field in DEADLINE_FIELDS:
        parsed = parse_date(value) if value else None
        if value and parsed is None:
            raise HTTPException(status_code=400, detail="Data inválida (use AAAA-MM-DD).")
        setattr(case, field, parsed)
        display = parsed.strftime("%d/%m/%Y") if parsed else "—"
    else:
        setattr(case, field, value)
        display = value if value not in (None, "") else "—"

    db.commit()

    # Fire STATUS_CHANGED trigger when status edited inline.
    if field == "status" and old_status != value:
        fire_triggers(db, case_id, "status_changed", {
            "from_status": old_status,
            "to_status": value,
            "visa_type": case.visa_type,
            "priority": case.priority,
        })

    return JSONResponse(content={
        "success": True,
        "field": field,
        "value": value,
        "display": display,
    })


# ==================== QUICK-CREATE CLIENT (inline no cadastro de processo) ====================

@router.post("/api/clients/quick-create")
async def quick_create_client(
    request: Request,
    db: Session = Depends(get_db),
):
    """Create a minimal client without leaving the case form.

    Body (JSON): {"first_name", "last_name", "email", "phone", "cpf"}
    Returns JSON: {"success": True, "client": {"id", "label"}}.
    Reuses the same fields/encryption as POST /clients/new (subset).
    """
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    first_name = (body.get("first_name") or "").strip()
    last_name = (body.get("last_name") or "").strip()
    if not first_name or not last_name:
        raise HTTPException(status_code=400, detail="Nome e sobrenome são obrigatórios.")

    def _clean(key):
        v = body.get(key)
        return v.strip() if isinstance(v, str) and v.strip() else None

    email = _clean("email")
    phone = _clean("phone")
    whatsapp = _clean("whatsapp")
    cpf = _clean("cpf")

    client = Client(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        whatsapp=whatsapp,
        cpf=encrypt_value(cpf) if cpf else cpf,
        client_type="individual",
        status="active",
        org_id=request.state.org_id,
    )
    db.add(client)
    db.commit()
    db.refresh(client)

    label = f"{client.first_name} {client.last_name}".strip()
    if client.client_number:
        label = f"{label} · {client.client_number}"

    return JSONResponse(content={
        "success": True,
        "client": {"id": client.id, "label": label},
    })


# ==================== DOCUMENT CHECKLIST (BR) ====================

@router.get("/api/checklist/{tipo_acao}")
async def get_case_checklist(tipo_acao: str):
    """Return the document checklist for a given Brazilian case type."""
    from services.checklists_br import get_checklist
    checklist = get_checklist(tipo_acao)
    return JSONResponse(content=checklist)
