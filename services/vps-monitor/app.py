"""
VPS Monitor - Real-time Dashboard
Monitor system metrics, PM2 services, and application usage
"""
from dotenv import load_dotenv
import os
load_dotenv(os.getenv('APP_BASE_PATH', '/opt/casehub') + '/vps-monitor/.env')

import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

from collectors.system import system_collector
from collectors.pm2 import pm2_collector
from collectors.services import services_collector
from collectors.applications import applications_collector
from collectors.activity import activity_collector
from collectors.whatsapp import whatsapp_collector
from collectors.integrations import integrations_collector
from collectors.database import database_collector
from collectors.nginx import nginx_collector
from collectors.security import security_collector

app = FastAPI(
    title="VPS Monitor",
    description="Real-time VPS monitoring dashboard",
    version="1.0.0"
)

# Static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# === Dashboard Routes ===

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page"""
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "title": "VPS Monitor"
    })


@app.get("/orchestrator", response_class=HTMLResponse)
async def orchestrator(request: Request):
    """Orchestrator visual interface - n8n style"""
    return templates.TemplateResponse("orchestrator.html", {
        "request": request,
        "title": "VPS Orchestrator"
    })


@app.get("/api/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


# === System Metrics ===

@app.get("/api/system")
async def get_system_metrics():
    """Get current system metrics"""
    return system_collector.collect()


@app.get("/api/system/history")
async def get_system_history(metric: str = None):
    """Get system metrics history"""
    return system_collector.get_history(metric)


# === PM2 Process Management ===

@app.get("/api/pm2")
async def get_pm2_processes():
    """Get all PM2 processes"""
    return pm2_collector.collect()


@app.get("/api/pm2/{name}")
async def get_pm2_process(name: str):
    """Get specific PM2 process"""
    proc = pm2_collector.get_process(name)
    if not proc:
        raise HTTPException(status_code=404, detail=f"Process {name} not found")
    return proc


@app.post("/api/pm2/{name}/restart")
async def restart_pm2_process(name: str):
    """Restart a PM2 process (admin only)"""
    result = pm2_collector.restart_process(name)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    return result


@app.get("/api/pm2/{name}/logs")
async def get_pm2_logs(name: str, lines: int = 50):
    """Get PM2 process logs"""
    return pm2_collector.get_logs(name, lines)


@app.post("/api/pm2/{name}/stop")
async def stop_pm2_process(name: str):
    """Stop a PM2 process"""
    result = pm2_collector.stop_process(name)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    return result


@app.post("/api/pm2/{name}/start")
async def start_pm2_process(name: str):
    """Start a PM2 process"""
    result = pm2_collector.start_process(name)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    return result


@app.delete("/api/pm2/{name}")
async def delete_pm2_process(name: str):
    """Delete a PM2 process (remove from PM2)"""
    result = pm2_collector.delete_process(name)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    return result


@app.get("/api/pm2/{name}/info")
async def get_pm2_process_info(name: str):
    """Get detailed PM2 process info including env vars"""
    result = pm2_collector.get_process_info(name)
    if not result.get("success", True) == False:
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
    return result


@app.post("/api/pm2/{name}/flush")
async def flush_pm2_process_logs(name: str):
    """Flush logs for a specific PM2 process"""
    result = pm2_collector.flush_logs(name)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    return result


@app.post("/api/pm2/flush")
async def flush_all_pm2_logs():
    """Flush logs for all PM2 processes"""
    result = pm2_collector.flush_logs()
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    return result


@app.post("/api/pm2/{name}/reload")
async def reload_pm2_process(name: str):
    """Reload a PM2 process with 0-downtime (graceful reload)"""
    result = pm2_collector.reload_process(name)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    return result


@app.post("/api/pm2/{name}/scale/{instances}")
async def scale_pm2_process(name: str, instances: int):
    """Scale a PM2 process to N instances"""
    if instances < 1 or instances > 16:
        raise HTTPException(status_code=400, detail="Instances must be between 1 and 16")
    result = pm2_collector.scale_process(name, instances)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    return result


@app.get("/api/pm2/{name}/describe")
async def describe_pm2_process(name: str):
    """Get full PM2 describe output for a process"""
    result = pm2_collector.describe_process(name)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
    return result


@app.post("/api/pm2/save")
async def save_pm2_state():
    """Save current PM2 process list (pm2 save)"""
    result = pm2_collector.save()
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    return result


@app.post("/api/pm2/{name}/reset")
async def reset_pm2_restart_count(name: str):
    """Reset restart count for a PM2 process"""
    result = pm2_collector.reset_restart_count(name)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    return result


@app.post("/api/pm2/{name}/memory-limit/{max_memory}")
async def set_pm2_memory_limit(name: str, max_memory: str):
    """Set memory limit for a PM2 process (e.g., 500M, 1G)"""
    # Validate format
    if not max_memory.upper().endswith(('M', 'G', 'K')):
        raise HTTPException(status_code=400, detail="Memory must end with M, G, or K (e.g., 500M, 1G)")
    result = pm2_collector.set_memory_limit(name, max_memory.upper())
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    return result


# === Services Health ===

@app.get("/api/services")
async def get_services_health():
    """Get health status of all services"""
    return await services_collector.check_all()


@app.get("/api/services/{name}")
async def get_service_health(name: str):
    """Get health status of specific service"""
    result = await services_collector.check_service(name)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# === WhatsApp Bot Metrics ===

@app.get("/api/whatsapp")
async def get_whatsapp_metrics():
    """Get WhatsApp bot metrics and status"""
    return await whatsapp_collector.collect()


@app.get("/api/whatsapp/status")
async def get_whatsapp_status():
    """Get WhatsApp connection status only"""
    return await whatsapp_collector.get_status()


@app.get("/api/whatsapp/stats")
async def get_whatsapp_stats():
    """Get WhatsApp database statistics"""
    return whatsapp_collector.get_db_stats()


# === External Integrations Health ===

@app.get("/api/integrations")
async def get_all_integrations():
    """Get health status of all external integrations"""
    return await integrations_collector.collect_all()


@app.get("/api/integrations/moskit")
async def get_moskit_health():
    """Check Moskit CRM API health"""
    return await integrations_collector.check_moskit()


@app.get("/api/integrations/gemini")
async def get_gemini_health():
    """Check Google Gemini API health"""
    return await integrations_collector.check_gemini()


@app.get("/api/integrations/stripe")
async def get_stripe_health():
    """Check Stripe API connectivity"""
    return await integrations_collector.check_stripe()


# === Database Metrics ===

@app.get("/api/databases")
async def get_all_databases():
    """Get metrics from all databases"""
    return database_collector.collect_all()


@app.get("/api/databases/mysql")
async def get_mysql_metrics():
    """Get MySQL database metrics"""
    return database_collector.get_mysql_metrics()


@app.get("/api/databases/postgres")
async def get_postgres_metrics():
    """Get PostgreSQL database metrics"""
    return database_collector.get_postgres_metrics()

# === Nginx Metrics ===

@app.get("/api/nginx")
async def get_nginx_metrics():
    """Get Nginx server metrics"""
    return nginx_collector.collect_all()



# === Application Metrics ===

@app.get("/api/apps")
async def get_all_apps_metrics():
    """Get metrics from all applications"""
    return applications_collector.collect_all()


@app.get("/api/apps/casehub")
async def get_casehub_metrics():
    """Get CaseHub metrics"""
    return applications_collector.collect_casehub()


@app.get("/api/apps/intake")
async def get_intake_metrics():
    """Get Intake metrics"""
    return applications_collector.collect_intake()


@app.get("/api/apps/tools")
async def get_tools_metrics():
    """Get CaseHub Tools metrics"""
    return applications_collector.collect_tools()


# === Shared stream snapshots (avoid duplicate collectors per client) ===

STREAM_SNAPSHOT = None
ACTIVITY_SNAPSHOT = None
STREAM_TASK = None
ACTIVITY_TASK = None


async def _refresh_stream_snapshot() -> None:
    """Continuously refresh dashboard snapshot used by SSE clients."""
    global STREAM_SNAPSHOT
    while True:
        try:
            system = await asyncio.to_thread(system_collector.collect)
            pm2 = await asyncio.to_thread(pm2_collector.collect)
            services = await services_collector.check_all()
            STREAM_SNAPSHOT = {
                "timestamp": datetime.now().isoformat(),
                "system": system,
                "pm2": pm2,
                "services": services,
            }
        except Exception as e:
            STREAM_SNAPSHOT = {
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
            }
        await asyncio.sleep(5)


async def _refresh_activity_snapshot() -> None:
    """Continuously refresh activity snapshot used by SSE clients."""
    global ACTIVITY_SNAPSHOT
    while True:
        try:
            users_data = await asyncio.to_thread(activity_collector.get_active_users, minutes=5)
            recent_events = await asyncio.to_thread(activity_collector.get_recent_events, 20)
            ACTIVITY_SNAPSHOT = {
                "timestamp": datetime.now().isoformat(),
                "active_count": users_data.get('total_active', 0),
                "by_source": users_data.get('by_source', {}),
                "users": users_data.get('users', []),
                "recent_events": recent_events,
            }
        except Exception as e:
            ACTIVITY_SNAPSHOT = {
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
            }
        await asyncio.sleep(2)


# === Combined Dashboard Data ===

@app.get("/api/dashboard")
async def get_dashboard_data():
    """Get all dashboard data in one request"""
    system = system_collector.collect()
    pm2 = pm2_collector.collect()
    services = await services_collector.check_all()
    apps = applications_collector.collect_all()
    databases = database_collector.collect_all()
    integrations = await integrations_collector.collect_all()

    return {
        "timestamp": datetime.now().isoformat(),
        "system": system,
        "pm2": pm2,
        "services": services,
        "applications": apps,
        "databases": databases,
        "integrations": integrations,
    }


# === Real-time SSE Stream ===

async def event_generator() -> AsyncGenerator[dict, None]:
    """Generate events for SSE stream"""
    while True:
        data = STREAM_SNAPSHOT
        if not data:
            data = {"timestamp": datetime.now().isoformat(), "loading": True}

        event_name = "error" if data.get("error") else "update"
        yield {
            "event": event_name,
            "data": json.dumps(data)
        }

        await asyncio.sleep(5)


@app.get("/api/stream")
async def stream_updates():
    """SSE endpoint for real-time updates"""
    return EventSourceResponse(event_generator())


# === User Activity Tracking ===

@app.get("/activity", response_class=HTMLResponse)
async def activity_dashboard(request: Request):
    """Real-time user activity dashboard"""
    return templates.TemplateResponse("activity.html", {
        "request": request,
        "title": "Activity Monitor - Quem está online"
    })


@app.post("/api/activity/track")
async def track_activity(request: Request):
    """Receive tracking events from frontend scripts"""
    try:
        data = await request.json()
        # Add IP address from request
        data['ip_address'] = request.client.host if request.client else ''
        data['user_agent'] = request.headers.get('user-agent', '')[:500]

        success = activity_collector.record_event(data)
        return {"success": success}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/activity/users")
async def get_active_users(source: str = None, minutes: int = 5):
    """Get all currently active users"""
    return activity_collector.get_active_users(source=source, minutes=minutes)


@app.get("/api/activity/user/{session_id}")
async def get_user_timeline(session_id: str, limit: int = 50):
    """Get activity timeline for a specific session"""
    return {
        "session_id": session_id,
        "timeline": activity_collector.get_user_timeline(session_id, limit)
    }


@app.get("/api/activity/feed")
async def get_activity_feed(limit: int = 50):
    """Get recent events for live feed"""
    return {
        "timestamp": datetime.now().isoformat(),
        "events": activity_collector.get_recent_events(limit)
    }


@app.get("/api/activity/stats")
async def get_activity_stats():
    """Get aggregate activity statistics"""
    return activity_collector.get_stats()


async def activity_event_generator() -> AsyncGenerator[dict, None]:
    """Generate events for activity SSE stream"""
    while True:
        data = ACTIVITY_SNAPSHOT
        if not data:
            data = {"timestamp": datetime.now().isoformat(), "loading": True}

        event_name = "error" if data.get("error") else "activity_update"
        yield {
            "event": event_name,
            "data": json.dumps(data)
        }

        await asyncio.sleep(2)


@app.get("/api/activity/stream")
async def stream_activity_updates():
    """SSE endpoint for real-time activity updates"""
    return EventSourceResponse(activity_event_generator())



# === WhatsApp Bot Control ===

@app.post("/api/whatsapp/bot-toggle")
async def toggle_whatsapp_bot(request: Request):
    """Toggle WhatsApp bot on/off"""
    try:
        data = await request.json()
        enable = data.get("enable", True)
        
        # Call WhatsApp bot's toggle endpoint
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://127.0.0.1:3001/api/admin/bot-global-toggle",
                json={"enable": enable},
                timeout=10.0
            )
            return response.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/whatsapp/bot-status")
async def get_whatsapp_bot_status():
    """Get WhatsApp bot enabled/disabled status"""
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "http://127.0.0.1:3001/api/admin/bot-status",
                timeout=10.0
            )
            return response.json()
    except Exception as e:
        return {"success": False, "enabled": None, "error": str(e)}


# === Email Processing Control ===

@app.post("/api/email/process")
async def trigger_email_processing(request: Request):
    """Trigger email processing manually"""
    try:
        import subprocess
        result = subprocess.run(
            ["python3", os.getenv("APP_BASE_PATH", "/opt/casehub") + "/ilc-tools/email_processor.py", "--check-clients"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=os.getenv("APP_BASE_PATH", "/opt/casehub") + "/ilc-tools"
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout[:2000] if result.stdout else "",
            "errors": result.stderr[:1000] if result.stderr else "",
            "timestamp": datetime.now().isoformat()
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Email processing timed out after 120s"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/email/status")
async def get_email_processing_status():
    """Get email processing status from logs"""
    try:
        import subprocess
        # Check last email processor logs
        result = subprocess.run(
            ["tail", "-50", "/root/.pm2/logs/ilc-tools-out.log"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Parse for email processing related lines
        lines = result.stdout.split("\n")
        email_lines = [l for l in lines if "email" in l.lower() or "imap" in l.lower() or "notion" in l.lower()]
        
        return {
            "success": True,
            "recent_activity": email_lines[-10:] if email_lines else [],
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/email/stats")
async def get_email_stats():
    """Get email processing statistics"""
    try:
        import subprocess
        import os
        
        # Count attachments in recent days
        attachments_path = os.getenv("APP_BASE_PATH", "/opt/casehub") + "/ilc-tools/attachments"
        total_attachments = 0
        recent_days = []
        
        if os.path.exists(attachments_path):
            for day_dir in sorted(os.listdir(attachments_path))[-7:]:  # Last 7 days
                day_path = os.path.join(attachments_path, day_dir)
                if os.path.isdir(day_path):
                    count = len([f for f in os.listdir(day_path) if os.path.isfile(os.path.join(day_path, f))])
                    recent_days.append({"date": day_dir, "attachments": count})
                    total_attachments += count
        
        return {
            "success": True,
            "total_recent_attachments": total_attachments,
            "by_day": recent_days,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# === Notion Health ===

@app.get("/api/notion/health")
async def check_notion_health():
    """Check Notion API connectivity"""
    try:
        import httpx
        import os
        
        notion_token = os.environ.get("NOTION_TOKEN", "")
        if not notion_token:
            # Try to read from ilc-tools .env
            env_path = os.getenv("APP_BASE_PATH", "/opt/casehub") + "/ilc-tools/.env"
            if os.path.exists(env_path):
                with open(env_path) as f:
                    for line in f:
                        if line.startswith("NOTION_API_KEY=") or line.startswith("NOTION_TOKEN="):
                            notion_token = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
        
        if not notion_token:
            return {"success": False, "error": "Notion token not found"}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.notion.com/v1/users/me",
                headers={
                    "Authorization": f"Bearer {notion_token}",
                    "Notion-Version": "2022-06-28"
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "connected": True,
                    "user": data.get("name", "Unknown"),
                    "type": data.get("type", "Unknown"),
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "success": False,
                    "connected": False,
                    "status_code": response.status_code,
                    "error": response.text[:200]
                }
    except Exception as e:
        return {"success": False, "connected": False, "error": str(e)}


@app.post("/api/notion/retry-failed")
async def retry_failed_notion_tasks():
    """Retry failed Notion task creations"""
    try:
        import subprocess
        # This would call a script that retries failed Notion operations
        result = subprocess.run(
            ["python3", "-c", """
import sys
sys.path.insert(0, os.getenv('APP_BASE_PATH', '/opt/casehub') + '/ilc-tools')
from notion_notifier import retry_failed_notifications
retry_failed_notifications()
print('Retry completed')
"""],
            capture_output=True,
            text=True,
            timeout=60
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout[:1000],
            "errors": result.stderr[:500] if result.stderr else "",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# === Database Control ===

@app.post("/api/db/postgresql/start")
async def start_postgresql():
    """Start PostgreSQL service"""
    try:
        import subprocess
        result = subprocess.run(
            ["systemctl", "start", "postgresql"],
            capture_output=True,
            text=True,
            timeout=30
        )
        return {
            "success": result.returncode == 0,
            "service": "postgresql",
            "action": "start",
            "message": result.stdout or "PostgreSQL started",
            "errors": result.stderr[:500] if result.stderr else ""
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/db/postgresql/stop")
async def stop_postgresql():
    """Stop PostgreSQL service"""
    try:
        import subprocess
        result = subprocess.run(
            ["systemctl", "stop", "postgresql"],
            capture_output=True,
            text=True,
            timeout=30
        )
        return {
            "success": result.returncode == 0,
            "service": "postgresql",
            "action": "stop",
            "message": result.stdout or "PostgreSQL stopped",
            "errors": result.stderr[:500] if result.stderr else ""
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/db/mariadb/start")
async def start_mariadb():
    """Start MariaDB service"""
    try:
        import subprocess
        result = subprocess.run(
            ["systemctl", "start", "mariadb"],
            capture_output=True,
            text=True,
            timeout=30
        )
        return {
            "success": result.returncode == 0,
            "service": "mariadb",
            "action": "start",
            "message": result.stdout or "MariaDB started",
            "errors": result.stderr[:500] if result.stderr else ""
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/db/mariadb/stop")
async def stop_mariadb():
    """Stop MariaDB service"""
    try:
        import subprocess
        result = subprocess.run(
            ["systemctl", "stop", "mariadb"],
            capture_output=True,
            text=True,
            timeout=30
        )
        return {
            "success": result.returncode == 0,
            "service": "mariadb",
            "action": "stop",
            "message": result.stdout or "MariaDB stopped",
            "errors": result.stderr[:500] if result.stderr else ""
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/db/backup")
async def backup_databases(request: Request):
    """Execute database backup"""
    try:
        import subprocess
        from datetime import datetime
        
        data = await request.json() if request.headers.get("content-type") == "application/json" else {}
        databases = data.get("databases", ["postgresql", "mariadb"])
        
        results = {}
        backup_dir = f"/root/backups/{datetime.now().strftime('%Y-%m-%d')}"
        
        # Create backup directory
        subprocess.run(["mkdir", "-p", backup_dir], check=True)
        
        if "postgresql" in databases:
            pg_file = f"{backup_dir}/postgresql_{datetime.now().strftime('%H%M%S')}.sql"
            result = subprocess.run(
                ["pg_dumpall", "-U", "postgres", "-f", pg_file],
                capture_output=True,
                text=True,
                timeout=300
            )
            results["postgresql"] = {
                "success": result.returncode == 0,
                "file": pg_file if result.returncode == 0 else None,
                "error": result.stderr[:200] if result.stderr else None
            }
        
        if "mariadb" in databases:
            maria_file = f"{backup_dir}/mariadb_{datetime.now().strftime('%H%M%S')}.sql"
            result = subprocess.run(
                ["mysqldump", "--all-databases", "-r", maria_file],
                capture_output=True,
                text=True,
                timeout=300
            )
            results["mariadb"] = {
                "success": result.returncode == 0,
                "file": maria_file if result.returncode == 0 else None,
                "error": result.stderr[:200] if result.stderr else None
            }
        
        return {
            "success": all(r.get("success", False) for r in results.values()),
            "backup_dir": backup_dir,
            "results": results,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# === System Extended ===

@app.get("/api/system/disk-details")
async def get_disk_details():
    """Get detailed disk usage by directory"""
    try:
        import subprocess
        
        # Get disk usage for key directories
        directories = [
            "/var/www/casehub.app",
            "/root/.pm2/logs",
            "/root/backups",
            "/var/log",
            "/tmp"
        ]
        
        results = {}
        for dir_path in directories:
            try:
                result = subprocess.run(
                    ["du", "-sh", dir_path],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode == 0:
                    size = result.stdout.split()[0]
                    results[dir_path] = size
            except:
                results[dir_path] = "N/A"
        
        # Get overall disk usage
        df_result = subprocess.run(
            ["df", "-h", "/"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        disk_info = {}
        if df_result.returncode == 0:
            lines = df_result.stdout.strip().split("\n")
            if len(lines) > 1:
                parts = lines[1].split()
                disk_info = {
                    "total": parts[1] if len(parts) > 1 else "N/A",
                    "used": parts[2] if len(parts) > 2 else "N/A",
                    "available": parts[3] if len(parts) > 3 else "N/A",
                    "percent": parts[4] if len(parts) > 4 else "N/A"
                }
        
        return {
            "success": True,
            "disk": disk_info,
            "directories": results,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/system/cleanup-logs")
async def cleanup_old_logs(request: Request):
    """Clean up old log files"""
    try:
        import subprocess
        
        data = await request.json() if request.headers.get("content-type") == "application/json" else {}
        days = data.get("days", 7)  # Default: keep last 7 days
        
        results = {}
        
        # Clean PM2 logs older than N days
        pm2_result = subprocess.run(
            ["find", "/root/.pm2/logs", "-name", "*.log", "-mtime", f"+{days}", "-delete"],
            capture_output=True,
            text=True,
            timeout=60
        )
        results["pm2_logs"] = {"success": pm2_result.returncode == 0}
        
        # Clean old attachments (keep 30 days)
        attach_result = subprocess.run(
            ["find", os.getenv("APP_BASE_PATH", "/opt/casehub") + "/ilc-tools/attachments", "-type", "d", "-mtime", "+30", "-exec", "rm", "-rf", "{}", "+"],
            capture_output=True,
            text=True,
            timeout=60
        )
        results["attachments"] = {"success": attach_result.returncode == 0}
        
        # Flush PM2 logs
        flush_result = subprocess.run(
            ["pm2", "flush"],
            capture_output=True,
            text=True,
            timeout=30
        )
        results["pm2_flush"] = {"success": flush_result.returncode == 0}
        
        return {
            "success": True,
            "cleaned": results,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# === Nginx Control ===

@app.post("/api/nginx/reload")
async def reload_nginx():
    """Reload Nginx configuration"""
    try:
        import subprocess
        
        # First test config
        test_result = subprocess.run(
            ["nginx", "-t"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if test_result.returncode != 0:
            return {
                "success": False,
                "error": "Nginx config test failed",
                "details": test_result.stderr
            }
        
        # Reload
        reload_result = subprocess.run(
            ["systemctl", "reload", "nginx"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        return {
            "success": reload_result.returncode == 0,
            "action": "reload",
            "message": "Nginx reloaded successfully" if reload_result.returncode == 0 else reload_result.stderr,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/nginx/restart")
async def restart_nginx():
    """Restart Nginx service"""
    try:
        import subprocess
        result = subprocess.run(
            ["systemctl", "restart", "nginx"],
            capture_output=True,
            text=True,
            timeout=30
        )
        return {
            "success": result.returncode == 0,
            "action": "restart",
            "message": "Nginx restarted" if result.returncode == 0 else result.stderr,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# === Maestro Control ===

@app.get("/api/maestro/status")
async def get_maestro_status():
    """Get Maestro orchestrator status"""
    try:
        import subprocess
        import os
        
        # Check if Maestro process is running via PM2
        pm2_result = subprocess.run(
            ["pm2", "jlist"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        maestro_status = "unknown"
        maestro_info = {}
        
        if pm2_result.returncode == 0:
            import json
            processes = json.loads(pm2_result.stdout)
            for proc in processes:
                if "maestro" in proc.get("name", "").lower():
                    maestro_status = proc.get("pm2_env", {}).get("status", "unknown")
                    maestro_info = {
                        "name": proc.get("name"),
                        "pid": proc.get("pid"),
                        "memory": proc.get("monit", {}).get("memory", 0),
                        "cpu": proc.get("monit", {}).get("cpu", 0),
                        "uptime": proc.get("pm2_env", {}).get("pm_uptime", 0),
                        "restarts": proc.get("pm2_env", {}).get("restart_time", 0)
                    }
                    break
        
        # Check Maestro log for recent activity
        log_path = "/root/.pm2/logs/maestro-out.log"
        recent_logs = []
        if os.path.exists(log_path):
            result = subprocess.run(
                ["tail", "-20", log_path],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                recent_logs = result.stdout.strip().split("\n")[-5:]
        
        return {
            "success": True,
            "status": maestro_status,
            "info": maestro_info,
            "recent_logs": recent_logs,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/maestro/force-check")
async def force_maestro_check():
    """Force Maestro to run a system check"""
    try:
        import subprocess
        
        # Restart Maestro to trigger immediate check
        result = subprocess.run(
            ["pm2", "restart", "maestro"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        return {
            "success": result.returncode == 0,
            "message": "Maestro restarted for forced check" if result.returncode == 0 else result.stderr,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"success": False, "error": str(e)}



# ============================================================
# VPS MASTER CONTROL CENTER - Configuration Management APIs
# Added: February 2026
# ============================================================

import re
import shutil
from pathlib import Path

# === Configuration File Registry ===

CONFIG_FILES = {
    "email_processor": {
        "path": os.getenv("APP_BASE_PATH", "/opt/casehub") + "/casehub/email_processor.py",
        "service": "casehub",
        "variables": ["CLIENT_MAPPING", "EXPANSION_KEYWORDS"]
    },
    "notion_notifier": {
        "path": os.getenv("APP_BASE_PATH", "/opt/casehub") + "/casehub/notion_notifier.py",
        "service": "casehub",
        "variables": ["TEAM_IDS", "TEAM_EMAILS", "DATABASE_IDS"]
    },
    "casehub_auth": {
        "path": os.getenv("APP_BASE_PATH", "/opt/casehub") + "/casehub/auth.py",
        "service": "casehub",
        "variables": ["ACCESS_TOKEN_EXPIRE_MINUTES"]
    },
    "ilc_tools_auth": {
        "path": os.getenv("APP_BASE_PATH", "/opt/casehub") + "/ilc-tools/auth.py",
        "service": "ilc-tools",
        "variables": ["JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "JWT_REFRESH_TOKEN_EXPIRE_DAYS"]
    },
    "ilc_tools_app": {
        "path": os.getenv("APP_BASE_PATH", "/opt/casehub") + "/ilc-tools/app.py",
        "service": "ilc-tools",
        "variables": ["RATE_LIMITS", "ALLOWED_ORIGINS"]
    },
    "vps_monitor_config": {
        "path": os.getenv("APP_BASE_PATH", "/opt/casehub") + "/vps-monitor/config.py",
        "service": "vps-monitor",
        "variables": ["UPDATE_INTERVALS", "HISTORY_MAX_POINTS"]
    },
    "client_intake_app": {
        "path": os.getenv("APP_BASE_PATH", "/opt/casehub") + "/client-intake/app.py",
        "service": "client-intake",
        "variables": ["MAX_FILE_SIZE", "ALLOWED_EXTENSIONS", "PARALEGAL_EMAILS"]
    },
    "document_watcher": {
        "path": os.getenv("APP_BASE_PATH", "/opt/casehub") + "/document-service/document_watcher.py",
        "service": "document-watcher",
        "variables": ["WATCH_DIRS"]
    },
    "maestro": {
        "path": "/opt/maestro/maestro.py",
        "service": "maestro",
        "variables": ["CHECK_INTERVAL", "ALERT_THRESHOLD"]
    },
    "whatsapp_server": {
        "path": os.getenv("APP_BASE_PATH", "/opt/casehub") + "/whatsapp-bot/server.js",
        "service": "whatsapp-bot",
        "variables": ["BOT_CONFIG", "TEMPLATES", "LLM_CONFIG"]
    }
}

BACKUP_DIR = os.getenv("APP_BASE_PATH", "/opt/casehub") + "/vps-monitor/backups/configs"

def ensure_backup_dir():
    """Ensure backup directory exists"""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)


# === Config Files Management ===

@app.get("/api/config/files")
async def list_config_files():
    """List all configurable files with their variables"""
    result = {}
    for file_id, info in CONFIG_FILES.items():
        path = Path(info["path"])
        result[file_id] = {
            "path": info["path"],
            "service": info["service"],
            "variables": info["variables"],
            "exists": path.exists(),
            "size": path.stat().st_size if path.exists() else 0,
            "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat() if path.exists() else None
        }
    return {"success": True, "files": result}


@app.get("/api/config/read/{file_id}")
async def read_config_file(file_id: str):
    """Read contents of a config file"""
    if file_id not in CONFIG_FILES:
        raise HTTPException(status_code=404, detail=f"Config file {file_id} not found")

    file_path = Path(CONFIG_FILES[file_id]["path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File {file_path} does not exist")

    try:
        content = file_path.read_text(encoding="utf-8")
        return {
            "success": True,
            "file_id": file_id,
            "path": str(file_path),
            "content": content,
            "lines": len(content.splitlines()),
            "size": len(content)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/config/variables/{file_id}")
async def get_config_variables(file_id: str):
    """Extract specific variables from a config file"""
    if file_id not in CONFIG_FILES:
        raise HTTPException(status_code=404, detail=f"Config file {file_id} not found")

    file_info = CONFIG_FILES[file_id]
    file_path = Path(file_info["path"])

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File {file_path} does not exist")

    try:
        content = file_path.read_text(encoding="utf-8")
        variables = {}

        for var_name in file_info["variables"]:
            # Python dict/list pattern
            pattern = rf"^{var_name}\s*=\s*(\{{[\s\S]*?\n\}}|\[[\s\S]*?\n\]|\"[^\"]*\"|\'[^\']*\'|\d+)"
            match = re.search(pattern, content, re.MULTILINE)
            if match:
                try:
                    import ast
                    variables[var_name] = ast.literal_eval(match.group(1))
                except:
                    variables[var_name] = match.group(1)
            else:
                variables[var_name] = None

        return {
            "success": True,
            "file_id": file_id,
            "variables": variables
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/config/backup/{file_id}")
async def backup_config_file(file_id: str):
    """Create a backup of a config file"""
    if file_id not in CONFIG_FILES:
        raise HTTPException(status_code=404, detail=f"Config file {file_id} not found")

    file_path = Path(CONFIG_FILES[file_id]["path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File {file_path} does not exist")

    try:
        ensure_backup_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{file_id}_{timestamp}{file_path.suffix}"
        backup_path = Path(BACKUP_DIR) / backup_name

        shutil.copy2(file_path, backup_path)

        return {
            "success": True,
            "backup_path": str(backup_path),
            "backup_name": backup_name,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/config/write/{file_id}")
async def write_config_file(file_id: str, request: Request):
    """Write/update a config file (creates backup first)"""
    if file_id not in CONFIG_FILES:
        raise HTTPException(status_code=404, detail=f"Config file {file_id} not found")

    try:
        data = await request.json()
        content = data.get("content")

        if not content:
            raise HTTPException(status_code=400, detail="Content is required")

        file_path = Path(CONFIG_FILES[file_id]["path"])

        # Create backup first
        if file_path.exists():
            ensure_backup_dir()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{file_id}_{timestamp}_before_write{file_path.suffix}"
            backup_path = Path(BACKUP_DIR) / backup_name
            shutil.copy2(file_path, backup_path)

        # Write new content
        file_path.write_text(content, encoding="utf-8")

        # Restart associated service
        service = CONFIG_FILES[file_id]["service"]
        restart_result = None
        if service:
            import subprocess
            result = subprocess.run(
                ["pm2", "restart", service],
                capture_output=True,
                text=True,
                timeout=30
            )
            restart_result = {
                "service": service,
                "restarted": result.returncode == 0,
                "output": result.stdout if result.returncode == 0 else result.stderr
            }

        return {
            "success": True,
            "file_id": file_id,
            "path": str(file_path),
            "backup": backup_name if file_path.exists() else None,
            "service_restart": restart_result,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# === Client Management (CLIENT_MAPPING) ===

def get_client_mapping():
    """Read CLIENT_MAPPING from email_processor.py"""
    file_path = Path(CONFIG_FILES["email_processor"]["path"])
    content = file_path.read_text(encoding="utf-8")

    # Find CLIENT_MAPPING dict
    pattern = r"CLIENT_MAPPING\s*=\s*(\{[\s\S]*?\n\})"
    match = re.search(pattern, content)
    if match:
        try:
            import ast
            return ast.literal_eval(match.group(1))
        except:
            return {}
    return {}


def save_client_mapping(clients: dict):
    """Save CLIENT_MAPPING to email_processor.py"""
    file_path = Path(CONFIG_FILES["email_processor"]["path"])
    content = file_path.read_text(encoding="utf-8")

    # Create backup
    ensure_backup_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = Path(BACKUP_DIR) / f"email_processor_{timestamp}_clients.py"
    shutil.copy2(file_path, backup_path)

    # Format new CLIENT_MAPPING
    import pprint
    formatted = "CLIENT_MAPPING = " + pprint.pformat(clients, indent=4, width=100)

    # Replace in content
    pattern = r"CLIENT_MAPPING\s*=\s*\{[\s\S]*?\n\}"
    new_content = re.sub(pattern, formatted, content)

    file_path.write_text(new_content, encoding="utf-8")
    return backup_path


@app.get("/api/clients")
async def list_clients():
    """List all clients from CLIENT_MAPPING"""
    try:
        clients = get_client_mapping()
        result = []
        for email, info in clients.items():
            result.append({
                "email": email,
                "name": info.get("name", ""),
                "paralegal": info.get("paralegal", ""),
                "case": info.get("case", ""),
                "case_type": info.get("case_type", ""),
                "timezone": info.get("timezone", ""),
                "language": info.get("language", "en"),
                "phone": info.get("phone", ""),
                "cc_always": info.get("cc_always", [])
            })
        return {"success": True, "clients": result, "count": len(result)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/clients/{email:path}")
async def get_client(email: str):
    """Get specific client by email"""
    try:
        clients = get_client_mapping()
        if email not in clients:
            raise HTTPException(status_code=404, detail=f"Client {email} not found")

        client = clients[email]
        return {
            "success": True,
            "client": {
                "email": email,
                **client
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/clients")
async def create_client(request: Request):
    """Add a new client to CLIENT_MAPPING"""
    try:
        data = await request.json()
        email = data.get("email")

        if not email:
            raise HTTPException(status_code=400, detail="Email is required")

        clients = get_client_mapping()

        if email in clients:
            raise HTTPException(status_code=409, detail=f"Client {email} already exists")

        # Required fields
        clients[email] = {
            "name": data.get("name", ""),
            "paralegal": data.get("paralegal", "Ana Clara"),
            "case": data.get("case", "")
        }

        # Optional fields
        if data.get("case_type"):
            clients[email]["case_type"] = data["case_type"]
        if data.get("timezone"):
            clients[email]["timezone"] = data["timezone"]
        if data.get("language"):
            clients[email]["language"] = data["language"]
        if data.get("phone"):
            clients[email]["phone"] = data["phone"]
        if data.get("cc_always"):
            clients[email]["cc_always"] = data["cc_always"]

        backup_path = save_client_mapping(clients)

        # Restart casehub
        import subprocess
        subprocess.run(["pm2", "restart", "casehub"], capture_output=True, timeout=30)

        return {
            "success": True,
            "message": f"Client {email} created",
            "client": {"email": email, **clients[email]},
            "backup": str(backup_path)
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.patch("/api/clients/{email:path}")
async def update_client(email: str, request: Request):
    """Update an existing client"""
    try:
        data = await request.json()
        clients = get_client_mapping()

        if email not in clients:
            raise HTTPException(status_code=404, detail=f"Client {email} not found")

        # Update fields
        for field in ["name", "paralegal", "case", "case_type", "timezone", "language", "phone", "cc_always"]:
            if field in data:
                clients[email][field] = data[field]

        backup_path = save_client_mapping(clients)

        # Restart casehub
        import subprocess
        subprocess.run(["pm2", "restart", "casehub"], capture_output=True, timeout=30)

        return {
            "success": True,
            "message": f"Client {email} updated",
            "client": {"email": email, **clients[email]},
            "backup": str(backup_path)
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.delete("/api/clients/{email:path}")
async def delete_client(email: str):
    """Remove a client from CLIENT_MAPPING"""
    try:
        clients = get_client_mapping()

        if email not in clients:
            raise HTTPException(status_code=404, detail=f"Client {email} not found")

        deleted = clients.pop(email)
        backup_path = save_client_mapping(clients)

        # Restart casehub
        import subprocess
        subprocess.run(["pm2", "restart", "casehub"], capture_output=True, timeout=30)

        return {
            "success": True,
            "message": f"Client {email} deleted",
            "deleted_client": {"email": email, **deleted},
            "backup": str(backup_path)
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


# === WhatsApp Bot Configuration ===

@app.get("/api/whatsapp/config")
async def get_whatsapp_config():
    """Get WhatsApp bot configuration"""
    try:
        file_path = Path(os.getenv("APP_BASE_PATH", "/opt/casehub") + "/whatsapp-bot/server.js")
        content = file_path.read_text(encoding="utf-8")

        config = {}

        # Extract globalBotEnabled
        match = re.search(r"globalBotEnabled\s*=\s*(true|false)", content)
        if match:
            config["globalBotEnabled"] = match.group(1) == "true"

        # Extract work hours
        match = re.search(r"workHoursStart\s*=\s*(\d+)", content)
        if match:
            config["workHoursStart"] = int(match.group(1))

        match = re.search(r"workHoursEnd\s*=\s*(\d+)", content)
        if match:
            config["workHoursEnd"] = int(match.group(1))

        # Extract business hours enabled
        match = re.search(r"businessHoursEnabled\s*=\s*(true|false)", content)
        if match:
            config["businessHoursEnabled"] = match.group(1) == "true"

        return {"success": True, "config": config}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/whatsapp/config")
async def update_whatsapp_config(request: Request):
    """Update WhatsApp bot configuration"""
    try:
        data = await request.json()
        file_path = Path(os.getenv("APP_BASE_PATH", "/opt/casehub") + "/whatsapp-bot/server.js")
        content = file_path.read_text(encoding="utf-8")

        # Backup
        ensure_backup_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = Path(BACKUP_DIR) / f"server_{timestamp}.js"
        shutil.copy2(file_path, backup_path)

        # Update values
        if "globalBotEnabled" in data:
            val = "true" if data["globalBotEnabled"] else "false"
            content = re.sub(r"globalBotEnabled\s*=\s*(true|false)", f"globalBotEnabled = {val}", content)

        if "workHoursStart" in data:
            content = re.sub(r"workHoursStart\s*=\s*\d+", f"workHoursStart = {data['workHoursStart']}", content)

        if "workHoursEnd" in data:
            content = re.sub(r"workHoursEnd\s*=\s*\d+", f"workHoursEnd = {data['workHoursEnd']}", content)

        if "businessHoursEnabled" in data:
            val = "true" if data["businessHoursEnabled"] else "false"
            content = re.sub(r"businessHoursEnabled\s*=\s*(true|false)", f"businessHoursEnabled = {val}", content)

        file_path.write_text(content, encoding="utf-8")

        # Restart bot
        import subprocess
        subprocess.run(["pm2", "restart", "whatsapp-bot"], capture_output=True, timeout=30)

        return {
            "success": True,
            "message": "WhatsApp config updated",
            "backup": str(backup_path),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/whatsapp/templates")
async def get_whatsapp_templates():
    """Get WhatsApp message templates"""
    try:
        file_path = Path(os.getenv("APP_BASE_PATH", "/opt/casehub") + "/whatsapp-bot/server.js")
        content = file_path.read_text(encoding="utf-8")

        templates = {}

        # Find message templates in the file
        template_pattern = r"(template_\w+|MESSAGE_\w+)\s*[:=]\s*['\"`]([^'\"`]+)['\"`]"
        matches = re.findall(template_pattern, content, re.IGNORECASE)

        for name, value in matches:
            templates[name] = value

        return {"success": True, "templates": templates}
    except Exception as e:
        return {"success": False, "error": str(e)}


# === Email Processor Control ===

@app.get("/api/email/status")
async def get_email_processor_status():
    """Get email processor status"""
    try:
        import subprocess

        # Check casehub PM2 status
        result = subprocess.run(
            ["pm2", "jlist"],
            capture_output=True,
            text=True,
            timeout=10
        )

        casehub_status = "unknown"
        if result.returncode == 0:
            processes = json.loads(result.stdout)
            for proc in processes:
                if proc.get("name") == "casehub":
                    casehub_status = proc.get("pm2_env", {}).get("status", "unknown")
                    break

        # Check last email processing log
        log_path = Path("/root/.pm2/logs/casehub-out.log")
        last_logs = []
        if log_path.exists():
            result = subprocess.run(
                ["tail", "-50", str(log_path)],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "email" in line.lower() or "processed" in line.lower():
                        last_logs.append(line)
                last_logs = last_logs[-10:]

        return {
            "success": True,
            "casehub_status": casehub_status,
            "email_logs": last_logs,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/email/run")
async def run_email_processor(request: Request):
    """Manually trigger email processing"""
    try:
        import subprocess

        data = await request.json() if request.headers.get("content-type") == "application/json" else {}
        dry_run = data.get("dry_run", False)
        since_hours = data.get("since_hours", 24)

        cmd = ["python3", os.getenv("APP_BASE_PATH", "/opt/casehub") + "/casehub/email_processor.py", "--check-clients", "--verbose"]
        if dry_run:
            cmd.append("--dry-run")
        if since_hours:
            cmd.extend(["--since-hours", str(since_hours)])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=os.getenv("APP_BASE_PATH", "/opt/casehub") + "/casehub"
        )

        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "errors": result.stderr,
            "dry_run": dry_run,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/email/keywords")
async def get_expansion_keywords():
    """Get EXPANSION_KEYWORDS from email_processor.py"""
    try:
        file_path = Path(CONFIG_FILES["email_processor"]["path"])
        content = file_path.read_text(encoding="utf-8")

        pattern = r"EXPANSION_KEYWORDS\s*=\s*(\[[\s\S]*?\])"
        match = re.search(pattern, content)

        if match:
            import ast
            keywords = ast.literal_eval(match.group(1))
            return {"success": True, "keywords": keywords}

        return {"success": True, "keywords": []}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/email/keywords")
async def update_expansion_keywords(request: Request):
    """Update EXPANSION_KEYWORDS"""
    try:
        data = await request.json()
        keywords = data.get("keywords", [])

        file_path = Path(CONFIG_FILES["email_processor"]["path"])
        content = file_path.read_text(encoding="utf-8")

        # Backup
        ensure_backup_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = Path(BACKUP_DIR) / f"email_processor_{timestamp}_keywords.py"
        shutil.copy2(file_path, backup_path)

        # Format and replace
        formatted = "EXPANSION_KEYWORDS = " + repr(keywords)
        content = re.sub(r"EXPANSION_KEYWORDS\s*=\s*\[[\s\S]*?\]", formatted, content)

        file_path.write_text(content, encoding="utf-8")

        # Restart casehub
        import subprocess
        subprocess.run(["pm2", "restart", "casehub"], capture_output=True, timeout=30)

        return {
            "success": True,
            "keywords": keywords,
            "backup": str(backup_path),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# === Backups Management ===

@app.get("/api/backups")
async def list_backups():
    """List all configuration backups"""
    try:
        ensure_backup_dir()
        backup_path = Path(BACKUP_DIR)

        backups = []
        for f in sorted(backup_path.iterdir(), reverse=True):
            if f.is_file():
                backups.append({
                    "name": f.name,
                    "path": str(f),
                    "size": f.stat().st_size,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                })

        return {"success": True, "backups": backups, "count": len(backups)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/backups/create")
async def create_full_backup(request: Request):
    """Create backup of multiple config files"""
    try:
        data = await request.json() if request.headers.get("content-type") == "application/json" else {}
        file_ids = data.get("file_ids", list(CONFIG_FILES.keys()))

        ensure_backup_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backups_created = []

        for file_id in file_ids:
            if file_id in CONFIG_FILES:
                file_path = Path(CONFIG_FILES[file_id]["path"])
                if file_path.exists():
                    backup_name = f"{file_id}_{timestamp}{file_path.suffix}"
                    backup_dest = Path(BACKUP_DIR) / backup_name
                    shutil.copy2(file_path, backup_dest)
                    backups_created.append(backup_name)

        return {
            "success": True,
            "timestamp": timestamp,
            "backups_created": backups_created,
            "count": len(backups_created)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/backups/restore/{backup_name}")
async def restore_backup(backup_name: str):
    """Restore a configuration from backup"""
    try:
        backup_path = Path(BACKUP_DIR) / backup_name

        if not backup_path.exists():
            raise HTTPException(status_code=404, detail=f"Backup {backup_name} not found")

        # Determine which config file this belongs to
        target_file = None
        target_service = None

        for file_id, info in CONFIG_FILES.items():
            if backup_name.startswith(file_id):
                target_file = info["path"]
                target_service = info["service"]
                break

        if not target_file:
            raise HTTPException(status_code=400, detail="Could not determine target file for backup")

        # Create backup of current file before restore
        current_path = Path(target_file)
        if current_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            pre_restore = Path(BACKUP_DIR) / f"pre_restore_{timestamp}_{current_path.name}"
            shutil.copy2(current_path, pre_restore)

        # Restore
        shutil.copy2(backup_path, current_path)

        # Restart service
        import subprocess
        if target_service:
            subprocess.run(["pm2", "restart", target_service], capture_output=True, timeout=30)

        return {
            "success": True,
            "restored": backup_name,
            "target": target_file,
            "service_restarted": target_service,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.delete("/api/backups/{backup_name}")
async def delete_backup(backup_name: str):
    """Delete a backup file"""
    try:
        backup_path = Path(BACKUP_DIR) / backup_name

        if not backup_path.exists():
            raise HTTPException(status_code=404, detail=f"Backup {backup_name} not found")

        backup_path.unlink()

        return {
            "success": True,
            "deleted": backup_name,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


# === Environment Variables ===

ENV_FILES = {
    "casehub": os.getenv("APP_BASE_PATH", "/opt/casehub") + "/casehub/.env",
    "ilc-tools": os.getenv("APP_BASE_PATH", "/opt/casehub") + "/ilc-tools/.env",
    "vps-monitor": os.getenv("APP_BASE_PATH", "/opt/casehub") + "/vps-monitor/.env",
    "whatsapp-bot": os.getenv("APP_BASE_PATH", "/opt/casehub") + "/whatsapp-bot/.env",
    "client-intake": os.getenv("APP_BASE_PATH", "/opt/casehub") + "/client-intake/.env"
}

SENSITIVE_KEYS = ["PASSWORD", "SECRET", "TOKEN", "KEY", "CREDENTIAL", "AUTH"]

def is_sensitive(key: str) -> bool:
    """Check if a key contains sensitive information"""
    return any(s in key.upper() for s in SENSITIVE_KEYS)


@app.get("/api/env/{service}")
async def get_env_variables(service: str):
    """Get environment variables for a service (hides sensitive values)"""
    if service not in ENV_FILES:
        raise HTTPException(status_code=404, detail=f"Service {service} not found")

    try:
        env_path = Path(ENV_FILES[service])
        if not env_path.exists():
            return {"success": True, "variables": {}, "message": "No .env file found"}

        content = env_path.read_text(encoding="utf-8")
        variables = {}

        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")

                if is_sensitive(key):
                    variables[key] = "********" if value else ""
                else:
                    variables[key] = value

        return {"success": True, "service": service, "variables": variables}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/env/{service}")
async def update_env_variable(service: str, request: Request):
    """Update a single environment variable"""
    if service not in ENV_FILES:
        raise HTTPException(status_code=404, detail=f"Service {service} not found")

    try:
        data = await request.json()
        key = data.get("key")
        value = data.get("value")

        if not key:
            raise HTTPException(status_code=400, detail="Key is required")

        env_path = Path(ENV_FILES[service])

        # Backup
        ensure_backup_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if env_path.exists():
            backup_path = Path(BACKUP_DIR) / f"{service}_env_{timestamp}"
            shutil.copy2(env_path, backup_path)

        # Read current content
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
        else:
            content = ""

        # Update or add variable
        lines = content.splitlines()
        found = False
        new_lines = []

        for line in lines:
            if line.strip().startswith(f"{key}="):
                new_lines.append(f'{key}="{value}"')
                found = True
            else:
                new_lines.append(line)

        if not found:
            new_lines.append(f'{key}="{value}"')

        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

        # Restart service
        import subprocess
        subprocess.run(["pm2", "restart", service], capture_output=True, timeout=30)

        return {
            "success": True,
            "service": service,
            "key": key,
            "updated": True,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/env/{service}/test")
async def test_env_connections(service: str):
    """Test connections using environment variables"""
    if service not in ENV_FILES:
        raise HTTPException(status_code=404, detail=f"Service {service} not found")

    try:
        results = {}

        env_path = Path(ENV_FILES[service])
        if not env_path.exists():
            return {"success": True, "tests": {}, "message": "No .env file found"}

        # Load env vars
        from dotenv import dotenv_values
        env_vars = dotenv_values(env_path)

        # Test database connections
        if "DATABASE_URL" in env_vars:
            try:
                import subprocess
                db_url = env_vars["DATABASE_URL"]
                # Simple connection test
                if "postgresql" in db_url:
                    result = subprocess.run(
                        ["pg_isready", "-d", db_url],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    results["database"] = {"status": "connected" if result.returncode == 0 else "failed"}
            except:
                results["database"] = {"status": "error"}

        # Test SMTP if configured
        if "SMTP_HOST" in env_vars:
            try:
                import socket
                host = env_vars.get("SMTP_HOST")
                port = int(env_vars.get("SMTP_PORT", 587))
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex((host, port))
                sock.close()
                results["smtp"] = {"status": "connected" if result == 0 else "failed", "host": host, "port": port}
            except:
                results["smtp"] = {"status": "error"}

        return {"success": True, "service": service, "tests": results}
    except Exception as e:
        return {"success": False, "error": str(e)}


# === Notion Configuration ===

@app.get("/api/notion/config")
async def get_notion_config():
    """Get Notion configuration from notion_notifier.py"""
    try:
        file_path = Path(CONFIG_FILES["notion_notifier"]["path"])
        content = file_path.read_text(encoding="utf-8")

        config = {}

        # Extract TEAM_IDS
        match = re.search(r"team_ids[\"']\s*:\s*(\{[^}]+\})", content)
        if match:
            try:
                import ast
                config["team_ids"] = ast.literal_eval(match.group(1))
            except:
                pass

        # Extract TEAM_EMAILS
        match = re.search(r"team_emails[\"']\s*:\s*(\{[^}]+\})", content)
        if match:
            try:
                import ast
                config["team_emails"] = ast.literal_eval(match.group(1))
            except:
                pass

        # Extract DATABASE_IDS
        match = re.search(r"database_ids[\"']\s*:\s*(\{[^}]+\})", content)
        if match:
            try:
                import ast
                config["database_ids"] = ast.literal_eval(match.group(1))
            except:
                pass

        return {"success": True, "config": config}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/notion/test")
async def test_notion_connection():
    """Test Notion API connection"""
    try:
        import subprocess

        # Load token from casehub .env
        from dotenv import dotenv_values
        env = dotenv_values(os.getenv("APP_BASE_PATH", "/opt/casehub") + "/casehub/.env")
        token = env.get("NOTION_TOKEN") or env.get("NOTION_API_KEY")

        if not token:
            return {"success": False, "error": "No Notion token found"}

        # Test API call
        result = subprocess.run(
            ["curl", "-s", "-H", f"Authorization: Bearer {token}",
             "-H", "Notion-Version: 2022-06-28",
             "https://api.notion.com/v1/users/me"],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            response = json.loads(result.stdout)
            if "object" in response and response["object"] == "user":
                return {"success": True, "status": "connected", "user": response.get("name", "Unknown")}
            else:
                return {"success": False, "status": "invalid_response", "response": response}

        return {"success": False, "status": "failed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# === Alert Hub / Notifications ===

@app.get("/api/alerts/config")
async def get_alerts_config():
    """Get alert thresholds configuration"""
    try:
        # Default thresholds
        config = {
            "cpu_warning": 80,
            "cpu_critical": 95,
            "ram_warning": 85,
            "ram_critical": 95,
            "disk_warning": 80,
            "disk_critical": 90,
            "whatsapp_enabled": True,
            "email_enabled": True,
            "admin_phone": "5532991513405"
        }

        # Try to load from config file if exists
        config_path = Path(os.getenv("APP_BASE_PATH", "/opt/casehub") + "/vps-monitor/alerts_config.json")
        if config_path.exists():
            saved_config = json.loads(config_path.read_text())
            config.update(saved_config)

        return {"success": True, "config": config}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/alerts/config")
async def update_alerts_config(request: Request):
    """Update alert thresholds"""
    try:
        data = await request.json()

        config_path = Path(os.getenv("APP_BASE_PATH", "/opt/casehub") + "/vps-monitor/alerts_config.json")

        # Load existing or default
        if config_path.exists():
            config = json.loads(config_path.read_text())
        else:
            config = {}

        # Update values
        for key in ["cpu_warning", "cpu_critical", "ram_warning", "ram_critical",
                    "disk_warning", "disk_critical", "whatsapp_enabled", "email_enabled", "admin_phone"]:
            if key in data:
                config[key] = data[key]

        # Save
        config_path.write_text(json.dumps(config, indent=2))

        return {
            "success": True,
            "config": config,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# === Dashboard Summary for n8n ===

@app.get("/api/master/summary")
async def get_master_summary():
    """Complete system summary for VPS Master Control"""
    try:
        summary = {
            "timestamp": datetime.now().isoformat(),
            "system": system_collector.collect(),
            "pm2": pm2_collector.collect(),
            "clients_count": len(get_client_mapping()),
            "config_files": len(CONFIG_FILES),
            "services": list(ENV_FILES.keys())
        }

        # Get backups count
        backup_path = Path(BACKUP_DIR)
        if backup_path.exists():
            summary["backups_count"] = len(list(backup_path.iterdir()))
        else:
            summary["backups_count"] = 0

        return {"success": True, "summary": summary}
    except Exception as e:
        return {"success": False, "error": str(e)}


# === Security Status ===

@app.get("/api/security")
async def get_security_status():
    """Get complete security status"""
    return security_collector.collect()

@app.get("/api/security/score")
async def get_security_score():
    """Get security score summary"""
    return security_collector.get_score()





# === CaseHub Leads CRM Summary ===

@app.get("/api/leads/summary")
async def get_leads_summary():
    """Read CaseHub leads CRM data and return summary for dashboard."""
    import json
    from collections import Counter

    leads_file = Path(os.getenv("APP_BASE_PATH", "/opt/casehub") + "/casehub/data/leads_crm.json")
    try:
        data = json.loads(leads_file.read_text())
        leads_dict = data.get("leads", {})
        if isinstance(leads_dict, dict):
            leads = list(leads_dict.values())
        else:
            leads = leads_dict if isinstance(leads_dict, list) else []

        total = len(leads)

        # Pipeline stage counts
        stages = Counter()
        statuses = Counter()
        sources = Counter()
        needs_attention = []

        for lead in leads:
            if not isinstance(lead, dict):
                continue
            stage = lead.get("pipeline_stage") or lead.get("stage") or "new"
            status = lead.get("lead_status") or lead.get("status") or "new"
            source = lead.get("source") or "unknown"

            stages[stage] += 1
            statuses[status] += 1
            sources[source] += 1

            # Lead needs attention if:
            # - conversation_state is "waiting_reply" or "needs_followup"
            # - status is "new" and no recent activity
            conv_state = lead.get("conversation_state", "")
            updated = lead.get("updated_at", "")
            if conv_state in ("waiting_reply", "needs_followup", "awaiting_human"):
                needs_attention.append({
                    "name": lead.get("display_name") or lead.get("name") or "?",
                    "phone": lead.get("phone", ""),
                    "status": status,
                    "stage": stage,
                    "source": source,
                    "updated_at": updated,
                    "conversation_state": conv_state,
                })

        # Sort needs_attention by updated_at (oldest first = most urgent)
        needs_attention.sort(key=lambda x: x.get("updated_at", ""))

        # Recent leads (last 5 created)
        all_leads_sorted = sorted(
            [l for l in leads if isinstance(l, dict)],
            key=lambda x: x.get("created_at", ""),
            reverse=True
        )
        recent = []
        for l in all_leads_sorted[:5]:
            recent.append({
                "name": l.get("display_name") or l.get("name") or "?",
                "source": l.get("source", ""),
                "created_at": l.get("created_at", ""),
                "status": l.get("lead_status") or l.get("status", ""),
            })

        return {
            "success": True,
            "total": total,
            "pipeline": dict(stages.most_common()),
            "statuses": dict(statuses.most_common()),
            "sources": dict(sources.most_common()),
            "needs_attention": needs_attention[:10],
            "needs_attention_count": len(needs_attention),
            "recent": recent,
            "last_updated": data.get("last_updated", ""),
            "last_moskit_sync": data.get("last_moskit_sync", ""),
            "timestamp": datetime.now().isoformat()
        }
    except FileNotFoundError:
        return {"success": False, "error": "Leads CRM file not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# === Sentinela Auto-Healing Proxy ===

_sentinela_cache = {"data": None, "ts": 0}

@app.get("/api/sentinela/{path:path}")
async def proxy_sentinela(path: str):
    """Proxy requests to Sentinela API on port 8015 with 15s cache."""
    import time
    import httpx

    cache_key = path
    now = time.time()

    # Simple cache for status endpoint
    if path == "status" and _sentinela_cache["data"] and (now - _sentinela_cache["ts"]) < 15:
        return JSONResponse(content=_sentinela_cache["data"])

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"http://127.0.0.1:8015/{path}")
            data = resp.json()
            if path == "status":
                _sentinela_cache["data"] = data
                _sentinela_cache["ts"] = now
            return JSONResponse(content=data, status_code=resp.status_code)
    except Exception as e:
        return JSONResponse(
            content={"error": "Sentinela offline", "detail": str(e)},
            status_code=503
        )



# === Maestro WhatsApp Admin Proxy ===

_maestro_cache = {"data": None, "ts": 0}

@app.get("/api/maestro-tab/status")
async def proxy_maestro_status():
    """Proxy Maestro status from WhatsApp bot on port 3001 with 15s cache."""
    import time
    import httpx

    now = time.time()
    if _maestro_cache["data"] and (now - _maestro_cache["ts"]) < 15:
        return JSONResponse(content=_maestro_cache["data"])

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://127.0.0.1:3001/api/maestro/status")
            data = resp.json()
            _maestro_cache["data"] = data
            _maestro_cache["ts"] = now
            return JSONResponse(content=data, status_code=resp.status_code)
    except Exception as e:
        return JSONResponse(
            content={"error": "Maestro offline", "detail": str(e)},
            status_code=503
        )


@app.get("/api/maestro-tab/audit")
async def get_maestro_audit(limit: int = 30):
    """Read recent entries from Maestro audit log."""
    import os
    import re

    entries = []

    # v4 audit log (plain text format)
    v4_path = os.getenv("APP_BASE_PATH", "/opt/casehub") + "/whatsapp-bot/backups/maestro/audit.log"
    if os.path.exists(v4_path):
        try:
            with open(v4_path, "r") as f:
                lines = f.readlines()
            for line in lines[-(limit * 2):]:
                line = line.strip()
                if not line:
                    continue
                match = re.match(
                    r'\[([^\]]+)\]\s*\[([^\]]+)\]\s*(\w+):\s*(.*)',
                    line
                )
                if match:
                    entries.append({
                        "timestamp": match.group(1),
                        "phone": match.group(2),
                        "type": match.group(3),
                        "details": match.group(4)
                    })
        except Exception:
            pass

    # Fallback: JSONL audit file
    jsonl_path = "/opt/maestro/logs/audit.jsonl"
    if os.path.exists(jsonl_path) and not entries:
        try:
            import json as _json
            with open(jsonl_path, "r") as f:
                lines = f.readlines()
            for line in lines[-limit:]:
                line = line.strip()
                if line:
                    try:
                        entry = _json.loads(line)
                        entries.append(entry)
                    except _json.JSONDecodeError:
                        pass
        except Exception:
            pass

    entries.reverse()
    return {
        "success": True,
        "entries": entries[:limit],
        "count": len(entries)
    }

# === Startup/Shutdown ===

@app.on_event("startup")
async def startup():
    """Start shared refresh tasks for SSE streams."""
    global STREAM_TASK, ACTIVITY_TASK
    if STREAM_TASK is None or STREAM_TASK.done():
        STREAM_TASK = asyncio.create_task(_refresh_stream_snapshot())
    if ACTIVITY_TASK is None or ACTIVITY_TASK.done():
        ACTIVITY_TASK = asyncio.create_task(_refresh_activity_snapshot())


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown"""
    global STREAM_TASK, ACTIVITY_TASK
    tasks = [task for task in (STREAM_TASK, ACTIVITY_TASK) if task and not task.done()]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    STREAM_TASK = None
    ACTIVITY_TASK = None
    await services_collector.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8010)
