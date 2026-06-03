"""
CaseHub - Email Content Analyzer
Uses Perplexity AI to classify emails and determine if auto-reply should be sent
v2.0 - 02/02/2026 - Improved urgency detection (less false positives)
"""
from dotenv import load_dotenv
load_dotenv()

import os
import re
import httpx
import logging
from typing import Tuple, Optional
from enum import Enum

logger = logging.getLogger(__name__)

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")


class EmailClassification(str, Enum):
    SKIP = "SKIP"      # Confirmação/agradecimento - não enviar auto-reply
    REPLY = "REPLY"    # Questão legal/pedido - enviar auto-reply
    URGENT = "URGENT"  # Urgente - enviar auto-reply + notificar Victor


# Keywords for fallback classification
SKIP_KEYWORDS = [
    "obrigado", "obrigada", "thanks", "thank you", "gracias",
    "ok", "okay", "recebi", "received", "got it", "entendi",
    "perfeito", "perfect", "ótimo", "great", "understood",
    "até mais", "abraços", "regards", "cheers", "valeu",
    "combinado", "certo", "tudo bem", "show", "beleza",
    "sounds good", "will do", "noted", "acknowledged"
]

# Follow-up patterns - these are NOT urgent, just normal follow-ups
FOLLOWUP_KEYWORDS = [
    "any update", "any updates", "further update", "any news",
    "following up", "follow up", "checking in", "status update",
    "let me know", "waiting for", "when will", "how long",
    "any progress", "have you reviewed", "reviewed the",
    "alguma novidade", "algum update", "tem novidade",
    "aguardando", "esperando", "já analisou", "já revisou"
]

# URGENT keywords - ONLY true emergencies
# Must indicate immediate risk or very short deadline
URGENT_KEYWORDS = [
    # Detention/arrest
    "detention", "detained", "arrested", "preso", "detido", "detenção",
    "ice raid", "taken into custody",
    # Deportation
    "deportation", "deportação", "removal order", "removal proceedings",
    "deportado", "being deported", "order to leave",
    # Court dates (imminent)
    "court date tomorrow", "hearing tomorrow", "audiência amanhã",
    "court date today", "hearing today", "audiência hoje",
    # Denial/RFE (petition issues)
    "denial", "denied", "negado", "negativa", "indeferido",
    "rfe received", "rfe response", "request for evidence",
    # True emergencies
    "emergency", "emergência", "emergencia",
    "life threatening", "medical emergency",
    # Explicit urgency words with context
    "need help now", "preciso de ajuda agora",
    "please call immediately", "ligue imediatamente"
]

# NOT urgent - even if they say "urgent" casually
NOT_URGENT_OVERRIDES = [
    "not urgent", "no rush", "when you have time", "at your convenience",
    "não é urgente", "sem pressa", "quando puder",
    "just following up", "just checking", "quick question"
]


def classify_with_keywords(subject: str, body: str) -> EmailClassification:
    """Fallback classification using keywords - more conservative urgency detection"""
    text = f"{subject} {body}".lower()

    # First check for NOT urgent overrides
    for keyword in NOT_URGENT_OVERRIDES:
        if keyword in text:
            return EmailClassification.REPLY

    # Check for follow-up patterns - these are REPLY, not URGENT
    for keyword in FOLLOWUP_KEYWORDS:
        if keyword in text:
            return EmailClassification.REPLY

    # Check for true urgent situations (must be explicit emergency/detention/deportation)
    urgent_matches = 0
    for keyword in URGENT_KEYWORDS:
        if keyword in text:
            urgent_matches += 1
    
    # Require at least one strong urgent keyword
    if urgent_matches >= 1:
        # Double-check it is not a simple follow-up disguised
        if any(fw in text for fw in ["update", "status", "reviewed", "checking"]):
            return EmailClassification.REPLY
        return EmailClassification.URGENT

    # Check skip keywords (only for short emails)
    for keyword in SKIP_KEYWORDS:
        if keyword in text:
            # Only skip if the email is SHORT (< 100 chars body)
            if len(body.strip()) < 100:
                return EmailClassification.SKIP

    # Default to REPLY for anything substantive
    return EmailClassification.REPLY


async def classify_with_ai(subject: str, body: str) -> Optional[EmailClassification]:
    """Classify email using Perplexity AI with improved prompt"""
    if not PERPLEXITY_API_KEY:
        logger.warning("PERPLEXITY_API_KEY not set, using keyword fallback")
        return None

    prompt = f"""Analyze this email from a client to an immigration law firm.
Classify it as exactly one of:
- SKIP: Simple confirmation, thank you, acknowledgment, or conversation closure (e.g., "ok thanks", "got it", "obrigado")
- REPLY: Legal question, request for information, status update request, follow-up, or requires a response
- URGENT: ONLY for TRUE EMERGENCIES - detention, arrest, deportation proceedings, court date within 48 hours, or immediate legal crisis

IMPORTANT: Simple follow-ups asking for status/updates are NOT urgent. They are REPLY.
Examples of REPLY (not urgent):
- "Any updates on my case?"
- "Following up on my documents"
- "Have you reviewed my letters?"
- "When will my petition be filed?"

Examples of URGENT (true emergencies only):
- "I was arrested by ICE"
- "I have a court date tomorrow"
- "Received deportation order"
- "Emergency - need help now"

Email Subject: {subject}
Email Body: {body[:1000]}

Respond with ONLY one word: SKIP, REPLY, or URGENT"""

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "sonar",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 10,
                    "temperature": 0.1
                }
            )

            if response.status_code == 200:
                data = response.json()
                answer = data["choices"][0]["message"]["content"].strip().upper()

                if "URGENT" in answer:
                    return EmailClassification.URGENT
                elif "SKIP" in answer:
                    return EmailClassification.SKIP
                else:
                    return EmailClassification.REPLY
            else:
                logger.error(f"Perplexity API error: {response.status_code}")
                return None

    except Exception as e:
        logger.error(f"Error calling Perplexity AI: {e}")
        return None


async def analyze_email(subject: str, body: str) -> Tuple[EmailClassification, str]:
    """
    Analyze email content and return classification with reason.
    Uses keywords first for obvious cases, then AI for nuanced analysis.
    
    v2.0: Keywords first for follow-ups to prevent false urgent alerts

    Returns:
        Tuple of (classification, reason)
    """
    text = f"{subject} {body}".lower()
    
    # STEP 1: Check for obvious follow-ups (BEFORE AI) - these are never urgent
    for keyword in FOLLOWUP_KEYWORDS:
        if keyword in text:
            return (EmailClassification.REPLY, "Follow-up detected (keyword)")
    
    # STEP 2: Check for NOT urgent overrides
    for keyword in NOT_URGENT_OVERRIDES:
        if keyword in text:
            return (EmailClassification.REPLY, "Not urgent override (keyword)")
    
    # STEP 3: Check for obvious SKIP (short confirmations)
    if len(body.strip()) < 100:
        for keyword in SKIP_KEYWORDS:
            if keyword in text:
                return (EmailClassification.SKIP, "Simple confirmation (keyword)")
    
    # STEP 4: Check for TRUE urgent emergencies
    urgent_count = sum(1 for kw in URGENT_KEYWORDS if kw in text)
    if urgent_count >= 1:
        # Verify it is not mixed with follow-up language
        followup_count = sum(1 for kw in FOLLOWUP_KEYWORDS if kw in text)
        if followup_count == 0:
            return (EmailClassification.URGENT, f"Urgent keyword detected ({urgent_count} matches)")
    
    # STEP 5: Try AI for nuanced cases
    ai_result = await classify_with_ai(subject, body)
    
    if ai_result:
        # Extra safety: if AI says urgent, double-check with keywords
        if ai_result == EmailClassification.URGENT:
            # Verify there is at least one true urgent keyword
            if urgent_count == 0:
                return (EmailClassification.REPLY, "AI suggested urgent but no urgent keywords found")
        return (ai_result, "AI classification")

    # Fallback to keyword classification
    keyword_result = classify_with_keywords(subject, body)
    return (keyword_result, "Keyword fallback")
