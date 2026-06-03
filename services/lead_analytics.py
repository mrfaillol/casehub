"""
CaseHub - Lead Analytics Engine
Advanced analytics computations for the leads CRM.
Provides funnel conversion, velocity, source attribution,
channel engagement, and intelligence summaries.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

STAGES = [
    "NEW_LEAD", "LEAD_QUALIFICATION", "INTAKE_CALL",
    "CONSULTATION", "CLOSING", "VISA_IN_PROGRESS",
]

CONVERTED_STAGES = {"CLOSING", "VISA_IN_PROGRESS"}


def compute_funnel_conversion(leads: Dict[str, dict]) -> Dict[str, Any]:
    """
    Compute funnel conversion rates between pipeline stages.
    Returns % conversion from each stage to the next.
    """
    active = [l for l in leads.values() if not l.get("is_deleted")]

    # Count leads that have been in each stage (using stage_history)
    stage_counts = defaultdict(int)
    for lead in active:
        current_stage = lead.get("pipeline_stage", "NEW_LEAD")
        history = lead.get("stage_history", [])

        # Count current + all historical stages
        seen = {current_stage}
        for h in history:
            s = h.get("stage") or h.get("to")
            if s:
                seen.add(s)

        for s in seen:
            stage_counts[s] += 1

    # Build funnel
    funnel = []
    for i, stage in enumerate(STAGES):
        count = stage_counts.get(stage, 0)
        prev_count = stage_counts.get(STAGES[i - 1], 0) if i > 0 else count
        conversion = round((count / prev_count * 100), 1) if prev_count > 0 else 0

        funnel.append({
            "stage": stage,
            "count": count,
            "conversion_from_previous": conversion if i > 0 else 100.0,
        })

    # Overall conversion rate
    total_entered = stage_counts.get("NEW_LEAD", 0)
    total_converted = sum(stage_counts.get(s, 0) for s in CONVERTED_STAGES)
    overall_conversion = round((total_converted / total_entered * 100), 1) if total_entered > 0 else 0

    return {
        "funnel": funnel,
        "overall_conversion": overall_conversion,
        "total_entered": total_entered,
        "total_converted": total_converted,
    }


def compute_pipeline_velocity(leads: Dict[str, dict]) -> Dict[str, Any]:
    """
    Compute average time spent in each pipeline stage.
    Uses stage_history timestamps.
    """
    stage_durations = defaultdict(list)
    active = [l for l in leads.values() if not l.get("is_deleted")]

    for lead in active:
        history = lead.get("stage_history", [])
        if len(history) < 2:
            continue

        # Sort by timestamp
        sorted_h = sorted(history, key=lambda x: x.get("timestamp", ""))

        for i in range(len(sorted_h) - 1):
            try:
                stage = sorted_h[i].get("stage") or sorted_h[i].get("to", "")
                t1 = datetime.fromisoformat(sorted_h[i]["timestamp"].replace("Z", "+00:00"))
                t2 = datetime.fromisoformat(sorted_h[i + 1]["timestamp"].replace("Z", "+00:00"))
                days = (t2 - t1).total_seconds() / 86400
                if 0 < days < 365:  # Sanity check
                    stage_durations[stage].append(days)
            except (KeyError, ValueError, TypeError):
                continue

    velocity = {}
    for stage in STAGES:
        durations = stage_durations.get(stage, [])
        if durations:
            velocity[stage] = {
                "avg_days": round(sum(durations) / len(durations), 1),
                "median_days": round(sorted(durations)[len(durations) // 2], 1),
                "min_days": round(min(durations), 1),
                "max_days": round(max(durations), 1),
                "count": len(durations),
            }
        else:
            velocity[stage] = {"avg_days": 0, "median_days": 0, "min_days": 0, "max_days": 0, "count": 0}

    # Total average cycle time (NEW_LEAD to CLOSING/VISA_IN_PROGRESS)
    total_cycle = []
    for lead in active:
        history = lead.get("stage_history", [])
        if not history:
            continue
        sorted_h = sorted(history, key=lambda x: x.get("timestamp", ""))
        first = sorted_h[0]
        last = sorted_h[-1]
        last_stage = last.get("stage") or last.get("to", "")
        if last_stage in CONVERTED_STAGES:
            try:
                t1 = datetime.fromisoformat(first["timestamp"].replace("Z", "+00:00"))
                t2 = datetime.fromisoformat(last["timestamp"].replace("Z", "+00:00"))
                days = (t2 - t1).total_seconds() / 86400
                if 0 < days < 365:
                    total_cycle.append(days)
            except (KeyError, ValueError, TypeError):
                continue

    avg_cycle = round(sum(total_cycle) / len(total_cycle), 1) if total_cycle else 0

    return {
        "by_stage": velocity,
        "avg_total_cycle_days": avg_cycle,
        "conversions_tracked": len(total_cycle),
    }


def compute_source_attribution(leads: Dict[str, dict]) -> Dict[str, Any]:
    """
    Compute lead performance by source with conversion rates.
    """
    active = [l for l in leads.values() if not l.get("is_deleted")]

    sources = defaultdict(lambda: {
        "total": 0, "converted": 0, "avg_score": 0,
        "scores": [], "revenue": 0, "hot": 0,
    })

    for lead in active:
        source = lead.get("source", "MANUAL") or "MANUAL"
        sources[source]["total"] += 1
        sources[source]["scores"].append(lead.get("lead_score", 0))

        if lead.get("pipeline_stage") in CONVERTED_STAGES:
            sources[source]["converted"] += 1

        if lead.get("lead_score", 0) >= 70:
            sources[source]["hot"] += 1

        deal = lead.get("deal", {})
        if deal and deal.get("value"):
            sources[source]["revenue"] += deal["value"]

    result = {}
    for source, data in sources.items():
        result[source] = {
            "total_leads": data["total"],
            "converted": data["converted"],
            "conversion_rate": round((data["converted"] / data["total"] * 100), 1) if data["total"] > 0 else 0,
            "avg_score": round(sum(data["scores"]) / len(data["scores"]), 1) if data["scores"] else 0,
            "hot_leads": data["hot"],
            "total_revenue": data["revenue"],
        }

    return {"sources": result}


def compute_channel_engagement(leads: Dict[str, dict]) -> Dict[str, Any]:
    """
    Compare engagement across WhatsApp vs Email channels.
    """
    active = [l for l in leads.values() if not l.get("is_deleted")]

    whatsapp_only = 0
    email_only = 0
    both = 0
    neither = 0
    whatsapp_avg_score = []
    email_avg_score = []
    both_avg_score = []

    for lead in active:
        has_phone = bool(lead.get("phone"))
        has_email = bool(lead.get("email"))
        score = lead.get("lead_score", 0)

        intel = lead.get("intelligence", {})
        channel_eng = intel.get("channel_engagement", {})
        has_email_comms = channel_eng.get("email", {}).get("message_count", 0) > 0
        has_wpp_comms = (lead.get("message_count", 0) or 0) > 0

        if has_wpp_comms and has_email_comms:
            both += 1
            both_avg_score.append(score)
        elif has_wpp_comms:
            whatsapp_only += 1
            whatsapp_avg_score.append(score)
        elif has_email_comms or has_email:
            email_only += 1
            email_avg_score.append(score)
        else:
            neither += 1

    avg = lambda lst: round(sum(lst) / len(lst), 1) if lst else 0

    return {
        "whatsapp_only": {"count": whatsapp_only, "avg_score": avg(whatsapp_avg_score)},
        "email_only": {"count": email_only, "avg_score": avg(email_avg_score)},
        "both_channels": {"count": both, "avg_score": avg(both_avg_score)},
        "no_engagement": neither,
        "total": len(active),
    }


def compute_intelligence_summary(leads: Dict[str, dict]) -> Dict[str, Any]:
    """
    Aggregate intelligence data across all leads.
    """
    active = [l for l in leads.values() if not l.get("is_deleted")]

    total_analyzed = 0
    risk_counts = {"low": 0, "medium": 0, "high": 0}
    signal_counts = defaultdict(int)
    opp_scores = []
    top_alerts = []

    for lead in active:
        intel = lead.get("intelligence", {})
        if not intel or not intel.get("last_analyzed_at"):
            continue

        total_analyzed += 1
        risk = intel.get("risk_level", "low")
        if risk in risk_counts:
            risk_counts[risk] += 1

        opp_scores.append(intel.get("opportunity_score", 0))

        for sig in intel.get("signals", []):
            signal_counts[sig.get("name", "unknown")] += 1

        # Collect high-risk or high-opportunity for alerts
        if risk == "high" or intel.get("opportunity_score", 0) >= 80:
            top_alerts.append({
                "lead_id": lead.get("id"),
                "lead_name": lead.get("name", "Unknown"),
                "risk_level": risk,
                "opportunity_score": intel.get("opportunity_score", 0),
                "next_action": intel.get("next_best_action", ""),
            })

    # Sort alerts: high risk first, then high opportunity
    top_alerts.sort(key=lambda x: (x["risk_level"] != "high", -x["opportunity_score"]))

    avg_opp = round(sum(opp_scores) / len(opp_scores), 1) if opp_scores else 0

    # Top signals
    top_signals = sorted(signal_counts.items(), key=lambda x: -x[1])[:10]

    return {
        "total_analyzed": total_analyzed,
        "total_leads": len(active),
        "coverage": round((total_analyzed / len(active) * 100), 1) if active else 0,
        "risk_distribution": risk_counts,
        "avg_opportunity_score": avg_opp,
        "top_signals": [{"name": n, "count": c} for n, c in top_signals],
        "active_alerts": top_alerts[:10],
    }


def compute_score_trends(leads: Dict[str, dict], days: int = 30) -> Dict[str, Any]:
    """
    Compute score trends over time using score_history.
    """
    cutoff = datetime.now() - timedelta(days=days)
    active = [l for l in leads.values() if not l.get("is_deleted")]

    daily_scores = defaultdict(lambda: {"fit": [], "engagement": [], "intent": [], "quality": [], "overall": []})

    for lead in active:
        history = lead.get("score_history", [])
        for entry in history:
            try:
                ts = datetime.fromisoformat(entry.get("timestamp", "").replace("Z", "+00:00"))
                if ts.replace(tzinfo=None) < cutoff:
                    continue
                day = ts.strftime("%Y-%m-%d")
                if "fit_score" in entry:
                    daily_scores[day]["fit"].append(entry["fit_score"])
                if "engagement_score" in entry:
                    daily_scores[day]["engagement"].append(entry["engagement_score"])
                if "intent_score" in entry:
                    daily_scores[day]["intent"].append(entry["intent_score"])
                if "quality_score" in entry:
                    daily_scores[day]["quality"].append(entry["quality_score"])
                if "overall_score" in entry:
                    daily_scores[day]["overall"].append(entry["overall_score"])
            except (ValueError, TypeError):
                continue

    avg = lambda lst: round(sum(lst) / len(lst), 1) if lst else None

    # Build sorted daily data
    sorted_days = sorted(daily_scores.keys())
    trend_data = []
    for day in sorted_days:
        d = daily_scores[day]
        trend_data.append({
            "date": day,
            "fit": avg(d["fit"]),
            "engagement": avg(d["engagement"]),
            "intent": avg(d["intent"]),
            "quality": avg(d["quality"]),
            "overall": avg(d["overall"]),
        })

    return {"daily": trend_data, "days": days}
