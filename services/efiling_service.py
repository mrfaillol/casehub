"""
CaseHub - E-Filing Service
Manage e-filing submissions to USCIS.
"""
import os
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from enum import Enum
from config import settings


class EFilingStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    QUEUED = "queued"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ERROR = "error"


class EFilingService:
    """Service for managing e-filing submissions."""

    # USCIS Service Centers
    SERVICE_CENTERS = {
        "NSC": {
            "name": "Nebraska Service Center",
            "address": "P.O. Box 87140, Lincoln, NE 68501",
            "forms": ["I-129", "I-140", "I-765", "I-539"]
        },
        "TSC": {
            "name": "Texas Service Center",
            "address": "P.O. Box 852135, Mesquite, TX 75185",
            "forms": ["I-129", "I-140", "I-130", "I-765"]
        },
        "VSC": {
            "name": "Vermont Service Center",
            "address": "75 Lower Welden Street, St. Albans, VT 05479",
            "forms": ["I-130", "I-485", "I-751"]
        },
        "CSC": {
            "name": "California Service Center",
            "address": "P.O. Box 10140, Laguna Niguel, CA 92607",
            "forms": ["I-129", "I-130", "I-140"]
        },
        "POTOMAC": {
            "name": "Potomac Service Center",
            "address": "P.O. Box 3000, Carrboro, NC 27510",
            "forms": ["N-400", "I-90", "I-131"]
        }
    }

    # Filing types
    FILING_TYPES = {
        "initial": "Initial Filing",
        "extension": "Extension",
        "amendment": "Amendment",
        "rfe_response": "RFE Response",
        "appeal": "Appeal"
    }

    # Payment methods
    PAYMENT_METHODS = {
        "credit_card": "Credit Card",
        "check": "Check/Money Order",
        "ach": "ACH Transfer",
        "pay_gov": "Pay.gov"
    }

    def create_submission(
        self,
        case_id: int,
        form_number: str,
        filing_type: str = "initial",
        service_center: str = None,
        documents: List[dict] = None,
        notes: str = None
    ) -> dict:
        """Create a new e-filing submission record.

        Args:
            case_id: ID of the case
            form_number: USCIS form number
            filing_type: Type of filing
            service_center: Target service center
            documents: List of documents to include
            notes: Any notes

        Returns:
            Dictionary with submission info
        """
        submission_id = str(uuid.uuid4())[:12].upper()

        return {
            "submission_id": submission_id,
            "case_id": case_id,
            "form_number": form_number.upper(),
            "filing_type": filing_type,
            "service_center": service_center,
            "status": EFilingStatus.DRAFT,
            "documents": documents or [],
            "notes": notes,
            "created_at": datetime.now().isoformat(),
            "estimated_submission_date": None,
            "receipt_number": None,
            "confirmation_number": None
        }

    def validate_submission(self, submission: dict) -> dict:
        """Validate a submission is ready for filing.

        Args:
            submission: Submission dictionary

        Returns:
            Dictionary with validation result and any errors
        """
        errors = []
        warnings = []

        # Check required fields
        if not submission.get("form_number"):
            errors.append("Form number is required")

        if not submission.get("case_id"):
            errors.append("Case is required")

        # Check documents
        documents = submission.get("documents", [])
        if not documents:
            warnings.append("No documents attached")

        # Check service center
        if not submission.get("service_center"):
            warnings.append("Service center not specified")

        # Check for required documents based on form
        form_number = submission.get("form_number", "").upper()
        required_docs = self._get_required_documents(form_number)
        attached_types = [d.get("type") for d in documents]

        for req in required_docs:
            if req not in attached_types:
                errors.append(f"Missing required document: {req}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "ready_to_submit": len(errors) == 0
        }

    def _get_required_documents(self, form_number: str) -> List[str]:
        """Get required documents for a form."""
        required = {
            "I-140": ["petition_letter", "evidence_of_ability"],
            "I-129": ["lca", "petition_letter"],
            "I-485": ["passport", "photos", "birth_certificate", "medical_exam"],
            "I-130": ["proof_of_relationship", "petitioner_status"],
            "I-765": ["passport", "photos", "i94"],
            "N-400": ["passport", "photos", "green_card"]
        }
        return required.get(form_number, [])

    def get_service_centers(self) -> Dict[str, dict]:
        """Get all USCIS service centers."""
        return self.SERVICE_CENTERS

    def get_service_center_for_form(self, form_number: str) -> List[dict]:
        """Get service centers that accept a specific form."""
        result = []
        for code, center in self.SERVICE_CENTERS.items():
            if form_number.upper() in center.get("forms", []):
                result.append({"code": code, **center})
        return result

    def get_filing_types(self) -> Dict[str, str]:
        """Get available filing types."""
        return self.FILING_TYPES

    def calculate_fees(
        self,
        form_number: str,
        premium_processing: bool = False,
        biometric_required: bool = False
    ) -> dict:
        """Calculate filing fees."""
        # Base fees (2024 rates)
        fees = {
            "I-129": {"base": 460, "premium": 2805},
            "I-140": {"base": 700, "premium": 2805},
            "I-485": {"base": 1225, "premium": 0},
            "I-130": {"base": 625, "premium": 0},
            "I-765": {"base": 410, "premium": 0},
            "I-131": {"base": 630, "premium": 0},
            "I-539": {"base": 370, "premium": 1965},
            "N-400": {"base": 760, "premium": 0},
            "I-751": {"base": 750, "premium": 0}
        }

        form_fees = fees.get(form_number.upper(), {"base": 0, "premium": 0})
        biometric_fee = 85 if biometric_required else 0

        total = form_fees["base"]
        if premium_processing and form_fees["premium"] > 0:
            total += form_fees["premium"]
        total += biometric_fee

        return {
            "base_fee": form_fees["base"],
            "premium_fee": form_fees["premium"] if premium_processing else 0,
            "biometric_fee": biometric_fee,
            "total": total,
            "premium_available": form_fees["premium"] > 0
        }

    def get_estimated_processing_time(self, form_number: str, service_center: str = None) -> dict:
        """Get estimated processing times."""
        # Average processing times (in months)
        times = {
            "I-129": {"min": 2, "max": 6, "premium": 0.5},
            "I-140": {"min": 6, "max": 12, "premium": 0.5},
            "I-485": {"min": 12, "max": 36, "premium": None},
            "I-130": {"min": 12, "max": 24, "premium": None},
            "I-765": {"min": 3, "max": 6, "premium": None},
            "I-131": {"min": 3, "max": 6, "premium": None},
            "N-400": {"min": 8, "max": 14, "premium": None}
        }

        form_times = times.get(form_number.upper(), {"min": 6, "max": 12, "premium": None})

        return {
            "standard_min_months": form_times["min"],
            "standard_max_months": form_times["max"],
            "premium_days": int(form_times["premium"] * 30) if form_times["premium"] else None,
            "estimated_completion_min": (datetime.now() + timedelta(days=form_times["min"]*30)).strftime("%Y-%m-%d"),
            "estimated_completion_max": (datetime.now() + timedelta(days=form_times["max"]*30)).strftime("%Y-%m-%d")
        }

    def generate_cover_letter(self, submission: dict, case_data: dict, client_data: dict) -> str:
        """Generate a cover letter for the submission."""
        today = datetime.now().strftime("%B %d, %Y")

        letter = f"""
{settings.ORG_NAME}
Email: {settings.ORG_EMAIL}

{today}

U.S. Citizenship and Immigration Services
{self.SERVICE_CENTERS.get(submission.get('service_center', 'NSC'), {}).get('address', '')}

RE: {submission.get('form_number')} - {submission.get('filing_type', 'Initial Filing').title()}
    Petitioner: {case_data.get('employer_name', 'N/A')}
    Beneficiary: {client_data.get('first_name', '')} {client_data.get('last_name', '')}
    Case Number: {case_data.get('case_number', 'N/A')}

Dear USCIS Officer:

Please find enclosed the {submission.get('form_number')} petition and supporting documents
for the above-referenced beneficiary.

ENCLOSED DOCUMENTS:
"""

        for i, doc in enumerate(submission.get('documents', []), 1):
            letter += f"\n{i}. {doc.get('name', 'Document')}"

        letter += """

Please contact our office if you require any additional information.

Respectfully submitted,

_________________________
Immigration Law Center
Authorized Representative
"""
        return letter


# SQL for e-filing tables
CREATE_EFILING_TABLE = """
CREATE TABLE IF NOT EXISTS efiling_submissions (
    id SERIAL PRIMARY KEY,
    submission_id VARCHAR(20) UNIQUE NOT NULL,
    case_id INTEGER REFERENCES cases(id),
    form_number VARCHAR(20) NOT NULL,
    filing_type VARCHAR(50) DEFAULT 'initial',
    service_center VARCHAR(20),
    status VARCHAR(50) DEFAULT 'draft',
    documents JSONB,
    fees JSONB,
    payment_method VARCHAR(50),
    payment_confirmed BOOLEAN DEFAULT false,
    receipt_number VARCHAR(50),
    confirmation_number VARCHAR(50),
    submitted_at TIMESTAMP,
    accepted_at TIMESTAMP,
    notes TEXT,
    cover_letter TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by INTEGER REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_efiling_case ON efiling_submissions(case_id);
CREATE INDEX IF NOT EXISTS idx_efiling_status ON efiling_submissions(status);
CREATE INDEX IF NOT EXISTS idx_efiling_submission_id ON efiling_submissions(submission_id);

CREATE TABLE IF NOT EXISTS efiling_history (
    id SERIAL PRIMARY KEY,
    submission_id INTEGER REFERENCES efiling_submissions(id) ON DELETE CASCADE,
    action VARCHAR(100) NOT NULL,
    old_status VARCHAR(50),
    new_status VARCHAR(50),
    details TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    created_by INTEGER REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_efiling_history_submission ON efiling_history(submission_id);
"""


# Singleton instance
efiling_service = EFilingService()
