"""
CaseHub - Files Router (Unified File Manager)
Created Feb 22, 2026 | Updated Feb 23, 2026
- Points to Active Clients folder + Tasks folder
- Recursive file listing with folder paths
- Persists drive_folder_id and tasks_folder_data in client record
- Manual folder linking endpoint
- Source tags (Active Clients vs Tasks/Paralegal)
"""
import json
import logging
from fastapi import APIRouter, Depends, Request, HTTPException, Form

logger = logging.getLogger(__name__)
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from typing import Optional

from models import get_db, Client, Document, User
from auth import get_current_user
from models.tenant import tenant_query
from config import settings

ACTIVE_CLIENTS_FOLDER_ID = settings.GOOGLE_DRIVE_ROOT_ID

router = APIRouter(prefix="/files", tags=["files"])


def _get_handler(db, org_id):
    """Get GoogleDriveHandler instance scoped to (db, org_id). Returns None if no token."""
    try:
        from services.google_drive_handler import GoogleDriveHandler
        handler = GoogleDriveHandler(db, org_id=org_id)
        return handler if handler.service else None
    except Exception as e:
        logger.error("[FILES] Error creating Drive handler for org %s: %s", org_id, e)
        return None


def _find_client_drive_folder(handler, client):
    """Find client folder in Active Clients by name matching. Returns {id, name} or None."""
    try:
        return handler.find_client_folder(client.last_name, client.first_name)
    except Exception as e:
        logger.error("[FILES] Error finding drive folder: %s", e)
        return None


def _list_files_recursive(handler, folder_id, max_results=500):
    """List all files recursively in a folder, with folder_path context."""
    try:
        return handler.list_files_recursive(folder_id, max_results)
    except Exception as e:
        logger.error("[FILES] Error listing files recursively: %s", e)
        return []


@router.get("", response_class=HTMLResponse)
async def file_manager_page(
    request: Request,
    client_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Main File Manager page."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Sentinela T5 (2026-05-28): filter clients por org_id pra evitar IDOR
    # cross-tenant — JOIN raiz (clients) não escopava por org. CWE-639.
    result = db.execute(text("""
        SELECT c.id, c.first_name, c.last_name, COUNT(d.id) as doc_count,
               c.drive_folder_id, c.drive_folder_name
        FROM clients c
        LEFT JOIN documents d ON d.client_id = c.id
        WHERE c.org_id = :org_id
        GROUP BY c.id, c.first_name, c.last_name, c.drive_folder_id, c.drive_folder_name
        ORDER BY c.last_name, c.first_name
    """), {"org_id": request.state.org_id})
    clients = [
        {
            "id": r[0], "first_name": r[1], "last_name": r[2],
            "doc_count": r[3], "drive_folder_id": r[4], "drive_folder_name": r[5]
        }
        for r in result.fetchall()
    ]

    return templates.TemplateResponse("app/files/index.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "clients": clients,
        "selected_client_id": client_id
    })


@router.get("/api/client/{client_id}/compare")
async def compare_client_files(
    request: Request,
    client_id: int,
    db: Session = Depends(get_db)
):
    """Compare CaseHub documents vs Google Drive files for a client."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")

        # --- CaseHub documents ---
        docs = tenant_query(db, Document, request.state.org_id).filter(
            Document.client_id == client_id
        ).order_by(Document.created_at.desc()).all()

        vps_files = []
        for d in docs:
            vps_files.append({
                "id": d.id,
                "name": d.name or "",
                "doc_type": getattr(d, 'doc_type', '') or "",
                "mime_type": getattr(d, 'mime_type', '') or "",
                "file_size": getattr(d, 'file_size', 0) or 0,
                "created_at": d.created_at.strftime("%d/%m/%Y") if d.created_at else "",
                "drive_file_id": getattr(d, 'drive_file_id', None),
                "status": getattr(d, 'status', '') or ""
            })

        # --- Google Drive files (Active Clients) ---
        drive_files = []
        drive_folder = None
        folder_id = None

        handler = _get_handler(db, request.state.org_id)
        if handler:
            # Step 1: Check if client has saved drive_folder_id
            if client.drive_folder_id:
                folder_id = client.drive_folder_id
                drive_folder = {
                    "id": client.drive_folder_id,
                    "name": client.drive_folder_name or "Linked folder"
                }
            else:
                # Step 2: Auto-match by name
                folder = _find_client_drive_folder(handler, client)
                if folder:
                    # Step 3: Save to DB for next time
                    client.drive_folder_id = folder["id"]
                    client.drive_folder_name = folder["name"]
                    try:
                        db.commit()
                    except Exception:
                        db.rollback()
                    folder_id = folder["id"]
                    drive_folder = folder

            # Step 4: List Active Clients files recursively
            if folder_id:
                ac_files = _list_files_recursive(handler, folder_id)
                for f in ac_files:
                    f["source"] = "active_clients"
                    f["paralegal"] = ""
                    f["archived"] = False
                drive_files.extend(ac_files)

            # Step 5: Tasks folder integration
            tasks_entries = []
            if client.tasks_folder_data:
                try:
                    tasks_entries = json.loads(client.tasks_folder_data)
                except (json.JSONDecodeError, TypeError):
                    tasks_entries = []

            if not tasks_entries:
                # Auto-search Tasks for this client
                try:
                    found = handler.find_client_in_tasks(client.last_name, client.first_name)
                    if found:
                        tasks_entries = found
                        client.tasks_folder_data = json.dumps(found)
                        try:
                            db.commit()
                        except Exception:
                            db.rollback()
                except Exception as e:
                    logger.error("[FILES] Error searching Tasks: %s", e)

            # List files from each Tasks folder
            for entry in tasks_entries:
                try:
                    tf = _list_files_recursive(handler, entry["id"])
                    for f in tf:
                        f["source"] = "tasks"
                        f["paralegal"] = entry.get("paralegal", "")
                        f["archived"] = entry.get("archived", False)
                    drive_files.extend(tf)
                except Exception as e:
                    logger.error("[FILES] Error listing Tasks folder %s: %s", entry.get('name'), e)

        # --- Build sync map ---
        matched = {}
        vps_drive_ids = {}
        for d in docs:
            dfid = getattr(d, 'drive_file_id', None)
            if dfid:
                vps_drive_ids[dfid] = d.id
        for df in drive_files:
            if df["id"] in vps_drive_ids:
                matched[df["id"]] = vps_drive_ids[df["id"]]

        synced_count = len(matched)
        vps_only = len([f for f in vps_files if not f.get("drive_file_id")])
        drive_only = len([f for f in drive_files if f["id"] not in matched])

        # Collect unique folder paths for filter
        folder_paths = sorted(set(
            f.get("folder_path", "") for f in drive_files if f.get("folder_path")
        ))

        # Collect unique sources for filter
        sources = sorted(set(
            (f.get("source", "active_clients") + ("/" + f["paralegal"] if f.get("paralegal") else ""))
            for f in drive_files
        ))

        # Tasks entries for display
        tasks_info = []
        for entry in (tasks_entries if handler else []):
            tasks_info.append({
                "paralegal": entry.get("paralegal", ""),
                "name": entry.get("name", ""),
                "archived": entry.get("archived", False)
            })

        # Stats
        ac_count = len([f for f in drive_files if f.get("source") == "active_clients"])
        tasks_count = len([f for f in drive_files if f.get("source") == "tasks"])

        return {
            "success": True,
            "client": {
                "id": client.id,
                "name": f"{client.last_name}, {client.first_name}",
                "drive_folder_id": client.drive_folder_id
            },
            "drive_folder": drive_folder,
            "vps_files": vps_files,
            "drive_files": drive_files,
            "matched": matched,
            "folder_paths": folder_paths,
            "sources": sources,
            "tasks_info": tasks_info,
            "stats": {
                "vps_total": len(vps_files),
                "drive_total": len(drive_files),
                "ac_total": ac_count,
                "tasks_total": tasks_count,
                "synced": synced_count,
                "vps_only": vps_only,
                "drive_only": drive_only
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Compare failed: {str(e)}")


@router.get("/api/drive-folders")
async def list_drive_folders(
    request: Request,
    db: Session = Depends(get_db)
):
    """List all folders in Active Clients (for manual linking dropdown)."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    handler = _get_handler(db, request.state.org_id)
    if not handler:
        return {"success": False, "error": "Drive not connected", "folders": []}

    folders = handler.list_active_clients_folders()
    return {"success": True, "folders": folders}


@router.post("/api/client/{client_id}/link-folder")
async def link_client_folder(
    request: Request,
    client_id: int,
    folder_id: str = Form(...),
    folder_name: str = Form(...),
    db: Session = Depends(get_db)
):
    """Manually link a client to a Google Drive folder."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    client.drive_folder_id = folder_id
    client.drive_folder_name = folder_name
    db.commit()

    return {
        "success": True,
        "message": f"Linked {client.last_name}, {client.first_name} to '{folder_name}'"
    }


@router.post("/api/client/{client_id}/unlink-folder")
async def unlink_client_folder(
    request: Request,
    client_id: int,
    db: Session = Depends(get_db)
):
    """Remove the Drive folder link from a client."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    client.drive_folder_id = None
    client.drive_folder_name = None
    db.commit()

    return {"success": True, "message": "Folder link removed"}


@router.post("/api/client/{client_id}/clear-tasks-cache")
async def clear_tasks_cache(
    request: Request,
    client_id: int,
    db: Session = Depends(get_db)
):
    """Clear cached Tasks folder data for a client (forces re-search on next load)."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    client.tasks_folder_data = None
    db.commit()

    return {"success": True, "message": "Tasks cache cleared"}


@router.get("/api/clients-with-counts")
async def list_clients_with_file_counts(
    request: Request,
    db: Session = Depends(get_db)
):
    """List all clients with CaseHub document counts."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Sentinela T5 (2026-05-28): filter clients por org_id pra evitar IDOR
    # cross-tenant — JOIN raiz (clients) não escopava por org. CWE-639.
    result = db.execute(text("""
        SELECT c.id, c.first_name, c.last_name, COUNT(d.id) as doc_count,
               c.drive_folder_id, c.drive_folder_name
        FROM clients c
        LEFT JOIN documents d ON d.client_id = c.id
        WHERE c.org_id = :org_id
        GROUP BY c.id, c.first_name, c.last_name, c.drive_folder_id, c.drive_folder_name
        ORDER BY c.last_name, c.first_name
    """), {"org_id": request.state.org_id})

    clients = []
    for r in result.fetchall():
        clients.append({
            "id": r[0],
            "first_name": r[1],
            "last_name": r[2],
            "doc_count": r[3],
            "drive_folder_id": r[4],
            "drive_folder_name": r[5]
        })

    return {"success": True, "clients": clients}
