"""
LOR Generator - AILA Integration
Melhora a secao de National Importance com dados da AILA Knowledge Base

INSTALACAO:
1. Copiar para /opt/casehub/ilc-tools/tools/lor_aila_integration.py
2. Modificar lor_generator.py para importar e usar essas funcoes
"""

from typing import Dict, List, Optional, Tuple
import sys
import os

# Try to import AILA client
AILA_AVAILABLE = False
aila_client = None

try:
    from aila_client import AILAClient, get_aila_client
    aila_client = get_aila_client()
    AILA_AVAILABLE = aila_client.is_available
    if AILA_AVAILABLE:
        print("[LOR-AILA] AILA integration enabled")
except Exception as e:
    print(f"[LOR-AILA] AILA integration not available: {e}")


# =============================================================================
# NATIONAL IMPORTANCE DATA BY FIELD
# =============================================================================

FIELD_STATISTICS = {
    "technology": {
        "shortage": "According to the Bureau of Labor Statistics, the U.S. will face a shortage of 1.2 million software developers by 2026.",
        "economic_impact": "The tech industry contributes over $2 trillion annually to the U.S. economy.",
        "priority": "The America COMPETES Act emphasizes the critical need for STEM talent to maintain global competitiveness.",
        "jobs": "Each tech worker creates an average of 4.3 additional jobs in the local economy."
    },
    "healthcare": {
        "shortage": "The Association of American Medical Colleges projects a shortage of up to 124,000 physicians by 2034.",
        "economic_impact": "Healthcare represents 18% of U.S. GDP, approximately $4.3 trillion annually.",
        "priority": "The National Institutes of Health has identified healthcare workforce development as a critical priority.",
        "jobs": "Healthcare is the fastest-growing employment sector in the United States."
    },
    "engineering": {
        "shortage": "The American Society of Civil Engineers estimates infrastructure needs of $4.5 trillion by 2025.",
        "economic_impact": "Engineering services contribute $250 billion annually to the U.S. economy.",
        "priority": "The Infrastructure Investment and Jobs Act allocates $1.2 trillion for critical infrastructure.",
        "jobs": "Each infrastructure dollar invested creates $1.57 in economic activity."
    },
    "artificial_intelligence": {
        "shortage": "The AI talent gap in the U.S. exceeds 100,000 positions according to Indeed hiring data.",
        "economic_impact": "AI is projected to add $15.7 trillion to the global economy by 2030, with the U.S. capturing 26%.",
        "priority": "Executive Order 14110 on AI emphasizes developing a strong AI workforce as a national priority.",
        "jobs": "AI specialists are among the highest-paid professionals in the technology sector."
    },
    "cybersecurity": {
        "shortage": "There are over 700,000 unfilled cybersecurity positions in the United States.",
        "economic_impact": "Cybercrime costs the U.S. economy over $100 billion annually.",
        "priority": "The National Cybersecurity Strategy 2023 identifies workforce development as critical.",
        "jobs": "Cybersecurity professionals are in the top 5 most in-demand roles nationwide."
    },
    "renewable_energy": {
        "shortage": "The clean energy sector will need 1.5 million new workers by 2030.",
        "economic_impact": "Clean energy investments in the U.S. exceeded $300 billion in 2023.",
        "priority": "The Inflation Reduction Act dedicates $369 billion to clean energy initiatives.",
        "jobs": "Solar and wind technicians are the two fastest-growing occupations in America."
    },
    "biotechnology": {
        "shortage": "The biotech industry faces a shortage of 100,000 skilled workers.",
        "economic_impact": "Biotechnology contributes $2 trillion annually to the U.S. economy.",
        "priority": "The National Biotechnology and Biomanufacturing Initiative prioritizes domestic production.",
        "jobs": "Biotech jobs pay 50% more than the average private sector wage."
    },
    "finance": {
        "shortage": "Financial services face increasing demand for quantitative and technology skills.",
        "economic_impact": "Financial services represent 7.4% of U.S. GDP.",
        "priority": "Treasury and SEC initiatives emphasize modernizing financial infrastructure.",
        "jobs": "New York City alone has over 350,000 financial services jobs."
    },
    "academia": {
        "shortage": "Universities face a shortage of PhD-qualified faculty across STEM fields.",
        "economic_impact": "Higher education contributes $700 billion annually to the U.S. economy.",
        "priority": "NSF and NIH funding priorities emphasize research workforce development.",
        "jobs": "University research generates significant employment and innovation spillovers."
    }
}


# =============================================================================
# PRONG 3 TEMPLATES (Matter of Dhanasar)
# =============================================================================

PRONG_3_TEMPLATES = {
    "urgency": """The United States faces an urgent need in {field}. {shortage_stat} Without
immediate action to attract and retain top talent like {beneficiary}, the nation risks falling
behind international competitors, particularly China and the European Union, who are
aggressively recruiting in this space.""",

    "flexibility": """Requiring {beneficiary} to secure a specific employer would unduly
restrict {his_her} ability to maximize contributions to the national interest. Given the
cross-disciplinary nature of {his_her} work in {field}, {beneficiary} must have the
flexibility to collaborate across institutions, consult with multiple organizations, and
pursue opportunities that may not exist within a single employer's scope.""",

    "self_employment": """{beneficiary} intends to continue {his_her} work through
entrepreneurial activities that would be impossible under traditional employment
arrangements. {His_Her} proposed venture in {field} addresses critical national needs
that established employers have been unable or unwilling to address.""",

    "general": """On balance, the benefit to the United States of waiving the job offer
and labor certification requirements outweighs any potential detriment to U.S. workers.
{beneficiary}'s specialized expertise in {field} is rare; {economic_impact} The labor
market would not be adversely affected, as there is no domestic workforce capable of
providing the unique contributions that {beneficiary} offers."""
}


# =============================================================================
# INTEGRATION FUNCTIONS
# =============================================================================

def get_field_category(field: str) -> str:
    """Map specific field to category for statistics lookup"""
    field_lower = field.lower()

    mappings = {
        "technology": ["software", "computer", "programming", "tech", "developer", "web", "mobile", "app"],
        "healthcare": ["medical", "doctor", "nurse", "health", "clinical", "patient", "hospital", "pharmaceutical"],
        "engineering": ["engineer", "civil", "mechanical", "electrical", "structural", "infrastructure"],
        "artificial_intelligence": ["ai", "machine learning", "ml", "deep learning", "neural", "nlp", "computer vision"],
        "cybersecurity": ["security", "cyber", "infosec", "hacking", "penetration", "threat"],
        "renewable_energy": ["solar", "wind", "renewable", "clean energy", "sustainability", "green"],
        "biotechnology": ["biotech", "genetic", "molecular", "pharmaceutical", "drug", "biology"],
        "finance": ["financial", "banking", "investment", "trading", "fintech", "quantitative"],
        "academia": ["professor", "research", "university", "academic", "scholar", "faculty"]
    }

    for category, keywords in mappings.items():
        if any(kw in field_lower for kw in keywords):
            return category

    # Default to technology if no match
    return "technology"


def get_national_importance_content(
    field: str,
    beneficiary_name: str,
    his_her: str = "his/her"
) -> Dict[str, str]:
    """
    Get national importance content for LOR

    Args:
        field: Beneficiary's field of work
        beneficiary_name: Name for personalization
        his_her: Pronoun to use

    Returns:
        Dict with statistics, urgency, flexibility sections
    """
    category = get_field_category(field)
    stats = FIELD_STATISTICS.get(category, FIELD_STATISTICS["technology"])

    # Try to get AILA context if available
    aila_context = None
    if AILA_AVAILABLE and aila_client:
        try:
            aila_data = aila_client.get_national_importance_context(field, "EB-2 NIW")
            if aila_data and aila_data.get("statistics"):
                aila_context = aila_data
        except Exception:
            pass

    result = {
        "shortage_statement": stats["shortage"],
        "economic_impact": stats["economic_impact"],
        "priority_statement": stats["priority"],
        "jobs_impact": stats["jobs"],
        "prong_3_urgency": PRONG_3_TEMPLATES["urgency"].format(
            field=field,
            shortage_stat=stats["shortage"],
            beneficiary=beneficiary_name,
            his_her=his_her
        ),
        "prong_3_flexibility": PRONG_3_TEMPLATES["flexibility"].format(
            field=field,
            beneficiary=beneficiary_name,
            his_her=his_her
        ),
        "prong_3_general": PRONG_3_TEMPLATES["general"].format(
            field=field,
            beneficiary=beneficiary_name,
            economic_impact=stats["economic_impact"],
            his_her=his_her.capitalize()
        )
    }

    # Add AILA context if available
    if aila_context:
        result["aila_statistics"] = aila_context.get("statistics", [])
        result["aila_policies"] = aila_context.get("policies", [])
        result["aila_sources"] = aila_context.get("sources", [])

    return result


def enhance_lor_with_aila(
    lor_content: str,
    field: str,
    beneficiary_name: str,
    visa_type: str = "EB-2 NIW"
) -> Tuple[str, List[str]]:
    """
    Enhance LOR content with AILA data

    Args:
        lor_content: Original LOR text
        field: Beneficiary's field
        beneficiary_name: Beneficiary's name
        visa_type: Type of visa petition

    Returns:
        Tuple of (enhanced content, list of sources used)
    """
    if not AILA_AVAILABLE:
        return lor_content, []

    sources = []

    # Search for field-specific content
    try:
        results = aila_client.search_sync(
            f"{field} {visa_type} national importance evidence",
            n_results=3
        )

        if results:
            # Add a footnote section
            footnotes = []
            for i, r in enumerate(results, 1):
                source = r.get("source", "AILA Document")
                sources.append(source)
                content_snippet = r.get("content", "")[:200]
                footnotes.append(f"[{i}] {source}")

            if footnotes:
                lor_content += "\n\n_____\nReferences:\n" + "\n".join(footnotes)

    except Exception as e:
        print(f"[LOR-AILA] Enhancement error: {e}")

    return lor_content, sources


def get_criteria_language(criterion: str, visa_type: str = "EB-1A") -> Optional[str]:
    """
    Get AILA-approved language for specific criteria

    Args:
        criterion: The criterion to describe (e.g., "awards", "judging")
        visa_type: Type of visa

    Returns:
        Template language or None
    """
    if not AILA_AVAILABLE:
        return None

    try:
        results = aila_client.search_sync(
            f"{visa_type} {criterion} evidence requirements approved",
            n_results=2
        )
        if results:
            return results[0].get("content", "")[:600]
    except Exception:
        pass

    return None


# =============================================================================
# GOVERNMENT DOCUMENT SOURCES (for footnotes)
# =============================================================================

GOVERNMENT_SOURCES = {
    "technology": [
        "Bureau of Labor Statistics, Occupational Outlook Handbook 2024",
        "National Science Foundation, Science and Engineering Indicators 2024",
        "Department of Commerce, Strengthening American Technology Leadership"
    ],
    "healthcare": [
        "Association of American Medical Colleges, 2024 Physician Workforce Report",
        "Centers for Disease Control and Prevention, Healthcare Workforce Statistics",
        "Health Resources & Services Administration, National Center for Health Workforce Analysis"
    ],
    "engineering": [
        "American Society of Civil Engineers, 2024 Infrastructure Report Card",
        "Bureau of Labor Statistics, Engineers Occupational Outlook",
        "Department of Transportation, Infrastructure Investment Plan"
    ],
    "artificial_intelligence": [
        "Executive Order 14110, Safe, Secure, and Trustworthy AI Development",
        "National AI Initiative Office, 2024 Annual Report",
        "NIST AI Risk Management Framework"
    ],
    "cybersecurity": [
        "National Cybersecurity Strategy, 2023",
        "Cybersecurity and Infrastructure Security Agency, Workforce Framework",
        "Department of Labor, Cybersecurity Career Pathways"
    ],
    "renewable_energy": [
        "Department of Energy, U.S. Energy and Employment Report 2024",
        "Inflation Reduction Act Implementation Report",
        "National Renewable Energy Laboratory, Jobs & Economic Development Analysis"
    ],
    "biotechnology": [
        "Executive Order on Biotechnology and Biomanufacturing Innovation",
        "National Institutes of Health, Research Workforce Report",
        "BIO, The State of American Bioeconomy"
    ],
    "finance": [
        "Bureau of Labor Statistics, Financial Services Employment Data",
        "Treasury Department, Financial Services Sector Report",
        "Federal Reserve, Labor Market Conditions in Financial Services"
    ],
    "academia": [
        "National Science Foundation, Survey of Graduate Students and Postdocs",
        "American Council on Education, Higher Education Report",
        "National Academies, The State of US Science and Engineering"
    ]
}


def get_government_sources(field: str, limit: int = 3) -> List[str]:
    """Get government document sources for footnotes"""
    category = get_field_category(field)
    sources = GOVERNMENT_SOURCES.get(category, GOVERNMENT_SOURCES["technology"])
    return sources[:limit]


# =============================================================================
# MAIN EXPORT
# =============================================================================

__all__ = [
    "AILA_AVAILABLE",
    "get_field_category",
    "get_national_importance_content",
    "enhance_lor_with_aila",
    "get_criteria_language",
    "get_government_sources",
    "FIELD_STATISTICS",
    "PRONG_3_TEMPLATES",
    "GOVERNMENT_SOURCES"
]
