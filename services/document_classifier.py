"""
CaseHub - Multi-LLM Document Classifier Service
Classifies immigration documents by type with multiple LLM fallbacks.

Chain: LM Studio Local → Gemini → Perplexity → Filename Pattern Matching
"""
import os
import re
import logging
from typing import Dict, Any, Optional, Tuple
from pathlib import Path

from config import settings

try:
    import httpx
except ImportError:
    httpx = None

try:
    from dotenv import load_dotenv
    # Load .env from casehub directory
    env_path = Path(__file__).parent.parent / '.env'
    load_dotenv(dotenv_path=env_path)
except ImportError:
    pass  # dotenv not available, use system env vars

logger = logging.getLogger(__name__)

# Document types - ALL IN ENGLISH (for Client Portal)
# Updated: 2026-03-03 - Aligned with migration 2026-03-03_standardize_categories_english.sql
DOCUMENT_TYPES = [
    "Passport", "I-94 Travel Record", "Visa", "EAD Card", "Green Card",
    "Birth Certificate", "Marriage Certificate", "Diploma", "Academic Transcript",
    "Employment Letter", "Employment Contract", "Tax Return", "Pay Stub", "Financial Statement",
    "Letter of Recommendation", "Resume/CV", "Award/Recognition", "Professional Membership",
    "Publication", "Supporting Evidence", "USCIS Form",
    "Receipt Notice", "Approval Notice", "Request for Evidence", "Personal Statement",
    "Medical Records", "Police Certificate", "Portfolio/Work Samples", "Photo",
    "Other Document"
]

# Exhibit mapping by document type - ALL IN ENGLISH
# Updated: 2026-03-03
EXHIBIT_MAP = {
    # Personal Documents (Exhibit C)
    "Passport": "C",
    "I-94 Travel Record": "C",
    "Visa": "C",
    "EAD Card": "C",
    "Green Card": "C",
    "Birth Certificate": "C",
    "Marriage Certificate": "C",
    "Photo": "C",

    # Educational (Exhibit C)
    "Diploma": "C",
    "Academic Transcript": "C",

    # Professional (Exhibit C/D)
    "Employment Letter": "C",
    "Employment Contract": "C",
    "Letter of Recommendation": "D",
    "Resume/CV": "C",
    "Award/Recognition": "C",
    "Professional Membership": "C",
    "Publication": "D",
    "Portfolio/Work Samples": "D",

    # Financial (Exhibit E)
    "Tax Return": "E",
    "Pay Stub": "E",
    "Financial Statement": "E",

    # Immigration Forms (Exhibit A)
    "USCIS Form": "A",
    "Receipt Notice": "A",
    "Approval Notice": "A",
    "Request for Evidence": "A",

    # Other
    "Supporting Evidence": None,  # Needs context-based sub-classification
    "Personal Statement": "D",
    "Medical Records": "C",
    "Police Certificate": "C",
    "Other Document": None  # Needs manual review
}

# Filename pattern matching (fallback) - ALL IN ENGLISH
# Updated: 2026-03-03 - Keywords include Portuguese/Spanish for backward compatibility
FILENAME_PATTERNS = {
    # Personal Documents
    "Passport": ["passport", "pasaporte", "passaporte"],
    "I-94 Travel Record": ["i-94", "i94", "arrival", "departure", "travel record"],
    "Visa": ["visa", "visto"],
    "EAD Card": ["ead", "employment authorization", "work permit"],
    "Green Card": ["green card", "permanent resident", "i-551"],
    "Birth Certificate": ["birth", "nascimento", "certidao"],
    "Marriage Certificate": ["marriage", "casamento", "wedding"],
    "Photo": ["photo", "photograph", "foto", "picture"],

    # Educational
    "Diploma": ["diploma", "degree", "graduacao", "phd", "master", "bachelor"],
    "Academic Transcript": ["transcript", "historico", "grades", "academic record"],

    # Professional
    "Employment Letter": ["employment letter", "carta de emprego", "job letter", "offer letter"],
    "Employment Contract": ["contract", "contrato", "agreement"],
    "Letter of Recommendation": ["recommendation", "recomendacao", "lor", "reference letter"],
    "Resume/CV": ["resume", "cv", "curriculum", "curriculo"],
    "Award/Recognition": ["award", "prize", "recognition", "premio"],
    "Professional Membership": ["membership", "association", "society", "associacao"],
    "Publication": ["publication", "article", "paper", "journal", "publicacao"],
    "Portfolio/Work Samples": ["portfolio", "work sample", "sample", "artwork"],

    # Financial
    "Tax Return": ["tax return", "1040", "w-2", "imposto"],
    "Pay Stub": ["pay stub", "paystub", "paycheck", "contracheque", "holerite"],
    "Financial Statement": ["bank statement", "extrato", "financial", "assets"],

    # Immigration
    "USCIS Form": ["i-140", "i-485", "i-765", "i-131", "i-130", "i-129", "g-28", "i-907", "eta-9089", "g-1145"],
    "Receipt Notice": ["receipt", "recibo", "i-797c"],
    "Approval Notice": ["approval", "aprovacao", "approved", "i-797"],
    "Request for Evidence": ["rfe", "request for evidence", "solicitacao"],

    # Other
    "Supporting Evidence": ["evidence", "exhibit", "prova", "proof"],
    "Personal Statement": ["statement", "declaracao", "letter"],
    "Medical Records": ["medical", "exam", "vaccination", "health"],
    "Police Certificate": ["police", "criminal", "background check", "antecedentes"]
}

# Classification prompt template - ALL IN ENGLISH
# Updated: 2026-03-03
CLASSIFICATION_PROMPT = """Analyze this immigration document and classify it into exactly ONE of these categories.
Respond with ONLY the category name from the list below, nothing else.

Document filename: {filename}
{content_section}

Categories (MUST use exact spelling):
- Passport
- I-94 Travel Record
- Visa
- EAD Card
- Green Card
- Birth Certificate
- Marriage Certificate
- Diploma
- Academic Transcript
- Employment Letter
- Employment Contract
- Tax Return
- Pay Stub
- Financial Statement
- Letter of Recommendation
- Resume/CV
- Award/Recognition
- Professional Membership
- Publication
- Supporting Evidence
- USCIS Form
- Receipt Notice
- Approval Notice
- Request for Evidence
- Personal Statement
- Medical Records
- Police Certificate
- Portfolio/Work Samples
- Photo
- Other Document

Category:"""


def classify_by_filename(filename: str) -> Tuple[str, float]:
    """Classify document based on filename patterns. Returns (doc_type, confidence)."""
    filename_lower = filename.lower()
    # Also create a normalized version (underscores/hyphens → spaces)
    filename_normalized = filename_lower.replace("_", " ").replace("-", " ")
    for doc_type, keywords in FILENAME_PATTERNS.items():
        for keyword in keywords:
            # Match against both original and normalized filename
            if keyword in filename_lower or keyword in filename_normalized:
                return doc_type, 0.6
            # Also try normalized keyword against normalized filename
            kw_normalized = keyword.replace("-", " ").replace("_", " ")
            if kw_normalized in filename_normalized:
                return doc_type, 0.6
    return "Other Document", 0.1  # Fallback category (was "Outro" in Portuguese)


def _validate_llm_response(response_text: str) -> Optional[str]:
    """Validate LLM response against known document types."""
    response_clean = response_text.strip().strip('"').strip("'")
    for doc_type in DOCUMENT_TYPES:
        if doc_type.lower() == response_clean.lower():
            return doc_type
        if doc_type.lower() in response_clean.lower():
            return doc_type
    return None


async def _classify_with_lm_studio(filename: str, content_preview: str = "") -> Optional[Tuple[str, float]]:
    """Classify using LM Studio local endpoint."""
    if httpx is None:
        return None
    lm_studio_url = f"{settings.LM_STUDIO_URL}/v1/chat/completions"

    content_section = f"Content preview (first 500 chars):\n{content_preview[:500]}" if content_preview else ""
    prompt = CLASSIFICATION_PROMPT.format(filename=filename, content_section=content_section)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(lm_studio_url, json={
                "model": "local-model",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 50,
                "temperature": 0.1
            })
            if resp.status_code == 200:
                data = resp.json()
                answer = data["choices"][0]["message"]["content"].strip()
                doc_type = _validate_llm_response(answer)
                if doc_type:
                    logger.info(f"LM Studio classified '{filename}' as '{doc_type}'")
                    return doc_type, 0.85
            logger.warning(f"LM Studio returned unexpected response: {resp.status_code}")
    except Exception as e:
        logger.warning(f"LM Studio unavailable: {e}")
    return None


async def _classify_with_gemini(filename: str, content_preview: str = "") -> Optional[Tuple[str, float]]:
    """Classify using Google Gemini API."""
    if httpx is None:
        return None
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return None

    content_section = f"Content preview (first 500 chars):\n{content_preview[:500]}" if content_preview else ""
    prompt = CLASSIFICATION_PROMPT.format(filename=filename, content_section=content_section)

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 50, "temperature": 0.1}
            })
            if resp.status_code == 200:
                data = resp.json()
                answer = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                doc_type = _validate_llm_response(answer)
                if doc_type:
                    logger.info(f"Gemini classified '{filename}' as '{doc_type}'")
                    return doc_type, 0.80
            logger.warning(f"Gemini returned status {resp.status_code}")
    except Exception as e:
        logger.warning(f"Gemini classification failed: {e}")
    return None


async def _classify_with_perplexity(filename: str, content_preview: str = "") -> Optional[Tuple[str, float]]:
    """Classify using Perplexity API."""
    if httpx is None:
        return None
    api_key = os.getenv("PERPLEXITY_API_KEY", "")
    if not api_key:
        return None

    content_section = f"Content preview (first 500 chars):\n{content_preview[:500]}" if content_preview else ""
    prompt = CLASSIFICATION_PROMPT.format(filename=filename, content_section=content_section)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "llama-3.1-sonar-small-128k-online",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 50,
                    "temperature": 0.1
                }
            )
            if resp.status_code == 200:
                data = resp.json()
                answer = data["choices"][0]["message"]["content"].strip()
                doc_type = _validate_llm_response(answer)
                if doc_type:
                    logger.info(f"Perplexity classified '{filename}' as '{doc_type}'")
                    return doc_type, 0.75
            logger.warning(f"Perplexity returned status {resp.status_code}")
    except Exception as e:
        logger.warning(f"Perplexity classification failed: {e}")
    return None


async def classify_document(filename: str, content_preview: str = "") -> Dict[str, Any]:
    """
    Classify a document using multi-LLM chain with fallbacks.

    Returns dict with: doc_type, confidence, method, suggested_exhibit
    """
    # Try LM Studio Local first
    result = await _classify_with_lm_studio(filename, content_preview)
    if result:
        doc_type, confidence = result
        return {
            "doc_type": doc_type,
            "confidence": confidence,
            "method": "lm_studio",
            "suggested_exhibit": EXHIBIT_MAP.get(doc_type)
        }

    # Fallback 1: Gemini
    result = await _classify_with_gemini(filename, content_preview)
    if result:
        doc_type, confidence = result
        return {
            "doc_type": doc_type,
            "confidence": confidence,
            "method": "gemini",
            "suggested_exhibit": EXHIBIT_MAP.get(doc_type)
        }

    # Fallback 2: Perplexity
    result = await _classify_with_perplexity(filename, content_preview)
    if result:
        doc_type, confidence = result
        return {
            "doc_type": doc_type,
            "confidence": confidence,
            "method": "perplexity",
            "suggested_exhibit": EXHIBIT_MAP.get(doc_type)
        }

    # Fallback 3: Filename pattern matching
    doc_type, confidence = classify_by_filename(filename)
    return {
        "doc_type": doc_type,
        "confidence": confidence,
        "method": "filename_pattern",
        "suggested_exhibit": EXHIBIT_MAP.get(doc_type)
    }


def get_exhibit_for_type(doc_type: str) -> Optional[str]:
    """Get the default exhibit letter for a document type."""
    return EXHIBIT_MAP.get(doc_type)


async def classify_with_ocr(document_id: int, db_session) -> Dict[str, Any]:
    """
    Classify document using OCR text + multi-LLM chain.

    Enhanced version that uses extracted OCR text for more accurate classification.

    Args:
        document_id: Document ID to classify
        db_session: SQLAlchemy database session

    Returns:
        Dictionary with:
            - doc_type: Classified document type
            - confidence: Classification confidence (0.0-1.0)
            - method: Classification method used
            - suggested_exhibit: Exhibit letter (A-M)
            - error: Error message if failed

    Example:
        >>> result = await classify_with_ocr(123, db_session)
        >>> if result.get('error'):
        ...     print(f"Classification failed: {result['error']}")
        ... else:
        ...     print(f"Classified as {result['doc_type']} (confidence: {result['confidence']:.2f})")
    """
    from models.document import Document

    doc = db_session.query(Document).filter(Document.id == document_id).first()
    if not doc:
        return {"error": "Document not found", "doc_type": "Other Document", "confidence": 0.0}

    # Wait for OCR if pending
    if doc.ocr_status == "pending":
        return {
            "error": "OCR not yet completed",
            "retry": True,
            "doc_type": "Other Document",
            "confidence": 0.0
        }

    # Build enhanced context with OCR text
    context = {
        "filename": doc.name,
        "ocr_text": doc.ocr_text[:2000] if doc.ocr_text else "",  # First 2000 chars
        "mime_type": doc.mime_type,
        "client_name": f"{doc.client.last_name}, {doc.client.first_name}" if doc.client else ""
    }

    # Enhanced prompt with OCR text
    if context["ocr_text"]:
        enhanced_prompt = f"""Analyze this immigration document and classify it.

Document: {context['filename']}
Client: {context['client_name']}

Content (first 2000 chars):
{context['ocr_text']}

Classify into ONE category from this list:
{', '.join(DOCUMENT_TYPES)}

Respond in JSON format:
{{"category": "<category name>", "confidence": <0-1>, "reasoning": "<brief explanation>"}}
"""

        # Try LLMs in order with enhanced prompt
        # Priority 1: Gemini (best for document analysis)
        result = await _classify_with_gemini_enhanced(enhanced_prompt)
        if result:
            doc_type, confidence = result
            logger.info(
                f"Document {document_id} classified via Gemini with OCR: "
                f"{doc_type} (confidence: {confidence:.2f})"
            )
            return {
                "doc_type": doc_type,
                "confidence": confidence,
                "method": "gemini_ocr",
                "suggested_exhibit": EXHIBIT_MAP.get(doc_type)
            }

        # Priority 2: Try existing Gemini without enhancement
        result = await _classify_with_gemini(context["filename"], context["ocr_text"])
        if result:
            doc_type, confidence = result
            return {
                "doc_type": doc_type,
                "confidence": confidence,
                "method": "gemini_basic",
                "suggested_exhibit": EXHIBIT_MAP.get(doc_type)
            }

    # Fallback to filename-only classification if no OCR text
    logger.info(f"Document {document_id} has no OCR text, using filename classification")
    return await classify_document(context["filename"], "")


async def _classify_with_gemini_enhanced(prompt: str) -> Optional[Tuple[str, float]]:
    """
    Classify using Gemini with enhanced OCR-based prompt.

    Args:
        prompt: Enhanced prompt with OCR text

    Returns:
        Tuple of (doc_type, confidence) or None if failed
    """
    if not httpx:
        return None

    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        logger.warning("GEMINI_API_KEY not set, skipping Gemini classification")
        return None

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_api_key}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json={
                    "contents": [{
                        "parts": [{"text": prompt}]
                    }],
                    "generationConfig": {
                        "temperature": 0.1,  # Low temperature for consistent classification
                        "maxOutputTokens": 200
                    }
                }
            )

            if response.status_code != 200:
                logger.error(f"Gemini API error: {response.status_code} - {response.text}")
                return None

            data = response.json()

            if not data.get("candidates"):
                return None

            text = data["candidates"][0]["content"]["parts"][0]["text"]

            # Parse JSON response
            import json
            try:
                # Try to extract JSON from response
                json_match = re.search(r'\{.*?\}', text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                    category = result.get("category", "Other Document")
                    confidence = float(result.get("confidence", 0.8))

                    # Validate category
                    if category in DOCUMENT_TYPES:
                        return (category, confidence)

                    # Try fuzzy matching
                    for doc_type in DOCUMENT_TYPES:
                        if doc_type.lower() in category.lower():
                            return (doc_type, confidence * 0.9)  # Reduce confidence for fuzzy match

                    return ("Other Document", 0.5)

            except json.JSONDecodeError:
                logger.warning(f"Failed to parse Gemini JSON response: {text}")

            # Fallback: search for document type in response
            text_lower = text.lower()
            for doc_type in DOCUMENT_TYPES:
                if doc_type.lower() in text_lower:
                    return (doc_type, 0.75)

            return None

    except Exception as e:
        logger.error(f"Gemini enhanced classification failed: {e}")
        return None
