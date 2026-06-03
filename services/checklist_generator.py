"""
CaseHub - Document Checklist Generator Service
Generates visa-specific document checklists and cross-references with uploaded documents.

Supports: EB-1A, EB-2 NIW, O-1A
"""
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


# ============================================================
# VISA REQUIREMENTS DEFINITIONS
# ============================================================

EXHIBIT_NAMES = {
    "A": "Forms",
    "B": "Brief (Cover Letter, TOC, Personal Statement)",
    "C": "Self-Petitioner Information",
    "D": "Critical Role / Letters of Recommendation",
    "E": "High Salary / Financial Evidence",
    "F": "Memberships",
    "G": "Judging Work of Others",
    "H": "Awards & Acknowledgements",
    "I": "Recognition / Published Material About You",
    "J": "Job Offers",
    "K": "Media Coverage",
    "L": "Original Contributions / Publications",
    "M": "Supporting Research"
}

VISA_REQUIREMENTS = {
    "EB-1A": {
        "label": "EB-1A Extraordinary Ability",
        "description": "Must meet at least 3 of 10 criteria (8 CFR 204.5(h)(3))",
        "required": [
            {"type": "Passport", "exhibit": "C", "label": "Passport (valid, bio page scan)"},
            {"type": "I-94 Travel Record", "exhibit": "C", "label": "I-94 Arrival/Departure Record"},
            {"type": "Visa", "exhibit": "C", "label": "Current Visa (if applicable)"},
            {"type": "Diploma", "exhibit": "C", "label": "Highest Degree Diploma"},
            {"type": "Academic Transcript", "exhibit": "C", "label": "Academic Transcripts"},
            {"type": "Employment Letter", "exhibit": "C", "label": "Current Employment Verification Letter"},
            {"type": "USCIS Form", "exhibit": "A", "label": "Form I-140"},
            {"type": "USCIS Form", "exhibit": "A", "label": "Form G-1145 (e-Notification)"},
        ],
        "criteria_based": [
            {
                "criterion": "awards",
                "label": "National/International Awards",
                "exhibit": "H",
                "docs": [
                    {"label": "Award certificates/trophies", "type": "Evidence"},
                    {"label": "News articles about the award", "type": "Evidence"},
                    {"label": "Selection criteria documentation", "type": "Evidence"},
                    {"label": "List of past recipients", "type": "Evidence"},
                ]
            },
            {
                "criterion": "memberships",
                "label": "Exclusive Memberships",
                "exhibit": "F",
                "docs": [
                    {"label": "Membership certificates", "type": "Evidence"},
                    {"label": "Membership requirements documentation", "type": "Evidence"},
                    {"label": "Evidence of selective admission", "type": "Evidence"},
                ]
            },
            {
                "criterion": "published_material",
                "label": "Published Material About You",
                "exhibit": "I",
                "docs": [
                    {"label": "News/magazine articles about you", "type": "Evidence"},
                    {"label": "Interview transcripts/recordings", "type": "Evidence"},
                    {"label": "Professional journal articles about your work", "type": "Evidence"},
                ]
            },
            {
                "criterion": "judging",
                "label": "Judging Work of Others",
                "exhibit": "G",
                "docs": [
                    {"label": "Reviewer invitations/confirmations", "type": "Evidence"},
                    {"label": "Editorial board appointment letters", "type": "Evidence"},
                    {"label": "Grant panel appointment letters", "type": "Evidence"},
                ]
            },
            {
                "criterion": "original_contributions",
                "label": "Original Contributions of Major Significance",
                "exhibit": "L",
                "docs": [
                    {"label": "Patents (granted or pending)", "type": "Evidence"},
                    {"label": "Expert testimonial letters", "type": "Letter of Recommendation"},
                    {"label": "Citation evidence (Google Scholar, etc.)", "type": "Evidence"},
                    {"label": "Implementation/adoption evidence", "type": "Evidence"},
                ]
            },
            {
                "criterion": "scholarly_articles",
                "label": "Scholarly Articles in Professional Journals",
                "exhibit": "L",
                "docs": [
                    {"label": "Published articles (PDFs)", "type": "Evidence"},
                    {"label": "Citation reports", "type": "Evidence"},
                    {"label": "Journal impact factor evidence", "type": "Evidence"},
                ]
            },
            {
                "criterion": "exhibitions",
                "label": "Artistic Exhibitions/Showcases",
                "exhibit": "H",
                "docs": [
                    {"label": "Exhibition catalogs", "type": "Evidence"},
                    {"label": "Gallery statements", "type": "Evidence"},
                    {"label": "Reviews of exhibited work", "type": "Evidence"},
                ]
            },
            {
                "criterion": "leading_role",
                "label": "Leading/Critical Role in Distinguished Orgs",
                "exhibit": "D",
                "docs": [
                    {"label": "Organizational charts", "type": "Evidence"},
                    {"label": "Title/position documentation", "type": "Evidence"},
                    {"label": "Scope of responsibility letters", "type": "Evidence"},
                ]
            },
            {
                "criterion": "high_salary",
                "label": "High Salary/Remuneration",
                "exhibit": "E",
                "docs": [
                    {"label": "Pay stubs (recent 3 months)", "type": "Pay Stub"},
                    {"label": "Offer letter with salary", "type": "Employment Letter"},
                    {"label": "Industry salary surveys (BLS, etc.)", "type": "Evidence"},
                    {"label": "Comparative salary analysis", "type": "Evidence"},
                ]
            },
            {
                "criterion": "commercial_success",
                "label": "Commercial Success in Performing Arts",
                "exhibit": "E",
                "docs": [
                    {"label": "Sales/revenue figures", "type": "Evidence"},
                    {"label": "Box office records", "type": "Evidence"},
                    {"label": "Chart positions/streaming numbers", "type": "Evidence"},
                ]
            },
        ],
        "always_recommended": [
            {"type": "Letter of Recommendation", "exhibit": "D", "label": "Letters of Recommendation (5-6 minimum)", "min_count": 5},
            {"type": "Birth Certificate", "exhibit": "C", "label": "Birth Certificate (translated if needed)"},
            {"type": "Evidence", "exhibit": "C", "label": "CV/Resume (comprehensive)"},
        ]
    },

    "EB-2 NIW": {
        "label": "EB-2 National Interest Waiver",
        "description": "Matter of Dhanasar framework - 3 prongs",
        "required": [
            {"type": "Passport", "exhibit": "C", "label": "Passport (valid, bio page scan)"},
            {"type": "I-94 Travel Record", "exhibit": "C", "label": "I-94 Arrival/Departure Record"},
            {"type": "Visa", "exhibit": "C", "label": "Current Visa (if applicable)"},
            {"type": "Diploma", "exhibit": "C", "label": "Advanced Degree (Master's/PhD)"},
            {"type": "Academic Transcript", "exhibit": "C", "label": "Academic Transcripts"},
            {"type": "Employment Letter", "exhibit": "C", "label": "Employment Verification Letter"},
            {"type": "USCIS Form", "exhibit": "A", "label": "Form I-140"},
            {"type": "USCIS Form", "exhibit": "A", "label": "Form ETA-9089"},
            {"type": "USCIS Form", "exhibit": "A", "label": "Form G-1145 (e-Notification)"},
        ],
        "prong_based": [
            {
                "prong": "prong1",
                "label": "Prong 1: Substantial Merit & National Importance",
                "docs": [
                    {"label": "Personal Statement", "type": "Evidence", "exhibit": "B"},
                    {"label": "Government statistics (field importance)", "type": "Evidence", "exhibit": "L"},
                    {"label": "Executive orders/policy documents", "type": "Evidence", "exhibit": "L"},
                    {"label": "Industry reports", "type": "Evidence", "exhibit": "L"},
                ]
            },
            {
                "prong": "prong2",
                "label": "Prong 2: Well Positioned to Advance the Endeavor",
                "docs": [
                    {"label": "CV/Resume (comprehensive)", "type": "Evidence", "exhibit": "C"},
                    {"label": "Publications list with citations", "type": "Evidence", "exhibit": "L"},
                    {"label": "Citation evidence (Google Scholar)", "type": "Evidence", "exhibit": "L"},
                    {"label": "Patents (granted or pending)", "type": "Evidence", "exhibit": "L"},
                    {"label": "Professional certifications/licenses", "type": "Evidence", "exhibit": "C"},
                ]
            },
            {
                "prong": "prong3",
                "label": "Prong 3: On Balance, Beneficial to Waive Requirements",
                "docs": [
                    {"label": "Employment history documentation", "type": "Employment Letter", "exhibit": "C"},
                    {"label": "Future work plan in the US", "type": "Evidence", "exhibit": "B"},
                    {"label": "Evidence of US benefit/impact", "type": "Evidence", "exhibit": "L"},
                ]
            },
        ],
        "always_recommended": [
            {"type": "Letter of Recommendation", "exhibit": "D", "label": "Expert Letters (5-6 minimum)", "min_count": 5},
            {"type": "Birth Certificate", "exhibit": "C", "label": "Birth Certificate (translated if needed)"},
            {"type": "Tax Return", "exhibit": "E", "label": "Tax Returns (last 3 years)", "min_count": 3},
            {"type": "Evidence", "exhibit": "C", "label": "CV/Resume (comprehensive)"},
        ]
    },

    "O-1A": {
        "label": "O-1A Extraordinary Ability",
        "description": "Must meet at least 3 of 8 criteria",
        "required": [
            {"type": "Passport", "exhibit": "C", "label": "Passport (valid, bio page scan)"},
            {"type": "I-94 Travel Record", "exhibit": "C", "label": "I-94 Arrival/Departure Record"},
            {"type": "USCIS Form", "exhibit": "A", "label": "Form I-129"},
            {"type": "USCIS Form", "exhibit": "A", "label": "Form I-129 Supplement O"},
            {"type": "Employment Letter", "exhibit": "C", "label": "Offer Letter/Contract from US Employer"},
            {"type": "Diploma", "exhibit": "C", "label": "Degree Documentation"},
        ],
        "criteria_based": [
            {
                "criterion": "awards",
                "label": "National/International Awards",
                "exhibit": "H",
                "docs": [
                    {"label": "Award certificates", "type": "Evidence"},
                    {"label": "News about awards", "type": "Evidence"},
                ]
            },
            {
                "criterion": "memberships",
                "label": "Exclusive Memberships",
                "exhibit": "F",
                "docs": [
                    {"label": "Membership certificates", "type": "Evidence"},
                    {"label": "Requirements documentation", "type": "Evidence"},
                ]
            },
            {
                "criterion": "published_material",
                "label": "Published Material About You",
                "exhibit": "I",
                "docs": [
                    {"label": "Media coverage", "type": "Evidence"},
                    {"label": "Interviews", "type": "Evidence"},
                ]
            },
            {
                "criterion": "judging",
                "label": "Judging Work of Others",
                "exhibit": "G",
                "docs": [
                    {"label": "Peer review evidence", "type": "Evidence"},
                    {"label": "Editorial/panel roles", "type": "Evidence"},
                ]
            },
            {
                "criterion": "original_contributions",
                "label": "Original Contributions",
                "exhibit": "L",
                "docs": [
                    {"label": "Patents", "type": "Evidence"},
                    {"label": "Impact/adoption evidence", "type": "Evidence"},
                ]
            },
            {
                "criterion": "scholarly_articles",
                "label": "Scholarly Articles",
                "exhibit": "L",
                "docs": [
                    {"label": "Publications", "type": "Evidence"},
                    {"label": "Citation reports", "type": "Evidence"},
                ]
            },
            {
                "criterion": "leading_role",
                "label": "Leading/Critical Role",
                "exhibit": "D",
                "docs": [
                    {"label": "Leadership evidence", "type": "Evidence"},
                    {"label": "Org charts", "type": "Evidence"},
                ]
            },
            {
                "criterion": "high_salary",
                "label": "High Salary/Remuneration",
                "exhibit": "E",
                "docs": [
                    {"label": "Compensation evidence", "type": "Pay Stub"},
                    {"label": "Salary comparison data", "type": "Evidence"},
                ]
            },
        ],
        "always_recommended": [
            {"type": "Letter of Recommendation", "exhibit": "D", "label": "Advisory Opinion / Expert Letters (4-5)", "min_count": 4},
            {"type": "Evidence", "exhibit": "C", "label": "CV/Resume (comprehensive)"},
            {"type": "Evidence", "exhibit": "C", "label": "Itinerary/work plan"},
        ]
    }
}

# Aliases for common visa_type values in the database
VISA_TYPE_ALIASES = {
    "eb-1a": "EB-1A", "eb1a": "EB-1A", "eb-1 a": "EB-1A",
    "eb-2 niw": "EB-2 NIW", "eb2niw": "EB-2 NIW", "eb-2niw": "EB-2 NIW",
    "niw": "EB-2 NIW", "eb2 niw": "EB-2 NIW",
    "o-1a": "O-1A", "o1a": "O-1A", "o-1 a": "O-1A",
}


@dataclass
class ChecklistItem:
    label: str
    doc_type: str
    exhibit: str
    status: str  # present, missing, needs_review, insufficient
    required: bool = True
    min_count: int = 1
    current_count: int = 0
    matched_documents: list = field(default_factory=list)
    section: str = ""  # "required", "criteria:awards", "prong:prong1", "recommended"
    criterion_label: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class ExhibitSection:
    letter: str
    name: str
    items: List[ChecklistItem] = field(default_factory=list)
    present_count: int = 0
    total_count: int = 0

    def to_dict(self):
        return {
            "letter": self.letter,
            "name": self.name,
            "items": [i.to_dict() for i in self.items],
            "present_count": self.present_count,
            "total_count": self.total_count
        }


@dataclass
class ChecklistResult:
    case_id: int
    visa_type: str
    visa_label: str
    visa_description: str
    exhibits: Dict[str, ExhibitSection] = field(default_factory=dict)
    total_present: int = 0
    total_required: int = 0
    progress_percent: int = 0
    unmatched_documents: list = field(default_factory=list)

    def to_dict(self):
        return {
            "case_id": self.case_id,
            "visa_type": self.visa_type,
            "visa_label": self.visa_label,
            "visa_description": self.visa_description,
            "exhibits": {k: v.to_dict() for k, v in self.exhibits.items()},
            "total_present": self.total_present,
            "total_required": self.total_required,
            "progress_percent": self.progress_percent,
            "unmatched_documents": self.unmatched_documents
        }


def normalize_visa_type(visa_type: str) -> Optional[str]:
    """Normalize visa type string to match VISA_REQUIREMENTS keys."""
    if not visa_type:
        return None
    vt = visa_type.strip()
    if vt in VISA_REQUIREMENTS:
        return vt
    alias = VISA_TYPE_ALIASES.get(vt.lower())
    if alias:
        return alias
    # Fuzzy fallback: check if visa_type starts with a known key
    vt_lower = vt.lower()
    for key, canonical in VISA_TYPE_ALIASES.items():
        if vt_lower.startswith(key):
            return canonical
    return None


def generate_checklist(case_id: int, visa_type: str, documents: list) -> ChecklistResult:
    """
    Generate a document checklist for a case.

    Args:
        case_id: The case ID
        visa_type: Normalized visa type (e.g., "EB-1A")
        documents: List of Document model objects from the database

    Returns:
        ChecklistResult with all exhibits and items
    """
    requirements = VISA_REQUIREMENTS.get(visa_type)
    if not requirements:
        return ChecklistResult(
            case_id=case_id,
            visa_type=visa_type or "Unknown",
            visa_label="Unknown Visa Type",
            visa_description="No checklist template available for this visa type.",
            total_present=0,
            total_required=0,
            progress_percent=0
        )

    result = ChecklistResult(
        case_id=case_id,
        visa_type=visa_type,
        visa_label=requirements["label"],
        visa_description=requirements["description"]
    )

    # Initialize exhibit sections
    for letter, name in EXHIBIT_NAMES.items():
        result.exhibits[letter] = ExhibitSection(letter=letter, name=name)

    # Build a lookup of documents by type
    docs_by_type: Dict[str, list] = {}
    all_doc_ids_matched = set()

    for doc in documents:
        dt = doc.doc_type or "Other Document"
        if dt not in docs_by_type:
            docs_by_type[dt] = []
        docs_by_type[dt].append({
            "id": doc.id,
            "name": doc.name,
            "doc_type": dt,
            "status": doc.status,
            "created_at": doc.created_at.strftime("%Y-%m-%d") if doc.created_at else "",
            "llm_classified": doc.llm_classified or False,
            "suggested_exhibit": doc.suggested_exhibit
        })

    def _match_docs(doc_type: str, count_needed: int = 1) -> tuple:
        """Match uploaded documents against a requirement. Returns (matched_list, status)."""
        available = docs_by_type.get(doc_type, [])
        # Filter out already matched
        unmatched = [d for d in available if d["id"] not in all_doc_ids_matched]

        matched = unmatched[:count_needed]
        for m in matched:
            all_doc_ids_matched.add(m["id"])

        total_available = len(available)
        if total_available >= count_needed:
            if any(d.get("llm_classified") and not d.get("status") == "reviewed" for d in matched):
                return matched, "needs_review"
            return matched, "present"
        elif total_available > 0:
            return matched, "insufficient"
        return [], "missing"

    # Process REQUIRED documents
    for req in requirements.get("required", []):
        matched, status = _match_docs(req["type"])
        exhibit_letter = req.get("exhibit", "C")

        item = ChecklistItem(
            label=req["label"],
            doc_type=req["type"],
            exhibit=exhibit_letter,
            status=status,
            required=True,
            section="required",
            matched_documents=matched,
            current_count=len(matched)
        )
        result.exhibits[exhibit_letter].items.append(item)

    # Process CRITERIA-BASED documents (EB-1A, O-1A)
    for criterion in requirements.get("criteria_based", []):
        exhibit_letter = criterion.get("exhibit", "L")
        for doc_req in criterion.get("docs", []):
            doc_type = doc_req.get("type", "Evidence")
            matched, status = _match_docs(doc_type)
            target_exhibit = doc_req.get("exhibit", exhibit_letter)

            item = ChecklistItem(
                label=doc_req["label"],
                doc_type=doc_type,
                exhibit=target_exhibit,
                status=status,
                required=False,
                section=f"criteria:{criterion['criterion']}",
                criterion_label=criterion["label"],
                matched_documents=matched,
                current_count=len(matched)
            )
            result.exhibits[target_exhibit].items.append(item)

    # Process PRONG-BASED documents (EB-2 NIW)
    for prong in requirements.get("prong_based", []):
        for doc_req in prong.get("docs", []):
            doc_type = doc_req.get("type", "Evidence")
            exhibit_letter = doc_req.get("exhibit", "L")
            matched, status = _match_docs(doc_type)

            item = ChecklistItem(
                label=doc_req["label"],
                doc_type=doc_type,
                exhibit=exhibit_letter,
                status=status,
                required=False,
                section=f"prong:{prong['prong']}",
                criterion_label=prong["label"],
                matched_documents=matched,
                current_count=len(matched)
            )
            result.exhibits[exhibit_letter].items.append(item)

    # Process ALWAYS RECOMMENDED
    for rec in requirements.get("always_recommended", []):
        min_count = rec.get("min_count", 1)
        available = docs_by_type.get(rec["type"], [])
        total_available = len(available)
        matched = [d for d in available if d["id"] not in all_doc_ids_matched][:min_count]
        for m in matched:
            all_doc_ids_matched.add(m["id"])

        if total_available >= min_count:
            status = "present"
        elif total_available > 0:
            status = "insufficient"
        else:
            status = "missing"

        exhibit_letter = rec.get("exhibit", "D")
        item = ChecklistItem(
            label=rec["label"],
            doc_type=rec["type"],
            exhibit=exhibit_letter,
            status=status,
            required=True,
            min_count=min_count,
            current_count=total_available,
            section="recommended",
            matched_documents=matched
        )
        result.exhibits[exhibit_letter].items.append(item)

    # Calculate totals per exhibit
    for exhibit in result.exhibits.values():
        exhibit.total_count = len(exhibit.items)
        exhibit.present_count = sum(1 for i in exhibit.items if i.status in ("present", "needs_review"))

    # Calculate overall progress
    all_items = []
    for exhibit in result.exhibits.values():
        all_items.extend(exhibit.items)

    result.total_required = len(all_items)
    result.total_present = sum(1 for i in all_items if i.status in ("present", "needs_review"))
    result.progress_percent = int((result.total_present / result.total_required * 100)) if result.total_required > 0 else 0

    # Find unmatched documents (uploaded but not mapped to any requirement)
    for doc in documents:
        if doc.id not in all_doc_ids_matched:
            result.unmatched_documents.append({
                "id": doc.id,
                "name": doc.name,
                "doc_type": doc.doc_type or "Other Document",
                "created_at": doc.created_at.strftime("%Y-%m-%d") if doc.created_at else "",
                "suggested_exhibit": doc.suggested_exhibit
            })

    return result


def get_supported_visa_types() -> List[Dict[str, str]]:
    """Return list of supported visa types with labels."""
    return [
        {"key": k, "label": v["label"], "description": v["description"]}
        for k, v in VISA_REQUIREMENTS.items()
    ]
