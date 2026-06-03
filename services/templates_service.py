"""
CaseHub - Document Templates Service
Generate documents from templates with placeholders
"""
import os
import re
from datetime import datetime, date
from typing import Dict, Any, Optional, List
from jinja2 import Template, Environment
from sqlalchemy.orm import Session

from config import settings
from models import Client, Case, User


class DocumentTemplateService:
    """Service for managing and rendering document templates."""

    # Available placeholders grouped by category
    PLACEHOLDERS = {
        "client": [
            ("client.full_name", "Client full name"),
            ("client.first_name", "Client first name"),
            ("client.last_name", "Client last name"),
            ("client.email", "Client email"),
            ("client.phone", "Client phone"),
            ("client.address", "Client address"),
            ("client.date_of_birth", "Client date of birth"),
            ("client.country_of_origin", "Client country of origin"),
            ("client.alien_number", "Alien number (A#)"),
            ("client.passport_number", "Passport number"),
        ],
        "case": [
            ("case.case_number", "Case number"),
            ("case.case_name", "Case name"),
            ("case.receipt_number", "Receipt number"),
            ("case.visa_type", "Visa type"),
            ("case.status", "Case status"),
            ("case.filing_date", "Filing date"),
            ("case.priority_date", "Priority date"),
            ("case.case_value", "Case value"),
        ],
        "firm": [
            ("firm.name", "Firm name"),
            ("firm.address", "Firm address"),
            ("firm.phone", "Firm phone"),
            ("firm.email", "Firm email"),
            ("firm.website", "Firm website"),
        ],
        "dates": [
            ("today", "Today's date"),
            ("today_long", "Today's date (long format)"),
            ("current_year", "Current year"),
        ],
    }

    # Default firm info - loaded from settings
    FIRM_INFO = {
        "name": settings.ORG_NAME,
        "address": "",
        "phone": "",
        "email": settings.ORG_EMAIL,
        "website": settings.ORG_DOMAIN,
    }

    def __init__(self, db: Session):
        self.db = db
        self.env = Environment()

    def get_context(self, client_id: Optional[int] = None, case_id: Optional[int] = None) -> Dict[str, Any]:
        """Build template context from client and case data."""
        context = {
            "firm": self.FIRM_INFO,
            "today": date.today().strftime("%m/%d/%Y"),
            "today_long": date.today().strftime("%B %d, %Y"),
            "current_year": date.today().year,
        }

        if client_id:
            client = self.db.query(Client).filter(Client.id == client_id).first()
            if client:
                context["client"] = {
                    "full_name": f"{client.first_name} {client.last_name}",
                    "first_name": client.first_name,
                    "last_name": client.last_name,
                    "email": client.email or "",
                    "phone": client.phone or "",
                    "address": client.address or "",
                    "date_of_birth": client.date_of_birth.strftime("%m/%d/%Y") if client.date_of_birth else "",
                    "country_of_origin": client.country_of_origin or "",
                    "alien_number": client.alien_number or "",
                    "passport_number": client.passport_number or "",
                }

        if case_id:
            case = self.db.query(Case).filter(Case.id == case_id).first()
            if case:
                context["case"] = {
                    "case_number": case.case_number or "",
                    "case_name": case.case_name or "",
                    "receipt_number": case.receipt_number or "",
                    "visa_type": case.visa_type or "",
                    "status": case.status or "",
                    "filing_date": case.filing_date.strftime("%m/%d/%Y") if case.filing_date else "",
                    "priority_date": case.priority_date.strftime("%m/%d/%Y") if case.priority_date else "",
                    "case_value": f"${case.case_value:,.2f}" if case.case_value else "",
                }

                # If client not provided, get from case
                if not client_id and case.client_id:
                    client = self.db.query(Client).filter(Client.id == case.client_id).first()
                    if client:
                        context["client"] = {
                            "full_name": f"{client.first_name} {client.last_name}",
                            "first_name": client.first_name,
                            "last_name": client.last_name,
                            "email": client.email or "",
                            "phone": client.phone or "",
                            "address": client.address or "",
                            "date_of_birth": client.date_of_birth.strftime("%m/%d/%Y") if client.date_of_birth else "",
                            "country_of_origin": client.country_of_origin or "",
                            "alien_number": client.alien_number or "",
                            "passport_number": client.passport_number or "",
                        }

        return context

    def render_template(self, template_content: str, context: Dict[str, Any]) -> str:
        """Render a template with the given context."""
        try:
            template = Template(template_content)
            return template.render(**context)
        except Exception as e:
            return f"Error rendering template: {str(e)}"

    def preview_template(self, template_content: str, client_id: Optional[int] = None, case_id: Optional[int] = None) -> str:
        """Preview a template with actual data."""
        context = self.get_context(client_id, case_id)
        return self.render_template(template_content, context)


# Default document templates
DEFAULT_TEMPLATES = [
    {
        "name": "Engagement Letter",
        "category": "contracts",
        "description": "Standard client engagement letter",
        "content": """{{ firm.name }}
{{ firm.address }}
{{ firm.phone }} | {{ firm.email }}

{{ today_long }}

{{ client.full_name }}
{{ client.address }}

RE: Immigration Legal Services - {{ case.visa_type }}

Dear {{ client.first_name }},

Thank you for choosing {{ firm.name }} to assist you with your immigration matter. This letter confirms our engagement to represent you in connection with your {{ case.visa_type }} application.

SCOPE OF REPRESENTATION:
We will provide the following services:
1. Evaluate your eligibility for {{ case.visa_type }}
2. Prepare and file the necessary forms and supporting documentation
3. Respond to any Requests for Evidence (RFE)
4. Monitor your case status with USCIS

FEES AND COSTS:
Our legal fees for this matter are {{ case.case_value }}. This does not include USCIS filing fees, which will be billed separately.

Payment terms: 50% due upon signing, 50% due upon filing.

Please sign below to indicate your acceptance of these terms.

Sincerely,

_________________________
Attorney Name
{{ firm.name }}

ACCEPTED AND AGREED:

_________________________          _______________
{{ client.full_name }}                    Date
"""
    },
    {
        "name": "Cover Letter - USCIS",
        "category": "uscis",
        "description": "Standard cover letter for USCIS filings",
        "content": """{{ firm.name }}
{{ firm.address }}
{{ firm.phone }} | {{ firm.email }}

{{ today_long }}

U.S. Citizenship and Immigration Services
[Service Center Address]

RE: {{ case.visa_type }} Petition for {{ client.full_name }}
     Receipt Number: {{ case.receipt_number }}
     A#: {{ client.alien_number }}

Dear Sir/Madam:

Please find enclosed the {{ case.visa_type }} petition and supporting documentation for {{ client.full_name }}.

PETITIONER/APPLICANT INFORMATION:
Name: {{ client.full_name }}
Date of Birth: {{ client.date_of_birth }}
Country of Birth: {{ client.country_of_origin }}
A#: {{ client.alien_number }}

ENCLOSED DOCUMENTS:
1. Form [Form Number]
2. Filing fee check/money order
3. Supporting documents (see index)
4. Passport copies
5. [Additional documents]

Please contact our office if you require any additional information.

Respectfully submitted,

_________________________
Attorney Name
{{ firm.name }}

Enclosures
"""
    },
    {
        "name": "Client Welcome Letter",
        "category": "client_communication",
        "description": "Welcome letter for new clients",
        "content": """{{ firm.name }}
Immigration Law Services

{{ today_long }}

Dear {{ client.first_name }},

Welcome to {{ firm.name }}! We are delighted to have you as our client and look forward to assisting you with your immigration journey.

YOUR CASE INFORMATION:
Case Number: {{ case.case_number }}
Case Type: {{ case.visa_type }}
Current Status: {{ case.status }}

WHAT'S NEXT:
1. Please complete the intake questionnaire we sent to {{ client.email }}
2. Gather the required documents (list attached)
3. Schedule your initial consultation

CONTACT INFORMATION:
Email: {{ firm.email }}
Phone: {{ firm.phone }}
Website: {{ firm.website }}

IMPORTANT REMINDERS:
- Keep copies of all documents you provide to us
- Notify us immediately of any address or contact changes
- Do not sign any documents related to your immigration status without consulting us first

We are committed to providing you with excellent legal service. Please don't hesitate to reach out if you have any questions.

Best regards,

{{ firm.name }} Team
"""
    },
    {
        "name": "RFE Response Cover Letter",
        "category": "uscis",
        "description": "Cover letter for RFE responses",
        "content": """{{ firm.name }}
{{ firm.address }}
{{ firm.phone }} | {{ firm.email }}

{{ today_long }}

U.S. Citizenship and Immigration Services
[Service Center Address]

RE: Response to Request for Evidence
     Petitioner/Applicant: {{ client.full_name }}
     Receipt Number: {{ case.receipt_number }}
     A#: {{ client.alien_number }}

Dear Sir/Madam:

This letter is submitted in response to the Request for Evidence (RFE) dated [RFE Date] regarding the above-referenced petition.

SUMMARY OF EVIDENCE PROVIDED:
[List of evidence items addressing each RFE point]

1. [RFE Point 1]
   - [Evidence provided]

2. [RFE Point 2]
   - [Evidence provided]

We respectfully submit that the enclosed evidence fully addresses each point raised in the RFE and demonstrates that {{ client.full_name }} meets all requirements for {{ case.visa_type }}.

Please contact our office if you require any additional information.

Respectfully submitted,

_________________________
Attorney Name
{{ firm.name }}

Enclosures
"""
    },
    {
        "name": "Payment Receipt",
        "category": "billing",
        "description": "Receipt for client payments",
        "content": """{{ firm.name }}
{{ firm.address }}

PAYMENT RECEIPT

Date: {{ today_long }}

Received from: {{ client.full_name }}
Address: {{ client.address }}

Case Reference: {{ case.case_number }} - {{ case.visa_type }}

PAYMENT DETAILS:
Amount Received: $[AMOUNT]
Payment Method: [Cash/Check/Credit Card/Wire]
Check/Reference #: [NUMBER]

FOR: [Description of services]

Balance Due: $[BALANCE]

Thank you for your payment.

_________________________
{{ firm.name }}
{{ firm.phone }}
"""
    },
]


def get_template_service(db: Session) -> DocumentTemplateService:
    """Get template service instance."""
    return DocumentTemplateService(db)
