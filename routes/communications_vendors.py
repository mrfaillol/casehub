"""
CaseHub - Communications Vendor Integrations
Moskit sync, check-in list management, batch email background tasks
"""
import logging
import os
import json
import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from models import get_db
from auth import get_current_user
from services.moskit import moskit_service

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

vendors_router = APIRouter(tags=["communications-vendors"])


# ============================================
# SHARED HELPERS (imported at function level to avoid circular imports)
# ============================================

def _get_comm_helpers():
    """Lazy import of shared helpers from communications module."""
    from routes.communications import (
        load_weekly_checkin_clients,
        save_weekly_checkin_clients,
        get_exclusion_list,
        load_checkin_config,
        save_checkin_config,
        load_comm_history,
        save_comm_history,
        send_email_via_resend,
        WEEKLY_TEMPLATE,
        MONTHLY_TEMPLATE,
    )
    return {
        "load_weekly_checkin_clients": load_weekly_checkin_clients,
        "save_weekly_checkin_clients": save_weekly_checkin_clients,
        "get_exclusion_list": get_exclusion_list,
        "load_checkin_config": load_checkin_config,
        "save_checkin_config": save_checkin_config,
        "load_comm_history": load_comm_history,
        "save_comm_history": save_comm_history,
        "send_email_via_resend": send_email_via_resend,
        "WEEKLY_TEMPLATE": WEEKLY_TEMPLATE,
        "MONTHLY_TEMPLATE": MONTHLY_TEMPLATE,
    }


# ============================================
# MOSKIT INTEGRATION ENDPOINTS
# ============================================

@vendors_router.get("/api/moskit/clients")
async def get_moskit_clients(request: Request, db: Session = Depends(get_db)):
    """Get all clients from Moskit with email"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    result = await moskit_service.get_contacts_with_email()
    if not result.get("success"):
        return JSONResponse({"error": result.get("error", "Failed to fetch from Moskit")}, status_code=500)

    # Add exclusion status to each client
    helpers = _get_comm_helpers()
    exclusions = helpers["get_exclusion_list"]()
    exclusion_names = [e.get("name", "").lower() for e in exclusions]

    clients = []
    for contact in result.get("data", []):
        name = contact.get("name", "")
        is_excluded = any(excl in name.lower() or name.lower() in excl for excl in exclusion_names)
        clients.append({
            "id": contact.get("id"),
            "name": name,
            "email": contact.get("email"),
            "phones": contact.get("phones", []),
            "excluded": is_excluded,
            "source": "moskit"
        })

    return {"clients": clients, "total": len(clients)}


@vendors_router.get("/api/moskit/sync")
async def sync_moskit_clients(request: Request, db: Session = Depends(get_db)):
    """Sync clients from Moskit and save to cache"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    result = await moskit_service.get_contacts_with_email()
    if not result.get("success"):
        return JSONResponse({"error": result.get("error", "Failed to fetch from Moskit")}, status_code=500)

    # Save to cache file
    cache_path = os.path.join(DATA_DIR, "moskit_clients_cache.json")
    cache_data = {
        "synced_at": datetime.now().isoformat(),
        "clients": result.get("data", []),
        "total": result.get("total", 0)
    }
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, indent=2, ensure_ascii=False)

    return {"success": True, "synced": len(result.get("data", [])), "synced_at": cache_data["synced_at"]}


# ============================================
# WEEKLY CHECK-IN LIST MANAGEMENT
# ============================================

@vendors_router.get("/api/checkin-list")
async def get_checkin_list(request: Request, db: Session = Depends(get_db)):
    """Get weekly check-in clients list"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    helpers = _get_comm_helpers()
    data = helpers["load_weekly_checkin_clients"]()
    return {
        "success": True,
        "clients": data.get("clients", []),
        "total": len(data.get("clients", [])),
        "lastUpdated": data.get("lastUpdated"),
        "lastSyncedWithMoskit": data.get("lastSyncedWithMoskit")
    }


@vendors_router.post("/api/checkin-list/add")
async def add_to_checkin_list(request: Request, db: Session = Depends(get_db)):
    """Add email to weekly check-in list and sync to Moskit"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    email = body.get("email", "").strip().lower()
    name = body.get("name", "").strip()

    if not email or "@" not in email:
        return JSONResponse({"error": "Invalid email"}, status_code=400)

    # Generate name from email if not provided
    if not name:
        name = email.split("@")[0].replace(".", " ").replace("_", " ").title()

    helpers = _get_comm_helpers()
    data = helpers["load_weekly_checkin_clients"]()

    # Check if already exists
    existing_emails = [c.get("email", "").lower() for c in data.get("clients", [])]
    if email in existing_emails:
        return {"success": False, "error": "Email already in list"}

    # Create in Moskit
    moskit_result = await moskit_service.create_contact_for_checkin(email, name)
    moskit_id = moskit_result.get("id") if moskit_result.get("success") else None

    # Add to local list
    data["clients"].append({
        "email": email,
        "name": name,
        "moskit_id": moskit_id,
        "added_at": datetime.now().isoformat()
    })
    helpers["save_weekly_checkin_clients"](data)

    return {
        "success": True,
        "message": f"Added {email} to check-in list",
        "moskit_synced": moskit_id is not None,
        "moskit_id": moskit_id
    }


@vendors_router.post("/api/checkin-list/remove")
async def remove_from_checkin_list(request: Request, db: Session = Depends(get_db)):
    """Remove email from weekly check-in list and from Moskit"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    email = body.get("email", "").strip().lower()

    if not email:
        return JSONResponse({"error": "Email required"}, status_code=400)

    helpers = _get_comm_helpers()
    data = helpers["load_weekly_checkin_clients"]()

    # Find the client
    client_to_remove = None
    for client in data.get("clients", []):
        if client.get("email", "").lower() == email:
            client_to_remove = client
            break

    if not client_to_remove:
        return {"success": False, "error": "Email not found in list"}

    # Delete from Moskit if synced
    moskit_deleted = False
    if client_to_remove.get("moskit_id"):
        result = await moskit_service.delete_contact(client_to_remove["moskit_id"])
        moskit_deleted = result.get("success", False)

    # Remove from local list
    data["clients"] = [c for c in data["clients"] if c.get("email", "").lower() != email]
    helpers["save_weekly_checkin_clients"](data)

    return {
        "success": True,
        "message": f"Removed {email} from check-in list",
        "moskit_deleted": moskit_deleted
    }


@vendors_router.post("/api/checkin-list/import")
async def import_checkin_list(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Import emails to weekly check-in list and sync all to Moskit"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    emails_text = body.get("emails", "")
    if not emails_text:
        return JSONResponse({"error": "No emails provided"}, status_code=400)

    # Parse emails - support comma, semicolon, newline separated
    import re
    emails = re.split(r'[,;\n\r]+', emails_text)
    emails = [e.strip().lower() for e in emails if e.strip() and "@" in e.strip()]

    if not emails:
        return {"success": False, "error": "No valid emails found"}

    helpers = _get_comm_helpers()
    data = helpers["load_weekly_checkin_clients"]()
    existing_emails = [c.get("email", "").lower() for c in data.get("clients", [])]

    new_emails = [e for e in emails if e not in existing_emails]

    if not new_emails:
        return {"success": True, "message": "All emails already in list", "added": 0}

    # Add to local list first (without moskit_id)
    for email in new_emails:
        name = email.split("@")[0].replace(".", " ").replace("_", " ").title()
        data["clients"].append({
            "email": email,
            "name": name,
            "moskit_id": None,
            "added_at": datetime.now().isoformat()
        })

    helpers["save_weekly_checkin_clients"](data)

    # Sync to Moskit in background
    background_tasks.add_task(sync_new_clients_to_moskit, new_emails)

    return {
        "success": True,
        "message": f"Added {len(new_emails)} emails. Syncing to Moskit in background...",
        "added": len(new_emails),
        "skipped": len(emails) - len(new_emails)
    }


@vendors_router.post("/api/checkin-list/sync")
async def sync_checkin_list_with_moskit(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Sync entire check-in list with Moskit (both directions)"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # Start sync in background
    background_tasks.add_task(full_sync_with_moskit)

    return {
        "success": True,
        "message": "Full sync with Moskit started in background"
    }


# ============================================
# BACKGROUND TASKS
# ============================================

async def send_batch_background(clients: list, comm_type: str, sent_by: str):
    """Background task to send batch emails (legacy)"""
    helpers = _get_comm_helpers()
    template = helpers["WEEKLY_TEMPLATE"] if comm_type == "weekly" else helpers["MONTHLY_TEMPLATE"]
    load_comm_history = helpers["load_comm_history"]
    save_comm_history = helpers["save_comm_history"]

    history = load_comm_history()

    for client in clients:
        client_name = client.get("name", "")

        history_entry = {
            "client_name": client_name,
            "type": comm_type,
            "sent_at": datetime.now().isoformat(),
            "sent_by": sent_by,
            "status": "pending_email_lookup"
        }

        if comm_type == "weekly":
            history.setdefault("weekly", []).append(history_entry)
        else:
            history.setdefault("monthly", []).append(history_entry)

        await asyncio.sleep(6)

    save_comm_history(history)


async def send_batch_background_moskit(clients: list, comm_type: str, sent_by: str):
    """Background task to send batch emails to Moskit clients"""
    helpers = _get_comm_helpers()
    template = helpers["WEEKLY_TEMPLATE"] if comm_type == "weekly" else helpers["MONTHLY_TEMPLATE"]
    load_comm_history = helpers["load_comm_history"]
    save_comm_history = helpers["save_comm_history"]
    load_checkin_config = helpers["load_checkin_config"]
    save_checkin_config = helpers["save_checkin_config"]
    send_email = helpers["send_email_via_resend"]

    history = load_comm_history()
    config = load_checkin_config()
    rate_limit = config.get("rate_limit", 10)  # emails per minute

    sent_count = 0
    failed_count = 0

    for client in clients:
        client_name = client.get("name", "")
        client_email = client.get("email", "")

        if not client_email:
            continue

        # Prepare email
        first_name = client_name.split()[0] if client_name else "Client"
        subject = template["subject"]
        body = template["body"].replace("{client_name}", first_name)

        # Send email
        result = await send_email(client_email, subject, body)

        # Log to history
        history_entry = {
            "client_name": client_name,
            "client_email": client_email,
            "moskit_id": client.get("moskit_id"),
            "type": comm_type,
            "sent_at": datetime.now().isoformat(),
            "sent_by": sent_by,
            "status": "sent" if result.get("success") else "failed",
            "resend_id": result.get("data", {}).get("id") if result.get("success") else None,
            "error": result.get("error") if not result.get("success") else None
        }

        if comm_type == "weekly":
            history.setdefault("weekly", []).append(history_entry)
        else:
            history.setdefault("monthly", []).append(history_entry)

        if result.get("success"):
            sent_count += 1
        else:
            failed_count += 1

        # Rate limiting - wait based on rate_limit
        await asyncio.sleep(60 / rate_limit)

    # Update config with last sent info
    config["last_sent"] = datetime.now().isoformat()
    config["last_sent_count"] = sent_count
    save_checkin_config(config)
    save_comm_history(history)


async def sync_new_clients_to_moskit(emails: list):
    """Background task to sync new clients to Moskit"""
    helpers = _get_comm_helpers()
    load_weekly_checkin_clients = helpers["load_weekly_checkin_clients"]
    save_weekly_checkin_clients = helpers["save_weekly_checkin_clients"]

    data = load_weekly_checkin_clients()

    for email in emails:
        # Find the client in local list
        for client in data["clients"]:
            if client.get("email", "").lower() == email.lower() and not client.get("moskit_id"):
                # Create in Moskit
                result = await moskit_service.create_contact_for_checkin(email, client.get("name", ""))
                if result.get("success"):
                    client["moskit_id"] = result.get("id")
                    client["synced_at"] = datetime.now().isoformat()
                await asyncio.sleep(1)  # Rate limit
                break

    data["lastSyncedWithMoskit"] = datetime.now().isoformat()
    save_weekly_checkin_clients(data)


async def full_sync_with_moskit():
    """Full bidirectional sync with Moskit"""
    helpers = _get_comm_helpers()
    load_weekly_checkin_clients = helpers["load_weekly_checkin_clients"]
    save_weekly_checkin_clients = helpers["save_weekly_checkin_clients"]

    data = load_weekly_checkin_clients()

    # 1. Sync local clients that don't have moskit_id
    for client in data["clients"]:
        if not client.get("moskit_id"):
            result = await moskit_service.create_contact_for_checkin(
                client.get("email", ""),
                client.get("name", "")
            )
            if result.get("success"):
                client["moskit_id"] = result.get("id")
                client["synced_at"] = datetime.now().isoformat()
            await asyncio.sleep(0.5)

    # 2. Get all [CHECKIN] contacts from Moskit
    moskit_result = await moskit_service.get_checkin_contacts()
    if moskit_result.get("success"):
        moskit_contacts = moskit_result.get("data", [])
        local_emails = [c.get("email", "").lower() for c in data["clients"]]

        # Add any Moskit [CHECKIN] contacts not in local list
        for contact in moskit_contacts:
            email = contact.get("email", "").lower()
            if email and email not in local_emails:
                data["clients"].append({
                    "email": email,
                    "name": contact.get("name", ""),
                    "moskit_id": contact.get("id"),
                    "synced_at": datetime.now().isoformat()
                })

    data["lastSyncedWithMoskit"] = datetime.now().isoformat()
    save_weekly_checkin_clients(data)
