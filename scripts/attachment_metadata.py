#!/usr/bin/env python3
"""
Attachment Metadata Manager - CaseHub
Manages metadata for email attachments stored on disk.
"""

import os
import json
import uuid
import mimetypes
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Configuration
DATA_DIR = Path(__file__).parent / "data"
ATTACHMENTS_METADATA_FILE = DATA_DIR / "attachments_metadata.json"
ATTACHMENTS_BASE_PATH = Path(os.getenv("ATTACHMENTS_BASE_PATH", str(Path(__file__).parent / "attachments")))


def load_attachments_metadata() -> Dict[str, Any]:
    """Load attachments metadata from JSON file."""
    if not ATTACHMENTS_METADATA_FILE.exists():
        return {"attachments": [], "lastUpdated": datetime.now().isoformat()}

    try:
        with open(ATTACHMENTS_METADATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Error loading attachments metadata: {e}")
        return {"attachments": [], "lastUpdated": datetime.now().isoformat()}


def save_attachments_metadata(data: Dict[str, Any]) -> None:
    """Save attachments metadata to JSON file."""
    data["lastUpdated"] = datetime.now().isoformat()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with open(ATTACHMENTS_METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except IOError as e:
        logger.error(f"Error saving attachments metadata: {e}")


def get_mime_type(filename: str) -> str:
    """Get MIME type for a file based on extension."""
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or "application/octet-stream"


def add_attachment_metadata(
    email_message_id: str,
    client_email: str,
    client_name: str,
    original_filename: str,
    safe_filename: str,
    document_type: str,
    file_path: str,
    file_size: int,
    received_at: str = None,
    thread_id: str = None
) -> str:
    """
    Add metadata for a new attachment.

    Returns:
        The generated attachment ID.
    """
    data = load_attachments_metadata()

    attachment_id = str(uuid.uuid4())

    attachment = {
        "id": attachment_id,
        "email_message_id": email_message_id,
        "thread_id": thread_id,
        "client_email": client_email,
        "client_name": client_name,
        "original_filename": original_filename,
        "safe_filename": safe_filename,
        "document_type": document_type,
        "file_path": file_path,
        "file_size": file_size,
        "mime_type": get_mime_type(original_filename),
        "received_at": received_at or datetime.now().isoformat(),
        "created_at": datetime.now().isoformat()
    }

    data["attachments"].append(attachment)
    save_attachments_metadata(data)

    logger.info(f"Added attachment metadata: {attachment_id} - {original_filename}")
    return attachment_id


def get_attachment_by_id(attachment_id: str) -> Optional[Dict[str, Any]]:
    """Get attachment metadata by ID."""
    data = load_attachments_metadata()

    for attachment in data["attachments"]:
        if attachment.get("id") == attachment_id:
            return attachment

    return None


def get_attachments_by_message_id(email_message_id: str) -> List[Dict[str, Any]]:
    """Get all attachments for a specific email message."""
    data = load_attachments_metadata()

    return [
        att for att in data["attachments"]
        if att.get("email_message_id") == email_message_id
    ]


def get_attachments_by_thread_id(thread_id: str) -> List[Dict[str, Any]]:
    """Get all attachments for a specific thread."""
    data = load_attachments_metadata()

    return [
        att for att in data["attachments"]
        if att.get("thread_id") == thread_id
    ]


def get_attachments_by_client(client_email: str) -> List[Dict[str, Any]]:
    """Get all attachments from a specific client."""
    data = load_attachments_metadata()

    return [
        att for att in data["attachments"]
        if att.get("client_email") == client_email
    ]


def get_attachment_path(attachment_id: str) -> Optional[Path]:
    """
    Get the file path for an attachment, with security validation.

    Returns:
        Path object if valid and exists, None otherwise.
    """
    attachment = get_attachment_by_id(attachment_id)
    if not attachment:
        return None

    file_path = Path(attachment["file_path"])

    # Security: Ensure path is within attachments directory
    try:
        attachments_base = ATTACHMENTS_BASE_PATH.resolve()
        resolved_path = file_path.resolve()

        if not str(resolved_path).startswith(str(attachments_base)):
            logger.warning(f"Path traversal attempt detected: {file_path}")
            return None
    except Exception as e:
        logger.error(f"Path validation error: {e}")
        return None

    if not file_path.exists():
        logger.warning(f"Attachment file not found: {file_path}")
        return None

    return file_path


def update_attachment_thread_id(attachment_id: str, thread_id: str) -> bool:
    """Update the thread_id for an attachment."""
    data = load_attachments_metadata()

    for attachment in data["attachments"]:
        if attachment.get("id") == attachment_id:
            attachment["thread_id"] = thread_id
            save_attachments_metadata(data)
            return True

    return False


def delete_attachment_metadata(attachment_id: str) -> bool:
    """Delete attachment metadata (does not delete the file)."""
    data = load_attachments_metadata()

    original_count = len(data["attachments"])
    data["attachments"] = [
        att for att in data["attachments"]
        if att.get("id") != attachment_id
    ]

    if len(data["attachments"]) < original_count:
        save_attachments_metadata(data)
        return True

    return False


def get_all_attachments(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    """Get all attachments with pagination."""
    data = load_attachments_metadata()

    # Sort by received_at descending (most recent first)
    attachments = sorted(
        data["attachments"],
        key=lambda x: x.get("received_at", ""),
        reverse=True
    )

    return attachments[offset:offset + limit]


def get_attachment_stats() -> Dict[str, Any]:
    """Get statistics about attachments."""
    data = load_attachments_metadata()

    stats = {
        "total_count": len(data["attachments"]),
        "total_size": sum(att.get("file_size", 0) for att in data["attachments"]),
        "by_type": {},
        "by_client": {}
    }

    for att in data["attachments"]:
        # Count by type
        doc_type = att.get("document_type", "Other Document")
        stats["by_type"][doc_type] = stats["by_type"].get(doc_type, 0) + 1

        # Count by client
        client = att.get("client_name", "Unknown")
        stats["by_client"][client] = stats["by_client"].get(client, 0) + 1

    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("Attachment Metadata Manager")
    print("=" * 40)

    # Show current stats
    stats = get_attachment_stats()
    print(f"Total attachments: {stats['total_count']}")
    print(f"Total size: {stats['total_size'] / 1024 / 1024:.2f} MB")
    print(f"By type: {stats['by_type']}")
