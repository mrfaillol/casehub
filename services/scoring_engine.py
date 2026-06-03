"""
Advanced Lead Scoring Engine - 4-Dimensional Scoring System.
Similar to Moskit/Facebook Ads scoring algorithms.

Scores:
- Fit Score (25%): How well the lead matches ideal client profile
- Engagement Score (25%): Level of interaction
- Intent Score (35%): Purchase/conversion intent
- Quality Score (15%): Data completeness
"""

from typing import Dict, Any, Tuple
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# SCORING WEIGHTS
# =============================================================================

SCORE_WEIGHTS = {
    "fit": 0.25,
    "engagement": 0.25,
    "intent": 0.35,
    "quality": 0.15,
}

# =============================================================================
# VISA TYPE VALUES
# =============================================================================

VISA_TYPE_VALUES = {
    # High-value visas (35 points)
    "eb-1a": 35, "eb1a": 35, "eb-1": 35, "eb1": 35,
    "eb-1b": 35, "eb1b": 35,
    "eb-2 niw": 35, "eb2 niw": 35, "eb-2niw": 35, "niw": 35,
    "eb-2": 30, "eb2": 30,
    
    # Medium-high value (30 points)
    "o-1a": 30, "o1a": 30, "o-1": 30, "o1": 30,
    "o-1b": 28, "o1b": 28,
    
    # Medium value (25 points)
    "l-1a": 25, "l1a": 25, "l-1": 25, "l1": 25,
    "l-1b": 22, "l1b": 22,
    "eb-3": 22, "eb3": 22,
    
    # Family-based (20 points)
    "family": 20, "family-based": 20, "family based": 20,
    "green card": 20, "greencard": 20,
    "i-130": 20, "i130": 20,
    
    # H-1B (18 points)
    "h-1b": 18, "h1b": 18, "h-1": 18, "h1": 18,
    
    # Humanitarian (15 points)
    "asylum": 15, "asilo": 15,
    "vawa": 15, "u-visa": 15, "u visa": 15, "t-visa": 15, "t visa": 15,
    "sijs": 15,
    
    # Investor (30 points)
    "eb-5": 30, "eb5": 30, "investor": 30, "e-2": 30, "e2": 30,
}


# =============================================================================
# FIT SCORE (0-100)
# =============================================================================

def calculate_fit_score(lead: Dict, whatsapp_data: Dict = None) -> Tuple[int, Dict[str, int]]:
    """
    Calculate Fit Score - how well the lead matches ideal client profile.
    
    Factors:
    - visa_type_value (0-35): Value of visa type
    - budget_indicator (0-25): Payment signals
    - urgency_level (0-20): Timeline urgency
    - location_score (0-20): Geographic fit
    
    Returns: (total_score, factors_breakdown)
    """
    factors = {
        "visa_type_value": 0,
        "budget_indicator": 0,
        "urgency_level": 0,
        "location_score": 0,
    }
    
    whatsapp_data = whatsapp_data or {}
    wp_lead = whatsapp_data.get("lead") or {}
    
    # 1. Visa Type Value (0-35)
    visa_interest = (
        lead.get("visa_interest") or 
        lead.get("intake_form_primary_pathway") or 
        wp_lead.get("visa_interest") or
        wp_lead.get("intake_form_primary_pathway") or
        ""
    ).lower()
    
    for visa_key, value in VISA_TYPE_VALUES.items():
        if visa_key in visa_interest:
            factors["visa_type_value"] = value
            break
    else:
        factors["visa_type_value"] = 10  # Default for unknown
    
    # 2. Budget Indicator (0-25)
    payment_status = lead.get("payment_status") or wp_lead.get("payment_status")
    consultation_scheduled = lead.get("consultation_scheduled") or wp_lead.get("consultation_scheduled")
    consultation_type = lead.get("consultation_type") or wp_lead.get("consultation_type")
    
    if payment_status == "paid":
        factors["budget_indicator"] = 25
    elif consultation_type == "paid":
        factors["budget_indicator"] = 20
    elif consultation_scheduled:
        factors["budget_indicator"] = 15
    elif consultation_type == "free":
        factors["budget_indicator"] = 10
    else:
        factors["budget_indicator"] = 5
    
    # 3. Urgency Level (0-20)
    is_urgent = lead.get("is_urgent") or wp_lead.get("is_urgent")
    urgency = wp_lead.get("urgency", "normal")
    notes = (lead.get("notes") or "").lower()
    
    if is_urgent or urgency == "critica":
        factors["urgency_level"] = 20
    elif urgency == "alta" or "urgent" in notes or "urgente" in notes:
        factors["urgency_level"] = 15
    else:
        factors["urgency_level"] = 8
    
    # 4. Location Score (0-20)
    phone = lead.get("phone") or wp_lead.get("phone") or ""
    clean_phone = phone.replace("+", "").replace(" ", "").replace("-", "")
    
    if clean_phone.startswith("1") and len(clean_phone) == 11:
        factors["location_score"] = 20  # US number
    elif clean_phone.startswith("55"):
        factors["location_score"] = 18  # Brazil (target market)
    elif clean_phone.startswith(("44", "61", "64", "91")):
        factors["location_score"] = 15  # English-speaking countries
    else:
        factors["location_score"] = 10  # Other
    
    total = sum(factors.values())
    return min(100, total), factors


# =============================================================================
# ENGAGEMENT SCORE (0-100)
# =============================================================================

def calculate_engagement_score(lead: Dict, whatsapp_data: Dict = None) -> Tuple[int, Dict[str, int]]:
    """
    Calculate Engagement Score - level of interaction.

    Factors:
    - message_count_score (0-30): Total messages exchanged
    - message_recency (0-30): How recent was last interaction
    - response_time_avg (0-20): Response speed
    - form_completion_rate (0-20): Intake form progress
    - email_formality_boost (0-15): Boost for email-originating leads

    Returns: (total_score, factors_breakdown)
    """
    factors = {
        "message_count_score": 0,
        "message_recency": 0,
        "response_time_avg": 0,
        "form_completion_rate": 0,
        "email_formality_boost": 0,
    }
    
    whatsapp_data = whatsapp_data or {}
    wp_lead = whatsapp_data.get("lead") or {}
    conv_metrics = whatsapp_data.get("conversation_metrics") or {}
    
    # 1. Message Count Score (0-30)
    msg_count = (
        lead.get("message_count") or 
        wp_lead.get("message_count") or 
        conv_metrics.get("message_count") or 0
    )
    
    if msg_count >= 20:
        factors["message_count_score"] = 30
    elif msg_count >= 10:
        factors["message_count_score"] = 25
    elif msg_count >= 5:
        factors["message_count_score"] = 15
    else:
        factors["message_count_score"] = min(msg_count * 3, 10)
    
    # 2. Message Recency (0-30)
    last_msg = (
        lead.get("last_message_at") or 
        lead.get("last_activity_at") or
        wp_lead.get("last_interaction") or
        conv_metrics.get("last_message_at")
    )
    
    if last_msg:
        try:
            if isinstance(last_msg, str):
                last_msg_dt = datetime.fromisoformat(last_msg.replace("Z", "+00:00"))
            else:
                last_msg_dt = last_msg
            
            days_ago = (datetime.now() - last_msg_dt.replace(tzinfo=None)).days
            
            if days_ago <= 1:
                factors["message_recency"] = 30
            elif days_ago <= 3:
                factors["message_recency"] = 25
            elif days_ago <= 7:
                factors["message_recency"] = 15
            elif days_ago <= 30:
                factors["message_recency"] = 8
            else:
                factors["message_recency"] = 0
        except:
            factors["message_recency"] = 5  # Default if parsing fails
    
    # 3. Response Time (0-20) - estimated from conversation state
    conv_state = wp_lead.get("conversation_state") or lead.get("conversation_state")
    messages_24h = conv_metrics.get("messages_last_24h", 0)
    
    if messages_24h >= 5:
        factors["response_time_avg"] = 20  # Very active
    elif messages_24h >= 2:
        factors["response_time_avg"] = 15
    elif conv_state in ("AWAITING_HUMAN", "NEEDS_REVIEW"):
        factors["response_time_avg"] = 12  # Recently active
    else:
        factors["response_time_avg"] = 5
    
    # 4. Form Completion Rate (0-20)
    intake_state = wp_lead.get("intake_form_state") or lead.get("intake_form_state", "not_started")
    current_q = wp_lead.get("intake_form_current_question", 0) or lead.get("intake_form_current_question", 0)
    
    if intake_state == "completed":
        factors["form_completion_rate"] = 20
    elif intake_state == "in_progress":
        # Pro-rata based on questions answered (46 total)
        factors["form_completion_rate"] = min(15, int((current_q / 46) * 15))
    elif intake_state == "invited":
        factors["form_completion_rate"] = 3
    else:
        factors["form_completion_rate"] = 0

    # 5. Email Formality Boost (0-15)
    # Leads communicating via email show higher seriousness/intent
    has_email = bool(lead.get("email") or wp_lead.get("email"))
    intel = lead.get("intelligence", {})
    channel_engagement = intel.get("channel_engagement", {})
    email_channel = channel_engagement.get("email", {})
    comm_log = lead.get("communication_log", [])
    has_email_comms = email_channel.get("message_count", 0) > 0 or any(
        c.get("channel") == "email" and c.get("direction") == "inbound"
        for c in comm_log
    )

    if has_email and has_email_comms:
        factors["email_formality_boost"] = 10  # Email + actual email comms
        # Extra boost if email formality score is high
        email_formality = intel.get("email_formality_score", 0)
        if email_formality >= 70:
            factors["email_formality_boost"] = 15
        elif email_formality >= 40:
            factors["email_formality_boost"] = 12
    elif has_email:
        factors["email_formality_boost"] = 5  # Has email but no email comms yet

    total = sum(factors.values())
    return min(100, total), factors


# =============================================================================
# INTENT SCORE (0-100)
# =============================================================================

def calculate_intent_score(lead: Dict, whatsapp_data: Dict = None) -> Tuple[int, Dict[str, int]]:
    """
    Calculate Intent Score - purchase/conversion intent.
    
    Factors:
    - consultation_interest (0-35): Interest in consultation
    - pricing_interest (0-25): Interest in pricing/payment
    - intake_completion (0-25): Intake form score
    - direct_service_questions (0-15): Directly asked about services
    
    Returns: (total_score, factors_breakdown)
    """
    factors = {
        "consultation_interest": 0,
        "pricing_interest": 0,
        "intake_completion": 0,
        "direct_service_questions": 0,
    }
    
    whatsapp_data = whatsapp_data or {}
    wp_lead = whatsapp_data.get("lead") or {}
    
    # 1. Consultation Interest (0-35)
    consultation_scheduled = lead.get("consultation_scheduled") or wp_lead.get("consultation_scheduled")
    consultation_type = lead.get("consultation_type") or wp_lead.get("consultation_type")
    
    if consultation_scheduled and consultation_type == "paid":
        factors["consultation_interest"] = 35
    elif consultation_scheduled:
        factors["consultation_interest"] = 25
    elif consultation_type:
        factors["consultation_interest"] = 20
    else:
        factors["consultation_interest"] = 5
    
    # 2. Pricing Interest (0-25)
    payment_status = lead.get("payment_status") or wp_lead.get("payment_status")
    payment_amount = lead.get("payment_amount") or wp_lead.get("payment_amount")
    
    if payment_status == "paid":
        factors["pricing_interest"] = 25
    elif payment_status == "pending":
        factors["pricing_interest"] = 20
    elif payment_amount:
        factors["pricing_interest"] = 15
    else:
        factors["pricing_interest"] = 0
    
    # 3. Intake Completion (0-25)
    intake_score = (
        lead.get("intake_form_final_score") or 
        wp_lead.get("intake_form_final_score") or
        whatsapp_data.get("intake_points") or 0
    )
    
    if intake_score >= 80:
        factors["intake_completion"] = 25
    elif intake_score >= 60:
        factors["intake_completion"] = 20
    elif intake_score >= 40:
        factors["intake_completion"] = 15
    elif intake_score > 0:
        factors["intake_completion"] = int(intake_score * 0.25)
    else:
        factors["intake_completion"] = 0
    
    # 4. Direct Service Questions (0-15)
    conv_state = lead.get("conversation_state") or wp_lead.get("conversation_state")
    needs_review = wp_lead.get("needs_human_review", False)
    human_takeover = wp_lead.get("human_takeover", False)
    
    if human_takeover or needs_review:
        factors["direct_service_questions"] = 15  # Asked complex questions
    elif conv_state in ("AWAITING_HUMAN", "NEEDS_REVIEW"):
        factors["direct_service_questions"] = 12
    elif conv_state == "QUALIFIED":
        factors["direct_service_questions"] = 10
    else:
        factors["direct_service_questions"] = 5
    
    total = sum(factors.values())
    return min(100, total), factors


# =============================================================================
# QUALITY SCORE (0-100)
# =============================================================================

def calculate_quality_score(lead: Dict, whatsapp_data: Dict = None) -> Tuple[int, Dict[str, int]]:
    """
    Calculate Quality Score - data completeness.
    
    Factors:
    - contact_completeness (0-30): Phone + email
    - profile_completeness (0-30): Name, profession, visa, language
    - document_submissions (0-20): Documents received
    - intake_form_score (0-20): From WhatsApp bot
    
    Returns: (total_score, factors_breakdown)
    """
    factors = {
        "contact_completeness": 0,
        "profile_completeness": 0,
        "document_submissions": 0,
        "intake_form_score": 0,
    }
    
    whatsapp_data = whatsapp_data or {}
    wp_lead = whatsapp_data.get("lead") or {}
    
    # 1. Contact Completeness (0-30)
    has_phone = bool(lead.get("phone") or wp_lead.get("phone"))
    has_email = bool(lead.get("email") or wp_lead.get("email"))
    
    if has_phone:
        factors["contact_completeness"] += 15
    if has_email:
        factors["contact_completeness"] += 15
    
    # 2. Profile Completeness (0-30)
    profile_fields = [
        lead.get("name") or wp_lead.get("name") or wp_lead.get("client_name") or wp_lead.get("whatsapp_name"),
        lead.get("profession") or wp_lead.get("profession"),
        lead.get("visa_interest") or wp_lead.get("visa_interest") or wp_lead.get("visa_type"),
        lead.get("language") or wp_lead.get("language"),
    ]
    
    filled = sum(1 for f in profile_fields if f)
    factors["profile_completeness"] = int((filled / len(profile_fields)) * 30)
    
    # 3. Document Submissions (0-20)
    docs_count = lead.get("documents_count", 0)
    factors["document_submissions"] = min(20, docs_count * 5)
    
    # 4. Intake Form Score (0-20)
    intake_score = (
        lead.get("intake_form_final_score") or 
        wp_lead.get("intake_form_final_score") or 0
    )
    factors["intake_form_score"] = min(20, int(intake_score * 0.2))
    
    total = sum(factors.values())
    return min(100, total), factors


# =============================================================================
# OVERALL SCORE CALCULATION
# =============================================================================

def calculate_all_scores(lead: Dict, whatsapp_data: Dict = None) -> Dict[str, Any]:
    """
    Calculate all 4 scores and overall score for a lead.
    
    Returns: {
        "fit_score": int,
        "fit_factors": dict,
        "engagement_score": int,
        "engagement_factors": dict,
        "intent_score": int,
        "intent_factors": dict,
        "quality_score": int,
        "quality_factors": dict,
        "overall_score": int,
        "lead_status": str,  # cold/warm/qualified/hot
        "calculated_at": str,
    }
    """
    fit_score, fit_factors = calculate_fit_score(lead, whatsapp_data)
    engagement_score, engagement_factors = calculate_engagement_score(lead, whatsapp_data)
    intent_score, intent_factors = calculate_intent_score(lead, whatsapp_data)
    quality_score, quality_factors = calculate_quality_score(lead, whatsapp_data)
    
    # Calculate weighted overall score
    overall = int(
        fit_score * SCORE_WEIGHTS["fit"] +
        engagement_score * SCORE_WEIGHTS["engagement"] +
        intent_score * SCORE_WEIGHTS["intent"] +
        quality_score * SCORE_WEIGHTS["quality"]
    )
    
    # Determine lead status
    if overall >= 70:
        lead_status = "hot"
    elif overall >= 50:
        lead_status = "qualified"
    elif overall >= 30:
        lead_status = "warm"
    else:
        lead_status = "cold"
    
    return {
        "fit_score": fit_score,
        "fit_factors": fit_factors,
        "engagement_score": engagement_score,
        "engagement_factors": engagement_factors,
        "intent_score": intent_score,
        "intent_factors": intent_factors,
        "quality_score": quality_score,
        "quality_factors": quality_factors,
        "overall_score": overall,
        "lead_status": lead_status,
        "calculated_at": datetime.now().isoformat(),
    }


def get_score_summary(scores: Dict) -> str:
    """Get a human-readable summary of scores."""
    return (
        f"Overall: {scores['overall_score']}/100 ({scores['lead_status'].upper()}) | "
        f"Fit: {scores['fit_score']} | Engagement: {scores['engagement_score']} | "
        f"Intent: {scores['intent_score']} | Quality: {scores['quality_score']}"
    )


# =============================================================================
# SCORE DISTRIBUTION ANALYSIS
# =============================================================================

def analyze_score_distribution(leads: list) -> Dict[str, Any]:
    """
    Analyze score distribution across all leads.
    Returns statistics for charts.
    """
    if not leads:
        return {}
    
    fit_scores = []
    engagement_scores = []
    intent_scores = []
    quality_scores = []
    overall_scores = []
    
    status_counts = {"hot": 0, "qualified": 0, "warm": 0, "cold": 0}
    
    for lead in leads:
        if "fit_score" in lead:
            fit_scores.append(lead["fit_score"])
        if "engagement_score" in lead:
            engagement_scores.append(lead["engagement_score"])
        if "intent_score" in lead:
            intent_scores.append(lead["intent_score"])
        if "quality_score" in lead:
            quality_scores.append(lead["quality_score"])
        
        overall = lead.get("overall_score") or lead.get("lead_score", 0)
        overall_scores.append(overall)
        
        if overall >= 70:
            status_counts["hot"] += 1
        elif overall >= 50:
            status_counts["qualified"] += 1
        elif overall >= 30:
            status_counts["warm"] += 1
        else:
            status_counts["cold"] += 1
    
    def avg(lst):
        return round(sum(lst) / len(lst), 1) if lst else 0
    
    return {
        "total_leads": len(leads),
        "status_distribution": status_counts,
        "averages": {
            "fit": avg(fit_scores),
            "engagement": avg(engagement_scores),
            "intent": avg(intent_scores),
            "quality": avg(quality_scores),
            "overall": avg(overall_scores),
        },
        "ranges": {
            "fit": {"min": min(fit_scores) if fit_scores else 0, "max": max(fit_scores) if fit_scores else 0},
            "engagement": {"min": min(engagement_scores) if engagement_scores else 0, "max": max(engagement_scores) if engagement_scores else 0},
            "intent": {"min": min(intent_scores) if intent_scores else 0, "max": max(intent_scores) if intent_scores else 0},
            "quality": {"min": min(quality_scores) if quality_scores else 0, "max": max(quality_scores) if quality_scores else 0},
            "overall": {"min": min(overall_scores) if overall_scores else 0, "max": max(overall_scores) if overall_scores else 0},
        },
    }


if __name__ == "__main__":
    # Test with sample lead
    sample_lead = {
        "phone": "+5511999999999",
        "name": "Test Lead",
        "email": "test@example.com",
        "visa_interest": "EB-2 NIW",
        "consultation_scheduled": True,
        "consultation_type": "paid",
        "message_count": 15,
        "last_activity_at": datetime.now().isoformat(),
        "intake_form_final_score": 75,
        "is_urgent": True,
    }
    
    logging.basicConfig(level=logging.INFO)
    scores = calculate_all_scores(sample_lead)
    logger.info("Sample Lead Scores:")
    logger.info(get_score_summary(scores))
    logger.info("Full breakdown:")
    for key, value in scores.items():
        logger.info("  %s: %s", key, value)
