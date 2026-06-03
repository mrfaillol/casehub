"""
CaseHub - Notion Ticket Service
Submit support tickets to Notion for review.
Inherits from NotionTasksService to reuse API infrastructure.
"""
import os
from datetime import datetime
from typing import Dict
from dotenv import load_dotenv
load_dotenv()

from services.notion_tasks import NotionTasksService

TICKET_DATABASE_ID = os.getenv("NOTION_TICKET_DATABASE_ID", "")


class NotionTicketService(NotionTasksService):
    """Lightweight ticket submission to a dedicated Notion database."""

    def create_ticket(self, ticket_data: Dict) -> Dict:
        """Create a ticket page in the Notion tickets database."""
        if not TICKET_DATABASE_ID:
            return {"error": "NOTION_TICKET_DATABASE_ID not configured"}

        properties = {
            "Title": self._to_title(ticket_data.get("title", "Untitled Ticket")),
            "Description": self._to_rich_text(ticket_data.get("description", "")),
            "Category": self._to_select(ticket_data.get("category", "Other")),
            "Severity": self._to_select(ticket_data.get("severity", "Medium")),
            "Reporter": self._to_rich_text(ticket_data.get("reporter_email", "")),
            "Reporter Name": self._to_rich_text(ticket_data.get("reporter_name", "")),
            "Page URL": self._to_url(ticket_data.get("page_url")),
            "Browser": self._to_rich_text(ticket_data.get("browser", "")),
            "CaseHub Version": self._to_rich_text(ticket_data.get("version", "")),
            "Submitted At": self._to_rich_text(ticket_data.get("submitted_at", datetime.now().isoformat())),
            "Environment": self._to_rich_text(ticket_data.get("environment", "")),
        }

        return self._request("POST", "/pages", {
            "parent": {"database_id": TICKET_DATABASE_ID},
            "properties": properties,
            "icon": {"emoji": "\U0001f3ab"}
        })


notion_ticket_service = NotionTicketService()
