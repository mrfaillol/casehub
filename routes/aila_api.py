"""
CaseHub - AILA Knowledge Base API
Endpoints for semantic search and immigration requirements lookup.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from models import get_db
from auth import get_current_user
import os
import sys

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/aila", tags=["aila"])

# AILA Search Service
AILA_AVAILABLE = False
aila_search = None

try:
    from config import settings as _settings
    sys.path.insert(0, os.path.join(_settings.BASE_DIR, "services"))
    from aila_search import AILASearch

    if AILASearch.is_available():
        aila_search = AILASearch()
        AILA_AVAILABLE = True
        logger.info("[AILA API] Knowledge base loaded: %d documents", aila_search.document_count)
except Exception as e:
    logger.warning("[AILA API] AILA search not available: %s", e)


# =============================================================================
# VISA REQUIREMENTS DATABASE (from AILA materials)
# =============================================================================

VISA_REQUIREMENTS = {
    "EB-1A": {
        "name": "Extraordinary Ability",
        "category": "Employment-Based First Preference",
        "criteria_needed": "3 of 10",
        "criteria": [
            "Receipt of nationally/internationally recognized prizes or awards",
            "Membership in associations requiring outstanding achievements",
            "Published material about the alien in professional publications",
            "Participation as a judge of the work of others",
            "Original contributions of major significance",
            "Authorship of scholarly articles",
            "Display of work at artistic exhibitions or showcases",
            "Leading or critical role in distinguished organizations",
            "High salary or remuneration",
            "Commercial successes in the performing arts"
        ],
        "required_docs": [
            "Form I-140",
            "Evidence of extraordinary ability (3+ criteria)",
            "Evidence of continued work in the field",
            "Passport copy",
            "Academic credentials evaluation",
            "Letters of recommendation (5-8 recommended)"
        ],
        "optional_docs": [
            "Citation reports",
            "Media coverage",
            "Peer review evidence",
            "Membership certificates",
            "Award certificates",
            "Patent documents",
            "Revenue/salary documentation"
        ],
        "filing_fee": 715,
        "premium_fee": 2805,
        "processing_time": "6-12 months (regular), 15 business days (premium)"
    },
    "EB-2 NIW": {
        "name": "National Interest Waiver",
        "category": "Employment-Based Second Preference",
        "criteria_needed": "All 3 prongs (Matter of Dhanasar)",
        "criteria": [
            "Prong 1: Proposed endeavor has substantial merit and national importance",
            "Prong 2: Well positioned to advance the proposed endeavor",
            "Prong 3: Balance of factors shows benefit to waive job offer/labor certification"
        ],
        "required_docs": [
            "Form I-140",
            "Advanced degree evidence OR exceptional ability (6 criteria)",
            "Personal statement detailing proposed endeavor",
            "Evidence of national importance",
            "Letters of recommendation (5-8 recommended)",
            "Passport copy",
            "Academic credentials evaluation"
        ],
        "optional_docs": [
            "Business plan (if entrepreneurial)",
            "Citation reports",
            "Media coverage",
            "Patents",
            "Government statistics supporting field importance",
            "Contracts or funding letters"
        ],
        "filing_fee": 715,
        "premium_fee": 2805,
        "processing_time": "12-18 months (regular), 45 business days (premium)"
    },
    "H-1B": {
        "name": "Specialty Occupation",
        "category": "Non-Immigrant",
        "criteria_needed": "All requirements",
        "criteria": [
            "Bachelor's degree or equivalent in specialty field",
            "Job requires theoretical and practical application of specialized knowledge",
            "Employer-employee relationship",
            "Prevailing wage offered"
        ],
        "required_docs": [
            "Form I-129",
            "Labor Condition Application (LCA)",
            "Degree certificates and transcripts",
            "Credential evaluation (if foreign degree)",
            "Passport copy",
            "Employer support letter",
            "Job description"
        ],
        "optional_docs": [
            "Expert opinion letter",
            "Organizational chart",
            "Client contracts (if consulting)",
            "Previous H-1B approvals"
        ],
        "filing_fee": 460,
        "premium_fee": 2805,
        "fraud_fee": 500,
        "acwia_fee": 750,  # or 1500 for 25+ employees
        "processing_time": "3-6 months (regular), 15 business days (premium)"
    },
    "O-1A": {
        "name": "Extraordinary Ability (Sciences/Business)",
        "category": "Non-Immigrant",
        "criteria_needed": "3 of 8",
        "criteria": [
            "Receipt of nationally/internationally recognized awards",
            "Membership in associations requiring outstanding achievements",
            "Published material in professional publications",
            "Participation as a judge of others' work",
            "Original contributions of major significance",
            "Authorship of scholarly articles",
            "Employment in critical capacity for distinguished organizations",
            "High salary or remuneration"
        ],
        "required_docs": [
            "Form I-129",
            "Evidence of extraordinary ability (3+ criteria)",
            "Advisory opinion or peer group letter",
            "Contract with US employer or agent",
            "Itinerary of events/employment",
            "Passport copy"
        ],
        "optional_docs": [
            "Letters from experts in the field",
            "Prior O-1 approvals",
            "Citation reports",
            "Media coverage"
        ],
        "filing_fee": 460,
        "premium_fee": 2805,
        "processing_time": "3-6 months (regular), 15 business days (premium)"
    },
    "L-1A": {
        "name": "Intracompany Transfer (Manager/Executive)",
        "category": "Non-Immigrant",
        "criteria_needed": "All requirements",
        "criteria": [
            "Employed abroad for 1 continuous year in last 3 years",
            "Employed in managerial or executive capacity abroad",
            "Coming to US in managerial or executive capacity",
            "Qualifying relationship between US and foreign entity"
        ],
        "required_docs": [
            "Form I-129",
            "Evidence of qualifying relationship",
            "Evidence of 1 year employment abroad",
            "Job descriptions (abroad and US)",
            "Organizational charts",
            "Passport copy",
            "Company financial documents"
        ],
        "optional_docs": [
            "Tax returns",
            "Annual reports",
            "Office lease",
            "Employee lists"
        ],
        "filing_fee": 460,
        "premium_fee": 2805,
        "fraud_fee": 500,
        "processing_time": "3-6 months (regular), 15 business days (premium)"
    },
    "TN": {
        "name": "USMCA Professional",
        "category": "Non-Immigrant",
        "criteria_needed": "All requirements",
        "criteria": [
            "Citizen of Canada or Mexico",
            "Profession on TN list",
            "Prearranged full-time or part-time employment",
            "Meet educational/licensing requirements for profession"
        ],
        "required_docs": [
            "Form I-129 (or apply at POE for Canadians)",
            "Proof of citizenship",
            "Degree/credentials for profession",
            "Employer support letter with job details",
            "Passport"
        ],
        "optional_docs": [
            "Credential evaluation",
            "Professional licenses",
            "Prior TN approvals"
        ],
        "filing_fee": 460,
        "processing_time": "At POE (Canada), 3-6 months (Mexico/mail)"
    }
}


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class SearchRequest(BaseModel):
    query: str
    n_results: Optional[int] = 5
    visa_type: Optional[str] = None


class SearchResult(BaseModel):
    content: str
    source: str
    relevance: float
    page: Optional[int] = None


class SearchResponse(BaseModel):
    results: List[SearchResult]
    query: str
    total_results: int


class RequirementsResponse(BaseModel):
    visa_type: str
    name: str
    category: str
    criteria_needed: str
    criteria: List[str]
    required_docs: List[str]
    optional_docs: List[str]
    fees: Dict[str, int]
    processing_time: str
    aila_context: Optional[str] = None


class EligibilityRequest(BaseModel):
    visa_type: str
    education_level: str  # "bachelors", "masters", "phd"
    years_experience: int
    has_awards: bool = False
    has_publications: bool = False
    has_citations: bool = False
    has_patents: bool = False
    has_media_coverage: bool = False
    has_memberships: bool = False
    has_judging_experience: bool = False
    has_original_contributions: bool = False
    has_high_salary: bool = False
    field: Optional[str] = None


class EligibilityResponse(BaseModel):
    visa_type: str
    score: int  # 0-100
    criteria_met: int
    criteria_needed: int
    recommendation: str
    strengths: List[str]
    weaknesses: List[str]
    suggested_evidence: List[str]


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/status")
async def get_status(request: Request, db: Session = Depends(get_db)):
    """Get AILA Knowledge Base status"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "available": AILA_AVAILABLE,
        "document_count": aila_search.document_count if aila_search else 0,
        "visa_types_supported": list(VISA_REQUIREMENTS.keys())
    }


@router.post("/search", response_model=SearchResponse)
async def search_aila(request: Request, search_request: SearchRequest, db: Session = Depends(get_db)):
    """Search the AILA Knowledge Base"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not AILA_AVAILABLE:
        raise HTTPException(status_code=503, detail="AILA Knowledge Base not available")

    query = search_request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    # Add visa type context if provided
    if search_request.visa_type:
        query = f"{search_request.visa_type} {query}"

    results = aila_search.search(query, n_results=search_request.n_results)

    return SearchResponse(
        results=[
            SearchResult(
                content=r.get("text", ""),
                source=r.get("source", "Unknown"),
                relevance=r.get("relevance", 0),
                page=r.get("chunk_index")
            )
            for r in results
        ],
        query=search_request.query,
        total_results=len(results)
    )


@router.get("/search")
async def search_aila_get(
    request: Request,
    query: str = Query(..., description="Search query"),
    n_results: int = Query(5, description="Number of results"),
    visa_type: Optional[str] = Query(None, description="Filter by visa type"),
    db: Session = Depends(get_db),
):
    """Search the AILA Knowledge Base (GET method)"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not AILA_AVAILABLE:
        raise HTTPException(status_code=503, detail="AILA Knowledge Base not available")

    search_query = query.strip()
    if not search_query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    if visa_type:
        search_query = f"{visa_type} {search_query}"

    results = aila_search.search(search_query, n_results=n_results)

    return {
        "results": [
            {
                "content": r.get("text", ""),
                "source": r.get("source", "Unknown"),
                "relevance": r.get("relevance", 0),
                "page": r.get("chunk_index")
            }
            for r in results
        ],
        "query": query,
        "total_results": len(results)
    }


@router.get("/requirements/{visa_type}", response_model=RequirementsResponse)
async def get_requirements(visa_type: str, request: Request, db: Session = Depends(get_db)):
    """Get requirements for a specific visa type"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    visa_upper = visa_type.upper().replace("_", " ").replace("-", " ")

    # Find matching visa type
    matched = None
    for key in VISA_REQUIREMENTS:
        if key.replace("-", " ").replace("_", " ").upper() == visa_upper:
            matched = key
            break
        if visa_upper in key.upper():
            matched = key
            break

    if not matched:
        raise HTTPException(
            status_code=404,
            detail=f"Visa type '{visa_type}' not found. Available: {list(VISA_REQUIREMENTS.keys())}"
        )

    req = VISA_REQUIREMENTS[matched]

    # Get additional context from AILA if available
    aila_context = None
    if AILA_AVAILABLE:
        context = aila_search.get_context_for_llm(
            f"{matched} requirements eligibility documents",
            n_results=3,
            max_tokens=500
        )
        if context:
            aila_context = context

    # Build fees dict
    fees = {"filing": req.get("filing_fee", 0)}
    if "premium_fee" in req:
        fees["premium"] = req["premium_fee"]
    if "fraud_fee" in req:
        fees["fraud"] = req["fraud_fee"]
    if "acwia_fee" in req:
        fees["acwia"] = req["acwia_fee"]

    return RequirementsResponse(
        visa_type=matched,
        name=req["name"],
        category=req["category"],
        criteria_needed=req["criteria_needed"],
        criteria=req["criteria"],
        required_docs=req["required_docs"],
        optional_docs=req["optional_docs"],
        fees=fees,
        processing_time=req["processing_time"],
        aila_context=aila_context
    )


@router.get("/requirements")
async def list_all_requirements(request: Request, db: Session = Depends(get_db)):
    """List all available visa types and their basic info"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "visa_types": [
            {
                "code": key,
                "name": val["name"],
                "category": val["category"],
                "filing_fee": val.get("filing_fee", 0),
                "premium_available": "premium_fee" in val
            }
            for key, val in VISA_REQUIREMENTS.items()
        ]
    }


@router.post("/eligibility", response_model=EligibilityResponse)
async def check_eligibility(request: Request, eligibility_request: EligibilityRequest, db: Session = Depends(get_db)):
    """Check eligibility for a visa type based on profile"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    visa_type = eligibility_request.visa_type.upper().replace("_", " ")

    # Map criteria to request fields
    criteria_checks = {
        "awards": eligibility_request.has_awards,
        "publications": eligibility_request.has_publications,
        "citations": eligibility_request.has_citations,
        "patents": eligibility_request.has_patents,
        "media": eligibility_request.has_media_coverage,
        "memberships": eligibility_request.has_memberships,
        "judging": eligibility_request.has_judging_experience,
        "contributions": eligibility_request.has_original_contributions,
        "salary": eligibility_request.has_high_salary
    }

    criteria_met = sum(1 for v in criteria_checks.values() if v)
    strengths = [k for k, v in criteria_checks.items() if v]
    weaknesses = [k for k, v in criteria_checks.items() if not v]

    # Different scoring based on visa type
    if "EB-1A" in visa_type or "O-1" in visa_type:
        criteria_needed = 3
        base_score = (criteria_met / criteria_needed) * 100
        score = min(100, int(base_score))

        if criteria_met >= 3:
            recommendation = "Strong candidate. You meet the minimum criteria threshold."
        elif criteria_met == 2:
            recommendation = "Borderline. Consider strengthening one more area before filing."
        else:
            recommendation = "More evidence needed. Focus on building at least 3 criteria."

    elif "EB-2 NIW" in visa_type:
        # NIW requires advanced degree + 3 prongs of Dhanasar
        criteria_needed = 3  # Simplified as criteria count
        has_advanced_degree = eligibility_request.education_level in ["masters", "phd"]

        if has_advanced_degree:
            base_score = 40 + (criteria_met / 9) * 60
        else:
            base_score = 20 + (criteria_met / 9) * 60

        score = min(100, int(base_score))

        if score >= 70:
            recommendation = "Good candidate. Strong profile for NIW petition."
        elif score >= 50:
            recommendation = "Moderate. Consider additional evidence for Prong 2 and 3."
        else:
            recommendation = "Weak profile. May need to build more evidence or consider other options."

    elif "H-1B" in visa_type:
        # H-1B mainly requires degree + specialty occupation
        has_degree = eligibility_request.education_level in ["bachelors", "masters", "phd"]
        score = 80 if has_degree else 30
        criteria_needed = 1

        if has_degree:
            recommendation = "Eligible for H-1B if job is specialty occupation."
        else:
            recommendation = "Need bachelor's degree or equivalent work experience (3 years = 1 year college)."

    else:
        # Generic scoring
        criteria_needed = 3
        score = int((criteria_met / 9) * 100)
        recommendation = f"Score based on {criteria_met} criteria met."

    # Suggested evidence based on weaknesses
    evidence_suggestions = {
        "awards": "Apply for industry awards, competitions, or recognitions",
        "publications": "Publish articles in trade publications or peer-reviewed journals",
        "citations": "Track citations to your work; consider Google Scholar profile",
        "patents": "File provisional patents for innovations",
        "media": "Seek press coverage for achievements or expert commentary opportunities",
        "memberships": "Join professional associations that require achievements for membership",
        "judging": "Volunteer to review papers, judge competitions, or evaluate grants",
        "contributions": "Document innovations with impact metrics, testimonials",
        "salary": "Gather evidence of above-average compensation for your field"
    }

    suggested = [evidence_suggestions[w] for w in weaknesses[:4]]

    return EligibilityResponse(
        visa_type=visa_type,
        score=score,
        criteria_met=criteria_met,
        criteria_needed=criteria_needed,
        recommendation=recommendation,
        strengths=strengths,
        weaknesses=weaknesses[:5],
        suggested_evidence=suggested
    )


@router.get("/context/{visa_type}")
async def get_aila_context(
    visa_type: str,
    request: Request,
    topic: str = Query("requirements", description="Specific topic to search"),
    db: Session = Depends(get_db),
):
    """Get AILA context for a specific visa type and topic"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not AILA_AVAILABLE:
        raise HTTPException(status_code=503, detail="AILA Knowledge Base not available")

    query = f"{visa_type} {topic}"
    context = aila_search.get_context_for_llm(query, n_results=5, max_tokens=2000)

    if not context:
        return {"context": None, "message": "No relevant context found"}

    sources = aila_search.get_sources_list(query, n_results=5)

    return {
        "visa_type": visa_type,
        "topic": topic,
        "context": context,
        "sources": sources
    }


@router.get("/fees/{visa_type}")
async def get_fees(visa_type: str, request: Request, db: Session = Depends(get_db)):
    """Get current filing fees for a visa type"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    visa_upper = visa_type.upper().replace("_", " ")

    matched = None
    for key in VISA_REQUIREMENTS:
        if key.replace("-", " ").upper() == visa_upper or visa_upper in key.upper():
            matched = key
            break

    if not matched:
        raise HTTPException(status_code=404, detail=f"Visa type '{visa_type}' not found")

    req = VISA_REQUIREMENTS[matched]

    fees = {
        "visa_type": matched,
        "filing_fee": req.get("filing_fee", 0),
        "premium_available": "premium_fee" in req
    }

    if "premium_fee" in req:
        fees["premium_fee"] = req["premium_fee"]
    if "fraud_fee" in req:
        fees["fraud_fee"] = req["fraud_fee"]
    if "acwia_fee" in req:
        fees["acwia_fee"] = req["acwia_fee"]
        fees["acwia_note"] = "$750 for <25 employees, $1500 for 25+ employees"

    # Calculate total
    total = fees["filing_fee"]
    for key in ["fraud_fee", "acwia_fee"]:
        if key in fees and isinstance(fees[key], int):
            total += fees[key]

    fees["total_without_premium"] = total
    if "premium_fee" in fees:
        fees["total_with_premium"] = total + fees["premium_fee"]

    return fees
