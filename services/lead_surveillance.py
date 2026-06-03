"""
CaseHub - Lead Surveillance Worker
Background asyncio task that monitors leads for new conversations,
detects signals, and generates alerts.

Runs as a FastAPI lifespan background task.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Surveillance state (in-memory, survives across cycles)
_state = {
    "active": False,
    "last_check_at": None,
    "leads_monitored": 0,
    "alerts": [],
    "cycle_count": 0,
    "errors": [],
}

# Config
CYCLE_INTERVAL_SECONDS = 300  # 5 minutes
MAX_GEMINI_CALLS_PER_CYCLE = 10
MAX_ALERTS = 50


async def surveillance_loop():
    """Main surveillance loop - runs in background."""
    logger.info("Surveillance worker started")
    while True:
        try:
            if _state["active"]:
                await run_surveillance_cycle()
            await asyncio.sleep(CYCLE_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("Surveillance worker cancelled")
            break
        except Exception as e:
            logger.error(f"Surveillance cycle error: {e}")
            _state["errors"].append({
                "time": datetime.utcnow().isoformat(),
                "error": str(e),
            })
            _state["errors"] = _state["errors"][-10:]
            await asyncio.sleep(60)  # Wait 1 min on error before retrying


async def run_surveillance_cycle():
    """Execute one surveillance cycle."""
    try:
        from services import leads_manager
        from services.lead_intelligence import (
            analyze_lead_conversation,
            has_fresh_intelligence,
            classify_lead_stage_from_content,
            should_update_pipeline_stage,
        )
        from whatsapp_db import get_full_conversation_text, get_conversation_stats
    except ImportError as e:
        logger.error(f"Surveillance imports failed: {e}")
        return

    _state["cycle_count"] += 1
    cycle_start = datetime.utcnow()

    data = leads_manager.load_leads()
    all_leads = data.get("leads", {})

    # Find leads needing analysis (have phone, not deleted, stale or no intel)
    candidates = []
    for lid, lead in all_leads.items():
        if lead.get("is_deleted"):
            continue
        if not lead.get("phone"):
            continue
        if not has_fresh_intelligence(lead, max_age_hours=2):
            candidates.append((lid, lead))

    _state["leads_monitored"] = len([
        l for l in all_leads.values()
        if not l.get("is_deleted") and l.get("phone")
    ])

    # Sort by priority: hot > qualified > warm > cold, then by score desc
    priority_order = {"hot": 0, "qualified": 1, "warm": 2, "cold": 3}
    candidates.sort(key=lambda x: (
        priority_order.get(x[1].get("lead_status", "cold"), 3),
        -(x[1].get("lead_score", 0)),
    ))

    # Process up to MAX_GEMINI_CALLS_PER_CYCLE
    analyzed = 0
    new_alerts = []

    for lid, lead in candidates[:MAX_GEMINI_CALLS_PER_CYCLE]:
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

            # Check for high-risk or high-opportunity alerts
            risk = intelligence.get("risk_level", "low")
            opp = intelligence.get("opportunity_score", 0)
            signals = intelligence.get("signals", [])

            if risk == "high":
                new_alerts.append({
                    "type": "high_risk",
                    "lead_id": lid,
                    "lead_name": lead.get("name", "Unknown"),
                    "message": f"High risk detected: {intelligence.get('next_best_action', '')}",
                    "time": datetime.utcnow().isoformat(),
                })

            if opp >= 80:
                new_alerts.append({
                    "type": "hot_opportunity",
                    "lead_id": lid,
                    "lead_name": lead.get("name", "Unknown"),
                    "message": f"Hot opportunity (score {opp}): {intelligence.get('next_best_action', '')}",
                    "time": datetime.utcnow().isoformat(),
                })

            # Check for specific urgent signals
            for sig in signals:
                if sig.get("name") in ("ghosting", "competitor_mention") and sig.get("confidence", 0) >= 0.7:
                    new_alerts.append({
                        "type": "urgent_signal",
                        "lead_id": lid,
                        "lead_name": lead.get("name", "Unknown"),
                        "message": f"{sig['name']}: {sig.get('evidence', '')}",
                        "time": datetime.utcnow().isoformat(),
                    })

            lead["intelligence"] = intelligence

            # === PIPELINE STAGE VERIFICATION ===
            # After analyzing conversation, verify lead is in the correct stage
            current_stage = lead.get("pipeline_stage", "NEW_LEAD")
            suggested_stage, stage_reason = classify_lead_stage_from_content(
                lead, conversation_text, intelligence
            )

            if should_update_pipeline_stage(current_stage, suggested_stage):
                old_stage = current_stage
                lead["pipeline_stage"] = suggested_stage
                if "stage_history" not in lead:
                    lead["stage_history"] = []
                lead["stage_history"].append({
                    "from": old_stage,
                    "to": suggested_stage,
                    "timestamp": datetime.utcnow().isoformat(),
                    "actor": "surveillance_auto_classify",
                    "reason": stage_reason,
                })
                new_alerts.append({
                    "type": "stage_change",
                    "lead_id": lid,
                    "lead_name": lead.get("name", "Unknown"),
                    "message": f"Pipeline: {old_stage} → {suggested_stage} ({stage_reason})",
                    "time": datetime.utcnow().isoformat(),
                })
                logger.info(
                    f"Auto-reclassified {lead.get('name', lid)}: "
                    f"{old_stage} → {suggested_stage} ({stage_reason})"
                )

            lead["updated_at"] = leads_manager._now()
            analyzed += 1

        except Exception as e:
            logger.error(f"Surveillance error for lead {lid}: {e}")

    # Save if anything was analyzed
    if analyzed > 0:
        leads_manager.save_leads(data)

    # Update alerts
    if new_alerts:
        _state["alerts"] = (new_alerts + _state["alerts"])[:MAX_ALERTS]

    _state["last_check_at"] = cycle_start.isoformat()

    stage_changes = sum(1 for a in new_alerts if a.get("type") == "stage_change")
    logger.info(
        f"Surveillance cycle #{_state['cycle_count']}: "
        f"{analyzed} analyzed, {len(new_alerts)} alerts, "
        f"{stage_changes} stage changes, "
        f"{len(candidates)} candidates"
    )


def get_surveillance_status() -> Dict[str, Any]:
    """Get current surveillance status."""
    return {
        "active": _state["active"],
        "last_check_at": _state["last_check_at"],
        "leads_monitored": _state["leads_monitored"],
        "cycle_count": _state["cycle_count"],
        "alerts_count": len(_state["alerts"]),
        "alerts": _state["alerts"][:10],
        "errors": _state["errors"][-3:],
    }


def toggle_surveillance() -> Dict[str, Any]:
    """Toggle surveillance on/off."""
    _state["active"] = not _state["active"]
    logger.info(f"Surveillance {'activated' if _state['active'] else 'deactivated'}")
    return {"active": _state["active"]}


async def force_check() -> Dict[str, Any]:
    """Force an immediate surveillance cycle."""
    was_active = _state["active"]
    _state["active"] = True
    await run_surveillance_cycle()
    _state["active"] = was_active
    return {
        "analyzed": _state["cycle_count"],
        "alerts_count": len(_state["alerts"]),
    }
