"""
CaseHub - Calendar Routes
Enhanced calendar with tasks, events, and better visualization
"""
from datetime import datetime, date, timedelta
from typing import Optional
import logging
import os
from pathlib import Path
import re
import uuid

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, text, bindparam

from models import get_db, Client, Case, Task, User
from auth import get_current_user
from models.tenant import tenant_query
from i18n import get_translations
from core.template_config import templates, PREFIX
from services.google_calendar import GoogleCalendarService

router = APIRouter(prefix="/calendar", tags=["calendar"])

UPLOADS_ROOT = Path(os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")).resolve()
APPOINTMENT_ATTACHMENT_KIND = "appointment_attachments"
MAX_APPOINTMENT_ATTACHMENT_SIZE = 25 * 1024 * 1024
APPOINTMENT_ATTACHMENT_EXT = {
    ".jpg": "image", ".jpeg": "image", ".png": "image", ".gif": "image", ".webp": "image",
    ".pdf": "file", ".doc": "file", ".docx": "file", ".xls": "file", ".xlsx": "file",
    ".ppt": "file", ".pptx": "file", ".txt": "file", ".csv": "file", ".zip": "file",
}
APPOINTMENT_ATTACHMENT_DOC_MIME = {
    "application/pdf", "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain", "text/csv", "application/zip",
}


@router.post("/gcal-webhook")
async def gcal_webhook(request: Request, db: Session = Depends(get_db)):
    """Receiver PÚBLICO para notificações push do Google Calendar (events.watch).

    DORMANTE atrás de GOOGLE_CALENDAR_WATCH_ENABLED (default OFF). O polling
    (import_all_connected) é o fallback permanente.

    Contrato de segurança (auditável pelo Sentinela):
      - Endpoint PÚBLICO/UNTRUSTED: o Google posta aqui SEM cookie de auth e
        SEM subdomínio de tenant (a TenantMiddleware isenta este path).
      - Flag OFF -> 200 no-op imediato (seguro para deploy agora).
      - NUNCA confiamos no corpo da requisição para dados: o ping não carrega
        evento; puxamos os deltas autoritativos via API autenticada.
      - Validamos X-Goog-Channel-Token contra o hash armazenado (compare_digest,
        constant-time). Canal desconhecido / token inválido -> 200 silencioso,
        sem processar, sem vazar quais canais existem.
      - Org-scoped: a org/conta vêm do REGISTRO do canal, não do request.
      - Dedupe por X-Goog-Message-Number por canal (ignora replays/out-of-order).
      - Sempre 200 rápido; o import é best-effort (erros engolidos + log) para o
        Google não entrar em retry-storm e não vazar erro interno.
    """
    # Always-200 contract: Google must receive 200 even when the push path is
    # off or the channel is unknown. We read headers (never the body) and only
    # act when the flag is ON and the channel validates.
    ok = JSONResponse({"ok": True}, status_code=200)

    # 1. Flag OFF -> 200 no-op. No DB read, no body parse.
    if not GoogleCalendarService.watch_enabled():
        return ok

    channel_id = request.headers.get("X-Goog-Channel-ID", "")
    resource_state = request.headers.get("X-Goog-Resource-State", "")
    presented_token = request.headers.get("X-Goog-Channel-Token", "")
    message_number_raw = request.headers.get("X-Goog-Message-Number", "")

    if not channel_id:
        return ok  # malformed ping; never leak

    # 2. Validate the channel + token (constant-time). Unknown/invalid -> 200
    #    silently, WITHOUT processing and WITHOUT leaking channel existence.
    try:
        service = GoogleCalendarService(db)
        channel = service.find_channel(channel_id)
    except Exception as exc:  # noqa: BLE001 — best-effort, never 500 to Google
        logger.warning("gcal-webhook channel lookup failed: %s", type(exc).__name__)
        return ok
    if not channel:
        return ok
    if not GoogleCalendarService.validate_channel_token(channel, presented_token):
        # Token mismatch on a known channel: refuse to process, stay silent.
        logger.warning("gcal-webhook token mismatch channel=%s", channel_id[:24])
        return ok

    org_id = channel.get("org_id")
    account_name = channel.get("account_name")
    if not org_id or not account_name:
        return ok

    # 3. Handshake (sync) -> 200 no-op. Google sends this once at registration.
    if resource_state == "sync":
        return ok

    # 4. Only 'exists'/'change' notifications trigger a pull. Anything else
    #    (e.g. 'not_exists') is ignored.
    if resource_state not in ("exists", "change"):
        return ok

    # 5. Dedupe on X-Goog-Message-Number per channel (replay/out-of-order).
    try:
        message_number = int(message_number_raw)
    except (TypeError, ValueError):
        message_number = 0
    if message_number:
        try:
            is_new = service.mark_channel_message(channel["id"], message_number)
        except Exception:  # noqa: BLE001
            is_new = False
        if not is_new:
            return ok  # replay or out-of-order -> ignore

    # 6. Pull authoritative deltas for THAT org/account only. Best-effort: a
    #    fresh org-scoped service is built so org_id is never taken from the
    #    request. Errors are swallowed + logged so Google does not retry-storm.
    try:
        GoogleCalendarService(db, org_id=int(org_id)).import_events(account_name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("gcal-webhook import best-effort failed org=%s: %s",
                       org_id, type(exc).__name__)

    return ok


@router.get("/google_settings")
async def legacy_google_calendar_settings_redirect():
    """Keep old Google settings URL from becoming a 404."""
    return RedirectResponse(url=f"{PREFIX}/google-calendar/settings", status_code=302)


def get_context(request: Request, db: Session, **kwargs):
    """Build template context."""
    lang = request.cookies.get("lang", "en")
    user = get_current_user(request, db)
    return {
        "request": request,
        "PREFIX": PREFIX,
        "lang": lang,
        "t": get_translations(lang),
        "user": user,
        **kwargs
    }


def _ensure_appointment_feedback_schema(db: Session) -> None:
    """Additive alpha-safe columns for Trello-like appointment details."""
    bind = db.get_bind()
    dialect = bind.dialect.name if bind is not None else "sqlite"
    id_type = "SERIAL PRIMARY KEY" if dialect == "postgresql" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    additions = [
        ("appointments", "checklist", "TEXT"),
        ("appointments", "attachments", "TEXT"),
    ]
    db.execute(text(f"""
        CREATE TABLE IF NOT EXISTS appointment_attachments (
            id {id_type},
            org_id INTEGER NOT NULL,
            appointment_id INTEGER NOT NULL,
            file_path VARCHAR(255) NOT NULL,
            filename VARCHAR(255) NOT NULL,
            mime_type VARCHAR(120),
            size_bytes INTEGER,
            uploaded_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_appointment_attachments_org_appt ON appointment_attachments(org_id, appointment_id)"))
    db.commit()
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
                # Incident 2026-07-01 (prod outage, `users` table locked ~22min
                # — see core.app_factory._alter_table_add_column_bounded for
                # the full writeup): this is the same lazy ALTER TABLE
                # pattern, called on every request. Bound the lock wait so a
                # busy `appointments` table can't queue this ALTER (and
                # everything behind it) indefinitely.
                if dialect == "postgresql":
                    db.execute(text("SET LOCAL lock_timeout = '3s'"))
                db.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
                db.commit()
        except Exception:
            db.rollback()


def _load_appointment_attachment_files(db: Session, org_id: int, appointment_ids: list[int]) -> dict[int, list[dict]]:
    if not appointment_ids:
        return {}
    try:
        rows = db.execute(
            text("""
                SELECT id, appointment_id, file_path, filename
                FROM appointment_attachments
                WHERE org_id = :org_id AND appointment_id IN :ids
                ORDER BY created_at ASC, id ASC
            """).bindparams(bindparam("ids", expanding=True)),
            {"org_id": org_id, "ids": appointment_ids},
        ).fetchall()
    except Exception as exc:  # pragma: no cover - defensive for pre-migration DBs
        logger.warning("Appointment attachment lookup failed: %s", exc)
        return {}
    files: dict[int, list[dict]] = {}
    for row in rows:
        stored = os.path.basename(row.file_path or "")
        if not stored:
            continue
        files.setdefault(row.appointment_id, []).append({
            "id": row.id,
            "name": row.filename or stored,
            "url": f"/uploads/{APPOINTMENT_ATTACHMENT_KIND}/{stored}",
        })
    return files


def _load_appointment_for_sync(db: Session, org_id: int, appt_id: int) -> Optional[dict]:
    # `origin` may not exist on very old alpha DBs; COALESCE via a guarded
    # select keeps this working before _ensure_sync_schema has run once.
    try:
        row = db.execute(
            text("""
                SELECT id, title, type, client_name, date, time_start, time_end,
                       is_virtual, notes, local, pericia_status, gcal_event_id,
                       google_calendar_id, google_calendar_account,
                       COALESCE(origin, 'casehub') AS origin
                FROM appointments
                WHERE id = :id AND org_id = :org_id
            """),
            {"id": appt_id, "org_id": org_id},
        ).fetchone()
    except Exception:
        db.rollback()
        row = db.execute(
            text("""
                SELECT id, title, type, client_name, date, time_start, time_end,
                       is_virtual, notes, gcal_event_id
                FROM appointments
                WHERE id = :id AND org_id = :org_id
            """),
            {"id": appt_id, "org_id": org_id},
        ).fetchone()
    return dict(row._mapping) if row else None


def _time_to_minutes(value) -> Optional[int]:
    if value in (None, ""):
        return None
    if hasattr(value, "hour") and hasattr(value, "minute"):
        return int(value.hour) * 60 + int(value.minute)
    try:
        parsed = datetime.strptime(str(value)[:5], "%H:%M").time()
    except (TypeError, ValueError):
        return None
    return parsed.hour * 60 + parsed.minute


def _appointment_conflicts(
    db: Session,
    org_id: int,
    appt_date,
    time_start,
    time_end,
    assigned_to,
    exclude_id: Optional[int] = None,
) -> list[dict]:
    if not assigned_to or not appt_date:
        return []
    try:
        assigned_to_int = int(assigned_to)
    except (TypeError, ValueError):
        return []
    start_min = _time_to_minutes(time_start)
    if start_min is None:
        return []
    end_min = _time_to_minutes(time_end)
    if end_min is None or end_min <= start_min:
        end_min = start_min + 60

    params = {"org_id": org_id, "date": appt_date, "assigned_to": assigned_to_int}
    exclude_sql = ""
    if exclude_id is not None:
        params["exclude_id"] = exclude_id
        exclude_sql = "AND id != :exclude_id"

    rows = db.execute(
        text(f"""
            SELECT id, title, client_name, time_start, time_end
            FROM appointments
            WHERE org_id = :org_id
              AND date = :date
              AND assigned_to = :assigned_to
              AND time_start IS NOT NULL
              {exclude_sql}
            ORDER BY time_start NULLS LAST, id
        """),
        params,
    ).fetchall()
    conflicts = []
    for row in rows:
        existing_start = _time_to_minutes(row.time_start)
        if existing_start is None:
            continue
        existing_end = _time_to_minutes(row.time_end)
        if existing_end is None or existing_end <= existing_start:
            existing_end = existing_start + 60
        if start_min < existing_end and end_min > existing_start:
            conflicts.append({
                "id": row.id,
                "title": row.title,
                "client_name": row.client_name or "",
                "time_start": row.time_start.strftime("%H:%M") if row.time_start else "",
                "time_end": row.time_end.strftime("%H:%M") if row.time_end else "",
            })
    return conflicts


def _sync_google_appointment(db: Session, org_id: int, appt_id: int) -> dict:
    appointment = _load_appointment_for_sync(db, org_id, appt_id)
    if not appointment:
        return {"synced": False, "code": "appointment_not_found", "message": ""}

    # Anti-loop (c): compromissos importados do Google (origin='google') NUNCA
    # são reempurrados pro Google — isso geraria eco/duplicata. O dono dessa
    # direção é o próprio Google; aqui só mantemos a cópia local.
    if (appointment.get("origin") or "casehub") == "google":
        return {"synced": False, "code": "origin_google_skip_push", "message": ""}

    try:
        result = GoogleCalendarService(db, org_id=org_id).sync_appointment(appointment)
    except Exception as exc:
        logger.warning("Google Calendar sync skipped for appointment %s: %s", appt_id, exc)
        return {
            "synced": False,
            "code": "google_calendar_unavailable",
            "message": "Compromisso salvo localmente; Google Calendar nao esta conectado.",
        }
    event_id = result.get("event_id")
    if result.get("synced") and event_id:
        db.execute(
            text("""
                UPDATE appointments
                SET gcal_event_id = :event_id,
                    google_calendar_id = :calendar_id,
                    google_calendar_account = :account,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id AND org_id = :org_id
            """),
            {
                "event_id": event_id,
                "calendar_id": result.get("calendar_id"),
                "account": result.get("account"),
                "id": appt_id,
                "org_id": org_id,
            },
        )
        db.commit()
    return result


def _local_only_calendar_status() -> dict:
    return {
        "synced": False,
        "code": "local_only",
        "message": "Compromisso salvo na agenda local do CaseHub.",
    }


def _wants_google_sync(body: dict) -> bool:
    """Decide se devemos propagar pro Google Calendar.

    Bug UsuarioDemo 02/06: compromissos salvavam na DB mas nunca refletiam no Google
    Agenda porque o front nunca enviava `sync_google`, e o backend só
    sincronizava quando esse flag era verdadeiro. Agora o default e SINCRONIZAR
    (push pro Google) sempre que houver conta conectada; o front so precisa
    enviar `sync_google: false` se quiser explicitamente manter local-only.
    O sync em si e best-effort: GoogleCalendarService trata token expirado
    (refresh), conta ausente e falhas de API sem quebrar o save local.
    """
    value = body.get("sync_google", True)
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "0", "no", "off", ""}
    return bool(value)


def _parse_iso_date_param(value: Optional[str]):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _optional_int(value, field: str):
    if value in (None, "", 0, "0"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} invalido")


def _coerce_assigned_to_ids(body: dict) -> list[int]:
    raw = body.get("assigned_to_ids")
    if raw is None:
        raw = body.get("assigned_to")
    if raw in (None, "", 0, "0"):
        return []
    if not isinstance(raw, list):
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


_APPOINTMENT_OUTCOMES = {"cancelado", "contrato_fechado", "follow_up", "sem_direito", ""}
_LEGACY_OUTCOME_ALIASES = {"no_show": "follow_up"}


def _normalize_appointment_outcome(value) -> str:
    if not isinstance(value, str):
        return ""
    outcome = value.strip()
    outcome = _LEGACY_OUTCOME_ALIASES.get(outcome, outcome)
    if outcome not in _APPOINTMENT_OUTCOMES:
        return ""
    return outcome


def _validate_org_user_ids(db: Session, org_id: int, user_ids: list[int]) -> list[int]:
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


def _load_appointment_assignee_ids(db: Session, appt_ids: list[int]) -> dict:
    if not appt_ids:
        return {}
    try:
        rows = db.execute(
            text("""
                SELECT appointment_id, user_id
                FROM appointment_assignees
                WHERE appointment_id IN :ids
                ORDER BY appointment_id
            """).bindparams(bindparam("ids", expanding=True)),
            {"ids": appt_ids},
        ).fetchall()
    except Exception:
        db.rollback()
        return {}

    by_appt: dict = {}
    for row in rows:
        by_appt.setdefault(row.appointment_id, []).append(row.user_id)
    return by_appt


def _load_appointment_assignees(db: Session, org_id: int, assignee_ids_by_appt: dict) -> dict:
    user_ids = sorted({uid for ids in assignee_ids_by_appt.values() for uid in ids if uid})
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
        initials = "".join(part[:1].upper() for part in parts[:2]) or "?"
        users[row.id] = {
            "id": row.id,
            "name": row.name or "",
            "short_name": parts[0] if parts else (row.name or ""),
            "initials": initials,
            "color": row.color or "#1C2447",
            "photo_url": row.photo_url or "",
        }
    return {
        appt_id: [users[uid] for uid in user_ids if uid in users]
        for appt_id, user_ids in assignee_ids_by_appt.items()
    }


def _save_appointment_assignees(db: Session, appt_id: int, user_ids: list[int]) -> None:
    try:
        db.execute(
            text("DELETE FROM appointment_assignees WHERE appointment_id = :appt_id"),
            {"appt_id": appt_id},
        )
        for user_id in user_ids:
            db.execute(
                text("""
                    INSERT INTO appointment_assignees (appointment_id, user_id)
                    VALUES (:appt_id, :user_id)
                    ON CONFLICT DO NOTHING
                """),
                {"appt_id": appt_id, "user_id": user_id},
            )
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Could not persist multi-assignees for appointment %s", appt_id)


def _notify_new_appointment_assignees(
    db: Session,
    org_id: int,
    actor_id: int,
    assignee_ids: set[int],
    title: str,
    appt_date: str,
    time_start: str,
) -> None:
    notify_ids = [uid for uid in sorted(assignee_ids) if uid and uid != actor_id]
    if not notify_ids:
        return
    try:
        from routes.team_messages import post_system_dm_to_user
        title = str(title or "compromisso").strip()[:160]
        when = str(appt_date or "").strip()
        start = str(time_start or "").strip()[:5]
        if start:
            when = f"{when} {start}".strip()
        when_label = f" em {when}" if when else ""
        body = f"Agenda: você foi designado(a) para \"{title}\"{when_label}."
        for user_id in notify_ids:
            post_system_dm_to_user(db, org_id, user_id, body)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


def _linked_row_exists(db: Session, table: str, org_id: int, row_id: int) -> bool:
    allowed = {
        "cases": "cases",
        "prazos_processuais": "prazos_processuais",
        "tasks": "tasks",
    }
    table_name = allowed[table]
    return bool(db.execute(
        text(f"SELECT 1 FROM {table_name} WHERE id = :id AND org_id = :org_id"),
        {"id": row_id, "org_id": org_id},
    ).first())


@router.get("", response_class=HTMLResponse)
async def calendar_view(request: Request):
    """Rota legada da aba Agenda.

    03/06 (UsuarioDemo): a aba "Agenda" da navegação levava a /calendar (esta rota)
    em vez de /calendar/agenda, que é a rota canônica da tela (lista +
    calendário, seletor de visualização, modal de novo compromisso). A nav
    agora aponta direto para /calendar/agenda; mantemos esta rota como um
    redirect server-side 302 para que qualquer link/bookmark antigo para
    /calendar (e GET /calendar/) caia na mesma tela canônica, preservando
    a query string (ex.: ?week=, ?appt=, ?new=).
    """
    query = request.url.query
    target = f"{PREFIX}/calendar/agenda"
    if query:
        target = f"{target}?{query}"
    return RedirectResponse(url=target, status_code=302)


@router.get("/events")
async def get_events(
    request: Request,
    start: Optional[str] = None,
    end: Optional[str] = None,
    filter_type: Optional[str] = None,
    user_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get calendar events (cases and tasks)."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    _ensure_appointment_feedback_schema(db)
    events = []

    # Parse date range
    try:
        start_date = datetime.fromisoformat(start.replace('Z', '')).date() if start else date.today() - timedelta(days=30)
        end_date = datetime.fromisoformat(end.replace('Z', '')).date() if end else date.today() + timedelta(days=60)
    except (ValueError, AttributeError):
        start_date = date.today() - timedelta(days=30)
        end_date = date.today() + timedelta(days=60)

    # Get case events
    if not filter_type or filter_type in ['all', 'cases']:
        cases = tenant_query(db, Case, request.state.org_id).all()

        # Batch the per-case client lookup that ran inside the loop (N+1).
        case_client_ids = {c.client_id for c in cases if c.client_id}
        case_clients_by_id = {
            cl.id: cl
            for cl in tenant_query(db, Client, request.state.org_id)
            .filter(Client.id.in_(case_client_ids)).all()
        } if case_client_ids else {}

        for case in cases:
            client = case_clients_by_id.get(case.client_id)
            client_name = f"{client.first_name} {client.last_name}" if client else "Unknown"

            # Filing date
            if case.filing_date:
                events.append({
                    "id": f"case_{case.id}_filed",
                    "title": f"Filed: {client_name} - {case.visa_type or 'Case'}",
                    "start": case.filing_date.isoformat(),
                    "color": "#0d6efd",
                    "url": f"{PREFIX}/cases/{case.id}",
                    "extendedProps": {
                        "type": "case",
                        "subtype": "filing",
                        "caseId": case.id
                    }
                })

            # Expiration date
            if case.expiration_date:
                events.append({
                    "id": f"case_{case.id}_exp",
                    "title": f"Expires: {client_name}",
                    "start": case.expiration_date.isoformat(),
                    "color": "#dc3545",
                    "url": f"{PREFIX}/cases/{case.id}",
                    "extendedProps": {
                        "type": "case",
                        "subtype": "expiration",
                        "caseId": case.id
                    }
                })

            # Priority date
            if case.priority_date:
                events.append({
                    "id": f"case_{case.id}_priority",
                    "title": f"Priority: {client_name}",
                    "start": case.priority_date.isoformat(),
                    "color": "#198754",
                    "url": f"{PREFIX}/cases/{case.id}",
                    "extendedProps": {
                        "type": "case",
                        "subtype": "priority",
                        "caseId": case.id
                    }
                })

    # Get task events
    if not filter_type or filter_type in ['all', 'tasks']:
        task_query = tenant_query(db, Task, request.state.org_id).filter(Task.due_date.isnot(None))

        if user_id:
            task_query = task_query.filter(Task.assigned_to == user_id)

        tasks = task_query.all()

        # Batch the per-task case + client lookups that ran inside the loop
        # (two N+1s). Fetch only the cases actually referenced by tasks, then
        # only the clients those cases reference.
        task_case_ids = {t.case_id for t in tasks if t.case_id}
        task_cases_by_id = {
            c.id: c
            for c in tenant_query(db, Case, request.state.org_id)
            .filter(Case.id.in_(task_case_ids)).all()
        } if task_case_ids else {}
        task_client_ids = {c.client_id for c in task_cases_by_id.values() if c.client_id}
        task_clients_by_id = {
            cl.id: cl
            for cl in tenant_query(db, Client, request.state.org_id)
            .filter(Client.id.in_(task_client_ids)).all()
        } if task_client_ids else {}

        for task in tasks:
            # Determine color based on status and priority
            if task.status == "completed":
                color = "#6c757d"
            elif task.priority == "urgent":
                color = "#dc3545"
            elif task.priority == "high":
                color = "#ffc107"
            else:
                color = "#17a2b8"

            # Get case info if available (dict lookups; batched above)
            case_info = ""
            if task.case_id:
                case = task_cases_by_id.get(task.case_id)
                if case:
                    client = task_clients_by_id.get(case.client_id)
                    if client:
                        case_info = f" ({client.first_name} {client.last_name})"

            events.append({
                "id": f"task_{task.id}",
                "title": f"Task: {task.title}{case_info}",
                "start": task.due_date.isoformat(),
                "color": color,
                "url": f"{PREFIX}/tasks/{task.id}",
                "extendedProps": {
                    "type": "task",
                    "priority": task.priority,
                    "status": task.status,
                    "taskId": task.id
                }
            })

    # AG3: Include appointments in calendar events
    if not filter_type or filter_type in ['all', 'appointments']:
        try:
            appts = db.execute(
                text("""
                    SELECT a.*, u.name as user_name, u.color as user_color, u.photo_url as user_photo_url
                    FROM appointments a
                    LEFT JOIN users u ON a.assigned_to = u.id
                    WHERE a.org_id = :org_id AND a.date BETWEEN :start AND :end
                    ORDER BY a.date, a.time_start
                """),
                {"org_id": request.state.org_id, "start": start_date, "end": end_date},
            ).fetchall()
            appt_ids = [a.id for a in appts]
            evt_assignee_ids = _load_appointment_assignee_ids(db, appt_ids)
            evt_attachment_files = _load_appointment_attachment_files(db, request.state.org_id, appt_ids)
            for appt in appts:
                evt_start = appt.date.isoformat()
                evt_end = appt.date.isoformat()
                if appt.time_start:
                    evt_start = f"{appt.date.isoformat()}T{appt.time_start.strftime('%H:%M:%S')}"
                if appt.time_end:
                    evt_end = f"{appt.date.isoformat()}T{appt.time_end.strftime('%H:%M:%S')}"
                color = appt.user_color or '#1C2447'
                events.append({
                    "id": appt.id,
                    "title": f"{appt.title}" + (f" ({appt.client_name})" if appt.client_name else ""),
                    "start": evt_start,
                    "end": evt_end,
                    "color": color,
                    # Deep-link pro editor do compromisso na visão lista (29/05 Equipe CaseHub:
                    # clicar num compromisso no grid abria href="#" e só dava refresh).
                    "url": f"{PREFIX}/calendar/agenda?appt={appt.id}",
                    # extendedProps carrega os campos crus do compromisso p/ a Visão
                    # do Dia (timeline) reconstruir o bloco e reabrir o editor existente
                    # (openEditAppt) sem precisar de um endpoint novo — 03/06 UsuarioDemo.
                    "extendedProps": {
                        "type": "appointment",
                        "title": appt.title or "",
                        "apptType": appt.type,
                        "date": appt.date.isoformat(),
                        "timeStart": appt.time_start.strftime('%H:%M') if appt.time_start else "",
                        "timeEnd": appt.time_end.strftime('%H:%M') if appt.time_end else "",
                        "assignedTo": appt.assigned_to or "",
                        "assignedToIds": evt_assignee_ids.get(appt.id) or ([appt.assigned_to] if appt.assigned_to else []),
                        "clientName": appt.client_name or "",
                        "notes": appt.notes or "",
                        "checklist": getattr(appt, "checklist", "") or "",
                        "attachments": getattr(appt, "attachments", "") or "",
                        "attachmentFiles": evt_attachment_files.get(appt.id, []),
                        "local": appt.local or "",
                        "periciaStatus": appt.pericia_status or "",
                        "isVirtual": "1" if appt.is_virtual else "0",
                        "outcome": (getattr(appt, "outcome", "") or ""),
                        "title": appt.title or "",
                        "userName": appt.user_name or "",
                        "userColor": appt.user_color or "",
                        "userPhotoUrl": appt.user_photo_url or "",
                    },
                })
        except Exception as e:
            logger.warning("Could not load appointments for calendar: %s", e)

    return JSONResponse(events)


@router.get("/today")
async def today_events(request: Request, db: Session = Depends(get_db)):
    """Get today's events summary."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    today = date.today()

    # Tasks due today
    tasks_today = tenant_query(db, Task, request.state.org_id).filter(
        Task.due_date == today,
        Task.status != "completed"
    ).all()

    # Cases expiring today
    expiring_today = tenant_query(db, Case, request.state.org_id).filter(Case.expiration_date == today).all()

    # Tasks overdue
    overdue = tenant_query(db, Task, request.state.org_id).filter(
        Task.due_date < today,
        Task.status != "completed"
    ).count()

    return JSONResponse({
        "tasks_due": len(tasks_today),
        "expiring_cases": len(expiring_today),
        "overdue_tasks": overdue,
        "tasks": [{"id": t.id, "title": t.title, "priority": t.priority} for t in tasks_today],
        "cases": [{"id": c.id, "name": c.case_name or c.case_number} for c in expiring_today]
    })


@router.get("/upcoming")
async def upcoming_events(request: Request, days: int = 7, db: Session = Depends(get_db)):
    """Get upcoming events for the next N days."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    today = date.today()
    end_date = today + timedelta(days=days)

    # Tasks
    tasks = tenant_query(db, Task, request.state.org_id).filter(
        Task.due_date >= today,
        Task.due_date <= end_date,
        Task.status != "completed"
    ).order_by(Task.due_date).all()

    # Cases expiring
    expiring = tenant_query(db, Case, request.state.org_id).filter(
        Case.expiration_date >= today,
        Case.expiration_date <= end_date
    ).order_by(Case.expiration_date).all()

    return JSONResponse({
        "tasks": [{
            "id": t.id,
            "title": t.title,
            "due_date": t.due_date.isoformat(),
            "priority": t.priority,
            "days_until": (t.due_date - today).days
        } for t in tasks],
        "expiring_cases": [{
            "id": c.id,
            "name": c.case_name or c.case_number,
            "expiration_date": c.expiration_date.isoformat(),
            "days_until": (c.expiration_date - today).days
        } for c in expiring]
    })


@router.post("/quick-task")
async def quick_add_task(
    request: Request,
    title: str = Form(...),
    due_date: str = Form(...),
    priority: str = Form("medium"),
    case_id: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    """Quick add task from calendar."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        due = datetime.strptime(due_date, "%Y-%m-%d").date()
    except Exception as e:
        logger.error("Failed to parse due_date '%s': %s", due_date, e)
        raise HTTPException(status_code=400, detail="Invalid date format")

    task = Task(
        title=title,
        due_date=due,
        priority=priority,
        case_id=case_id,
        status="pending",
        assigned_to=user.id,
        org_id=request.state.org_id)
    db.add(task)
    db.commit()

    return JSONResponse({
        "success": True,
        "task_id": task.id,
        "message": "Task created successfully"
    })


@router.post("/sync-google")
def sync_google_now(request: Request, db: Session = Depends(get_db)):
    """Botão "Sincronizar agora": two-way manual sync sob demanda.

    Importa eventos novos/alterados/cancelados das contas Google conectadas
    desta org para a tabela appointments (origin='google', anti-loop) e depois
    exporta compromissos locais ainda sem gcal_event_id. O push normal
    CaseHub → Google continua acontecendo no save/update/delete dos novos
    compromissos. Best-effort: retorna resumo (200) mesmo se uma conta falhar;
    não derruba a página.

    Webhook events.watch (push em tempo real) existe como caminho DORMANTE em
    POST /calendar/gcal-webhook, atrás da flag GOOGLE_CALENDAR_WATCH_ENABLED
    (default OFF). Este pull manual permanece o fallback permanente.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)
    org_id = request.state.org_id
    try:
        service = GoogleCalendarService(db, org_id=org_id)
        result = service.import_all_connected()
        priority_start = _parse_iso_date_param(request.query_params.get("start_date"))
        priority_end = _parse_iso_date_param(request.query_params.get("end_date"))
        export_result = service.export_unsynced_appointments(
            priority_start_date=priority_start,
            priority_end_date=priority_end,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Manual Google sync failed org=%s: %s", org_id, exc)
        return JSONResponse(
            {"success": False, "code": "google_sync_failed",
             "message": "Nao foi possivel sincronizar com o Google Calendar agora."},
            status_code=200,
        )
    connected = bool(result.get("accounts") or export_result.get("account"))
    imported = result.get("imported", 0)
    updated = result.get("updated", 0)
    cancelled = result.get("cancelled", 0)
    exported = export_result.get("exported", 0)
    failed = export_result.get("failed", 0)
    candidates = export_result.get("candidates", 0)
    pending = max(candidates - exported, 0)
    any_change = any((imported, updated, cancelled, exported))
    message = "Google Calendar nao esta conectado."
    if connected:
        message = (
            f"Sincronizado: {imported} novo(s), "
            f"{updated} atualizado(s), "
            f"{cancelled} removido(s), "
            f"{exported} enviado(s) ao Google."
        )
        if not any_change and not pending:
            message += " (nenhuma mudança desde a última sincronização)"
        if pending:
            message += f" {pending} compromisso(s) ainda pendente(s)."
    return JSONResponse({
        "success": True,
        "connected": connected,
        "imported": imported,
        "updated": updated,
        "cancelled": cancelled,
        "exported": exported,
        "export_failed": failed,
        "export_candidates": candidates,
        "export_processed": export_result.get("processed", 0),
        "export_pending": pending,
        "message": message,
    })


# ── Appointments (Agenda VS) ───────────────────────────────────

@router.get("/agenda", response_class=HTMLResponse)
async def agenda_lista_view(request: Request, db: Session = Depends(get_db)):
    """A1: Vista vertical estilo Trello para compromissos da semana."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    _ensure_appointment_feedback_schema(db)
    org_id = request.state.org_id

    # Pull incremental Google → CaseHub ANTES de renderizar, org-scoped e
    # best-effort: importa eventos novos/alterados/cancelados do Google para a
    # tabela appointments para que apareçam na lista + calendário + timeline
    # como compromissos normais. Qualquer falha (token, rede, API) é engolida —
    # a agenda nunca quebra por causa do sync. Push CaseHub→Google permanece
    # intacto (sync_appointment no save/update/delete).
    try:
        GoogleCalendarService(db, org_id=org_id).import_all_connected()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Google pull (agenda load) skipped org=%s: %s", org_id, exc)

    # Get current week range
    today = date.today()
    weekday = today.weekday()  # 0=Mon
    week_start = today - timedelta(days=weekday)
    week_end = week_start + timedelta(days=4)  # Fri

    # Query week param
    try:
        week_offset = int(request.query_params.get("week", 0))
    except (ValueError, TypeError):
        week_offset = 0
    week_start += timedelta(weeks=week_offset)
    week_end = week_start + timedelta(days=4)

    # Load appointments
    appointments = db.execute(
        text("""
            SELECT a.*, u.name as user_name, u.color as user_color, u.photo_url as user_photo_url
            FROM appointments a
            LEFT JOIN users u ON a.assigned_to = u.id
            WHERE a.org_id = :org_id AND a.date BETWEEN :start AND :end
            ORDER BY a.date, a.time_start NULLS LAST
        """),
        {"org_id": org_id, "start": week_start, "end": week_end},
    ).fetchall()

    # Group by day
    days = []
    for i in range(5):  # seg-sex
        d = week_start + timedelta(days=i)
        day_appts = [a for a in appointments if a.date == d]
        days.append({
            "date": d,
            "weekday": ["Segunda", "Terca", "Quarta", "Quinta", "Sexta"][i],
            "is_today": d == today,
            "appointments": day_appts,
        })

    month_names = [
        "Janeiro", "Fevereiro", "Marco", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
    ]
    # Mês independente da semana: month_offset (offset em meses a partir do mês
    # corrente) desacopla a grade mensal do ?week. DECISÃO DE PRODUTO: quando
    # ?month ausente, abrir SEMPRE no mês de hoje (mais previsível). ?week segue
    # governando Lista/Ambos sem interferir aqui.
    try:
        month_offset = int(request.query_params.get("month", 0))
    except (ValueError, TypeError):
        month_offset = 0
    # Aritmética de mês segura a partir de today.replace(day=1) (dia já = 1, sem
    # clamp necessário): avança/retrocede month_offset meses.
    base_month = today.replace(day=1)
    total_month = (base_month.year * 12 + (base_month.month - 1)) + month_offset
    month_start = date(total_month // 12, (total_month % 12) + 1, 1)
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    month_end = next_month - timedelta(days=1)
    calendar_start = month_start - timedelta(days=month_start.weekday())
    calendar_end = month_end + timedelta(days=6 - month_end.weekday())
    month_appointments = db.execute(
        text("""
            SELECT a.*, u.name as user_name, u.color as user_color, u.photo_url as user_photo_url
            FROM appointments a
            LEFT JOIN users u ON a.assigned_to = u.id
            WHERE a.org_id = :org_id AND a.date BETWEEN :start AND :end
            ORDER BY a.date, a.time_start NULLS LAST
        """),
        {"org_id": org_id, "start": calendar_start, "end": calendar_end},
    ).fetchall()
    month_weeks = []
    cursor = calendar_start
    while cursor <= calendar_end:
        week = []
        for _ in range(7):
            day_appts = [a for a in month_appointments if a.date == cursor]
            week.append({
                "date": cursor,
                "day": cursor.day,
                "in_month": cursor.month == month_start.month,
                "is_today": cursor == today,
                "appointments": day_appts,
            })
            cursor += timedelta(days=1)
        month_weeks.append(week)

    # Load users for dropdown
    org_users = db.execute(
        text("SELECT id, name, color, photo_url FROM users WHERE org_id = :o AND enabled = TRUE ORDER BY name"),
        {"o": org_id},
    ).fetchall()
    cases = db.execute(
        text("""
            SELECT id, COALESCE(case_number, numero_processo, CAST(id AS TEXT)) AS numero,
                   COALESCE(case_name, tipo_acao, 'Processo') AS nome
            FROM cases
            WHERE org_id = :org_id
            ORDER BY updated_at DESC NULLS LAST, id DESC
            LIMIT 200
        """),
        {"org_id": org_id},
    ).fetchall()
    prazos = db.execute(
        text("""
            SELECT id, tipo, data_vencimento,
                   COALESCE(processo_override, CAST(case_id AS TEXT), '') AS processo
            FROM prazos_processuais
            WHERE org_id = :org_id
              AND COALESCE(status, 'pendente') NOT IN ('concluido', 'concluído', 'cancelado')
            ORDER BY data_vencimento ASC NULLS LAST, id DESC
            LIMIT 200
        """),
        {"org_id": org_id},
    ).fetchall()
    kanban_tasks = db.execute(
        text("""
            SELECT id, title
            FROM tasks
            WHERE org_id = :org_id
              AND COALESCE(status, 'pending') != 'completed'
              AND parent_task_id IS NULL
            ORDER BY updated_at DESC NULLS LAST, id DESC
            LIMIT 200
        """),
        {"org_id": org_id},
    ).fetchall()

    # AG7: Stats cards — compromissos arquivados excluídos.
    _archived = "AND COALESCE(outcome, '') NOT IN ('cancelado', 'contrato_fechado', 'sem_direito')"
    stats_hoje = db.execute(
        text(f"SELECT COUNT(*) FROM appointments WHERE org_id = :o AND date = :d {_archived}"),
        {"o": org_id, "d": today},
    ).scalar() or 0
    stats_atend_semana = db.execute(
        text(f"SELECT COUNT(*) FROM appointments WHERE org_id = :o AND date BETWEEN :s AND :e AND type = 'atendimento' {_archived}"),
        {"o": org_id, "s": week_start, "e": week_end},
    ).scalar() or 0
    stats_aud_semana = db.execute(
        text(f"SELECT COUNT(*) FROM appointments WHERE org_id = :o AND date BETWEEN :s AND :e AND type = 'audiencia' {_archived}"),
        {"o": org_id, "s": week_start, "e": week_end},
    ).scalar() or 0
    stats_reun_semana = db.execute(
        text(f"SELECT COUNT(*) FROM appointments WHERE org_id = :o AND date BETWEEN :s AND :e AND type = 'reuniao' {_archived}"),
        {"o": org_id, "s": week_start, "e": week_end},
    ).scalar() or 0
    stats_follow_up = db.execute(
        text("SELECT COUNT(*) FROM appointments WHERE org_id = :o AND outcome IN ('no_show', 'follow_up')"),
        {"o": org_id},
    ).scalar() or 0
    follow_up_list = db.execute(
        text("""
            SELECT a.id, a.title, a.date, a.time_start, a.client_name, a.type, a.outcome,
                   u.name AS user_name, u.color AS user_color
            FROM appointments a
            LEFT JOIN users u ON a.assigned_to = u.id
            WHERE a.org_id = :o AND a.outcome IN ('no_show', 'follow_up')
            ORDER BY a.date DESC, a.time_start NULLS LAST
            LIMIT 50
        """),
        {"o": org_id},
    ).fetchall()

    # Perícias próximas (estilo Pe-Das1): próximas 30 dias a partir de hoje,
    # org-scoped, ordenadas por proximidade. "dias_ate" = dias até a perícia.
    pericias_proximas = db.execute(
        text(f"""
            SELECT a.id, a.title, a.date, a.time_start, a.time_end,
                   a.client_name, a.local, a.pericia_status,
                   a.notes, a.checklist, a.attachments, a.outcome, a.is_virtual, a.assigned_to,
                   u.name AS user_name,
                   (a.date - :today) AS dias_ate
            FROM appointments a
            LEFT JOIN users u ON a.assigned_to = u.id
            WHERE a.org_id = :o AND a.type = 'pericia' AND a.date >= :today {_archived}
            ORDER BY a.date ASC, a.time_start NULLS LAST
            LIMIT 8
        """),
        {"o": org_id, "today": today},
    ).fetchall()
    stats_pericia_semana = db.execute(
        text(f"SELECT COUNT(*) FROM appointments WHERE org_id = :o AND date BETWEEN :s AND :e AND type = 'pericia' {_archived}"),
        {"o": org_id, "s": week_start, "e": week_end},
    ).scalar() or 0
    all_appt_ids = sorted({
        *(a.id for a in appointments),
        *(a.id for a in month_appointments),
        *(p.id for p in pericias_proximas),
    })
    appt_assignee_ids = _load_appointment_assignee_ids(db, all_appt_ids)
    appt_assignees = _load_appointment_assignees(db, org_id, appt_assignee_ids)
    appt_files = _load_appointment_attachment_files(db, org_id, all_appt_ids)

    # Appointment types
    appt_types = [
        {"value": "audiencia", "label": "Audiencia"},
        {"value": "pericia", "label": "Pericia"},
        {"value": "reuniao", "label": "Reuniao"},
        {"value": "atendimento", "label": "Atendimento"},
        {"value": "outro", "label": "Outro"},
    ]

    t = get_translations(request.cookies.get("lang", "pt-BR"))
    return templates.TemplateResponse("app/calendar/agenda_lista.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "t": t,
        "days": days,
        "week_start": week_start,
        "week_end": week_end,
        "week_offset": week_offset,
        "month_offset": month_offset,
        "month_prev_offset": month_offset - 1,
        "month_next_offset": month_offset + 1,
        "month_label": f"{month_names[month_start.month - 1]} {month_start.year}",
        "month_weeks": month_weeks,
        "org_users": org_users,
        "cases": cases,
        "prazos": prazos,
        "kanban_tasks": kanban_tasks,
        "appt_types": appt_types,
        "today": today,
        "stats_hoje": stats_hoje,
        "stats_atend_semana": stats_atend_semana,
        "stats_aud_semana": stats_aud_semana,
        "stats_reun_semana": stats_reun_semana,
        "stats_pericia_semana": stats_pericia_semana,
        "pericias_proximas": pericias_proximas,
        "stats_follow_up": stats_follow_up,
        "follow_up_list": follow_up_list,
        "appt_assignee_ids": appt_assignee_ids,
        "appt_assignees": appt_assignees,
        "appt_files": appt_files,
    })


@router.post("/appointments")
async def create_appointment(request: Request, db: Session = Depends(get_db)):
    """A2+A10: Create a new appointment."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)

    _ensure_appointment_feedback_schema(db)
    org_id = request.state.org_id
    body = await request.json()

    title = body.get("title", "").strip()
    appt_type = body.get("type", "atendimento")
    assigned_to_ids = _coerce_assigned_to_ids(body)
    valid_assigned_to_ids = _validate_org_user_ids(db, org_id, assigned_to_ids)
    if len(valid_assigned_to_ids) != len(assigned_to_ids):
        return JSONResponse({"error": "Responsavel invalido"}, status_code=400)
    assigned_to = valid_assigned_to_ids[0] if valid_assigned_to_ids else None
    client_name = body.get("client_name", "").strip()
    case_id = body.get("case_id")
    prazo_id = body.get("prazo_id")
    task_id = body.get("task_id")
    appt_date = body.get("date", "")
    time_start = body.get("time_start", "")
    time_end = body.get("time_end", "")
    is_virtual = body.get("is_virtual", False)
    notes = body.get("notes", "").strip()
    checklist = (body.get("checklist") or "").strip()
    attachments = (body.get("attachments") or "").strip()
    local = (body.get("local") or "").strip()
    pericia_status = (body.get("pericia_status") or "").strip()
    outcome = _normalize_appointment_outcome(body.get("outcome"))

    if not title:
        return JSONResponse({"error": "Titulo obrigatorio"}, status_code=400)
    if not appt_date:
        return JSONResponse({"error": "Data obrigatoria"}, status_code=400)

    # Validate case_id belongs to this org before persisting — the column
    # has a FK to cases(id) but Postgres alone cannot tell us *which org*
    # owns the case. Without this guard a caller could attach an
    # appointment to another tenant's case by guessing the id.
    try:
        case_id_int = _optional_int(case_id, "case_id")
        prazo_id_int = _optional_int(prazo_id, "prazo_id")
        task_id_int = _optional_int(task_id, "task_id")
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    if case_id_int and not _linked_row_exists(db, "cases", org_id, case_id_int):
        return JSONResponse({"error": "case_id nao pertence a esta org"}, status_code=404)
    if prazo_id_int and not _linked_row_exists(db, "prazos_processuais", org_id, prazo_id_int):
        return JSONResponse({"error": "prazo_id nao pertence a esta org"}, status_code=404)
    if task_id_int and not _linked_row_exists(db, "tasks", org_id, task_id_int):
        return JSONResponse({"error": "task_id nao pertence a esta org"}, status_code=404)
    conflicts = _appointment_conflicts(db, org_id, appt_date, time_start, time_end, assigned_to)

    result = db.execute(
        text("""
            INSERT INTO appointments (org_id, title, type, assigned_to, client_name, case_id, prazo_id, task_id, date,
                time_start, time_end, is_virtual, notes, checklist, attachments, local, pericia_status, outcome, created_by)
            VALUES (:org_id, :title, :type, :assigned_to, :client_name, :case_id, :prazo_id, :task_id, :date,
                :time_start, :time_end, :is_virtual, :notes, :checklist, :attachments, :local, :pericia_status, :outcome, :created_by)
            RETURNING id
        """),
        {
            "org_id": org_id, "title": title, "type": appt_type,
            "assigned_to": int(assigned_to) if assigned_to else None,
            "client_name": client_name or None,
            "case_id": case_id_int,
            "prazo_id": prazo_id_int,
            "task_id": task_id_int,
            "date": appt_date,
            "time_start": time_start or None,
            "time_end": time_end or None,
            "is_virtual": is_virtual,
            "notes": notes or None,
            "checklist": checklist or None,
            "attachments": attachments or None,
            "local": local or None,
            "pericia_status": pericia_status or None,
            "outcome": outcome or None,
            "created_by": user.id,
        },
    )
    appt_id = result.scalar()
    db.commit()
    _save_appointment_assignees(db, appt_id, valid_assigned_to_ids)
    _notify_new_appointment_assignees(
        db,
        org_id,
        user.id,
        set(valid_assigned_to_ids),
        title,
        appt_date,
        time_start,
    )

    google_calendar = _sync_google_appointment(db, org_id, appt_id) if _wants_google_sync(body) else _local_only_calendar_status()

    logger.info("Appointment created: %s on %s (id=%d)", title, appt_date, appt_id)
    return JSONResponse({"success": True, "id": appt_id, "conflicts": conflicts, "google_calendar": google_calendar})


@router.put("/appointments/{appt_id}")
async def update_appointment(request: Request, appt_id: int, db: Session = Depends(get_db)):
    """AG1: Edit an existing appointment."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)

    _ensure_appointment_feedback_schema(db)
    body = await request.json()

    org_id = request.state.org_id
    existing = db.execute(
        text("SELECT assigned_to FROM appointments WHERE id = :id AND org_id = :org_id"),
        {"id": appt_id, "org_id": org_id},
    ).fetchone()
    if not existing:
        return JSONResponse({"error": "Compromisso nao encontrado"}, status_code=404)
    previous_assignees = set(_load_appointment_assignee_ids(db, [appt_id]).get(appt_id) or [])
    if existing.assigned_to:
        previous_assignees.add(existing.assigned_to)

    assigned_to_ids = _coerce_assigned_to_ids(body)
    valid_assigned_to_ids = _validate_org_user_ids(db, org_id, assigned_to_ids)
    if len(valid_assigned_to_ids) != len(assigned_to_ids):
        return JSONResponse({"error": "Responsavel invalido"}, status_code=400)
    assigned_to = valid_assigned_to_ids[0] if valid_assigned_to_ids else None

    link_sql = ""
    link_params = {}
    link_fields = [
        ("case_id", "cases"),
        ("prazo_id", "prazos_processuais"),
        ("task_id", "tasks"),
    ]
    for field, table in link_fields:
        if field not in body:
            continue
        raw_value = body.get(field)
        try:
            value = _optional_int(raw_value, field)
        except ValueError as exc:
            error = "case_id invalido" if field == "case_id" else str(exc)
            return JSONResponse({"error": error}, status_code=400)
        exists = not value or _linked_row_exists(db, table, org_id, value)
        if value and not exists:
            return JSONResponse({"error": f"{field} nao pertence a esta org"}, status_code=404)
        link_sql += f", {field} = :{field}"
        link_params[field] = value
    conflicts = _appointment_conflicts(
        db,
        org_id,
        body.get("date"),
        body.get("time_start"),
        body.get("time_end"),
        body.get("assigned_to"),
        exclude_id=appt_id,
    )

    outcome_sql = ""
    outcome_params = {}
    if "outcome" in body:
        outcome_sql = ", outcome = :outcome"
        outcome_params["outcome"] = _normalize_appointment_outcome(body.get("outcome")) or None

    db.execute(
        text(f"""
            UPDATE appointments SET title = :title, type = :type, assigned_to = :assigned_to,
                client_name = :client_name, date = :date, time_start = :time_start,
                time_end = :time_end, is_virtual = :is_virtual, notes = :notes,
                checklist = :checklist, attachments = :attachments,
                local = :local, pericia_status = :pericia_status{outcome_sql}{link_sql},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id AND org_id = :org_id
        """),
        {
            "id": appt_id, "org_id": org_id,
            "title": body.get("title", "").strip(),
            "type": body.get("type", "atendimento"),
            "assigned_to": assigned_to,
            "client_name": body.get("client_name", "").strip() or None,
            "date": body.get("date"),
            "time_start": body.get("time_start") or None,
            "time_end": body.get("time_end") or None,
            "is_virtual": body.get("is_virtual", False),
            "notes": body.get("notes", "").strip() or None,
            "checklist": (body.get("checklist") or "").strip() or None,
            "attachments": (body.get("attachments") or "").strip() or None,
            "local": (body.get("local") or "").strip() or None,
            "pericia_status": (body.get("pericia_status") or "").strip() or None,
            **outcome_params,
            **link_params,
        },
    )
    db.commit()
    _save_appointment_assignees(db, appt_id, valid_assigned_to_ids)
    _notify_new_appointment_assignees(
        db,
        org_id,
        user.id,
        set(valid_assigned_to_ids) - previous_assignees,
        body.get("title", ""),
        body.get("date", ""),
        body.get("time_start", ""),
    )
    google_calendar = _sync_google_appointment(db, request.state.org_id, appt_id) if _wants_google_sync(body) else _local_only_calendar_status()
    return JSONResponse({"success": True, "id": appt_id, "conflicts": conflicts, "google_calendar": google_calendar})


@router.post("/appointments/{appt_id}/attachments")
async def upload_appointment_attachment(
    request: Request,
    appt_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)

    _ensure_appointment_feedback_schema(db)
    org_id = request.state.org_id
    appt = db.execute(
        text("SELECT id FROM appointments WHERE id = :id AND org_id = :org_id"),
        {"id": appt_id, "org_id": org_id},
    ).first()
    if not appt:
        return JSONResponse({"error": "Compromisso nao encontrado"}, status_code=404)

    raw_name = os.path.basename(file.filename or "arquivo")
    raw_name = re.sub(r"[^\w\s\-\.]", "_", raw_name)[:120]
    if not raw_name or ".." in raw_name or "/" in raw_name or "\\" in raw_name:
        return JSONResponse({"error": "Nome de arquivo invalido"}, status_code=400)

    ext = os.path.splitext(raw_name)[1].lower()
    attachment_kind = APPOINTMENT_ATTACHMENT_EXT.get(ext)
    if not attachment_kind:
        return JSONResponse({"error": "Tipo de arquivo nao permitido"}, status_code=400)

    content = await file.read()
    if not content:
        return JSONResponse({"error": "Arquivo vazio"}, status_code=400)
    if len(content) > MAX_APPOINTMENT_ATTACHMENT_SIZE:
        return JSONResponse({"error": "Arquivo muito grande (max 25MB)"}, status_code=413)

    try:
        import magic
        detected = magic.from_buffer(content[:4096], mime=True) or ""
        allowed = detected.startswith("image/") or detected in APPOINTMENT_ATTACHMENT_DOC_MIME
        if not allowed or detected == "image/svg+xml":
            return JSONResponse({"error": "Conteudo do arquivo nao permitido"}, status_code=400)
    except ImportError:
        detected = (file.content_type or "application/octet-stream")[:120]

    dest_dir = UPLOADS_ROOT / f"org_{int(org_id)}" / APPOINTMENT_ATTACHMENT_KIND
    try:
        dest_dir.resolve().relative_to(UPLOADS_ROOT)
    except (ValueError, OSError):
        return JSONResponse({"error": "Caminho invalido"}, status_code=400)
    dest_dir.mkdir(parents=True, exist_ok=True)

    stored = f"{uuid.uuid4().hex}{ext}"
    dest = dest_dir / stored
    with open(dest, "wb") as fh:
        fh.write(content)

    db.execute(
        text("""
            INSERT INTO appointment_attachments
                (org_id, appointment_id, file_path, filename, mime_type, size_bytes, uploaded_by)
            VALUES
                (:org_id, :appointment_id, :file_path, :filename, :mime_type, :size_bytes, :uploaded_by)
        """),
        {
            "org_id": org_id,
            "appointment_id": appt_id,
            "file_path": str(dest),
            "filename": raw_name,
            "mime_type": detected[:120],
            "size_bytes": len(content),
            "uploaded_by": user.id,
        },
    )
    db.commit()
    return JSONResponse({
        "success": True,
        "name": raw_name,
        "url": f"/uploads/{APPOINTMENT_ATTACHMENT_KIND}/{stored}",
        "kind": attachment_kind,
    })


@router.delete("/appointments/{appt_id}/attachments/{attachment_id}")
async def delete_appointment_attachment(
    request: Request,
    appt_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
):
    """Remove a single appointment attachment (row + file on disk), org-scoped."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)

    org_id = request.state.org_id
    row = db.execute(
        text("""
            SELECT file_path FROM appointment_attachments
            WHERE id = :id AND appointment_id = :appt_id AND org_id = :org_id
        """),
        {"id": attachment_id, "appt_id": appt_id, "org_id": org_id},
    ).first()
    if not row:
        return JSONResponse({"error": "Anexo nao encontrado"}, status_code=404)

    db.execute(
        text("DELETE FROM appointment_attachments WHERE id = :id AND org_id = :org_id"),
        {"id": attachment_id, "org_id": org_id},
    )
    db.commit()

    # Best-effort file cleanup, confined to the uploads root (defensive).
    try:
        stored = Path(row.file_path)
        stored.resolve().relative_to(UPLOADS_ROOT)
        if stored.is_file():
            stored.unlink()
    except (ValueError, OSError):
        pass

    return JSONResponse({"success": True})


@router.delete("/appointments/{appt_id}")
async def delete_appointment(request: Request, appt_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)
    row = db.execute(
        text("""
            SELECT gcal_event_id, google_calendar_id, google_calendar_account
            FROM appointments
            WHERE id = :id AND org_id = :org_id
        """),
        {"id": appt_id, "org_id": request.state.org_id},
    ).fetchone()
    gcal_event_id = row[0] if row else None
    google_calendar_id = row[1] if row else None
    google_calendar_account = row[2] if row else None
    db.execute(
        text("DELETE FROM appointments WHERE id = :id AND org_id = :org_id"),
        {"id": appt_id, "org_id": request.state.org_id},
    )
    db.commit()
    if gcal_event_id:
        try:
            google_calendar = GoogleCalendarService(
                db, org_id=getattr(request.state, "org_id", None)
            ).delete_appointment_event(
                gcal_event_id,
                account_name=google_calendar_account,
                calendar_id=google_calendar_id,
            )
        except Exception as exc:
            logger.warning("Google Calendar delete skipped for appointment %s: %s", appt_id, exc)
            google_calendar = _local_only_calendar_status()
    else:
        google_calendar = _local_only_calendar_status()
    return JSONResponse({"success": True, "google_calendar": google_calendar})
