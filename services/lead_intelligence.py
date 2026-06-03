"""
CaseHub - Lead Intelligence Service
LLM-powered conversation analysis, signal detection, and closing tips.

Uses Gemini 2.0 Flash to analyze WhatsApp/email conversations and detect
behavioral signals that indicate where a lead is in the buying journey.
"""

import os
import re
import json
import httpx
import logging
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


# =============================================================================
# SIGNAL DEFINITIONS
# =============================================================================

SIGNAL_TYPES = {
    "pre_obligational": {
        "information_gathering": "Asking general questions about visas/process",
        "eligibility_check": "Asking 'do I qualify?' type questions",
        "timeline_inquiry": "Asking about processing times",
        "comparison_shopping": "Mentioning other firms or comparing options",
        "price_sensitivity": "Asking about costs without commitment",
    },
    "obligational": {
        "ready_to_schedule": "Expressing desire to book consultation",
        "document_ready": "Offering to send documents",
        "payment_intent": "Asking about payment methods/plans",
        "urgency_expressed": "Expressing time pressure to act",
        "referral_mention": "Mentioning they were referred by someone",
        "family_involvement": "Involving spouse/family in decision",
    },
    "risk": {
        "going_cold": "Decreasing response frequency or engagement",
        "competitor_mention": "Naming another law firm",
        "objection_raised": "Doubt about price, timeline, or outcome",
        "ghosting": "No response for 3+ days after active conversation",
        "negative_sentiment": "Expressing frustration or disappointment",
    },
}


# =============================================================================
# PROMPTS
# =============================================================================

SIGNAL_DETECTION_PROMPT = """You are a lead intelligence analyst for an immigration law firm.

Analyze this conversation between a potential client and our team/chatbot. Detect behavioral signals indicating where this lead is in the buying journey.

LEAD CONTEXT:
- Name: {lead_name}
- Visa Interest: {visa_interest}
- Pipeline Stage: {pipeline_stage}
- Current Score: {lead_score}/100
- Days Since First Contact: {days_since_first_contact}
- Source: {source}

CONVERSATION ({message_count} messages):
{conversation_text}

Classify signals into these categories:

PRE-OBLIGATIONAL (gathering info, not committed):
- information_gathering, eligibility_check, timeline_inquiry, comparison_shopping, price_sensitivity

OBLIGATIONAL (moving toward commitment):
- ready_to_schedule, document_ready, payment_intent, urgency_expressed, referral_mention, family_involvement

RISK (potential to lose the lead):
- going_cold, competitor_mention, objection_raised, ghosting, negative_sentiment

Also determine the appropriate pipeline stage for this lead based on the conversation content:
- NEW_LEAD: No meaningful engagement beyond initial contact
- LEAD_QUALIFICATION: Asking questions, gathering information, showing interest
- INTAKE_CALL: Providing case details, answering intake questions, deep engagement
- CONSULTATION: Ready to schedule or has scheduled consultation, discussed payment, was referred, completed intake form

Respond ONLY with valid JSON (no markdown, no code blocks):
{{
    "signals": [
        {{
            "type": "pre_obligational|obligational|risk",
            "name": "signal_name",
            "confidence": 0.0-1.0,
            "evidence": "exact quote or observation",
            "recommendation": "specific action for the paralegal"
        }}
    ],
    "conversation_summary": "2-3 sentence summary in Portuguese",
    "risk_level": "low|medium|high",
    "opportunity_score": 0-100,
    "suggested_stage": "NEW_LEAD|LEAD_QUALIFICATION|INTAKE_CALL|CONSULTATION",
    "next_best_action": "specific recommended next step in Portuguese",
    "closing_tips": [
        {{
            "tip": "specific actionable advice in Portuguese",
            "priority": "high|medium|low",
            "reason": "why this tip matters"
        }}
    ]
}}"""


# =============================================================================
# CORE INTELLIGENCE SERVICE
# =============================================================================

async def call_gemini(prompt: str, temperature: float = 0.4, max_tokens: int = 1500) -> Optional[str]:
    """Call Gemini API and return text response."""
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set")
        return None

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                GEMINI_URL,
                params={"key": GEMINI_API_KEY},
                json={
                    "contents": [
                        {"role": "user", "parts": [{"text": prompt}]}
                    ],
                    "generationConfig": {
                        "temperature": temperature,
                        "maxOutputTokens": max_tokens,
                        "responseMimeType": "application/json",
                    }
                }
            )

            if response.status_code == 200:
                data = response.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "")

            logger.error(f"Gemini API error: {response.status_code} - {response.text[:200]}")
            return None

    except Exception as e:
        logger.error(f"Gemini API call failed: {e}")
        return None


def parse_gemini_json(text: str) -> Optional[dict]:
    """Parse JSON response from Gemini, handling common formatting issues."""
    if not text:
        return None
    try:
        # Try direct parse first
        return json.loads(text)
    except json.JSONDecodeError:
        # Strip markdown code blocks if present
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse Gemini JSON: {text[:200]}")
            return None


async def analyze_lead_conversation(
    lead: dict,
    conversation_text: str,
    message_count: int = 0
) -> dict:
    """
    Run full LLM analysis on a lead's conversation.
    Returns intelligence dict to store in lead record.
    """
    if not conversation_text or len(conversation_text.strip()) < 20:
        return {
            "signals": [],
            "closing_tips": [],
            "risk_level": "low",
            "opportunity_score": 0,
            "conversation_summary": "Sem conversas suficientes para analise.",
            "next_best_action": "Aguardar mais interacao do lead.",
            "last_analyzed_at": datetime.utcnow().isoformat(),
            "analysis_version": 1,
        }

    # Calculate days since first contact
    days_since = 0
    first_contact = lead.get("first_contact_at") or lead.get("created_at", "")
    if first_contact:
        try:
            fc = datetime.fromisoformat(first_contact.replace("Z", "+00:00"))
            days_since = (datetime.utcnow() - fc.replace(tzinfo=None)).days
        except (ValueError, TypeError):
            pass

    # Truncate conversation to ~4000 chars for token efficiency
    if len(conversation_text) > 4000:
        conversation_text = conversation_text[-4000:]

    prompt = SIGNAL_DETECTION_PROMPT.format(
        lead_name=lead.get("name", "Unknown"),
        visa_interest=lead.get("visa_interest", "Not specified"),
        pipeline_stage=lead.get("pipeline_stage", "NEW_LEAD"),
        lead_score=lead.get("lead_score", 0),
        days_since_first_contact=days_since,
        source=lead.get("source", "Unknown"),
        message_count=message_count or "unknown",
        conversation_text=conversation_text,
    )

    raw_response = await call_gemini(prompt, temperature=0.3)
    result = parse_gemini_json(raw_response)

    if not result:
        return {
            "signals": [],
            "closing_tips": [],
            "risk_level": "low",
            "opportunity_score": lead.get("lead_score", 0),
            "conversation_summary": "Analise LLM indisponivel no momento.",
            "next_best_action": "Tentar novamente mais tarde.",
            "last_analyzed_at": datetime.utcnow().isoformat(),
            "analysis_version": 1,
            "error": "gemini_parse_failed",
        }

    # Normalize and validate the response
    valid_stages = {"NEW_LEAD", "LEAD_QUALIFICATION", "INTAKE_CALL", "CONSULTATION"}
    suggested = result.get("suggested_stage", "")

    intelligence = {
        "signals": _validate_signals(result.get("signals", [])),
        "closing_tips": result.get("closing_tips", [])[:5],
        "risk_level": result.get("risk_level", "low") if result.get("risk_level") in ("low", "medium", "high") else "low",
        "opportunity_score": max(0, min(100, int(result.get("opportunity_score", 0)))),
        "suggested_stage": suggested if suggested in valid_stages else "",
        "conversation_summary": str(result.get("conversation_summary", ""))[:500],
        "next_best_action": str(result.get("next_best_action", ""))[:300],
        "last_analyzed_at": datetime.utcnow().isoformat(),
        "analysis_version": 2,
    }

    return intelligence


def _validate_signals(signals: list) -> list:
    """Validate and clean signal list from LLM output."""
    valid = []
    valid_types = set(SIGNAL_TYPES.keys())
    valid_names = set()
    for stype in SIGNAL_TYPES.values():
        valid_names.update(stype.keys())

    for s in (signals or [])[:10]:
        if not isinstance(s, dict):
            continue
        if s.get("type") not in valid_types:
            continue
        if s.get("name") not in valid_names:
            continue

        valid.append({
            "type": s["type"],
            "name": s["name"],
            "confidence": max(0.0, min(1.0, float(s.get("confidence", 0.5)))),
            "evidence": str(s.get("evidence", ""))[:200],
            "recommendation": str(s.get("recommendation", ""))[:200],
            "timestamp": datetime.utcnow().isoformat(),
            "channel": "whatsapp",
        })

    return valid


# =============================================================================
# INTELLIGENCE DATA MANAGEMENT
# =============================================================================

async def analyze_email_formality(lead: dict, email_texts: List[str]) -> dict:
    """
    Analyze formality of lead's email communications.
    Returns formality score and analysis.
    """
    if not email_texts:
        return {"email_formality_score": 0, "analysis": "No emails to analyze"}

    combined = "\n---\n".join(email_texts[:5])  # Max 5 emails
    if len(combined) > 2000:
        combined = combined[:2000]

    prompt = f"""Analyze the formality and professionalism of these emails from a potential immigration law client.

EMAILS:
{combined}

Rate formality 0-100 based on:
- Professional greeting/closing (0-25)
- Clear subject/purpose (0-25)
- Grammar and structure (0-25)
- Specificity of legal questions (0-25)

Respond ONLY with valid JSON:
{{
    "formality_score": 0-100,
    "indicators": ["list of formality indicators found"],
    "assessment": "one sentence assessment in Portuguese"
}}"""

    raw = await call_gemini(prompt, temperature=0.2, max_tokens=500)
    result = parse_gemini_json(raw)

    if result:
        return {
            "email_formality_score": max(0, min(100, int(result.get("formality_score", 0)))),
            "indicators": result.get("indicators", [])[:5],
            "assessment": str(result.get("assessment", ""))[:200],
        }

    return {"email_formality_score": 50, "analysis": "LLM analysis unavailable, default score"}


# =============================================================================
# CONTENT-BASED PIPELINE STAGE CLASSIFICATION
# =============================================================================

# The META ad auto-message - NOT a real engagement signal
_META_AUTO_VARIANTS = [
    'tenho interesse e queria mais informacoes',
    'tenho interesse e queria mais informações',
    'i would like to know more about your immigration services',
]

_GREETINGS = frozenset({
    'ola', 'oi', 'bom dia', 'boa tarde', 'boa noite', 'hi', 'hello', 'hey',
    'sim', 'ok', 'obrigado', 'obrigada', 'grato', 'grata', 'otimo', 'perfeito',
    'tudo bem', 'blz', 'valeu', 'thanks', 'thank you', 'yes', 'no', 'nao', 'nope',
})

PIPELINE_STAGES_ORDER = [
    "NEW_LEAD", "LEAD_QUALIFICATION", "INTAKE_CALL",
    "CONSULTATION", "CLOSING", "VISA_IN_PROGRESS",
]


def _is_auto_message(msg: str) -> bool:
    """Check if a message is an auto-generated META ad click or a simple greeting."""
    msg_clean = msg.lower().strip()
    for p in '.,!?':
        msg_clean = msg_clean.replace(p, '')
    for auto in _META_AUTO_VARIANTS:
        if auto in msg_clean:
            return True
    if msg_clean in _GREETINGS:
        return True
    return False


def classify_lead_stage_from_content(
    lead: dict,
    conversation_text: str,
    intelligence: Optional[dict] = None,
) -> Tuple[str, str]:
    """
    Classify a lead's pipeline stage based on actual conversation content.

    Uses deterministic keyword/pattern analysis on WhatsApp conversation text,
    optionally enhanced by LLM intelligence signals.

    Returns: (suggested_stage, reason)

    Stage criteria:
    - CONSULTATION: Agreed to schedule, discussed payment, was referred, or completed 25+ intake questions
    - INTAKE_CALL: Providing case details, started intake form, or high engagement (5+ real msgs)
    - LEAD_QUALIFICATION: Asked about visas, asked substantive questions, or has real responses
    - NEW_LEAD: Only sent auto-message or no meaningful engagement
    """
    if not conversation_text or len(conversation_text.strip()) < 20:
        return 'NEW_LEAD', 'no_conversation'

    text_lower = conversation_text.lower()
    lines = conversation_text.strip().split('\n')

    # Extract lead messages (not bot messages)
    lead_msgs_raw = []
    for line in lines:
        if '] LEAD:' in line:
            msg = line.split('] LEAD:', 1)[-1].strip()
            lead_msgs_raw.append(msg)

    if not lead_msgs_raw:
        return 'NEW_LEAD', 'no_lead_messages'

    # Filter out auto-messages to get REAL lead messages
    real_msgs = [m for m in lead_msgs_raw if not _is_auto_message(m)]
    real_text = ' '.join([m.lower() for m in real_msgs])

    if not real_msgs:
        return 'NEW_LEAD', 'only_auto_msg'

    # Count intake form progress
    intake_qs = re.findall(r'pergunta (\d+) de 45|question (\d+) of 45', text_lower)
    max_q = max([int(q[0] or q[1]) for q in intake_qs], default=0)

    # === CONSULTATION: strong buying signals ===
    has_scheduling = any(w in real_text for w in [
        'vamos sim', 'quero agendar', 'quero consulta', 'want to schedule',
        'i want to book', 'yes i will be there', 'vou sim', 'quero marcar',
        'agendado', 'i will be there', 'confirmo', 'that works for me',
        'can we schedule', 'vamos agendar', 'quero a consulta',
    ])
    has_payment = any(w in real_text for w in [
        'parcela', 'parcelamento', 'pagamento', 'pagar', 'quanto custa',
        'custos do processo', 'honorarios', 'valores do processo',
        'formas de pagamento', 'credit card', 'cartao',
    ])
    has_referral = any(w in real_text for w in [
        'referred', 'indicacao', 'indicou', 'recomendou', 'been referred',
    ])
    deep_intake = max_q >= 25

    # Also check LLM signals if available
    llm_consult_signal = False
    if intelligence:
        for sig in intelligence.get("signals", []):
            if sig.get("type") == "obligational" and sig.get("confidence", 0) >= 0.7:
                if sig.get("name") in ("ready_to_schedule", "payment_intent"):
                    llm_consult_signal = True
                    break
        # LLM suggested stage
        llm_stage = intelligence.get("suggested_stage", "")
        if llm_stage == "CONSULTATION" and intelligence.get("opportunity_score", 0) >= 70:
            llm_consult_signal = True

    consult_score = sum([has_scheduling, has_payment, has_referral, deep_intake, llm_consult_signal])
    if consult_score >= 1:
        reasons = []
        if has_scheduling: reasons.append('scheduling')
        if has_payment: reasons.append('payment')
        if has_referral: reasons.append('referral')
        if deep_intake: reasons.append('intake_q%d' % max_q)
        if llm_consult_signal and not reasons: reasons.append('llm_signal')
        return 'CONSULTATION', '+'.join(reasons)

    # === INTAKE_CALL: providing case info, doing intake ===
    started_intake = max_q >= 1
    has_case_details = any(w in real_text for w in [
        'meu passaporte', 'meu visto', 'my passport', 'my visa',
        'tenho cidadania', 'moro nos eua', 'i live in',
        'minha esposa', 'meu marido', 'my wife', 'my husband',
        'fiquei la', 'voltei', 'negaram', 'overstay', 'deportado',
        'castigo', 'my case', 'fui deportado', 'fiquei mais tempo',
        'passei do prazo', 'visto vencido', 'expired visa',
        'meus documentos', 'my documents', 'curriculo', 'cv',
        'pop the details',
    ])
    has_detailed_msgs = any(len(m) > 80 for m in real_msgs)
    high_engagement = len(real_msgs) >= 5
    gave_email = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', real_text) is not None

    intake_score = sum([started_intake, has_case_details, has_detailed_msgs, high_engagement])
    if intake_score >= 2:
        return 'INTAKE_CALL', 'multiple_intake_signals'
    if intake_score >= 1 and (len(real_msgs) >= 3 or gave_email):
        return 'INTAKE_CALL', 'intake_signal+engagement'

    # === LEAD_QUALIFICATION: showing interest ===
    asked_visa = any(w in real_text for w in [
        'green card', 'eb-2', 'eb2', 'niw', 'h-1b', 'h1b', 'l-1', 'l1',
        'e-2', 'e2', 'o-1', 'o1', 'visto de trabalho', 'work visa',
        'cidadania', 'citizenship', 'visto de turismo', 'tourist visa',
        'b1', 'b2', 'trabalhar nos eua', 'morar nos eua',
        'ir para os eua', 'imigrar',
    ])
    asked_questions = any(w in real_text for w in [
        'como funciona', 'how does it work', 'quanto tempo', 'how long',
        'processo', 'process', 'requisitos', 'requirements',
        'me qualifico', 'do i qualify', 'elegibilidade', 'quanto custa',
        'possibilidade',
    ])
    has_substance = len(real_msgs) == 1 and len(real_msgs[0]) > 25

    if asked_visa or asked_questions or len(real_msgs) >= 2 or has_substance:
        return 'LEAD_QUALIFICATION', 'engaged'

    if len(real_msgs) >= 1:
        return 'LEAD_QUALIFICATION', 'has_response'

    return 'NEW_LEAD', 'no_real_engagement'


def should_update_pipeline_stage(
    current_stage: str,
    suggested_stage: str,
    allow_demotion: bool = False,
) -> bool:
    """
    Determine if a lead's pipeline stage should be updated.

    By default only promotes (moves forward in pipeline).
    Set allow_demotion=True to also allow moving backward.
    Never touches CLOSING or VISA_IN_PROGRESS (those are set manually).
    """
    if current_stage in ("CLOSING", "VISA_IN_PROGRESS"):
        return False  # Never auto-change these
    if suggested_stage in ("CLOSING", "VISA_IN_PROGRESS"):
        return False  # Never auto-promote to these
    if current_stage == suggested_stage:
        return False

    try:
        current_idx = PIPELINE_STAGES_ORDER.index(current_stage)
        suggested_idx = PIPELINE_STAGES_ORDER.index(suggested_stage)
    except ValueError:
        return False

    if suggested_idx > current_idx:
        return True  # Promotion
    if allow_demotion and suggested_idx < current_idx:
        return True  # Demotion (only with flag)

    return False


def get_lead_intelligence(lead: dict) -> dict:
    """Get cached intelligence from lead record."""
    return lead.get("intelligence", {})


def has_fresh_intelligence(lead: dict, max_age_hours: int = 2) -> bool:
    """Check if lead has recent intelligence data."""
    intel = lead.get("intelligence", {})
    last = intel.get("last_analyzed_at")
    if not last:
        return False
    try:
        analyzed_at = datetime.fromisoformat(last)
        age = (datetime.utcnow() - analyzed_at).total_seconds() / 3600
        return age < max_age_hours
    except (ValueError, TypeError):
        return False
