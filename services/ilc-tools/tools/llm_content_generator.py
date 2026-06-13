#!/usr/bin/env python3
"""
LLM Content Generator for Immigration Documents
Uses Gemini API as primary, Perplexity as fallback.
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

# API Configuration - Gemini is PRIMARY, Perplexity is FALLBACK
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"

# Writing style variations for humanization
WRITING_STYLES = [
    "direct and confident, using short declarative sentences",
    "warm but professional, with personal anecdotes",
    "formal and academic, with careful word choice",
    "conversational yet authoritative",
    "precise and technical, with specific details",
    "narrative-driven, telling a story",
]

# Tone variations
TONES = [
    "enthusiastic endorsement",
    "measured professional assessment",
    "strong advocacy",
    "thoughtful evaluation",
    "genuine personal recommendation",
]

# Opening style mappings (from Advanced Customization)
OPENING_STYLES = {
    "direct_personal": "Start with a direct personal introduction: 'I am [Name], [Title] at [Org]...'",
    "formal_declaration": "Begin with a formal declaration: 'My name is X. I am writing in strong support...'",
    "credentials_first": "Lead with your professional qualifications and expertise before introducing the beneficiary",
    "anecdote_opener": "Start with a specific memorable story or moment that illustrates the beneficiary's qualities",
    "context_first": "Establish the professional context or situation before introducing the people involved",
    "symposium_meeting": "Explain how you first met at a professional conference, symposium, or industry event",
    "project_collaboration": "Begin by describing a specific project or collaboration that brought you together",
    "independent_evaluator": "Emphasize your objective, independent perspective as an expert evaluator in the field",
}

# Letter structure mappings
LETTER_STRUCTURES = {
    "flowing_narrative": "Write as continuous prose without section headers, flowing naturally between topics",
    "sectioned": "Organize with clear section headers: Background, Professional Relationship, Achievements, National Importance, Conclusion",
    "problem_solution": "Structure around challenges the beneficiary addressed and the impactful solutions they developed",
    "chronological": "Follow a timeline of your relationship and the beneficiary's achievements over the years",
}


def get_unique_seed() -> str:
    """Generate unique seed for variation."""
    timestamp = datetime.now().isoformat()
    random_component = random.randint(100000, 999999)
    return hashlib.md5(f"{timestamp}-{random_component}".encode()).hexdigest()[:8]


async def _call_gemini(prompt: str, max_tokens: int = 4000) -> str:
    """Call Gemini API."""
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
    """Call Perplexity API as fallback."""
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
    # Advanced Customization options
    opening_style: Optional[str] = None,
    letter_structure: Optional[str] = None,
    relationship_type: Optional[str] = None,
) -> List[str]:
    """
    Generate LOR content using LLM.
    Returns list of paragraphs for the letter.
    Uses Gemini as primary, Perplexity as fallback.
    """

    # Use user's Advanced Customization choices, or random for variation
    if opening_style and opening_style in OPENING_STYLES:
        style = OPENING_STYLES[opening_style]
    else:
        style = random.choice(WRITING_STYLES)
    
    if letter_structure and letter_structure in LETTER_STRUCTURES:
        structure = LETTER_STRUCTURES[letter_structure]
    else:
        structure = "Write as flowing prose"
    
    tone = random.choice(TONES)
    unique_seed = get_unique_seed()
    
    # Log what's being used
    logger.info(f"LOR Style: opening_style={opening_style}, letter_structure={letter_structure}")
    logger.info(f"Using style='{style[:50]}...', structure='{structure[:50]}...'")

    # Build the prompt
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

OPENING STYLE: {style}
LETTER STRUCTURE: {structure}
TONE: {tone}

FIELD-SPECIFIC REQUIREMENTS for {field}:
- Include relevant Executive Orders, strategic plans, or government initiatives
- Cite real statistics about the field's importance to the US
- Reference workforce gaps or national priorities

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

---

Write a Letter of Recommendation for {beneficiary_name}'s EB-2 NIW petition.

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

    content = None

    # Try Gemini first
    if GEMINI_API_KEY:
        try:
            logger.info("Generating LOR with Gemini API...")
            content = await _call_gemini(prompt, max_tokens=2000)
            logger.info("LOR generated successfully with Gemini")
        except Exception as e:
            logger.warning(f"Gemini failed, falling back to Perplexity: {str(e)}")

    # Fallback to Perplexity
    if content is None and PERPLEXITY_API_KEY:
        try:
            logger.info("Generating LOR with Perplexity API (fallback)...")
            content = await _call_perplexity(
                system_prompt=prompt.split("---")[0],
                user_prompt=prompt.split("---")[1] if "---" in prompt else prompt,
                max_tokens=2000
            )
            logger.info("LOR generated successfully with Perplexity")
        except Exception as e:
            logger.error(f"Both APIs failed: {str(e)}")
            raise Exception("Failed to generate LOR: both Gemini and Perplexity APIs failed")

    if content is None:
        raise Exception("No API keys configured for LLM generation")

    # Split into paragraphs
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

    logger.info(f"Generated LOR with {len(' '.join(paragraphs).split())} words")
    return paragraphs


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
    MINIMUM 2,500 words total.
    Uses Gemini as primary, Perplexity as fallback.
    """

    style = random.choice(WRITING_STYLES)
    unique_seed = get_unique_seed()

    # Get field-specific references
    field_refs = get_field_references(field)
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

FORBIDDEN:
- Em dashes (—)
- Generic phrases without substance
- Vague claims without evidence
- Sections shorter than the minimum word counts specified above
- Rushing through any section

---

Write a comprehensive Personal Statement for {beneficiary_name}'s EB-2 NIW petition in the field of {field}.

APPLICANT-PROVIDED CONTEXT:
{context}

INSTRUCTIONS:
1. Generate the COMPLETE 5-section personal statement
2. Use Roman numerals (I, II, III, IV, V) for section headers
3. Each section must meet or exceed the minimum word count specified
4. TOTAL document must be at least 2,500 words
5. Be specific, detailed, and thorough in every section
6. Include real statistics and government citations for {field}
7. Make it personal and unique to this beneficiary
8. End with the perjury declaration in Section V

Write the complete document now. Do not abbreviate or summarize. Every section must be fully developed."""

    content = None

    # Try Gemini first
    if GEMINI_API_KEY:
        try:
            logger.info("Generating PS with Gemini API...")
            content = await _call_gemini(prompt, max_tokens=8000)
            logger.info("PS generated successfully with Gemini")
        except Exception as e:
            logger.warning(f"Gemini failed, falling back to Perplexity: {str(e)}")

    # Fallback to Perplexity
    if content is None and PERPLEXITY_API_KEY:
        try:
            logger.info("Generating PS with Perplexity API (fallback)...")
            content = await _call_perplexity(
                system_prompt=prompt.split("---")[0],
                user_prompt=prompt.split("---")[1] if "---" in prompt else prompt,
                max_tokens=8000
            )
            logger.info("PS generated successfully with Perplexity")
        except Exception as e:
            logger.error(f"Both APIs failed: {str(e)}")
            raise Exception("Failed to generate PS: both Gemini and Perplexity APIs failed")

    if content is None:
        raise Exception("No API keys configured for LLM generation")

    # Parse sections from the response
    sections = parse_ps_sections(content)

    total_words = sum(len(s.split()) for s in sections.values())
    logger.info(f"Generated PS with {total_words} words")

    return sections


def parse_ps_sections(content: str) -> Dict[str, str]:
    """Parse the PS content into sections."""
    sections = {
        "overview": "",
        "national_importance": "",
        "practical_impact": "",
        "well_positioned": "",
        "conclusion": "",
    }

    # Try to find section markers
    import re

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


# Government document references by field
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
        ],
    },
    "healthcare": {
        "executive_orders": [],
        "strategic_plans": ["NIH Strategic Plan for Data Science", "HHS Strategic Plan 2022-2026"],
        "statistics": [
            "Healthcare spending reached $4.3 trillion in 2021",
            "Projected shortage of 124,000 physicians by 2034",
        ],
    },
    "clean_energy": {
        "executive_orders": [
            "Inflation Reduction Act provisions on clean energy",
        ],
        "strategic_plans": ["DOE Strategic Plan", "National Climate Strategy"],
        "statistics": [
            "Clean energy investments exceeded $150 billion in 2023",
            "1.5 million clean energy jobs created since 2020",
        ],
    },
    "biotech": {
        "executive_orders": [
            "Executive Order 14081, 'Advancing Biotechnology and Biomanufacturing Innovation' (September 12, 2022)",
        ],
        "strategic_plans": ["National Biotechnology and Biomanufacturing Initiative"],
        "statistics": [
            "US biotech industry valued at $600+ billion",
            "Biotech R&D investments grew 15% annually",
        ],
    },
}


def get_field_references(field: str) -> Dict:
    """Get government references for a field."""
    # Normalize field name
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
