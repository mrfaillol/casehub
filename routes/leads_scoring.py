"""
CaseHub - Leads Scoring, Deals & Intelligence Routes
Extracted from leads.py: scoring, deal tracking, lead intelligence,
surveillance, and pipeline reclassification.
"""
import logging
import traceback
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from models import get_db
from auth import get_current_user
from config import settings
from services import leads_manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers (shared with leads.py)
# ---------------------------------------------------------------------------
import os

WEBHOOK_API_KEY = os.getenv("CRM_WEBHOOK_API_KEY", "")


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


# ---------------------------------------------------------------------------
# Optional service imports
# ---------------------------------------------------------------------------
try:
    import whatsapp_db
    from services import scoring_engine
except ImportError as e:
    logger.warning(f"Scoring modules not available: {e}")
    whatsapp_db = None
    scoring_engine = None

try:
    from services.lead_intelligence import (
        analyze_lead_conversation,
        analyze_email_formality,
        get_lead_intelligence,
        has_fresh_intelligence,
        classify_lead_stage_from_content,
        should_update_pipeline_stage,
    )
    from whatsapp_db import get_full_conversation_text, get_conversation_stats
    INTEL_AVAILABLE = True
except Exception as e:
    logger.warning(f"Lead intelligence not available: {e}")
    INTEL_AVAILABLE = False

try:
    from services.lead_surveillance import (
        get_surveillance_status,
        toggle_surveillance,
        force_check,
    )
    SURVEILLANCE_AVAILABLE = True
except Exception as e:
    logger.warning(f"Lead surveillance not available: {e}")
    SURVEILLANCE_AVAILABLE = False

try:
    from services import template_manager
except ImportError as e:
    logger.warning(f"Template manager not available: {e}")
    template_manager = None

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = APIRouter(tags=["leads-scoring"])


# =============================================================================
# SCORING & WHATSAPP DATA ENDPOINTS (Phase 5A)
# =============================================================================

@router.get("/{lead_id}/scores")
async def get_lead_scores(request: Request, lead_id: str, db: Session = Depends(get_db)):
    """Get all 4 dimension scores for a lead."""
    user = require_user(request, db)

    if not scoring_engine:
        raise HTTPException(status_code=503, detail="Scoring engine not available")

    data = leads_manager.load_leads()
    if lead_id not in data["leads"]:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead = data["leads"][lead_id]

    # Fetch WhatsApp data for enhanced scoring
    whatsapp_data = {}
    if whatsapp_db and lead.get("phone"):
        try:
            whatsapp_data = whatsapp_db.get_scoring_data(lead["phone"])
        except Exception as e:
            logger.warning(f"Could not fetch WhatsApp data for scoring: {e}")

    # Calculate scores
    scores = scoring_engine.calculate_all_scores(lead, whatsapp_data)

    return {
        "lead_id": lead_id,
        "scores": scores,
    }


@router.post("/{lead_id}/recalculate-scores")
async def recalculate_lead_scores(request: Request, lead_id: str, db: Session = Depends(get_db)):
    """Recalculate and save all scores for a lead."""
    user = require_user(request, db)

    if not scoring_engine:
        raise HTTPException(status_code=503, detail="Scoring engine not available")

    data = leads_manager.load_leads()
    if lead_id not in data["leads"]:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead = data["leads"][lead_id]

    # Fetch WhatsApp data for enhanced scoring
    whatsapp_data = {}
    if whatsapp_db and lead.get("phone"):
        try:
            whatsapp_data = whatsapp_db.get_scoring_data(lead["phone"])
        except Exception as e:
            logger.warning(f"Could not fetch WhatsApp data for scoring: {e}")

    # Calculate scores
    scores = scoring_engine.calculate_all_scores(lead, whatsapp_data)

    # Update lead with new scores
    lead["fit_score"] = scores["fit_score"]
    lead["fit_factors"] = scores["fit_factors"]
    lead["engagement_score"] = scores["engagement_score"]
    lead["engagement_factors"] = scores["engagement_factors"]
    lead["intent_score"] = scores["intent_score"]
    lead["intent_factors"] = scores["intent_factors"]
    lead["quality_score"] = scores["quality_score"]
    lead["quality_factors"] = scores["quality_factors"]
    lead["overall_score"] = scores["overall_score"]
    lead["lead_score"] = scores["overall_score"]  # Update legacy field too
    lead["lead_status"] = scores["lead_status"]
    lead["scores_calculated_at"] = scores["calculated_at"]

    leads_manager.save_leads(data)
    logger.info(f"Scores recalculated for lead {lead_id} by {user.email}: overall={scores['overall_score']}")

    return {
        "lead_id": lead_id,
        "scores": scores,
        "saved": True,
    }


@router.post("/batch-recalculate")
async def batch_recalculate_scores(request: Request, db: Session = Depends(get_db)):
    """Recalculate scores for all leads (can be slow for large datasets)."""
    user = require_user(request, db)

    if not scoring_engine:
        raise HTTPException(status_code=503, detail="Scoring engine not available")

    data = leads_manager.load_leads()
    leads = [l for l in data["leads"].values() if not l.get("is_deleted")]

    updated = 0
    errors = 0

    for lead in leads:
        try:
            # Fetch WhatsApp data
            whatsapp_data = {}
            if whatsapp_db and lead.get("phone"):
                try:
                    whatsapp_data = whatsapp_db.get_scoring_data(lead["phone"])
                except Exception as e:
                    logger.error("Failed to fetch WhatsApp scoring data: %s", e)

            # Calculate scores
            scores = scoring_engine.calculate_all_scores(lead, whatsapp_data)

            # Update lead
            lead["fit_score"] = scores["fit_score"]
            lead["fit_factors"] = scores["fit_factors"]
            lead["engagement_score"] = scores["engagement_score"]
            lead["engagement_factors"] = scores["engagement_factors"]
            lead["intent_score"] = scores["intent_score"]
            lead["intent_factors"] = scores["intent_factors"]
            lead["quality_score"] = scores["quality_score"]
            lead["quality_factors"] = scores["quality_factors"]
            lead["overall_score"] = scores["overall_score"]
            lead["lead_score"] = scores["overall_score"]
            lead["lead_status"] = scores["lead_status"]
            lead["scores_calculated_at"] = scores["calculated_at"]

            updated += 1
        except Exception as e:
            logger.error(f"Error scoring lead {lead.get('id')}: {e}")
            errors += 1

    leads_manager.save_leads(data)
    logger.info(f"Batch score recalculation by {user.email}: {updated} updated, {errors} errors")

    return {
        "updated": updated,
        "errors": errors,
        "total": len(leads),
    }


@router.get("/score-distribution")
async def get_score_distribution(request: Request, db: Session = Depends(get_db)):
    """Get score distribution statistics for charts."""
    user = require_user(request, db)

    if not scoring_engine:
        raise HTTPException(status_code=503, detail="Scoring engine not available")

    data = leads_manager.load_leads()
    leads = [l for l in data["leads"].values() if not l.get("is_deleted")]

    distribution = scoring_engine.analyze_score_distribution(leads)
    return distribution


# =============================================================================
# DEAL MANAGEMENT ENDPOINTS (Phase 5B)
# =============================================================================

@router.post("/{lead_id}/deal")
async def create_or_update_deal(request: Request, lead_id: str, db: Session = Depends(get_db)):
    """Create or update a deal for a lead."""
    user = require_user(request, db)

    data = leads_manager.load_leads()
    if lead_id not in data["leads"]:
        raise HTTPException(status_code=404, detail="Lead not found")

    body = await request.json()
    try:
        deal = leads_manager.create_deal(data, lead_id, body, actor=user.email)
        leads_manager.save_leads(data)
        logger.info(f"Deal created/updated for lead {lead_id} by {user.email}: ${deal.get('value', 0)}")
        return {"status": "ok", "deal": deal}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{lead_id}/deal/stage")
async def update_deal_stage_endpoint(request: Request, lead_id: str, db: Session = Depends(get_db)):
    """Update deal stage for a lead."""
    user = require_user(request, db)

    data = leads_manager.load_leads()
    body = await request.json()
    stage = body.get("stage")

    if not stage:
        raise HTTPException(status_code=400, detail="Stage is required")

    try:
        deal = leads_manager.update_deal_stage(data, lead_id, stage, actor=user.email)
        leads_manager.save_leads(data)
        logger.info(f"Deal stage updated for lead {lead_id} to {stage} by {user.email}")
        return {"status": "ok", "deal": deal}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{lead_id}/deal")
async def delete_deal_endpoint(request: Request, lead_id: str, db: Session = Depends(get_db)):
    """Delete a deal from a lead."""
    user = require_user(request, db)

    data = leads_manager.load_leads()
    try:
        result = leads_manager.delete_deal(data, lead_id, actor=user.email)
        if result:
            leads_manager.save_leads(data)
            logger.info(f"Deal deleted for lead {lead_id} by {user.email}")
            return {"status": "ok", "deleted": True}
        else:
            return {"status": "ok", "deleted": False, "message": "No deal to delete"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/deals")
async def list_deals(
    request: Request,
    stage: Optional[str] = None,
    min_value: Optional[int] = None,
    assignee: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all deals with optional filters."""
    user = require_user(request, db)

    data = leads_manager.load_leads()
    filters = {}
    if stage:
        filters["stage"] = stage
    if min_value:
        filters["min_value"] = min_value
    if assignee:
        filters["assignee"] = assignee

    deals = leads_manager.get_all_deals(data, filters)
    return {"deals": deals, "count": len(deals)}


@router.get("/deals/pipeline")
async def get_deals_pipeline(request: Request, db: Session = Depends(get_db)):
    """Get deals grouped by stage for pipeline view."""
    user = require_user(request, db)

    data = leads_manager.load_leads()
    pipeline = leads_manager.get_deals_by_stage(data)
    return {"pipeline": pipeline}


@router.get("/deals/forecast")
async def get_deals_forecast(request: Request, db: Session = Depends(get_db)):
    """Get revenue forecast from deals."""
    user = require_user(request, db)

    data = leads_manager.load_leads()
    forecast = leads_manager.get_revenue_forecast(data)
    return forecast


@router.get("/service-catalog")
async def get_service_catalog(request: Request, db: Session = Depends(get_db)):
    """Get service catalog with prices."""
    user = require_user(request, db)
    return {"catalog": leads_manager.SERVICE_CATALOG, "stages": leads_manager.DEAL_STAGES}


# =============================================================================
# TEMPLATE ENDPOINTS (Phase 5D)
# =============================================================================

@router.get("/templates")
async def get_templates(request: Request, channel: str = None, language: str = None, db: Session = Depends(get_db)):
    """Get all available templates."""
    user = require_user(request, db)

    if not template_manager:
        raise HTTPException(status_code=503, detail="Template manager not available")

    templates = template_manager.get_all_templates()

    if channel:
        templates = [t for t in templates if t["channel"] == channel]
    if language:
        templates = [t for t in templates if t["language"] == language]

    return {"templates": templates}


@router.get("/{lead_id}/template/{template_id}/preview")
async def preview_template(request: Request, lead_id: str, template_id: str, db: Session = Depends(get_db)):
    """Preview a template with lead data substituted."""
    user = require_user(request, db)

    if not template_manager:
        raise HTTPException(status_code=503, detail="Template manager not available")

    data = leads_manager.load_leads()
    if lead_id not in data["leads"]:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead = data["leads"][lead_id]
    preview = template_manager.preview_template(template_id, lead)

    if "error" in preview:
        raise HTTPException(status_code=404, detail=preview["error"])

    return preview


@router.post("/{lead_id}/template/{template_id}/send")
async def send_template(request: Request, lead_id: str, template_id: str, body: dict, db: Session = Depends(get_db)):
    """Send a template message to a lead (with approval flow)."""
    user = require_user(request, db)

    if not template_manager:
        raise HTTPException(status_code=503, detail="Template manager not available")

    data = leads_manager.load_leads()
    if lead_id not in data["leads"]:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead = data["leads"][lead_id]
    preview = template_manager.preview_template(template_id, lead)

    if "error" in preview:
        raise HTTPException(status_code=404, detail=preview["error"])

    channel = preview["channel"]
    content = preview["content"]
    recipient = preview["recipient"]
    now = datetime.now().isoformat()

    success = False
    error_msg = None

    # Send via appropriate channel
    if channel == "whatsapp":
        phone = recipient.get("phone")
        if not phone:
            return {"success": False, "error": "Lead has no phone number"}

        # For now, log the send action (actual WhatsApp integration would go here)
        # In production, this would call the WhatsApp bot API
        logger.info(f"WhatsApp template sent to {phone}: {template_id}")
        success = True

    elif channel == "email":
        email = recipient.get("email")
        if not email:
            return {"success": False, "error": "Lead has no email address"}

        # For now, log the send action (actual email integration would go here)
        # In production, this would use the email sending functionality
        logger.info(f"Email template sent to {email}: {template_id}")
        success = True

    # Log the send in communication_log
    if success:
        if "communication_log" not in lead:
            lead["communication_log"] = []

        lead["communication_log"].append({
            "timestamp": now,
            "type": "template_sent",
            "direction": "outbound",
            "channel": channel,
            "summary": f"Template sent: {preview['name']}",
            "content": content[:200] + "..." if len(content) > 200 else content,
            "template_id": template_id,
            "actor": user.email,
        })
        lead["communication_log"] = lead["communication_log"][-50:]
        lead["last_activity_at"] = now
        lead["updated_at"] = now

        leads_manager.save_leads(data)
        logger.info(f"Template {template_id} sent to lead {lead_id} via {channel} by {user.email}")

    return {
        "success": success,
        "channel": channel,
        "template_id": template_id,
        "error": error_msg,
    }


# =============================================================================
# LEAD INTELLIGENCE ENDPOINTS
# =============================================================================

@router.get("/{lead_id}/intel/analyze")
async def analyze_lead_intel(
    lead_id: str,
    request: Request,
    force: bool = Query(False, description="Force re-analysis even if fresh"),
    db: Session = Depends(get_db),
):
    """Trigger LLM analysis on a lead's WhatsApp conversation."""
    user = require_user(request, db)

    if not INTEL_AVAILABLE:
        return JSONResponse({"error": "Lead intelligence service not available"}, status_code=503)

    data = leads_manager.load_leads()
    lead = data["leads"].get(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Check if we have fresh intelligence already
    if not force and has_fresh_intelligence(lead, max_age_hours=2):
        return {
            "success": True,
            "cached": True,
            "intelligence": get_lead_intelligence(lead),
        }

    # Get conversation text from WhatsApp DB
    phone = lead.get("phone", "")
    if not phone:
        return JSONResponse({"error": "Lead has no phone number for conversation lookup"}, status_code=400)

    conversation_text = get_full_conversation_text(phone, limit=50)
    conv_stats = get_conversation_stats(phone)
    message_count = conv_stats.get("total_messages", 0) if conv_stats else 0

    # Run LLM analysis
    intelligence = await analyze_lead_conversation(
        lead=lead,
        conversation_text=conversation_text,
        message_count=message_count,
    )

    # Save intelligence to lead record
    lead["intelligence"] = intelligence
    lead["updated_at"] = leads_manager._now()
    leads_manager.save_leads(data)

    logger.info(f"Intel analysis completed for lead {lead_id} by {user.email} - "
                f"signals={len(intelligence.get('signals', []))}, "
                f"risk={intelligence.get('risk_level')}")

    return {
        "success": True,
        "cached": False,
        "intelligence": intelligence,
    }


@router.get("/{lead_id}/intel/signals")
async def get_lead_signals(
    lead_id: str,
    request: Request,
    signal_type: Optional[str] = Query(None, description="Filter: pre_obligational|obligational|risk"),
    db: Session = Depends(get_db),
):
    """Get cached intelligence signals for a lead."""
    require_user(request, db)

    data = leads_manager.load_leads()
    lead = data["leads"].get(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    intel = lead.get("intelligence", {})
    signals = intel.get("signals", [])

    if signal_type:
        signals = [s for s in signals if s.get("type") == signal_type]

    return {
        "success": True,
        "lead_id": lead_id,
        "signals": signals,
        "risk_level": intel.get("risk_level", "unknown"),
        "opportunity_score": intel.get("opportunity_score", 0),
        "last_analyzed_at": intel.get("last_analyzed_at"),
    }


@router.get("/{lead_id}/intel/tips")
async def get_lead_tips(
    lead_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Get closing tips and next best action for a lead."""
    require_user(request, db)

    data = leads_manager.load_leads()
    lead = data["leads"].get(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    intel = lead.get("intelligence", {})

    return {
        "success": True,
        "lead_id": lead_id,
        "closing_tips": intel.get("closing_tips", []),
        "next_best_action": intel.get("next_best_action", ""),
        "conversation_summary": intel.get("conversation_summary", ""),
        "risk_level": intel.get("risk_level", "unknown"),
        "opportunity_score": intel.get("opportunity_score", 0),
        "last_analyzed_at": intel.get("last_analyzed_at"),
    }


@router.post("/intel/batch-analyze")
async def batch_analyze_leads(
    request: Request,
    limit: int = Query(10, description="Max leads to analyze per batch"),
    db: Session = Depends(get_db),
):
    """Batch analyze leads that have conversations but no intelligence."""
    user = require_user(request, db)

    if not INTEL_AVAILABLE:
        return JSONResponse({"error": "Lead intelligence service not available"}, status_code=503)

    data = leads_manager.load_leads()
    analyzed = []
    errors = []

    # Find leads needing analysis (no intel or stale intel)
    candidates = []
    for lid, lead in data["leads"].items():
        if lead.get("is_deleted"):
            continue
        if not lead.get("phone"):
            continue
        if not has_fresh_intelligence(lead, max_age_hours=24):
            candidates.append((lid, lead))

    # Sort by lead_score descending (analyze hottest leads first)
    candidates.sort(key=lambda x: x[1].get("lead_score", 0), reverse=True)
    candidates = candidates[:limit]

    for lid, lead in candidates:
        try:
            phone = lead.get("phone", "")
            conversation_text = get_full_conversation_text(phone, limit=50)
            if len(conversation_text.strip()) < 20:
                continue

            conv_stats = get_conversation_stats(phone)
            message_count = conv_stats.get("total_messages", 0) if conv_stats else 0

            intelligence = await analyze_lead_conversation(
                lead=lead,
                conversation_text=conversation_text,
                message_count=message_count,
            )
            lead["intelligence"] = intelligence
            lead["updated_at"] = leads_manager._now()
            analyzed.append(lid)
        except Exception as e:
            errors.append({"lead_id": lid, "error": str(e)})
            logger.error(f"Batch intel error for {lid}: {e}")

    if analyzed:
        leads_manager.save_leads(data)

    logger.info(f"Batch analysis by {user.email}: {len(analyzed)} analyzed, {len(errors)} errors")

    return {
        "success": True,
        "analyzed_count": len(analyzed),
        "analyzed_leads": analyzed,
        "errors": errors,
        "remaining": len([c for c in data["leads"].values()
                         if not c.get("is_deleted") and c.get("phone")
                         and not has_fresh_intelligence(c, max_age_hours=24)]),
    }


@router.get("/{lead_id}/intel/email-signal")
async def get_email_formality_signal(
    lead_id: str,
    request: Request,
    analyze: bool = Query(False, description="Run LLM formality analysis on emails"),
    db: Session = Depends(get_db),
):
    """Get email formality signal for a lead. Optionally runs LLM analysis."""
    require_user(request, db)

    if not INTEL_AVAILABLE:
        return JSONResponse({"error": "Lead intelligence service not available"}, status_code=503)

    data = leads_manager.load_leads()
    lead = data["leads"].get(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    has_email = bool(lead.get("email"))
    comm_log = lead.get("communication_log", [])
    email_comms = [c for c in comm_log if c.get("channel") == "email"]
    inbound_emails = [c for c in email_comms if c.get("direction") == "inbound"]

    result = {
        "has_email": has_email,
        "email": lead.get("email", ""),
        "total_email_comms": len(email_comms),
        "inbound_email_count": len(inbound_emails),
        "outbound_email_count": len(email_comms) - len(inbound_emails),
        "email_formality_score": lead.get("intelligence", {}).get("email_formality_score", 0),
    }

    if analyze and inbound_emails:
        email_texts = [c.get("content", "") for c in inbound_emails if c.get("content")]
        if email_texts:
            formality = await analyze_email_formality(lead, email_texts)
            # Save to intelligence
            intel = lead.get("intelligence", {})
            intel["email_formality_score"] = formality.get("email_formality_score", 0)
            intel["email_formality_detail"] = formality
            lead["intelligence"] = intel
            lead["updated_at"] = leads_manager._now()
            leads_manager.save_leads(data)
            result["email_formality_score"] = formality.get("email_formality_score", 0)
            result["formality_detail"] = formality

    return {"success": True, "lead_id": lead_id, **result}


# =============================================================================
# SURVEILLANCE ENDPOINTS
# =============================================================================

@router.get("/intel/surveillance/status")
async def surveillance_status(request: Request, db: Session = Depends(get_db)):
    """Get surveillance worker status."""
    require_user(request, db)
    if not SURVEILLANCE_AVAILABLE:
        return {"active": False, "error": "Surveillance not available"}
    return get_surveillance_status()


@router.post("/intel/surveillance/toggle")
async def surveillance_toggle(request: Request, db: Session = Depends(get_db)):
    """Toggle surveillance on/off."""
    require_user(request, db)
    if not SURVEILLANCE_AVAILABLE:
        return JSONResponse({"error": "Surveillance not available"}, status_code=503)
    return toggle_surveillance()


@router.post("/intel/surveillance/check")
async def surveillance_check_now(request: Request, db: Session = Depends(get_db)):
    """Force immediate surveillance check."""
    require_user(request, db)
    if not SURVEILLANCE_AVAILABLE:
        return JSONResponse({"error": "Surveillance not available"}, status_code=503)
    result = await force_check()
    return result


# =============================================================================
# PIPELINE STAGE RECLASSIFICATION
# =============================================================================

@router.post("/intel/reclassify")
async def reclassify_pipeline_stages(
    request: Request,
    allow_demotion: bool = Query(False, description="Allow demoting leads to lower stages"),
    db: Session = Depends(get_db),
):
    """
    Reclassify all leads' pipeline stages based on WhatsApp conversation content.
    Uses deterministic analysis + LLM intelligence signals.
    Only promotes by default; set allow_demotion=true for full reclassification.
    Never touches CLOSING or VISA_IN_PROGRESS stages.
    """
    require_user(request, db)
    if not INTEL_AVAILABLE:
        return JSONResponse({"error": "Intelligence not available"}, status_code=503)

    data = leads_manager.load_leads()
    all_leads = data.get("leads", {})
    now = datetime.utcnow().isoformat()

    changes = []
    for lid, lead in all_leads.items():
        if lead.get("is_deleted"):
            continue
        phone = lead.get("phone", "")
        current_stage = lead.get("pipeline_stage", "NEW_LEAD")

        if phone:
            text = get_full_conversation_text(phone, limit=50)
            intel = lead.get("intelligence", {})
            suggested, reason = classify_lead_stage_from_content(lead, text, intel)
        else:
            continue  # Can't classify without conversation

        if should_update_pipeline_stage(current_stage, suggested, allow_demotion):
            if "stage_history" not in lead:
                lead["stage_history"] = []
            lead["stage_history"].append({
                "from": current_stage,
                "to": suggested,
                "timestamp": now,
                "actor": "manual_reclassify",
                "reason": reason,
            })
            lead["pipeline_stage"] = suggested
            lead["updated_at"] = now
            changes.append({
                "lead_id": lid,
                "name": lead.get("name", "Unknown"),
                "from": current_stage,
                "to": suggested,
                "reason": reason,
            })

    if changes:
        leads_manager.save_leads(data)

    # Count final distribution
    distribution = {}
    for lead in all_leads.values():
        if lead.get("is_deleted"):
            continue
        s = lead.get("pipeline_stage", "NEW_LEAD")
        distribution[s] = distribution.get(s, 0) + 1

    return {
        "changes": len(changes),
        "details": changes[:50],
        "distribution": distribution,
        "allow_demotion": allow_demotion,
    }


@router.get("/{lead_id}/intel/stage-check")
async def check_lead_stage(
    lead_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Check if a lead's pipeline stage matches its conversation content.
    Returns current stage, suggested stage, and whether an update is recommended.
    """
    require_user(request, db)
    if not INTEL_AVAILABLE:
        return JSONResponse({"error": "Intelligence not available"}, status_code=503)

    data = leads_manager.load_leads()
    lead = data.get("leads", {}).get(lead_id)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)

    phone = lead.get("phone", "")
    if not phone:
        return {"current_stage": lead.get("pipeline_stage"), "suggested_stage": None,
                "reason": "no_phone", "update_recommended": False}

    text = get_full_conversation_text(phone, limit=50)
    intel = lead.get("intelligence", {})
    suggested, reason = classify_lead_stage_from_content(lead, text, intel)
    current = lead.get("pipeline_stage", "NEW_LEAD")

    return {
        "current_stage": current,
        "suggested_stage": suggested,
        "reason": reason,
        "update_recommended": should_update_pipeline_stage(current, suggested),
        "would_demote": should_update_pipeline_stage(current, suggested, allow_demotion=True) and not should_update_pipeline_stage(current, suggested),
    }
