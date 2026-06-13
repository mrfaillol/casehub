"""
CaseHub - Intake Packages Routes
Manage client intake questionnaire and document packages.
"""
import json
import logging
from typing import Optional, List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, User, Case, Client
from auth import get_current_user
from models.tenant import tenant_query
from services.intake_service import intake_service, CREATE_INTAKE_TABLE, PackageStatus, ItemStatus, ItemType
from services.intake_email_service import send_intake_email
from config import settings

OVERDUE_DAYS = 5  # Questionnaires overdue after this many days

PREFIX = settings.PREFIX

router = APIRouter(prefix="/intake", tags=["intake"])
templates = Jinja2Templates(directory="templates")


def ensure_tables(db: Session):
    """Ensure intake tables exist."""
    try:
        db.execute(text(CREATE_INTAKE_TABLE))
        db.commit()
    except Exception as e:
        db.rollback()


@router.get("", response_class=HTMLResponse)
async def intake_list(
    request: Request,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all intake packages."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    # Get packages with filters.
    # SECURITY: intake_packages has no org_id column of its own, so tenancy is
    # derived from the linked case/client. Without this scope the list leaked
    # EVERY org's packages (cross-tenant IDOR). We require the package's case OR
    # client to belong to the caller's org.
    org_id = request.state.org_id
    query = """
        SELECT p.*, c.case_number, c.case_name, c.visa_type,
               cl.first_name, cl.last_name, cl.email,
               (SELECT COUNT(*) FROM intake_items WHERE package_id = p.id) as item_count,
               (SELECT COUNT(*) FROM intake_items WHERE package_id = p.id AND status IN ('submitted', 'approved')) as completed_count
        FROM intake_packages p
        LEFT JOIN cases c ON p.case_id = c.id
        LEFT JOIN clients cl ON p.client_id = cl.id
        WHERE (c.org_id = :org_id OR cl.org_id = :org_id)
    """
    params = {"org_id": org_id}

    if status:
        query += " AND p.status = :status"
        params["status"] = status
    else:
        query += " AND p.status != 'deleted'"

    query += " ORDER BY p.created_at DESC"

    try:
        result = db.execute(text(query), params)
        packages = result.fetchall()
    except Exception:
        db.rollback()
        packages = []

    # Calculate overdue packages (sent/in_progress for >5 days without completion)
    overdue_threshold = datetime.now() - timedelta(days=OVERDUE_DAYS)
    overdue_info = {}  # package_id -> days_since_sent
    for pkg in packages:
        sent_at = getattr(pkg, 'sent_at', None)
        pkg_status = getattr(pkg, 'status', '')
        if (sent_at and sent_at < overdue_threshold
                and pkg_status in ('sent', 'in_progress', 'active')):
            days = (datetime.now() - sent_at).days
            overdue_info[pkg.package_id] = days

    # Get status counts (org-scoped — same tenancy derivation as the list above).
    try:
        counts_result = db.execute(text("""
            SELECT p.status, COUNT(*) as count
            FROM intake_packages p
            LEFT JOIN cases c ON p.case_id = c.id
            LEFT JOIN clients cl ON p.client_id = cl.id
            WHERE (c.org_id = :org_id OR cl.org_id = :org_id)
            GROUP BY p.status
        """), {"org_id": org_id})
        status_counts = {row.status: row.count for row in counts_result.fetchall()}
    except Exception:
        db.rollback()
        status_counts = {}

    return templates.TemplateResponse("app/intake/list.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "packages": packages,
        "status_counts": status_counts,
        "selected_status": status,
        "statuses": [s.value for s in PackageStatus],
        "overdue_info": overdue_info,
        "overdue_count": len(overdue_info),
    })


@router.get("/new", response_class=HTMLResponse)
async def new_package(
    request: Request,
    case_id: Optional[int] = None,
    template: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Create new intake package."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    # Get cases
    cases = tenant_query(db, Case, request.state.org_id).order_by(Case.created_at.desc()).all()

    # Get selected case
    selected_case = None
    client = None
    suggested_template = None

    if case_id:
        selected_case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
        if selected_case:
            client = tenant_query(db, Client, request.state.org_id).filter(Client.id == selected_case.client_id).first()
            suggested_template = intake_service.get_template_for_visa(selected_case.visa_type or "")

    # Get template if specified
    if template:
        suggested_template = intake_service.get_template_for_visa(template)

    # Get all available templates
    available_templates = intake_service.get_available_templates()

    return templates.TemplateResponse("app/intake/create.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "cases": cases,
        "selected_case": selected_case,
        "client": client,
        "suggested_template": suggested_template,
        "available_templates": available_templates,
        "item_types": [t.value for t in ItemType]
    })


@router.post("/create")
async def create_package(
    request: Request,
    case_id: int = Form(...),
    name: str = Form(...),
    message: str = Form(None),
    expires_in_days: int = Form(30),
    items_json: str = Form("[]"),
    auto_send: str = Form(None),
    db: Session = Depends(get_db)
):
    """Create a new intake package. If auto_send=True, automatically sends email to client."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ensure_tables(db)

    # Parse items
    try:
        items = json.loads(items_json)
    except Exception:
        db.rollback()
        items = []

    # Get case and client
    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Create package
    package = intake_service.create_package(
        case_id=case_id,
        name=name,
        items=items,
        expires_in_days=expires_in_days,
        message=message
    )

    try:
        # Insert package
        db.execute(text("""
            INSERT INTO intake_packages
            (package_id, access_token, case_id, client_id, name, status, message, expires_at, created_by)
            VALUES (:pid, :token, :case_id, :client_id, :name, :status, :msg, :expires, :uid)
        """), {
            "pid": package["package_id"],
            "token": package["access_token"],
            "case_id": case_id,
            "client_id": case.client_id,
            "name": name,
            "status": PackageStatus.DRAFT,
            "msg": message,
            "expires": package["expires_at"],
            "uid": user.id
        })

        # Get the package ID
        result = db.execute(text("SELECT id FROM intake_packages WHERE package_id = :pid"),
                           {"pid": package["package_id"]})
        pkg_row = result.fetchone()
        pkg_id = pkg_row.id

        # Insert items
        for i, item in enumerate(items):
            db.execute(text("""
                INSERT INTO intake_items
                (package_id, item_type, name, description, required, status, sort_order, questionnaire_id)
                VALUES (:pkg_id, :type, :name, :desc, :req, :status, :order, :qid)
            """), {
                "pkg_id": pkg_id,
                "type": item.get("type", "document_request"),
                "name": item.get("name", ""),
                "desc": item.get("description", ""),
                "req": item.get("required", True),
                "status": ItemStatus.PENDING,
                "order": i,
                "qid": item.get("questionnaire_id")
            })

        db.commit()

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    # Auto-send email to client if requested
    if auto_send and auto_send.lower() in ("true", "1", "on"):
        try:
            client = tenant_query(db, Client, request.state.org_id).filter(Client.id == case.client_id).first()
            if client and client.email:
                intake_link = intake_service.generate_client_link(
                    package["package_id"], package["access_token"]
                )
                email_result = send_intake_email(
                    client_email=client.email,
                    client_name=f"{client.first_name} {client.last_name}".strip() or "Client",
                    package_name=name,
                    intake_link=intake_link,
                    expires_at=package.get("expires_at"),
                    package_id=package["package_id"],
                    case_number=getattr(case, "case_number", ""),
                    validate_link=True
                )
                if email_result.get("email_sent"):
                    db.execute(text(
                        "UPDATE intake_packages SET status = :status, sent_at = NOW() "
                        "WHERE package_id = :pid"
                    ), {"status": PackageStatus.SENT, "pid": package["package_id"]})
                    db.commit()
                    import logging
                    logging.getLogger(__name__).info(
                        f"Auto-sent intake package {package['package_id']} to {client.email}"
                    )
                    return RedirectResponse(
                        url=f"{PREFIX}/intake/{package['package_id']}?success=sent",
                        status_code=302
                    )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Auto-send error: {e}", exc_info=True)

    return RedirectResponse(url=f"{PREFIX}/intake/{package['package_id']}", status_code=302)


@router.get("/{package_id}", response_class=HTMLResponse)
async def view_package(
    request: Request,
    package_id: str,
    db: Session = Depends(get_db)
):
    """View intake package details."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    try:
        result = db.execute(text("""
            SELECT p.*, c.case_number, c.case_name, c.visa_type,
                   cl.first_name, cl.last_name, cl.email,
                   u.name as creator_name
            FROM intake_packages p
            LEFT JOIN cases c ON p.case_id = c.id
            LEFT JOIN clients cl ON p.client_id = cl.id
            LEFT JOIN users u ON p.created_by = u.id
            WHERE p.package_id = :pid
        """), {"pid": package_id})
        package = result.fetchone()

        if not package:
            raise HTTPException(status_code=404, detail="Package not found")

        # Get items
        items_result = db.execute(text("""
            SELECT i.*,
                   (SELECT COUNT(*) FROM intake_responses WHERE item_id = i.id) as response_count
            FROM intake_items i
            WHERE i.package_id = (SELECT id FROM intake_packages WHERE package_id = :pid)
            ORDER BY i.sort_order
        """), {"pid": package_id})
        items = items_result.fetchall()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Calculate completion
    items_list = [{"status": item.status, "required": item.required} for item in items]
    completion = intake_service.calculate_completion(items_list)

    # Generate client link
    client_link = intake_service.generate_client_link(package_id, package.access_token)

    # Calculate overdue status
    is_overdue = False
    days_since_sent = 0
    sent_at = getattr(package, 'sent_at', None)
    if sent_at and package.status in ('sent', 'in_progress', 'active'):
        days_since_sent = (datetime.now() - sent_at).days
        is_overdue = days_since_sent > OVERDUE_DAYS

    return templates.TemplateResponse("app/intake/view.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "package": package,
        "items": items,
        "completion": completion,
        "client_link": client_link,
        "item_statuses": [s.value for s in ItemStatus],
        "is_overdue": is_overdue,
        "days_since_sent": days_since_sent,
    })


@router.post("/{package_id}/send")
async def send_package(
    request: Request,
    package_id: str,
    send_email_flag: bool = Form(True),
    db: Session = Depends(get_db)
):
    """Send intake package to client with automatic email."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        # Fetch package details with client and case info
        result = db.execute(text("""
            SELECT p.*, c.first_name, c.last_name, c.email,
                   cs.case_number, cs.case_name
            FROM intake_packages p
            LEFT JOIN clients c ON p.client_id = c.id
            LEFT JOIN cases cs ON p.case_id = cs.id
            WHERE p.package_id = :pid
        """), {"pid": package_id})
        package = result.fetchone()

        if not package:
            raise HTTPException(status_code=404, detail="Package not found")

        # Validate client has email
        if not package.email:
            raise HTTPException(
                status_code=400,
                detail="Client has no email address. Please add an email before sending."
            )

        # Generate intake link
        intake_link = intake_service.generate_client_link(package.package_id, package.access_token)

        # Send email if requested
        email_result = {"success": False, "email_sent": False}
        if send_email_flag:
            client_full_name = f"{package.first_name} {package.last_name}".strip()
            email_result = send_intake_email(
                client_email=package.email,
                client_name=client_full_name or "Client",
                package_name=package.name,
                intake_link=intake_link,
                expires_at=package.expires_at,
                package_id=package.package_id,
                case_number=package.case_number or "",
                validate_link=True  # CRITICAL: Validate link before sending
            )

            # If link validation failed, abort and show error
            if not email_result.get("link_validated", False):
                validation_error = email_result.get("validation_error", "Unknown error")
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot send - intake link is invalid: {validation_error}"
                )

            # If email sending failed, abort and show error
            if not email_result.get("email_sent", False):
                send_error = email_result.get("send_error", "Unknown error")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to send email: {send_error}"
                )

        # Only mark as "sent" if email was successfully sent (or sending was skipped)
        if email_result.get("email_sent", False) or not send_email_flag:
            db.execute(text("""
                UPDATE intake_packages
                SET status = :status, sent_at = NOW(), updated_at = NOW()
                WHERE package_id = :pid
            """), {"status": PackageStatus.SENT, "pid": package_id})
            db.commit()

            # Redirect with success message
            return RedirectResponse(
                url=f"{PREFIX}/intake/{package_id}?success=sent",
                status_code=302
            )
        else:
            # Should not reach here, but fallback
            raise HTTPException(status_code=500, detail="Unexpected error during send")

    except HTTPException:
        # Re-raise HTTP exceptions (validation errors, etc)
        raise

    except Exception as e:
        db.rollback()
        # Log unexpected errors
        import logging
        logging.exception(f"Unexpected error sending intake package {package_id}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/{package_id}/send-message")
async def send_message_to_client(
    request: Request,
    package_id: str,
    message: str = Form(...),
    send_email: bool = Form(True),
    send_whatsapp: bool = Form(False),
    db: Session = Depends(get_db)
):
    """Send a custom message to client about their intake package."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        # Import send_custom_message function
        from services.intake_email_service import send_custom_message

        # Fetch package details with client info
        result = db.execute(text("""
            SELECT p.*, c.first_name, c.last_name, c.email
            FROM intake_packages p
            LEFT JOIN clients c ON p.client_id = c.id
            WHERE p.package_id = :pid
        """), {"pid": package_id})
        package = result.fetchone()

        if not package:
            raise HTTPException(status_code=404, detail="Package not found")

        # Validate client has email if email sending is requested
        if send_email and not package.email:
            raise HTTPException(
                status_code=400,
                detail="Client has no email address. Cannot send message via email."
            )

        # Send message
        client_full_name = f"{package.first_name} {package.last_name}".strip()
        result = send_custom_message(
            client_email=package.email if send_email else "",
            client_name=client_full_name or "Client",
            message=message,
            package_id=package.package_id,
            send_via_email=send_email,
            send_via_whatsapp=send_whatsapp
        )

        if result.get("success"):
            return RedirectResponse(
                url=f"{PREFIX}/intake/{package_id}?success=message_sent",
                status_code=302
            )
        else:
            error_msg = result.get("error", "Unknown error")
            raise HTTPException(status_code=500, detail=f"Failed to send message: {error_msg}")

    except HTTPException:
        raise

    except Exception as e:
        import logging
        logging.exception(f"Error sending custom message for package {package_id}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.post("/{package_id}/item/{item_id}/status")
async def update_item_status(
    request: Request,
    package_id: str,
    item_id: int,
    status: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Update item status (for reviewing submissions)."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        db.execute(text("""
            UPDATE intake_items
            SET status = :status, notes = :notes, reviewed_at = NOW(), reviewed_by = :uid
            WHERE id = :item_id
              AND package_id IN (
                SELECT id FROM intake_packages WHERE org_id = :org_id
              )
        """), {
            "status": status,
            "notes": notes,
            "uid": user.id,
            "item_id": item_id,
            "org_id": user.org_id
        })

        # Check if all items are completed
        result = db.execute(text("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN status IN ('submitted', 'approved') THEN 1 ELSE 0 END) as done
            FROM intake_items
            WHERE package_id = (SELECT id FROM intake_packages WHERE package_id = :pid)
        """), {"pid": package_id})
        counts = result.fetchone()

        if counts.total == counts.done:
            db.execute(text("""
                UPDATE intake_packages
                SET status = :status, completed_at = NOW(), updated_at = NOW()
                WHERE package_id = :pid
            """), {"status": PackageStatus.COMPLETED, "pid": package_id})

        db.commit()

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/intake/{package_id}", status_code=302)


@router.post("/{package_id}/delete")
async def delete_package(
    request: Request,
    package_id: str,
    db: Session = Depends(get_db)
):
    """Delete an intake package."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        # Soft delete
        db.execute(text("UPDATE intake_packages SET status = 'deleted' WHERE package_id = :pid"),
                   {"pid": package_id})
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return RedirectResponse(url=f"{PREFIX}/intake", status_code=302)


# === API Endpoints ===

@router.get("/api/templates", response_class=JSONResponse)
async def get_templates(
    request: Request,
    db: Session = Depends(get_db)
):
    """API: Get available intake templates."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})

    templates_list = intake_service.get_available_templates()
    return JSONResponse(content=templates_list)


@router.get("/api/template/{visa_type}", response_class=JSONResponse)
async def get_template(
    request: Request,
    visa_type: str,
    db: Session = Depends(get_db)
):
    """API: Get template for a specific visa type."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})

    template = intake_service.get_template_for_visa(visa_type)
    return JSONResponse(content=template)


@router.get("/api/package/{package_id}/stats", response_class=JSONResponse)
async def get_package_stats(
    request: Request,
    package_id: str,
    db: Session = Depends(get_db)
):
    """API: Get package completion stats."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})

    try:
        result = db.execute(text("""
            SELECT status, required FROM intake_items
            WHERE package_id = (SELECT id FROM intake_packages WHERE package_id = :pid)
        """), {"pid": package_id})
        items = [{"status": row.status, "required": row.required} for row in result.fetchall()]
        completion = intake_service.calculate_completion(items)
        return JSONResponse(content=completion)
    except Exception as e:
        logger.error("Failed to get intake package completion: %s", e)
        return JSONResponse(status_code=404, content={"error": "Package not found"})


@router.get("/{package_id}/item/{item_id}/responses", response_class=HTMLResponse)
async def view_item_responses(
    request: Request,
    package_id: str,
    item_id: int,
    db: Session = Depends(get_db)
):
    """View responses for a specific intake item."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    try:
        # Get package info
        pkg_result = db.execute(text("""
            SELECT p.*, cl.first_name, cl.last_name
            FROM intake_packages p
            LEFT JOIN clients cl ON p.client_id = cl.id
            WHERE p.package_id = :pid
        """), {"pid": package_id})
        package = pkg_result.fetchone()

        if not package:
            raise HTTPException(status_code=404, detail="Package not found")

        # Get item info with template
        item_result = db.execute(text("""
            SELECT i.*, qt.name as template_name
            FROM intake_items i
            LEFT JOIN questionnaire_templates qt ON i.questionnaire_id = qt.id
            WHERE i.id = :iid
        """), {"iid": item_id})
        item = item_result.fetchone()

        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        # Get fields for this template
        fields = []
        if item.questionnaire_id:
            fields_result = db.execute(text("""
                SELECT field_name, label, field_type, section
                FROM questionnaire_fields
                WHERE template_id = :tid
                ORDER BY section, "order"
            """), {"tid": item.questionnaire_id})
            fields = fields_result.fetchall()

        # Get all responses for this item
        responses_result = db.execute(text("""
            SELECT * FROM intake_responses
            WHERE item_id = :iid
            ORDER BY submitted_at DESC
        """), {"iid": item_id})
        responses = responses_result.fetchall()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return templates.TemplateResponse("app/intake/responses.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "package": package,
        "item": item,
        "fields": fields,
        "responses": responses
    })
