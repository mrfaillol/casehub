from datetime import datetime, timedelta
import uuid
import json
from typing import List, Optional, Dict
from enum import Enum
from config import settings

class ItemStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"

class PackageStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    ACTIVE = "active"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ARCHIVED = "archived"

class ItemType(str, Enum):
    QUESTIONNAIRE = "questionnaire"
    DOCUMENT_REQUEST = "document_request"
    SIGNATURE = "signature"

class IntakeService:
    """Service for managing intake packages and forms.

    TEMPLATE_IDS: Maps form identifiers to DB questionnaire_template IDs.
    Run add_intake_templates.py on VPS to create new templates and get their IDs.
    Update this dict after running the migration script.
    """

    # Questionnaire template IDs from VPS database.
    # Updated 2026-03-03 after running scripts/add_intake_templates.py
    TEMPLATE_IDS = {
        "AR-11": 2,
        "G-639": 3,
        "I-90": 4,
        "I-129": 5,
        "I-130": 38,      # "Form I-130" (expanded version)
        "I-131": 43,      # "Form I-131" (expanded version)
        "I-539": 8,
        "I-589": 9,
        "I-765": 42,      # "Form I-765" (expanded version)
        "I-821": 11,
        "I-821D": 12,
        "I-907": 13,
        "N-336": 14,
        "N-400": 53,      # "Form N-400" (expanded version)
        "N-565": 16,
        "I-140": 19,
        "I-485": 40,      # "Form I-485" (expanded version)
        "I-864": 41,      # "Form I-864" (expanded version)
        "G-28": 52,       # G-28 Attorney Authorization
        "COMMON-INFO": 59, # Client Personal Information (dedup)
        "I-140-specific": 60,
        "I-907-specific": 61,
        "I-485-specific": 62,
        "I-765-specific": 63,
        "I-131-specific": 64,
    }

    PACKAGE_TEMPLATES = {
        "EB-1A": {
            "name": "EB-1A Extraordinary Ability",
            "items": [
                {"type": "questionnaire", "name": "Personal Information", "required": True, "questionnaire_id": "COMMON-INFO", "is_common": True},
                {"type": "questionnaire", "name": "G-28 - Attorney Authorization", "required": True, "questionnaire_id": "G-28"},
                {"type": "questionnaire", "name": "I-140 - Petition Details", "required": True, "questionnaire_id": "I-140-specific"},
                {"type": "questionnaire", "name": "I-907 - Premium Processing", "required": False, "questionnaire_id": "I-907-specific"},
                {"type": "document_request", "name": "Passport Bio Page", "required": True},
            ]
        },
        "EB-2 NIW": {
            "name": "EB-2 NIW National Interest Waiver",
            "items": [
                {"type": "questionnaire", "name": "Personal Information", "required": True, "questionnaire_id": "COMMON-INFO", "is_common": True},
                {"type": "questionnaire", "name": "G-28 - Attorney Authorization", "required": True, "questionnaire_id": "G-28"},
                {"type": "questionnaire", "name": "I-140 - Petition Details", "required": True, "questionnaire_id": "I-140-specific"},
                {"type": "questionnaire", "name": "I-907 - Premium Processing", "required": False, "questionnaire_id": "I-907-specific"},
                {"type": "document_request", "name": "Advanced Degree/Diplomas", "required": True},
                {"type": "document_request", "name": "Passport Bio Page", "required": True},
            ]
        },
        "Family-Based": {
            "name": "Family-Based Immigration Intake",
            "items": [
                {"type": "questionnaire", "name": "Personal Information", "required": True, "questionnaire_id": "COMMON-INFO", "is_common": True},
                {"type": "questionnaire", "name": "G-28 - Attorney Authorization", "required": True, "questionnaire_id": "G-28"},
                {"type": "questionnaire", "name": "I-130 - Petition for Alien Relative", "required": True, "questionnaire_id": "I-130"},
                {"type": "questionnaire", "name": "I-485 - Adjustment of Status", "required": True, "questionnaire_id": "I-485-specific"},
                {"type": "questionnaire", "name": "I-864 - Affidavit of Support", "required": True, "questionnaire_id": "I-864"},
                {"type": "questionnaire", "name": "I-765 - Employment Authorization", "required": False, "questionnaire_id": "I-765-specific"},
                {"type": "questionnaire", "name": "I-131 - Advance Parole", "required": False, "questionnaire_id": "I-131-specific"},
                {"type": "document_request", "name": "Petitioner Passport/ID", "required": True},
                {"type": "document_request", "name": "Beneficiary Passport", "required": True},
                {"type": "document_request", "name": "Marriage Certificate", "required": True},
                {"type": "document_request", "name": "Birth Certificates", "required": True},
                {"type": "document_request", "name": "Proof of Bona Fide Marriage", "required": True},
            ]
        },
        "Naturalization": {
            "name": "N-400 Naturalization Application",
            "items": [
                {"type": "questionnaire", "name": "Personal Information", "required": True, "questionnaire_id": "COMMON-INFO", "is_common": True},
                {"type": "questionnaire", "name": "G-28 - Attorney Authorization", "required": True, "questionnaire_id": "G-28"},
                {"type": "questionnaire", "name": "N-400 - Application for Naturalization", "required": True, "questionnaire_id": "N-400"},
                {"type": "document_request", "name": "Green Card Copy", "required": True},
                {"type": "document_request", "name": "Passport Copy", "required": True},
                {"type": "document_request", "name": "Tax Returns (5 years)", "required": True},
                {"type": "document_request", "name": "Marriage/Divorce Certificates", "required": False},
            ]
        },
        "Asylum": {
            "name": "I-589 Asylum Application",
            "items": [
                {"type": "questionnaire", "name": "Personal Information", "required": True, "questionnaire_id": "COMMON-INFO", "is_common": True},
                {"type": "questionnaire", "name": "G-28 - Attorney Authorization", "required": True, "questionnaire_id": "G-28"},
                {"type": "questionnaire", "name": "I-589 - Asylum Application", "required": True, "questionnaire_id": "I-589"},
                {"type": "document_request", "name": "Passport Bio Page", "required": True},
                {"type": "document_request", "name": "Birth Certificate", "required": True},
                {"type": "document_request", "name": "Marriage Certificate (if applicable)", "required": False},
                {"type": "document_request", "name": "Evidence of Persecution", "required": True},
                {"type": "document_request", "name": "Country Conditions Reports", "required": False},
            ]
        },
        "TPS": {
            "name": "I-821 Temporary Protected Status",
            "items": [
                {"type": "questionnaire", "name": "Personal Information", "required": True, "questionnaire_id": "COMMON-INFO", "is_common": True},
                {"type": "questionnaire", "name": "G-28 - Attorney Authorization", "required": True, "questionnaire_id": "G-28"},
                {"type": "questionnaire", "name": "I-821 - TPS Application", "required": True, "questionnaire_id": "I-821"},
                {"type": "document_request", "name": "Passport or National ID", "required": True},
                {"type": "document_request", "name": "Birth Certificate", "required": True},
                {"type": "document_request", "name": "Evidence of Nationality", "required": True},
                {"type": "document_request", "name": "Evidence of Continuous Residence", "required": True},
            ]
        },
        "DACA": {
            "name": "I-821D DACA Application",
            "items": [
                {"type": "questionnaire", "name": "Personal Information", "required": True, "questionnaire_id": "COMMON-INFO", "is_common": True},
                {"type": "questionnaire", "name": "G-28 - Attorney Authorization", "required": True, "questionnaire_id": "G-28"},
                {"type": "questionnaire", "name": "I-821D - DACA Application", "required": True, "questionnaire_id": "I-821D"},
                {"type": "document_request", "name": "Proof of Identity", "required": True},
                {"type": "document_request", "name": "Proof of Entry Before Age 16", "required": True},
                {"type": "document_request", "name": "Proof of Continuous Residence", "required": True},
                {"type": "document_request", "name": "School Records", "required": True},
            ]
        },
        "Change-of-Address": {
            "name": "AR-11 Change of Address",
            "items": [
                {"type": "questionnaire", "name": "AR-11 - Change of Address", "required": True, "questionnaire_id": "AR-11"}
            ]
        },
        "Extend-Change-Status": {
            "name": "I-539 Extend/Change Nonimmigrant Status",
            "items": [
                {"type": "questionnaire", "name": "Personal Information", "required": True, "questionnaire_id": "COMMON-INFO", "is_common": True},
                {"type": "questionnaire", "name": "G-28 - Attorney Authorization", "required": True, "questionnaire_id": "G-28"},
                {"type": "questionnaire", "name": "I-539 - Extend/Change Status", "required": True, "questionnaire_id": "I-539"},
                {"type": "document_request", "name": "Current I-94", "required": True},
                {"type": "document_request", "name": "Passport Bio Page", "required": True},
                {"type": "document_request", "name": "Current Visa", "required": True},
                {"type": "document_request", "name": "Financial Support Documents", "required": False},
            ]
        },
        "Replace-Green-Card": {
            "name": "I-90 Replace Permanent Resident Card",
            "items": [
                {"type": "questionnaire", "name": "Personal Information", "required": True, "questionnaire_id": "COMMON-INFO", "is_common": True},
                {"type": "questionnaire", "name": "G-28 - Attorney Authorization", "required": True, "questionnaire_id": "G-28"},
                {"type": "questionnaire", "name": "I-90 - Replace Green Card", "required": True, "questionnaire_id": "I-90"},
                {"type": "document_request", "name": "Current Green Card Copy (if available)", "required": False},
                {"type": "document_request", "name": "Passport-style Photo", "required": True},
                {"type": "document_request", "name": "Marriage/Divorce Certificate (if name changed)", "required": False},
            ]
        },
        "Premium-Processing": {
            "name": "I-907 Premium Processing Request",
            "items": [
                {"type": "questionnaire", "name": "I-907 - Premium Processing", "required": True, "questionnaire_id": "I-907"},
                {"type": "document_request", "name": "Underlying Petition Copy", "required": True}
            ]
        },
        "Naturalization-Hearing": {
            "name": "N-336 Request for Hearing",
            "items": [
                {"type": "questionnaire", "name": "Personal Information", "required": True, "questionnaire_id": "COMMON-INFO", "is_common": True},
                {"type": "questionnaire", "name": "G-28 - Attorney Authorization", "required": True, "questionnaire_id": "G-28"},
                {"type": "questionnaire", "name": "N-336 - Hearing Request", "required": True, "questionnaire_id": "N-336"},
                {"type": "document_request", "name": "N-400 Denial Notice", "required": True},
                {"type": "document_request", "name": "Supporting Evidence", "required": True},
            ]
        },
        "Replace-Naturalization-Cert": {
            "name": "N-565 Replace Naturalization Certificate",
            "items": [
                {"type": "questionnaire", "name": "Personal Information", "required": True, "questionnaire_id": "COMMON-INFO", "is_common": True},
                {"type": "questionnaire", "name": "G-28 - Attorney Authorization", "required": True, "questionnaire_id": "G-28"},
                {"type": "questionnaire", "name": "N-565 - Replace Certificate", "required": True, "questionnaire_id": "N-565"},
                {"type": "document_request", "name": "Current Certificate Copy (if available)", "required": False},
                {"type": "document_request", "name": "Passport-style Photo", "required": True},
            ]
        },
        "FOIA": {
            "name": "G-639 FOIA Request",
            "items": [
                {"type": "questionnaire", "name": "G-639 - FOIA/Privacy Act Request", "required": True, "questionnaire_id": "G-639"},
                {"type": "document_request", "name": "ID Verification", "required": True},
            ]
        },
        "Nonimmigrant-Worker": {
            "name": "I-129 Petition for Nonimmigrant Worker",
            "items": [
                {"type": "questionnaire", "name": "Personal Information", "required": True, "questionnaire_id": "COMMON-INFO", "is_common": True},
                {"type": "questionnaire", "name": "G-28 - Attorney Authorization", "required": True, "questionnaire_id": "G-28"},
                {"type": "questionnaire", "name": "I-129 - Nonimmigrant Worker Petition", "required": True, "questionnaire_id": "I-129"},
                {"type": "questionnaire", "name": "I-907 - Premium Processing", "required": False, "questionnaire_id": "I-907-specific"},
                {"type": "document_request", "name": "Beneficiary Passport", "required": True},
                {"type": "document_request", "name": "Job Offer Letter", "required": True},
                {"type": "document_request", "name": "Company Documentation", "required": True},
                {"type": "document_request", "name": "Educational Credentials", "required": True},
            ]
        }
    }

    def resolve_template_id(self, template_key: str) -> Optional[int]:
        """Resolve a template key (e.g. 'G-28', 'I-140-specific') to a DB ID."""
        if isinstance(template_key, int):
            return template_key
        return self.TEMPLATE_IDS.get(template_key)

    def create_package(
        self,
        case_id: int,
        name: str,
        items: List[dict],
        expires_in_days: int = 30,
        message: str = None
    ) -> dict:
        """Create a new intake package."""
        package_id = str(uuid.uuid4())[:12].upper()
        access_token = str(uuid.uuid4())

        return {
            "package_id": package_id,
            "access_token": access_token,
            "case_id": case_id,
            "name": name,
            "status": PackageStatus.DRAFT.value,
            "items": items,
            "message": message,
            "expires_at": (datetime.now() + timedelta(days=expires_in_days)).isoformat(),
            "created_at": datetime.now().isoformat()
        }

    def get_template_for_visa(self, visa_type: str) -> dict:
        """Get the intake template for a visa type, resolving questionnaire IDs."""
        template = None

        if visa_type in self.PACKAGE_TEMPLATES:
            template = self.PACKAGE_TEMPLATES[visa_type]
        else:
            visa_upper = visa_type.upper()
            for key, t in self.PACKAGE_TEMPLATES.items():
                if key.upper() in visa_upper or visa_upper in key.upper():
                    template = t
                    break

        if not template:
            return {
                "name": f"{visa_type} Intake Package",
                "items": [
                    {"type": "questionnaire", "name": "Personal Information", "required": True, "questionnaire_id": self.resolve_template_id("COMMON-INFO"), "is_common": True},
                    {"type": "questionnaire", "name": "G-28 - Attorney Authorization", "required": True, "questionnaire_id": self.resolve_template_id("G-28")},
                    {"type": "document_request", "name": "Passport Copy", "required": True},
                ]
            }

        # Resolve string questionnaire_ids to DB IDs
        resolved = {**template, "items": []}
        for item in template["items"]:
            resolved_item = {**item}
            if "questionnaire_id" in item and isinstance(item["questionnaire_id"], str):
                resolved_item["questionnaire_id"] = self.resolve_template_id(item["questionnaire_id"])
            resolved["items"].append(resolved_item)

        return resolved

    def get_available_templates(self) -> List[dict]:
        """Get all available package templates."""
        return [
            {"visa_type": key, "name": val["name"], "item_count": len(val["items"])}
            for key, val in self.PACKAGE_TEMPLATES.items()
        ]

    def calculate_completion(self, items: List[dict]) -> dict:
        """Calculate package completion percentage."""
        total = len(items)
        completed = sum(1 for item in items if item.get("status") == ItemStatus.SUBMITTED.value or item.get("status") == ItemStatus.APPROVED.value)
        required = [item for item in items if item.get("required", True)]
        required_completed = sum(1 for item in required if item.get("status") == ItemStatus.SUBMITTED.value or item.get("status") == ItemStatus.APPROVED.value)

        return {
            "total_items": total,
            "completed_items": completed,
            "percentage": int((completed / total) * 100) if total > 0 else 0,
            "required_items": len(required),
            "required_completed": required_completed,
            "all_required_done": required_completed == len(required)
        }

    def generate_client_link(self, package_id: str, access_token: str, base_url: str = "") -> str:
        """Generate the client-facing intake link."""
        base_url = (base_url or settings.BASE_URL or "").rstrip("/")
        path = f"/intake/{package_id}?token={access_token}"
        return f"{base_url}{path}" if base_url else path

    def validate_package(self, package: dict) -> dict:
        """Validate a package is ready to send."""
        errors = []
        warnings = []

        items = package.get("items", [])
        if not items:
            errors.append("Package has no items")

        if not package.get("name"):
            errors.append("Package name is required")

        if not package.get("case_id"):
            errors.append("Package must be associated with a case")

        required_items = [i for i in items if i.get("required")]
        if not required_items:
            warnings.append("Package has no required items")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "ready_to_send": len(errors) == 0
        }

# SQL for intake tables (kept for reference, usually separate file)
CREATE_INTAKE_TABLE = """
CREATE TABLE IF NOT EXISTS intake_packages (
    id SERIAL PRIMARY KEY,
    package_id VARCHAR(20) UNIQUE NOT NULL,
    access_token VARCHAR(100) NOT NULL,
    case_id INTEGER REFERENCES cases(id),
    client_id INTEGER REFERENCES clients(id),
    name VARCHAR(255) NOT NULL,
    status VARCHAR(50) DEFAULT 'draft',
    message TEXT,
    expires_at TIMESTAMP,
    sent_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by INTEGER REFERENCES users(id)
);
"""

intake_service = IntakeService()
