"""
Meeting Watchdog - State Management
Tracks pending proposals, confirmed meetings, processed message IDs.
Provides deduplication and crash recovery.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "data" / "watchdog_state.json"
LOG_FILE = BASE_DIR / "data" / "watchdog_log.json"

MAX_PROCESSED_IDS = 2000


def _load_json(filepath: Path) -> dict:
    """Load JSON file, return empty dict if not found."""
    try:
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Error loading {filepath}: {e}")
    return {}


def _save_json(filepath: Path, data: dict):
    """Save dict to JSON file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def load_state() -> dict:
    """Load watchdog state from disk."""
    state = _load_json(STATE_FILE)
    if not state:
        state = {
            "pending_proposals": [],
            "confirmed_meetings": [],
            "pending_review": [],
            "processed_message_ids": [],
            "last_scan": None,
        }
    return state


def save_state(state: dict):
    """Save watchdog state to disk, trimming processed IDs."""
    if len(state.get("processed_message_ids", [])) > MAX_PROCESSED_IDS:
        state["processed_message_ids"] = state["processed_message_ids"][-MAX_PROCESSED_IDS:]
    _save_json(STATE_FILE, state)


def is_message_processed(state: dict, message_id: str) -> bool:
    """Check if a message ID has already been processed."""
    return message_id in state.get("processed_message_ids", [])


def mark_message_processed(state: dict, message_id: str):
    """Add message ID to processed list."""
    if "processed_message_ids" not in state:
        state["processed_message_ids"] = []
    if message_id not in state["processed_message_ids"]:
        state["processed_message_ids"].append(message_id)


def is_duplicate_meeting(state: dict, client_email: str, confirmed_dt_iso: str) -> bool:
    """Check if a meeting has already been confirmed for this client at this time."""
    for entry in state.get("confirmed_meetings", []):
        if (entry.get("client_email") == client_email
                and entry.get("confirmed_datetime") == confirmed_dt_iso
                and entry.get("event_created")):
            return True
    return False


def add_confirmed_meeting(state: dict, meeting_data: dict):
    """Add a confirmed meeting to state."""
    if "confirmed_meetings" not in state:
        state["confirmed_meetings"] = []
    meeting_data["processed_at"] = datetime.now().isoformat()
    state["confirmed_meetings"].append(meeting_data)


def add_pending_review(state: dict, review_data: dict):
    """Add an item that needs admin review (medium confidence)."""
    if "pending_review" not in state:
        state["pending_review"] = []
    review_data["detected_at"] = datetime.now().isoformat()
    state["pending_review"].append(review_data)


def update_last_scan(state: dict):
    """Update the last scan timestamp."""
    state["last_scan"] = datetime.now().isoformat()


def get_failed_actions(state: dict) -> list:
    """Get confirmed meetings where event creation or email sending failed."""
    failed = []
    for entry in state.get("confirmed_meetings", []):
        if not entry.get("event_created") or not entry.get("confirmation_email_sent"):
            failed.append(entry)
    return failed


def log_action(action: str, details: dict):
    """Append an action to the audit log."""
    log = _load_json(LOG_FILE)
    if "actions" not in log:
        log["actions"] = []
    log["actions"].append({
        "timestamp": datetime.now().isoformat(),
        "action": action,
        **details,
    })
    # Keep last 500 log entries
    if len(log["actions"]) > 500:
        log["actions"] = log["actions"][-500:]
    _save_json(LOG_FILE, log)
