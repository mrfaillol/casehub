#!/usr/bin/env python3
"""
LLM Content Generator for Immigration Documents
Uses Gemini API as primary, Perplexity API as fallback.
Each generation is unique - no templates, pure AI-generated text.

IMPORTANT: This module is for INTERNAL use only.
The end-user interface should NOT mention AI generation.
"""

import os
import random
import hashlib
from datetime import datetime
from typing import Optional, Dict, List
import httpx
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# API CONFIGURATION
# =============================================================================

# Primary: Gemini (ILC account)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

# Fallback: Perplexity (personal account)
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"

# =============================================================================
# WRITING STYLE VARIATIONS
# =============================================================================

WRITING_STYLES = [
    "direct and confident, using short declarative sentences",
    "warm but professional, with personal anecdotes",
    "formal and academic, with careful word choice",
    "conversational yet authoritative",
    "precise and technical, with specific details",
    "narrative-driven, telling a story",
]

TONES = [
    "enthusiastic endorsement",
    "measured professional assessment",
    "strong advocacy",
    "thoughtful evaluation",
    "genuine personal recommendation",
]

# =============================================================================
# FIELD REFERENCES - Government Documents & Statistics
# =============================================================================

FIELD_REFERENCES = {
    "cybersecurity": {
        "executive_orders": [
            "Executive Order 14028, 'Improving the Nation's Cybersecurity' (May 12, 2021)",
            "Executive Order 14144, 'Strengthening and Promoting Innovation in the Nation's Cybersecurity' (January 16, 2025)",
        ],
        "strategic_plans": ["National Cybersecurity Strategy (March 2023)"],
        "statistics": [
            "Cybercrime losses exceeded $12.5 billion in 2023 (FBI)",
            "500,000+ unfilled cybersecurity positions in the US (CyberSeek)",
            "Ransomware attacks increased 95% in 2023",
        ],
    },
    "ai_ml": {
        "executive_orders": [
            "Executive Order 14110, 'Safe, Secure, and Trustworthy Development and Use of Artificial Intelligence' (October 30, 2023)",
        ],
        "strategic_plans": ["National AI R&D Strategic Plan (2023 Update)"],
        "statistics": [
            "AI market projected to reach $190 billion by 2025",
            "69% of companies report AI talent shortage",
            "US AI investment reached $67 billion in 2023",
        ],
    },
    "healthcare": {
        "executive_orders": [
            "Executive Order 14036, 'Promoting Competition in the American Economy' (healthcare provisions)",
        ],
        "strategic_plans": [
            "NIH Strategic Plan for Data Science",
            "HHS Strategic Plan 2022-2026",
            "National Health Security Strategy",
        ],
        "statistics": [
            "Healthcare spending reached $4.5 trillion in 2023",
            "Projected shortage of 124,000 physicians by 2034 (AAMC)",
            "Nursing shortage expected to reach 500,000 by 2030",
        ],
    },
    "clean_energy": {
        "executive_orders": [
            "Inflation Reduction Act provisions on clean energy (2022)",
            "Executive Order 14008, 'Tackling the Climate Crisis' (January 27, 2021)",
        ],
        "strategic_plans": [
            "DOE Strategic Plan 2022-2026",
            "National Climate Strategy",
            "U.S. Long-Term Strategy to 2050",
        ],
        "statistics": [
            "Clean energy investments exceeded $150 billion in 2023",
            "1.5 million clean energy jobs created since 2020",
            "Renewable energy capacity grew 22% in 2023",
        ],
    },
    "biotech": {
        "executive_orders": [
            "Executive Order 14081, 'Advancing Biotechnology and Biomanufacturing Innovation' (September 12, 2022)",
        ],
        "strategic_plans": [
            "National Biotechnology and Biomanufacturing Initiative",
            "NIH Strategic Plan 2021-2025",
        ],
        "statistics": [
            "US biotech industry valued at $600+ billion",
            "Biotech R&D investments grew 15% annually",
            "Biomanufacturing sector expected to grow to $1.4 trillion by 2030",
        ],
    },
    "finance": {
        "executive_orders": [
            "Executive Order 14067, 'Ensuring Responsible Development of Digital Assets' (March 9, 2022)",
        ],
        "strategic_plans": [
            "Treasury Financial Stability Oversight Council Reports",
            "Federal Reserve Financial Stability Report",
        ],
        "statistics": [
            "US financial services sector represents 8.5% of GDP",
            "FinTech investments exceeded $50 billion in 2023",
            "75,000+ financial analyst positions unfilled annually",
        ],
    },
    "engineering": {
        "executive_orders": [
            "CHIPS and Science Act (2022)",
            "Infrastructure Investment and Jobs Act (2021)",
        ],
        "strategic_plans": [
            "National Science Foundation Strategic Plan",
            "DOD Engineering Workforce Strategy",
        ],
        "statistics": [
            "Engineering workforce shortage of 220,000+ professionals",
            "STEM job growth outpacing non-STEM by 3x",
            "Infrastructure spending creating 1.5 million engineering jobs",
        ],
    },
    "education": {
        "executive_orders": [],
        "strategic_plans": [
            "Department of Education Strategic Plan 2022-2026",
            "National STEM Education Strategic Plan",
        ],
        "statistics": [
            "Teacher shortage affecting 300,000+ positions nationwide",
            "STEM educator gap particularly severe in underserved areas",
            "PhD graduates in education declining 15% over past decade",
        ],
    },
    "robotics": {
        "executive_orders": [
            "Executive Order 14110 (AI provisions affecting robotics)",
        ],
        "strategic_plans": [
            "National AI R&D Strategic Plan (robotics provisions)",
            "NSF Robotics Research Priorities",
        ],
        "statistics": [
            "US robotics market valued at $17 billion in 2023",
            "Manufacturing robotics adoption growing 25% annually",
            "Healthcare robotics projected to reach $12 billion by 2026",
        ],
    },
    "semiconductor": {
        "executive_orders": [
            "CHIPS and Science Act (August 9, 2022)",
            "Executive Order 14017, 'America's Supply Chains' (February 24, 2021)",
        ],
        "strategic_plans": [
            "National Semiconductor Technology Center Strategy",
            "DOD Microelectronics Strategy",
        ],
        "statistics": [
            "$52 billion federal investment in domestic semiconductor manufacturing",
            "US share of global chip manufacturing dropped from 37% to 12%",
            "100,000+ semiconductor jobs to be created by 2030",
        ],
    },
    "aerospace": {
        "executive_orders": [
            "Space Policy Directive-1 through 5",
        ],
        "strategic_plans": [
            "NASA Artemis Program",
            "FAA Aerospace Forecast",
            "National Space Strategy",
        ],
        "statistics": [
            "US aerospace industry contributes $909 billion to GDP",
            "2.2 million aerospace jobs in the United States",
            "Commercial space sector growing 9% annually",
        ],
    },
    "data_science": {
        "executive_orders": [
            "Executive Order 14110 (AI/Data provisions)",
            "Federal Data Strategy Action Plan",
        ],
        "strategic_plans": [
            "NIH Strategic Plan for Data Science",
            "Federal Data Strategy 2020-2024",
        ],
        "statistics": [
            "Data scientist positions growing 36% faster than average",
            "140,000+ unfilled data science positions",
            "Big data market to reach $273 billion by 2026",
        ],
    },
    "pharmaceutical": {
        "executive_orders": [
            "Executive Order 14036 (drug pricing provisions)",
            "Executive Order 13944, 'Lowering Drug Prices' (September 13, 2020)",
        ],
        "strategic_plans": [
            "FDA Drug Development Modernization",
            "NIH HEAL Initiative",
        ],
        "statistics": [
            "US pharmaceutical R&D spending exceeded $100 billion in 2023",
            "48% of new drugs globally developed in the US",
            "Pharmaceutical sector employs 350,000+ researchers",
        ],
    },
    "materials_science": {
        "executive_orders": [
            "CHIPS and Science Act (materials provisions)",
        ],
        "strategic_plans": [
            "Materials Genome Initiative Strategic Plan",
            "DOE Basic Energy Sciences Priorities",
        ],
        "statistics": [
            "Advanced materials market projected at $90 billion",
            "Critical materials shortage affecting multiple industries",
            "Materials research funding increased 20% since 2020",
        ],
    },
    "environmental": {
        "executive_orders": [
            "Executive Order 14008, 'Tackling the Climate Crisis' (January 27, 2021)",
            "Executive Order 13990, 'Protecting Public Health and the Environment'",
        ],
        "strategic_plans": [
            "EPA Strategic Plan 2022-2026",
            "National Climate Assessment",
        ],
        "statistics": [
            "Environmental consulting market at $35 billion",
            "Climate-related jobs growing 8% annually",
            "EPA workforce needs 15,000+ additional scientists",
        ],
    },
}


def get_field_references(field: str) -> Dict:
    """Get government references for a field."""
    field_lower = field.lower().replace(" ", "_").replace("-", "_")

    # Try exact match
    if field_lower in FIELD_REFERENCES:
        return FIELD_REFERENCES[field_lower]

    # Try partial match
    for key in FIELD_REFERENCES:
        if key in field_lower or field_lower in key:
            return FIELD_REFERENCES[key]

    # Default generic references
    return {
        "executive_orders": [],
        "strategic_plans": ["Relevant federal strategic initiatives"],
        "statistics": ["Significant workforce demand in this sector"],
    }


def get_unique_seed() -> str:
    """Generate unique seed for variation."""
    timestamp = datetime.now().isoformat()
    random_component = random.randint(100000, 999999)
    return hashlib.md5(f"{timestamp}-{random_component}".encode()).hexdigest()[:8]


# =============================================================================
# API CALL FUNCTIONS
# =============================================================================

async def _call_gemini(prompt: str, max_tokens: int = 4000) -> str:
    """Call Gemini API (primary)."""
    if not GEMINI_API_KEY:
        raise Exception("GEMINI_API_KEY not configured")

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.85,
                    "maxOutputTokens": max_tokens,
                    "topP": 0.95,
                },
            },
        )

        if response.status_code != 200:
            logger.error(f"Gemini API error: {response.status_code} - {response.text}")
            raise Exception(f"Gemini API error: {response.status_code}")

        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


async def _call_perplexity(system_prompt: str, user_prompt: str, max_tokens: int = 4000) -> str:
    """Call Perplexity API (fallback)."""
    if not PERPLEXITY_API_KEY:
        raise Exception("PERPLEXITY_API_KEY not configured")

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            PERPLEXITY_API_URL,
            headers={
                "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "sonar",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.85,
                "max_tokens": max_tokens,
            },
        )

        if response.status_code != 200:
            logger.error(f"Perplexity API error: {response.status_code} - {response.text}")
            raise Exception(f"Perplexity API error: {response.status_code}")

        data = response.json()
        return data["choices"][0]["message"]["content"]


# =============================================================================
# LOR GENERATION
# =============================================================================

async def generate_lor_content(
    beneficiary_name: str,
    field: str,
    recommender_name: str,
    recommender_title: str,
    recommender_org: str,
    recommender_email: str,
    relationship: str,
    years_known: str,
    custom_content: Optional[str] = None,
    recommender_credentials: Optional[str] = None,
    specific_achievements: Optional[str] = None,
) -> List[str]:
    """
    Generate LOR content using LLM.
    Returns list of paragraphs for the letter.
    Target: 600-900 words.
    """

    style = random.choice(WRITING_STYLES)
    tone = random.choice(TONES)
    unique_seed = get_unique_seed()
    field_refs = get_field_references(field)

    # Build field context
    field_context = ""
    if field_refs.get("executive_orders"):
        field_context += f"\nRelevant Executive Orders: {', '.join(field_refs['executive_orders'])}"
    if field_refs.get("strategic_plans"):
        field_context += f"\nRelevant Strategic Plans: {', '.join(field_refs['strategic_plans'])}"
    if field_refs.get("statistics"):
        field_context += f"\nRelevant Statistics: {', '.join(field_refs['statistics'])}"

    prompt = f"""You are a professional document writer creating a Letter of Recommendation for an EB-2 National Interest Waiver (NIW) immigration petition.

CRITICAL REQUIREMENTS:
1. Write in FIRST PERSON as the recommender ({recommender_name})
2. The letter must be 600-900 words
3. Must address ALL THREE PRONGS of Matter of Dhanasar:
   - Prong 1: Substantial merit and national importance
   - Prong 2: Well positioned to advance the endeavor
   - Prong 3: On balance, beneficial to waive labor certification
4. Include specific statistics and cite government documents
5. NO templates, NO generic phrases like "I am writing to recommend" or "It is my pleasure"
6. Each letter must be UNIQUE - use variation seed: {unique_seed}

WRITING STYLE: {style}
TONE: {tone}

FIELD-SPECIFIC CONTEXT for {field}:{field_context}

STRUCTURE (follow this order):
1. Personal introduction establishing credibility (your background, qualifications)
2. How you know the beneficiary and context of relationship
3. Specific observations of their work and contributions
4. Why their work matters nationally (statistics, government priorities)
5. Why they are uniquely qualified (skills, experience, track record)
6. Why waiving labor certification is in the national interest
7. Strong concluding endorsement

FORBIDDEN:
- Em dashes (—)
- "I am writing to recommend"
- "It is my pleasure"
- Generic superlatives without evidence
- Template-sounding language

RECOMMENDER INFORMATION:
- Name: {recommender_name}
- Title: {recommender_title}
- Organization: {recommender_org}
- Email: {recommender_email}
- Relationship to beneficiary: {relationship}
- Years known: {years_known}
{f'- Additional credentials: {recommender_credentials}' if recommender_credentials else ''}

BENEFICIARY INFORMATION:
- Name: {beneficiary_name}
- Field: {field}
{f'- Specific achievements: {specific_achievements}' if specific_achievements else ''}
{f'- Additional context: {custom_content}' if custom_content else ''}

Write the letter body only (no headers, no signature block - those will be added separately).
Start directly with your introduction as the recommender.
End with your endorsement statement.

Remember: 600-900 words, unique voice, address all three prongs."""

    try:
        # Try Gemini first
        logger.info("Generating LOR with Gemini API...")
        content = await _call_gemini(prompt, max_tokens=2000)
        logger.info("LOR generated successfully with Gemini")
    except Exception as e:
        logger.warning(f"Gemini failed, falling back to Perplexity: {e}")
        try:
            content = await _call_perplexity(
                "You are a professional immigration document writer.",
                prompt,
                max_tokens=2000
            )
            logger.info("LOR generated successfully with Perplexity (fallback)")
        except Exception as e2:
            logger.error(f"Both APIs failed: {e2}")
            raise

    # Split into paragraphs
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    logger.info(f"Generated LOR with {len(' '.join(paragraphs).split())} words")

    return paragraphs


# =============================================================================
# PERSONAL STATEMENT GENERATION
# =============================================================================

async def generate_ps_content(
    beneficiary_name: str,
    field: str,
    overview: Optional[str] = None,
    national_importance: Optional[str] = None,
    practical_impact: Optional[str] = None,
    well_positioned: Optional[str] = None,
    conclusion: Optional[str] = None,
    background_info: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Generate Personal Statement content using LLM.
    Returns dict with sections.
    Target: 2,500-4,000 words total.
    """

    style = random.choice(WRITING_STYLES)
    unique_seed = get_unique_seed()
    field_refs = get_field_references(field)

    # Build field context
    field_context = ""
    if field_refs.get("executive_orders"):
        field_context += f"\nRelevant Executive Orders to cite: {', '.join(field_refs['executive_orders'])}"
    if field_refs.get("strategic_plans"):
        field_context += f"\nRelevant Strategic Plans: {', '.join(field_refs['strategic_plans'])}"
    if field_refs.get("statistics"):
        field_context += f"\nRelevant Statistics: {', '.join(field_refs['statistics'])}"

    # Build context from user inputs
    context_parts = []
    if overview:
        context_parts.append(f"Overview context provided by applicant: {overview}")
    if national_importance:
        context_parts.append(f"National importance context provided by applicant: {national_importance}")
    if practical_impact:
        context_parts.append(f"Practical impact context provided by applicant: {practical_impact}")
    if well_positioned:
        context_parts.append(f"Qualifications context provided by applicant: {well_positioned}")
    if conclusion:
        context_parts.append(f"Conclusion context provided by applicant: {conclusion}")
    if background_info:
        for key, value in background_info.items():
            context_parts.append(f"{key}: {value}")

    context = "\n".join(context_parts) if context_parts else "No additional context provided - generate comprehensive content based on field expertise."

    prompt = f"""You are a professional immigration document writer creating a Personal Statement for an EB-2 National Interest Waiver (NIW) petition.

ABSOLUTE MINIMUM WORD COUNT: 2,500 words. Aim for 3,000+ words.
This is a LEGAL DOCUMENT that will be reviewed by USCIS. It must be comprehensive and detailed.

CRITICAL REQUIREMENTS:
1. Write in FIRST PERSON as the beneficiary ({beneficiary_name})
2. The statement MUST be at least 2,500 words - this is non-negotiable
3. Must be structured in 5 numbered sections with specific minimum lengths
4. Address all THREE PRONGS of Matter of Dhanasar throughout
5. Include specific government document citations (Executive Orders, Strategic Plans)
6. Include real statistics about the field
7. End with perjury declaration
8. Variation seed: {unique_seed}

WRITING STYLE: {style}

MANDATORY STRUCTURE WITH MINIMUM WORD COUNTS:

I. Overview of the Proposed Endeavor (MINIMUM 700 words)
   Required content:
   - Complete academic and professional journey (education, positions held, progression)
   - THREE distinct components of your proposed endeavor in the US
   - How each component connects to national priorities
   - Your specific expertise and how you developed it
   - Current role and responsibilities in detail

II. National Importance of the Endeavor (MINIMUM 600 words)
   Required content:
   - At least TWO specific government document citations with dates
   - At least THREE relevant statistics with sources
   - Explanation of the "twofold benefit" to the United States
   - Connection to workforce gaps and national security
   - Economic impact of your field

III. Practical Impact and Innovation (MINIMUM 500 words)
   Required content:
   - At least THREE specific innovations or contributions with metrics
   - Publications with citation counts if applicable
   - Patents or pending patents
   - Conference presentations
   - Real-world applications of your work
   - Quantifiable outcomes (percentages, dollar amounts, users affected)

IV. Why I Am Well-Positioned to Advance the Endeavor (MINIMUM 500 words)
   Required content:
   - Complete academic credentials with institution names
   - Your dual role as both researcher/practitioner
   - Unique combination of skills that sets you apart
   - Track record of success with specific examples
   - Network and collaborations
   - Why you specifically (not just anyone in the field) can do this

V. Conclusion (MINIMUM 250 words)
   Required content:
   - Summary of the twofold benefit
   - Reiteration of your unique qualifications
   - Direct request to USCIS
   - MUST include verbatim: "I declare under penalty of perjury under the laws of the United States of America that the foregoing is true and correct."
   - Signature line: "Signed: [Name]" and "Date: [Current Date]"

FIELD-SPECIFIC CONTEXT for {field}:{field_context}

APPLICANT-PROVIDED CONTEXT:
{context}

FORBIDDEN:
- Em dashes (—)
- Generic phrases without substance
- Vague claims without evidence
- Sections shorter than the minimum word counts specified above
- Rushing through any section

Write the complete document now. Do not abbreviate or summarize. Every section must be fully developed."""

    try:
        # Try Gemini first
        logger.info("Generating PS with Gemini API...")
        content = await _call_gemini(prompt, max_tokens=8000)
        logger.info("PS generated successfully with Gemini")
    except Exception as e:
        logger.warning(f"Gemini failed, falling back to Perplexity: {e}")
        try:
            content = await _call_perplexity(
                "You are a professional immigration document writer creating comprehensive legal documents.",
                prompt,
                max_tokens=8000
            )
            logger.info("PS generated successfully with Perplexity (fallback)")
        except Exception as e2:
            logger.error(f"Both APIs failed: {e2}")
            raise

    # Parse sections
    sections = parse_ps_sections(content)
    total_words = sum(len(s.split()) for s in sections.values())
    logger.info(f"Generated PS with {total_words} words")

    return sections


def parse_ps_sections(content: str) -> Dict[str, str]:
    """Parse the PS content into sections."""
    import re

    sections = {
        "overview": "",
        "national_importance": "",
        "practical_impact": "",
        "well_positioned": "",
        "conclusion": "",
    }

    # Common section patterns
    patterns = [
        (r"I\.\s*Overview.*?(?=II\.|$)", "overview"),
        (r"II\.\s*National.*?(?=III\.|$)", "national_importance"),
        (r"III\.\s*Practical.*?(?=IV\.|$)", "practical_impact"),
        (r"IV\.\s*(?:Why I Am )?Well.*?(?=V\.|$)", "well_positioned"),
        (r"V\.\s*Conclusion.*", "conclusion"),
    ]

    for pattern, key in patterns:
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if match:
            sections[key] = match.group(0).strip()

    # Fallback: if parsing failed, put everything in overview
    if not any(sections.values()):
        sections["overview"] = content

    return sections
