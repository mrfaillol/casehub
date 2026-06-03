"""
CaseHub - Case Wizard AILA Integration
Adiciona checklist de documentos e requisitos baseados na AILA Knowledge Base

INSTALACAO:
1. Deploy to services/case_wizard_aila.py
2. Importar nas rotas do wizard quando necessario
"""

import logging
from typing import Dict, List, Optional
import sys
import os

logger = logging.getLogger(__name__)

# Try to import AILA search
AILA_AVAILABLE = False
aila_search = None

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from aila_search import AILASearch

    if AILASearch.is_available():
        aila_search = AILASearch()
        AILA_AVAILABLE = True
        logger.info(f"[CaseWizard-AILA] Integration enabled: {aila_search.document_count} documents")
except Exception as e:
    logger.warning(f"[CaseWizard-AILA] AILA not available: {e}")


# =============================================================================
# DOCUMENT CHECKLISTS BY VISA TYPE
# =============================================================================

DOCUMENT_CHECKLISTS = {
    "EB-1A": {
        "required": [
            {"doc": "Form I-140", "category": "Forms", "notes": "Petition for Alien Worker"},
            {"doc": "Passport (bio page)", "category": "Identity", "notes": "Valid for 6+ months"},
            {"doc": "Academic credentials", "category": "Education", "notes": "Degrees + transcripts"},
            {"doc": "Credential evaluation", "category": "Education", "notes": "If foreign degree"},
            {"doc": "CV/Resume", "category": "Background", "notes": "Detailed with dates"},
            {"doc": "Evidence of 3+ criteria", "category": "Evidence", "notes": "See criteria below"},
        ],
        "evidence_categories": [
            {
                "criterion": "Awards",
                "description": "National/international recognition for excellence",
                "docs": ["Award certificates", "Award criteria", "News coverage of award", "List of past recipients"]
            },
            {
                "criterion": "Memberships",
                "description": "Associations requiring outstanding achievements",
                "docs": ["Membership certificate", "Membership requirements", "Selection criteria"]
            },
            {
                "criterion": "Published material about you",
                "description": "Professional publications about your work",
                "docs": ["Articles about you", "Interviews", "Profile pieces"]
            },
            {
                "criterion": "Judging",
                "description": "Judging others' work in your field",
                "docs": ["Reviewer invitations", "Editorial board letters", "Grant panel appointments"]
            },
            {
                "criterion": "Original contributions",
                "description": "Contributions of major significance",
                "docs": ["Patents", "Expert letters", "Implementation evidence", "Citation reports"]
            },
            {
                "criterion": "Scholarly articles",
                "description": "Authorship in professional journals",
                "docs": ["Published articles", "Citation counts", "Journal impact factors"]
            },
            {
                "criterion": "Exhibitions",
                "description": "Display at artistic exhibitions",
                "docs": ["Exhibition catalogs", "Gallery statements", "Reviews"]
            },
            {
                "criterion": "Leading role",
                "description": "Leading/critical role in distinguished organizations",
                "docs": ["Org chart", "Title documentation", "Scope of duties letter"]
            },
            {
                "criterion": "High salary",
                "description": "High remuneration relative to field",
                "docs": ["Pay stubs", "Offer letter", "Salary survey comparison"]
            },
            {
                "criterion": "Commercial success",
                "description": "Commercial success in performing arts",
                "docs": ["Box office records", "Sales figures", "Charts/rankings"]
            }
        ],
        "letters_recommended": 6,
        "letters_notes": "From independent experts who can evaluate your achievements"
    },
    "EB-2 NIW": {
        "required": [
            {"doc": "Form I-140", "category": "Forms", "notes": "Petition for Alien Worker"},
            {"doc": "Passport (bio page)", "category": "Identity", "notes": "Valid for 6+ months"},
            {"doc": "Advanced degree evidence", "category": "Education", "notes": "Master's/PhD or Bachelor's + 5 years"},
            {"doc": "Credential evaluation", "category": "Education", "notes": "If foreign degree"},
            {"doc": "CV/Resume", "category": "Background", "notes": "Detailed with dates"},
            {"doc": "Personal Statement", "category": "NIW Core", "notes": "Proposed endeavor + 3 prongs"},
        ],
        "evidence_categories": [
            {
                "criterion": "Prong 1: Merit & National Importance",
                "description": "Endeavor has substantial merit and national importance",
                "docs": [
                    "Personal statement",
                    "Government statistics (BLS, NSF, etc.)",
                    "Executive orders/policies",
                    "Industry reports",
                    "Expert letters on field importance"
                ]
            },
            {
                "criterion": "Prong 2: Well Positioned",
                "description": "Well positioned to advance the endeavor",
                "docs": [
                    "Track record evidence",
                    "Past project outcomes",
                    "Publications",
                    "Awards/recognition",
                    "Expert letters on qualifications"
                ]
            },
            {
                "criterion": "Prong 3: Beneficial to Waive",
                "description": "On balance, beneficial to waive requirements",
                "docs": [
                    "Letters on urgency of field",
                    "Evidence of unique skills",
                    "Self-employment or flexibility needs",
                    "Evidence that labor cert would delay contributions"
                ]
            }
        ],
        "letters_recommended": 6,
        "letters_notes": "Mix of supervisors, colleagues, and independent experts"
    },
    "H-1B": {
        "required": [
            {"doc": "Form I-129", "category": "Forms", "notes": "Petition for Nonimmigrant Worker"},
            {"doc": "Labor Condition Application (LCA)", "category": "Forms", "notes": "Certified by DOL"},
            {"doc": "Passport (bio page)", "category": "Identity", "notes": "Valid for 6+ months"},
            {"doc": "Bachelor's degree or higher", "category": "Education", "notes": "In relevant field"},
            {"doc": "Credential evaluation", "category": "Education", "notes": "If foreign degree"},
            {"doc": "Employer support letter", "category": "Employment", "notes": "With job duties"},
            {"doc": "Resume/CV", "category": "Background", "notes": "Shows relevant experience"},
        ],
        "optional": [
            {"doc": "Expert opinion letter", "category": "Evidence", "notes": "If degree not in exact field"},
            {"doc": "Specialty occupation evidence", "category": "Evidence", "notes": "Industry requirements"},
            {"doc": "Previous H-1B approvals", "category": "History", "notes": "If extension/transfer"},
            {"doc": "Client contracts", "category": "Employment", "notes": "If third-party placement"},
            {"doc": "Organizational chart", "category": "Employment", "notes": "Showing position"},
        ],
        "letters_recommended": 0,
        "letters_notes": "Usually not needed unless specialty occupation is contested"
    },
    "O-1A": {
        "required": [
            {"doc": "Form I-129", "category": "Forms", "notes": "Petition for Nonimmigrant Worker"},
            {"doc": "Passport (bio page)", "category": "Identity", "notes": "Valid for 6+ months"},
            {"doc": "Advisory opinion", "category": "Evidence", "notes": "From peer group or union"},
            {"doc": "Contract or summary of terms", "category": "Employment", "notes": "With US employer/agent"},
            {"doc": "Itinerary", "category": "Employment", "notes": "If multiple employers"},
            {"doc": "CV/Resume", "category": "Background", "notes": "Detailed with dates"},
            {"doc": "Evidence of 3+ criteria", "category": "Evidence", "notes": "Same as EB-1A"},
        ],
        "evidence_categories": [
            {
                "criterion": "Same criteria as EB-1A",
                "description": "Need 3 of 8 criteria",
                "docs": ["See EB-1A evidence categories"]
            }
        ],
        "letters_recommended": 5,
        "letters_notes": "From experts attesting to extraordinary ability"
    },
    "L-1A": {
        "required": [
            {"doc": "Form I-129", "category": "Forms", "notes": "Petition for Nonimmigrant Worker"},
            {"doc": "Form I-129S", "category": "Forms", "notes": "If blanket L"},
            {"doc": "Passport (bio page)", "category": "Identity", "notes": "Valid for 6+ months"},
            {"doc": "Evidence of 1 year abroad", "category": "Employment", "notes": "In managerial/executive role"},
            {"doc": "Job descriptions", "category": "Employment", "notes": "Abroad and US positions"},
            {"doc": "Organizational charts", "category": "Employment", "notes": "Both entities"},
            {"doc": "Qualifying relationship evidence", "category": "Corporate", "notes": "Parent/sub/affiliate/branch"},
        ],
        "optional": [
            {"doc": "Company financial documents", "category": "Corporate", "notes": "Annual reports, tax returns"},
            {"doc": "Office lease", "category": "Corporate", "notes": "For US office"},
            {"doc": "Employee lists", "category": "Corporate", "notes": "Both entities"},
            {"doc": "Business plan", "category": "Corporate", "notes": "If new office"},
        ],
        "letters_recommended": 0,
        "letters_notes": "Not typically needed"
    },
    "TN": {
        "required": [
            {"doc": "Form I-129", "category": "Forms", "notes": "Or apply at POE for Canadians"},
            {"doc": "Passport", "category": "Identity", "notes": "Proof of Canadian/Mexican citizenship"},
            {"doc": "Degree/credentials", "category": "Education", "notes": "For TN profession"},
            {"doc": "Employer support letter", "category": "Employment", "notes": "Detailed job offer"},
        ],
        "optional": [
            {"doc": "Credential evaluation", "category": "Education", "notes": "If foreign degree"},
            {"doc": "Professional licenses", "category": "Credentials", "notes": "If profession requires"},
            {"doc": "Prior TN approvals", "category": "History", "notes": "If renewal"},
        ],
        "letters_recommended": 0,
        "letters_notes": "Not needed for TN"
    }
}


# =============================================================================
# FUNCTIONS
# =============================================================================

def get_checklist(visa_type: str) -> Optional[Dict]:
    """
    Get document checklist for a visa type

    Args:
        visa_type: Type of visa (e.g., "EB-1A", "H-1B")

    Returns:
        Checklist dict or None if not found
    """
    # Normalize visa type
    visa_normalized = visa_type.upper().replace("_", " ").replace("-", " ")

    for key, value in DOCUMENT_CHECKLISTS.items():
        if key.replace("-", " ").upper() == visa_normalized:
            return {"visa_type": key, **value}
        if visa_normalized in key.upper():
            return {"visa_type": key, **value}

    return None


def get_aila_tips(visa_type: str, category: str = "requirements") -> List[Dict]:
    """
    Get AILA tips for a visa type

    Args:
        visa_type: Type of visa
        category: Topic category (requirements, evidence, rfe, processing)

    Returns:
        List of tips from AILA knowledge base
    """
    if not AILA_AVAILABLE or not aila_search:
        return []

    try:
        results = aila_search.search(
            f"{visa_type} {category} tips practice pointers",
            n_results=3,
            min_relevance=0.5
        )

        return [
            {
                "tip": r.get("text", "")[:400],
                "source": r.get("source", "AILA")
            }
            for r in results
        ]
    except Exception as e:
        logger.error(f"[CaseWizard-AILA] Error getting tips: {e}")
        return []


def get_rfe_prevention_tips(visa_type: str) -> List[str]:
    """
    Get RFE prevention tips for a visa type

    Args:
        visa_type: Type of visa

    Returns:
        List of tips to prevent RFEs
    """
    common_tips = {
        "EB-1A": [
            "Include at least 4-5 criteria even though only 3 are required",
            "Get letters from truly independent experts, not just colleagues",
            "Include detailed citation analysis with context",
            "Document the significance of awards with criteria and past recipients",
            "Show sustained acclaim over time, not just one achievement"
        ],
        "EB-2 NIW": [
            "Clearly articulate the proposed endeavor in the personal statement",
            "Include government statistics supporting national importance",
            "Get letters specifically addressing the 3 prongs of Dhanasar",
            "Show track record of success, not just potential",
            "Explain why labor certification would be impractical"
        ],
        "H-1B": [
            "Ensure job duties clearly require specialized knowledge",
            "Include detailed client contracts if third-party placement",
            "Provide expert opinion if degree is in related but not exact field",
            "Document the complexity of the specific position",
            "Include industry evidence that role requires degree"
        ],
        "O-1A": [
            "Get advisory opinion early in the process",
            "Include evidence of sustained recognition, not just one-time",
            "Document the significance of achievements in context",
            "Show extraordinary compared to peers in field",
            "Include press coverage if available"
        ],
        "L-1A": [
            "Clearly document managerial/executive duties",
            "Include detailed org charts showing supervisory scope",
            "Document the qualifying relationship with corporate docs",
            "Show the beneficiary manages a function or subdivision",
            "Include evidence of 1 year abroad in qualifying role"
        ],
        "TN": [
            "Ensure profession is on the TN list",
            "Match degree to profession requirements",
            "Detailed support letter with duties aligned to profession",
            "Include credential evaluation if needed",
            "Document prearranged employment"
        ]
    }

    return common_tips.get(visa_type, [
        "Ensure all required documents are included",
        "Double-check for consistency across all documents",
        "Include detailed evidence for each requirement",
        "Get independent expert letters when appropriate"
    ])


def check_document_completeness(
    visa_type: str,
    submitted_docs: List[str]
) -> Dict:
    """
    Check if submitted documents meet requirements

    Args:
        visa_type: Type of visa
        submitted_docs: List of document names/types submitted

    Returns:
        Dict with status, missing docs, and suggestions
    """
    checklist = get_checklist(visa_type)
    if not checklist:
        return {"status": "unknown", "message": "Visa type not recognized"}

    required = checklist.get("required", [])
    submitted_lower = [d.lower() for d in submitted_docs]

    missing = []
    for req in required:
        doc_name = req["doc"].lower()
        # Check if any submitted doc matches
        found = any(doc_name in sub or sub in doc_name for sub in submitted_lower)
        if not found:
            missing.append(req)

    if not missing:
        return {
            "status": "complete",
            "message": "All required documents submitted",
            "missing": [],
            "suggestions": get_rfe_prevention_tips(visa_type)[:3]
        }
    else:
        return {
            "status": "incomplete",
            "message": f"Missing {len(missing)} required document(s)",
            "missing": missing,
            "suggestions": [f"Upload {m['doc']}: {m['notes']}" for m in missing[:5]]
        }


def get_wizard_context(visa_type: str) -> Dict:
    """
    Get all context needed for the case wizard

    Args:
        visa_type: Type of visa being filed

    Returns:
        Dict with checklist, tips, and AILA context
    """
    return {
        "checklist": get_checklist(visa_type),
        "aila_tips": get_aila_tips(visa_type),
        "rfe_prevention": get_rfe_prevention_tips(visa_type),
        "aila_available": AILA_AVAILABLE
    }


# =============================================================================
# STANDALONE TEST
# =============================================================================

if __name__ == "__main__":
    import json

    print("=== Case Wizard AILA Integration Test ===\n")

    for visa in ["EB-1A", "EB-2 NIW", "H-1B"]:
        print(f"\n--- {visa} ---")
        checklist = get_checklist(visa)
        if checklist:
            print(f"Required docs: {len(checklist.get('required', []))}")
            print(f"Letters recommended: {checklist.get('letters_recommended', 0)}")

        tips = get_rfe_prevention_tips(visa)
        print(f"RFE prevention tips: {len(tips)}")

        if AILA_AVAILABLE:
            aila = get_aila_tips(visa)
            print(f"AILA tips found: {len(aila)}")
