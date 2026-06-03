"""
CaseHub - Customer Service Communications Routes
Dashboard, email templates, exclusions, check-in config, batch send orchestration.
Vendor-specific integrations live in communications_vendors.py.
"""
import logging
from fastapi import APIRouter, Depends, Request, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
import json
import os
from datetime import datetime, date, timedelta
import httpx
import asyncio

from models import get_db
from auth import get_current_user
from services.moskit import moskit_service
from config import settings

logger = logging.getLogger(__name__)

# PREFIX = "/casehub"  # Imported from template_config.py
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# ============================================
# WEEKLY CHECK-IN CONFIG
# ============================================

def get_checkin_config_path():
    return os.path.join(DATA_DIR, "weekly_checkin_config.json")

def load_checkin_config():
    """Load weekly check-in configuration"""
    path = get_checkin_config_path()
    default_config = {
        "enabled": True,
        "schedule": {
            "day": "monday",
            "hour": 9,
            "minute": 0,
            "timezone": "America/New_York"
        },
        "test_mode": False,
        "test_email": settings.ADMIN_EMAIL or "",
        "from_email": settings.ORG_EMAIL or settings.SMTP_USER,
        "rate_limit": 10,
        "last_sent": None,
        "last_sent_count": 0
    }
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                return config
        except Exception as e:
            logger.error("Failed to load check-in config: %s", e)
    return default_config

def save_checkin_config(config):
    """Save weekly check-in configuration"""
    path = get_checkin_config_path()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

router = APIRouter(prefix="/communications", tags=["communications"])

# Include vendor-specific sub-router (Moskit sync, check-in list management)
from routes.communications_vendors import vendors_router
router.include_router(vendors_router)

try:
    os.makedirs(DATA_DIR, exist_ok=True)
except PermissionError:
    pass

# ============================================
# DATA FILES
# ============================================

def get_client_teams_path():
    return os.path.join(DATA_DIR, "client_teams.json")

def get_comm_history_path():
    return os.path.join(DATA_DIR, "comm_history.json")

def get_weekly_checkin_clients_path():
    return os.path.join(DATA_DIR, "weekly_checkin_clients.json")

def load_weekly_checkin_clients():
    """Load weekly check-in clients list"""
    path = get_weekly_checkin_clients_path()
    default_data = {
        "description": "Lista de clientes para weekly check-in - sincronizada com Moskit",
        "lastUpdated": None,
        "lastSyncedWithMoskit": None,
        "clients": []
    }
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load weekly check-in clients: %s", e)
    return default_data

def save_weekly_checkin_clients(data):
    """Save weekly check-in clients list"""
    path = get_weekly_checkin_clients_path()
    data["lastUpdated"] = datetime.now().isoformat()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_client_teams():
    """Load client team assignments"""
    path = get_client_teams_path()
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"teams": {}, "exclusions": {"clients": []}}

def save_client_teams(data):
    """Save client team assignments"""
    path = get_client_teams_path()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_comm_history():
    """Load communication history"""
    path = get_comm_history_path()
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"weekly": [], "monthly": []}

def save_comm_history(data):
    """Save communication history"""
    path = get_comm_history_path()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_exclusion_list():
    """Get list of excluded clients"""
    data = load_client_teams()
    return data.get("exclusions", {}).get("clients", [])

def should_exclude_client(client_name: str) -> Optional[str]:
    """Check if client should be excluded, return reason if so"""
    exclusions = get_exclusion_list()
    client_name_lower = (client_name or "").lower().strip()
    for excl in exclusions:
        excl_name = (excl.get("name") or "").lower().strip()
        if excl_name in client_name_lower or client_name_lower in excl_name:
            return excl.get("reason", "Listed in exclusion configuration")
    return None

def get_all_active_clients():
    """Get all active clients from teams"""
    data = load_client_teams()
    clients = []
    for team_name, team_data in data.get("teams", {}).items():
        paralegal = team_data.get("paralegal", "Unknown")
        status = team_data.get("status", "active")
        for client in team_data.get("clients", []):
            client_info = {
                "name": client.get("name"),
                "case_type": client.get("case_type"),
                "team": team_name,
                "paralegal": paralegal,
                "status": status
            }
            # Check exclusion
            reason = should_exclude_client(client.get("name", ""))
            if reason:
                client_info["excluded"] = True
                client_info["exclusion_reason"] = reason
            else:
                client_info["excluded"] = False
            clients.append(client_info)
    return clients

# ============================================
# EMAIL TEMPLATES
# ============================================

WEEKLY_TEMPLATE = {
    "subject": f"Weekly Check-In - {settings.ORG_NAME}",
    "body": f"""Dear {{client_name}},

We hope you are doing well.

This is a brief weekly check-in to see if you have any questions or need any assistance at this time. Our team remains available and happy to support you with anything you may need.

Please feel free to reach out at your convenience.

Warm regards,
{settings.ORG_NAME}"""
}

MONTHLY_TEMPLATE = {
    "subject": f"Monthly Follow-Up - {settings.ORG_NAME}",
    "body": f"""Dear {{client_name}},

We hope this message finds you well.

As part of our monthly follow-up, we would like to check in to see if you have any questions, concerns, or if there is anything we can assist you with regarding your case.

Please do not hesitate to contact us if you need any clarification or support.

Warm regards,
{settings.ORG_NAME}"""
}

# ============================================
# GMAIL SMTP EMAIL (migrado de Resend em 2026-02-23)
# ============================================

SMTP_HOST = settings.SMTP_HOST
SMTP_PORT = settings.SMTP_PORT
SMTP_USER = settings.SMTP_USER or settings.GMAIL_CENTER_EMAIL
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", os.environ.get("GMAIL_CENTER_APP_PASSWORD", ""))
FROM_EMAIL = settings.SMTP_USER or settings.ORG_EMAIL

async def send_email_via_resend(to_email: str, subject: str, body: str) -> dict:
    """Send email using Gmail SMTP (legacy name kept for compatibility)"""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    if not SMTP_PASSWORD:
        return {"success": False, "error": "SMTP_PASSWORD not configured"}

    try:
        msg = MIMEMultipart()
        msg["From"] = f"{settings.ORG_NAME} <{FROM_EMAIL}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, [to_email], msg.as_string())

        return {"success": True, "data": {"id": f"smtp-{int(__import__('time').time())}"}}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ============================================
# ROUTES - DASHBOARD
# ============================================

@router.get("", response_class=HTMLResponse)
async def communications_dashboard(request: Request, db: Session = Depends(get_db)):
    """Customer Service Communications Dashboard - Weekly Check-in List"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Get clients from weekly check-in list (local JSON)
    checkin_data = load_weekly_checkin_clients()

    # Get exclusions list
    exclusions = get_exclusion_list()
    exclusion_names = [e.get("name", "").lower() for e in exclusions]
    exclusion_emails = [e.get("email", "").lower() for e in exclusions if e.get("email")]

    # Build client list from weekly check-in list
    clients = []
    for client in checkin_data.get("clients", []):
        name = client.get("name", "")
        email = client.get("email", "")

        # Check if excluded by name or email
        is_excluded = any(
            excl in name.lower() or name.lower() in excl
            for excl in exclusion_names if excl
        ) or email.lower() in exclusion_emails

        clients.append({
            "id": client.get("moskit_id"),
            "name": name,
            "email": email,
            "phone": "",
            "excluded": is_excluded,
            "exclusion_reason": "Listed in exclusion configuration" if is_excluded else None,
            "source": "weekly_checkin_list",
            "moskit_id": client.get("moskit_id"),
            "synced": client.get("moskit_id") is not None
        })

    active_clients = [c for c in clients if not c.get("excluded")]
    excluded_clients = [c for c in clients if c.get("excluded")]

    # Get communication history
    history = load_comm_history()

    # Calculate stats
    today = date.today()
    this_week = [h for h in history.get("weekly", [])
                 if datetime.fromisoformat(h.get("sent_at", "2000-01-01")).date() >= today - timedelta(days=7)]
    this_month = [h for h in history.get("monthly", [])
                  if datetime.fromisoformat(h.get("sent_at", "2000-01-01")).date() >= today.replace(day=1)]

    stats = {
        "total_clients": len(clients),
        "active_clients": len(active_clients),
        "excluded_clients": len(excluded_clients),
        "weekly_sent_this_week": len(this_week),
        "monthly_sent_this_month": len(this_month)
    }

    return templates.TemplateResponse("app/admin/communications.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "clients": clients,
        "active_clients": active_clients,
        "excluded_clients": excluded_clients,
        "exclusions": exclusions,
        "stats": stats,
        "history": history,
        "weekly_template": WEEKLY_TEMPLATE,
        "monthly_template": MONTHLY_TEMPLATE,
        "now": datetime.now(),
        "checkin_data": checkin_data
    })

# ============================================
# ROUTES - API ENDPOINTS
# ============================================

@router.get("/api/clients")
async def get_clients(request: Request, db: Session = Depends(get_db)):
    """API: Get all clients with status"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    clients = get_all_active_clients()
    return {"clients": clients, "total": len(clients)}

@router.get("/api/stats")
async def get_stats(request: Request, db: Session = Depends(get_db)):
    """API: Get communication statistics"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    clients = get_all_active_clients()
    history = load_comm_history()
    today = date.today()

    return {
        "total_clients": len(clients),
        "active_clients": len([c for c in clients if not c.get("excluded")]),
        "excluded_clients": len([c for c in clients if c.get("excluded")]),
        "weekly_history": len(history.get("weekly", [])),
        "monthly_history": len(history.get("monthly", []))
    }

@router.get("/api/history")
async def get_history(
    request: Request,
    comm_type: str = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """API: Get communication history"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    history = load_comm_history()

    if comm_type == "weekly":
        records = history.get("weekly", [])[-limit:]
    elif comm_type == "monthly":
        records = history.get("monthly", [])[-limit:]
    else:
        records = (history.get("weekly", []) + history.get("monthly", []))[-limit:]

    return {"history": records}

@router.post("/api/exclude")
async def exclude_client(
    request: Request,
    client_name: str = Form(...),
    reason: str = Form(...),
    db: Session = Depends(get_db)
):
    """API: Add client to exclusion list"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    data = load_client_teams()
    if "exclusions" not in data:
        data["exclusions"] = {"clients": []}
    if "clients" not in data["exclusions"]:
        data["exclusions"]["clients"] = []

    # Check if already excluded
    for excl in data["exclusions"]["clients"]:
        if excl.get("name", "").lower() == client_name.lower():
            return {"success": False, "error": "Client already excluded"}

    data["exclusions"]["clients"].append({
        "name": client_name,
        "reason": reason,
        "excluded_at": datetime.now().isoformat(),
        "excluded_by": user.email if hasattr(user, 'email') else user.name
    })

    save_client_teams(data)
    return {"success": True, "message": f"Client '{client_name}' added to exclusion list"}

@router.post("/api/include")
async def include_client(
    request: Request,
    client_name: str = Form(...),
    db: Session = Depends(get_db)
):
    """API: Remove client from exclusion list"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    data = load_client_teams()
    exclusions = data.get("exclusions", {}).get("clients", [])

    new_exclusions = [e for e in exclusions if e.get("name", "").lower() != client_name.lower()]

    if len(new_exclusions) == len(exclusions):
        return {"success": False, "error": "Client not found in exclusion list"}

    data["exclusions"]["clients"] = new_exclusions
    save_client_teams(data)

    return {"success": True, "message": f"Client '{client_name}' removed from exclusion list"}

@router.post("/api/send-single")
async def send_single_email(
    request: Request,
    client_name: str = Form(...),
    client_email: str = Form(...),
    comm_type: str = Form(...),
    db: Session = Depends(get_db)
):
    """API: Send single follow-up email"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # Check exclusion
    if should_exclude_client(client_name):
        return {"success": False, "error": "Client is in exclusion list"}

    # Get template
    if comm_type == "weekly":
        template = WEEKLY_TEMPLATE
    else:
        template = MONTHLY_TEMPLATE

    subject = template["subject"]
    body = template["body"].replace("{client_name}", client_name.split()[0])

    # Send email
    result = await send_email_via_resend(client_email, subject, body)

    if result["success"]:
        # Log to history
        history = load_comm_history()
        history_entry = {
            "client_name": client_name,
            "client_email": client_email,
            "type": comm_type,
            "sent_at": datetime.now().isoformat(),
            "sent_by": user.email if hasattr(user, 'email') else user.name,
            "status": "sent",
            "resend_id": result.get("data", {}).get("id")
        }

        if comm_type == "weekly":
            history.setdefault("weekly", []).append(history_entry)
        else:
            history.setdefault("monthly", []).append(history_entry)

        save_comm_history(history)

        return {"success": True, "message": f"Email sent to {client_name}"}
    else:
        return {"success": False, "error": result.get("error", "Unknown error")}

@router.post("/api/send-batch")
async def send_batch_emails(
    request: Request,
    background_tasks: BackgroundTasks,
    comm_type: str = Form(...),
    test_mode: bool = Form(False),
    test_email: str = Form(None),
    db: Session = Depends(get_db)
):
    """API: Send batch follow-up emails to weekly check-in list clients"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # Get clients from weekly check-in list
    checkin_data = load_weekly_checkin_clients()

    # Get exclusions
    exclusions = get_exclusion_list()
    exclusion_names = [e.get("name", "").lower() for e in exclusions]
    exclusion_emails = [e.get("email", "").lower() for e in exclusions if e.get("email")]

    # Build list of clients to send to (with email, not excluded)
    clients = []
    for client in checkin_data.get("clients", []):
        name = client.get("name", "")
        email = client.get("email", "")

        # Skip if no email
        if not email:
            continue

        # Skip if excluded
        is_excluded = any(
            excl in name.lower() or name.lower() in excl
            for excl in exclusion_names if excl
        ) or email.lower() in exclusion_emails
        if is_excluded:
            continue

        clients.append({
            "name": name,
            "email": email,
            "moskit_id": client.get("moskit_id")
        })

    if not clients:
        return {"success": False, "error": "No clients to send to"}

    # In test mode, send only to test email
    config = load_checkin_config()
    actual_test_email = test_email or config.get("test_email", "")

    if test_mode and actual_test_email:
        template = WEEKLY_TEMPLATE if comm_type == "weekly" else MONTHLY_TEMPLATE
        subject = f"[TEST] {template['subject']}"
        body = f"TEST EMAIL - Would be sent to {len(clients)} clients\n\n" + template["body"].replace("{client_name}", "Test Client")

        result = await send_email_via_resend(actual_test_email, subject, body)
        return {"success": result["success"], "message": f"Test email sent to {actual_test_email}", "client_count": len(clients)}

    # For actual batch send, use background task (vendor module)
    from routes.communications_vendors import send_batch_background_moskit
    background_tasks.add_task(
        send_batch_background_moskit,
        clients=clients,
        comm_type=comm_type,
        sent_by=user.email if hasattr(user, 'email') else user.name
    )

    return {"success": True, "message": f"Batch send started for {len(clients)} clients", "client_count": len(clients)}

# ============================================
# ROUTES - TEMPLATES
# ============================================

@router.get("/templates")
async def get_templates(request: Request, db: Session = Depends(get_db)):
    """Get email templates"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    return {
        "weekly": WEEKLY_TEMPLATE,
        "monthly": MONTHLY_TEMPLATE
    }

# ============================================
# ROUTES - EXCLUSIONS MANAGEMENT
# ============================================

@router.get("/exclusions", response_class=HTMLResponse)
async def view_exclusions(request: Request, db: Session = Depends(get_db)):
    """View exclusion list"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    exclusions = get_exclusion_list()

    return templates.TemplateResponse("admin/exclusions.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "exclusions": exclusions
    })


# ============================================
# WEEKLY CHECK-IN CONTROL ENDPOINTS
# ============================================

@router.get("/api/config")
async def get_checkin_configuration(request: Request, db: Session = Depends(get_db)):
    """Get weekly check-in configuration"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    config = load_checkin_config()
    return {"config": config}


@router.post("/api/config")
async def update_checkin_configuration(request: Request, db: Session = Depends(get_db)):
    """Update weekly check-in configuration"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        body = await request.json()
    except Exception as e:
        logger.error("Failed to parse JSON body: %s", e)
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    config = load_checkin_config()

    # Update only provided fields
    if "enabled" in body:
        config["enabled"] = bool(body["enabled"])
    if "test_mode" in body:
        config["test_mode"] = bool(body["test_mode"])
    if "test_email" in body:
        config["test_email"] = body["test_email"]
    if "schedule" in body:
        if "day" in body["schedule"]:
            config["schedule"]["day"] = body["schedule"]["day"]
        if "hour" in body["schedule"]:
            config["schedule"]["hour"] = int(body["schedule"]["hour"])
        if "minute" in body["schedule"]:
            config["schedule"]["minute"] = int(body["schedule"]["minute"])

    save_checkin_config(config)
    return {"success": True, "config": config}


@router.post("/api/toggle")
async def toggle_checkin_system(request: Request, db: Session = Depends(get_db)):
    """Toggle weekly check-in system on/off"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    config = load_checkin_config()
    config["enabled"] = not config["enabled"]
    save_checkin_config(config)

    return {"success": True, "enabled": config["enabled"]}


@router.post("/api/send-test")
async def send_test_email(request: Request, db: Session = Depends(get_db)):
    """Send test email to configured test address"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    config = load_checkin_config()
    test_email = config.get("test_email", "")

    if not test_email:
        return JSONResponse({"error": "No test email configured"}, status_code=400)

    subject = f"[TEST] {WEEKLY_TEMPLATE['subject']}"
    body = f"This is a test email from CaseHub Weekly Check-In System.\n\n" + WEEKLY_TEMPLATE["body"].replace("{client_name}", "Test Client")

    result = await send_email_via_resend(test_email, subject, body)

    if result["success"]:
        return {"success": True, "message": f"Test email sent to {test_email}"}
    else:
        return {"success": False, "error": result.get("error", "Failed to send")}


@router.get("/api/dashboard")
async def get_dashboard_data(request: Request, db: Session = Depends(get_db)):
    """Get dashboard data for weekly check-in system"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    config = load_checkin_config()
    history = load_comm_history()

    # Calculate next send date
    import calendar
    days_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
    target_day = days_map.get(config["schedule"]["day"].lower(), 0)
    today = date.today()
    days_ahead = target_day - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    next_send_date = today + timedelta(days=days_ahead)

    # Get Moskit client count (wrapped in try/except - Moskit API may be unavailable)
    try:
        moskit_result = await moskit_service.get_contacts_with_email()
        moskit_clients_count = moskit_result.get("total", 0) if moskit_result.get("success") else 0
    except Exception as e:
        logger.warning("[COMM] Moskit API unavailable: %s", e)
        moskit_clients_count = 0

    # Count recent sends
    today_dt = datetime.now()
    week_ago = today_dt - timedelta(days=7)
    month_ago = today_dt - timedelta(days=30)

    try:
        weekly_this_week = len([h for h in history.get("weekly", [])
                               if datetime.fromisoformat(h.get("sent_at", "2000-01-01")) > week_ago])
        monthly_this_month = len([h for h in history.get("monthly", [])
                                 if datetime.fromisoformat(h.get("sent_at", "2000-01-01")) > month_ago])
    except Exception:
        weekly_this_week = 0
        monthly_this_month = 0

    # Get checkin list count
    checkin_data = load_weekly_checkin_clients()
    checkin_clients_count = len(checkin_data.get("clients", []))

    return {
        "enabled": config["enabled"],
        "test_mode": config["test_mode"],
        "test_email": config["test_email"],
        "schedule": config["schedule"],
        "next_send": next_send_date.strftime("%Y-%m-%d"),
        "next_send_formatted": next_send_date.strftime("%A, %B %d"),
        "last_sent": config.get("last_sent"),
        "last_sent_count": config.get("last_sent_count", 0),
        "moskit_clients": moskit_clients_count,
        "checkin_clients": checkin_clients_count,
        "weekly_sent_this_week": weekly_this_week,
        "monthly_sent_this_month": monthly_this_month
    }
