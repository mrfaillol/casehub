"""
CaseHub - Client Routes
"""
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import inspect, or_, text
from typing import Optional
import logging

from models import get_db, Client, Case, User, Document

logger = logging.getLogger(__name__)
from auth import get_current_user
from services.encryption import encrypt_value, decrypt_value
from models.tenant import tenant_query
from routes.custom_fields import get_custom_fields_for_entity, save_custom_fields_from_form
from config import settings
from core.template_config import templates

PREFIX = settings.PREFIX

router = APIRouter(prefix="/clients", tags=["clients"])


def _table_columns(db: Session, table_name: str) -> set[str]:
    try:
        return {column["name"] for column in inspect(db.get_bind()).get_columns(table_name)}
    except Exception as e:
        logger.debug("Column inspection failed for %s: %s", table_name, e)
        db.rollback()
        return set()


def _load_financial_summary(db: Session, client_id: int) -> dict:
    columns = _table_columns(db, "invoices")
    if {"client_id", "due_date", "total", "amount_paid", "balance_due", "status"} <= columns:
        fin = db.execute(text("""
            SELECT
                COALESCE(SUM(total), 0) as total_honorarios,
                COALESCE(SUM(amount_paid), 0) as total_pago,
                COALESCE(SUM(balance_due), 0) as saldo_devedor,
                MIN(CASE WHEN status IN ('sent', 'overdue') AND due_date >= CURRENT_DATE THEN due_date END) as proximo_vencimento
            FROM invoices
            WHERE client_id = :client_id AND COALESCE(status, '') != 'cancelled'
        """), {"client_id": client_id}).fetchone()
    elif {"client_id", "due_date", "total_amount", "payment_status"} <= columns:
        fin = db.execute(text("""
            SELECT
                COALESCE(SUM(total_amount), 0) as total_honorarios,
                COALESCE(SUM(CASE WHEN payment_status = 'paid' THEN total_amount ELSE 0 END), 0) as total_pago,
                COALESCE(SUM(CASE WHEN payment_status != 'paid' OR payment_status IS NULL THEN total_amount ELSE 0 END), 0) as saldo_devedor,
                MIN(CASE WHEN payment_status IN ('sent', 'overdue', 'pending') AND due_date >= CURRENT_DATE THEN due_date END) as proximo_vencimento
            FROM invoices
            WHERE client_id = :client_id AND COALESCE(payment_status, '') != 'cancelled'
        """), {"client_id": client_id}).fetchone()
    else:
        return {}

    if not fin:
        return {}

    return {
        "total_honorarios": float(fin.total_honorarios or 0),
        "total_pago": float(fin.total_pago or 0),
        "saldo_devedor": float(fin.saldo_devedor or 0),
        "proximo_vencimento": fin.proximo_vencimento,
    }

def _load_birthdays(db: Session, org_id: int) -> tuple[list, list]:
    """Aniversariantes do mês/dia, org-scoped (by month/day of date_of_birth)."""
    from datetime import date as _date
    today = _date.today()
    rows = (
        tenant_query(db, Client, org_id)
        .filter(Client.date_of_birth.isnot(None))
        .filter(Client.status != "inactive")
        .all()
    )
    month_list, today_list = [], []
    for c in rows:
        dob = c.date_of_birth
        if not dob or dob.month != today.month:
            continue
        turning = today.year - dob.year
        item = {
            "id": c.id,
            "name": c.full_name,
            "day": dob.day,
            "date": dob.strftime("%d/%m"),
            "turning": turning,
            "phone": c.phone or "",
            "is_today": dob.day == today.day,
        }
        month_list.append(item)
        if dob.day == today.day:
            today_list.append(item)
    month_list.sort(key=lambda x: (x["day"], x["name"]))
    return today_list, month_list


@router.get("", response_class=HTMLResponse)
async def list_clients(
    request: Request,
    search: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    query = tenant_query(db, Client, request.state.org_id)
    
    if search:
        search_filter = f"%{search}%"
        # Note: ssn, alien_number, passport_number are encrypted and cannot be
        # searched with ILIKE. Search by name, email, and client_number instead.
        query = query.filter(
            or_(
                Client.first_name.ilike(search_filter),
                Client.last_name.ilike(search_filter),
                Client.email.ilike(search_filter),
                Client.client_number.ilike(search_filter)
            )
        )
    
    if status:
        query = query.filter(Client.status == status)
    
    total = query.count()
    per_page = 20
    clients = query.order_by(Client.first_name.asc(), Client.last_name.asc()).offset((page-1)*per_page).limit(per_page).all()

    birthdays_today, birthdays_month = _load_birthdays(db, request.state.org_id)

    return templates.TemplateResponse("app/clients/list.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "clients": clients,
        "total": total,
        "page": page,
        "per_page": per_page,
        "search": search or "",
        "status": status or "",
        "birthdays_today": birthdays_today,
        "birthdays_month": birthdays_month,
    })

@router.get("/new", response_class=HTMLResponse)
async def new_client(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    custom_fields = get_custom_fields_for_entity(db, "client")
    
    return templates.TemplateResponse("app/clients/form.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "client": None,
        "action": "Create",
        "custom_fields": custom_fields
    })

@router.post("/new")
async def create_client(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(None),
    phone: str = Form(None),
    whatsapp: str = Form(None),
    date_of_birth: str = Form(None),
    country_of_origin: str = Form(None),
    ssn: str = Form(None),
    alien_number: str = Form(None),
    passport_number: str = Form(None),
    cpf: str = Form(None),
    rg: str = Form(None),
    cnpj: str = Form(None),
    oab_number: str = Form(None),
    client_type: str = Form("individual"),
    address: str = Form(None),
    status: str = Form("lead"),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    from datetime import datetime
    dob = None
    if date_of_birth:
        try:
            dob = datetime.strptime(date_of_birth, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass

    client = Client(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        whatsapp=whatsapp,
        date_of_birth=dob,
        country_of_origin=country_of_origin,
        ssn=encrypt_value(ssn) if ssn else ssn,
        alien_number=encrypt_value(alien_number) if alien_number else alien_number,
        passport_number=encrypt_value(passport_number) if passport_number else passport_number,
        cpf=encrypt_value(cpf) if cpf else cpf,
        rg=encrypt_value(rg) if rg else rg,
        cnpj=encrypt_value(cnpj) if cnpj else cnpj,
        oab_number=oab_number,
        client_type=client_type,
        address=address,
        status=status,
        notes=notes,
        org_id=request.state.org_id)
    db.add(client)
    db.commit()
    db.refresh(client)
    
    # Save custom fields
    form_data = await request.form()
    save_custom_fields_from_form(db, "client", client.id, dict(form_data))
    
    return RedirectResponse(url=f"{PREFIX}/clients/{client.id}", status_code=302)

@router.get("/{client_id}", response_class=HTMLResponse)
async def view_client(request: Request, client_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Decrypt PII for display
    client.decrypt_pii()

    cases = tenant_query(db, Case, request.state.org_id).filter(Case.client_id == client_id).all()
    custom_fields = get_custom_fields_for_entity(db, "client", client_id)

    # Generate checklist summaries for this client's cases
    client_checklists = []
    try:
        from services.checklist_generator import generate_checklist, normalize_visa_type
        case_ids = [c.id for c in cases]
        all_docs = tenant_query(db, Document, request.state.org_id).filter(Document.case_id.in_(case_ids)).all() if case_ids else []
        docs_by_case = {}
        for doc in all_docs:
            docs_by_case.setdefault(doc.case_id, []).append(doc)
        for case in cases:
            vt = normalize_visa_type(case.visa_type)
            if not vt:
                continue
            checklist = generate_checklist(case.id, vt, docs_by_case.get(case.id, []))
            pct = checklist.progress_percent
            client_checklists.append({
                "case": case,
                "visa_label": checklist.visa_label,
                "progress_percent": pct,
                "total_present": checklist.total_present,
                "total_required": checklist.total_required,
                "status": "complete" if pct >= 100 else "in_progress" if pct > 0 else "not_started",
            })
    except Exception as e:
        logger.error(f"Error generating client checklists: {e}")
        db.rollback()

    # Fetch linked emails. Communication tables are optional on Basic/Lite
    # deployments, so missing tables must not break client CRUD.
    emails = []
    try:
        emails = db.execute(text("""
            SELECT id, subject, sender, received_at, direction, is_read
            FROM email_messages
            WHERE client_id = :client_id
            ORDER BY received_at DESC
            LIMIT 50
        """), {"client_id": client_id}).fetchall()
    except Exception as e:
        logger.debug("Linked emails query failed for client %d: %s", client_id, e)
        db.rollback()

    # Check if client has active portal access
    has_portal_access = False
    try:
        has_portal_access = db.execute(
            text("SELECT 1 FROM portal_users WHERE client_id = :id AND is_active = true"),
            {"id": client_id}
        ).fetchone() is not None
    except Exception as e:
        logger.debug("Portal access query failed for client %d: %s", client_id, e)
        db.rollback()

    # Lite: Activity timeline from audit_log
    activity_timeline = []
    try:
        activity_timeline = db.execute(text("""
            SELECT action, entity_type, description, created_at, user_email
            FROM audit_log
            WHERE (entity_type = 'client' AND entity_id = :client_id)
               OR (entity_type IN ('case', 'document', 'invoice', 'task') AND entity_id IN (
                   SELECT id FROM cases WHERE client_id = :client_id
               ))
            ORDER BY created_at DESC
            LIMIT 15
        """), {"client_id": client_id}).fetchall()
    except Exception as e:
        logger.debug(f"Activity timeline query failed (table may not exist): {e}")
        db.rollback()

    # Lite: Financial summary from invoices
    financial_summary = {}
    try:
        financial_summary = _load_financial_summary(db, client_id)
    except Exception as e:
        logger.debug(f"Financial summary query failed (table may not exist): {e}")
        db.rollback()

    # Optional reads above may roll back schema-drift failures and expire ORM
    # objects. Rehydrate the user theme before Jinja evaluates base.html.
    _ = user.ui_theme

    return templates.TemplateResponse("app/clients/detail.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "client": client,
        "cases": cases,
        "custom_fields": custom_fields,
        "client_checklists": client_checklists,
        "emails": emails,
        "has_portal_access": has_portal_access,
        "activity_timeline": activity_timeline,
        "financial_summary": financial_summary
    })


_DRIVE_FOLDER_URL_PATTERNS = (
    # https://drive.google.com/drive/folders/<id>[?...]
    r"drive\.google\.com/drive/(?:u/\d+/)?folders/([A-Za-z0-9_\-]{15,})",
    # https://drive.google.com/drive/u/0/folders/<id>
    # Shared-with-me + open?id= URL forms:
    r"drive\.google\.com/(?:open|file/d)\?id=([A-Za-z0-9_\-]{15,})",
    r"drive\.google\.com/(?:open|file/d)/([A-Za-z0-9_\-]{15,})",
)


def _parse_drive_folder_id(raw: str) -> Optional[str]:
    """Extract a Drive folder id from either a raw id or a Drive URL.

    Lawyers paste URLs much more often than they paste IDs. Accept both
    so the UI can stay simple ("paste the folder link"). Returns ``None``
    when nothing parsable was found — the route layer rejects with 400.

    Accepts:
    - Bare id (alphanumeric + ``_-``, length ≥ 15 — Drive ids are
      typically 33 chars; the 15-char floor weeds out accidental short
      strings without locking us to one Drive id format).
    - Several Drive URL shapes (``/drive/folders/ID``, ``open?id=ID``,
      ``file/d/ID``), with or without the ``/u/<n>/`` user-prefix.

    Rejects: anything else, including http URLs to other hosts.
    """
    import re

    if not raw:
        return None
    candidate = raw.strip()
    # Bare-id fast path. A bare id never contains "/" or "?".
    if "/" not in candidate and "?" not in candidate and re.fullmatch(r"[A-Za-z0-9_\-]{15,}", candidate):
        return candidate
    for pattern in _DRIVE_FOLDER_URL_PATTERNS:
        match = re.search(pattern, candidate)
        if match:
            return match.group(1)
    return None


@router.post("/{client_id}/drive-folder")
async def set_client_drive_folder(request: Request, client_id: int, db: Session = Depends(get_db)):
    """Link a client to a Google Drive folder (per-client storage).

    Accepts JSON body ``{"drive_folder_id": str, "drive_folder_name":
    optional str}``. ``drive_folder_id`` may be a bare id OR a Drive URL —
    the parser handles both so the UI can present a single "paste folder
    link" field.

    Passing an empty / null ``drive_folder_id`` UNLINKS the client (sets
    both columns to NULL) — same endpoint, no separate DELETE route.

    Persisting an explicit id replaces the brittle name-derived lookup
    in ``get_client_drive_folder`` (which searched Drive by
    ``LASTNAME, First - VISA`` and broke whenever the lawyer renamed the
    folder or the case lacked a visa_type).
    """
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    client = (
        tenant_query(db, Client, request.state.org_id)
        .filter(Client.id == client_id)
        .first()
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    try:
        body = await request.json()
    except Exception:
        body = {}

    raw_id = (body.get("drive_folder_id") or "").strip()
    raw_name = (body.get("drive_folder_name") or "").strip() or None

    if raw_id == "":
        # Explicit unlink: clear both columns.
        client.drive_folder_id = None
        client.drive_folder_name = None
        db.commit()
        return {
            "success": True,
            "unlinked": True,
            "client_id": client_id,
        }

    folder_id = _parse_drive_folder_id(raw_id)
    if not folder_id:
        return {
            "success": False,
            "error": "invalid_drive_folder_id",
            "detail": (
                "drive_folder_id must be a bare Drive id (≥15 chars) "
                "or a recognized Drive URL "
                "(/drive/folders/<id>, open?id=<id>, file/d/<id>)."
            ),
        }

    client.drive_folder_id = folder_id
    client.drive_folder_name = raw_name
    db.commit()

    logger.info(
        "[DRIVE LINK] client_id=%s linked to drive_folder_id=%s",
        client_id,
        folder_id,
    )
    return {
        "success": True,
        "client_id": client_id,
        "drive_folder_id": folder_id,
        "drive_folder_name": raw_name,
    }


@router.get("/{client_id}/drive-folder")
async def get_client_drive_folder(request: Request, client_id: int, db: Session = Depends(get_db)):
    """Get Google Drive folder link for client.

    Prefers the **stored** ``client.drive_folder_id`` (set via POST). Only
    falls back to the legacy name-based search when no id is stored —
    that path remains for clients provisioned before this PR.
    """
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Preferred path: stored explicit drive_folder_id.
    if client.drive_folder_id:
        web_link = f"https://drive.google.com/drive/folders/{client.drive_folder_id}"
        return {
            "success": True,
            "folder_id": client.drive_folder_id,
            "web_link": web_link,
            "client_name": client.drive_folder_name or f"{client.first_name} {client.last_name}".strip(),
            "source": "stored",
        }

    # Legacy fallback: derive folder from client name + visa_type via the
    # GoogleDriveHandler search. Brittle (renames break it) — surfaced
    # with ``source="legacy_name_search"`` so the UI can prompt the user
    # to "Connect a folder" instead.
    try:
        from services.google_drive_handler import GoogleDriveHandler

        handler = GoogleDriveHandler(db, org_id=request.state.org_id)

        # Format client name as "LAST_NAME, First_Name - VISA_TYPE" to match Drive folder naming
        # Try with case first
        case = tenant_query(db, Case, request.state.org_id).filter(Case.client_id == client_id).first()

        last_name = client.last_name.upper() if client.last_name else ""
        first_name = client.first_name if client.first_name else ""

        # Try format with visa type first (most specific)
        if case and case.visa_type:
            client_name = f"{last_name}, {first_name} - {case.visa_type}"
        else:
            # Fallback to format without visa type
            client_name = f"{last_name}, {first_name}"

        # Get folder ID and web link
        folder_id = handler.get_client_folder(client_name)
        web_link = handler.get_client_folder_web_link(client_name)

        return {
            "success": True,
            "folder_id": folder_id,
            "web_link": web_link,
            "client_name": client_name,
            "source": "legacy_name_search",
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "source": "legacy_name_search",
        }


@router.get("/{client_id}/drive-files")
async def list_client_drive_files(request: Request, client_id: int, db: Session = Depends(get_db)):
    """List all files in client's Google Drive folder."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    try:
        from services.google_drive_handler import GoogleDriveHandler

        handler = GoogleDriveHandler(db, org_id=request.state.org_id)
        client_name = f"{client.first_name} {client.last_name}".strip()

        # Get list of files
        files = handler.list_client_files(client_name, max_results=50)

        return {
            "success": True,
            "files": files,
            "total": len(files),
            "client_name": client_name
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "files": []
        }


@router.get("/{client_id}/edit", response_class=HTMLResponse)
async def edit_client_form(request: Request, client_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Decrypt PII for edit form
    client.decrypt_pii()

    custom_fields = get_custom_fields_for_entity(db, "client", client_id)

    return templates.TemplateResponse("app/clients/form.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "client": client,
        "action": "Update",
        "custom_fields": custom_fields
    })

@router.post("/{client_id}/edit")
async def update_client(
    request: Request,
    client_id: int,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(None),
    phone: str = Form(None),
    whatsapp: str = Form(None),
    date_of_birth: str = Form(None),
    country_of_origin: str = Form(None),
    ssn: str = Form(None),
    alien_number: str = Form(None),
    passport_number: str = Form(None),
    cpf: str = Form(None),
    rg: str = Form(None),
    cnpj: str = Form(None),
    oab_number: str = Form(None),
    client_type: str = Form("individual"),
    address: str = Form(None),
    status: str = Form("lead"),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    from datetime import datetime
    dob = None
    if date_of_birth:
        try:
            dob = datetime.strptime(date_of_birth, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass

    client.first_name = first_name
    client.last_name = last_name
    client.email = email
    client.phone = phone
    client.whatsapp = whatsapp
    client.date_of_birth = dob
    client.country_of_origin = country_of_origin
    client.ssn = encrypt_value(ssn) if ssn else ssn
    client.alien_number = encrypt_value(alien_number) if alien_number else alien_number
    client.passport_number = encrypt_value(passport_number) if passport_number else passport_number
    client.cpf = encrypt_value(cpf) if cpf else cpf
    client.rg = encrypt_value(rg) if rg else rg
    client.cnpj = encrypt_value(cnpj) if cnpj else cnpj
    client.oab_number = oab_number
    client.client_type = client_type
    client.address = address
    client.status = status
    client.notes = notes
    
    db.commit()
    
    # Save custom fields
    form_data = await request.form()
    save_custom_fields_from_form(db, "client", client_id, dict(form_data))
    
    return RedirectResponse(url=f"{PREFIX}/clients/{client_id}", status_code=302)

@router.post("/{client_id}/delete")
async def delete_client(request: Request, client_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    db.delete(client)
    db.commit()
    
    return RedirectResponse(url=f"{PREFIX}/clients", status_code=302)
