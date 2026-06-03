"""
CaseHub - Notion Sync Service
Two-way synchronization between CaseHub and Notion databases
"""
from dotenv import load_dotenv
load_dotenv()

import os
import json
import requests
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

# Notion API Configuration
NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# Notion token must be set via NOTION_TOKEN environment variable
# Get your token at: https://www.notion.so/my-integrations
DEFAULT_NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")


class NotionSyncService:
    """Service for syncing CaseHub data with Notion"""

    def __init__(self, token: str = None):
        self.token = token or os.getenv("NOTION_TOKEN", DEFAULT_NOTION_TOKEN)
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION
        }
        self.database_ids = {}

    def _request(self, method: str, endpoint: str, data: dict = None) -> dict:
        """Make request to Notion API"""
        url = f"{NOTION_API_URL}{endpoint}"
        try:
            if method == "GET":
                response = requests.get(url, headers=self.headers)
            elif method == "POST":
                response = requests.post(url, headers=self.headers, json=data)
            elif method == "PATCH":
                response = requests.patch(url, headers=self.headers, json=data)
            else:
                return {"error": f"Unknown method: {method}"}

            if response.status_code in [200, 201]:
                return response.json()
            else:
                return {
                    "error": f"API Error: {response.status_code}",
                    "details": response.text
                }
        except Exception as e:
            return {"error": str(e)}

    def search_databases(self, query: str = "") -> List[Dict]:
        """Search for databases in the workspace"""
        result = self._request("POST", "/search", {
            "query": query,
            "filter": {"property": "object", "value": "database"}
        })
        if "error" in result:
            return []
        return result.get("results", [])

    def get_database(self, database_id: str) -> Dict:
        """Get database schema"""
        return self._request("GET", f"/databases/{database_id}")

    def query_database(self, database_id: str, filter_obj: dict = None, sorts: list = None) -> List[Dict]:
        """Query pages in a database"""
        data = {}
        if filter_obj:
            data["filter"] = filter_obj
        if sorts:
            data["sorts"] = sorts

        result = self._request("POST", f"/databases/{database_id}/query", data)
        if "error" in result:
            return []
        return result.get("results", [])

    def create_page(self, database_id: str, properties: Dict, children: List = None) -> Dict:
        """Create a new page in a database"""
        data = {
            "parent": {"database_id": database_id},
            "properties": properties
        }
        if children:
            data["children"] = children
        return self._request("POST", "/pages", data)

    def update_page(self, page_id: str, properties: Dict) -> Dict:
        """Update page properties"""
        return self._request("PATCH", f"/pages/{page_id}", {"properties": properties})

    # ==========================================
    # Property Converters
    # ==========================================

    def _to_notion_title(self, value: str) -> Dict:
        """Convert string to Notion title property"""
        return {"title": [{"text": {"content": value or ""}}]}

    def _to_notion_rich_text(self, value: str) -> Dict:
        """Convert string to Notion rich_text property"""
        return {"rich_text": [{"text": {"content": value or ""}}]}

    def _to_notion_number(self, value: float) -> Dict:
        """Convert number to Notion number property"""
        return {"number": value}

    def _to_notion_select(self, value: str) -> Dict:
        """Convert string to Notion select property"""
        if not value:
            return {"select": None}
        return {"select": {"name": value}}

    def _to_notion_date(self, value: date) -> Dict:
        """Convert date to Notion date property"""
        if not value:
            return {"date": None}
        return {"date": {"start": value.isoformat()}}

    def _to_notion_email(self, value: str) -> Dict:
        """Convert string to Notion email property"""
        return {"email": value if value else None}

    def _to_notion_phone(self, value: str) -> Dict:
        """Convert string to Notion phone_number property"""
        return {"phone_number": value if value else None}

    def _from_notion_title(self, prop: Dict) -> str:
        """Extract text from Notion title property"""
        title_arr = prop.get("title", [])
        if title_arr:
            return title_arr[0].get("text", {}).get("content", "")
        return ""

    def _from_notion_rich_text(self, prop: Dict) -> str:
        """Extract text from Notion rich_text property"""
        rt_arr = prop.get("rich_text", [])
        if rt_arr:
            return rt_arr[0].get("text", {}).get("content", "")
        return ""

    def _from_notion_select(self, prop: Dict) -> str:
        """Extract value from Notion select property"""
        select = prop.get("select")
        if select:
            return select.get("name", "")
        return ""

    def _from_notion_date(self, prop: Dict) -> Optional[date]:
        """Extract date from Notion date property"""
        date_obj = prop.get("date")
        if date_obj and date_obj.get("start"):
            try:
                return datetime.fromisoformat(date_obj["start"].split("T")[0]).date()
            except:
                pass
        return None

    # ==========================================
    # Client Sync
    # ==========================================

    def sync_client_to_notion(self, client, database_id: str) -> Dict:
        """Sync a CaseHub client to Notion"""
        properties = {
            "Name": self._to_notion_title(f"{client.first_name} {client.last_name}"),
            "First Name": self._to_notion_rich_text(client.first_name),
            "Last Name": self._to_notion_rich_text(client.last_name),
            "Email": self._to_notion_email(client.email),
            "Phone": self._to_notion_phone(client.phone),
            "Country": self._to_notion_select(client.country_of_origin),
            "Status": self._to_notion_select(client.status),
        }

        # Check if client has notion_page_id
        if hasattr(client, 'notion_page_id') and client.notion_page_id:
            return self.update_page(client.notion_page_id, properties)
        else:
            return self.create_page(database_id, properties)

    def sync_client_from_notion(self, page: Dict) -> Dict:
        """Convert Notion page to client data"""
        props = page.get("properties", {})
        return {
            "notion_page_id": page.get("id"),
            "first_name": self._from_notion_rich_text(props.get("First Name", {})),
            "last_name": self._from_notion_rich_text(props.get("Last Name", {})),
            "email": props.get("Email", {}).get("email"),
            "phone": props.get("Phone", {}).get("phone_number"),
            "country_of_origin": self._from_notion_select(props.get("Country", {})),
            "status": self._from_notion_select(props.get("Status", {})),
        }

    # ==========================================
    # Case Sync
    # ==========================================

    def sync_case_to_notion(self, case, database_id: str) -> Dict:
        """Sync a CaseHub case to Notion"""
        properties = {
            "Name": self._to_notion_title(case.case_name or case.case_number or "Untitled"),
            "Case Number": self._to_notion_rich_text(case.case_number),
            "Receipt Number": self._to_notion_rich_text(case.receipt_number),
            "Visa Type": self._to_notion_select(case.visa_type),
            "Status": self._to_notion_select(case.status),
            "Priority": self._to_notion_select(case.priority),
        }

        if case.application_date:
            properties["Application Date"] = self._to_notion_date(case.application_date)
        if case.case_value:
            properties["Case Value"] = self._to_notion_number(float(case.case_value))

        if hasattr(case, 'notion_page_id') and case.notion_page_id:
            return self.update_page(case.notion_page_id, properties)
        else:
            return self.create_page(database_id, properties)

    def sync_case_from_notion(self, page: Dict) -> Dict:
        """Convert Notion page to case data"""
        props = page.get("properties", {})
        return {
            "notion_page_id": page.get("id"),
            "case_name": self._from_notion_title(props.get("Name", {})),
            "case_number": self._from_notion_rich_text(props.get("Case Number", {})),
            "receipt_number": self._from_notion_rich_text(props.get("Receipt Number", {})),
            "visa_type": self._from_notion_select(props.get("Visa Type", {})),
            "status": self._from_notion_select(props.get("Status", {})),
            "priority": self._from_notion_select(props.get("Priority", {})),
            "application_date": self._from_notion_date(props.get("Application Date", {})),
        }

    # ==========================================
    # Full Sync Operations
    # ==========================================

    def full_sync_clients(self, db: Session, database_id: str, direction: str = "both") -> Dict:
        """
        Full synchronization of clients
        direction: 'to_notion', 'from_notion', or 'both'
        """
        from models import Client

        results = {
            "synced_to_notion": 0,
            "synced_from_notion": 0,
            "errors": []
        }

        if direction in ["to_notion", "both"]:
            clients = db.query(Client).all()
            for client in clients:
                try:
                    result = self.sync_client_to_notion(client, database_id)
                    if "error" not in result:
                        if not hasattr(client, 'notion_page_id') or not client.notion_page_id:
                            client.notion_page_id = result.get("id")
                            db.commit()
                        results["synced_to_notion"] += 1
                    else:
                        results["errors"].append(f"Client {client.id}: {result['error']}")
                except Exception as e:
                    results["errors"].append(f"Client {client.id}: {str(e)}")

        if direction in ["from_notion", "both"]:
            pages = self.query_database(database_id)
            for page in pages:
                try:
                    data = self.sync_client_from_notion(page)
                    notion_id = data.pop("notion_page_id")

                    # Find existing or create new
                    existing = db.query(Client).filter(Client.notion_page_id == notion_id).first()
                    if existing:
                        for key, value in data.items():
                            if value:
                                setattr(existing, key, value)
                    else:
                        # Only create if has name
                        if data.get("first_name") or data.get("last_name"):
                            new_client = Client(**data, notion_page_id=notion_id)
                            db.add(new_client)

                    db.commit()
                    results["synced_from_notion"] += 1
                except Exception as e:
                    results["errors"].append(f"Notion page: {str(e)}")

        return results

    def full_sync_cases(self, db: Session, database_id: str, direction: str = "both") -> Dict:
        """
        Full synchronization of cases
        direction: 'to_notion', 'from_notion', or 'both'
        """
        from models import Case

        results = {
            "synced_to_notion": 0,
            "synced_from_notion": 0,
            "errors": []
        }

        if direction in ["to_notion", "both"]:
            cases = db.query(Case).all()
            for case in cases:
                try:
                    result = self.sync_case_to_notion(case, database_id)
                    if "error" not in result:
                        if not hasattr(case, 'notion_page_id') or not case.notion_page_id:
                            case.notion_page_id = result.get("id")
                            db.commit()
                        results["synced_to_notion"] += 1
                    else:
                        results["errors"].append(f"Case {case.id}: {result['error']}")
                except Exception as e:
                    results["errors"].append(f"Case {case.id}: {str(e)}")

        if direction in ["from_notion", "both"]:
            pages = self.query_database(database_id)
            for page in pages:
                try:
                    data = self.sync_case_from_notion(page)
                    notion_id = data.pop("notion_page_id")

                    existing = db.query(Case).filter(Case.notion_page_id == notion_id).first()
                    if existing:
                        for key, value in data.items():
                            if value:
                                setattr(existing, key, value)
                    else:
                        if data.get("case_name") or data.get("case_number"):
                            new_case = Case(**data, notion_page_id=notion_id)
                            db.add(new_case)

                    db.commit()
                    results["synced_from_notion"] += 1
                except Exception as e:
                    results["errors"].append(f"Notion page: {str(e)}")

        return results


# Utility function for testing
def test_connection(token: str = None) -> Dict:
    """Test Notion API connection"""
    service = NotionSyncService(token)
    result = service._request("GET", "/users/me")
    if "error" in result:
        return {"success": False, "error": result["error"]}
    return {
        "success": True,
        "user": result.get("name", "Unknown"),
        "type": result.get("type", "Unknown")
    }
