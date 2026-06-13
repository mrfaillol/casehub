"""
CaseHub - Notion Tasks Service
Bidirectional sync between CaseHub and Notion Task Manager databases
"""
import os
from dotenv import load_dotenv
load_dotenv()
import json
import requests
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from functools import lru_cache
import time

import logging
from config import settings

logger = logging.getLogger(__name__)

# Notion API Configuration
NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
DEFAULT_NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")

# Task Manager Database IDs
TASK_DATABASES = {
    "juliana": {
        "database_id": "2eecd9459a03809a9547f45fb025dd8f",
        "name": "Task Manager (Juliana)",
        "color": "#dc3545"  # red
    },
    "ana": {
        "id": "28bd872b-594c-81b4-8de3-000206afa5fb",
        "database_id": "2eecd9459a03801194c2d9cc613677f5",
        "name": "Task Manager (Ana)",
        "color": "#ffc107"  # yellow
    },
    "danielle": {
        "database_id": "30acd9459a038075b8d7c8e4e6b00e08",
        "name": "Task Manager (Danielle)",
        "color": "#8b5cf6"  # purple
    },
    "daniel": {
        "database_id": "30acd9459a03804692b1fb2252cc2062",
        "name": "Task Manager (Daniel)",
        "color": "#3b82f6"  # blue
    }
}

# User IDs for @mentions and notifications
# Emails loaded from TEAM_EMAILS config; Notion IDs are Notion-specific
_NOTION_USER_IDS_BASE = {
    "juliana": {"id": "4a8a5088-b926-4e76-bc7a-2de211f3ee45", "name": "Juliana Moreschi"},
    "ana": {"id": "28bd872b-594c-81b4-8de3-000206afa5fb", "name": "Ana Clara Leal da Costa Bueno"},
    "victor": {"id": "10ed872b-594c-810c-aa8d-0002c3926bc7", "name": "Victor Vingren"},
    "laura": {"id": "2eed872b-594c-81a0-840f-0002bdfd469f", "name": "Laura Baticioto"},
    "danielle": {"id": "", "name": "Danielle Fujii"},
    "daniel": {"id": "", "name": "Daniel Clasen"},
}

def _build_notion_user_ids():
    """Merge Notion IDs with emails from TEAM_EMAILS config."""
    team_emails = {}
    raw = settings.TEAM_EMAILS
    if raw:
        try:
            team = json.loads(raw)
            team_emails = {k: v.get("email", "") for k, v in team.items()}
        except (json.JSONDecodeError, AttributeError):
            pass
    result = {}
    for key, data in _NOTION_USER_IDS_BASE.items():
        result[key] = {**data, "email": team_emails.get(key, "")}
    return result

NOTION_USER_IDS = _build_notion_user_ids()

# Cache for tasks (5 minutes)
_task_cache = {}
_cache_timestamp = {}
CACHE_TTL = 1800  # 30 minutes (avoid 19s cold-start from Notion API)




class NotionTasksService:
    """Service for managing tasks via Notion API"""

    def __init__(self, token: str = None):
        self.token = token or os.getenv("NOTION_TOKEN", DEFAULT_NOTION_TOKEN)
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION
        }

    def _request(self, method: str, endpoint: str, data: dict = None) -> dict:
        """Make request to Notion API"""
        url = f"{NOTION_API_URL}{endpoint}"
        try:
            if method == "GET":
                response = requests.get(url, headers=self.headers, timeout=30)
            elif method == "POST":
                response = requests.post(url, headers=self.headers, json=data, timeout=30)
            elif method == "PATCH":
                response = requests.patch(url, headers=self.headers, json=data, timeout=30)
            else:
                return {"error": f"Unknown method: {method}"}

            if response.status_code in [200, 201]:
                return response.json()
            else:
                logger.error("Failed to call Notion API %s %s: HTTP %s", method, endpoint, response.status_code)
                return {
                    "error": f"API Error: {response.status_code}",
                    "details": response.text
                }
        except (requests.RequestException, Exception) as e:
            logger.error("Failed to call Notion API %s %s: %s", method, endpoint, e)
            return {"error": str(e)}

    # ==========================================
    # Property Extractors (Notion → Python)
    # ==========================================

    def _from_title(self, prop: Dict) -> str:
        """Extract text from title property"""
        title_arr = prop.get("title", [])
        if title_arr:
            return title_arr[0].get("text", {}).get("content", "")
        return ""

    def _from_rich_text(self, prop: Dict) -> str:
        """Extract text from rich_text property"""
        rt_arr = prop.get("rich_text", [])
        if rt_arr:
            return "".join([t.get("text", {}).get("content", "") for t in rt_arr])
        return ""

    def _from_multi_select(self, prop: Dict) -> List[str]:
        """Extract values from multi_select property"""
        ms_arr = prop.get("multi_select", [])
        return [item.get("name", "") for item in ms_arr]

    def _from_select(self, prop: Dict) -> str:
        """Extract value from select property"""
        select = prop.get("select")
        if select:
            return select.get("name", "")
        return ""

    def _from_status(self, prop: Dict) -> str:
        """Extract value from status property"""
        status = prop.get("status")
        if status:
            return status.get("name", "")
        return ""

    def _from_date(self, prop: Dict) -> Optional[str]:
        """Extract date from date property (returns ISO string)"""
        date_obj = prop.get("date")
        if date_obj and date_obj.get("start"):
            return date_obj["start"].split("T")[0]
        return None

    def _from_url(self, prop: Dict) -> str:
        """Extract URL from url property"""
        return prop.get("url") or ""

    def _from_checkbox(self, prop: Dict) -> bool:
        """Extract boolean from checkbox property"""
        return prop.get("checkbox", False)

    def _from_created_time(self, prop: Dict) -> str:
        """Extract created time"""
        return prop.get("created_time", "")

    def _from_last_edited_time(self, prop: Dict) -> str:
        """Extract last edited time"""
        return prop.get("last_edited_time", "")

    def _from_created_by(self, prop: Dict) -> str:
        """Extract created by user name"""
        created_by = prop.get("created_by", {})
        return created_by.get("name", "") or created_by.get("id", "")

    def _from_last_edited_by(self, prop: Dict) -> str:
        """Extract last edited by user name"""
        edited_by = prop.get("last_edited_by", {})
        return edited_by.get("name", "") or edited_by.get("id", "")

    # ==========================================
    # Property Builders (Python → Notion)
    # ==========================================

    def _to_title(self, value: str) -> Dict:
        """Convert string to title property"""
        return {"title": [{"text": {"content": value or ""}}]}

    def _to_rich_text(self, value: str) -> Dict:
        """Convert string to rich_text property"""
        return {"rich_text": [{"text": {"content": value or ""}}]}

    def _to_multi_select(self, values: List[str]) -> Dict:
        """Convert list to multi_select property"""
        return {"multi_select": [{"name": v} for v in (values or [])]}

    def _to_select(self, value: str) -> Dict:
        """Convert string to select property"""
        if not value:
            return {"select": None}
        return {"select": {"name": value}}

    def _to_status(self, value: str) -> Dict:
        """Convert string to status property"""
        if not value:
            return {"status": None}
        return {"status": {"name": value}}

    def _to_date(self, value: str) -> Dict:
        """Convert ISO date string to date property"""
        if not value:
            return {"date": None}
        return {"date": {"start": value}}

    def _to_url(self, value: str) -> Dict:
        """Convert string to url property"""
        return {"url": value if value else None}

    def _to_checkbox(self, value: bool) -> Dict:
        """Convert boolean to checkbox property"""
        return {"checkbox": bool(value)}

    # ==========================================
    # Task Conversion
    # ==========================================

    def convert_notion_to_task(self, page: Dict, source: str = "") -> Dict:
        """Convert Notion page to task dictionary"""
        props = page.get("properties", {})

        return {
            "notion_id": page.get("id"),
            "notion_url": page.get("url"),
            "source": source,

            # Main fields
            "title": self._from_title(props.get("Task", {})),
            "description": self._from_rich_text(props.get("Description", {})),
            "client_names": self._from_multi_select(props.get("Client", {})),
            "visa_type": self._from_select(props.get("Visa Type", {})),
            "status": self._from_status(props.get("Status", {})),
            "priority": self._from_select(props.get("Priority", {})),
            "assigned_to": self._from_multi_select(props.get("Assigned To", {})),

            # Dates
            "due_date": self._from_date(props.get("Due Date", {})),
            "handed_in_date": self._from_date(props.get("Handed in", {})),
            "completed_at": self._from_date(props.get("Completed On", {})),
            "date_received": self._from_date(props.get("Date Received", {})),

            # Additional fields
            "case_step": self._from_multi_select(props.get("Case Step", {})),
            "document_url": self._from_url(props.get("Document URL", {})),
            "comments": self._from_rich_text(props.get("Comments", {})),
            "answer": self._from_rich_text(props.get("Answer", {})),
            "email_ref": self._from_rich_text(props.get("E-mail", {})),
            "is_inbox": self._from_checkbox(props.get("Inbox", {})),

            # Auto fields
            "created_at": self._from_created_time(props.get("Created time", {})),
            "updated_at": self._from_last_edited_time(props.get("Last edited time", {})),
            "created_by_name": self._from_created_by(props.get("Created by", {})),
            "updated_by_name": self._from_last_edited_by(props.get("Last edited by", {})),
        }

    def convert_task_to_notion(self, task: Dict) -> Dict:
        """Convert task dictionary to Notion properties"""
        properties = {}

        if task.get("title"):
            properties["Task"] = self._to_title(task["title"])
        if task.get("description"):
            properties["Description"] = self._to_rich_text(task["description"])
        if task.get("client_names"):
            properties["Client"] = self._to_multi_select(task["client_names"])
        if task.get("visa_type"):
            properties["Visa Type"] = self._to_select(task["visa_type"])
        if task.get("status"):
            properties["Status"] = self._to_status(task["status"])
        if task.get("priority"):
            properties["Priority"] = self._to_select(task["priority"])
        if task.get("assigned_to"):
            properties["Assigned To"] = self._to_multi_select(task["assigned_to"])
        if task.get("due_date"):
            properties["Due Date"] = self._to_date(task["due_date"])
        if task.get("handed_in_date"):
            properties["Handed in"] = self._to_date(task["handed_in_date"])
        if task.get("completed_at"):
            properties["Completed On"] = self._to_date(task["completed_at"])
        if task.get("date_received"):
            properties["Date Received"] = self._to_date(task["date_received"])
        if task.get("case_step"):
            properties["Case Step"] = self._to_multi_select(task["case_step"])
        if task.get("document_url"):
            properties["Document URL"] = self._to_url(task["document_url"])
        if task.get("comments"):
            properties["Comments"] = self._to_rich_text(task["comments"])
        if task.get("answer"):
            properties["Answer"] = self._to_rich_text(task["answer"])
        if task.get("email_ref"):
            properties["E-mail"] = self._to_rich_text(task["email_ref"])
        if "is_inbox" in task:
            properties["Inbox"] = self._to_checkbox(task["is_inbox"])

        return properties

    # ==========================================
    # Task CRUD Operations
    # ==========================================

    def get_tasks_from_database(self, database_key: str, use_cache: bool = True) -> List[Dict]:
        """
        Get all tasks from a specific database
        database_key: 'juliana' or 'ana'
        """
        if database_key not in TASK_DATABASES:
            return []

        db_info = TASK_DATABASES[database_key]
        database_id = db_info["database_id"]

        # Check cache
        cache_key = f"tasks_{database_key}"
        if use_cache and cache_key in _task_cache:
            if time.time() - _cache_timestamp.get(cache_key, 0) < CACHE_TTL:
                return _task_cache[cache_key]

        # Query Notion
        all_tasks = []
        has_more = True
        start_cursor = None

        while has_more:
            data = {}
            if start_cursor:
                data["start_cursor"] = start_cursor

            result = self._request("POST", f"/databases/{database_id}/query", data)

            if "error" in result:
                break

            pages = result.get("results", [])
            for page in pages:
                task = self.convert_notion_to_task(page, source=database_key)
                task["source_name"] = db_info["name"]
                task["source_color"] = db_info["color"]
                all_tasks.append(task)

            has_more = result.get("has_more", False)
            start_cursor = result.get("next_cursor")

        # Update cache
        _task_cache[cache_key] = all_tasks
        _cache_timestamp[cache_key] = time.time()

        return all_tasks

    def get_all_tasks(self, use_cache: bool = True) -> List[Dict]:
        """Get tasks from all databases"""
        all_tasks = []
        for key in TASK_DATABASES:
            tasks = self.get_tasks_from_database(key, use_cache)
            all_tasks.extend(tasks)

        # Sort by due_date (nulls last), then by priority
        priority_order = {"Urgente": 0, "Alta": 1, "Normal": 2, "Baixa": 3, "": 4}

        def sort_key(t):
            due = t.get("due_date") or "9999-99-99"
            prio = priority_order.get(t.get("priority", ""), 4)
            return (due, prio)

        return sorted(all_tasks, key=sort_key)

    def create_task(self, database_key: str, task_data: Dict) -> Dict:
        """Create a new task in Notion"""
        if database_key not in TASK_DATABASES:
            return {"error": f"Invalid database key: {database_key}"}

        database_id = TASK_DATABASES[database_key]["database_id"]
        properties = self.convert_task_to_notion(task_data)

        result = self._request("POST", "/pages", {
            "parent": {"database_id": database_id},
            "properties": properties
        })

        # Invalidate cache
        self._invalidate_cache(database_key)

        return result

    def update_task(self, page_id: str, updates: Dict) -> Dict:
        """Update a task in Notion"""
        properties = self.convert_task_to_notion(updates)
        result = self._request("PATCH", f"/pages/{page_id}", {"properties": properties})

        # Invalidate all caches (we don't know which database it belongs to)
        for key in TASK_DATABASES:
            self._invalidate_cache(key)

        return result

    def update_task_status(self, page_id: str, status: str) -> Dict:
        """Quick update for task status"""
        return self.update_task(page_id, {"status": status})

    def archive_task(self, page_id: str) -> Dict:
        """Archive (soft delete) a task in Notion"""
        result = self._request("PATCH", f"/pages/{page_id}", {"archived": True})

        # Invalidate all caches
        for key in TASK_DATABASES:
            self._invalidate_cache(key)

        return result

    def _invalidate_cache(self, database_key: str = None):
        """Invalidate task cache"""
        global _task_cache, _cache_timestamp
        if database_key:
            cache_key = f"tasks_{database_key}"
            _task_cache.pop(cache_key, None)
            _cache_timestamp.pop(cache_key, None)
        else:
            _task_cache = {}
            _cache_timestamp = {}

    # ==========================================
    # Utility Methods
    # ==========================================

    def get_database_info(self) -> Dict:
        """Get information about configured databases"""
        return TASK_DATABASES

    def test_connection(self) -> Dict:
        """Test Notion API connection"""
        result = self._request("GET", "/users/me")
        if "error" in result:
            return {"success": False, "error": result["error"]}
        return {
            "success": True,
            "user": result.get("name", "Unknown"),
            "type": result.get("type", "Unknown")
        }

    def get_unique_values(self, field: str) -> List[str]:
        """Get unique values for a field across all tasks (for filters)"""
        all_tasks = self.get_all_tasks()
        values = set()

        for task in all_tasks:
            val = task.get(field)
            if isinstance(val, list):
                values.update(val)
            elif val:
                values.add(val)

        return sorted(list(values))



    # ==========================================
    # Notification Methods (3-tier cascade)
    # ==========================================

    def _build_mention_rich_text(self, user_key: str, prefix_text: str = "") -> List[Dict]:
        """Build rich text array with @mention for a user."""
        user_info = NOTION_USER_IDS.get(user_key)
        if not user_info or not user_info.get("id"):
            fallback_name = user_info.get("name", user_key) if user_info else user_key
            return [{"text": {"content": prefix_text + fallback_name}}]
        
        result = []
        if prefix_text:
            result.append({"text": {"content": prefix_text}})
        
        result.append({
            "type": "mention",
            "mention": {
                "type": "user",
                "user": {"id": user_info["id"]}
            }
        })
        return result

    def add_comment_with_mention(self, page_id: str, user_key: str, message: str = "") -> Dict:
        """Add a comment to a page with @mention (Tier 3 of notification cascade)."""
        user_info = NOTION_USER_IDS.get(user_key)
        
        rich_text = []
        
        if user_info and user_info.get("id"):
            rich_text.append({
                "type": "mention",
                "mention": {
                    "type": "user",
                    "user": {"id": user_info["id"]}
                }
            })
            rich_text.append({"type": "text", "text": {"content": " "}})
        
        if message:
            rich_text.append({"type": "text", "text": {"content": message}})
        else:
            rich_text.append({"type": "text", "text": {"content": "Nova tarefa criada!"}})
        
        return self._request("POST", "/comments", {
            "parent": {"page_id": page_id},
            "rich_text": rich_text
        })

    def create_task_with_notification(self, database_key: str, task_data: Dict, notify: bool = True) -> Dict:
        """
        Create a task with 3-tier notification cascade:
        1. @mention in task description
        2. Add to Assigned To field
        3. Comment with @mention
        """
        result = {
            "task": None,
            "notifications": {
                "mention_in_description": False,
                "assigned_to": False,
                "comment": False
            }
        }
        
        user_info = NOTION_USER_IDS.get(database_key)
        user_id = user_info.get("id") if user_info else None
        user_name = user_info.get("name") if user_info else database_key.title()
        
        # Tier 1: Add mention prefix to description
        if notify and user_id:
            original_desc = task_data.get("description", "")
            task_data["description"] = "@" + user_name + " - " + original_desc if original_desc else "@" + user_name
            result["notifications"]["mention_in_description"] = True
        
        # Tier 2: Add to Assigned To field
        if notify:
            if "assigned_to" not in task_data or not task_data["assigned_to"]:
                task_data["assigned_to"] = [user_name]
            elif user_name not in task_data["assigned_to"]:
                task_data["assigned_to"].append(user_name)
            result["notifications"]["assigned_to"] = True
        
        # Create the task
        task_result = self.create_task(database_key, task_data)
        result["task"] = task_result
        
        # Tier 3: Add comment with @mention
        if notify and "id" in task_result and user_id:
            page_id = task_result["id"]
            comment_result = self.add_comment_with_mention(
                page_id, 
                database_key,
                "Nova tarefa de email criada automaticamente pelo CaseHub!"
            )
            result["notifications"]["comment"] = "error" not in comment_result
            result["comment_result"] = comment_result
        
        return result



# Singleton instance
notion_tasks_service = NotionTasksService()
