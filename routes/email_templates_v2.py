"""
CaseHub - Email Templates API v2
Structured templates with placeholders and multilingual support
"""
from fastapi import APIRouter, Query, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import json
import logging
import os
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

from models import get_db, Client, Case
from auth import get_current_user
from models.tenant import tenant_query
from config import settings

router = APIRouter(prefix="/api/v2", tags=["templates-v2"])

# Path to templates file
TEMPLATES_PATH = Path(os.path.join(settings.BASE_DIR, "data", "email_templates_v2.json"))

# Cache
_templates_cache = None
_templates_mtime = None


def load_templates():
    """Load templates from JSON file with caching"""
    global _templates_cache, _templates_mtime

    try:
        current_mtime = os.path.getmtime(TEMPLATES_PATH)
        if _templates_cache is not None and _templates_mtime == current_mtime:
            return _templates_cache
        _templates_mtime = current_mtime
    except Exception as e:
        logger.error("Failed to check templates file mtime: %s", e)

    try:
        with open(TEMPLATES_PATH, 'r', encoding='utf-8') as f:
            _templates_cache = json.load(f)
            return _templates_cache
    except Exception as e:
        logger.error("Error loading templates: %s", e)
        return {"categories": [], "templates": {}}


@router.get("/email-templates")
async def get_all_templates(
    request: Request,
    lang: str = Query("en", description="Language: en, pt, or es"),
    category: Optional[str] = Query(None, description="Filter by category"),
    db: Session = Depends(get_db)
):
    """
    Get all email templates with optional filtering.

    Returns templates organized by category with preview support.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    data = load_templates()
    templates = data.get("templates", {})
    categories = data.get("categories", [])

    # Filter by category if specified
    if category:
        templates = {k: v for k, v in templates.items() if v.get("category") == category}

    # Format for frontend
    result = {}
    for key, template in templates.items():
        subject = template.get("subject", {})
        body = template.get("body", {})

        result[key] = {
            "id": template.get("id", key),
            "name": template.get("name", key),
            "category": template.get("category", "general"),
            "subject": subject.get(lang, subject.get("en", "")),
            "body": body.get(lang, body.get("en", "")),
            "placeholders": template.get("placeholders", []),
            "all_subjects": subject,
            "all_bodies": body
        }

    return JSONResponse({
        "success": True,
        "templates": result,
        "categories": categories,
        "languages": ["en", "pt", "es"],
        "current_language": lang,
        "count": len(result)
    })


@router.get("/email-templates/{template_id}")
async def get_single_template(
    template_id: str,
    request: Request,
    lang: str = Query("en"),
    db: Session = Depends(get_db)
):
    """Get a single template by ID"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    data = load_templates()
    templates = data.get("templates", {})

    if template_id not in templates:
        return JSONResponse({
            "success": False,
            "error": f"Template '{template_id}' not found"
        }, status_code=404)

    template = templates[template_id]
    subject = template.get("subject", {})
    body = template.get("body", {})

    return JSONResponse({
        "success": True,
        "template": {
            "id": template.get("id", template_id),
            "name": template.get("name", template_id),
            "category": template.get("category", "general"),
            "subject": subject.get(lang, subject.get("en", "")),
            "body": body.get(lang, body.get("en", "")),
            "placeholders": template.get("placeholders", []),
            "all_languages": {
                "en": {"subject": subject.get("en", ""), "body": body.get("en", "")},
                "pt": {"subject": subject.get("pt", ""), "body": body.get("pt", "")},
                "es": {"subject": subject.get("es", ""), "body": body.get("es", "")}
            }
        }
    })


@router.get("/email-templates/preview/{template_id}")
async def preview_template(
    template_id: str,
    request: Request,
    lang: str = Query("en"),
    client_id: Optional[int] = Query(None),
    case_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Get template with placeholders filled from client/case data.

    This provides a live preview with real data.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    data = load_templates()
    templates = data.get("templates", {})

    if template_id not in templates:
        return JSONResponse({
            "success": False,
            "error": f"Template '{template_id}' not found"
        }, status_code=404)

    template = templates[template_id]
    subject = template.get("subject", {}).get(lang, "")
    body = template.get("body", {}).get(lang, "")

    # Build placeholder values
    placeholders = {}

    # Get client data
    if client_id:
        client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
        if client:
            placeholders["client_name"] = f"{client.first_name} {client.last_name}"
            placeholders["client_email"] = client.email or ""
            placeholders["client_phone"] = client.phone or ""

    # Get case data — Sentinela T3 (2026-05-28): filter por org_id pra evitar
    # IDOR cross-tenant (linha 184 já usa tenant_query() pra clients; cases
    # estava quebrando o padrão). CWE-639.
    if case_id:
        from sqlalchemy import text
        result = db.execute(
            text("SELECT * FROM cases WHERE id = :id AND org_id = :org_id"),
            {"id": case_id, "org_id": request.state.org_id},
        ).fetchone()
        if result:
            placeholders["case_number"] = result.case_number or ""
            placeholders["visa_type"] = result.visa_type or ""
            placeholders["status"] = result.status or ""
            if result.filing_date:
                placeholders["filing_date"] = result.filing_date.strftime("%B %d, %Y")

    # Replace placeholders in subject and body
    preview_subject = subject
    preview_body = body

    for key, value in placeholders.items():
        preview_subject = preview_subject.replace(f"{{{key}}}", value)
        preview_body = preview_body.replace(f"{{{key}}}", value)

    # Mark remaining placeholders
    for placeholder in template.get("placeholders", []):
        if f"{{{placeholder}}}" in preview_body:
            preview_body = preview_body.replace(f"{{{placeholder}}}", f"[{placeholder}]")
        if f"{{{placeholder}}}" in preview_subject:
            preview_subject = preview_subject.replace(f"{{{placeholder}}}", f"[{placeholder}]")

    return JSONResponse({
        "success": True,
        "preview": {
            "subject": preview_subject,
            "body": preview_body,
            "filled_placeholders": placeholders,
            "remaining_placeholders": [
                p for p in template.get("placeholders", [])
                if p not in placeholders
            ]
        }
    })


@router.get("/compose-context")
async def get_compose_context(
    request: Request,
    client_id: Optional[int] = Query(None),
    case_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Get contextual data for email compose.

    Returns client info, case info, pending tasks, and suggested templates.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    from sqlalchemy import text

    context = {
        "client": None,
        "case": None,
        "pending_tasks": [],
        "recent_emails": [],
        "suggested_templates": []
    }

    # Get client data
    if client_id:
        client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
        if client:
            context["client"] = {
                "id": client.id,
                "name": f"{client.first_name} {client.last_name}",
                "email": client.email,
                "phone": client.phone,
                "country": client.country_of_origin
            }

    # Get case data
    if case_id:
        result = db.execute(text("""
            SELECT c.*, cl.first_name, cl.last_name, cl.email
            FROM cases c
            LEFT JOIN clients cl ON c.client_id = cl.id
            WHERE c.id = :id AND c.org_id = :org_id
        """), {"id": case_id, "org_id": request.state.org_id}).fetchone()

        if result:
            context["case"] = {
                "id": result.id,
                "case_number": result.case_number,
                "case_name": result.case_name,
                "visa_type": result.visa_type,
                "status": result.status,
                "client_name": f"{result.first_name} {result.last_name}" if result.first_name else None,
                "client_email": result.email
            }

            if not client_id and result.client_id:
                client = tenant_query(db, Client, request.state.org_id).filter(Client.id == result.client_id).first()
                if client:
                    context["client"] = {
                        "id": client.id,
                        "name": f"{client.first_name} {client.last_name}",
                        "email": client.email,
                        "phone": client.phone,
                        "country": client.country_of_origin
                    }

    # Get pending tasks for this case/client
    try:
        # Sentinela T4 (2026-05-28): filter por org_id pra evitar IDOR
        # cross-tenant — tasks raw query não escopava por org. CWE-639.
        task_query = "SELECT id, title, due_date, priority FROM tasks WHERE completed = FALSE AND org_id = :org_id"
        params = {"org_id": request.state.org_id}

        if case_id:
            task_query += " AND case_id = :case_id"
            params["case_id"] = case_id
        elif client_id:
            task_query += " AND client_id = :client_id"
            params["client_id"] = client_id

        task_query += " ORDER BY due_date ASC LIMIT 5"

        tasks = db.execute(text(task_query), params).fetchall()
        context["pending_tasks"] = [
            {
                "id": t.id,
                "title": t.title,
                "due_date": t.due_date.strftime("%Y-%m-%d") if t.due_date else None,
                "priority": t.priority
            }
            for t in tasks
        ]
    except Exception as e:
        logger.error("Failed to fetch tasks for template context: %s", e)

    # Suggest templates based on context
    if context["case"]:
        status = context["case"].get("status", "").lower()
        if status == "rfe":
            context["suggested_templates"] = ["rfe_notification", "document_request"]
        elif status == "approved":
            context["suggested_templates"] = ["case_approved"]
        elif status == "filed":
            context["suggested_templates"] = ["case_filed", "case_status_update"]
        else:
            context["suggested_templates"] = ["case_status_update", "document_request"]
    else:
        context["suggested_templates"] = ["weekly_checkin", "document_request"]

    return JSONResponse({
        "success": True,
        "context": context
    })


# =============================================================================
# EMAIL SIGNATURES
# =============================================================================

# Email signatures are now dynamically built from settings.
# Staff-specific signatures should be managed in the DB or admin UI.
# This provides a default "team" signature using config values.
def _build_default_signatures():
    """Build default email signatures from settings."""
    org = settings.ORG_NAME
    email = settings.ORG_EMAIL or settings.SMTP_USER
    domain = settings.ORG_DOMAIN
    web_url = f"https://{domain}" if domain else settings.BASE_URL

    return {
        "team": {
            "id": "team",
            "name": f"{org} Team",
            "html": f"""<div style="margin-top:20px; padding-top:15px; border-top:1px solid #ddd; font-family:Arial,sans-serif; font-size:13px; color:#333;">
<p style="margin:0 0 3px;"><strong>{org}</strong></p>
<p style="margin:0; color:#666;">Web: <a href="{web_url}" style="color:#4a90d9;">{domain or web_url}</a></p>
</div>""",
            "text": f"\n\n--\n{org}\nWeb: {domain or web_url}"
        },
    }

EMAIL_SIGNATURES = _build_default_signatures()


@router.get("/email-signatures")
async def get_email_signatures(request: Request, db: Session = Depends(get_db)):
    """Get all available email signatures"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    signatures = [
        {"id": s["id"], "name": s["name"]}
        for s in EMAIL_SIGNATURES.values()
    ]
    return JSONResponse({"success": True, "signatures": signatures})


@router.get("/email-signatures/{sig_id}")
async def get_email_signature(sig_id: str, request: Request, db: Session = Depends(get_db)):
    """Get a specific email signature"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    sig = EMAIL_SIGNATURES.get(sig_id)
    if not sig:
        return JSONResponse({"error": "Signature not found"}, status_code=404)

    return JSONResponse({"success": True, "signature": sig})
