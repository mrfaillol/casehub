"""
CaseHub - Task Routes
Includes both local database tasks and Notion-synced tasks
"""
from core.form_utils import form_int, form_float
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from core.template_config import templates, PREFIX
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import bindparam, or_, text
from typing import Optional, List
from datetime import datetime, date
import json
import re

from models import get_db, Client, Case, User, Task, Reminder, TaskComment
from auth import get_current_user
from models.tenant import tenant_query
from services.notion_tasks import notion_tasks_service, TASK_DATABASES
from i18n import get_translations

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/tasks", tags=["tasks"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py
# # templates.env.auto_reload = True  # Configured in template_config.py  # Configured in template_config.py
# # templates.env.cache = {}  # Disable template cache  # Configured in template_config.py  # Configured in template_config.py
# # templates.env.globals["PREFIX"] = PREFIX  # Configured in template_config.py  # Configured in template_config.py
templates.env.globals["now"] = lambda: date.today()

KANBAN_TOTAL_LIMIT = 500
TASK_CALENDAR_EVENT_LIMIT = 300
VALID_KANBAN_STATUSES = {"pending", "in_progress", "blocked", "completed"}
TASK_CALENDAR_PRIORITIES = {"urgent", "high", "medium", "low"}
KANBAN_STATUS_ALIASES = {
    "todo": "pending",
    "to_do": "pending",
    "a_fazer": "pending",
    "pendente": "pending",
    "pending": "pending",
    "doing": "in_progress",
    "em_andamento": "in_progress",
    "in_progress": "in_progress",
    "bloqueada": "blocked",
    "bloqueado": "blocked",
    "blocked": "blocked",
    "done": "completed",
    "concluida": "completed",
    "concluido": "completed",
    "completed": "completed",
}


def _canonical_kanban_status(value):
    if value is None:
        return None
    normalized = str(value).strip()
    return KANBAN_STATUS_ALIASES.get(normalized, normalized)


def _status_for_kanban_column(slug, is_done=False):
    canonical = _canonical_kanban_status(slug)
    if canonical in VALID_KANBAN_STATUSES:
        return canonical
    return "completed" if is_done else "pending"


def _slugify_column_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
    return slug[:60] or "lista"


def _normalize_column_visibility(value: str) -> str:
    return "private" if str(value or "").strip().lower() in {"private", "privada", "me"} else "shared"


def _can_manage_shared_kanban(user) -> bool:
    return str(getattr(user, "role", "") or getattr(user, "user_type", "")).lower() in {
        "admin", "owner", "manager", "gestor"
    }


def _ensure_kanban_schema(db):
    """Keep Kanban custom lists compatible with older Basic databases."""
    bind = db.get_bind()
    dialect = bind.dialect.name if bind is not None else "sqlite"
    false_default = "FALSE" if dialect == "postgresql" else "0"
    additions = [
        ("kanban_columns", "visibility", "VARCHAR(20) DEFAULT 'shared'"),
        ("kanban_columns", "owner_user_id", "INTEGER"),
        ("kanban_columns", "is_archived", f"BOOLEAN DEFAULT {false_default}"),
    ]
    for table, column, definition in additions:
        try:
            if dialect == "postgresql":
                exists = db.execute(
                    text("""
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = :table AND column_name = :column
                    """),
                    {"table": table, "column": column},
                ).first()
            else:
                exists = any(row[1] == column for row in db.execute(text(f"PRAGMA table_info({table})")).fetchall())
            if not exists:
                db.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
        except Exception:
            db.rollback()

    db.execute(text("""
        CREATE TABLE IF NOT EXISTS task_kanban_placements (
            id INTEGER PRIMARY KEY,
            org_id INTEGER NOT NULL,
            task_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            column_id INTEGER NOT NULL,
            position INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, task_id)
        )
    """))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_task_kanban_placements_column "
        "ON task_kanban_placements (org_id, user_id, column_id, position)"
    ))
    db.commit()


def _visible_column_where_sql() -> str:
    return (
        "org_id = :org_id AND COALESCE(is_archived, FALSE) = FALSE "
        "AND (COALESCE(visibility, 'shared') = 'shared' "
        "OR (visibility = 'private' AND owner_user_id = :user_id))"
    )


def _upsert_private_placement(db, *, org_id: int, user_id: int, task_id: int, column_id: int, position: int = 0):
    existing = db.execute(
        text("SELECT id FROM task_kanban_placements WHERE user_id = :user_id AND task_id = :task_id"),
        {"user_id": user_id, "task_id": task_id},
    ).fetchone()
    if existing:
        db.execute(
            text("""
                UPDATE task_kanban_placements
                SET org_id = :org_id, column_id = :column_id, position = :position,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """),
            {"id": existing.id, "org_id": org_id, "column_id": column_id, "position": position},
        )
    else:
        db.execute(
            text("""
                INSERT INTO task_kanban_placements
                    (org_id, task_id, user_id, column_id, position)
                VALUES (:org_id, :task_id, :user_id, :column_id, :position)
            """),
            {
                "org_id": org_id,
                "task_id": task_id,
                "user_id": user_id,
                "column_id": column_id,
                "position": position,
            },
        )


def _clear_private_placement(db, *, user_id: int, task_id: int):
    db.execute(
        text("DELETE FROM task_kanban_placements WHERE user_id = :user_id AND task_id = :task_id"),
        {"user_id": user_id, "task_id": task_id},
    )

def get_context(request: Request, db: Session, **kwargs):
    lang = request.cookies.get("lang", "pt-BR")
    t = get_translations(lang)
    user = get_current_user(request, db)
    return {"request": request, "PREFIX": PREFIX, "lang": lang, "t": t, "user": user, **kwargs}


def _is_lite_product(request: Request) -> bool:
    return getattr(request.app.state, "product", "lite") == "lite"


def _redirect_lite_to_kanban(request: Request):
    if _is_lite_product(request):
        return RedirectResponse(url=f"{PREFIX}/tasks/kanban", status_code=302)
    return None


def _block_lite_notion_json(request: Request):
    if _is_lite_product(request):
        return JSONResponse({"error": "Notion tasks are unavailable for this product"}, status_code=403)
    return None


def _assigned_user_ids_for_tasks(tasks):
    return sorted({t.assigned_to for t in tasks if t.assigned_to})

def parse_date(date_str: str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


# ==========================================
# DEFAULT REDIRECT - Notion Tasks is the default
# ==========================================

def _json_script_safe(obj):
    # escapa < -> \u003c: impede </script> breakout em JSON-in-<script> (XSS). JSON segue valido.
    return json.dumps(obj).replace(chr(60), chr(92) + "u003c")


@router.get("", response_class=HTMLResponse)
async def tasks_redirect(request: Request, db: Session = Depends(get_db)):
    """Redirect /tasks to kanban (Lite) or notion (Immigration)"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    if _is_lite_product(request):
        return RedirectResponse(url=f"{PREFIX}/tasks/kanban", status_code=302)
    return RedirectResponse(url=f"{PREFIX}/tasks/notion", status_code=302)


# ==========================================
# LOCAL TASKS - Secondary tab
# ==========================================

@router.get("/local", response_class=HTMLResponse)
async def list_tasks(
    request: Request,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    client_id: Optional[int] = None,
    case_id: Optional[int] = None,
    show_completed: bool = False,
    page: int = 1,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    query = tenant_query(db, Task, request.state.org_id).filter(
        Task.parent_task_id.is_(None)  # Only top-level tasks
    )

    if not show_completed:
        query = query.filter(Task.status != "completed")

    if status:
        query = query.filter(Task.status == status)
    if priority:
        query = query.filter(Task.priority == priority)
    if client_id:
        query = query.filter(Task.client_id == client_id)
    if case_id:
        query = query.filter(Task.case_id == case_id)

    total = query.count()
    per_page = 20
    tasks = query.order_by(Task.due_date.asc().nullslast(), Task.priority.desc()).offset((page-1)*per_page).limit(per_page).all()

    # Get overdue count
    overdue_count = tenant_query(db, Task, request.state.org_id).filter(
        Task.status != "completed",
        Task.due_date < date.today()
    ).count()

    # Get today's count
    today_count = tenant_query(db, Task, request.state.org_id).filter(
        Task.status != "completed",
        Task.due_date == date.today()
    ).count()

    return templates.TemplateResponse("app/tasks/list.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "tasks": tasks,
        "total": total,
        "page": page,
        "per_page": per_page,
        "status": status or "",
        "priority": priority or "",
        "show_completed": show_completed,
        "overdue_count": overdue_count,
        "today_count": today_count,
        "today": date.today()
    })


@router.get("/new", response_class=HTMLResponse)
async def new_task(
    request: Request,
    client_id: Optional[int] = None,
    case_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    clients = tenant_query(db, Client, request.state.org_id).order_by(Client.first_name).all()
    cases = tenant_query(db, Case, request.state.org_id).order_by(Case.created_at.desc()).all()
    users = tenant_query(db, User, request.state.org_id).filter(User.enabled == True).all()

    return templates.TemplateResponse("app/tasks/form.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "task": None,
        "clients": clients,
        "cases": cases,
        "users": users,
        "selected_client_id": client_id,
        "selected_case_id": case_id,
        "action": "Create"
    })


@router.post("/new")
async def create_task(
    request: Request,
    title: str = Form(...),
    description: str = Form(None),
    task_type: str = Form(None),
    status: str = Form("pending"),
    priority: str = Form("medium"),
    client_id: str = Form(None),
    case_id: str = Form(None),
    assigned_to: str = Form(None),
    due_date: str = Form(None),
    reminder_date: str = Form(None),
    tags: str = Form(None),
    estimated_hours: str = Form(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Convert form strings to proper types (HTML forms send empty strings, not None)
    client_id = form_int(client_id)
    case_id = form_int(case_id)
    assigned_to = form_int(assigned_to)
    estimated_hours = form_float(estimated_hours)

    task = Task(
        title=title,
        description=description,
        task_type=task_type,
        status=status,
        priority=priority,
        client_id=client_id,
        case_id=case_id,
        assigned_to=assigned_to,
        due_date=parse_date(due_date),
        reminder_date=parse_date(reminder_date),
        tags=tags.strip() if tags else None,
        estimated_hours=estimated_hours,
        org_id=request.state.org_id
    )
    db.add(task)
    db.flush()  # Get task.id

    # Process subtasks from form
    
    form_data = await request.form()
    subtask_titles = form_data.getlist("subtask_title[]")
    subtask_done = form_data.getlist("subtask_done[]")

    for i, stitle in enumerate(subtask_titles):
        stitle = stitle.strip()
        if not stitle:
            continue
        is_done = str(i) in subtask_done
        sub = Task(
            title=stitle,
            status="completed" if is_done else "pending",
            priority="medium",
            parent_task_id=task.id,
            org_id=request.state.org_id,
            completed_at=datetime.now() if is_done else None
        )
        db.add(sub)

    db.commit()

    return RedirectResponse(url=f"{PREFIX}/tasks", status_code=302)


# ==========================================
# NOTION TASKS ENDPOINTS (must be before /{task_id})
# ==========================================

@router.get("/notion", response_class=HTMLResponse)
async def notion_tasks(
    request: Request,
    source: Optional[str] = None,
    status: Optional[str] = None,
    visa_type: Optional[str] = None,
    client: Optional[str] = None,
    # Block Notion tasks for Lite product
    priority: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """View tasks from Notion databases with tabs for Juliana/Ana"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    lite_redirect = _redirect_lite_to_kanban(request)
    if lite_redirect:
        return lite_redirect

    # Get tasks from Notion
    try:
        if source and source in TASK_DATABASES:
            all_tasks = notion_tasks_service.get_tasks_from_database(source)
        else:
            all_tasks = notion_tasks_service.get_all_tasks()

        # Apply filters
        filtered_tasks = all_tasks

        if status:
            filtered_tasks = [t for t in filtered_tasks if t.get("status") == status]
        if visa_type:
            filtered_tasks = [t for t in filtered_tasks if t.get("visa_type") == visa_type]
        if client:
            filtered_tasks = [t for t in filtered_tasks if client in t.get("client_names", [])]
        if priority:
            filtered_tasks = [t for t in filtered_tasks if t.get("priority") == priority]

        # Get unique values for filters
        all_statuses = notion_tasks_service.get_unique_values("status")
        all_visa_types = notion_tasks_service.get_unique_values("visa_type")
        all_clients = notion_tasks_service.get_unique_values("client_names")
        all_priorities = notion_tasks_service.get_unique_values("priority")

        # Count by source
        juliana_count = len([t for t in all_tasks if t.get("source") == "juliana"])
        ana_count = len([t for t in all_tasks if t.get("source") == "ana"])

        # Overdue and today counts
        today_str = date.today().isoformat()
        overdue_count = len([t for t in filtered_tasks
                           if t.get("due_date") and t.get("due_date") < today_str
                           and t.get("status") not in ["Done", "Concluido"]])
        today_count = len([t for t in filtered_tasks
                         if t.get("due_date") == today_str])

        error_msg = None
    except Exception as e:
        filtered_tasks = []
        all_statuses = []
        all_visa_types = []
        all_clients = []
        all_priorities = []
        juliana_count = 0
        ana_count = 0
        overdue_count = 0
        today_count = 0
        error_msg = str(e)

    return templates.TemplateResponse("app/tasks/notion_list.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "tasks": filtered_tasks,
        "tasks_json": _json_script_safe([{
            "id": t.get("id", ""),
            "title": t.get("title", ""),
            "status": t.get("status", "A fazer"),
            "client_names": t.get("client_names", []),
            "visa_type": t.get("visa_type", ""),
            "priority": t.get("priority", ""),
            "due_date": t.get("due_date", ""),
            "source": t.get("source", ""),
            "notion_url": t.get("notion_url", "")
        } for t in filtered_tasks]),
        "databases": TASK_DATABASES,
        "selected_source": source or "",
        "selected_status": status or "",
        "selected_visa_type": visa_type or "",
        "selected_client": client or "",
        "selected_priority": priority or "",
        "all_statuses": all_statuses,
        "all_visa_types": all_visa_types,
        "all_clients": all_clients,
        "all_priorities": all_priorities,
        "juliana_count": juliana_count,
        "ana_count": ana_count,
        "total_count": juliana_count + ana_count,
        "overdue_count": overdue_count,
        "today_count": today_count,
        "error": error_msg
    })


@router.get("/notion/new", response_class=HTMLResponse)
async def new_notion_task_form(
    request: Request,
    source: str = "juliana",
    db: Session = Depends(get_db)
):
    """Form to create a new task in Notion"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    lite_redirect = _redirect_lite_to_kanban(request)
    if lite_redirect:
        return lite_redirect

    # Get unique values for dropdowns
    all_visa_types = notion_tasks_service.get_unique_values("visa_type")
    all_clients = notion_tasks_service.get_unique_values("client_names")
    all_priorities = notion_tasks_service.get_unique_values("priority")
    all_case_steps = notion_tasks_service.get_unique_values("case_step")

    return templates.TemplateResponse("app/tasks/notion_form.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "task": None,
        "databases": TASK_DATABASES,
        "selected_source": source,
        "all_visa_types": all_visa_types,
        "all_clients": all_clients,
        "all_priorities": all_priorities,
        "all_case_steps": all_case_steps,
        "action": "Criar"
    })


@router.post("/notion/create")
async def create_notion_task(
    request: Request,
    source: str = Form(...),
    title: str = Form(...),
    description: str = Form(None),
    client_names: str = Form(None),
    visa_type: str = Form(None),
    status: str = Form("To Do"),
    priority: str = Form(None),
    due_date: str = Form(None),
    case_step: str = Form(None),
    document_url: str = Form(None),
    db: Session = Depends(get_db)
):
    """Create a new task in Notion"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    lite_redirect = _redirect_lite_to_kanban(request)
    if lite_redirect:
        return lite_redirect

    task_data = {
        "title": title,
        "description": description,
        "client_names": [c.strip() for c in client_names.split(",")] if client_names else [],
        "visa_type": visa_type,
        "status": status,
        "priority": priority,
        "due_date": due_date if due_date else None,
        "case_step": [c.strip() for c in case_step.split(",")] if case_step else [],
        "document_url": document_url
    }

    result = notion_tasks_service.create_task(source, task_data)

    if "error" in result:
        return templates.TemplateResponse("app/tasks/notion_form.html", {
            "request": request,
            "user": user,
            "PREFIX": PREFIX,
            "task": task_data,
            "databases": TASK_DATABASES,
            "selected_source": source,
            "error": result["error"],
            "action": "Criar"
        })

    return RedirectResponse(url=f"{PREFIX}/tasks/notion?source={source}", status_code=302)


@router.post("/notion/{page_id}/status")
async def update_notion_task_status(
    request: Request,
    page_id: str,
    status: str = Form(...),
    db: Session = Depends(get_db)
):
    """Quick update task status in Notion"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    lite_response = _block_lite_notion_json(request)
    if lite_response:
        return lite_response

    result = notion_tasks_service.update_task_status(page_id, status)

    if "error" in result:
        return JSONResponse({"success": False, "error": result["error"]})

    return JSONResponse({"success": True})


@router.post("/notion/{page_id}/archive")
async def archive_notion_task(
    request: Request,
    page_id: str,
    db: Session = Depends(get_db)
):
    """Archive (delete) a task in Notion"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    lite_response = _block_lite_notion_json(request)
    if lite_response:
        return lite_response

    result = notion_tasks_service.archive_task(page_id)

    if "error" in result:
        return JSONResponse({"success": False, "error": result["error"]})

    return JSONResponse({"success": True})


# ==========================================
# NOTION TASKS API
# ==========================================

@router.get("/api/notion/tasks")
async def api_notion_tasks(
    request: Request,
    source: Optional[str] = None,
    status: Optional[str] = None,
    refresh: bool = False,
    db: Session = Depends(get_db)
):
    """API: Get tasks from Notion"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    lite_response = _block_lite_notion_json(request)
    if lite_response:
        return lite_response

    try:
        use_cache = not refresh

        if source and source in TASK_DATABASES:
            tasks = notion_tasks_service.get_tasks_from_database(source, use_cache)
        else:
            tasks = notion_tasks_service.get_all_tasks(use_cache)

        if status:
            tasks = [t for t in tasks if t.get("status") == status]

        return JSONResponse({
            "success": True,
            "tasks": tasks,
            "count": len(tasks)
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@router.get("/api/notion/databases")
async def api_notion_databases(
    request: Request,
    db: Session = Depends(get_db)
):
    """API: Get configured Notion databases"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    lite_response = _block_lite_notion_json(request)
    if lite_response:
        return lite_response

    return JSONResponse({
        "databases": TASK_DATABASES,
        "connection": notion_tasks_service.test_connection()
    })


@router.post("/api/notion/task")
async def api_create_notion_task(
    request: Request,
    db: Session = Depends(get_db)
):
    """API: Create task in Notion"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    lite_response = _block_lite_notion_json(request)
    if lite_response:
        return lite_response

    try:
        data = await request.json()
        source = data.pop("source", "juliana")
        result = notion_tasks_service.create_task(source, data)

        if "error" in result:
            return JSONResponse({"success": False, "error": result["error"]})

        return JSONResponse({"success": True, "page_id": result.get("id")})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@router.patch("/api/notion/task/{page_id}")
async def api_update_notion_task(
    request: Request,
    page_id: str,
    db: Session = Depends(get_db)
):
    """API: Update task in Notion"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    lite_response = _block_lite_notion_json(request)
    if lite_response:
        return lite_response

    try:
        data = await request.json()
        result = notion_tasks_service.update_task(page_id, data)

        if "error" in result:
            return JSONResponse({"success": False, "error": result["error"]})

        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


# ==========================================
# KANBAN VIEW
# ==========================================

@router.get("/kanban", response_class=HTMLResponse)
async def kanban_view(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    org_id = request.state.org_id

    _ensure_kanban_schema(db)
    _ensure_kanban_columns(db, org_id)

    view_mode = request.query_params.get("view", "all")
    if view_mode not in {"all", "shared", "private"}:
        view_mode = "all"

    kanban_cols = db.execute(
        text(f"""
            SELECT id, name, slug, position, color, is_done,
                   COALESCE(visibility, 'shared') AS visibility,
                   owner_user_id
            FROM kanban_columns
            WHERE {_visible_column_where_sql()}
              AND (:view_mode = 'all' OR COALESCE(visibility, 'shared') = :view_mode)
            ORDER BY
                CASE WHEN COALESCE(visibility, 'shared') = 'shared' THEN 0 ELSE 1 END,
                position ASC,
                id ASC
        """),
        {"org_id": org_id, "user_id": user.id, "view_mode": view_mode},
    ).fetchall()

    # User filter: ?user=me or ?user={id}
    user_filter = request.query_params.get("user")
    filter_user_id = None
    if user_filter == "me":
        filter_user_id = user.id
    elif user_filter and user_filter.isdigit():
        filter_user_id = int(user_filter)

    tasks_query = tenant_query(db, Task, org_id).filter(Task.parent_task_id.is_(None))
    if filter_user_id:
        tasks_query = tasks_query.filter(Task.assigned_to == filter_user_id)

    privately_placed_ids = [
        r.task_id for r in db.execute(
            text("SELECT task_id FROM task_kanban_placements WHERE org_id = :org_id AND user_id = :user_id"),
            {"org_id": org_id, "user_id": user.id},
        ).fetchall()
    ]

    column_entries = []
    column_count = max(len(kanban_cols), 1)
    per_column_limit = max(KANBAN_TOTAL_LIMIT // column_count, 1)
    initial_task_budget = KANBAN_TOTAL_LIMIT
    for col in kanban_cols:
        col_status = _status_for_kanban_column(col.slug, col.is_done)
        col_limit = min(per_column_limit, initial_task_budget)
        if col.visibility == "private":
            placement_rows = db.execute(
                text("""
                    SELECT task_id, position
                    FROM task_kanban_placements
                    WHERE org_id = :org_id AND user_id = :user_id AND column_id = :column_id
                    ORDER BY position ASC, task_id ASC
                """),
                {"org_id": org_id, "user_id": user.id, "column_id": col.id},
            ).fetchall()
            task_ids = [r.task_id for r in placement_rows]
            if task_ids:
                col_query = (
                    tasks_query
                    .filter(Task.id.in_(task_ids))
                    .order_by(Task.position.asc(), Task.due_date.asc().nullslast(), Task.id.asc())
                )
            else:
                col_query = tasks_query.filter(Task.id == -1)
        else:
            col_filter = or_(
                Task.column_id == col.id,
                (Task.column_id.is_(None)) & (Task.status == col_status),
            )
            col_query = tasks_query.filter(col_filter)
            if privately_placed_ids and view_mode != "shared":
                col_query = col_query.filter(~Task.id.in_(privately_placed_ids))
        col_query = (
            col_query
            .order_by(Task.position.asc(), Task.due_date.asc().nullslast(), Task.id.asc())
        )
        if col_limit > 0:
            col_tasks = col_query.limit(col_limit + 1).all()
            has_more = len(col_tasks) > col_limit
            col_tasks = col_tasks[:col_limit]
        else:
            col_tasks = []
            has_more = col_query.limit(1).first() is not None
        initial_task_budget -= len(col_tasks)
        column_entries.append({"column": col, "query": col_query, "tasks": col_tasks, "has_more": has_more})

    remaining_task_budget = KANBAN_TOTAL_LIMIT - sum(len(entry["tasks"]) for entry in column_entries)
    tasks_capped = False
    for entry in column_entries:
        if not entry["has_more"]:
            continue
        if remaining_task_budget <= 0:
            tasks_capped = True
            continue
        extra_tasks = entry["query"].offset(len(entry["tasks"])).limit(remaining_task_budget + 1).all()
        if len(extra_tasks) > remaining_task_budget:
            tasks_capped = True
            extra_tasks = extra_tasks[:remaining_task_budget]
        entry["tasks"].extend(extra_tasks)
        remaining_task_budget -= len(extra_tasks)

    columns_data = []
    visible_tasks = []
    for entry in column_entries:
        col = entry["column"]
        col_tasks = entry["tasks"]
        visible_tasks.extend(col_tasks)
        total_h = sum(t.estimated_hours or 0 for t in col_tasks)
        columns_data.append({
            "id": col.id,
            "name": col.name,
            "slug": col.slug,
            "status": _status_for_kanban_column(col.slug, col.is_done),
            "color": col.color,
            "is_done": col.is_done,
            "visibility": col.visibility,
            "visibility_label": "Meu quadro" if col.visibility == "private" else "Compartilhada",
            "is_private": col.visibility == "private",
            "is_owner": col.visibility != "private" or col.owner_user_id == user.id,
            "tasks": col_tasks,
            "hours": round(total_h, 1) if total_h else 0,
        })

    # Load org users for modal assignee dropdown
    org_users = tenant_query(db, User, org_id).filter(User.enabled == True).order_by(User.name).all()

    assigned_user_ids = _assigned_user_ids_for_tasks(visible_tasks)
    assigned_task_users = (
        tenant_query(db, User, org_id).filter(User.id.in_(assigned_user_ids)).order_by(User.name).all()
        if assigned_user_ids
        else []
    )

    return templates.TemplateResponse("app/tasks/kanban.html", {
        **get_context(request, db),
        "kanban_columns": columns_data,
        # Keep old format for backwards compat with template
        "columns": {c["slug"]: c["tasks"] for c in columns_data},
        "column_hours": {c["slug"]: c["hours"] for c in columns_data},
        "org_users": org_users,
        "assigned_task_users": assigned_task_users,
        "tasks_capped": tasks_capped,
        "kanban_total_limit": KANBAN_TOTAL_LIMIT,
        "filter_user_id": filter_user_id,
        "filter_user_param": user_filter or "",
        "kanban_view_mode": view_mode,
        "shared_column_count": len([c for c in columns_data if c["visibility"] == "shared"]),
        "private_column_count": len([c for c in columns_data if c["visibility"] == "private"]),
        "can_manage_shared_kanban": _can_manage_shared_kanban(user),
    })


def _ensure_kanban_columns(db, org_id):
    """Auto-create default kanban columns if org has none."""
    count = db.execute(
        text("""
            SELECT COUNT(*) FROM kanban_columns
            WHERE org_id = :org_id
              AND COALESCE(visibility, 'shared') = 'shared'
              AND COALESCE(is_archived, FALSE) = FALSE
        """),
        {"org_id": org_id},
    ).scalar() or 0
    if count > 0:
        return
    defaults = [
        ("Pendente", "pendente", 0, "#94a3b8", False),
        ("Em Andamento", "em_andamento", 1, "#3b82f6", False),
        ("Bloqueada", "blocked", 2, "#ef4444", False),
        ("Concluida", "completed", 3, "#22c55e", True),
    ]
    for name, slug, pos, color, is_done in defaults:
        db.execute(
            text("""
                INSERT INTO kanban_columns
                    (org_id, name, slug, position, color, is_done, visibility)
                VALUES (:o, :n, :s, :p, :c, :d, 'shared')
            """),
            {"o": org_id, "n": name, "s": slug, "p": pos, "c": color, "d": is_done},
        )
    db.commit()


@router.patch("/api/{task_id}/move")
async def move_task(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    body = await request.json()
    new_status = body.get("status")
    new_position = body.get("position", 0)
    new_column_id = body.get("column_id")

    task = tenant_query(db, Task, request.state.org_id).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    column_status = None
    target_private = False
    if "column_id" in body:
        if new_column_id:
            try:
                column_id_int = int(new_column_id)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="Invalid column")
            column = db.execute(
                text(f"""
                    SELECT slug, is_done, COALESCE(visibility, 'shared') AS visibility
                    FROM kanban_columns
                    WHERE id = :id AND {_visible_column_where_sql()}
                """),
                {"id": column_id_int, "org_id": request.state.org_id, "user_id": user.id},
            ).fetchone()
            if not column:
                raise HTTPException(status_code=400, detail="Invalid column")
            column_status = _status_for_kanban_column(column.slug, column.is_done)
            target_private = column.visibility == "private"
            if target_private:
                _upsert_private_placement(
                    db,
                    org_id=request.state.org_id,
                    user_id=user.id,
                    task_id=task.id,
                    column_id=column_id_int,
                    position=int(new_position or 0),
                )
            else:
                _clear_private_placement(db, user_id=user.id, task_id=task.id)
                task.column_id = column_id_int
        else:
            _clear_private_placement(db, user_id=user.id, task_id=task.id)
            task.column_id = None

    new_status = _canonical_kanban_status(new_status)
    if new_status not in VALID_KANBAN_STATUSES:
        if column_status:
            new_status = column_status
        else:
            raise HTTPException(status_code=400, detail="Invalid status")

    if not target_private:
        task.status = new_status
        task.position = new_position
        if new_status == "completed" and not task.completed_at:
            task.completed_at = datetime.now()
    db.commit()

    return {"success": True, "task_id": task_id, "status": new_status}


@router.post("/api/quick-add")
async def quick_add_task(
    request: Request,
    db: Session = Depends(get_db)
):
    """Quick-add a task from the kanban board"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    body = await request.json()
    title = body.get("title", "").strip()
    status = body.get("status", "pending")
    column_id = body.get("column_id")

    if not title:
        return JSONResponse({"error": "Title required"}, status_code=400)

    target_column = None
    if column_id:
        try:
            column_id = int(column_id)
        except (TypeError, ValueError):
            return JSONResponse({"error": "Invalid column"}, status_code=400)
        target_column = db.execute(
            text(f"""
                SELECT id, slug, is_done, COALESCE(visibility, 'shared') AS visibility
                FROM kanban_columns
                WHERE id = :id AND {_visible_column_where_sql()}
            """),
            {"id": column_id, "org_id": request.state.org_id, "user_id": user.id},
        ).fetchone()
        if not target_column:
            return JSONResponse({"error": "Invalid column"}, status_code=400)
        status = _status_for_kanban_column(target_column.slug, target_column.is_done)

    status = _canonical_kanban_status(status)

    if status not in VALID_KANBAN_STATUSES:
        return JSONResponse({"error": "Invalid status"}, status_code=400)

    try:
        task = Task(
            title=title,
            status=status,
            priority="medium",
            org_id=request.state.org_id,
            column_id=None if (target_column and target_column.visibility == "private") else column_id,
            assigned_to=user.id if (target_column and target_column.visibility == "private") else None,
            completed_at=datetime.now() if status == "completed" else None
        )
        db.add(task)
        db.flush()
        if target_column and target_column.visibility == "private":
            _upsert_private_placement(
                db,
                org_id=request.state.org_id,
                user_id=user.id,
                task_id=task.id,
                column_id=target_column.id,
                position=0,
            )
        db.commit()
        task_id = task.id
        task_title = task.title
        task_status = task.status
        task_priority = task.priority
    except Exception as e:
        db.rollback()
        # Fallback: insert via raw SQL
        result = db.execute(
            text("""
                INSERT INTO tasks (title, status, priority, org_id, column_id, assigned_to)
                VALUES (:t, :s, :p, :o, :column_id, :assigned_to)
                RETURNING id
            """),
            {
                "t": title,
                "s": status,
                "p": "medium",
                "o": request.state.org_id,
                "column_id": None if (target_column and target_column.visibility == "private") else column_id,
                "assigned_to": user.id if (target_column and target_column.visibility == "private") else None,
            },
        )
        task_id = result.scalar()
        if target_column and target_column.visibility == "private":
            _upsert_private_placement(
                db,
                org_id=request.state.org_id,
                user_id=user.id,
                task_id=task_id,
                column_id=target_column.id,
                position=0,
            )
        db.commit()
        task_title = title
        task_status = status
        task_priority = "medium"

    return JSONResponse({
        "success": True,
        "task": {
            "id": task_id,
            "title": task_title,
            "status": task_status,
            "priority": task_priority
        }
    })


# ── Kanban Column CRUD (K1-K3) ──────────────────────────────

@router.post("/api/columns")
async def create_column(request: Request, db: Session = Depends(get_db)):
    """K1: Create a new kanban column."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = request.state.org_id
    body = await request.json()
    name = body.get("name", "").strip()
    visibility = _normalize_column_visibility(body.get("visibility", "shared"))
    if not name:
        return JSONResponse({"error": "Nome obrigatorio"}, status_code=400)
    if visibility == "shared" and not _can_manage_shared_kanban(user):
        return JSONResponse({"error": "Apenas gestores podem criar listas compartilhadas"}, status_code=403)
    # Get max position
    max_pos = db.execute(
        text("""
            SELECT COALESCE(MAX(position), -1)
            FROM kanban_columns
            WHERE org_id = :o AND COALESCE(visibility, 'shared') = :visibility
              AND COALESCE(is_archived, FALSE) = FALSE
        """),
        {"o": org_id, "visibility": visibility},
    ).scalar()
    slug = _slugify_column_name(name)
    color = body.get("color") or "#94a3b8"
    result = db.execute(
        text("""
            INSERT INTO kanban_columns
                (org_id, name, slug, position, color, visibility, owner_user_id)
            VALUES (:o, :n, :s, :p, :color, :visibility, :owner)
            RETURNING id
        """),
        {
            "o": org_id,
            "n": name,
            "s": slug,
            "p": max_pos + 1,
            "color": color,
            "visibility": visibility,
            "owner": user.id if visibility == "private" else None,
        },
    )
    col_id = result.scalar()
    db.commit()
    return JSONResponse({
        "success": True,
        "id": col_id,
        "name": name,
        "position": max_pos + 1,
        "visibility": visibility,
    })


@router.patch("/api/columns/{col_id}")
async def update_column(request: Request, col_id: int, db: Session = Depends(get_db)):
    """K2+K3: Rename or reorder a kanban column."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = request.state.org_id
    column = db.execute(
        text(f"""
            SELECT id, COALESCE(visibility, 'shared') AS visibility, owner_user_id
            FROM kanban_columns
            WHERE id = :id AND {_visible_column_where_sql()}
        """),
        {"id": col_id, "o": org_id, "org_id": org_id, "user_id": user.id},
    ).fetchone()
    if not column:
        return JSONResponse({"error": "Coluna nao encontrada"}, status_code=404)
    if column.visibility == "shared" and not _can_manage_shared_kanban(user):
        return JSONResponse({"error": "Apenas gestores podem editar listas compartilhadas"}, status_code=403)
    body = await request.json()
    updates = []
    params = {"id": col_id, "o": org_id}
    if "name" in body:
        updates.append("name = :name")
        params["name"] = body["name"].strip()
    if "position" in body:
        updates.append("position = :pos")
        params["pos"] = int(body["position"])
    if "color" in body:
        updates.append("color = :color")
        params["color"] = body["color"]
    if "is_done" in body and column.visibility == "shared":
        updates.append("is_done = :is_done")
        params["is_done"] = bool(body["is_done"])
    if not updates:
        return JSONResponse({"error": "Nothing to update"}, status_code=400)
    db.execute(
        text(f"UPDATE kanban_columns SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE id = :id AND org_id = :o"),
        params,
    )
    db.commit()
    return JSONResponse({"success": True})


@router.delete("/api/columns/{col_id}")
async def delete_column(request: Request, col_id: int, db: Session = Depends(get_db)):
    """Delete a kanban column (move tasks to first column)."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = request.state.org_id
    column = db.execute(
        text(f"""
            SELECT id, COALESCE(visibility, 'shared') AS visibility, owner_user_id
            FROM kanban_columns
            WHERE id = :id AND {_visible_column_where_sql()}
        """),
        {"id": col_id, "org_id": org_id, "user_id": user.id},
    ).fetchone()
    if not column:
        return JSONResponse({"error": "Coluna nao encontrada"}, status_code=404)
    if column.visibility == "shared" and not _can_manage_shared_kanban(user):
        return JSONResponse({"error": "Apenas gestores podem remover listas compartilhadas"}, status_code=403)
    if column.visibility == "private":
        db.execute(
            text("DELETE FROM task_kanban_placements WHERE org_id = :o AND user_id = :user_id AND column_id = :id"),
            {"o": org_id, "user_id": user.id, "id": col_id},
        )
    else:
        first_col = db.execute(
        text("""
            SELECT id FROM kanban_columns
            WHERE org_id = :o AND id != :id
              AND COALESCE(visibility, 'shared') = 'shared'
              AND COALESCE(is_archived, FALSE) = FALSE
            ORDER BY position LIMIT 1
        """),
        {"o": org_id, "id": col_id},
        ).fetchone()
        if first_col:
            db.execute(
                text("UPDATE tasks SET column_id = :target WHERE column_id = :src AND org_id = :o"),
                {"target": first_col.id, "src": col_id, "o": org_id},
            )
    db.execute(
        text("UPDATE kanban_columns SET is_archived = TRUE, updated_at = CURRENT_TIMESTAMP WHERE id = :id AND org_id = :o"),
        {"id": col_id, "o": org_id},
    )
    db.commit()
    return JSONResponse({"success": True})


@router.post("/api/columns/reorder")
async def reorder_columns(request: Request, db: Session = Depends(get_db)):
    """K3: Reorder all columns at once."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = request.state.org_id
    body = await request.json()
    order = body.get("order", [])  # list of column IDs in new order
    for i, col_id in enumerate(order):
        db.execute(
            text(f"""
                UPDATE kanban_columns SET position = :pos, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id AND {_visible_column_where_sql()}
            """),
            {"pos": i, "id": int(col_id), "org_id": org_id, "user_id": user.id},
        )
    db.commit()
    return JSONResponse({"success": True})


@router.post("/api/{task_id}/subtask/toggle")
async def toggle_subtask(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db)
):
    """Toggle a subtask's completion status"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    task = tenant_query(db, Task, request.state.org_id).filter(Task.id == task_id).first()
    if not task or not task.parent_task_id:
        return JSONResponse({"error": "Subtask not found"}, status_code=404)

    if task.status == "completed":
        task.status = "pending"
        task.completed_at = None
    else:
        task.status = "completed"
        task.completed_at = datetime.now()

    db.commit()
    return JSONResponse({"success": True, "status": task.status})


# ==========================================
# TASK CALENDAR VIEW
# ==========================================

@router.get("/calendar", response_class=HTMLResponse)
async def task_calendar_view(request: Request, db: Session = Depends(get_db)):
    """Calendar view showing tasks by due_date using FullCalendar."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    tasks = tenant_query(db, Task, request.state.org_id).filter(
        Task.parent_task_id.is_(None),
        Task.due_date.isnot(None)
    ).order_by(
        Task.due_date.asc(),
        Task.id.asc(),
    ).limit(TASK_CALENDAR_EVENT_LIMIT).all()

    # Build events JSON for FullCalendar
    events = []
    for t in tasks:
        priority = t.priority if t.priority in TASK_CALENDAR_PRIORITIES else "medium"
        events.append({
            "id": t.id,
            "title": t.title,
            "start": t.due_date.isoformat(),
            "url": f"{PREFIX}/tasks/{t.id}",
            "classNames": [
                "task-calendar-event",
                f"task-calendar-event--{priority}",
            ],
            "extendedProps": {
                "status": t.status,
                "priority": priority,
                "assignee": t.assigned_to or "",
            }
        })

    return templates.TemplateResponse("app/tasks/calendar_view.html", {
        **get_context(request, db),
        "events_json": _json_script_safe(events),
    })


# ==========================================
# TASK COMMENTS
# ==========================================

@router.post("/{task_id}/comments")
async def add_task_comment(
    request: Request,
    task_id: int,
    content: str = Form(...),
    db: Session = Depends(get_db)
):
    """Add a comment to a task."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    task = tenant_query(db, Task, request.state.org_id).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    comment = TaskComment(
        task_id=task_id,
        user_id=user.id,
        content=content.strip()
    )
    db.add(comment)
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/tasks/{task_id}#comments", status_code=302)


# ==========================================
# TASK API - JSON endpoints for modal/AJAX
# ==========================================

@router.get("/api/{task_id}/detail")
async def get_task_detail(request: Request, task_id: int, db: Session = Depends(get_db)):
    """Get full task details as JSON for the Trello-style modal."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    task = tenant_query(db, Task, request.state.org_id).filter(Task.id == task_id).first()
    if not task:
        return JSONResponse({"error": "Task not found"}, status_code=404)

    # Build subtasks list
    subtasks = tenant_query(db, Task, request.state.org_id).filter(
        Task.parent_task_id == task_id
    ).order_by(Task.position.asc(), Task.id.asc()).all()

    # Build comments list
    comments = db.query(TaskComment).filter(TaskComment.task_id == task_id).order_by(TaskComment.created_at.asc()).all()

    return JSONResponse({
        "id": task.id,
        "title": task.title,
        "description": task.description or "",
        "status": task.status,
        "column_id": task.column_id,
        "position": task.position,
        "priority": task.priority or "medium",
        "assigned_to": task.assigned_to,
        "assignee_name": task.assignee.name if task.assignee else None,
        "client_id": task.client_id,
        "client_name": f"{task.client.first_name} {task.client.last_name}" if task.client else None,
        "case_id": task.case_id,
        "case_name": task.case.case_number or task.case.case_name if task.case else None,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "tags": task.tags or "",
        "estimated_hours": task.estimated_hours,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "subtasks": [
            {"id": s.id, "title": s.title, "status": s.status}
            for s in subtasks
        ],
        "comments": [
            {
                "id": c.id,
                "content": c.content,
                "user_name": c.user.name if c.user else "Sistema",
                "created_at": c.created_at.strftime("%d/%m %H:%M") if c.created_at else "",
            }
            for c in comments
        ],
    })


@router.put("/api/{task_id}/update")
async def update_task_api(request: Request, task_id: int, db: Session = Depends(get_db)):
    """Update task fields via JSON (from Trello-style modal)."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    task = tenant_query(db, Task, request.state.org_id).filter(Task.id == task_id).first()
    if not task:
        return JSONResponse({"error": "Task not found"}, status_code=404)

    body = await request.json()

    if "title" in body:
        task.title = body["title"].strip()
    if "description" in body:
        task.description = body["description"].strip() if body["description"] else None
    if "priority" in body and body["priority"] in ("low", "medium", "high", "urgent"):
        task.priority = body["priority"]
    if "assigned_to" in body:
        task.assigned_to = int(body["assigned_to"]) if body["assigned_to"] else None
    if "due_date" in body:
        task.due_date = parse_date(body["due_date"]) if body["due_date"] else None
    if "tags" in body:
        task.tags = body["tags"].strip() if body["tags"] else None
    if "estimated_hours" in body:
        task.estimated_hours = float(body["estimated_hours"]) if body["estimated_hours"] else None
    column_status = None
    if "column_id" in body:
        new_column_id = body["column_id"]
        if new_column_id:
            try:
                column_id_int = int(new_column_id)
            except (TypeError, ValueError):
                return JSONResponse({"error": "Invalid column"}, status_code=400)
            column = db.execute(
                text("SELECT slug, is_done FROM kanban_columns WHERE id = :id AND org_id = :org_id"),
                {"id": column_id_int, "org_id": request.state.org_id},
            ).fetchone()
            if not column:
                return JSONResponse({"error": "Invalid column"}, status_code=400)
            column_status = _status_for_kanban_column(column.slug, column.is_done)
            task.column_id = column_id_int
        else:
            task.column_id = None
    if "position" in body:
        try:
            task.position = max(int(body["position"]), 0)
        except (TypeError, ValueError):
            return JSONResponse({"error": "Invalid position"}, status_code=400)
    if "status" in body:
        new_status = _canonical_kanban_status(body["status"])
        if new_status not in VALID_KANBAN_STATUSES and column_status:
            new_status = column_status
        if new_status in VALID_KANBAN_STATUSES:
            task.status = new_status
            if new_status == "completed" and not task.completed_at:
                task.completed_at = datetime.now()
            elif new_status != "completed":
                task.completed_at = None
    elif column_status:
        task.status = column_status

    db.commit()
    return JSONResponse({"success": True, "task_id": task_id})


@router.post("/api/{task_id}/comments/add")
async def add_task_comment_api(request: Request, task_id: int, db: Session = Depends(get_db)):
    """Add a comment to a task via JSON."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    task = tenant_query(db, Task, request.state.org_id).filter(Task.id == task_id).first()
    if not task:
        return JSONResponse({"error": "Task not found"}, status_code=404)

    body = await request.json()
    content = body.get("content", "").strip()
    if not content:
        return JSONResponse({"error": "Content required"}, status_code=400)

    comment = TaskComment(task_id=task_id, user_id=user.id, content=content)
    db.add(comment)
    db.commit()

    return JSONResponse({
        "success": True,
        "comment": {
            "id": comment.id,
            "content": comment.content,
            "user_name": user.name,
            "created_at": comment.created_at.strftime("%d/%m %H:%M") if comment.created_at else "",
        }
    })


# ==========================================
# LOCAL TASKS - Dynamic routes (must be LAST)
# ==========================================

@router.get("/{task_id}", response_class=HTMLResponse)
async def view_task(request: Request, task_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    task = tenant_query(db, Task, request.state.org_id).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Load comments with user info
    comments = db.query(TaskComment).filter(TaskComment.task_id == task_id).order_by(TaskComment.created_at.asc()).all()

    return templates.TemplateResponse("app/tasks/detail.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "task": task,
        "comments": comments,
    })


@router.get("/{task_id}/edit", response_class=HTMLResponse)
async def edit_task_form(request: Request, task_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    task = tenant_query(db, Task, request.state.org_id).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    clients = tenant_query(db, Client, request.state.org_id).order_by(Client.first_name).all()
    cases = tenant_query(db, Case, request.state.org_id).order_by(Case.created_at.desc()).all()
    users = tenant_query(db, User, request.state.org_id).filter(User.enabled == True).all()

    subtasks = tenant_query(db, Task, request.state.org_id).filter(
        Task.parent_task_id == task_id
    ).order_by(Task.id.asc()).all()

    return templates.TemplateResponse("app/tasks/form.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "task": task,
        "clients": clients,
        "cases": cases,
        "users": users,
        "selected_client_id": None,
        "selected_case_id": None,
        "subtasks": subtasks,
        "action": "Update"
    })


@router.post("/{task_id}/edit")
async def update_task(
    request: Request,
    task_id: int,
    title: str = Form(...),
    description: str = Form(None),
    task_type: str = Form(None),
    status: str = Form("pending"),
    priority: str = Form("medium"),
    client_id: str = Form(None),
    case_id: str = Form(None),
    assigned_to: str = Form(None),
    due_date: str = Form(None),
    reminder_date: str = Form(None),
    tags: str = Form(None),
    estimated_hours: str = Form(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Convert form strings to proper types
    client_id = form_int(client_id)
    case_id = form_int(case_id)
    assigned_to = form_int(assigned_to)
    estimated_hours = form_float(estimated_hours)

    task = tenant_query(db, Task, request.state.org_id).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Check if completing
    if status == "completed" and task.status != "completed":
        task.completed_at = datetime.now()
    elif status != "completed":
        task.completed_at = None

    task.title = title
    task.description = description
    task.task_type = task_type
    task.status = status
    task.priority = priority
    task.client_id = client_id
    task.case_id = case_id
    task.assigned_to = assigned_to
    task.due_date = parse_date(due_date)
    task.reminder_date = parse_date(reminder_date)
    task.tags = tags.strip() if tags else None
    task.estimated_hours = estimated_hours

    db.commit()

    # Process subtasks from form
    form_data = await request.form()
    subtask_titles = form_data.getlist("subtask_title[]")
    subtask_done = form_data.getlist("subtask_done[]")

    # Get existing subtask IDs from form (for updates)
    subtask_ids = form_data.getlist("subtask_id[]")

    # Track which existing subtasks were in the form
    existing_subtask_ids = set()

    for i, stitle in enumerate(subtask_titles):
        stitle = stitle.strip()
        if not stitle:
            continue
        is_done = str(i) in subtask_done

        # Check if this is an existing subtask
        if i < len(subtask_ids) and subtask_ids[i]:
            sid = int(subtask_ids[i])
            existing_subtask_ids.add(sid)
            sub = db.query(Task).filter(Task.id == sid, Task.parent_task_id == task_id).first()
            if sub:
                sub.title = stitle
                sub.status = "completed" if is_done else "pending"
                if is_done and not sub.completed_at:
                    sub.completed_at = datetime.now()
                elif not is_done:
                    sub.completed_at = None
        else:
            # New subtask
            sub = Task(
                title=stitle,
                status="completed" if is_done else "pending",
                priority="medium",
                parent_task_id=task_id,
                org_id=task.org_id,
                completed_at=datetime.now() if is_done else None
            )
            db.add(sub)

    # Delete subtasks that were removed from the form
    for existing_sub in task.subtasks:
        if existing_sub.id not in existing_subtask_ids:
            db.delete(existing_sub)

    db.commit()

    return RedirectResponse(url=f"{PREFIX}/tasks/{task_id}", status_code=302)


@router.post("/{task_id}/complete")
async def complete_task(request: Request, task_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    task = tenant_query(db, Task, request.state.org_id).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = "completed"
    task.completed_at = datetime.now()
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/tasks", status_code=302)


@router.post("/{task_id}/delete")
async def delete_task(request: Request, task_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    task = tenant_query(db, Task, request.state.org_id).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    db.delete(task)
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/tasks", status_code=302)
