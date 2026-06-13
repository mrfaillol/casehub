"""
CaseHub Tools - Visa Eligibility Checker
Avaliacao automatica de elegibilidade para vistos de imigracao

INSTALACAO:
1. Copiar para /opt/casehub/ilc-tools/tools/eligibility_checker.py
2. Importar no app.py: from tools.eligibility_checker import EligibilityChecker
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import json


class VisaType(Enum):
    EB1A = "EB-1A"
    EB1B = "EB-1B"
    EB2_NIW = "EB-2 NIW"
    EB2_PERM = "EB-2 PERM"
    EB3 = "EB-3"
    O1A = "O-1A"
    O1B = "O-1B"
    H1B = "H-1B"
    L1A = "L-1A"
    L1B = "L-1B"
    TN = "TN"
    E2 = "E-2"


@dataclass
class CriteriaResult:
    criterion: str
    met: bool
    evidence_level: str  # "strong", "moderate", "weak", "none"
    notes: str
    suggestions: List[str]


@dataclass
class EligibilityResult:
    visa_type: str
    overall_score: int  # 0-100
    recommendation: str  # "strong", "moderate", "weak", "not_recommended"
    criteria_met: int
    criteria_needed: int
    criteria_results: List[CriteriaResult]
    strengths: List[str]
    weaknesses: List[str]
    action_items: List[str]
    alternative_visas: List[str]
    notes: str


# =============================================================================
# CRITERIA DEFINITIONS
# =============================================================================

EB1A_CRITERIA = [
    {
        "id": "awards",
        "name": "National/International Awards",
        "description": "Receipt of lesser nationally or internationally recognized prizes or awards for excellence",
        "questions": [
            "Have you received any awards or prizes for your work?",
            "Are these awards recognized nationally or internationally?",
            "Are they specifically for excellence in your field?"
        ],
        "evidence_examples": [
            "Award certificates",
            "News articles about the award",
            "Selection criteria documentation",
            "List of past recipients"
        ],
        "weight": 1.0
    },
    {
        "id": "memberships",
        "name": "Exclusive Memberships",
        "description": "Membership in associations requiring outstanding achievements as judged by experts",
        "questions": [
            "Are you a member of any professional associations?",
            "Do these associations require achievements for membership?",
            "Was your membership based on evaluation by experts?"
        ],
        "evidence_examples": [
            "Membership certificates",
            "Membership requirements documentation",
            "Evidence of selective admission process"
        ],
        "weight": 1.0
    },
    {
        "id": "published_material",
        "name": "Published Material About You",
        "description": "Published material in professional publications about you and your work",
        "questions": [
            "Have there been articles written about you or your work?",
            "Were these in professional or major trade publications?",
            "Do they discuss your specific contributions?"
        ],
        "evidence_examples": [
            "News articles",
            "Magazine features",
            "Professional journal articles about your work",
            "Interviews"
        ],
        "weight": 1.0
    },
    {
        "id": "judging",
        "name": "Judging Others' Work",
        "description": "Participation as a judge of the work of others in your field",
        "questions": [
            "Have you reviewed papers for journals or conferences?",
            "Have you served on grant review panels?",
            "Have you judged competitions in your field?"
        ],
        "evidence_examples": [
            "Reviewer invitations/confirmations",
            "Editorial board memberships",
            "Grant panel appointment letters",
            "Competition judging certificates"
        ],
        "weight": 1.0
    },
    {
        "id": "original_contributions",
        "name": "Original Contributions",
        "description": "Original scientific, scholarly, artistic, athletic, or business-related contributions of major significance",
        "questions": [
            "Have you made original contributions to your field?",
            "Are these contributions recognized by others as significant?",
            "Have others adopted or built upon your work?"
        ],
        "evidence_examples": [
            "Patents",
            "Expert testimonial letters",
            "Citation evidence",
            "Implementation evidence",
            "Revenue/impact metrics"
        ],
        "weight": 1.5
    },
    {
        "id": "scholarly_articles",
        "name": "Scholarly Articles",
        "description": "Authorship of scholarly articles in professional journals or major media",
        "questions": [
            "Have you authored articles in peer-reviewed journals?",
            "Have you written for major trade publications?",
            "How many publications do you have?"
        ],
        "evidence_examples": [
            "Published articles",
            "Citation reports",
            "Journal impact factors",
            "Co-author statements"
        ],
        "weight": 1.0
    },
    {
        "id": "exhibitions",
        "name": "Artistic Exhibitions",
        "description": "Display of your work at artistic exhibitions or showcases",
        "questions": [
            "Has your work been displayed at exhibitions?",
            "Were these exhibitions of artistic significance?",
            "What was the reception of your work?"
        ],
        "evidence_examples": [
            "Exhibition catalogs",
            "Gallery statements",
            "Reviews",
            "Photos of displays"
        ],
        "weight": 1.0
    },
    {
        "id": "leading_role",
        "name": "Leading/Critical Role",
        "description": "Leading or critical role in distinguished organizations",
        "questions": [
            "Have you held leadership positions?",
            "Were these at distinguished or reputable organizations?",
            "What was the scope of your responsibilities?"
        ],
        "evidence_examples": [
            "Organizational charts",
            "Title documentation",
            "Scope of responsibility letters",
            "Team size and budget evidence"
        ],
        "weight": 1.0
    },
    {
        "id": "high_salary",
        "name": "High Salary/Remuneration",
        "description": "Command of a high salary or remuneration relative to others in the field",
        "questions": [
            "Is your salary significantly above average for your field?",
            "Do you have evidence comparing your pay to industry standards?",
            "Have you received significant bonuses or equity?"
        ],
        "evidence_examples": [
            "Pay stubs/offer letters",
            "Industry salary surveys",
            "Comparative analysis",
            "Equity documentation"
        ],
        "weight": 1.0
    },
    {
        "id": "commercial_success",
        "name": "Commercial Success",
        "description": "Commercial successes in the performing arts (box office, ratings, sales)",
        "questions": [
            "Have you achieved commercial success in performing arts?",
            "Do you have evidence of box office, sales, or ratings?",
            "How does your success compare to peers?"
        ],
        "evidence_examples": [
            "Box office records",
            "Sales figures",
            "Streaming numbers",
            "Chart positions"
        ],
        "weight": 1.0
    }
]

NIW_PRONGS = [
    {
        "id": "prong1",
        "name": "Prong 1: Substantial Merit and National Importance",
        "description": "The proposed endeavor has both substantial merit and national importance",
        "questions": [
            "What is your proposed endeavor in the US?",
            "Does it have substantial merit (economic, cultural, scientific, etc.)?",
            "Does it have implications beyond a specific locality (national scope)?"
        ],
        "evidence_examples": [
            "Personal statement",
            "Government statistics showing field importance",
            "Executive orders or policy documents",
            "Industry reports"
        ],
        "weight": 2.0
    },
    {
        "id": "prong2",
        "name": "Prong 2: Well Positioned to Advance",
        "description": "You are well positioned to advance the proposed endeavor",
        "questions": [
            "What is your education and experience in this area?",
            "What is your track record of success?",
            "Do you have a clear plan to advance the endeavor?"
        ],
        "evidence_examples": [
            "Degrees and credentials",
            "Past project successes",
            "Letters from experts",
            "Business plan or research plan"
        ],
        "weight": 2.0
    },
    {
        "id": "prong3",
        "name": "Prong 3: National Interest Balance",
        "description": "On balance, it would be beneficial to waive the job offer and labor certification requirements",
        "questions": [
            "Why would the US benefit more from waiving the labor cert?",
            "Is there urgency to your work?",
            "Would requiring a specific employer limit your contributions?"
        ],
        "evidence_examples": [
            "Letters from government/industry",
            "Evidence of flexibility needed",
            "Urgency documentation",
            "Self-employment plans"
        ],
        "weight": 2.0
    }
]


# =============================================================================
# ELIGIBILITY CHECKER CLASS
# =============================================================================

class EligibilityChecker:
    """
    Checks visa eligibility based on applicant profile
    """

    def __init__(self, aila_search=None):
        """
        Initialize with optional AILA search integration

        Args:
            aila_search: AILASearch instance for enhanced context
        """
        self.aila_search = aila_search

    def check_eb1a(self, profile: Dict) -> EligibilityResult:
        """Check EB-1A eligibility"""
        criteria_results = []
        criteria_met = 0

        for criterion in EB1A_CRITERIA:
            cid = criterion["id"]
            has_evidence = profile.get(cid, False)
            evidence_level = profile.get(f"{cid}_level", "none")

            if has_evidence:
                criteria_met += 1
                met = True
            else:
                met = False

            suggestions = []
            if not met:
                suggestions = [
                    f"Gather evidence for: {criterion['name']}",
                    f"Examples: {', '.join(criterion['evidence_examples'][:2])}"
                ]

            criteria_results.append(CriteriaResult(
                criterion=criterion["name"],
                met=met,
                evidence_level=evidence_level if met else "none",
                notes=criterion["description"],
                suggestions=suggestions
            ))

        # Scoring
        score = min(100, int((criteria_met / 3) * 100))

        if criteria_met >= 4:
            recommendation = "strong"
            rec_text = "Strong candidate. You exceed the minimum criteria threshold."
        elif criteria_met == 3:
            recommendation = "moderate"
            rec_text = "Meets minimum requirements. Consider strengthening additional criteria."
        elif criteria_met == 2:
            recommendation = "weak"
            rec_text = "Borderline. Need to develop at least one more criterion."
        else:
            recommendation = "not_recommended"
            rec_text = "Not recommended. Consider alternative visa categories."

        strengths = [cr.criterion for cr in criteria_results if cr.met]
        weaknesses = [cr.criterion for cr in criteria_results if not cr.met][:4]

        action_items = []
        for cr in criteria_results:
            if not cr.met and cr.suggestions:
                action_items.extend(cr.suggestions[:1])

        alternatives = []
        if criteria_met < 3:
            if profile.get("education_level") in ["masters", "phd"]:
                alternatives.append("EB-2 NIW")
            alternatives.append("O-1A (if can demonstrate short-term extraordinary)")
            alternatives.append("H-1B (if specialty occupation)")

        return EligibilityResult(
            visa_type="EB-1A",
            overall_score=score,
            recommendation=recommendation,
            criteria_met=criteria_met,
            criteria_needed=3,
            criteria_results=criteria_results,
            strengths=strengths,
            weaknesses=weaknesses,
            action_items=action_items[:5],
            alternative_visas=alternatives,
            notes=rec_text
        )

    def check_eb2_niw(self, profile: Dict) -> EligibilityResult:
        """Check EB-2 NIW eligibility"""
        criteria_results = []

        # Check advanced degree requirement
        has_advanced = profile.get("education_level") in ["masters", "phd"]
        has_exceptional = profile.get("exceptional_ability_criteria", 0) >= 3

        if not has_advanced and not has_exceptional:
            return EligibilityResult(
                visa_type="EB-2 NIW",
                overall_score=20,
                recommendation="not_recommended",
                criteria_met=0,
                criteria_needed=3,
                criteria_results=[],
                strengths=[],
                weaknesses=["No advanced degree", "Insufficient exceptional ability evidence"],
                action_items=["Obtain master's degree", "Or demonstrate exceptional ability (3 of 6 criteria)"],
                alternative_visas=["EB-3", "H-1B"],
                notes="EB-2 NIW requires advanced degree or exceptional ability"
            )

        # Check 3 prongs
        prongs_met = 0
        for prong in NIW_PRONGS:
            pid = prong["id"]
            has_evidence = profile.get(pid, False)
            evidence_level = profile.get(f"{pid}_level", "none")

            if has_evidence:
                prongs_met += 1
                met = True
            else:
                met = False

            suggestions = []
            if not met:
                suggestions.append(f"Develop evidence for {prong['name']}")

            criteria_results.append(CriteriaResult(
                criterion=prong["name"],
                met=met,
                evidence_level=evidence_level if met else "none",
                notes=prong["description"],
                suggestions=suggestions
            ))

        # Scoring
        base_score = 40 if has_advanced else 30
        prong_score = (prongs_met / 3) * 60
        score = min(100, int(base_score + prong_score))

        if prongs_met == 3 and has_advanced:
            recommendation = "strong"
            rec_text = "Strong NIW candidate. All prongs satisfied with advanced degree."
        elif prongs_met >= 2:
            recommendation = "moderate"
            rec_text = "Moderate candidate. Work on strengthening remaining prong(s)."
        else:
            recommendation = "weak"
            rec_text = "Weak profile. Need significant evidence development."

        strengths = []
        if has_advanced:
            strengths.append("Advanced degree")
        strengths.extend([cr.criterion for cr in criteria_results if cr.met])

        weaknesses = [cr.criterion for cr in criteria_results if not cr.met]

        action_items = []
        for cr in criteria_results:
            if not cr.met and cr.suggestions:
                action_items.extend(cr.suggestions)

        return EligibilityResult(
            visa_type="EB-2 NIW",
            overall_score=score,
            recommendation=recommendation,
            criteria_met=prongs_met,
            criteria_needed=3,
            criteria_results=criteria_results,
            strengths=strengths,
            weaknesses=weaknesses,
            action_items=action_items[:5],
            alternative_visas=["EB-1A" if prongs_met >= 2 else "EB-3", "O-1A"],
            notes=rec_text
        )

    def check_o1a(self, profile: Dict) -> EligibilityResult:
        """Check O-1A eligibility (uses same criteria as EB-1A)"""
        eb1a_result = self.check_eb1a(profile)

        # O-1 has slightly different threshold and is temporary
        return EligibilityResult(
            visa_type="O-1A",
            overall_score=eb1a_result.overall_score,
            recommendation=eb1a_result.recommendation,
            criteria_met=eb1a_result.criteria_met,
            criteria_needed=3,
            criteria_results=eb1a_result.criteria_results,
            strengths=eb1a_result.strengths,
            weaknesses=eb1a_result.weaknesses,
            action_items=eb1a_result.action_items,
            alternative_visas=["EB-1A (if want permanent)", "H-1B"],
            notes=eb1a_result.notes + " Note: O-1 is a temporary visa (up to 3 years, renewable)."
        )

    def check_h1b(self, profile: Dict) -> EligibilityResult:
        """Check H-1B eligibility"""
        has_degree = profile.get("education_level") in ["bachelors", "masters", "phd"]
        years_exp = profile.get("years_experience", 0)

        # 3 years experience = 1 year of college
        equivalent_years = years_exp // 3
        has_equivalent = equivalent_years >= 4

        if has_degree:
            score = 85
            recommendation = "strong"
            rec_text = "Eligible for H-1B with bachelor's degree or higher."
            strengths = ["Bachelor's degree or higher"]
        elif has_equivalent:
            score = 60
            recommendation = "moderate"
            rec_text = f"May qualify with work experience equivalent ({years_exp} years = {equivalent_years} years college)"
            strengths = [f"{years_exp} years of work experience"]
        else:
            score = 20
            recommendation = "not_recommended"
            rec_text = "Need bachelor's degree or equivalent (12+ years experience)"
            strengths = []

        return EligibilityResult(
            visa_type="H-1B",
            overall_score=score,
            recommendation=recommendation,
            criteria_met=1 if has_degree or has_equivalent else 0,
            criteria_needed=1,
            criteria_results=[
                CriteriaResult(
                    criterion="Specialty Occupation Qualification",
                    met=has_degree or has_equivalent,
                    evidence_level="strong" if has_degree else "moderate",
                    notes="Bachelor's degree or equivalent required",
                    suggestions=[] if has_degree else ["Obtain credential evaluation"]
                )
            ],
            strengths=strengths,
            weaknesses=[] if has_degree else ["No formal degree"],
            action_items=[] if has_degree else ["Get credential evaluation for work experience"],
            alternative_visas=["TN (if Canadian/Mexican)", "L-1 (if intracompany)"],
            notes=rec_text
        )

    def check_eligibility(self, visa_type: str, profile: Dict) -> EligibilityResult:
        """
        Main entry point - check eligibility for any visa type

        Args:
            visa_type: Type of visa to check
            profile: Dictionary with applicant information

        Returns:
            EligibilityResult with full assessment
        """
        visa_upper = visa_type.upper().replace("_", " ").replace("-", " ")

        if "EB1A" in visa_upper or "EB-1A" in visa_type:
            return self.check_eb1a(profile)
        elif "NIW" in visa_upper or "EB2" in visa_upper:
            return self.check_eb2_niw(profile)
        elif "O1" in visa_upper or "O-1" in visa_type:
            return self.check_o1a(profile)
        elif "H1B" in visa_upper or "H-1B" in visa_type:
            return self.check_h1b(profile)
        else:
            raise ValueError(f"Unsupported visa type: {visa_type}")

    def get_quick_assessment(self, profile: Dict) -> Dict[str, Dict]:
        """
        Quick assessment across multiple visa types

        Returns:
            Dictionary mapping visa types to scores and recommendations
        """
        results = {}

        for visa_type in ["EB-1A", "EB-2 NIW", "O-1A", "H-1B"]:
            try:
                result = self.check_eligibility(visa_type, profile)
                results[visa_type] = {
                    "score": result.overall_score,
                    "recommendation": result.recommendation,
                    "criteria_met": result.criteria_met,
                    "criteria_needed": result.criteria_needed,
                    "summary": result.notes
                }
            except Exception as e:
                results[visa_type] = {
                    "score": 0,
                    "recommendation": "error",
                    "error": str(e)
                }

        # Sort by score descending
        sorted_results = dict(sorted(
            results.items(),
            key=lambda x: x[1].get("score", 0),
            reverse=True
        ))

        return sorted_results

    def to_json(self, result: EligibilityResult) -> str:
        """Convert result to JSON string"""
        return json.dumps({
            "visa_type": result.visa_type,
            "overall_score": result.overall_score,
            "recommendation": result.recommendation,
            "criteria_met": result.criteria_met,
            "criteria_needed": result.criteria_needed,
            "criteria_results": [
                {
                    "criterion": cr.criterion,
                    "met": cr.met,
                    "evidence_level": cr.evidence_level,
                    "notes": cr.notes,
                    "suggestions": cr.suggestions
                }
                for cr in result.criteria_results
            ],
            "strengths": result.strengths,
            "weaknesses": result.weaknesses,
            "action_items": result.action_items,
            "alternative_visas": result.alternative_visas,
            "notes": result.notes
        }, indent=2)


# =============================================================================
# STANDALONE USAGE
# =============================================================================

if __name__ == "__main__":
    # Example usage
    checker = EligibilityChecker()

    sample_profile = {
        "education_level": "phd",
        "years_experience": 8,
        "awards": True,
        "awards_level": "moderate",
        "publications": True,
        "publications_level": "strong",
        "citations": True,
        "citations_level": "strong",
        "original_contributions": True,
        "original_contributions_level": "moderate",
        "judging": False,
        "memberships": False,
        "high_salary": True,
        "high_salary_level": "moderate",
        "prong1": True,
        "prong1_level": "strong",
        "prong2": True,
        "prong2_level": "strong",
        "prong3": True,
        "prong3_level": "moderate"
    }

    print("=== Quick Assessment ===")
    quick = checker.get_quick_assessment(sample_profile)
    for visa, assessment in quick.items():
        print(f"\n{visa}: Score {assessment['score']}/100 - {assessment['recommendation']}")
        print(f"  {assessment.get('summary', '')}")

    print("\n=== Detailed EB-1A Assessment ===")
    result = checker.check_eb1a(sample_profile)
    print(checker.to_json(result))
