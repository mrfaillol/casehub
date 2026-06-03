#!/usr/bin/env python3
"""
Leads CRM Manager - Standalone leads management for CaseHub.
Manages leads_crm.json with CRUD operations, Moskit sync, Notion sync, and metrics.
"""

import json
import os
import uuid
import re
import shutil
import logging
import threading
import httpx
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from collections import Counter

from config import settings

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
LEGACY_DATA_DIR = BASE_DIR / "data"
DATA_DIR = Path(os.getenv("CASEHUB_LEADS_DATA_DIR") or Path(settings.BASE_DIR) / "data")
LEADS_FILE = DATA_DIR / "leads_crm.json"
BACKUP_DIR = DATA_DIR / "backups"
LEGACY_LEADS_FILE = LEGACY_DATA_DIR / "leads_crm.json"
ROOT_LEADS_FILE = Path(settings.BASE_DIR) / "leads_crm.json"

# Moskit configuration
MOSKIT_API_KEY = settings.MOSKIT_API_KEY
MOSKIT_BASE_URL = "https://api.moskitcrm.com/v2"
MOSKIT_RESPONSIBLE_ID = int(settings.MOSKIT_RESPONSIBLE_ID) if settings.MOSKIT_RESPONSIBLE_ID else 0
MOSKIT_PIPELINE_ID = int(settings.MOSKIT_PIPELINE_ID) if settings.MOSKIT_PIPELINE_ID else 0

MOSKIT_STAGES = {
    "NEW_LEAD": 322283,
    "LEAD_QUALIFICATION": 322808,
    "INTAKE_CALL": 322282,
    "CONSULTATION": 322284,
    "CLOSING": 322809,
    "VISA_IN_PROGRESS": 371211,
}

MOSKIT_STAGE_NAMES = {v: k for k, v in MOSKIT_STAGES.items()}

PATHWAY_CODES = {
    "FAM": "family_based",
    "EMP": "employment_based",
    "ASY": "humanitarian_asylum",
    "VAW": "humanitarian_vawa",
    "UVI": "humanitarian_u_visa",
    "TVI": "humanitarian_t_visa",
    "SIJ": "humanitarian_sijs",
    "INV": "investor",
    "NEW": "",
}

# Conversion feedback: pipeline stage → conversion event mapping
STAGE_CONVERSION_EVENTS = {
    "LEAD_QUALIFICATION": "qualified",
    "INTAKE_CALL": "qualified",
    "CONSULTATION": "consultation_scheduled",
    "CLOSING": "payment_completed",
}

WHATSAPP_BOT_URL = settings.WHATSAPP_BOT_URL


def notify_conversion_feedback(lead: dict, new_stage: str, old_stage: str = None):
    """Notify WhatsApp bot to send conversion events to Facebook/Google when lead advances in pipeline.

    The HTTP call is fire-and-forget telemetry: its result is only logged, no
    caller reads it. It runs on a detached daemon thread so the blocking POST
    (timeout=5.0) never stalls the caller — this is reached from async route
    handlers (update_lead_endpoint, mark-as-converted) via update_lead /
    mark_as_converted, where a synchronous httpx.post would block the loop.
    """
    event = STAGE_CONVERSION_EVENTS.get(new_stage)
    if not event:
        return

    # Don't re-send if moving between stages that map to the same event
    old_event = STAGE_CONVERSION_EVENTS.get(old_stage) if old_stage else None
    if old_event == event:
        return

    payload = {
        "event": event,
        "lead_id": lead.get("id", ""),
        "phone": lead.get("phone", ""),
        "email": lead.get("email", ""),
        "client_name": lead.get("name") or lead.get("whatsapp_name", ""),
        "gclid": lead.get("gclid", ""),
        "fbclid": lead.get("fbclid", ""),
        "source": lead.get("source", ""),
        "lead_score": lead.get("lead_score", 0),
    }

    def _send():
        try:
            resp = httpx.post(
                f"{WHATSAPP_BOT_URL}/api/conversion-feedback",
                json=payload,
                timeout=5.0,
            )
            if resp.status_code == 200:
                logger.info(f"[CONVERSION] Feedback sent: {event} for {payload['client_name'] or payload['phone']}")
            else:
                logger.warning(f"[CONVERSION] Feedback failed ({resp.status_code}): {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"[CONVERSION] Feedback error: {e}")

    threading.Thread(target=_send, name="conversion-feedback", daemon=True).start()


# Notion configuration
NOTION_TOKEN = settings.NOTION_TOKEN  # NEVER hardcode tokens in source code
NOTION_LEADS_DB = os.getenv("NOTION_LEADS_DB", "")
NOTION_API_URL = "https://api.notion.com/v1"

# Brazilian CRM pipeline stages (for Lite product)
STAGES_BR = {
    "PROSPECCAO": {"name": "Prospecção", "color": "#6b7280", "order": 1},
    "CONSULTA": {"name": "Consulta", "color": "#3b82f6", "order": 2},
    "PROPOSTA": {"name": "Proposta", "color": "#f59e0b", "order": 3},
    "CONTRATACAO": {"name": "Contratação", "color": "#1C2447", "order": 4},
    "EM_ANDAMENTO": {"name": "Em Andamento", "color": "#22c55e", "order": 5},
    "ENCERRADO": {"name": "Encerrado", "color": "#9ca3af", "order": 6},
}

# Valid field values (includes both Immigration + BR Lite stages)
VALID_STAGES = list(MOSKIT_STAGES.keys()) + list(STAGES_BR.keys())
VALID_STATUSES = ["new", "contacted", "qualified", "not_qualified", "converted", "lost"]
VALID_LEAD_STATUSES = ["cold", "warm", "qualified", "hot"]
VALID_SOURCES = ["WPP", "MSG", "IG", "SITE", "META", "MANUAL"]


# =============================================================================
# DATA LAYER
# =============================================================================

def load_leads() -> dict:
    """Load leads data from JSON file."""
    if LEADS_FILE.exists():
        with open(LEADS_FILE, "r") as f:
            return json.load(f)
    if LEGACY_LEADS_FILE.exists():
        with open(LEGACY_LEADS_FILE, "r") as f:
            return json.load(f)
    if ROOT_LEADS_FILE.exists():
        with open(ROOT_LEADS_FILE, "r") as f:
            return json.load(f)
    return {
        "version": "1.0.0",
        "last_updated": None,
        "last_moskit_sync": None,
        "last_notion_sync": None,
        "leads": {},
        "indexes": {"by_phone": {}, "by_email": {}, "by_moskit_id": {}, "by_notion_id": {}},
        "sync_log": [],
    }


def save_leads(data: dict) -> None:
    """Save leads data to JSON file with automatic backup."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # Create backup before writing
    if LEADS_FILE.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = BACKUP_DIR / f"leads_crm_{timestamp}.json"
        shutil.copy2(LEADS_FILE, backup_path)

        # Keep only last 10 backups
        backups = sorted(BACKUP_DIR.glob("leads_crm_*.json"), reverse=True)
        for old in backups[10:]:
            old.unlink()

    data["last_updated"] = datetime.now().isoformat()
    with open(LEADS_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str, ensure_ascii=False)

    logger.info(f"Leads saved ({len(data['leads'])} leads)")


def rebuild_indexes(data: dict) -> dict:
    """Rebuild all indexes from leads data."""
    data["indexes"] = {
        "by_phone": {},
        "by_email": {},
        "by_moskit_id": {},
        "by_notion_id": {},
    }
    for lid, lead in data["leads"].items():
        if lead.get("phone"):
            data["indexes"]["by_phone"][lead["phone"]] = lid
        if lead.get("email"):
            data["indexes"]["by_email"][lead["email"].lower()] = lid
        if lead.get("moskit_contact_id"):
            data["indexes"]["by_moskit_id"][str(lead["moskit_contact_id"])] = lid
        if lead.get("notion_page_id"):
            data["indexes"]["by_notion_id"][lead["notion_page_id"]] = lid
    return data


# =============================================================================
# CRUD OPERATIONS
# =============================================================================

def create_lead(data: dict, lead_info: dict) -> dict:
    """Create a new lead and return it."""
    lead_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()

    lead = {
        "id": lead_id,
        "created_at": now,
        "updated_at": now,
        # Identity
        "name": lead_info.get("name", ""),
        "display_name": "",
        "phone": lead_info.get("phone", ""),
        "email": lead_info.get("email", ""),
        "whatsapp_name": lead_info.get("whatsapp_name", ""),
        "language": lead_info.get("language", ""),
        # Source
        "source": lead_info.get("source", "MANUAL"),
        "source_detail": lead_info.get("source_detail", ""),
        "utm_source": lead_info.get("utm_source", ""),
        "utm_medium": lead_info.get("utm_medium", ""),
        "utm_campaign": lead_info.get("utm_campaign", ""),
        "utm_content": lead_info.get("utm_content", ""),
        "utm_term": lead_info.get("utm_term", ""),
        "gclid": lead_info.get("gclid", ""),
        "fbclid": lead_info.get("fbclid", ""),
        # Pipeline
        "pipeline_stage": lead_info.get("pipeline_stage", "NEW_LEAD"),
        "status": lead_info.get("status", "new"),
        "lead_status": lead_info.get("lead_status", "cold"),
        "conversation_state": lead_info.get("conversation_state", ""),
        # Scoring
        "lead_score": lead_info.get("lead_score", 0),
        "score_factors": lead_info.get("score_factors", []),
        "intake_form_final_score": lead_info.get("intake_form_final_score", None),
        "intake_form_primary_pathway": lead_info.get("intake_form_primary_pathway", ""),
        # Interest
        "visa_interest": lead_info.get("visa_interest", ""),
        "profession": lead_info.get("profession", ""),
        "is_urgent": lead_info.get("is_urgent", False),
        # Consultation
        "consultation_type": lead_info.get("consultation_type", None),
        "consultation_date": lead_info.get("consultation_date", None),
        "consultation_scheduled": lead_info.get("consultation_scheduled", False),
        "payment_status": lead_info.get("payment_status", None),
        "payment_amount": lead_info.get("payment_amount", None),
        # Communication
        "message_count": lead_info.get("message_count", 0),
        "last_message_at": lead_info.get("last_message_at", None),
        "first_contact_at": lead_info.get("first_contact_at", now),
        "notes": lead_info.get("notes", ""),
        "communication_log": lead_info.get("communication_log", []),
        # External IDs
        "moskit_contact_id": lead_info.get("moskit_contact_id", None),
        "moskit_deal_id": lead_info.get("moskit_deal_id", None),
        "moskit_sent": lead_info.get("moskit_sent", False),
        "moskit_stage_id": lead_info.get("moskit_stage_id", None),
        "notion_page_id": lead_info.get("notion_page_id", None),
        "notion_synced": lead_info.get("notion_synced", False),
        # Metadata
        "assigned_to": lead_info.get("assigned_to", None),
        "auto_registered": lead_info.get("auto_registered", False),
        "tags": lead_info.get("tags", []),
        "is_deleted": False,
        # Brazilian Lite fields
        "area_atuacao": lead_info.get("area_atuacao", ""),
        "valor_causa": lead_info.get("valor_causa", ""),
        "comarca": lead_info.get("comarca", ""),
        "indicado_por": lead_info.get("indicado_por", ""),
    }

    # Build display name
    lead["display_name"] = format_display_name(lead)

    # Store in data
    data["leads"][lead_id] = lead

    # Update indexes
    if lead["phone"]:
        data["indexes"]["by_phone"][lead["phone"]] = lead_id
    if lead["email"]:
        data["indexes"]["by_email"][lead["email"].lower()] = lead_id
    if lead["moskit_contact_id"]:
        data["indexes"]["by_moskit_id"][str(lead["moskit_contact_id"])] = lead_id

    return lead


def update_lead(data: dict, lead_id: str, updates: dict) -> dict:
    """Update a lead's fields with automatic tracking of stage and score changes."""
    if lead_id not in data["leads"]:
        raise ValueError(f"Lead not found: {lead_id}")

    lead = data["leads"][lead_id]
    now = datetime.now().isoformat()

    # Remove old index entries if changing indexed fields
    if "phone" in updates and updates["phone"] != lead.get("phone"):
        old_phone = lead.get("phone")
        if old_phone and old_phone in data["indexes"]["by_phone"]:
            del data["indexes"]["by_phone"][old_phone]
    if "email" in updates and updates["email"] != lead.get("email"):
        old_email = lead.get("email", "").lower()
        if old_email and old_email in data["indexes"]["by_email"]:
            del data["indexes"]["by_email"][old_email]

    # Track stage changes in stage_history
    old_stage = lead.get("pipeline_stage")
    if "pipeline_stage" in updates and updates["pipeline_stage"] != old_stage:
        if "stage_history" not in lead:
            lead["stage_history"] = []
        # Close previous stage entry
        if lead["stage_history"]:
            lead["stage_history"][-1]["exited_at"] = now
        # Open new stage entry
        lead["stage_history"].append({
            "stage": updates["pipeline_stage"],
            "previous_stage": old_stage,
            "entered_at": now,
            "exited_at": None,
        })
        # Keep last 20 entries
        lead["stage_history"] = lead["stage_history"][-20:]

        # Send conversion feedback to Facebook/Google via WhatsApp bot
        try:
            notify_conversion_feedback(lead, updates["pipeline_stage"], old_stage)
        except Exception as e:
            logger.warning(f"[CONVERSION] notify error: {e}")

    # Track score changes in score_history
    if "lead_score" in updates and updates["lead_score"] != lead.get("lead_score"):
        if "score_history" not in lead:
            lead["score_history"] = []
        lead["score_history"].append({
            "score": updates["lead_score"],
            "previous": lead.get("lead_score", 0),
            "timestamp": now,
        })
        # Keep last 20 entries
        lead["score_history"] = lead["score_history"][-20:]

    # Apply updates
    for key, value in updates.items():
        if key in ("id", "created_at"):  # Protected fields
            continue
        lead[key] = value

    lead["updated_at"] = now
    lead["last_activity_at"] = now
    lead["display_name"] = format_display_name(lead)

    # Update indexes
    if lead.get("phone"):
        data["indexes"]["by_phone"][lead["phone"]] = lead_id
    if lead.get("email"):
        data["indexes"]["by_email"][lead["email"].lower()] = lead_id
    if lead.get("moskit_contact_id"):
        data["indexes"]["by_moskit_id"][str(lead["moskit_contact_id"])] = lead_id

    return lead


def delete_lead(data: dict, lead_id: str) -> bool:
    """Soft-delete a lead."""
    if lead_id not in data["leads"]:
        raise ValueError(f"Lead not found: {lead_id}")
    data["leads"][lead_id]["is_deleted"] = True
    data["leads"][lead_id]["updated_at"] = datetime.now().isoformat()
    return True


def add_note(data: dict, lead_id: str, content: str, note_type: str = "note", actor: str = "staff") -> dict:
    """Add a note/communication entry to a lead."""
    if lead_id not in data["leads"]:
        raise ValueError(f"Lead not found: {lead_id}")

    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": note_type,
        "direction": "outbound" if actor == "staff" else "inbound",
        "summary": content,
        "actor": actor,
    }

    lead = data["leads"][lead_id]
    if "communication_log" not in lead:
        lead["communication_log"] = []
    lead["communication_log"].append(entry)

    # Keep only last 50 entries
    lead["communication_log"] = lead["communication_log"][-50:]
    lead["updated_at"] = datetime.now().isoformat()

    return entry


# =============================================================================
# QUERY & SEARCH
# =============================================================================

def find_by_phone(data: dict, phone: str) -> Optional[dict]:
    """Find a lead by phone number."""
    clean = re.sub(r"[^\d]", "", phone)
    lead_id = data["indexes"]["by_phone"].get(clean)
    if lead_id and lead_id in data["leads"]:
        return data["leads"][lead_id]
    # Fallback: brute-force search
    for lid, lead in data["leads"].items():
        if re.sub(r"[^\d]", "", lead.get("phone", "")) == clean:
            return lead
    return None


def find_by_moskit_id(data: dict, moskit_id: int) -> Optional[dict]:
    """Find a lead by Moskit contact ID."""
    lead_id = data["indexes"]["by_moskit_id"].get(str(moskit_id))
    if lead_id and lead_id in data["leads"]:
        return data["leads"][lead_id]
    return None


def get_all_leads(
    data: dict,
    search: str = None,
    stage: str = None,
    source: str = None,
    status: str = None,
    lead_status: str = None,
    score_min: int = None,
    score_max: int = None,
    date_from: str = None,
    date_to: str = None,
    sort_by: str = "updated_at",
    sort_order: str = "desc",
    page: int = 1,
    per_page: int = 50,
    include_deleted: bool = False,
) -> Tuple[List[dict], int]:
    """Get leads with filters, search, sort, and pagination. Returns (leads, total_count)."""
    leads = list(data["leads"].values())

    # Filter deleted
    if not include_deleted:
        leads = [l for l in leads if not l.get("is_deleted", False)]

    # Apply filters
    if stage:
        leads = [l for l in leads if l.get("pipeline_stage") == stage]
    if source:
        leads = [l for l in leads if l.get("source") == source]
    if status:
        leads = [l for l in leads if l.get("status") == status]
    if lead_status:
        leads = [l for l in leads if l.get("lead_status") == lead_status]
    if score_min is not None:
        leads = [l for l in leads if (l.get("lead_score") or 0) >= score_min]
    if score_max is not None:
        leads = [l for l in leads if (l.get("lead_score") or 0) <= score_max]
    if date_from:
        leads = [l for l in leads if l.get("created_at", "") >= date_from]
    if date_to:
        leads = [l for l in leads if l.get("created_at", "") <= date_to]

    # Search
    if search:
        search_lower = search.lower()
        leads = [
            l for l in leads
            if search_lower in (l.get("name") or "").lower()
            or search_lower in (l.get("phone") or "").lower()
            or search_lower in (l.get("email") or "").lower()
            or search_lower in (l.get("visa_interest") or "").lower()
            or search_lower in (l.get("notes") or "").lower()
        ]

    total = len(leads)

    # Sort (handle mixed types by converting to comparable values)
    reverse = sort_order == "desc"
    def sort_key(l):
        val = l.get(sort_by)
        if val is None:
            return (0, "") if isinstance(l.get("lead_score"), int) else (0, "")
        if isinstance(val, (int, float)):
            return (1, val)
        return (1, str(val))
    leads.sort(key=sort_key, reverse=reverse)

    # Paginate
    start = (page - 1) * per_page
    end = start + per_page
    return leads[start:end], total


# =============================================================================
# HELPERS
# =============================================================================

def infer_pathway_from_fields(lead: dict) -> str:
    """Infer immigration pathway from visa_interest or other lead fields.
    Returns pathway string (e.g. 'family_based') or empty string if unknown.
    """
    interest = (lead.get("visa_interest") or lead.get("interest") or "").lower()
    message = (lead.get("message") or lead.get("notes") or "").lower()
    text = f"{interest} {message}"

    if not text.strip():
        return ""

    # Family-based keywords
    if any(k in text for k in ["family", "spouse", "marriage", "husband", "wife", "parent", "child", "fianc"]):
        return "family_based"
    # Employment-based keywords
    if any(k in text for k in ["work", "employ", "job", "h-1b", "h1b", "eb-", "labor", "perm", "niw", "eb1", "eb2", "eb3"]):
        return "employment_based"
    # Asylum keywords
    if any(k in text for k in ["asylum", "refugee", "persecution", "fear", "political"]):
        return "humanitarian_asylum"
    # VAWA keywords
    if any(k in text for k in ["vawa", "violence", "abuse", "domestic", "batter"]):
        return "humanitarian_vawa"
    # U visa keywords
    if any(k in text for k in ["u visa", "u-visa", "crime victim", "u nonimmigrant"]):
        return "humanitarian_u_visa"
    # T visa keywords
    if any(k in text for k in ["t visa", "t-visa", "trafficking", "t nonimmigrant"]):
        return "humanitarian_t_visa"
    # SIJS keywords
    if any(k in text for k in ["sijs", "juvenile", "minor", "abandoned", "neglect"]):
        return "humanitarian_sijs"
    # Investor keywords
    if any(k in text for k in ["invest", "eb-5", "eb5", "entrepreneur"]):
        return "investor"

    return ""


def format_display_name(lead: dict) -> str:
    """Format display name in [LEAD SOURCE SCORE PATHWAY] Name format."""
    source = lead.get("source", "MANUAL")
    score = lead.get("lead_score", 0)
    pathway = lead.get("intake_form_primary_pathway", "")

    # Get pathway code (NEW = not yet qualified, never UNK)
    pathway_code = "NEW"
    for code, full in PATHWAY_CODES.items():
        if pathway == full:
            pathway_code = code
            break

    name = lead.get("name") or lead.get("whatsapp_name") or "Unknown"
    return f"[LEAD {source} {score} {pathway_code}] {name}"


def parse_lead_name(name: str) -> dict:
    """Parse [LEAD WPP 75 FAM] Maria Silva format."""
    match = re.match(r"\[LEAD\s+(\w+)\s+(\d+)\s*(\w*)\]\s*(.*)", name)
    if match:
        return {
            "source": match.group(1),
            "lead_score": int(match.group(2)),
            "pathway_code": match.group(3) or "NEW",
            "clean_name": match.group(4).strip(),
        }
    # Try simpler format [LEAD WPP] Name
    match2 = re.match(r"\[LEAD\s+(\w+)\]\s*(.*)", name)
    if match2:
        return {
            "source": match2.group(1),
            "lead_score": 0,
            "pathway_code": "NEW",
            "clean_name": match2.group(2).strip(),
        }
    return {"clean_name": name.strip()}


def get_score_status(score: int) -> str:
    """Get lead status based on score."""
    if score >= 70:
        return "hot"
    if score >= 50:
        return "qualified"
    if score >= 30:
        return "warm"
    return "cold"


def get_stage_from_score(score: int) -> str:
    """Get pipeline stage from score."""
    if score >= 80:
        return "INTAKE_CALL"
    if score >= 50:
        return "LEAD_QUALIFICATION"
    return "NEW_LEAD"


# =============================================================================
# MOSKIT SYNC
# =============================================================================

async def fetch_moskit_contacts() -> List[dict]:
    """Fetch all contacts from Moskit API."""
    contacts = []
    offset = 0
    limit = 200

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            try:
                response = await client.get(
                    f"{MOSKIT_BASE_URL}/contacts",
                    headers={"apikey": MOSKIT_API_KEY},
                    params={"limit": limit, "offset": offset},
                )
                response.raise_for_status()
                batch = response.json()

                if not batch:
                    break

                contacts.extend(batch)
                logger.info(f"Fetched {len(batch)} contacts (offset={offset})")

                if len(batch) < limit:
                    break
                offset += limit
            except Exception as e:
                logger.error(f"Moskit fetch error at offset {offset}: {e}")
                break

    return contacts


async def fetch_moskit_deals_for_contact(contact_id: int) -> List[dict]:
    """Fetch deals for a specific Moskit contact."""
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            response = await client.get(
                f"{MOSKIT_BASE_URL}/deals",
                headers={"apikey": MOSKIT_API_KEY},
                params={"contact": contact_id},
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Moskit deals fetch error for contact {contact_id}: {e}")
            return []


async def sync_from_moskit(data: dict) -> dict:
    """Import/sync all leads from Moskit API to CRM."""
    contacts = await fetch_moskit_contacts()

    imported = 0
    updated = 0
    skipped = 0
    errors = []

    for contact in contacts:
        try:
            name = contact.get("name", "")

            # Only process leads (those with [LEAD ...] format)
            if not re.match(r"\[LEAD", name):
                skipped += 1
                continue

            parsed = parse_lead_name(name)
            contact_id = contact.get("id")

            # Extract phone and email from Moskit contact
            phones = contact.get("phones", [])
            emails = contact.get("emails", [])
            phone = phones[0].get("number", "").replace("+", "") if phones else ""
            email = emails[0].get("address", "") if emails else ""

            # Clean phone
            phone = re.sub(r"[^\d]", "", phone)

            # Check if already exists
            existing = find_by_moskit_id(data, contact_id)
            if not existing and phone:
                existing = find_by_phone(data, phone)

            if existing:
                # Update existing lead with Moskit data
                updates = {
                    "moskit_contact_id": contact_id,
                    "moskit_sent": True,
                }
                if not existing.get("name") and parsed.get("clean_name"):
                    updates["name"] = parsed["clean_name"]
                if not existing.get("email") and email:
                    updates["email"] = email

                update_lead(data, existing["id"], updates)
                updated += 1
            else:
                # Create new lead from Moskit data
                pathway_code = parsed.get("pathway_code", "NEW")
                pathway = PATHWAY_CODES.get(pathway_code, "unknown")

                lead_info = {
                    "name": parsed.get("clean_name", name),
                    "phone": phone,
                    "email": email,
                    "source": parsed.get("source", "WPP"),
                    "lead_score": parsed.get("lead_score", 0),
                    "lead_status": get_score_status(parsed.get("lead_score", 0)),
                    "pipeline_stage": get_stage_from_score(parsed.get("lead_score", 0)),
                    "intake_form_primary_pathway": pathway,
                    "moskit_contact_id": contact_id,
                    "moskit_sent": True,
                    "notes": contact.get("notes", ""),
                    "first_contact_at": contact.get("createdDate", datetime.now().isoformat()),
                }

                # Fetch deals to get stage info
                deals = await fetch_moskit_deals_for_contact(contact_id)
                if deals:
                    deal = deals[0]  # Primary deal
                    lead_info["moskit_deal_id"] = deal.get("id")
                    stage_id = deal.get("stage", {}).get("id")
                    if stage_id:
                        lead_info["moskit_stage_id"] = stage_id
                        stage_name = MOSKIT_STAGE_NAMES.get(stage_id)
                        if stage_name:
                            lead_info["pipeline_stage"] = stage_name

                create_lead(data, lead_info)
                imported += 1

        except Exception as e:
            errors.append(f"Contact {contact.get('id', '?')}: {str(e)}")
            logger.error(f"Error processing Moskit contact: {e}")

    # Rebuild indexes after bulk import
    data = rebuild_indexes(data)

    # Log sync
    sync_entry = {
        "timestamp": datetime.now().isoformat(),
        "type": "moskit_import",
        "leads_imported": imported,
        "leads_updated": updated,
        "leads_skipped": skipped,
        "errors": errors[:10],  # Cap errors
    }
    data["sync_log"].append(sync_entry)
    data["sync_log"] = data["sync_log"][-50:]  # Keep last 50 entries
    data["last_moskit_sync"] = datetime.now().isoformat()

    logger.info(f"Moskit sync complete: {imported} imported, {updated} updated, {skipped} skipped, {len(errors)} errors")
    return sync_entry


# =============================================================================
# NOTION SYNC
# =============================================================================

def _notion_source_map(source: str) -> str:
    """Map internal source to Notion select option."""
    mapping = {
        "WPP": "Website",  # WhatsApp mapped to Website for now
        "META": "Meta Ads - Facebook",
        "MSG": "Meta Ads - Facebook",
        "IG": "Meta Ads - Instagram",
        "SITE": "Website",
        "MANUAL": "Other Document",
    }
    return mapping.get(source, "Other Document")


def _notion_status_map(status: str) -> str:
    """Map internal status to Notion select option."""
    mapping = {
        "new": "Novo",
        "contacted": "Contactado",
        "qualified": "Qualificado",
        "not_qualified": "Não Qualificado",
        "converted": "Convertido",
        "lost": "Perdido",
    }
    return mapping.get(status, "Novo")


async def sync_lead_to_notion(lead: dict) -> Optional[str]:
    """Create or update a lead in Notion. Returns page_id."""
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    properties = {
        "Nome": {"title": [{"text": {"content": lead.get("name", "Unknown")}}]},
        "Status": {"select": {"name": _notion_status_map(lead.get("status", "new"))}},
        "Fonte": {"select": {"name": _notion_source_map(lead.get("source", "MANUAL"))}},
        "Data de Entrada": {"date": {"start": (lead.get("created_at") or datetime.now().isoformat())[:10]}},
    }

    if lead.get("email"):
        properties["Email"] = {"email": lead["email"]}
    if lead.get("phone"):
        phone = lead["phone"]
        if not phone.startswith("+"):
            phone = "+" + phone
        properties["Telefone"] = {"phone_number": phone}
    if lead.get("visa_interest"):
        properties["Interesse"] = {"multi_select": [{"name": lead["visa_interest"]}]}
    if lead.get("profession"):
        properties["Profissão"] = {"rich_text": [{"text": {"content": lead["profession"]}}]}
    if lead.get("notes"):
        notes_text = lead["notes"][:2000]  # Notion limit
        properties["Notas"] = {"rich_text": [{"text": {"content": notes_text}}]}

    async with httpx.AsyncClient(timeout=15) as client:
        if lead.get("notion_page_id"):
            # Update existing page
            try:
                response = await client.patch(
                    f"{NOTION_API_URL}/pages/{lead['notion_page_id']}",
                    headers=headers,
                    json={"properties": properties},
                )
                response.raise_for_status()
                return lead["notion_page_id"]
            except Exception as e:
                logger.error(f"Notion update error for {lead.get('name')}: {e}")
                return None
        else:
            # Create new page
            try:
                response = await client.post(
                    f"{NOTION_API_URL}/pages",
                    headers=headers,
                    json={
                        "parent": {"database_id": NOTION_LEADS_DB},
                        "properties": properties,
                    },
                )
                response.raise_for_status()
                result = response.json()
                return result.get("id")
            except Exception as e:
                logger.error(f"Notion create error for {lead.get('name')}: {e}")
                return None


async def sync_all_to_notion(data: dict) -> dict:
    """Sync all leads to Notion database."""
    synced = 0
    errors = 0

    for lead_id, lead in data["leads"].items():
        if lead.get("is_deleted"):
            continue

        page_id = await sync_lead_to_notion(lead)
        if page_id:
            lead["notion_page_id"] = page_id
            lead["notion_synced"] = True
            synced += 1
        else:
            errors += 1

        # Rate limit: Notion allows ~3 requests/sec
        import asyncio
        await asyncio.sleep(0.4)

    data = rebuild_indexes(data)

    sync_entry = {
        "timestamp": datetime.now().isoformat(),
        "type": "notion_sync",
        "leads_synced": synced,
        "errors": errors,
    }
    data["sync_log"].append(sync_entry)
    data["last_notion_sync"] = datetime.now().isoformat()

    logger.info(f"Notion sync complete: {synced} synced, {errors} errors")
    return sync_entry


# =============================================================================
# METRICS
# =============================================================================

def get_metrics(data: dict) -> dict:
    """Calculate comprehensive dashboard metrics."""
    leads = [l for l in data["leads"].values() if not l.get("is_deleted")]
    total = len(leads)

    if total == 0:
        return {
            "total": 0, "by_source": {}, "by_stage": {}, "by_status": {},
            "by_lead_status": {}, "avg_score": 0, "today": 0,
            "this_week": 0, "this_month": 0,
        }

    today = datetime.now().date().isoformat()
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    month_ago = (datetime.now() - timedelta(days=30)).isoformat()

    scores = [l.get("lead_score", 0) for l in leads]

    return {
        "total": total,
        "by_source": dict(Counter(l.get("source", "MANUAL") for l in leads)),
        "by_stage": dict(Counter(l.get("pipeline_stage", "NEW_LEAD") for l in leads)),
        "by_status": dict(Counter(l.get("status", "new") for l in leads)),
        "by_lead_status": dict(Counter(l.get("lead_status", "cold") for l in leads)),
        "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "max_score": max(scores) if scores else 0,
        "today": sum(1 for l in leads if (l.get("created_at") or "")[:10] == today),
        "this_week": sum(1 for l in leads if (l.get("created_at") or "") >= week_ago),
        "this_month": sum(1 for l in leads if (l.get("created_at") or "") >= month_ago),
        "moskit_synced": sum(1 for l in leads if l.get("moskit_sent")),
        "notion_synced": sum(1 for l in leads if l.get("notion_synced")),
        "urgent": sum(1 for l in leads if l.get("is_urgent")),
    }


def get_pipeline_metrics(data: dict) -> dict:
    """Get pipeline funnel metrics with score distribution per stage."""
    leads = [l for l in data["leads"].values() if not l.get("is_deleted")]

    pipeline = {}
    for stage in VALID_STAGES:
        stage_leads = [l for l in leads if l.get("pipeline_stage") == stage]
        scores = [l.get("lead_score", 0) for l in stage_leads]
        pipeline[stage] = {
            "count": len(stage_leads),
            "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
            "hot": sum(1 for s in scores if s >= 70),
            "qualified": sum(1 for s in scores if 50 <= s < 70),
            "warm": sum(1 for s in scores if 30 <= s < 50),
            "cold": sum(1 for s in scores if s < 30),
            "leads": [{
                "id": l["id"],
                "name": l.get("name", ""),
                "score": l.get("lead_score", 0),
                "phone": l.get("phone", ""),
                "source": l.get("source", ""),
                "created_at": l.get("created_at", ""),
                "is_urgent": l.get("is_urgent", False),
            } for l in stage_leads[:10]],
        }

    return {"pipeline": pipeline, "total": len(leads)}


def get_trend_metrics(data: dict, days: int = 30) -> dict:
    """Get daily trend data for the specified period."""
    leads = [l for l in data["leads"].values() if not l.get("is_deleted")]
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    recent = [l for l in leads if (l.get("created_at") or "") >= cutoff]

    # Daily counts
    daily = Counter()
    for l in recent:
        day = (l.get("created_at") or "")[:10]
        if day:
            daily[day] += 1

    # Fill in missing days
    all_days = []
    for i in range(days, -1, -1):
        day = (datetime.now() - timedelta(days=i)).date().isoformat()
        all_days.append({"date": day, "count": daily.get(day, 0)})

    # Source breakdown per day
    daily_source = {}
    for l in recent:
        day = (l.get("created_at") or "")[:10]
        source = l.get("source", "MANUAL")
        if day:
            if day not in daily_source:
                daily_source[day] = Counter()
            daily_source[day][source] += 1

    return {
        "period_days": days,
        "total_leads": len(recent),
        "daily": all_days,
        "daily_by_source": {k: dict(v) for k, v in daily_source.items()},
    }


# =============================================================================
# FOLLOW-UPS & ASSIGNMENTS
# =============================================================================

def schedule_follow_up(data: dict, lead_id: str, date: str, note: str = "", actor: str = "staff") -> dict:
    """Schedule a follow-up for a lead."""
    if lead_id not in data["leads"]:
        raise ValueError(f"Lead not found: {lead_id}")

    lead = data["leads"][lead_id]
    lead["follow_up_date"] = date
    lead["follow_up_note"] = note
    lead["updated_at"] = datetime.now().isoformat()
    lead["last_activity_at"] = datetime.now().isoformat()

    # Log in communication_log
    if "communication_log" not in lead:
        lead["communication_log"] = []
    lead["communication_log"].append({
        "timestamp": datetime.now().isoformat(),
        "type": "follow_up",
        "direction": "internal",
        "summary": f"Follow-up scheduled for {date}: {note}" if note else f"Follow-up scheduled for {date}",
        "actor": actor,
    })
    lead["communication_log"] = lead["communication_log"][-50:]

    return lead


def assign_lead(data: dict, lead_id: str, assignee: str, actor: str = "staff") -> dict:
    """Assign a lead to a team member."""
    if lead_id not in data["leads"]:
        raise ValueError(f"Lead not found: {lead_id}")

    lead = data["leads"][lead_id]
    previous = lead.get("assigned_to")
    lead["assigned_to"] = assignee
    lead["updated_at"] = datetime.now().isoformat()
    lead["last_activity_at"] = datetime.now().isoformat()

    # Log assignment
    if "communication_log" not in lead:
        lead["communication_log"] = []
    msg = f"Assigned to {assignee}"
    if previous:
        msg += f" (was: {previous})"
    lead["communication_log"].append({
        "timestamp": datetime.now().isoformat(),
        "type": "assignment",
        "direction": "internal",
        "summary": msg,
        "actor": actor,
    })
    lead["communication_log"] = lead["communication_log"][-50:]

    return lead


def get_overdue_follow_ups(data: dict) -> List[dict]:
    """Get leads with overdue follow-ups."""
    leads = [l for l in data["leads"].values() if not l.get("is_deleted")]
    today = datetime.now().date().isoformat()
    overdue = []
    for l in leads:
        fu = l.get("follow_up_date")
        if fu and fu < today:
            overdue.append({
                "id": l["id"],
                "name": l.get("name", ""),
                "phone": l.get("phone", ""),
                "follow_up_date": fu,
                "follow_up_note": l.get("follow_up_note", ""),
                "assigned_to": l.get("assigned_to"),
                "lead_score": l.get("lead_score", 0),
                "pipeline_stage": l.get("pipeline_stage", ""),
                "days_overdue": (datetime.now().date() - datetime.fromisoformat(fu).date()).days,
            })
    overdue.sort(key=lambda x: x["follow_up_date"])
    return overdue


def check_duplicates(data: dict, phone: str = None, email: str = None) -> List[dict]:
    """Check for duplicate leads by phone or email."""
    results = []
    leads = [l for l in data["leads"].values() if not l.get("is_deleted")]

    if phone:
        clean_phone = re.sub(r"[^\d]", "", phone)
        if clean_phone:
            for l in leads:
                lead_phone = re.sub(r"[^\d]", "", l.get("phone", ""))
                if lead_phone and (lead_phone == clean_phone or lead_phone.endswith(clean_phone[-10:]) or clean_phone.endswith(lead_phone[-10:])):
                    results.append({
                        "id": l["id"],
                        "name": l.get("name", ""),
                        "phone": l.get("phone", ""),
                        "email": l.get("email", ""),
                        "match_type": "phone",
                        "pipeline_stage": l.get("pipeline_stage", ""),
                        "lead_score": l.get("lead_score", 0),
                    })

    if email:
        clean_email = email.lower().strip()
        if clean_email:
            for l in leads:
                if l.get("email", "").lower().strip() == clean_email:
                    # Avoid duplicates in results
                    if not any(r["id"] == l["id"] for r in results):
                        results.append({
                            "id": l["id"],
                            "name": l.get("name", ""),
                            "phone": l.get("phone", ""),
                            "email": l.get("email", ""),
                            "match_type": "email",
                            "pipeline_stage": l.get("pipeline_stage", ""),
                            "lead_score": l.get("lead_score", 0),
                        })

    return results


def get_activity_timeline(data: dict, lead_id: str) -> List[dict]:
    """Get merged activity timeline for a lead (communication_log + stage_history + score_history)."""
    if lead_id not in data["leads"]:
        raise ValueError(f"Lead not found: {lead_id}")

    lead = data["leads"][lead_id]
    timeline = []

    # Communication log entries
    for entry in lead.get("communication_log", []):
        timeline.append({
            "timestamp": entry.get("timestamp", ""),
            "type": entry.get("type", "note"),
            "content": entry.get("summary") or entry.get("content") or entry.get("message", ""),
            "actor": entry.get("actor", ""),
            "category": "communication",
        })

    # Stage history entries
    for entry in lead.get("stage_history", []):
        prev = entry.get("previous_stage", "")
        stage = entry.get("stage", "")
        timeline.append({
            "timestamp": entry.get("entered_at", ""),
            "type": "stage_change",
            "content": f"Stage changed: {prev} → {stage}",
            "actor": "",
            "category": "pipeline",
        })

    # Score history entries
    for entry in lead.get("score_history", []):
        prev = entry.get("previous", 0)
        score = entry.get("score", 0)
        direction = "↑" if score > prev else "↓"
        timeline.append({
            "timestamp": entry.get("timestamp", ""),
            "type": "score_change",
            "content": f"Score {direction} {prev} → {score}",
            "actor": "",
            "category": "scoring",
        })

    # Sort by timestamp descending
    timeline.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return timeline


def mark_as_converted(data: dict, lead_id: str, client_id: int = None, case_id: int = None, actor: str = "staff") -> dict:
    """Mark a lead as converted to a client."""
    if lead_id not in data["leads"]:
        raise ValueError(f"Lead not found: {lead_id}")

    lead = data["leads"][lead_id]
    now = datetime.now().isoformat()

    lead["status"] = "converted"
    lead["converted_at"] = now
    lead["converted_client_id"] = client_id
    lead["converted_case_id"] = case_id
    lead["updated_at"] = now
    lead["last_activity_at"] = now

    # Log conversion
    if "communication_log" not in lead:
        lead["communication_log"] = []
    msg = "Lead converted to client"
    if client_id:
        msg += f" (Client #{client_id})"
    if case_id:
        msg += f" (Case #{case_id})"
    lead["communication_log"].append({
        "timestamp": now,
        "type": "conversion",
        "direction": "internal",
        "summary": msg,
        "actor": actor,
    })
    lead["communication_log"] = lead["communication_log"][-50:]

    # Send conversion feedback (client retained = highest value conversion)
    try:
        notify_conversion_feedback(lead, "CLOSING", lead.get("pipeline_stage"))
    except Exception as e:
        logger.warning(f"[CONVERSION] notify error on conversion: {e}")

    return lead


# =============================================================================
# AGING METRICS
# =============================================================================

def get_aging_metrics(data: dict) -> dict:
    """Calculate average days in each pipeline stage."""
    leads = [l for l in data["leads"].values() if not l.get("is_deleted")]
    now = datetime.now()
    aging = {}
    for stage in VALID_STAGES:
        stage_leads = [l for l in leads if l.get("pipeline_stage") == stage]
        if stage_leads:
            days_list = []
            for l in stage_leads:
                created = l.get("created_at", "")
                if created:
                    try:
                        d = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        days_list.append((now - d.replace(tzinfo=None)).days)
                    except Exception:
                        pass
            aging[stage] = {
                "count": len(stage_leads),
                "avg_days": round(sum(days_list) / len(days_list), 1) if days_list else 0,
                "max_days": max(days_list) if days_list else 0,
            }
        else:
            aging[stage] = {"count": 0, "avg_days": 0, "max_days": 0}
    return aging


# =============================================================================
# WEBHOOK (for WhatsApp bot)
# =============================================================================

def upsert_from_webhook(data: dict, lead_data: dict) -> dict:
    """Create or update a lead from webhook data (WhatsApp bot)."""
    phone = re.sub(r"[^\d]", "", lead_data.get("phone", ""))
    if not phone:
        raise ValueError("Phone number is required")

    existing = find_by_phone(data, phone)

    if existing:
        # Update existing
        updates = {}
        for key in ["name", "email", "lead_score", "lead_status", "source",
                     "visa_interest", "conversation_state", "is_urgent",
                     "message_count", "last_message_at", "moskit_contact_id",
                     "moskit_deal_id", "moskit_sent", "moskit_stage_id",
                     "intake_form_final_score", "intake_form_primary_pathway",
                     "consultation_type", "consultation_scheduled", "payment_status",
                     "whatsapp_name", "gclid", "fbclid",
                     "utm_source", "utm_medium", "utm_campaign"]:
            if key in lead_data and lead_data[key] is not None:
                updates[key] = lead_data[key]

        if updates:
            # Update pipeline stage based on score if score changed
            if "lead_score" in updates:
                updates["pipeline_stage"] = get_stage_from_score(updates["lead_score"])
                updates["lead_status"] = get_score_status(updates["lead_score"])

            return update_lead(data, existing["id"], updates)
        return existing
    else:
        # Create new
        lead_data["phone"] = phone
        if lead_data.get("lead_score"):
            lead_data["pipeline_stage"] = get_stage_from_score(lead_data["lead_score"])
            lead_data["lead_status"] = get_score_status(lead_data["lead_score"])

        # Auto-infer pathway if not provided
        if not lead_data.get("intake_form_primary_pathway"):
            inferred = infer_pathway_from_fields(lead_data)
            if inferred:
                lead_data["intake_form_primary_pathway"] = inferred
                logger.info(f"[PATHWAY] Auto-inferred: {inferred} for {lead_data.get('name', phone)}")

        return create_lead(data, lead_data)

# =============================================================================
# DEAL/OPPORTUNITY MANAGEMENT (Phase 5B)
# =============================================================================

import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

# Service Catalog with prices
SERVICE_CATALOG = {
    "EB-1A": {"name": "EB-1A Extraordinary Ability", "price": 10000},
    "EB-1B": {"name": "EB-1B Outstanding Professor/Researcher", "price": 10000},
    "EB-2 NIW": {"name": "EB-2 National Interest Waiver", "price": 8000},
    "EB-2": {"name": "EB-2 Employment Based", "price": 7000},
    "EB-3": {"name": "EB-3 Skilled Worker", "price": 6000},
    "O-1A": {"name": "O-1A Extraordinary Ability", "price": 9000},
    "O-1B": {"name": "O-1B Arts", "price": 8500},
    "L-1A": {"name": "L-1A Intracompany Transfer (Manager)", "price": 7500},
    "L-1B": {"name": "L-1B Intracompany Transfer (Specialized)", "price": 7000},
    "H-1B": {"name": "H-1B Specialty Occupation", "price": 5000},
    "Family-Based": {"name": "Family-Based Green Card", "price": 5000},
    "Consultation": {"name": "Attorney Consultation", "price": 99},
    "I-485": {"name": "Adjustment of Status", "price": 3000},
    "I-765": {"name": "EAD Application", "price": 500},
    "I-131": {"name": "Advance Parole", "price": 500},
    "I-140": {"name": "Immigrant Petition", "price": 2500},
}

# Deal stages with default win probabilities
DEAL_STAGES = {
    "opportunity": {"name": "Opportunity", "win_probability": 10, "order": 1},
    "proposal": {"name": "Proposal Sent", "win_probability": 30, "order": 2},
    "negotiation": {"name": "Negotiation", "win_probability": 60, "order": 3},
    "closed_won": {"name": "Closed Won", "win_probability": 100, "order": 4},
    "closed_lost": {"name": "Closed Lost", "win_probability": 0, "order": 5},
}


def create_deal(data: dict, lead_id: str, deal_data: dict, actor: str = "staff") -> dict:
    """Create or update a deal for a lead."""
    if lead_id not in data["leads"]:
        raise ValueError(f"Lead not found: {lead_id}")

    lead = data["leads"][lead_id]
    now = datetime.now().isoformat()

    # Get existing deal or create new
    deal = lead.get("deal") or {}
    is_new = not deal.get("id")

    if is_new:
        deal["id"] = str(uuid.uuid4())[:8]
        deal["created_at"] = now

    # Update deal fields
    deal["value"] = deal_data.get("value", deal.get("value", 0))
    deal["win_probability"] = deal_data.get("win_probability", deal.get("win_probability", 10))
    deal["expected_close_date"] = deal_data.get("expected_close_date", deal.get("expected_close_date"))
    deal["deal_stage"] = deal_data.get("deal_stage", deal.get("deal_stage", "opportunity"))
    deal["products"] = deal_data.get("products", deal.get("products", []))
    deal["currency"] = deal_data.get("currency", "USD")
    deal["payment_plan"] = deal_data.get("payment_plan", deal.get("payment_plan"))
    deal["notes"] = deal_data.get("notes", deal.get("notes", ""))
    deal["updated_at"] = now

    # Auto-calculate value from products if not provided
    if not deal["value"] and deal["products"]:
        deal["value"] = sum(
            SERVICE_CATALOG.get(p, {}).get("price", 0)
            for p in deal["products"]
        )

    # Auto-set win probability from stage if not provided
    if "win_probability" not in deal_data:
        stage_info = DEAL_STAGES.get(deal["deal_stage"], {})
        deal["win_probability"] = stage_info.get("win_probability", 10)

    lead["deal"] = deal
    lead["updated_at"] = now
    lead["last_activity_at"] = now

    # Log deal activity
    if "communication_log" not in lead:
        lead["communication_log"] = []

    action = "created" if is_new else "updated"
    lead["communication_log"].append({
        "timestamp": now,
        "type": "deal",
        "direction": "internal",
        "summary": f"Deal {action}: ${deal['value']:,} ({deal['deal_stage']})",
        "actor": actor,
    })
    lead["communication_log"] = lead["communication_log"][-50:]

    return deal


def update_deal_stage(data: dict, lead_id: str, stage: str, actor: str = "staff") -> dict:
    """Update deal stage for a lead."""
    if lead_id not in data["leads"]:
        raise ValueError(f"Lead not found: {lead_id}")

    if stage not in DEAL_STAGES:
        raise ValueError(f"Invalid deal stage: {stage}")

    lead = data["leads"][lead_id]
    deal = lead.get("deal")

    if not deal:
        raise ValueError(f"Lead has no deal: {lead_id}")

    now = datetime.now().isoformat()
    old_stage = deal.get("deal_stage", "opportunity")

    deal["deal_stage"] = stage
    deal["win_probability"] = DEAL_STAGES[stage]["win_probability"]
    deal["updated_at"] = now

    lead["updated_at"] = now
    lead["last_activity_at"] = now

    # Log stage change
    if "communication_log" not in lead:
        lead["communication_log"] = []

    lead["communication_log"].append({
        "timestamp": now,
        "type": "deal_stage",
        "direction": "internal",
        "summary": f"Deal stage: {old_stage} → {stage}",
        "actor": actor,
    })
    lead["communication_log"] = lead["communication_log"][-50:]

    return deal


def get_all_deals(data: dict, filters: dict = None) -> List[dict]:
    """Get all deals with optional filters."""
    filters = filters or {}
    leads = [l for l in data["leads"].values() if not l.get("is_deleted") and l.get("deal")]

    results = []
    for lead in leads:
        deal = lead["deal"]

        # Apply filters
        if filters.get("stage") and deal.get("deal_stage") != filters["stage"]:
            continue
        if filters.get("min_value") and deal.get("value", 0) < filters["min_value"]:
            continue
        if filters.get("assignee") and lead.get("assigned_to") != filters["assignee"]:
            continue

        results.append({
            "lead_id": lead["id"],
            "lead_name": lead.get("name") or lead.get("display_name") or "Unknown",
            "lead_phone": lead.get("phone", ""),
            "lead_email": lead.get("email", ""),
            "assigned_to": lead.get("assigned_to"),
            "pipeline_stage": lead.get("pipeline_stage"),
            "deal": deal,
        })

    # Sort by value descending
    results.sort(key=lambda x: x["deal"].get("value", 0), reverse=True)
    return results


def get_deals_by_stage(data: dict) -> dict:
    """Get deals grouped by stage with totals."""
    leads = [l for l in data["leads"].values() if not l.get("is_deleted") and l.get("deal")]

    pipeline = {}
    for stage_key, stage_info in DEAL_STAGES.items():
        stage_deals = [l for l in leads if l["deal"].get("deal_stage") == stage_key]
        total_value = sum(l["deal"].get("value", 0) for l in stage_deals)
        weighted_value = sum(
            l["deal"].get("value", 0) * l["deal"].get("win_probability", 0) / 100
            for l in stage_deals
        )

        pipeline[stage_key] = {
            "name": stage_info["name"],
            "order": stage_info["order"],
            "count": len(stage_deals),
            "total_value": total_value,
            "weighted_value": round(weighted_value, 2),
            "avg_probability": round(
                sum(l["deal"].get("win_probability", 0) for l in stage_deals) / len(stage_deals), 1
            ) if stage_deals else 0,
            "deals": [{
                "lead_id": l["id"],
                "lead_name": l.get("name") or l.get("display_name") or "Unknown",
                "value": l["deal"].get("value", 0),
                "probability": l["deal"].get("win_probability", 0),
                "products": l["deal"].get("products", []),
            } for l in stage_deals[:5]],
        }

    return pipeline


def get_revenue_forecast(data: dict) -> dict:
    """Calculate revenue forecast from deals."""
    leads = [l for l in data["leads"].values() if not l.get("is_deleted") and l.get("deal")]

    # Only include active deals (not closed_lost)
    active_deals = [
        l for l in leads
        if l["deal"].get("deal_stage") not in ("closed_lost",)
    ]

    total_pipeline = sum(l["deal"].get("value", 0) for l in active_deals)
    weighted_forecast = sum(
        l["deal"].get("value", 0) * l["deal"].get("win_probability", 0) / 100
        for l in active_deals
    )

    # Closed won revenue
    closed_won = [l for l in leads if l["deal"].get("deal_stage") == "closed_won"]
    closed_revenue = sum(l["deal"].get("value", 0) for l in closed_won)

    # By stage breakdown
    by_stage = {}
    for stage_key in DEAL_STAGES:
        stage_deals = [l for l in leads if l["deal"].get("deal_stage") == stage_key]
        by_stage[stage_key] = {
            "count": len(stage_deals),
            "total": sum(l["deal"].get("value", 0) for l in stage_deals),
            "weighted": round(sum(
                l["deal"].get("value", 0) * l["deal"].get("win_probability", 0) / 100
                for l in stage_deals
            ), 2),
        }

    # By product breakdown
    by_product = {}
    for lead in active_deals:
        for product in lead["deal"].get("products", []):
            if product not in by_product:
                by_product[product] = {"count": 0, "total": 0}
            by_product[product]["count"] += 1
            price = SERVICE_CATALOG.get(product, {}).get("price", 0)
            by_product[product]["total"] += price

    return {
        "total_pipeline": total_pipeline,
        "weighted_forecast": round(weighted_forecast, 2),
        "closed_revenue": closed_revenue,
        "active_deals": len(active_deals),
        "closed_won_count": len(closed_won),
        "by_stage": by_stage,
        "by_product": by_product,
        "service_catalog": SERVICE_CATALOG,
    }


def delete_deal(data: dict, lead_id: str, actor: str = "staff") -> bool:
    """Delete a deal from a lead."""
    if lead_id not in data["leads"]:
        raise ValueError(f"Lead not found: {lead_id}")

    lead = data["leads"][lead_id]
    if not lead.get("deal"):
        return False

    now = datetime.now().isoformat()

    # Log deletion
    if "communication_log" not in lead:
        lead["communication_log"] = []

    lead["communication_log"].append({
        "timestamp": now,
        "type": "deal",
        "direction": "internal",
        "summary": f"Deal deleted (was: ${lead['deal'].get('value', 0):,})",
        "actor": actor,
    })
    lead["communication_log"] = lead["communication_log"][-50:]

    lead["deal"] = None
    lead["updated_at"] = now

    return True
