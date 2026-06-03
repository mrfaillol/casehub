"""
CaseHub - Bulk Operations Routes
Perform bulk actions on multiple records.
"""
import json
import logging
from typing import List
from datetime import datetime

logger = logging.getLogger(__name__)

from core.form_utils import form_int, form_float
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, User, Case, Client
from auth import get_current_user
from models.tenant import tenant_query
from services.bulk_service import bulk_service, CREATE_BULK_LOG_TABLE, EntityType

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/bulk", tags=["bulk"])

MAX_BULK_ITEMS = 500
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py


def ensure_tables(db: Session):
    """Ensure bulk operation tables exist."""
    try:
        db.execute(text(CREATE_BULK_LOG_TABLE))
        db.commit()
    except Exception as e:
        db.rollback()


@router.get("", response_class=HTMLResponse)
async def bulk_dashboard(
    request: Request,
    db: Session = Depends(get_db)
):
    """Bulk operations dashboard."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    # Get recent bulk operations
    try:
        result = db.execute(text("""
            SELECT b.*, u.name as user_name
            FROM bulk_operation_logs b
            LEFT JOIN users u ON b.created_by = u.id
            WHERE b.org_id = :org_id
            ORDER BY b.created_at DESC
            LIMIT 20
        """), {"org_id": request.state.org_id})
        recent_ops = result.fetchall()
    except Exception:
        db.rollback()
        recent_ops = []

    return templates.TemplateResponse("app/bulk/dashboard.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "recent_ops": recent_ops,
        "entity_types": [{"value": e.value, "label": e.value.title()} for e in EntityType]
    })


@router.get("/cases", response_class=HTMLResponse)
async def bulk_cases(
    request: Request,
    db: Session = Depends(get_db)
):
    """Bulk operations for cases."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Get cases
    cases = tenant_query(db, Case, request.state.org_id).order_by(Case.created_at.desc()).limit(200).all()

    # Get users for assignment
    try:
        users = db.execute(text("SELECT id, name FROM users WHERE enabled = true AND org_id = :org_id ORDER BY name"), {"org_id": request.state.org_id}).fetchall()
    except Exception:
        db.rollback()
        users = []

    operations = bulk_service.get_operations(EntityType.CASE)
    status_options = bulk_service.get_status_options(EntityType.CASE)

    return templates.TemplateResponse("app/bulk/cases.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "cases": cases,
        "users": users,
        "operations": operations,
        "status_options": status_options
    })


@router.post("/cases/execute")
async def execute_bulk_cases(
    request: Request,
    operation: str = Form(...),
    case_ids: str = Form(...),
    new_status: str = Form(None),
    assign_to: str = Form(None),
    db: Session = Depends(get_db)
):
    """Execute bulk operation on cases."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Convert form strings to proper types
    assign_to = form_int(assign_to)

    ensure_tables(db)

    # Parse case IDs
    try:
        ids = json.loads(case_ids)
    except Exception:
        db.rollback()
        ids = []

    if not ids:
        raise HTTPException(status_code=400, detail="No cases selected")

    if len(ids) > MAX_BULK_ITEMS:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_BULK_ITEMS} items per bulk operation")

    success_count = 0
    failed_count = 0

    try:
        if operation == "update_status" and new_status:
            for case_id in ids:
                try:
                    db.execute(text("UPDATE cases SET status = :status, updated_at = NOW() WHERE id = :id AND org_id = :org_id"),
                              {"status": new_status, "id": case_id, "org_id": request.state.org_id})
                    success_count += 1
                except Exception as e:
                    logger.error("Bulk update_status failed for case %s: %s", case_id, e)
                    failed_count += 1

        elif operation == "assign_user" and assign_to:
            for case_id in ids:
                try:
                    db.execute(text("UPDATE cases SET assigned_to = :uid, updated_at = NOW() WHERE id = :id AND org_id = :org_id"),
                              {"uid": assign_to, "id": case_id, "org_id": request.state.org_id})
                    success_count += 1
                except Exception as e:
                    logger.error("Bulk assign_user failed for case %s: %s", case_id, e)
                    failed_count += 1

        elif operation == "delete":
            for case_id in ids:
                try:
                    db.execute(text("DELETE FROM cases WHERE id = :id AND org_id = :org_id"), {"id": case_id, "org_id": request.state.org_id})
                    success_count += 1
                except Exception as e:
                    logger.error("Bulk delete failed for case %s: %s", case_id, e)
                    failed_count += 1

        elif operation == "export":
            # Export to CSV
            result = db.execute(text("""
                SELECT c.case_number, c.case_name, c.visa_type, c.status, c.created_at,
                       cl.first_name, cl.last_name
                FROM cases c
                LEFT JOIN clients cl ON c.client_id = cl.id
                WHERE c.id = ANY(:ids) AND c.org_id = :org_id
            """), {"ids": ids, "org_id": request.state.org_id})
            rows = result.fetchall()

            headers = ["Case Number", "Case Name", "Visa Type", "Status", "Created", "Client First", "Client Last"]
            data = [[row.case_number, row.case_name, row.visa_type, row.status,
                    row.created_at.strftime('%Y-%m-%d') if row.created_at else '',
                    row.first_name, row.last_name] for row in rows]

            csv_content = bulk_service.generate_csv(headers, data)

            # Log operation
            db.execute(text("""
                INSERT INTO bulk_operation_logs (entity_type, operation, entity_ids, total_count, success_count, created_by, org_id)
                VALUES ('case', 'export', :ids, :total, :total, :uid, :org_id)
            """), {"ids": ids, "total": len(ids), "uid": user.id, "org_id": request.state.org_id})
            db.commit()

            return Response(
                content=csv_content,
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=cases_export_{datetime.now().strftime('%Y%m%d')}.csv"}
            )

        # Log operation
        db.execute(text("""
            INSERT INTO bulk_operation_logs (entity_type, operation, entity_ids, total_count, success_count, failed_count, created_by, org_id)
            VALUES ('case', :op, :ids, :total, :success, :failed, :uid, :org_id)
        """), {
            "op": operation,
            "ids": ids,
            "total": len(ids),
            "success": success_count,
            "failed": failed_count,
            "uid": user.id,
            "org_id": request.state.org_id
        })

        db.commit()

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/bulk/cases?success={success_count}&failed={failed_count}", status_code=302)


@router.get("/clients", response_class=HTMLResponse)
async def bulk_clients(
    request: Request,
    db: Session = Depends(get_db)
):
    """Bulk operations for clients."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    clients = tenant_query(db, Client, request.state.org_id).order_by(Client.created_at.desc()).limit(200).all()

    operations = bulk_service.get_operations(EntityType.CLIENT)
    status_options = bulk_service.get_status_options(EntityType.CLIENT)

    return templates.TemplateResponse("app/bulk/clients.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "clients": clients,
        "operations": operations,
        "status_options": status_options
    })


@router.post("/clients/execute")
async def execute_bulk_clients(
    request: Request,
    operation: str = Form(...),
    client_ids: str = Form(...),
    new_status: str = Form(None),
    db: Session = Depends(get_db)
):
    """Execute bulk operation on clients."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ensure_tables(db)

    try:
        ids = json.loads(client_ids)
    except Exception:
        db.rollback()
        ids = []

    if not ids:
        raise HTTPException(status_code=400, detail="No clients selected")

    if len(ids) > MAX_BULK_ITEMS:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_BULK_ITEMS} items per bulk operation")

    success_count = 0
    failed_count = 0

    try:
        if operation == "update_status" and new_status:
            for client_id in ids:
                try:
                    db.execute(text("UPDATE clients SET status = :status, updated_at = NOW() WHERE id = :id AND org_id = :org_id"),
                              {"status": new_status, "id": client_id, "org_id": request.state.org_id})
                    success_count += 1
                except Exception as e:
                    logger.error("Bulk update_status failed for client %s: %s", client_id, e)
                    failed_count += 1

        elif operation == "delete":
            for client_id in ids:
                try:
                    db.execute(text("DELETE FROM clients WHERE id = :id AND org_id = :org_id"), {"id": client_id, "org_id": request.state.org_id})
                    success_count += 1
                except Exception as e:
                    logger.error("Bulk delete failed for client %s: %s", client_id, e)
                    failed_count += 1

        elif operation == "export":
            result = db.execute(text("""
                SELECT first_name, last_name, email, phone, status, created_at
                FROM clients WHERE id = ANY(:ids) AND org_id = :org_id
            """), {"ids": ids, "org_id": request.state.org_id})
            rows = result.fetchall()

            headers = ["First Name", "Last Name", "Email", "Phone", "Status", "Created"]
            data = [[row.first_name, row.last_name, row.email, row.phone, row.status,
                    row.created_at.strftime('%Y-%m-%d') if row.created_at else ''] for row in rows]

            csv_content = bulk_service.generate_csv(headers, data)

            db.execute(text("""
                INSERT INTO bulk_operation_logs (entity_type, operation, entity_ids, total_count, success_count, created_by, org_id)
                VALUES ('client', 'export', :ids, :total, :total, :uid, :org_id)
            """), {"ids": ids, "total": len(ids), "uid": user.id, "org_id": request.state.org_id})
            db.commit()

            return Response(
                content=csv_content,
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=clients_export_{datetime.now().strftime('%Y%m%d')}.csv"}
            )

        db.execute(text("""
            INSERT INTO bulk_operation_logs (entity_type, operation, entity_ids, total_count, success_count, failed_count, created_by, org_id)
            VALUES ('client', :op, :ids, :total, :success, :failed, :uid, :org_id)
        """), {
            "op": operation,
            "ids": ids,
            "total": len(ids),
            "success": success_count,
            "failed": failed_count,
            "uid": user.id,
            "org_id": request.state.org_id
        })

        db.commit()

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/bulk/clients?success={success_count}&failed={failed_count}", status_code=302)
