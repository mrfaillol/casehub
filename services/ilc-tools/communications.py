#!/usr/bin/env python3
"""
CaseHub - Customer Service Communications Module
Handles weekly/monthly client follow-up communications.
Version: 1.0.0
"""

import os
import json
import logging
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path
import uuid

# Email sending
import resend

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Directories
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Data files
COMM_CLIENTS_FILE = DATA_DIR / "communication_clients.json"
COMMUNICATIONS_FILE = DATA_DIR / "communications.json"
EMAIL_THREADS_FILE = DATA_DIR / "email_threads.json"
COMM_SCHEDULES_FILE = DATA_DIR / "communication_schedules.json"
EMAIL_TEMPLATES_FILE = DATA_DIR / "email_templates.json"

# Email configuration
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
GMAIL_CENTER_EMAIL = os.getenv("GMAIL_CENTER_EMAIL", "center@casehub.app")
GMAIL_CENTER_APP_PASSWORD = os.getenv("GMAIL_CENTER_APP_PASSWORD", "")

# Default sender
FROM_EMAIL = f"CaseHub <info@casehub.app>"

# =============================================================================
# DATA MANAGEMENT - CLIENTS
# =============================================================================

def load_comm_clients() -> Dict[str, Any]:
    """Load communication clients from JSON file."""
    if COMM_CLIENTS_FILE.exists():
        with open(COMM_CLIENTS_FILE, "r") as f:
            return json.load(f)
    return {"clients": [], "lastUpdated": None}


def save_comm_clients(data: Dict[str, Any]) -> None:
    """Save communication clients to JSON file."""
    data["lastUpdated"] = datetime.utcnow().isoformat()
    with open(COMM_CLIENTS_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def get_all_comm_clients() -> List[Dict[str, Any]]:
    """Get all communication clients."""
    data = load_comm_clients()
    return data.get("clients", [])


def get_comm_client_by_id(client_id: str) -> Optional[Dict[str, Any]]:
    """Get a single client by ID."""
    clients = get_all_comm_clients()
    for client in clients:
        if client.get("id") == client_id:
            return client
    return None


def update_comm_client(client_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update a communication client."""
    data = load_comm_clients()
    for i, client in enumerate(data["clients"]):
        if client.get("id") == client_id:
            data["clients"][i].update(updates)
            data["clients"][i]["updated_at"] = datetime.utcnow().isoformat()
            save_comm_clients(data)
            return data["clients"][i]
    raise ValueError(f"Client not found: {client_id}")


def exclude_client(client_id: str, reason: str, excluded_by: str) -> Dict[str, Any]:
    """Add client to exclusion list."""
    return update_comm_client(client_id, {
        "is_excluded": True,
        "exclusion_reason": reason,
        "excluded_at": datetime.utcnow().isoformat(),
        "excluded_by": excluded_by
    })


def include_client(client_id: str) -> Dict[str, Any]:
    """Remove client from exclusion list."""
    return update_comm_client(client_id, {
        "is_excluded": False,
        "exclusion_reason": None,
        "excluded_at": None,
        "excluded_by": None
    })


def load_client_teams() -> Dict[str, Any]:
    """Load client teams and exclusions configuration."""
    teams_file = DATA_DIR / "client_teams.json"
    if teams_file.exists():
        with open(teams_file, "r") as f:
            return json.load(f)
    return {"teams": {}, "exclusions": {"clients": []}}


def get_exclusion_list() -> List[Dict[str, str]]:
    """Get list of clients that should be excluded from communications."""
    config = load_client_teams()
    return config.get("exclusions", {}).get("clients", [])


def should_exclude_client(client_name: str) -> Optional[str]:
    """Check if a client should be excluded based on config. Returns reason if yes."""
    exclusions = get_exclusion_list()
    client_name_lower = (client_name or "").lower().strip()

    for excl in exclusions:
        excl_name = (excl.get("name") or "").lower().strip()
        # Partial match to handle variations like "Philip B Boyett" vs "Phillip Boyett"
        if excl_name in client_name_lower or client_name_lower in excl_name:
            return excl.get("reason", "Listed in exclusion configuration")
        # Also check first + last name match
        excl_parts = excl_name.split()
        client_parts = client_name_lower.split()
        if len(excl_parts) >= 2 and len(client_parts) >= 2:
            if excl_parts[0] == client_parts[0] and excl_parts[-1] == client_parts[-1]:
                return excl.get("reason", "Listed in exclusion configuration")
    return None


def sync_clients_from_json(source_file: str) -> Dict[str, Any]:
    """Sync clients from active-clients.json source file."""
    source_path = Path(source_file)
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_file}")

    with open(source_path, "r") as f:
        source_data = json.load(f)

    existing_data = load_comm_clients()
    existing_emails = {c.get("email", "").lower() for c in existing_data.get("clients", [])}

    new_count = 0
    updated_count = 0
    excluded_count = 0

    for source_client in source_data.get("clients", []):
        email_lower = (source_client.get("email") or "").lower()
        client_name = source_client.get("name", "")

        # Check if client should be excluded
        exclusion_reason = should_exclude_client(client_name)

        # Find existing client
        existing = None
        for i, c in enumerate(existing_data.get("clients", [])):
            if (c.get("email") or "").lower() == email_lower and email_lower:
                existing = (i, c)
                break

        if existing:
            # Update existing
            idx, old_client = existing
            updates = {
                "name": source_client.get("name"),
                "phone": source_client.get("phone"),
                "case_number": source_client.get("caseNumber"),
                "paralegal": source_client.get("paralegal"),
                "country": source_client.get("country"),
                "updated_at": datetime.utcnow().isoformat()
            }

            # Apply exclusion if configured
            if exclusion_reason and not old_client.get("is_excluded"):
                updates["is_excluded"] = True
                updates["exclusion_reason"] = exclusion_reason
                updates["excluded_at"] = datetime.utcnow().isoformat()
                updates["excluded_by"] = "system_config"
                excluded_count += 1

            existing_data["clients"][idx].update(updates)
            updated_count += 1
        else:
            # Add new client
            new_client = {
                "id": str(uuid.uuid4()),
                "name": source_client.get("name"),
                "email": source_client.get("email"),
                "phone": source_client.get("phone"),
                "case_number": source_client.get("caseNumber"),
                "paralegal": source_client.get("paralegal"),
                "country": source_client.get("country"),
                "moskit_id": None,
                "is_excluded": False,
                "exclusion_reason": None,
                "excluded_at": None,
                "excluded_by": None,
                "weekly_enabled": True,
                "monthly_enabled": True,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }

            # Auto-exclude clients without email
            if not source_client.get("email"):
                new_client["is_excluded"] = True
                new_client["exclusion_reason"] = "No email address"
                excluded_count += 1
            # Apply exclusion from config
            elif exclusion_reason:
                new_client["is_excluded"] = True
                new_client["exclusion_reason"] = exclusion_reason
                new_client["excluded_at"] = datetime.utcnow().isoformat()
                new_client["excluded_by"] = "system_config"
                excluded_count += 1

            if "clients" not in existing_data:
                existing_data["clients"] = []
            existing_data["clients"].append(new_client)
            new_count += 1

    save_comm_clients(existing_data)

    return {
        "new_clients": new_count,
        "updated_clients": updated_count,
        "excluded_clients": excluded_count,
        "total_clients": len(existing_data.get("clients", []))
    }


# =============================================================================
# DATA MANAGEMENT - COMMUNICATIONS
# =============================================================================

def load_communications() -> Dict[str, Any]:
    """Load communications history from JSON file."""
    if COMMUNICATIONS_FILE.exists():
        with open(COMMUNICATIONS_FILE, "r") as f:
            return json.load(f)
    return {"communications": [], "lastUpdated": None}


def save_communications(data: Dict[str, Any]) -> None:
    """Save communications history to JSON file."""
    data["lastUpdated"] = datetime.utcnow().isoformat()
    with open(COMMUNICATIONS_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def add_communication(comm: Dict[str, Any]) -> Dict[str, Any]:
    """Add a new communication record."""
    data = load_communications()
    comm["id"] = str(uuid.uuid4())
    comm["created_at"] = datetime.utcnow().isoformat()
    if "communications" not in data:
        data["communications"] = []
    data["communications"].append(comm)
    save_communications(data)
    return comm


def update_communication(comm_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update a communication record."""
    data = load_communications()
    for i, comm in enumerate(data.get("communications", [])):
        if comm.get("id") == comm_id:
            data["communications"][i].update(updates)
            save_communications(data)
            return data["communications"][i]
    raise ValueError(f"Communication not found: {comm_id}")


def get_communications_history(
    client_id: Optional[str] = None,
    comm_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """Get communications history with filters."""
    data = load_communications()
    comms = data.get("communications", [])

    # Apply filters
    if client_id:
        comms = [c for c in comms if c.get("client_id") == client_id]
    if comm_type:
        comms = [c for c in comms if c.get("type") == comm_type]
    if status:
        comms = [c for c in comms if c.get("status") == status]

    # Sort by created_at descending
    comms.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    # Apply pagination
    return comms[offset:offset + limit]


def get_client_last_communication(client_id: str, comm_type: str) -> Optional[Dict[str, Any]]:
    """Get the last communication of a specific type for a client."""
    comms = get_communications_history(client_id=client_id, comm_type=comm_type, limit=1)
    return comms[0] if comms else None


# =============================================================================
# DATA MANAGEMENT - SCHEDULES
# =============================================================================

def load_schedules() -> Dict[str, Any]:
    """Load communication schedules from JSON file."""
    if COMM_SCHEDULES_FILE.exists():
        with open(COMM_SCHEDULES_FILE, "r") as f:
            return json.load(f)
    # Default schedules
    return {
        "schedules": [
            {
                "id": "weekly",
                "type": "weekly",
                "is_active": True,
                "day_of_week": 0,  # Monday
                "day_of_month": None,
                "hour": 9,
                "minute": 0,
                "timezone": "America/New_York",
                "last_run_at": None,
                "last_run_status": None,
                "next_scheduled_at": None
            },
            {
                "id": "monthly",
                "type": "monthly",
                "is_active": True,
                "day_of_week": None,
                "day_of_month": 1,
                "hour": 9,
                "minute": 0,
                "timezone": "America/New_York",
                "last_run_at": None,
                "last_run_status": None,
                "next_scheduled_at": None
            }
        ],
        "lastUpdated": None
    }


def save_schedules(data: Dict[str, Any]) -> None:
    """Save communication schedules to JSON file."""
    data["lastUpdated"] = datetime.utcnow().isoformat()
    with open(COMM_SCHEDULES_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def get_schedules() -> List[Dict[str, Any]]:
    """Get all schedules."""
    data = load_schedules()
    return data.get("schedules", [])


def update_schedule(schedule_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update a schedule."""
    data = load_schedules()
    for i, schedule in enumerate(data.get("schedules", [])):
        if schedule.get("id") == schedule_id:
            data["schedules"][i].update(updates)
            save_schedules(data)
            return data["schedules"][i]
    raise ValueError(f"Schedule not found: {schedule_id}")


# =============================================================================
# DATA MANAGEMENT - EMAIL TEMPLATES
# =============================================================================

def load_templates() -> Dict[str, Any]:
    """Load email templates from JSON file."""
    if EMAIL_TEMPLATES_FILE.exists():
        with open(EMAIL_TEMPLATES_FILE, "r") as f:
            return json.load(f)
    # Default templates
    return {
        "templates": [
            {
                "id": "weekly",
                "type": "weekly",
                "name": "Weekly Check-In",
                "subject": "Weekly Check-In - CaseHub",
                "body_html": """<p>Dear {client_name},</p>
<p>We hope you are doing well.</p>
<p>This is a brief weekly check-in to see if you have any questions or need any assistance at this time. Our team remains available and happy to support you with anything you may need.</p>
<p>Please feel free to reach out at your convenience.</p>
<p>Warm regards,<br>CaseHub</p>""",
                "body_text": """Dear {client_name},

We hope you are doing well.

This is a brief weekly check-in to see if you have any questions or need any assistance at this time. Our team remains available and happy to support you with anything you may need.

Please feel free to reach out at your convenience.

Warm regards,
CaseHub""",
                "is_active": True
            },
            {
                "id": "monthly",
                "type": "monthly",
                "name": "Monthly Follow-Up",
                "subject": "Monthly Follow-Up - CaseHub",
                "body_html": """<p>Dear {client_name},</p>
<p>We hope this message finds you well.</p>
<p>As part of our monthly follow-up, we would like to check in to see if you have any questions, concerns, or if there is anything we can assist you with regarding your case.</p>
<p>Please do not hesitate to contact us if you need any clarification or support.</p>
<p>Warm regards,<br>CaseHub</p>""",
                "body_text": """Dear {client_name},

We hope this message finds you well.

As part of our monthly follow-up, we would like to check in to see if you have any questions, concerns, or if there is anything we can assist you with regarding your case.

Please do not hesitate to contact us if you need any clarification or support.

Warm regards,
CaseHub""",
                "is_active": True
            }
        ],
        "lastUpdated": None
    }


def save_templates(data: Dict[str, Any]) -> None:
    """Save email templates to JSON file."""
    data["lastUpdated"] = datetime.utcnow().isoformat()
    with open(EMAIL_TEMPLATES_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def get_templates() -> List[Dict[str, Any]]:
    """Get all email templates."""
    data = load_templates()
    return data.get("templates", [])


def get_template_by_type(template_type: str) -> Optional[Dict[str, Any]]:
    """Get template by type (weekly/monthly)."""
    templates = get_templates()
    for t in templates:
        if t.get("type") == template_type and t.get("is_active"):
            return t
    return None


def update_template(template_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update an email template."""
    data = load_templates()
    for i, template in enumerate(data.get("templates", [])):
        if template.get("id") == template_id:
            data["templates"][i].update(updates)
            save_templates(data)
            return data["templates"][i]
    raise ValueError(f"Template not found: {template_id}")


# =============================================================================
# EMAIL SENDING (Resend API)
# =============================================================================

def send_followup_email(
    client: Dict[str, Any],
    template_type: str,
    test_mode: bool = False,
    test_recipient: Optional[str] = None,
    sent_by: Optional[str] = None
) -> Dict[str, Any]:
    """Send a follow-up email to a client."""
    if not RESEND_API_KEY:
        raise ValueError("RESEND_API_KEY not configured")

    resend.api_key = RESEND_API_KEY

    template = get_template_by_type(template_type)
    if not template:
        raise ValueError(f"Template not found: {template_type}")

    client_name = client.get("name", "Client")
    recipient = test_recipient if test_mode else client.get("email")

    if not recipient:
        raise ValueError(f"No email address for client: {client_name}")

    # Render template
    subject = template["subject"]
    body_html = template["body_html"].replace("{client_name}", client_name)
    body_text = template["body_text"].replace("{client_name}", client_name)

    # Create communication record
    comm_record = add_communication({
        "client_id": client.get("id"),
        "client_name": client_name,
        "type": template_type,
        "status": "pending",
        "recipient_email": recipient,
        "subject": subject,
        "body_preview": body_text[:200],
        "is_test_mode": test_mode,
        "sent_by": sent_by,
        "scheduled_for": datetime.utcnow().isoformat()
    })

    try:
        # Send email via Resend
        response = resend.Emails.send({
            "from": FROM_EMAIL,
            "to": [recipient],
            "subject": subject,
            "html": body_html,
            "text": body_text
        })

        # Update record with success
        update_communication(comm_record["id"], {
            "status": "sent",
            "sent_at": datetime.utcnow().isoformat(),
            "resend_email_id": response.get("id")
        })

        logger.info(f"Email sent to {recipient} ({template_type})")
        return {"success": True, "email_id": response.get("id"), "communication_id": comm_record["id"]}

    except Exception as e:
        # Update record with failure
        update_communication(comm_record["id"], {
            "status": "failed",
            "failed_at": datetime.utcnow().isoformat(),
            "error_message": str(e)
        })

        logger.error(f"Failed to send email to {recipient}: {e}")
        return {"success": False, "error": str(e), "communication_id": comm_record["id"]}


def send_batch_followups(
    template_type: str,
    test_mode: bool = False,
    test_recipient: Optional[str] = None,
    sent_by: Optional[str] = None
) -> Dict[str, Any]:
    """Send batch follow-up emails to all eligible clients."""
    clients = get_all_comm_clients()

    # Filter eligible clients
    eligible = []
    for client in clients:
        if client.get("is_excluded"):
            continue
        if not client.get("email"):
            continue
        if template_type == "weekly" and not client.get("weekly_enabled", True):
            continue
        if template_type == "monthly" and not client.get("monthly_enabled", True):
            continue
        eligible.append(client)

    results = {
        "total": len(eligible),
        "sent": 0,
        "failed": 0,
        "errors": []
    }

    import time
    for client in eligible:
        result = send_followup_email(
            client=client,
            template_type=template_type,
            test_mode=test_mode,
            test_recipient=test_recipient,
            sent_by=sent_by
        )

        if result.get("success"):
            results["sent"] += 1
        else:
            results["failed"] += 1
            results["errors"].append({
                "client": client.get("name"),
                "error": result.get("error")
            })

        # Rate limiting - 6 seconds between emails
        if not test_mode:
            time.sleep(6)

    # Update schedule
    try:
        update_schedule(template_type, {
            "last_run_at": datetime.utcnow().isoformat(),
            "last_run_status": "success" if results["failed"] == 0 else "partial"
        })
    except ValueError:
        pass

    return results


# =============================================================================
# GMAIL IMAP INTEGRATION (Reading Threads from center@casehub.app)
# =============================================================================

def load_email_threads() -> Dict[str, Any]:
    """Load email threads from JSON file."""
    if EMAIL_THREADS_FILE.exists():
        with open(EMAIL_THREADS_FILE, "r") as f:
            return json.load(f)
    return {"threads": [], "messages": [], "lastUpdated": None}


def save_email_threads(data: Dict[str, Any]) -> None:
    """Save email threads to JSON file."""
    data["lastUpdated"] = datetime.utcnow().isoformat()
    with open(EMAIL_THREADS_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def get_email_threads(client_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get email threads, optionally filtered by client."""
    data = load_email_threads()
    threads = data.get("threads", [])

    if client_id:
        threads = [t for t in threads if t.get("client_id") == client_id]

    # Sort by last message date descending
    threads.sort(key=lambda x: x.get("last_message_at", ""), reverse=True)
    return threads


def get_thread_messages(thread_id: str) -> List[Dict[str, Any]]:
    """Get all messages in a thread."""
    data = load_email_threads()
    messages = [m for m in data.get("messages", []) if m.get("thread_id") == thread_id]
    messages.sort(key=lambda x: x.get("sent_at", ""))
    return messages


def sync_gmail_threads(client_email: Optional[str] = None) -> Dict[str, Any]:
    """Sync email threads from Gmail IMAP for center@casehub.app."""
    if not GMAIL_CENTER_APP_PASSWORD:
        raise ValueError("GMAIL_CENTER_APP_PASSWORD not configured")

    try:
        # Connect to Gmail IMAP
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_CENTER_EMAIL, GMAIL_CENTER_APP_PASSWORD)
        mail.select("INBOX")

        # Get client emails to search for
        clients = get_all_comm_clients()
        client_emails = []

        if client_email:
            client_emails = [client_email]
        else:
            client_emails = [c.get("email") for c in clients if c.get("email")]

        data = load_email_threads()
        new_threads = 0
        new_messages = 0

        for email_addr in client_emails[:20]:  # Limit to 20 clients per sync
            if not email_addr:
                continue

            # Find client
            client = next((c for c in clients if c.get("email", "").lower() == email_addr.lower()), None)
            if not client:
                continue

            # Search for emails from/to this client
            try:
                _, from_msgs = mail.search(None, f'FROM "{email_addr}"')
                _, to_msgs = mail.search(None, f'TO "{email_addr}"')

                msg_ids = set()
                if from_msgs[0]:
                    msg_ids.update(from_msgs[0].split())
                if to_msgs[0]:
                    msg_ids.update(to_msgs[0].split())

                # Process messages (limit to 10 per client)
                for msg_id in list(msg_ids)[:10]:
                    try:
                        _, msg_data = mail.fetch(msg_id, "(RFC822)")
                        msg = email.message_from_bytes(msg_data[0][1])

                        # Extract details
                        message_id = msg.get("Message-ID", str(uuid.uuid4()))
                        references = msg.get("References", "") or msg.get("In-Reply-To", "") or message_id
                        thread_id = references.split()[0] if references else message_id

                        from_addr = msg.get("From", "")
                        to_addr = msg.get("To", "")
                        subject = ""
                        subject_header = msg.get("Subject", "")
                        if subject_header:
                            decoded = decode_header(subject_header)
                            subject = decoded[0][0]
                            if isinstance(subject, bytes):
                                subject = subject.decode(decoded[0][1] or "utf-8")

                        date_str = msg.get("Date", "")

                        # Get body preview
                        body_preview = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        body_preview = payload.decode("utf-8", errors="ignore")[:200]
                                    break
                        else:
                            payload = msg.get_payload(decode=True)
                            if payload:
                                body_preview = payload.decode("utf-8", errors="ignore")[:200]

                        # Direction
                        direction = "inbound" if email_addr.lower() in from_addr.lower() else "outbound"

                        # Check if thread exists
                        existing_thread = next(
                            (t for t in data.get("threads", []) if t.get("gmail_thread_id") == thread_id),
                            None
                        )

                        if not existing_thread:
                            # Create new thread
                            new_thread = {
                                "id": str(uuid.uuid4()),
                                "client_id": client.get("id"),
                                "gmail_thread_id": thread_id,
                                "subject": subject,
                                "message_count": 1,
                                "last_message_at": date_str,
                                "last_message_snippet": body_preview,
                                "last_sender": from_addr,
                                "has_unread": direction == "inbound",
                                "needs_response": direction == "inbound",
                                "created_at": datetime.utcnow().isoformat(),
                                "updated_at": datetime.utcnow().isoformat()
                            }
                            if "threads" not in data:
                                data["threads"] = []
                            data["threads"].append(new_thread)
                            new_threads += 1
                            existing_thread = new_thread
                        else:
                            # Update existing thread
                            existing_thread["message_count"] = existing_thread.get("message_count", 0) + 1
                            existing_thread["last_message_at"] = date_str
                            existing_thread["last_message_snippet"] = body_preview
                            existing_thread["last_sender"] = from_addr
                            existing_thread["updated_at"] = datetime.utcnow().isoformat()

                        # Check if message already exists
                        existing_msg = next(
                            (m for m in data.get("messages", []) if m.get("gmail_message_id") == message_id),
                            None
                        )

                        if not existing_msg:
                            # Add message
                            new_msg = {
                                "id": str(uuid.uuid4()),
                                "thread_id": existing_thread["id"],
                                "gmail_message_id": message_id,
                                "sender": from_addr,
                                "recipient": to_addr,
                                "subject": subject,
                                "snippet": body_preview,
                                "direction": direction,
                                "sent_at": date_str
                            }
                            if "messages" not in data:
                                data["messages"] = []
                            data["messages"].append(new_msg)
                            new_messages += 1

                    except Exception as e:
                        logger.warning(f"Error processing message {msg_id}: {e}")
                        continue

            except Exception as e:
                logger.warning(f"Error searching for {email_addr}: {e}")
                continue

        mail.logout()
        save_email_threads(data)

        return {
            "success": True,
            "new_threads": new_threads,
            "new_messages": new_messages
        }

    except Exception as e:
        logger.error(f"Gmail sync error: {e}")
        return {"success": False, "error": str(e)}


# =============================================================================
# DASHBOARD STATS
# =============================================================================

def get_communications_status() -> Dict[str, Any]:
    """Get dashboard statistics for communications."""
    clients = get_all_comm_clients()
    comms = load_communications().get("communications", [])

    # Count stats
    total_clients = len(clients)
    active_clients = len([c for c in clients if not c.get("is_excluded") and c.get("email")])
    excluded_clients = len([c for c in clients if c.get("is_excluded")])

    # Recent communications (24h)
    now = datetime.utcnow()
    day_ago = now - timedelta(hours=24)

    recent_comms = [
        c for c in comms
        if c.get("created_at") and datetime.fromisoformat(c["created_at"].replace("Z", "")) > day_ago
    ]

    sent_24h = len([c for c in recent_comms if c.get("status") == "sent"])
    failed_24h = len([c for c in recent_comms if c.get("status") == "failed"])

    # Pending (not sent this week for weekly, not sent this month for monthly)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    pending_weekly = 0
    pending_monthly = 0

    for client in clients:
        if client.get("is_excluded") or not client.get("email"):
            continue

        client_comms = [c for c in comms if c.get("client_id") == client.get("id")]

        # Weekly
        if client.get("weekly_enabled", True):
            weekly_comms = [
                c for c in client_comms
                if c.get("type") == "weekly"
                and c.get("status") == "sent"
                and c.get("sent_at")
                and datetime.fromisoformat(c["sent_at"].replace("Z", "")) > week_ago
            ]
            if not weekly_comms:
                pending_weekly += 1

        # Monthly
        if client.get("monthly_enabled", True):
            monthly_comms = [
                c for c in client_comms
                if c.get("type") == "monthly"
                and c.get("status") == "sent"
                and c.get("sent_at")
                and datetime.fromisoformat(c["sent_at"].replace("Z", "")) > month_ago
            ]
            if not monthly_comms:
                pending_monthly += 1

    # Get schedules
    schedules = get_schedules()

    return {
        "total_clients": total_clients,
        "active_clients": active_clients,
        "excluded_clients": excluded_clients,
        "pending_weekly": pending_weekly,
        "pending_monthly": pending_monthly,
        "sent_24h": sent_24h,
        "failed_24h": failed_24h,
        "schedules": schedules
    }


# =============================================================================
# INITIALIZATION
# =============================================================================

def init_communications_data():
    """Initialize communications data files with defaults if they don't exist."""
    # Initialize schedules
    if not COMM_SCHEDULES_FILE.exists():
        save_schedules(load_schedules())
        logger.info("Initialized communication schedules")

    # Initialize templates
    if not EMAIL_TEMPLATES_FILE.exists():
        save_templates(load_templates())
        logger.info("Initialized email templates")

    # Initialize empty clients if not exists
    if not COMM_CLIENTS_FILE.exists():
        save_comm_clients({"clients": []})
        logger.info("Initialized communication clients")

    # Initialize empty communications if not exists
    if not COMMUNICATIONS_FILE.exists():
        save_communications({"communications": []})
        logger.info("Initialized communications history")

    # Initialize empty threads if not exists
    if not EMAIL_THREADS_FILE.exists():
        save_email_threads({"threads": [], "messages": []})
        logger.info("Initialized email threads")


# Initialize on module load
init_communications_data()
