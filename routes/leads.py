"""
CaseHub - Leads CRM Routes (Main CRUD + Pages)
API endpoints for leads CRUD, webhook, conversions, sync, and HTML pages.

Sub-routers are included from:
  - leads_scoring: scoring, deals, templates, intelligence, surveillance
  - leads_analytics: metrics, pipeline stats, trends, analytics dashboards
"""
import os
import logging
import traceback
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, Request, HTTPException, Header, Query
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from models import get_db, Client, Case
from auth import get_current_user
from config import settings

logger = logging.getLogger(__name__)

# Import leads_manager from services
from services import leads_manager

# Integration imports
try:
    from services.notion_tasks import notion_tasks_service
except Exception:
    notion_tasks_service = None

try:
    from scripts.create_meeting import create_attorney_meeting, get_calendar_service
    from datetime import datetime as dt_cls
except Exception:
    create_attorney_meeting = None
    get_calendar_service = None

# Import whatsapp_db for conversations endpoint
try:
    import whatsapp_db
except ImportError:
    whatsapp_db = None

# Webhook API key (for WhatsApp bot + internal n8n calls)
WEBHOOK_API_KEY = os.getenv("CRM_WEBHOOK_API_KEY", "")

router = APIRouter(prefix="/api/leads", tags=["leads"])

# ---------------------------------------------------------------------------
# Include sub-routers (scoring + analytics)
# They share the same /api/leads prefix so endpoints merge seamlessly.
# ---------------------------------------------------------------------------
from routes.leads_scoring import router as scoring_router
from routes.leads_analytics import router as analytics_router

router.include_router(scoring_router, prefix="")
router.include_router(analytics_router, prefix="")


# =============================================================================
# HELPERS
# =============================================================================

class _InternalUser:
    """Sentinel user for internal API key access (n8n, etc.)."""
    email = "system@internal"
    name = "System"
    role = "admin"

def require_user(request: Request, db: Session):
    """Require authenticated user or internal API key, or raise 401."""
    api_key = request.headers.get("x-api-key")
    if api_key and api_key == WEBHOOK_API_KEY:
        return _InternalUser()
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def verify_api_key(x_api_key: str = Header(None)):
    """Verify webhook API key."""
    if not x_api_key or x_api_key != WEBHOOK_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


# =============================================================================
# WEBHOOK (WhatsApp bot dual-write)
# =============================================================================

@router.post("/webhook")
async def leads_webhook(request: Request, _: bool = Depends(verify_api_key)):
    """
    Webhook endpoint for WhatsApp bot to create/update leads.
    Authenticated via X-API-Key header.
    """
    try:
        body = await request.json()
        data = leads_manager.load_leads()
        lead = leads_manager.upsert_from_webhook(data, body)
        leads_manager.save_leads(data)

        lead_id = lead.get("id", "unknown")
        phone = body.get("phone", "no-phone")
        logger.info(f"Webhook: lead upserted - {lead_id} ({phone})")

        return JSONResponse({
            "status": "ok",
            "lead_id": lead_id,
            "action": "upserted",
        })
    except ValueError as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=400)
    except Exception as e:
        logger.error(f"Webhook error: {traceback.format_exc()}")
        return JSONResponse({"status": "error", "message": repr(e)}, status_code=500)


# =============================================================================
# CRUD ENDPOINTS (session auth)
# =============================================================================

@router.get("")
async def list_leads(
    request: Request,
    search: Optional[str] = None,
    stage: Optional[str] = None,
    source: Optional[str] = None,
    status: Optional[str] = None,
    lead_status: Optional[str] = None,
    score_min: Optional[int] = None,
    score_max: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    sort_by: str = "updated_at",
    sort_order: str = "desc",
    page: int = 1,
    per_page: int = 50,
    db: Session = Depends(get_db),
):
    """List leads with filters, search, sorting, and pagination."""
    user = require_user(request, db)
    data = leads_manager.load_leads()
    leads, total = leads_manager.get_all_leads(
        data, search=search, stage=stage, source=source,
        status=status, lead_status=lead_status,
        score_min=score_min, score_max=score_max,
        date_from=date_from, date_to=date_to,
        sort_by=sort_by, sort_order=sort_order,
        page=page, per_page=per_page,
    )
    return {
        "leads": leads,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


# =============================================================================
# PHASE 2 ENDPOINTS (follow-up, assign, activity, overdue, duplicates)
# =============================================================================

@router.get("/overdue")
async def get_overdue(request: Request, db: Session = Depends(get_db)):
    """Get leads with overdue follow-ups."""
    user = require_user(request, db)
    data = leads_manager.load_leads()
    return {"overdue": leads_manager.get_overdue_follow_ups(data)}


@router.get("/duplicates")
async def check_duplicates(
    request: Request,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Check for duplicate leads by phone or email."""
    user = require_user(request, db)
    data = leads_manager.load_leads()
    return {"duplicates": leads_manager.check_duplicates(data, phone=phone, email=email)}


# =============================================================================
# ADDITIONAL ENDPOINTS (export, bulk)
# =============================================================================

@router.get("/export")
async def export_leads(
    request: Request,
    stage: Optional[str] = None,
    source: Optional[str] = None,
    lead_status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Export leads as CSV."""
    user = require_user(request, db)
    data = leads_manager.load_leads()
    leads = [l for l in data["leads"].values() if not l.get("is_deleted")]
    if stage:
        leads = [l for l in leads if l.get("pipeline_stage") == stage]
    if source:
        leads = [l for l in leads if l.get("source") == source]
    if lead_status:
        leads = [l for l in leads if l.get("lead_status") == lead_status]

    import csv
    import io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Name", "Phone", "Email", "Source", "Stage", "Score", "Status",
        "Visa Interest", "Created", "Updated", "Notes"
    ])
    for l in leads:
        writer.writerow([
            l.get("name", ""), l.get("phone", ""), l.get("email", ""),
            l.get("source", ""), l.get("pipeline_stage", ""),
            l.get("lead_score", 0), l.get("lead_status", ""),
            l.get("visa_interest", ""), l.get("created_at", ""),
            l.get("updated_at", ""), (l.get("notes", "") or "")[:200],
        ])

    from fastapi.responses import Response
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads_export.csv"}
    )


@router.post("/bulk")
async def bulk_operation(request: Request, db: Session = Depends(get_db)):
    """Bulk update or delete leads."""
    user = require_user(request, db)
    body = await request.json()
    lead_ids = body.get("lead_ids", [])
    action = body.get("action")

    if not lead_ids or not action:
        raise HTTPException(status_code=400, detail="Missing lead_ids or action")

    data = leads_manager.load_leads()

    if action == "delete":
        deleted = 0
        for lid in lead_ids:
            try:
                leads_manager.delete_lead(data, lid)
                deleted += 1
            except Exception:
                pass
        leads_manager.save_leads(data)
        logger.info(f"Bulk delete: {deleted} leads by {user.email}")
        return {"deleted": deleted}

    elif action == "update":
        updates = body.get("updates", {})
        updated = 0
        for lid in lead_ids:
            try:
                leads_manager.update_lead(data, lid, updates)
                updated += 1
            except Exception:
                pass
        leads_manager.save_leads(data)
        logger.info(f"Bulk update: {updated} leads by {user.email}")
        return {"updated": updated}

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")


# =============================================================================
# SYNC ENDPOINTS
# =============================================================================

@router.post("/sync/moskit")
async def sync_moskit(request: Request, db: Session = Depends(get_db)):
    """Trigger Moskit CRM sync."""
    user = require_user(request, db)
    data = leads_manager.load_leads()
    result = await leads_manager.sync_from_moskit(data)
    leads_manager.save_leads(data)
    logger.info(f"Moskit sync triggered by {user.email}: {result}")
    return result


@router.post("/sync/notion")
async def sync_notion(request: Request, db: Session = Depends(get_db)):
    """Trigger Notion sync."""
    user = require_user(request, db)
    data = leads_manager.load_leads()
    result = await leads_manager.sync_all_to_notion(data)
    leads_manager.save_leads(data)
    logger.info(f"Notion sync triggered by {user.email}: {result}")
    return result


# =============================================================================
# SINGLE-LEAD ENDPOINTS (must come after non-parameterized routes)
# =============================================================================

@router.get("/{lead_id}")
async def get_lead(request: Request, lead_id: str, db: Session = Depends(get_db)):
    """Get a single lead by ID."""
    user = require_user(request, db)
    data = leads_manager.load_leads()
    if lead_id not in data["leads"]:
        raise HTTPException(status_code=404, detail="Lead not found")
    return data["leads"][lead_id]


@router.post("")
async def create_lead(request: Request, db: Session = Depends(get_db)):
    """Create a new lead."""
    user = require_user(request, db)
    body = await request.json()
    data = leads_manager.load_leads()
    lead = leads_manager.create_lead(data, body)
    leads_manager.save_leads(data)
    logger.info(f"Lead {lead['id']} created by {user.email}")
    return lead


@router.put("/{lead_id}")
async def update_lead_endpoint(request: Request, lead_id: str, db: Session = Depends(get_db)):
    """Update an existing lead."""
    user = require_user(request, db)
    body = await request.json()
    data = leads_manager.load_leads()
    try:
        lead = leads_manager.update_lead(data, lead_id, body)
        leads_manager.save_leads(data)
        logger.info(f"Lead {lead_id} updated by {user.email}")
        return lead
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{lead_id}")
async def delete_lead_endpoint(request: Request, lead_id: str, db: Session = Depends(get_db)):
    """Soft-delete a lead."""
    user = require_user(request, db)
    data = leads_manager.load_leads()
    try:
        leads_manager.delete_lead(data, lead_id)
        leads_manager.save_leads(data)
        logger.info(f"Lead {lead_id} deleted by {user.email}")
        return {"status": "ok", "lead_id": lead_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{lead_id}/notes")
async def add_note(request: Request, lead_id: str, db: Session = Depends(get_db)):
    """Add a note to a lead."""
    user = require_user(request, db)
    body = await request.json()
    data = leads_manager.load_leads()
    try:
        entry = leads_manager.add_note(
            data, lead_id,
            content=body.get("content", ""),
            note_type=body.get("type", "note"),
            actor=user.email,
        )
        leads_manager.save_leads(data)
        return entry
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{lead_id}/follow-up")
async def schedule_follow_up(request: Request, lead_id: str, db: Session = Depends(get_db)):
    """Schedule a follow-up for a lead."""
    user = require_user(request, db)
    body = await request.json()
    date = body.get("date")
    note = body.get("note", "")
    if not date:
        raise HTTPException(status_code=400, detail="Date is required")
    data = leads_manager.load_leads()
    try:
        lead = leads_manager.schedule_follow_up(data, lead_id, date, note, actor=user.email)
        leads_manager.save_leads(data)
        logger.info(f"Follow-up scheduled for lead {lead_id} on {date} by {user.email}")
        return {"status": "ok", "follow_up_date": date}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{lead_id}/assign")
async def assign_lead(request: Request, lead_id: str, db: Session = Depends(get_db)):
    """Assign a lead to a team member."""
    user = require_user(request, db)
    body = await request.json()
    assignee = body.get("assignee")
    if not assignee:
        raise HTTPException(status_code=400, detail="Assignee is required")
    data = leads_manager.load_leads()
    try:
        lead = leads_manager.assign_lead(data, lead_id, assignee, actor=user.email)
        leads_manager.save_leads(data)
        logger.info(f"Lead {lead_id} assigned to {assignee} by {user.email}")
        return lead
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{lead_id}/activity")
async def get_activity(request: Request, lead_id: str, db: Session = Depends(get_db)):
    """Get merged activity timeline for a lead."""
    user = require_user(request, db)
    data = leads_manager.load_leads()
    try:
        timeline = leads_manager.get_activity_timeline(data, lead_id)
        return {"timeline": timeline}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{lead_id}/convert")
async def convert_lead(request: Request, lead_id: str, db: Session = Depends(get_db)):
    """Convert a lead to a CaseHub client (and optionally create a case)."""
    user = require_user(request, db)
    body = await request.json()
    create_case = body.get("create_case", False)

    data = leads_manager.load_leads()
    if lead_id not in data["leads"]:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead = data["leads"][lead_id]

    # Check if already converted
    if lead.get("status") == "converted" and lead.get("converted_client_id"):
        raise HTTPException(status_code=400, detail=f"Lead already converted to Client #{lead['converted_client_id']}")

    # Parse name into first_name / last_name
    name = lead.get("name", "") or lead.get("whatsapp_name", "") or "Unknown"
    name_parts = name.strip().split()
    first_name = name_parts[0] if name_parts else "Unknown"
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

    # Create Client in SQLAlchemy DB
    client = Client(
        first_name=first_name,
        last_name=last_name or first_name,
        email=lead.get("email", ""),
        phone=lead.get("phone", ""),
        whatsapp=lead.get("phone", ""),
        country_of_origin=lead.get("language", ""),
        notes=f"Converted from Lead CRM. Source: {lead.get('source', '')}. Score: {lead.get('lead_score', 0)}. Visa interest: {lead.get('visa_interest', '')}",
        status="active",
        org_id=request.state.org_id,
    )
    db.add(client)
    db.flush()  # Get the client ID

    case_id = None
    if create_case and lead.get("visa_interest"):
        case = Case(
            client_id=client.id,
            case_number=f"{settings.CASE_PREFIX}-{client.id:04d}",
            case_name=f"{first_name} {last_name} - {lead.get('visa_interest', 'Unknown')} case".strip(),
            visa_type=lead.get("visa_interest", ""),
            status="intake",
            priority="medium",
            notes=f"Auto-created from Lead CRM conversion",
            org_id=request.state.org_id,
        )
        db.add(case)
        db.flush()
        case_id = case.id

    db.commit()

    # Mark lead as converted
    leads_manager.mark_as_converted(data, lead_id, client_id=client.id, case_id=case_id, actor=user.email)
    leads_manager.save_leads(data)

    logger.info(f"Lead {lead_id} converted to Client #{client.id} by {user.email}" + (f" with Case #{case_id}" if case_id else ""))

    return {
        "status": "converted",
        "client_id": client.id,
        "case_id": case_id,
        "client_name": f"{first_name} {last_name}".strip(),
    }


@router.post("/{lead_id}/task")
async def create_notion_task(request: Request, lead_id: str, db: Session = Depends(get_db)):
    """Create a Notion task from a lead."""
    user = require_user(request, db)
    if not notion_tasks_service:
        raise HTTPException(status_code=503, detail="Notion integration not available")

    body = await request.json()
    title = body.get("title", "")
    assignee = body.get("assignee", "")
    due_date = body.get("due_date")
    description = body.get("description", "")

    if not title:
        raise HTTPException(status_code=400, detail="Title is required")

    # Map assignee to database key
    assignee_map = {
        "membro a": "member_a",
        "member a": "member_a",
        "member_a": "member_a",
        "membro b": "member_b",
        "member b": "member_b",
        "member_b": "member_b",
    }
    db_key = assignee_map.get(str(assignee).strip().lower(), "member_b")

    # Load lead data for context
    data = leads_manager.load_leads()
    if lead_id not in data["leads"]:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead = data["leads"][lead_id]

    # Build task data
    task_data = {
        "title": title,
        "description": description or f"Lead: {lead.get('name', 'Unknown')} | Phone: {lead.get('phone', '-')} | Source: {lead.get('source', '-')}",
        "status": "Not started",
        "priority": "Alta" if (lead.get("lead_score", 0) >= 70) else "Normal",
    }
    if due_date:
        task_data["due_date"] = due_date
    if lead.get("visa_interest"):
        task_data["visa_type"] = lead["visa_interest"]

    try:
        result = notion_tasks_service.create_task_with_notification(db_key, task_data, notify=True)
        task_result = result.get("task", {})

        if "error" in task_result:
            raise HTTPException(status_code=500, detail=task_result["error"])

        # Log in lead activity
        if "communication_log" not in lead:
            lead["communication_log"] = []
        lead["communication_log"].append({
            "timestamp": leads_manager.datetime.now().isoformat(),
            "type": "task",
            "direction": "internal",
            "summary": f"Notion task created: {title} (assigned to {assignee})",
            "actor": user.email,
        })
        lead["last_activity_at"] = leads_manager.datetime.now().isoformat()
        leads_manager.save_leads(data)

        notion_url = task_result.get("url", "")
        notion_id = task_result.get("id", "")
        logger.info(f"Notion task created for lead {lead_id}: {title} by {user.email}")
        return {
            "status": "ok",
            "notion_id": notion_id,
            "notion_url": notion_url,
            "title": title,
            "assignee": assignee,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Notion task creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{lead_id}/calendar")
async def create_calendar_event(request: Request, lead_id: str, db: Session = Depends(get_db)):
    """Create a Google Calendar event for a lead follow-up."""
    user = require_user(request, db)
    if not create_attorney_meeting or not get_calendar_service:
        raise HTTPException(status_code=503, detail="Calendar integration not available")

    body = await request.json()
    event_date = body.get("date")  # ISO date string YYYY-MM-DD
    event_time = body.get("time", "11:00")  # HH:MM
    duration = body.get("duration", 30)
    title = body.get("title", "")
    description = body.get("description", "")

    if not event_date:
        raise HTTPException(status_code=400, detail="Date is required")

    data = leads_manager.load_leads()
    if lead_id not in data["leads"]:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead = data["leads"][lead_id]

    lead_name = lead.get("name") or lead.get("whatsapp_name") or "Unknown Lead"
    if not title:
        title = f"Follow-up: {lead_name}"

    # Parse date and time
    try:
        start_dt = dt_cls.strptime(f"{event_date} {event_time}", "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date/time format")

    # Build description with lead info
    full_desc = description + "\n\nLead: " + lead_name + "\nPhone: " + lead.get("phone", "-") + "\nEmail: " + lead.get("email", "-") + "\nSource: " + lead.get("source", "-") + "\nStage: " + lead.get("pipeline_stage", "-") + "\nScore: " + str(lead.get("lead_score", 0))

    # Determine attendees (never include client)
    attendees = [e for e in [settings.ORG_CENTER_EMAIL, settings.ORG_EMAIL] if e]
    assigned = lead.get("assigned_to")
    # TODO: Move team email mapping to DB or settings
    team_emails = {}
    if assigned and assigned in team_emails:
        attendees.append(team_emails[assigned])

    try:
        result = create_attorney_meeting(
            client_name=lead_name,
            start_datetime=start_dt,
            duration_minutes=int(duration),
            attendees=attendees,
            description=full_desc.strip(),
        )

        if not result or not result.get("success"):
            error_msg = result.get("error", "Unknown error") if result else "Calendar service unavailable"
            raise HTTPException(status_code=500, detail=error_msg)

        # Also save follow-up in lead data
        lead["follow_up_date"] = event_date
        lead["follow_up_note"] = title
        if "communication_log" not in lead:
            lead["communication_log"] = []
        lead["communication_log"].append({
            "timestamp": leads_manager.datetime.now().isoformat(),
            "type": "calendar",
            "direction": "internal",
            "summary": f"Calendar event created: {title} on {event_date} {event_time}",
            "actor": user.email,
        })
        lead["last_activity_at"] = leads_manager.datetime.now().isoformat()
        leads_manager.save_leads(data)

        logger.info(f"Calendar event created for lead {lead_id}: {title} by {user.email}")
        return {
            "status": "ok",
            "event_id": result.get("event_id"),
            "meet_link": result.get("meet_link", ""),
            "html_link": result.get("html_link", ""),
            "title": title,
            "date": event_date,
            "time": event_time,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Calendar event creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{lead_id}/stage")
async def update_stage(request: Request, lead_id: str, db: Session = Depends(get_db)):
    """Update lead pipeline stage (for kanban drag-and-drop)."""
    user = require_user(request, db)
    body = await request.json()
    stage = body.get("stage")
    if stage not in leads_manager.VALID_STAGES:
        raise HTTPException(status_code=400, detail=f"Invalid stage: {stage}")
    data = leads_manager.load_leads()
    try:
        lead = leads_manager.update_lead(data, lead_id, {"pipeline_stage": stage})
        leads_manager.save_leads(data)
        logger.info(f"Lead {lead_id} moved to {stage} by {user.email}")
        return lead
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{lead_id}/conversations")
async def get_lead_conversations(request: Request, lead_id: str, db: Session = Depends(get_db)):
    """Get aggregated conversations (WhatsApp + Email) for a lead."""
    user = require_user(request, db)

    data = leads_manager.load_leads()
    if lead_id not in data["leads"]:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead = data["leads"][lead_id]
    phone = lead.get("phone", "")
    email = lead.get("email", "")
    messages = []

    # Get WhatsApp conversations
    if phone and whatsapp_db:
        try:
            wp_convs = whatsapp_db.get_conversations(phone, limit=50)
            for msg in wp_convs:
                messages.append({
                    "channel": "whatsapp",
                    "timestamp": msg.get("timestamp") or msg.get("created_at"),
                    "content": msg.get("content") or msg.get("message"),
                    "direction": "outbound" if (msg.get("from_me") or msg.get("role") == "assistant") else "inbound",
                    "from_me": msg.get("from_me", False) or msg.get("role") == "assistant",
                })
        except Exception as e:
            logger.warning(f"Error fetching WhatsApp for {lead_id}: {e}")

    # Get Email threads/messages
    if email:
        try:
            from communications import load_email_threads
            email_data = load_email_threads()
            all_messages = email_data.get("messages", [])

            # Filter messages where lead's email appears in from/to
            for msg in all_messages:
                msg_from = (msg.get("from") or "").lower()
                msg_to = (msg.get("to") or "").lower()
                if email.lower() in msg_from or email.lower() in msg_to:
                    _org_domain = (settings.ORG_DOMAIN or "").lower()
                    is_outbound = (_org_domain and _org_domain in msg_from) or (settings.ORG_EMAIL and settings.ORG_EMAIL.lower() in msg_from)
                    messages.append({
                        "channel": "email",
                        "timestamp": msg.get("sent_at") or msg.get("received_at"),
                        "content": msg.get("body") or msg.get("snippet") or msg.get("subject", ""),
                        "direction": "outbound" if is_outbound else "inbound",
                        "from_me": is_outbound,
                        "subject": msg.get("subject", ""),
                    })
        except Exception as e:
            logger.warning(f"Error fetching emails for {lead_id}: {e}")

    # Sort all messages by timestamp (newest first)
    messages.sort(key=lambda x: x.get("timestamp") or "", reverse=True)

    return {
        "lead_id": lead_id,
        "phone": phone,
        "email": email,
        "messages": messages[:100],  # Limit to 100 messages
        "total_count": len(messages),
    }


@router.get("/{lead_id}/whatsapp")
async def get_lead_whatsapp_data(request: Request, lead_id: str, db: Session = Depends(get_db)):
    """Get WhatsApp conversation history and data for a lead."""
    user = require_user(request, db)

    if not whatsapp_db:
        raise HTTPException(status_code=503, detail="WhatsApp integration not available")

    data = leads_manager.load_leads()
    if lead_id not in data["leads"]:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead = data["leads"][lead_id]
    phone = lead.get("phone")

    if not phone:
        return {"error": "Lead has no phone number", "conversations": [], "lead": None}

    try:
        whatsapp_data = whatsapp_db.get_whatsapp_data_for_lead(phone)
        return whatsapp_data
    except Exception as e:
        logger.error(f"Error fetching WhatsApp data for {lead_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# HTML PAGE ROUTES (separate router for pages)
# =============================================================================

from fastapi.responses import HTMLResponse
from core.template_config import inject_org_context, templates
from i18n import get_translations

pages_router = APIRouter(prefix="/leads", tags=["leads-pages"])

PREFIX = settings.PREFIX


@pages_router.get("", response_class=HTMLResponse)
async def leads_dashboard_page(request: Request, db: Session = Depends(get_db)):
    """Leads CRM dashboard page."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    data = leads_manager.load_leads()
    active = [l for l in data["leads"].values() if not l.get("is_deleted")]

    lang = request.cookies.get("lang", "en")
    team_members = [m.strip() for m in settings.TEAM_MEMBERS.split(",") if m.strip()] if settings.TEAM_MEMBERS else []
    product = getattr(getattr(request, "app", None), "state", None)
    product_name = getattr(product, "product", settings.CASEHUB_PRODUCT) if product else settings.CASEHUB_PRODUCT
    return templates.TemplateResponse("app/leads/dashboard.html", {
        **inject_org_context(request, user),
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "product": product_name,
        "lang": lang,
        "t": get_translations(lang),
        "total_leads": len(active),
        "team_members": team_members,
    })
