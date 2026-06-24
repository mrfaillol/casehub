"""
CaseHub - Task Routes
Includes both local database tasks and Notion-synced tasks
"""
from core.form_utils import form_int, form_float
from fastapi import APIRouter, Depends, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from core.template_config import templates, PREFIX
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import bindparam, or_, text
from typing import Optional, List
from datetime import datetime, date
import json
import re
import os
import uuid
import hashlib

from models import get_db, Client, Case, User, Task, Reminder, TaskComment, Organization, Document
from auth import get_current_user
from models.tenant import tenant_query
from services.notion_tasks import notion_tasks_service, TASK_DATABASES
from i18n import get_translations
from config import settings as _app_settings

# Card attachments (FB3, alpha UsuarioDemo — anexar documento no cartão Kanban estilo
# Trello). Reusa o mesmo diretório de uploads e os mesmos guards do pipeline de
# routes.documents (allowlist de extensão, sanitização de nome, cap de tamanho,
# SHA256). Mantido patchable nos testes via task_routes.UPLOAD_DIR.
UPLOAD_DIR = os.path.join(_app_settings.BASE_DIR, "data", "uploads")
ATTACH_ALLOWED_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.gif',
    '.tiff', '.tif', '.bmp', '.xls', '.xlsx', '.txt', '.rtf',
    '.csv', '.zip', '.rar', '.msg', '.eml',
}
ATTACH_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB (paridade com routes.documents)

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
KANBAN_MANAGER_ROLES = {"admin", "superadmin", "owner", "manager", "gestor"}
KANBAN_COLLAB_LOCK_KEY = "kanban_collab_locked"
KANBAN_DEFAULT_PRIVATE_COLUMN = "Recebidas"
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


def _normalize_task_visibility(value) -> str:
    """Task-level privacy. 'private' (só criador+responsável) | 'org' (default, toda a org)."""
    return "private" if str(value or "").strip().lower() in {"private", "privada", "me", "true", "1", "on"} else "org"


def _visible_task_filter(user_id: int):
    """Backend privacy guard — NÃO confiar só no front (Sentinela).
    Tarefa privada só aparece p/ o CRIADOR ou o RESPONSÁVEL; org-scope já vem do tenant_query.
    Tarefas legadas (visibility NULL/'org') seguem visíveis a toda a org."""
    return or_(
        Task.visibility.is_(None),
        Task.visibility != "private",
        Task.created_by == user_id,
        Task.assigned_to == user_id,
        text("""
            EXISTS (
                SELECT 1
                FROM task_assignees ta_visible
                WHERE ta_visible.task_id = tasks.id
                  AND ta_visible.user_id = :visible_user_id
            )
        """).bindparams(bindparam("visible_user_id", user_id)),
    )


def _not_archived_task_filter():
    """FB2: o board do Kanban só mostra cartões NÃO arquivados.
    COALESCE(is_archived, FALSE)=FALSE — tarefas legadas (is_archived NULL) seguem
    visíveis. Espelha o COALESCE(is_archived, FALSE) das queries de kanban_columns."""
    return or_(Task.is_archived.is_(None), Task.is_archived == False)  # noqa: E712


def _assigned_to_user_filter(user_id: int):
    return or_(
        Task.assigned_to == user_id,
        text("""
            EXISTS (
                SELECT 1
                FROM task_assignees ta_filter
                WHERE ta_filter.task_id = tasks.id
                  AND ta_filter.user_id = :filter_user_id
            )
        """).bindparams(bindparam("filter_user_id", user_id)),
    )


def _user_role_key(user) -> str:
    return str(getattr(user, "role", "") or getattr(user, "user_type", "") or "").lower()


def _settings_dict(value) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return dict(parsed) if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _kanban_org_settings(db: Session, org_id: int):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        return None, {}
    return org, _settings_dict(org.settings)


def _is_base_kanban_admin(user) -> bool:
    if not user:
        return False
    return str(getattr(user, "user_type", "") or "").lower() == "admin"


def _can_manage_kanban_collab(user, settings: Optional[dict] = None) -> bool:
    return _is_base_kanban_admin(user)


def _kanban_collab_locked(settings: Optional[dict]) -> bool:
    return bool((settings or {}).get(KANBAN_COLLAB_LOCK_KEY, False))


def _can_access_collaborator_board(user, target_user_id: int, settings: Optional[dict]) -> bool:
    if not user:
        return False
    try:
        if int(target_user_id) == int(user.id):
            return True
    except (TypeError, ValueError):
        return False
    return (not _kanban_collab_locked(settings)) or _can_manage_kanban_collab(user, settings)


def _can_manage_shared_kanban(user) -> bool:
    return _user_role_key(user) in KANBAN_MANAGER_ROLES


def _can_view_team_private_kanban(user) -> bool:
    return _user_role_key(user) in KANBAN_MANAGER_ROLES


def _ensure_kanban_schema(db):
    """Keep Kanban custom lists compatible with older Basic databases."""
    bind = db.get_bind()
    dialect = bind.dialect.name if bind is not None else "sqlite"
    false_default = "FALSE" if dialect == "postgresql" else "0"
    additions = [
        ("kanban_columns", "visibility", "VARCHAR(20) DEFAULT 'shared'"),
        ("kanban_columns", "owner_user_id", "INTEGER"),
        ("kanban_columns", "is_archived", f"BOOLEAN DEFAULT {false_default}"),
        # due_time: horário do prazo ("HH:MM") p/ reloginho Trello no card. Compat DBs antigas do alpha.
        ("tasks", "due_time", "VARCHAR(5)"),
        # Privacidade de tarefa (Equipe CaseHub 03/06): 'org' (default, toda a org vê) | 'private'
        # (só criador + responsável). created_by preserva o dono p/ enforcement no backend.
        ("tasks", "visibility", "VARCHAR(20) DEFAULT 'org'"),
        ("tasks", "created_by", "INTEGER"),
        # Soft-archive de cartão (FB2 alpha UsuarioDemo). Espelha kanban_columns.is_archived.
        # Default FALSE/0 mantém tarefas legadas visíveis no board. Compat DBs antigas.
        ("tasks", "is_archived", f"BOOLEAN DEFAULT {false_default}"),
        ("tasks", "archived_at", "TIMESTAMP"),
        # Anexo de documento no cartão (FB3, alpha UsuarioDemo). Nullable: a maioria dos
        # documentos não pertence a uma tarefa. FK lógica → tasks.id; ondelete SET
        # NULL preserva o arquivo se a tarefa sumir. Index p/ listagem por task.
        ("documents", "task_id", "INTEGER"),
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
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS task_assignees (
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            PRIMARY KEY (task_id, user_id)
        )
    """))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_task_kanban_placements_column "
        "ON task_kanban_placements (org_id, user_id, column_id, position)"
    ))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_task_assignees_user ON task_assignees (user_id)"))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_task_assignees_task ON task_assignees (task_id)"))
    # Index p/ listar anexos por cartão (FB3). IF NOT EXISTS é idempotente em
    # SQLite e Postgres; só roda se a coluna documents.task_id já existe.
    try:
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_documents_task_id ON documents (task_id)"))
    except Exception:
        db.rollback()
    db.execute(text("""
        INSERT INTO task_assignees (task_id, user_id)
        SELECT id, assigned_to
        FROM tasks
        WHERE assigned_to IS NOT NULL
        ON CONFLICT DO NOTHING
    """))
    db.commit()


def _visible_column_where_sql(*, include_team_private: bool = False) -> str:
    private_owner_clause = (
        "(:include_team_private = 1 OR owner_user_id = :user_id)"
        if include_team_private
        else "owner_user_id = :user_id"
    )
    return (
        "org_id = :org_id AND COALESCE(is_archived, FALSE) = FALSE "
        "AND (COALESCE(visibility, 'shared') = 'shared' "
        f"OR (visibility = 'private' AND {private_owner_clause}))"
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


def _clear_all_private_placements(db, *, org_id: int, task_id: int):
    db.execute(
        text("DELETE FROM task_kanban_placements WHERE org_id = :org_id AND task_id = :task_id"),
        {"org_id": org_id, "task_id": task_id},
    )


def _ensure_private_board_column(db, *, org_id: int, user_id: int):
    column = db.execute(
        text("""
            SELECT id, slug, is_done
            FROM kanban_columns
            WHERE org_id = :org_id
              AND COALESCE(visibility, 'shared') = 'private'
              AND owner_user_id = :user_id
              AND COALESCE(is_archived, FALSE) = FALSE
            ORDER BY position ASC, id ASC
            LIMIT 1
        """),
        {"org_id": org_id, "user_id": user_id},
    ).fetchone()
    if column:
        return column

    max_pos = db.execute(
        text("""
            SELECT COALESCE(MAX(position), -1)
            FROM kanban_columns
            WHERE org_id = :org_id
              AND COALESCE(visibility, 'shared') = 'private'
              AND owner_user_id = :user_id
        """),
        {"org_id": org_id, "user_id": user_id},
    ).scalar()
    result = db.execute(
        text("""
            INSERT INTO kanban_columns
                (org_id, name, slug, position, color, visibility, owner_user_id)
            VALUES (:org_id, :name, :slug, :position, :color, 'private', :user_id)
            RETURNING id, slug, is_done
        """),
        {
            "org_id": org_id,
            "name": KANBAN_DEFAULT_PRIVATE_COLUMN,
            "slug": "recebidas",
            "position": (max_pos or -1) + 1,
            "color": "#1C2447",
            "user_id": user_id,
        },
    )
    return result.fetchone()


def _task_clone_core_kwargs(task: Task, *, org_id: int, created_by: int, assigned_to: Optional[int]):
    return {
        "org_id": org_id,
        "title": task.title,
        "description": task.description,
        "priority": task.priority,
        "column_id": None,
        "client_id": task.client_id,
        "case_id": task.case_id,
        "assigned_to": assigned_to,
        "created_by": created_by,
        "due_date": task.due_date,
        "due_time": task.due_time,
    }


def _clone_task_tree(db, *, org_id: int, source_task: Task, target_user_id: int, created_by: int):
    clone = Task(**_task_clone_core_kwargs(
        source_task,
        org_id=org_id,
        created_by=created_by,
        assigned_to=target_user_id,
    ))
    db.add(clone)
    db.flush()
    return clone


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


def _coerce_task_assignee_ids(payload) -> list[int]:
    if hasattr(payload, "getlist"):
        raw = payload.getlist("assigned_to_ids") or payload.getlist("assigned_to_ids[]")
        if not raw:
            scalar = payload.get("assigned_to")
            raw = [scalar] if scalar not in (None, "", "0", 0) else []
    else:
        raw = payload.get("assigned_to_ids")
        if raw is None:
            raw = payload.get("assigned_to")
        if raw in (None, "", "0", 0):
            raw = []
        elif not isinstance(raw, list):
            raw = [raw]

    ids: list[int] = []
    seen: set[int] = set()
    for item in raw:
        try:
            user_id = int(item)
        except (TypeError, ValueError):
            continue
        if user_id <= 0 or user_id in seen:
            continue
        ids.append(user_id)
        seen.add(user_id)
    return ids


def _validate_task_assignee_ids(db: Session, org_id: int, user_ids: list[int]) -> list[int]:
    if not user_ids:
        return []
    rows = db.execute(
        text("""
            SELECT id
            FROM users
            WHERE org_id = :org_id AND enabled = TRUE AND id IN :ids
        """).bindparams(bindparam("ids", expanding=True)),
        {"org_id": org_id, "ids": user_ids},
    ).fetchall()
    valid = {row.id for row in rows}
    return [user_id for user_id in user_ids if user_id in valid]


def _load_task_assignee_ids(db: Session, task_ids: list[int]) -> dict[int, list[int]]:
    if not task_ids:
        return {}
    try:
        rows = db.execute(
            text("""
                SELECT task_id, user_id
                FROM task_assignees
                WHERE task_id IN :ids
                ORDER BY task_id, user_id
            """).bindparams(bindparam("ids", expanding=True)),
            {"ids": task_ids},
        ).fetchall()
    except Exception:
        db.rollback()
        return {}

    by_task: dict[int, list[int]] = {}
    for row in rows:
        by_task.setdefault(row.task_id, []).append(row.user_id)
    return by_task


def _load_task_assignees(db: Session, org_id: int, assignee_ids_by_task: dict[int, list[int]]) -> dict[int, list[dict]]:
    user_ids = sorted({uid for ids in assignee_ids_by_task.values() for uid in ids if uid})
    if not user_ids:
        return {}
    rows = db.execute(
        text("""
            SELECT id, name, color, photo_url
            FROM users
            WHERE org_id = :org_id AND id IN :ids
        """).bindparams(bindparam("ids", expanding=True)),
        {"org_id": org_id, "ids": user_ids},
    ).fetchall()
    users = {}
    for row in rows:
        cleaned = (row.name or "").replace("Dr. ", "").replace("Dra. ", "").strip()
        parts = cleaned.split()
        users[row.id] = {
            "id": row.id,
            "name": row.name or "",
            "short_name": parts[0] if parts else (row.name or ""),
            "initials": "".join(part[:1].upper() for part in parts[:2]) or "?",
            "color": row.color or "#1C2447",
            "photo_url": row.photo_url or "",
        }
    return {
        task_id: [users[uid] for uid in user_ids if uid in users]
        for task_id, user_ids in assignee_ids_by_task.items()
    }


def _save_task_assignees(db: Session, task_id: int, user_ids: list[int]) -> None:
    db.execute(text("DELETE FROM task_assignees WHERE task_id = :task_id"), {"task_id": task_id})
    for user_id in user_ids:
        db.execute(
            text("""
                INSERT INTO task_assignees (task_id, user_id)
                VALUES (:task_id, :user_id)
                ON CONFLICT DO NOTHING
            """),
            {"task_id": task_id, "user_id": user_id},
        )


def _attach_task_assignees(db: Session, org_id: int, tasks: list[Task]) -> None:
    if not tasks:
        return
    task_ids = [task.id for task in tasks if task.id]
    assignee_ids_by_task = _load_task_assignee_ids(db, task_ids)
    for task in tasks:
        if task.assigned_to:
            assignee_ids_by_task.setdefault(task.id, [task.assigned_to])
    assignees_by_task = _load_task_assignees(db, org_id, assignee_ids_by_task)
    for task in tasks:
        assignees = assignees_by_task.get(task.id, [])
        setattr(task, "assignees_list", assignees)
        setattr(task, "assigned_to_ids", [item["id"] for item in assignees])


def _assigned_user_ids_for_tasks(tasks, db=None):
    ids = {t.assigned_to for t in tasks if t.assigned_to}
    if db is not None:
        ids_by_task = _load_task_assignee_ids(db, [t.id for t in tasks if getattr(t, "id", None)])
        for user_ids in ids_by_task.values():
            ids.update(user_ids)
    return sorted(uid for uid in ids if uid)


def _notify_new_task_assignees(db: Session, task: Task, editor_id: int, new_user_ids: set[int]) -> None:
    notify_ids = [uid for uid in sorted(new_user_ids) if uid and uid != editor_id]
    if not notify_ids:
        return
    try:
        from services.notifications.in_app import create_notification
        for user_id in notify_ids:
            create_notification(
                db=db,
                user_id=user_id,
                title=f"Nova tarefa atribuída a você: {task.title[:120]}",
                notification_type="task_created",
                message="Você foi designado(a) como responsável por esta tarefa no Kanban.",
                severity="info",
                task_id=task.id,
                action_url=f"{PREFIX}/tasks/kanban",
            )
        db.commit()
    except Exception:
        db.rollback()
    try:
        from routes.team_messages import post_system_dm_to_user
        due_parts = []
        if getattr(task, "due_date", None):
            due_parts.append(str(task.due_date))
        if getattr(task, "due_time", None):
            due_parts.append(str(task.due_time)[:5])
        due_label = f" Prazo: {' '.join(due_parts)}." if due_parts else ""
        title = str(getattr(task, "title", "") or "tarefa").strip()[:160]
        body = f"Kanban: você foi designado(a) para \"{title}\".{due_label}"
        for user_id in notify_ids:
            post_system_dm_to_user(db, int(getattr(task, "org_id", 0) or 0), user_id, body)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

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
        Task.parent_task_id.is_(None),  # Only top-level tasks
        _visible_task_filter(user.id),  # Privacy guard
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
        Task.due_date < date.today(),
        _visible_task_filter(user.id),
    ).count()

    # Get today's count
    today_count = tenant_query(db, Task, request.state.org_id).filter(
        Task.status != "completed",
        Task.due_date == date.today(),
        _visible_task_filter(user.id),
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
    due_time: str = Form(None),
    reminder_date: str = Form(None),
    tags: str = Form(None),
    estimated_hours: str = Form(None),
    visibility: str = Form("org"),
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
    form_data = await request.form()
    requested_assignee_ids = _coerce_task_assignee_ids(form_data)
    if not requested_assignee_ids and assigned_to:
        requested_assignee_ids = [assigned_to]
    assignee_ids = _validate_task_assignee_ids(db, request.state.org_id, requested_assignee_ids)
    if len(assignee_ids) != len(requested_assignee_ids):
        raise HTTPException(status_code=400, detail="Invalid assignee")
    assigned_to = assignee_ids[0] if assignee_ids else None
    # due_time: "HH:MM" (input type=time). Mesma validação do edit (update_task_api)
    # para não corromper o reloginho do card. Inválido/vazio => None.
    due_time = (due_time or "").strip()
    due_time = due_time if re.match(r"^\d{2}:\d{2}$", due_time) else None

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
        due_time=due_time,
        reminder_date=parse_date(reminder_date),
        tags=tags.strip() if tags else None,
        estimated_hours=estimated_hours,
        visibility=_normalize_task_visibility(visibility),
        created_by=user.id,
        org_id=request.state.org_id
    )
    db.add(task)
    db.flush()  # Get task.id
    _save_task_assignees(db, task.id, assignee_ids)

    # Process subtasks from form
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
    _notify_new_task_assignees(db, task, user.id, set(assignee_ids))

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
    """View tasks from Notion databases with tabs for Membro A/Ana"""
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
        member_a_count = len([t for t in all_tasks if t.get("source") == "member_a"])
        member_b_count = len([t for t in all_tasks if t.get("source") == "member_b"])

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
        member_a_count = 0
        member_b_count = 0
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
        "member_a_count": member_a_count,
        "member_b_count": member_b_count,
        "total_count": member_a_count + member_b_count,
        "overdue_count": overdue_count,
        "today_count": today_count,
        "error": error_msg
    })


@router.get("/notion/new", response_class=HTMLResponse)
async def new_notion_task_form(
    request: Request,
    source: str = "member_a",
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
        source = data.pop("source", "member_a")
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

def _build_readonly_board(db, board_param, user, org_id, org_user_names, org_user_ids,
                          kanban_settings, filter_user_id):
    """Monta um quadro leve (somente leitura) para o modo multi-quadro lado a lado.

    Reaproveita a mesma resolução de colunas (org compartilhado vs. privado de uma
    pessoa) e busca de cartões do quadro interativo, mas sem o orçamento global de
    tarefas nem controles de edição — é uma visão de overview. Retorna None se o
    quadro for inacessível ao usuário atual (respeita _can_access_collaborator_board).
    """
    board_param = (board_param or "").strip()
    if board_param == "org":
        current_board = {"value": "org", "kind": "org", "user_id": None, "label": "Geral do escritório"}
        column_where = ("org_id = :org_id AND COALESCE(is_archived, FALSE) = FALSE "
                        "AND COALESCE(visibility, 'shared') = 'shared'")
        column_params = {"org_id": org_id}
    else:
        if board_param == "me":
            board_user_id = user.id
        elif board_param.isdigit():
            board_user_id = int(board_param)
        else:
            return None
        if board_user_id not in org_user_ids:
            return None
        if not _can_access_collaborator_board(user, board_user_id, kanban_settings):
            return None
        owner_name = org_user_names.get(board_user_id) or "colaborador"
        current_board = {
            "value": "me" if board_user_id == user.id else str(board_user_id),
            "kind": "me" if board_user_id == user.id else "user",
            "user_id": board_user_id,
            "label": "Meu quadro" if board_user_id == user.id else f"Quadro de {owner_name}",
        }
        column_where = ("org_id = :org_id AND COALESCE(is_archived, FALSE) = FALSE "
                        "AND COALESCE(visibility, 'shared') = 'private' AND owner_user_id = :board_user_id")
        column_params = {"org_id": org_id, "board_user_id": board_user_id}

    cols = db.execute(
        text(f"""
            SELECT id, name, slug, position, color, is_done,
                   COALESCE(visibility, 'shared') AS visibility, owner_user_id
            FROM kanban_columns
            WHERE {column_where}
            ORDER BY CASE WHEN COALESCE(visibility, 'shared') = 'shared' THEN 0 ELSE 1 END,
                     position ASC, id ASC
        """),
        column_params,
    ).fetchall()

    tasks_query = tenant_query(db, Task, org_id).filter(Task.parent_task_id.is_(None))
    tasks_query = tasks_query.filter(_visible_task_filter(user.id))
    tasks_query = tasks_query.filter(_not_archived_task_filter())  # FB2: oculta arquivados
    if filter_user_id:
        tasks_query = tasks_query.filter(_assigned_to_user_filter(filter_user_id))

    per_column = 60  # cap por coluna no overview multi-quadro
    columns_data, board_tasks = [], []
    for col in cols:
        col_status = _status_for_kanban_column(col.slug, col.is_done)
        if col.visibility == "private":
            placement_user_id = col.owner_user_id or user.id
            rows = db.execute(
                text("""
                    SELECT task_id FROM task_kanban_placements
                    WHERE org_id = :o AND user_id = :u AND column_id = :c
                    ORDER BY position ASC, task_id ASC
                """),
                {"o": org_id, "u": placement_user_id, "c": col.id},
            ).fetchall()
            ids = [r.task_id for r in rows]
            q = tasks_query.filter(Task.id.in_(ids)) if ids else tasks_query.filter(Task.id == -1)
        else:
            q = tasks_query.filter(or_(
                Task.column_id == col.id,
                (Task.column_id.is_(None)) & (Task.status == col_status),
            ))
        col_tasks = q.order_by(
            Task.position.asc(), Task.due_date.asc().nullslast(), Task.id.asc()
        ).limit(per_column).all()
        board_tasks.extend(col_tasks)
        owner_name = org_user_names.get(col.owner_user_id)
        columns_data.append({
            "id": col.id, "name": col.name, "slug": col.slug, "status": col_status,
            "color": col.color, "is_done": col.is_done, "visibility": col.visibility,
            "is_private": col.visibility == "private", "is_owner": col.owner_user_id == user.id,
            "owner_user_id": col.owner_user_id, "owner_name": owner_name,
            "can_add_cards": False, "can_manage": False,
            "visibility_label": ("Geral do escritório" if current_board["kind"] == "org" else current_board["label"]),
            "tasks": col_tasks, "hours": 0,
        })
    return {"current_board": current_board, "columns_data": columns_data, "_tasks": board_tasks}


@router.get("/kanban", response_class=HTMLResponse)
async def kanban_view(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    org_id = request.state.org_id

    _ensure_kanban_schema(db)
    _ensure_kanban_columns(db, org_id)

    org, kanban_settings = _kanban_org_settings(db, org_id)
    collab_locked = _kanban_collab_locked(kanban_settings)
    can_manage_collab = _can_manage_kanban_collab(user, kanban_settings)
    can_manage_shared = _can_manage_shared_kanban(user)
    can_view_team_private = (not collab_locked) or can_manage_collab

    # Load org users for modal assignee dropdown, board selector, and private-list owner labels.
    org_users = tenant_query(db, User, org_id).filter(User.enabled == True).order_by(User.name).all()
    org_user_names = {u.id: u.name for u in org_users}
    org_user_ids = set(org_user_names.keys())

    # Board selector: ?board=me | org | {user_id}. Legacy ?view=shared/private still maps
    # to the closest board so older links do not fall into a mixed, confusing board.
    legacy_view_mode = request.query_params.get("view", "")
    # Multi-quadro: ?boards=me,5,7 (lado a lado). Back-compat: ?board=me (único).
    _boards_raw = (request.query_params.get("boards") or request.query_params.get("board") or "").strip()
    explicit_board_selection = bool(_boards_raw)
    _board_params = [b.strip() for b in _boards_raw.split(",") if b.strip()][:6]
    if not _board_params:
        _board_params = ["org" if legacy_view_mode == "shared" else "me"]
    board_param = _board_params[0]

    board_access_denied = False
    if board_param == "org":
        current_board = {
            "value": "org",
            "kind": "org",
            "user_id": None,
            "label": "Geral do escritório",
        }
        view_mode = "shared"
    else:
        if board_param == "me":
            board_user_id = user.id
        elif board_param.isdigit():
            board_user_id = int(board_param)
        else:
            board_user_id = user.id
            board_access_denied = True

        if board_user_id not in org_user_ids:
            board_user_id = user.id
            board_access_denied = True
        if not _can_access_collaborator_board(user, board_user_id, kanban_settings):
            board_user_id = user.id
            board_access_denied = True

        board_owner_name = org_user_names.get(board_user_id) or "colaborador"
        current_board = {
            "value": "me" if board_user_id == user.id else str(board_user_id),
            "kind": "me" if board_user_id == user.id else "user",
            "user_id": board_user_id,
            "label": "Meu quadro" if board_user_id == user.id else f"Quadro de {board_owner_name}",
        }
        view_mode = "private"

    # Entrada limpa: sem parâmetro explícito, o Kanban abre no "Meu quadro".
    # Se o usuário ainda não tem coluna privada, cria a coluna mínima "Recebidas"
    # para evitar a tela enganosa "Sem colunas configuradas" quando a org já tem quadros.
    if current_board["kind"] == "me" and not explicit_board_selection:
        _ensure_private_board_column(db, org_id=org_id, user_id=user.id)
        db.commit()

    if current_board["kind"] == "org":
        column_where = (
            "org_id = :org_id AND COALESCE(is_archived, FALSE) = FALSE "
            "AND COALESCE(visibility, 'shared') = 'shared'"
        )
        column_params = {"org_id": org_id}
    else:
        column_where = (
            "org_id = :org_id AND COALESCE(is_archived, FALSE) = FALSE "
            "AND COALESCE(visibility, 'shared') = 'private' "
            "AND owner_user_id = :board_user_id"
        )
        column_params = {"org_id": org_id, "board_user_id": current_board["user_id"]}

    kanban_cols = db.execute(
        text(f"""
            SELECT id, name, slug, position, color, is_done,
                   COALESCE(visibility, 'shared') AS visibility,
                   owner_user_id
            FROM kanban_columns
            WHERE {column_where}
            ORDER BY
                CASE WHEN COALESCE(visibility, 'shared') = 'shared' THEN 0 ELSE 1 END,
                position ASC,
                id ASC
        """),
        column_params,
    ).fetchall()

    # User filter: ?user=me or ?user={id}
    user_filter = request.query_params.get("user")
    filter_user_id = None
    filter_applies_to_board = "org" in _board_params
    if user_filter == "me" and filter_applies_to_board:
        filter_user_id = user.id
    elif user_filter and user_filter.isdigit() and filter_applies_to_board:
        filter_user_id = int(user_filter)
    elif user_filter and not filter_applies_to_board:
        user_filter = ""

    tasks_query = tenant_query(db, Task, org_id).filter(Task.parent_task_id.is_(None))
    # Privacidade de tarefa (backend guard): tarefa privada só p/ criador+responsável.
    tasks_query = tasks_query.filter(_visible_task_filter(user.id))
    # FB2 (alpha UsuarioDemo): cartões arquivados somem do board (soft-archive, não delete).
    tasks_query = tasks_query.filter(_not_archived_task_filter())
    if filter_user_id:
        tasks_query = tasks_query.filter(_assigned_to_user_filter(filter_user_id))

    private_column_ids = [col.id for col in kanban_cols if col.visibility == "private"]
    if current_board["kind"] == "org":
        privately_placed_ids = [
            r.task_id for r in db.execute(
                text("SELECT task_id FROM task_kanban_placements WHERE org_id = :org_id"),
                {"org_id": org_id},
            ).fetchall()
        ]
    elif private_column_ids:
        private_placement_query = text("""
            SELECT task_id
            FROM task_kanban_placements
            WHERE org_id = :org_id AND column_id IN :column_ids
        """).bindparams(bindparam("column_ids", expanding=True))
        privately_placed_ids = [
            r.task_id for r in db.execute(
                private_placement_query,
                {"org_id": org_id, "column_ids": private_column_ids},
            ).fetchall()
        ]
    else:
        privately_placed_ids = []

    column_entries = []
    column_count = max(len(kanban_cols), 1)
    per_column_limit = max(KANBAN_TOTAL_LIMIT // column_count, 1)
    initial_task_budget = KANBAN_TOTAL_LIMIT
    for col in kanban_cols:
        col_status = _status_for_kanban_column(col.slug, col.is_done)
        col_limit = min(per_column_limit, initial_task_budget)
        if col.visibility == "private":
            placement_user_id = col.owner_user_id or user.id
            placement_rows = db.execute(
                text("""
                    SELECT task_id, position
                    FROM task_kanban_placements
                    WHERE org_id = :org_id AND user_id = :user_id AND column_id = :column_id
                    ORDER BY position ASC, task_id ASC
                """),
                {"org_id": org_id, "user_id": placement_user_id, "column_id": col.id},
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
            if privately_placed_ids:
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
        is_private = col.visibility == "private"
        is_owner = not is_private or col.owner_user_id == user.id
        owner_name = org_user_names.get(col.owner_user_id)
        if current_board["kind"] == "org":
            visibility_label = "Geral do escritório"
        elif is_private and not is_owner:
            visibility_label = f"Quadro de {owner_name}" if owner_name else "Quadro da equipe"
        elif is_private:
            visibility_label = "Meu quadro"
        else:
            visibility_label = "Compartilhada"
        columns_data.append({
            "id": col.id,
            "name": col.name,
            "slug": col.slug,
            "status": _status_for_kanban_column(col.slug, col.is_done),
            "color": col.color,
            "is_done": col.is_done,
            "visibility": col.visibility,
            "visibility_label": visibility_label,
            "is_private": is_private,
            "is_owner": is_owner,
            "owner_user_id": col.owner_user_id,
            "owner_name": owner_name,
            "can_manage": (can_manage_shared if not is_private else col.owner_user_id == user.id),
            "can_add_cards": (not is_private or col.owner_user_id == user.id),
            "tasks": col_tasks,
            "hours": round(total_h, 1) if total_h else 0,
        })

    # Clientes + processos p/ os selects de Cliente/Processo no modal (org-scoped).
    clients = tenant_query(db, Client, org_id).filter(
        or_(Client.status == None, Client.status != 'deleted')
    ).order_by(Client.first_name).all()
    cases = tenant_query(db, Case, org_id).order_by(Case.created_at.desc()).limit(300).all()

    # Multi-quadro: o primeiro é o quadro interativo (montado acima); os demais
    # são overview read-only lado a lado. Tarefas de todos entram em visible_tasks
    # para receberem responsáveis no attach abaixo.
    kanban_boards = [{
        "current_board": current_board,
        "columns_data": columns_data,
        "interactive": True,
        "access_denied": board_access_denied,
    }]
    _seen_board_values = {current_board["value"]}
    for _extra in _board_params[1:]:
        _b = _build_readonly_board(db, _extra, user, org_id, org_user_names,
                                   org_user_ids, kanban_settings, filter_user_id)
        if not _b or _b["current_board"]["value"] in _seen_board_values:
            continue
        _seen_board_values.add(_b["current_board"]["value"])
        visible_tasks.extend(_b.pop("_tasks", []))
        _b["interactive"] = False
        kanban_boards.append(_b)
    kanban_selected_boards = [b["current_board"]["value"] for b in kanban_boards]

    _attach_task_assignees(db, org_id, visible_tasks)
    assigned_user_ids = _assigned_user_ids_for_tasks(visible_tasks, db=db)
    assigned_task_users = (
        tenant_query(db, User, org_id).filter(User.id.in_(assigned_user_ids)).order_by(User.name).all()
        if assigned_user_ids
        else []
    )
    board_users = org_users if can_view_team_private else [u for u in org_users if u.id == user.id]

    return templates.TemplateResponse("app/tasks/kanban.html", {
        **get_context(request, db),
        "kanban_boards": kanban_boards,
        "kanban_selected_boards": kanban_selected_boards,
        "kanban_columns": columns_data,
        # Keep old format for backwards compat with template
        "columns": {c["slug"]: c["tasks"] for c in columns_data},
        "column_hours": {c["slug"]: c["hours"] for c in columns_data},
        "org_users": org_users,
        "clients": clients,
        "cases": cases,
        "assigned_task_users": assigned_task_users,
        "tasks_capped": tasks_capped,
        "kanban_total_limit": KANBAN_TOTAL_LIMIT,
        "filter_user_id": filter_user_id,
        "filter_user_param": user_filter or "",
        "kanban_view_mode": view_mode,
        "kanban_current_board": current_board,
        "kanban_board_access_denied": board_access_denied,
        "kanban_board_users": board_users,
        "kanban_collab_locked": collab_locked,
        "can_manage_kanban_collab": can_manage_collab,
        "shared_column_count": len([c for c in columns_data if c["visibility"] == "shared"]),
        "private_column_count": len([c for c in columns_data if c["visibility"] == "private"]),
        "can_manage_shared_kanban": can_manage_shared,
        "can_view_team_private_kanban": can_view_team_private,
    })


def _ensure_kanban_columns(db, org_id):
    """Seed default kanban columns ONLY on an org's first run.

    Guard counts ANY column ever created for the org (shared OR private,
    archived OR not). If the org has any row in kanban_columns, the seed
    never runs again — so deleting/archiving the shared 'Concluida' (or even
    every column) does NOT resurrect the 4 defaults on the next board load.
    Re-seeding is only for a genuinely new org (zero rows for this org_id).
    """
    count = db.execute(
        text("SELECT COUNT(*) FROM kanban_columns WHERE org_id = :org_id"),
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

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON invalido")
    new_status = body.get("status")
    new_position = body.get("position", 0)
    new_column_id = body.get("column_id")

    task = tenant_query(db, Task, request.state.org_id).filter(
        Task.id == task_id,
        _visible_task_filter(user.id),
    ).first()
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

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "JSON invalido"}, status_code=400)
    title = body.get("title", "").strip()
    status = body.get("status", "pending")
    column_id = body.get("column_id")
    task_visibility = _normalize_task_visibility(body.get("visibility") if "visibility" in body else ("private" if body.get("private") else "org"))
    requested_assignee_ids = _coerce_task_assignee_ids(body)
    assignee_ids = _validate_task_assignee_ids(db, request.state.org_id, requested_assignee_ids)
    if len(assignee_ids) != len(requested_assignee_ids):
        return JSONResponse({"error": "Invalid assignee"}, status_code=400)

    if not title:
        return JSONResponse({"error": "Title required"}, status_code=400)

    # Prazo opcional no quick-add (data + hora, pareados — o reloginho do card só
    # aparece quando há due_date). Hora validada como "HH:MM"; inválida => None.
    raw_due_date = (body.get("due_date") or "").strip() or None
    raw_due_time = (body.get("due_time") or "").strip()
    quick_due_date = parse_date(raw_due_date) if raw_due_date else None
    quick_due_time = raw_due_time if re.match(r"^\d{2}:\d{2}$", raw_due_time) else None

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

    if target_column and target_column.visibility == "private" and not assignee_ids:
        assignee_ids = [user.id]
    primary_assignee_id = assignee_ids[0] if assignee_ids else None
    notify_task = None

    try:
        task = Task(
            title=title,
            status=status,
            priority="medium",
            org_id=request.state.org_id,
            column_id=None if (target_column and target_column.visibility == "private") else column_id,
            assigned_to=primary_assignee_id,
            visibility=task_visibility,
            created_by=user.id,
            due_date=quick_due_date,
            due_time=quick_due_time,
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
        _save_task_assignees(db, task.id, assignee_ids)
        db.commit()
        task_id = task.id
        task_title = task.title
        task_status = task.status
        task_priority = task.priority
        notify_task = task
    except Exception as e:
        db.rollback()
        # Fallback: insert via raw SQL
        result = db.execute(
            text("""
                INSERT INTO tasks (title, status, priority, org_id, column_id, assigned_to, visibility, created_by, due_date, due_time)
                VALUES (:t, :s, :p, :o, :column_id, :assigned_to, :visibility, :created_by, :due_date, :due_time)
                RETURNING id
            """),
            {
                "t": title,
                "s": status,
                "p": "medium",
                "o": request.state.org_id,
                "column_id": None if (target_column and target_column.visibility == "private") else column_id,
                "assigned_to": primary_assignee_id,
                "visibility": task_visibility,
                "created_by": user.id,
                "due_date": quick_due_date,
                "due_time": quick_due_time,
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
        for assignee_id in assignee_ids:
            db.execute(
                text("""
                    INSERT INTO task_assignees (task_id, user_id)
                    VALUES (:task_id, :user_id)
                    ON CONFLICT DO NOTHING
                """),
                {"task_id": task_id, "user_id": assignee_id},
            )
        db.commit()
        task_title = title
        task_status = status
        task_priority = "medium"
        notify_task = tenant_query(db, Task, request.state.org_id).filter(Task.id == task_id).first()

    if notify_task:
        _notify_new_task_assignees(db, notify_task, user.id, set(assignee_ids))

    return JSONResponse({
        "success": True,
        "task": {
            "id": task_id,
            "title": task_title,
            "status": task_status,
            "priority": task_priority,
            "assigned_to_ids": assignee_ids,
        }
    })


@router.post("/api/kanban/lock")
async def update_kanban_collab_lock(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org, settings = _kanban_org_settings(db, request.state.org_id)
    if not org:
        return JSONResponse({"error": "Organization not found"}, status_code=404)
    if not _can_manage_kanban_collab(user, settings):
        return JSONResponse({"error": "Apenas administradores do Kanban podem travar quadros"}, status_code=403)

    try:
        body = await request.json()
    except Exception:
        body = {}
    current = _kanban_collab_locked(settings)
    settings[KANBAN_COLLAB_LOCK_KEY] = bool(body["locked"]) if "locked" in body else (not current)
    org.settings = settings
    flag_modified(org, "settings")
    db.commit()
    return JSONResponse({
        "success": True,
        "locked": settings[KANBAN_COLLAB_LOCK_KEY],
    })


@router.post("/api/{task_id}/send")
async def send_task_to_board(request: Request, task_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = request.state.org_id

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "JSON invalido"}, status_code=400)

    mode = str(body.get("mode") or "").strip().lower()
    if mode not in {"move", "copy"}:
        return JSONResponse({"error": "Modo invalido"}, status_code=400)
    try:
        target_user_id = int(body.get("target_user_id"))
    except (TypeError, ValueError):
        return JSONResponse({"error": "Destinatario invalido"}, status_code=400)

    target_user = tenant_query(db, User, org_id).filter(
        User.id == target_user_id,
        User.enabled == True,
    ).first()
    if not target_user:
        return JSONResponse({"error": "Destinatario invalido"}, status_code=400)

    task = tenant_query(db, Task, org_id).filter(
        Task.id == task_id,
        Task.parent_task_id.is_(None),
        _visible_task_filter(user.id),
    ).first()
    if not task:
        return JSONResponse({"error": "Task not found"}, status_code=404)

    try:
        target_column = _ensure_private_board_column(db, org_id=org_id, user_id=target_user_id)
        if not target_column:
            db.rollback()
            return JSONResponse({"error": "Falha ao preparar quadro destino"}, status_code=500)

        if mode == "move":
            task.assigned_to = target_user_id
            task.column_id = None
            _clear_all_private_placements(db, org_id=org_id, task_id=task.id)
            _upsert_private_placement(
                db,
                org_id=org_id,
                user_id=target_user_id,
                task_id=task.id,
                column_id=target_column.id,
                position=0,
            )
            result_task = task
        else:
            result_task = _clone_task_tree(
                db,
                org_id=org_id,
                source_task=task,
                target_user_id=target_user_id,
                created_by=user.id,
            )
            _upsert_private_placement(
                db,
                org_id=org_id,
                user_id=target_user_id,
                task_id=result_task.id,
                column_id=target_column.id,
                position=0,
            )
        db.commit()
    except Exception:
        db.rollback()
        return JSONResponse({"error": "Falha ao enviar tarefa"}, status_code=500)

    if target_user_id != user.id:
        try:
            from services.notifications.in_app import create_notification
            verb = "movida" if mode == "move" else "copiada"
            create_notification(
                db=db,
                user_id=target_user_id,
                title=f"Tarefa {verb} para você: {result_task.title[:120]}",
                notification_type="task_created",
                message="A tarefa foi enviada pelo Kanban.",
                severity="info",
                task_id=result_task.id,
                action_url=f"{PREFIX}/tasks/kanban?board=me",
            )
            db.commit()
        except Exception:
            db.rollback()

    return JSONResponse({
        "success": True,
        "mode": mode,
        "task_id": result_task.id,
        "target_user_id": target_user_id,
    })


# ── Kanban Column CRUD (K1-K3) ──────────────────────────────

@router.post("/api/columns")
async def create_column(request: Request, db: Session = Depends(get_db)):
    """K1: Create a new kanban column."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = request.state.org_id
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "JSON invalido"}, status_code=400)
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
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "JSON invalido"}, status_code=400)
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
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "JSON invalido"}, status_code=400)
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


@router.post("/api/{task_id}/subtask")
async def create_subtask(request: Request, task_id: int, db: Session = Depends(get_db)):
    """Create a subtask under a top-level task (Notion-style checklist item)."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # Org-scoped + privacy guard: só adiciona subtarefa a uma tarefa de topo que o
    # usuário enxerga (criador/responsável p/ privadas). Subtarefa de subtarefa: não.
    parent = tenant_query(db, Task, request.state.org_id).filter(
        Task.id == task_id,
        _visible_task_filter(user.id),
    ).first()
    if not parent or parent.parent_task_id:
        return JSONResponse({"error": "Task not found"}, status_code=404)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "JSON invalido"}, status_code=400)
    title = (body.get("title") or "").strip()
    if not title:
        return JSONResponse({"error": "Title required"}, status_code=400)

    sub = Task(
        title=title[:500],
        status="pending",
        priority="medium",
        org_id=request.state.org_id,
        parent_task_id=parent.id,
        created_by=user.id,
        visibility=parent.visibility,  # herda visibilidade do pai (privada continua privada)
    )
    db.add(sub)
    db.commit()
    return JSONResponse({"success": True, "subtask": {"id": sub.id, "title": sub.title, "status": sub.status}})


# ==========================================
# CARD ATTACHMENTS (FB3 — anexar documento no cartão Kanban, estilo Trello)
# ==========================================

def _visible_task_or_none(db, org_id, user_id, task_id):
    """Org-scoped + privacy guard: retorna a tarefa de topo visível ou None.
    Mesmo padrão de create_subtask — anexo só em tarefa que o usuário enxerga."""
    return tenant_query(db, Task, org_id).filter(
        Task.id == task_id,
        _visible_task_filter(user_id),
    ).first()


def _serialize_task_document(doc) -> dict:
    return {
        "id": doc.id,
        "name": doc.name or doc.original_filename or "documento",
        "doc_type": doc.doc_type or "other",
        "file_size": doc.file_size,
        "mime_type": doc.mime_type,
        "uploaded_by": doc.uploaded_by,
        "created_at": doc.created_at.isoformat() if getattr(doc, "created_at", None) else None,
        "download_url": f"{PREFIX}/tasks/api/{doc.task_id}/document/{doc.id}",
    }


@router.post("/api/{task_id}/document")
async def attach_task_document(
    request: Request,
    task_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Anexa um documento a um cartão Kanban (Trello-style).

    Reusa os mesmos guards do pipeline de routes.documents.upload: sanitização de
    nome (anti path-traversal), allowlist de extensão, cap de 50MB, SHA256 do
    conteúdo. Org-scoped + privacy guard via _visible_task_filter — só anexa a
    uma tarefa que o usuário enxerga; tarefa de outra org/privada → 404.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    task = _visible_task_or_none(db, request.state.org_id, user.id, task_id)
    if not task:
        return JSONResponse({"error": "Task not found"}, status_code=404)

    # --- Security: sanitize filename (prevent path traversal) ---
    safe_filename = os.path.basename(file.filename or "upload")
    safe_filename = re.sub(r'[^\w\s\-\.]', '_', safe_filename)
    if '..' in safe_filename or '/' in safe_filename or '\\' in safe_filename:
        return JSONResponse({"error": "Invalid filename"}, status_code=400)

    ext = os.path.splitext(safe_filename)[1].lower()
    if ext not in ATTACH_ALLOWED_EXTENSIONS:
        return JSONResponse({"error": f"File type '{ext}' not allowed"}, status_code=400)

    content = await file.read()
    if len(content) > ATTACH_MAX_FILE_SIZE:
        return JSONResponse({"error": "File too large (max 50MB)"}, status_code=413)
    if not content:
        return JSONResponse({"error": "Empty file"}, status_code=400)

    content_hash = hashlib.sha256(content).hexdigest()

    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
    except PermissionError:
        pass
    unique_filename = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    with open(file_path, "wb") as fh:
        fh.write(content)

    doc = Document(
        name=file.filename or safe_filename,
        original_filename=file.filename,
        doc_type="attachment",
        status="received",
        file_path=file_path,
        file_size=len(content),
        file_hash=content_hash,
        content_hash=content_hash,
        mime_type=file.content_type,
        task_id=task.id,
        client_id=task.client_id,
        case_id=task.case_id,
        uploaded_by=user.id,
        org_id=request.state.org_id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return JSONResponse({"success": True, "document": _serialize_task_document(doc)})


@router.get("/api/{task_id}/documents")
async def list_task_documents(request: Request, task_id: int, db: Session = Depends(get_db)):
    """Lista os anexos de um cartão (org-scoped + privacy guard)."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    task = _visible_task_or_none(db, request.state.org_id, user.id, task_id)
    if not task:
        return JSONResponse({"error": "Task not found"}, status_code=404)

    docs = tenant_query(db, Document, request.state.org_id).filter(
        Document.task_id == task.id
    ).order_by(Document.id.asc()).all()
    return JSONResponse({
        "success": True,
        "documents": [_serialize_task_document(d) for d in docs],
    })


@router.get("/api/{task_id}/document/{doc_id}")
async def download_task_document(request: Request, task_id: int, doc_id: int, db: Session = Depends(get_db)):
    """Baixa um anexo do cartão. Mesmo guard de path-traversal de routes.documents:
    o arquivo resolvido tem que viver dentro de UPLOAD_DIR."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    task = _visible_task_or_none(db, request.state.org_id, user.id, task_id)
    if not task:
        return JSONResponse({"error": "Task not found"}, status_code=404)

    doc = tenant_query(db, Document, request.state.org_id).filter(
        Document.id == doc_id,
        Document.task_id == task.id,
    ).first()
    if not doc or not doc.file_path or not os.path.exists(doc.file_path):
        return JSONResponse({"error": "File not found"}, status_code=404)

    resolved_path = os.path.realpath(doc.file_path)
    allowed_dir = os.path.realpath(UPLOAD_DIR)
    if not resolved_path.startswith(allowed_dir + os.sep) and resolved_path != allowed_dir:
        return JSONResponse({"error": "Access denied"}, status_code=403)

    return FileResponse(resolved_path, filename=doc.name, media_type=doc.mime_type)


@router.delete("/api/{task_id}/document/{doc_id}")
async def delete_task_document(request: Request, task_id: int, doc_id: int, db: Session = Depends(get_db)):
    """Remove um anexo do cartão sem apagar a tarefa.

    Mesmo escopo de list/download: org + privacidade do cartão. O arquivo em
    disco é removido best-effort, sempre confinado ao UPLOAD_DIR.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    task = _visible_task_or_none(db, request.state.org_id, user.id, task_id)
    if not task:
        return JSONResponse({"error": "Task not found"}, status_code=404)

    doc = tenant_query(db, Document, request.state.org_id).filter(
        Document.id == doc_id,
        Document.task_id == task.id,
    ).first()
    if not doc:
        return JSONResponse({"error": "File not found"}, status_code=404)

    file_path = doc.file_path
    db.delete(doc)
    db.commit()

    if file_path:
        resolved_path = os.path.realpath(file_path)
        allowed_dir = os.path.realpath(UPLOAD_DIR)
        if (resolved_path.startswith(allowed_dir + os.sep) or resolved_path == allowed_dir) and os.path.isfile(resolved_path):
            try:
                os.remove(resolved_path)
            except OSError:
                pass

    return JSONResponse({"success": True, "task_id": task_id, "document_id": doc_id})


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
        Task.due_date.isnot(None),
        _visible_task_filter(user.id),  # Privacy guard
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

    # Privacy guard: tarefa privada de outro usuário retorna 404 (sem vazar conteúdo).
    task = tenant_query(db, Task, request.state.org_id).filter(
        Task.id == task_id,
        _visible_task_filter(user.id),
    ).first()
    if not task:
        return JSONResponse({"error": "Task not found"}, status_code=404)

    # Build subtasks list
    subtasks = tenant_query(db, Task, request.state.org_id).filter(
        Task.parent_task_id == task_id
    ).order_by(Task.position.asc(), Task.id.asc()).all()

    # Build comments list
    comments = db.query(TaskComment).filter(TaskComment.task_id == task_id).order_by(TaskComment.created_at.asc()).all()
    assignee_ids = _load_task_assignee_ids(db, [task_id]).get(task_id, [])
    if not assignee_ids and task.assigned_to:
        assignee_ids = [task.assigned_to]

    return JSONResponse({
        "id": task.id,
        "title": task.title,
        "description": task.description or "",
        "status": task.status,
        "column_id": task.column_id,
        "position": task.position,
        "priority": task.priority or "medium",
        "assigned_to": task.assigned_to,
        "assigned_to_ids": assignee_ids,
        "assignee_name": task.assignee.name if task.assignee else None,
        "client_id": task.client_id,
        "client_name": f"{task.client.first_name} {task.client.last_name}" if task.client else None,
        "case_id": task.case_id,
        "case_name": task.case.case_number or task.case.case_name if task.case else None,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "due_time": task.due_time or None,
        "tags": task.tags or "",
        "visibility": task.visibility or "org",
        "is_private": (task.visibility == "private"),
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

    # Privacy guard: ninguém edita tarefa privada de outro usuário (404, sem vazar).
    task = tenant_query(db, Task, request.state.org_id).filter(
        Task.id == task_id,
        _visible_task_filter(user.id),
    ).first()
    if not task:
        return JSONResponse({"error": "Task not found"}, status_code=404)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "JSON invalido"}, status_code=400)

    # Capturar responsáveis anteriores ANTES de mutar para notificar só diffs reais.
    prev_assignee_ids = set(_load_task_assignee_ids(db, [task.id]).get(task.id, []))
    if not prev_assignee_ids and task.assigned_to:
        prev_assignee_ids.add(task.assigned_to)
    newly_assigned_user_ids: set[int] = set()

    if "title" in body:
        task.title = body["title"].strip()
    if "description" in body:
        task.description = body["description"].strip() if body["description"] else None
    if "priority" in body and body["priority"] in ("low", "medium", "high", "urgent"):
        task.priority = body["priority"]
    if "assigned_to_ids" in body or "assigned_to" in body:
        requested_assignee_ids = _coerce_task_assignee_ids(body)
        assignee_ids = _validate_task_assignee_ids(db, request.state.org_id, requested_assignee_ids)
        if len(assignee_ids) != len(requested_assignee_ids):
            return JSONResponse({"error": "Invalid assignee"}, status_code=400)
        task.assigned_to = assignee_ids[0] if assignee_ids else None
        _save_task_assignees(db, task.id, assignee_ids)
        newly_assigned_user_ids = set(assignee_ids) - prev_assignee_ids
    if "client_id" in body:
        # Org-scope guard (anti-IDOR): só aceita cliente da mesma org. Espelha o guard de assignee.
        new_client = int(body["client_id"]) if body["client_id"] else None
        if new_client is not None:
            if not tenant_query(db, Client, request.state.org_id).filter(Client.id == new_client).first():
                return JSONResponse({"error": "Invalid client"}, status_code=400)
        task.client_id = new_client
    if "case_id" in body:
        # Org-scope guard (anti-IDOR): só aceita processo da mesma org.
        new_case = int(body["case_id"]) if body["case_id"] else None
        if new_case is not None:
            if not tenant_query(db, Case, request.state.org_id).filter(Case.id == new_case).first():
                return JSONResponse({"error": "Invalid case"}, status_code=400)
        task.case_id = new_case
    if "due_date" in body:
        task.due_date = parse_date(body["due_date"]) if body["due_date"] else None
    if "due_time" in body:
        # Aceita "HH:MM" (input type=time). Vazio/None limpa. Valida formato p/ não corromper o badge.
        raw_time = (body["due_time"] or "").strip()
        if raw_time:
            if re.match(r"^\d{2}:\d{2}$", raw_time):
                task.due_time = raw_time
        else:
            task.due_time = None
    if "tags" in body:
        task.tags = body["tags"].strip() if body["tags"] else None
    if "visibility" in body:
        # Só pode marcar/desmarcar privada quem já enxerga (criador/responsável) — o guard
        # acima já garante isso. Ao tornar privada sem dono registrado, fixa o editor como criador.
        task.visibility = _normalize_task_visibility(body["visibility"])
        if task.visibility == "private" and not task.created_by:
            task.created_by = user.id
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

    _notify_new_task_assignees(db, task, user.id, newly_assigned_user_ids)

    return JSONResponse({"success": True, "task_id": task_id})


@router.delete("/api/{task_id}/delete")
async def delete_task_api(request: Request, task_id: int, db: Session = Depends(get_db)):
    """Item 2: excluir tarefa do Kanban via JSON. Org-scoped — só apaga tarefa da org do usuário."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # tenant_query garante filtro por org + privacy guard: tarefa de outra org ou privada de
    # outro usuário retorna None → 404 (sem vazamento cross-tenant nem cross-user).
    task = tenant_query(db, Task, request.state.org_id).filter(
        Task.id == task_id,
        _visible_task_filter(user.id),
    ).first()
    if not task:
        return JSONResponse({"error": "Task not found"}, status_code=404)

    try:
        # Limpa placements privados e subtarefas filhas antes de remover a tarefa-pai (FK self-ref).
        db.execute(
            text("DELETE FROM task_kanban_placements WHERE org_id = :org_id AND task_id = :task_id"),
            {"org_id": request.state.org_id, "task_id": task_id},
        )
        db.execute(text("DELETE FROM task_assignees WHERE task_id = :task_id"), {"task_id": task_id})
        for child in tenant_query(db, Task, request.state.org_id).filter(Task.parent_task_id == task_id).all():
            db.execute(
                text("DELETE FROM task_kanban_placements WHERE org_id = :org_id AND task_id = :task_id"),
                {"org_id": request.state.org_id, "task_id": child.id},
            )
            db.execute(text("DELETE FROM task_assignees WHERE task_id = :task_id"), {"task_id": child.id})
            db.delete(child)
        db.delete(task)
        db.commit()
    except Exception:
        db.rollback()
        return JSONResponse({"error": "Falha ao excluir tarefa"}, status_code=500)

    return JSONResponse({"success": True, "task_id": task_id})


@router.post("/api/{task_id}/archive")
async def archive_task_api(request: Request, task_id: int, db: Session = Depends(get_db)):
    """FB2 (alpha UsuarioDemo): ARQUIVAR tarefa (soft) em vez de excluir (hard delete).

    UPDATE is_archived=TRUE — a tarefa some do board mas não é apagada (reversível
    via /unarchive). Org-scoped + privacy guard: tarefa de outra org ou privada de
    outro usuário retorna 404 (sem vazamento cross-tenant nem cross-user)."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    task = tenant_query(db, Task, request.state.org_id).filter(
        Task.id == task_id,
        _visible_task_filter(user.id),
    ).first()
    if not task:
        return JSONResponse({"error": "Task not found"}, status_code=404)

    task.is_archived = True
    task.archived_at = datetime.now()
    db.commit()
    return JSONResponse({"success": True, "task_id": task_id})


@router.post("/api/{task_id}/unarchive")
async def unarchive_task_api(request: Request, task_id: int, db: Session = Depends(get_db)):
    """FB2: DESARQUIVAR tarefa — volta is_archived=FALSE (reverte /archive).
    Org-scoped + privacy guard idêntico ao archive."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    task = tenant_query(db, Task, request.state.org_id).filter(
        Task.id == task_id,
        _visible_task_filter(user.id),
    ).first()
    if not task:
        return JSONResponse({"error": "Task not found"}, status_code=404)

    task.is_archived = False
    task.archived_at = None
    db.commit()
    return JSONResponse({"success": True, "task_id": task_id})


@router.post("/api/columns/{col_id}/archive-cards")
async def archive_column_cards_api(request: Request, col_id: int, db: Session = Depends(get_db)):
    """FB2: ARQUIVAR TODOS os cartões (tarefas de topo) de uma lista de uma vez.

    Bulk UPDATE is_archived=TRUE escopado por org_id + column_id. A própria coluna
    deve ser visível ao usuário (_visible_column_where_sql) ou retorna 404 — assim
    col_id colidindo entre orgs nunca arquiva cartões de outra org (Sentinela)."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = request.state.org_id

    # A coluna precisa pertencer à org do usuário (e ser visível p/ ele). Sem isto,
    # um col_id de outra org cairia no UPDATE abaixo. Mesma checagem de delete_column.
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
        return JSONResponse({"error": "Apenas gestores podem arquivar listas compartilhadas"}, status_code=403)

    # Bulk archive org-scoped: só cartões de topo, não-arquivados, desta coluna E desta org.
    result = db.execute(
        text("""
            UPDATE tasks
            SET is_archived = TRUE, archived_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE org_id = :org_id
              AND column_id = :col_id
              AND parent_task_id IS NULL
              AND COALESCE(is_archived, FALSE) = FALSE
        """),
        {"org_id": org_id, "col_id": col_id},
    )
    db.commit()
    return JSONResponse({"success": True, "column_id": col_id, "archived": result.rowcount or 0})


@router.post("/api/{task_id}/comments/add")
async def add_task_comment_api(request: Request, task_id: int, db: Session = Depends(get_db)):
    """Add a comment to a task via JSON."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    task = tenant_query(db, Task, request.state.org_id).filter(Task.id == task_id).first()
    if not task:
        return JSONResponse({"error": "Task not found"}, status_code=404)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "JSON invalido"}, status_code=400)
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

    task = tenant_query(db, Task, request.state.org_id).filter(
        Task.id == task_id,
        _visible_task_filter(user.id),  # Privacy guard
    ).first()
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

    task = tenant_query(db, Task, request.state.org_id).filter(
        Task.id == task_id,
        _visible_task_filter(user.id),  # Privacy guard
    ).first()
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
    visibility: str = Form(None),
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
    form_data = await request.form()
    requested_assignee_ids = _coerce_task_assignee_ids(form_data)
    if not requested_assignee_ids and assigned_to:
        requested_assignee_ids = [assigned_to]
    assignee_ids = _validate_task_assignee_ids(db, request.state.org_id, requested_assignee_ids)
    if len(assignee_ids) != len(requested_assignee_ids):
        raise HTTPException(status_code=400, detail="Invalid assignee")
    assigned_to = assignee_ids[0] if assignee_ids else None

    task = tenant_query(db, Task, request.state.org_id).filter(
        Task.id == task_id,
        _visible_task_filter(user.id),  # Privacy guard
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    previous_assignees = set(_load_task_assignee_ids(db, [task.id]).get(task.id, []))
    if not previous_assignees and task.assigned_to:
        previous_assignees.add(task.assigned_to)

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
    if visibility is not None:
        task.visibility = _normalize_task_visibility(visibility)
        if task.visibility == "private" and not task.created_by:
            task.created_by = user.id

    _save_task_assignees(db, task.id, assignee_ids)
    db.commit()
    _notify_new_task_assignees(db, task, user.id, set(assignee_ids) - previous_assignees)

    # Process subtasks from form
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

    task = tenant_query(db, Task, request.state.org_id).filter(
        Task.id == task_id,
        _visible_task_filter(user.id),  # Privacy guard
    ).first()
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

    task = tenant_query(db, Task, request.state.org_id).filter(
        Task.id == task_id,
        _visible_task_filter(user.id),  # Privacy guard
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    db.execute(text("DELETE FROM task_assignees WHERE task_id = :task_id"), {"task_id": task_id})
    db.delete(task)
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/tasks", status_code=302)
