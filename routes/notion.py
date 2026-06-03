"""
CaseHub - Notion Integration Routes
Manage Notion sync configuration and trigger syncs
"""
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from typing import Optional
import json
import os

from models import get_db, Client, Case
from auth import get_current_user
from models.tenant import tenant_query
from services.notion_sync import NotionSyncService, test_connection

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/notion", tags=["notion"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py

# Configuration file path
CONFIG_FILE = "notion_config.json"


def get_context(request: Request, db: Session, **kwargs):
    from i18n import get_translations
    lang = request.cookies.get("lang", "pt-BR")
    t = get_translations(lang)
    user = get_current_user(request, db)
    return {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "t": t,
        "lang": lang,
        **kwargs
    }


def load_config() -> dict:
    """Load Notion configuration from file"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {
        "token": "",
        "clients_database_id": "",
        "cases_database_id": "",
        "auto_sync": False,
        "last_sync": None
    }


def save_config(config: dict):
    """Save Notion configuration to file"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2, default=str)


@router.get("", response_class=HTMLResponse)
async def notion_settings(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    config = load_config()

    # Test connection if token exists
    connection_status = None
    databases = []
    if config.get("token"):
        connection_status = test_connection(config["token"])
        if connection_status.get("success"):
            service = NotionSyncService(config["token"])
            databases = service.search_databases()

    # Get sync stats
    client_count = tenant_query(db, Client, request.state.org_id).count()
    case_count = tenant_query(db, Case, request.state.org_id).count()

    return templates.TemplateResponse("app/notion/settings.html", get_context(
        request, db,
        config=config,
        connection_status=connection_status,
        databases=databases,
        client_count=client_count,
        case_count=case_count
    ))


@router.post("/save-config")
async def save_notion_config(
    request: Request,
    token: str = Form(...),
    clients_database_id: str = Form(""),
    cases_database_id: str = Form(""),
    auto_sync: bool = Form(False),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    config = load_config()
    config["token"] = token
    config["clients_database_id"] = clients_database_id
    config["cases_database_id"] = cases_database_id
    config["auto_sync"] = auto_sync
    save_config(config)

    return RedirectResponse(url=f"{PREFIX}/notion", status_code=302)


@router.post("/test-connection")
async def test_notion_connection(
    request: Request,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    config = load_config()
    if not config.get("token"):
        return JSONResponse({"error": "No token configured"}, status_code=400)

    result = test_connection(config["token"])
    return JSONResponse(result)


@router.post("/sync/clients")
async def sync_clients(
    request: Request,
    direction: str = Form("to_notion"),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    config = load_config()
    if not config.get("token") or not config.get("clients_database_id"):
        return templates.TemplateResponse("app/notion/settings.html", get_context(
            request, db,
            config=config,
            error="Please configure Notion token and Clients database ID first"
        ))

    service = NotionSyncService(config["token"])
    results = service.full_sync_clients(db, config["clients_database_id"], direction)

    # Update last sync time
    from datetime import datetime
    config["last_sync"] = datetime.now().isoformat()
    save_config(config)

    return templates.TemplateResponse("app/notion/sync_results.html", get_context(
        request, db,
        results=results,
        sync_type="Clients",
        direction=direction
    ))


@router.post("/sync/cases")
async def sync_cases(
    request: Request,
    direction: str = Form("to_notion"),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    config = load_config()
    if not config.get("token") or not config.get("cases_database_id"):
        return templates.TemplateResponse("app/notion/settings.html", get_context(
            request, db,
            config=config,
            error="Please configure Notion token and Cases database ID first"
        ))

    service = NotionSyncService(config["token"])
    results = service.full_sync_cases(db, config["cases_database_id"], direction)

    from datetime import datetime
    config["last_sync"] = datetime.now().isoformat()
    save_config(config)

    return templates.TemplateResponse("app/notion/sync_results.html", get_context(
        request, db,
        results=results,
        sync_type="Cases",
        direction=direction
    ))


@router.get("/databases")
async def list_databases(request: Request, db: Session = Depends(get_db)):
    """API endpoint to list available Notion databases"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    config = load_config()
    if not config.get("token"):
        return JSONResponse({"error": "No token configured"}, status_code=400)

    service = NotionSyncService(config["token"])
    databases = service.search_databases()

    return JSONResponse({
        "databases": [
            {
                "id": db.get("id"),
                "title": db.get("title", [{}])[0].get("text", {}).get("content", "Untitled") if db.get("title") else "Untitled"
            }
            for db in databases
        ]
    })
