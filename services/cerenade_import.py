"""
CaseHub - Cerenade Import Service
Import data from Cerenade eImmigration system via web scraping
"""
import json
import os
import re
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

# Data paths for previously exported Cerenade data
CERENADE_DATA_PATH = "/Users/beijaflor/Projects_Local/immigration-law-suite/ia-agent-setup/cerenade_data"


class CerenadeImportService:
    """Service for importing data from Cerenade"""

    def __init__(self, data_path: str = None):
        self.data_path = data_path or CERENADE_DATA_PATH

    def load_json_file(self, filename: str) -> List[Dict]:
        """Load data from a JSON file"""
        filepath = os.path.join(self.data_path, filename)
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

    def parse_date(self, date_str: str) -> Optional[date]:
        """Parse various date formats from Cerenade"""
        if not date_str or date_str.strip() == "":
            return None

        formats = [
            "%m/%d/%Y",
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%B %d, %Y",
            "%b %d, %Y"
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except:
                continue
        return None

    def clean_phone(self, phone: str) -> str:
        """Clean phone number"""
        if not phone:
            return ""
        # Remove non-digits except + for country code
        cleaned = re.sub(r'[^\d+]', '', phone)
        return cleaned

    def map_status(self, cerenade_status: str) -> str:
        """Map Cerenade status to CaseHub status"""
        status_map = {
            "Active": "active",
            "Prospect": "prospect",
            "Lead": "lead",
            "Closed": "closed",
            "Approved": "approved",
            "Denied": "denied",
            "Pending": "intake",
            "In Progress": "drafting",
            "Filed": "filed",
            "RFE": "rfe",
            "Document Collection": "document_collection",
            "Review": "review"
        }
        return status_map.get(cerenade_status, "intake")

    # ==========================================
    # Client Import
    # ==========================================

    def import_clients_from_json(self, db: Session, json_data: List[Dict]) -> Dict:
        """Import clients from JSON data"""
        from models import Client

        results = {
            "imported": 0,
            "updated": 0,
            "skipped": 0,
            "errors": []
        }

        for item in json_data:
            try:
                # Parse name
                full_name = item.get("name", "")
                name_parts = full_name.split(" ", 2)
                first_name = name_parts[0] if name_parts else ""
                middle_name = name_parts[1] if len(name_parts) > 2 else ""
                last_name = name_parts[-1] if len(name_parts) > 1 else ""

                # Check if client exists (by email or name)
                email = item.get("email", "")
                existing = None
                if email:
                    existing = db.query(Client).filter(Client.email == email).first()
                if not existing and first_name and last_name:
                    existing = db.query(Client).filter(
                        Client.first_name == first_name,
                        Client.last_name == last_name
                    ).first()

                client_data = {
                    "first_name": first_name,
                    "middle_name": middle_name,
                    "last_name": last_name,
                    "email": email,
                    "phone": self.clean_phone(item.get("phone", "")),
                    "whatsapp": self.clean_phone(item.get("whatsapp", "")),
                    "date_of_birth": self.parse_date(item.get("dob", "")),
                    "country_of_origin": item.get("country", ""),
                    "ssn": item.get("ssn", ""),
                    "alien_number": item.get("alien_number", ""),
                    "passport_number": item.get("passport", ""),
                    "address": item.get("address", ""),
                    "status": self.map_status(item.get("status", "")),
                    "notes": item.get("notes", ""),
                    "cerenade_id": str(item.get("id", ""))
                }

                if existing:
                    # Update existing
                    for key, value in client_data.items():
                        if value and hasattr(existing, key):
                            setattr(existing, key, value)
                    results["updated"] += 1
                else:
                    # Create new
                    new_client = Client(**client_data)
                    db.add(new_client)
                    results["imported"] += 1

                db.commit()

            except Exception as e:
                results["errors"].append(f"Client {item.get('name', 'Unknown')}: {str(e)}")
                results["skipped"] += 1

        return results

    # ==========================================
    # Case Import
    # ==========================================

    def import_cases_from_json(self, db: Session, json_data: List[Dict]) -> Dict:
        """Import cases from JSON data"""
        from models import Case, Client

        results = {
            "imported": 0,
            "updated": 0,
            "skipped": 0,
            "errors": []
        }

        for item in json_data:
            try:
                # Find client
                client_name = item.get("client_name", "")
                client = None
                if client_name:
                    name_parts = client_name.split(" ")
                    if len(name_parts) >= 2:
                        client = db.query(Client).filter(
                            Client.first_name == name_parts[0],
                            Client.last_name == name_parts[-1]
                        ).first()

                # Check if case exists
                case_number = item.get("case_number", "")
                existing = None
                if case_number:
                    existing = db.query(Case).filter(Case.case_number == case_number).first()

                case_data = {
                    "client_id": client.id if client else None,
                    "case_number": case_number,
                    "external_case_number": item.get("external_case_number", ""),
                    "receipt_number": item.get("receipt_number", ""),
                    "case_name": item.get("case_name", ""),
                    "visa_type": item.get("visa_type", ""),
                    "status": self.map_status(item.get("status", "")),
                    "priority": item.get("priority", "medium").lower(),
                    "area_of_practice": item.get("area_of_practice", ""),
                    "jurisdiction": item.get("jurisdiction", ""),
                    "application_date": self.parse_date(item.get("filed_date", "")),
                    "processing_date": self.parse_date(item.get("processing_date", "")),
                    "expiration_date": self.parse_date(item.get("expiration_date", "")),
                    "case_value": float(item.get("case_value", 0) or 0),
                    "amount_paid": float(item.get("amount_paid", 0) or 0),
                    "notes": item.get("notes", ""),
                    "cerenade_id": str(item.get("id", ""))
                }

                if existing:
                    for key, value in case_data.items():
                        if value and hasattr(existing, key):
                            setattr(existing, key, value)
                    results["updated"] += 1
                else:
                    new_case = Case(**case_data)
                    db.add(new_case)
                    results["imported"] += 1

                db.commit()

            except Exception as e:
                results["errors"].append(f"Case {item.get('case_number', 'Unknown')}: {str(e)}")
                results["skipped"] += 1

        return results

    # ==========================================
    # Document Import
    # ==========================================

    def import_documents_from_json(self, db: Session, json_data: List[Dict]) -> Dict:
        """Import document metadata from JSON data"""
        from models import Document, Client, Case

        results = {
            "imported": 0,
            "updated": 0,
            "skipped": 0,
            "errors": []
        }

        for item in json_data:
            try:
                # Find client/case
                client_id = None
                case_id = None

                if item.get("client_name"):
                    name_parts = item["client_name"].split(" ")
                    if len(name_parts) >= 2:
                        client = db.query(Client).filter(
                            Client.first_name == name_parts[0],
                            Client.last_name == name_parts[-1]
                        ).first()
                        if client:
                            client_id = client.id

                if item.get("case_number"):
                    case = db.query(Case).filter(Case.case_number == item["case_number"]).first()
                    if case:
                        case_id = case.id

                doc_data = {
                    "client_id": client_id,
                    "case_id": case_id,
                    "name": item.get("name", ""),
                    "type": item.get("type", "other"),
                    "status": item.get("status", "pending"),
                    "notes": item.get("notes", ""),
                    "expiration_date": self.parse_date(item.get("expiration_date", "")),
                    "cerenade_id": str(item.get("id", ""))
                }

                # Check if document exists
                existing = None
                if item.get("name") and (client_id or case_id):
                    existing = db.query(Document).filter(
                        Document.name == item["name"],
                        Document.client_id == client_id if client_id else True
                    ).first()

                if existing:
                    for key, value in doc_data.items():
                        if value and hasattr(existing, key):
                            setattr(existing, key, value)
                    results["updated"] += 1
                else:
                    new_doc = Document(**doc_data)
                    db.add(new_doc)
                    results["imported"] += 1

                db.commit()

            except Exception as e:
                results["errors"].append(f"Document {item.get('name', 'Unknown')}: {str(e)}")
                results["skipped"] += 1

        return results

    # ==========================================
    # Full Import from Files
    # ==========================================

    def import_all_from_files(self, db: Session) -> Dict:
        """Import all data from exported Cerenade JSON files"""
        results = {
            "clients": {"imported": 0, "updated": 0, "skipped": 0, "errors": []},
            "cases": {"imported": 0, "updated": 0, "skipped": 0, "errors": []},
            "documents": {"imported": 0, "updated": 0, "skipped": 0, "errors": []}
        }

        # Import clients
        clients_data = self.load_json_file("clients.json")
        if clients_data:
            results["clients"] = self.import_clients_from_json(db, clients_data)

        # Import cases
        cases_data = self.load_json_file("cases.json")
        if cases_data:
            results["cases"] = self.import_cases_from_json(db, cases_data)

        # Import documents
        docs_data = self.load_json_file("documents.json")
        if docs_data:
            results["documents"] = self.import_documents_from_json(db, docs_data)

        return results

    def import_from_uploaded_json(self, db: Session, json_content: str, data_type: str) -> Dict:
        """Import data from uploaded JSON content"""
        try:
            data = json.loads(json_content)
            if not isinstance(data, list):
                data = [data]

            if data_type == "clients":
                return self.import_clients_from_json(db, data)
            elif data_type == "cases":
                return self.import_cases_from_json(db, data)
            elif data_type == "documents":
                return self.import_documents_from_json(db, data)
            else:
                return {"error": f"Unknown data type: {data_type}"}

        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON: {str(e)}"}
        except Exception as e:
            return {"error": str(e)}
