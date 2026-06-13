"""
Meeting Watchdog - LLM Analyzer
Uses Perplexity Sonar to detect meeting confirmations in client emails.
"""

import json
import logging
import os
import re
from typing import Optional, Dict

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"
PERPLEXITY_MODEL = "sonar"

HIGH_CONFIDENCE = float(os.getenv("WATCHDOG_HIGH_CONFIDENCE", "0.85"))
MEDIUM_CONFIDENCE = float(os.getenv("WATCHDOG_MEDIUM_CONFIDENCE", "0.50"))


def _build_prompt(candidate: dict) -> str:
    """Build the LLM prompt from a candidate email."""
    client_info = candidate.get("client_info", {})
    thread = candidate.get("thread_context")

    outbound_section = ""
    if thread and thread.get("is_outbound"):
        outbound_body = thread.get("body", "")[:1500]
        outbound_section = f"""
OUTBOUND EMAIL (what the law firm sent to the client):
Subject: {thread.get('subject', 'N/A')}
Body:
{outbound_body}
"""

    prompt = f"""You are analyzing an email exchange between an immigration law firm (CaseHub) and a client.

Your task: determine if the client's latest email is CONFIRMING a meeting time that was proposed.

CLIENT INFO:
- Name: {client_info.get('name', 'Unknown')}
- Language: {client_info.get('language', 'en')} (pt=Portuguese, en=English)
- Timezone: {client_info.get('timezone', 'ET')}
- Case Type: {client_info.get('case_type', 'Unknown')}
{outbound_section}
CLIENT'S REPLY:
Subject: {candidate.get('subject', '')}
Date: {candidate.get('date', '')}
Body:
{candidate.get('body', '')[:2000]}

INSTRUCTIONS:
1. Is the client confirming a previously proposed meeting time? Look for explicit confirmations like "yes", "confirmed", "works for me", "combinado", "pode ser", "confirmado".
2. If yes, extract the confirmed date and time. Convert to EST (America/New_York). If the client mentions a time in their timezone (e.g., "11 AM CT"), convert it to EST.
3. Determine if the meeting is with the Attorney (Daniel) or a Paralegal.
4. If the client is proposing a DIFFERENT time instead of confirming, that is NOT a confirmation.
5. If the email is about something else entirely (documents, questions, etc.), that is NOT a confirmation.

Respond with ONLY a valid JSON object (no markdown, no extra text):
{{
  "is_meeting_confirmation": true or false,
  "confidence": 0.0 to 1.0,
  "confirmed_datetime_est": "YYYY-MM-DDTHH:MM:SS" or null,
  "meeting_type": "attorney" or "paralegal" or "unknown",
  "client_proposed_alternative": true or false,
  "alternative_description": null or "description of alternative time proposed",
  "language_detected": "en" or "pt",
  "reasoning": "brief explanation"
}}"""

    return prompt


def _extract_json(text: str) -> Optional[dict]:
    """Extract JSON from LLM response, handling markdown code blocks."""
    text = text.strip()

    # Remove markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines if they're code block markers
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in text
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


def _adjust_confidence(llm_result: dict, candidate: dict) -> float:
    """
    Adjust LLM confidence based on context signals.
    Boost if reply-to-proposal. Penalize if no context or invalid time.
    """
    base = llm_result.get("confidence", 0.0)

    # Boost: email is a direct reply to an outbound meeting proposal
    if candidate.get("is_reply_to_proposal"):
        base = min(1.0, base + 0.10)

    # Penalize: no thread context at all
    if not candidate.get("thread_context"):
        base = max(0.0, base - 0.20)

    # Penalize: attorney meeting but time outside Daniel's window
    if llm_result.get("meeting_type") == "attorney" and llm_result.get("confirmed_datetime_est"):
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(llm_result["confirmed_datetime_est"])
            if dt.weekday() not in [2, 3]:  # Not Wed/Thu
                base = max(0.0, base - 0.15)
            if dt.hour < 11 or dt.hour >= 14:
                base = max(0.0, base - 0.15)
        except (ValueError, TypeError):
            pass

    return round(base, 2)


def analyze_candidate(candidate: dict) -> Optional[Dict]:
    """
    Send a candidate email to Perplexity Sonar for meeting confirmation analysis.

    Args:
        candidate: dict from scanner with email content and context

    Returns:
        Analysis result dict with adjusted confidence, or None on failure.
    """
    if not PERPLEXITY_API_KEY:
        logger.error("PERPLEXITY_API_KEY not configured")
        return None

    prompt = _build_prompt(candidate)

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                PERPLEXITY_URL,
                headers={
                    "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": PERPLEXITY_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are an email analysis assistant. Respond only with valid JSON."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 1024,
                    "temperature": 0.1,
                },
            )

            if response.status_code != 200:
                logger.error(f"Perplexity API error {response.status_code}: {response.text[:200]}")
                return None

            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            result = _extract_json(content)
            if not result:
                logger.warning(f"Could not parse LLM JSON response: {content[:200]}")
                return None

            # Adjust confidence
            result["confidence"] = _adjust_confidence(result, candidate)

            # Add classification
            if result["confidence"] >= HIGH_CONFIDENCE:
                result["action"] = "auto_confirm"
            elif result["confidence"] >= MEDIUM_CONFIDENCE:
                result["action"] = "review"
            else:
                result["action"] = "ignore"

            logger.info(
                f"LLM analysis for {candidate.get('sender_name', '?')}: "
                f"confirmation={result.get('is_meeting_confirmation')}, "
                f"confidence={result['confidence']}, action={result['action']}"
            )

            return result

    except httpx.TimeoutException:
        logger.error("Perplexity API timeout")
    except Exception as e:
        logger.error(f"LLM analysis error: {e}")

    return None
