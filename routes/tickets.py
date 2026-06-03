"""
CaseHub - Ticket System Routes
One-click ticket submission to Notion.
"""
import json
import os
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from models import get_db
from auth import get_current_user
from services.notion_tickets import notion_ticket_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


@router.post("/submit")
async def submit_ticket(request: Request, db: Session = Depends(get_db)):
    """Submit a support ticket to Notion."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"success": False, "error": "Not authenticated"}, status_code=401)

    data = await request.json()

    title = (data.get("title") or "").strip()
    if not title:
        return JSONResponse({"success": False, "error": "Title is required"}, status_code=400)

    ticket_data = {
        "title": title,
        "description": (data.get("description") or "").strip(),
        "category": data.get("category", "Other"),
        "severity": data.get("severity", "Medium"),
        "reporter_email": user.email,
        "reporter_name": user.name,
        "page_url": data.get("page_url", ""),
        "browser": data.get("browser", ""),
        "version": data.get("version", ""),
        "submitted_at": datetime.now().isoformat(),
        "environment": data.get("environment", ""),
    }

    # Local backup - never lose a ticket
    try:
        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "tickets.jsonl"), "a") as f:
            f.write(json.dumps(ticket_data) + "\n")
    except Exception as e:
        logger.warning(f"Failed to log ticket locally: {e}")

    result = notion_ticket_service.create_ticket(ticket_data)

    if "error" in result:
        logger.error(f"Ticket submission failed: {result['error']}")
        return JSONResponse({
            "success": False,
            "error": "Failed to submit ticket. It has been logged locally."
        }, status_code=500)

    return {
        "success": True,
        "notion_url": result.get("url", ""),
        "ticket_id": result.get("id", ""),
    }
