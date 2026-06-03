"""
CaseHub - Calendar Routes
Enhanced calendar with tasks, events, and better visualization
"""
from datetime import datetime, date, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, text

from models import get_db, Client, Case, Task, User
from auth import get_current_user
from models.tenant import tenant_query
from i18n import get_translations
from core.template_config import templates, PREFIX
from services.google_calendar import GoogleCalendarService

router = APIRouter(prefix="/calendar", tags=["calendar"])


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


def _load_appointment_for_sync(db: Session, org_id: int, appt_id: int) -> Optional[dict]:
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


def _sync_google_appointment(db: Session, org_id: int, appt_id: int) -> dict:
    appointment = _load_appointment_for_sync(db, org_id, appt_id)
    if not appointment:
        return {"synced": False, "code": "appointment_not_found", "message": ""}

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
    if result.get("synced") and event_id and event_id != appointment.get("gcal_event_id"):
        db.execute(
            text("""
                UPDATE appointments
                SET gcal_event_id = :event_id, updated_at = CURRENT_TIMESTAMP
                WHERE id = :id AND org_id = :org_id
            """),
            {"event_id": event_id, "id": appt_id, "org_id": org_id},
        )
        db.commit()
    return result


def _local_only_calendar_status() -> dict:
    return {
        "synced": False,
        "code": "local_only",
        "message": "Compromisso salvo na agenda local do CaseHub.",
    }


def _optional_int(value, field: str):
    if value in (None, "", 0, "0"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} invalido")


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
async def calendar_view(request: Request, db: Session = Depends(get_db)):
    """Calendar default view.

    02/06 ([parceiro]): a LISTA (compromissos da semana / atendimentos /
    audiências / reuniões) volta a ser o default da Agenda — [parceiro] prefere
    a visão lista em vez do painel "Sua agenda em foco" com KPIs vazios.
    /calendar e /calendar/agenda renderizam a MESMA tela lista (toggle
    interno Lista/Calendário, novo compromisso em modal sobre a lista).
    Sem redirect entre rotas e sem ?new=1.
    """
    return await agenda_lista_view(request, db)


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

    events = []

    # Parse date range
    start_date = datetime.fromisoformat(start.replace('Z', '')).date() if start else date.today() - timedelta(days=30)
    end_date = datetime.fromisoformat(end.replace('Z', '')).date() if end else date.today() + timedelta(days=60)

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
                    SELECT a.*, u.name as user_name, u.color as user_color
                    FROM appointments a
                    LEFT JOIN users u ON a.assigned_to = u.id
                    WHERE a.org_id = :org_id AND a.date BETWEEN :start AND :end
                    ORDER BY a.date, a.time_start
                """),
                {"org_id": request.state.org_id, "start": start_date, "end": end_date},
            ).fetchall()
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
                    # Deep-link pro editor do compromisso na visão lista (29/05 Victor:
                    # clicar num compromisso no grid abria href="#" e só dava refresh).
                    "url": f"{PREFIX}/calendar/agenda?appt={appt.id}",
                    "extendedProps": {"type": "appointment", "apptType": appt.type},
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


# ── Appointments (Agenda VS) ───────────────────────────────────

@router.get("/agenda", response_class=HTMLResponse)
async def agenda_lista_view(request: Request, db: Session = Depends(get_db)):
    """A1: Vista vertical estilo Trello para compromissos da semana."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    org_id = request.state.org_id

    # Get current week range
    today = date.today()
    weekday = today.weekday()  # 0=Mon
    week_start = today - timedelta(days=weekday)
    week_end = week_start + timedelta(days=4)  # Fri

    # Query week param
    week_offset = int(request.query_params.get("week", 0))
    week_start += timedelta(weeks=week_offset)
    week_end = week_start + timedelta(days=4)

    # Load appointments
    appointments = db.execute(
        text("""
            SELECT a.*, u.name as user_name, u.color as user_color
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
    month_start = week_start.replace(day=1)
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    month_end = next_month - timedelta(days=1)
    calendar_start = month_start - timedelta(days=month_start.weekday())
    calendar_end = month_end + timedelta(days=6 - month_end.weekday())
    month_appointments = db.execute(
        text("""
            SELECT a.*, u.name as user_name, u.color as user_color
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
        text("SELECT id, name, color FROM users WHERE org_id = :o AND enabled = TRUE ORDER BY name"),
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

    # AG7: Stats cards
    stats_hoje = db.execute(
        text("SELECT COUNT(*) FROM appointments WHERE org_id = :o AND date = :d"),
        {"o": org_id, "d": today},
    ).scalar() or 0
    stats_atend_semana = db.execute(
        text("SELECT COUNT(*) FROM appointments WHERE org_id = :o AND date BETWEEN :s AND :e AND type = 'atendimento'"),
        {"o": org_id, "s": week_start, "e": week_end},
    ).scalar() or 0
    stats_aud_semana = db.execute(
        text("SELECT COUNT(*) FROM appointments WHERE org_id = :o AND date BETWEEN :s AND :e AND type = 'audiencia'"),
        {"o": org_id, "s": week_start, "e": week_end},
    ).scalar() or 0
    stats_reun_semana = db.execute(
        text("SELECT COUNT(*) FROM appointments WHERE org_id = :o AND date BETWEEN :s AND :e AND type = 'reuniao'"),
        {"o": org_id, "s": week_start, "e": week_end},
    ).scalar() or 0

    # Appointment types
    appt_types = [
        {"value": "audiencia", "label": "Audiencia"},
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
    })


@router.post("/appointments")
async def create_appointment(request: Request, db: Session = Depends(get_db)):
    """A2+A10: Create a new appointment."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)

    org_id = request.state.org_id
    body = await request.json()

    title = body.get("title", "").strip()
    appt_type = body.get("type", "atendimento")
    assigned_to = body.get("assigned_to")
    client_name = body.get("client_name", "").strip()
    case_id = body.get("case_id")
    prazo_id = body.get("prazo_id")
    task_id = body.get("task_id")
    appt_date = body.get("date", "")
    time_start = body.get("time_start", "")
    time_end = body.get("time_end", "")
    is_virtual = body.get("is_virtual", False)
    notes = body.get("notes", "").strip()

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

    result = db.execute(
        text("""
            INSERT INTO appointments (org_id, title, type, assigned_to, client_name, case_id, prazo_id, task_id, date,
                time_start, time_end, is_virtual, notes, created_by)
            VALUES (:org_id, :title, :type, :assigned_to, :client_name, :case_id, :prazo_id, :task_id, :date,
                :time_start, :time_end, :is_virtual, :notes, :created_by)
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
            "created_by": user.id,
        },
    )
    appt_id = result.scalar()
    db.commit()

    google_calendar = _sync_google_appointment(db, org_id, appt_id) if body.get("sync_google") else _local_only_calendar_status()

    logger.info("Appointment created: %s on %s (id=%d)", title, appt_date, appt_id)
    return JSONResponse({"success": True, "id": appt_id, "google_calendar": google_calendar})


@router.put("/appointments/{appt_id}")
async def update_appointment(request: Request, appt_id: int, db: Session = Depends(get_db)):
    """AG1: Edit an existing appointment."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)
    body = await request.json()

    org_id = request.state.org_id

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
        try:
            value = _optional_int(body.get(field), field)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        if value and not _linked_row_exists(db, table, org_id, value):
            return JSONResponse({"error": f"{field} nao pertence a esta org"}, status_code=404)
        link_sql += f", {field} = :{field}"
        link_params[field] = value

    db.execute(
        text(f"""
            UPDATE appointments SET title = :title, type = :type, assigned_to = :assigned_to,
                client_name = :client_name, date = :date, time_start = :time_start,
                time_end = :time_end, is_virtual = :is_virtual, notes = :notes{link_sql},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id AND org_id = :org_id
        """),
        {
            "id": appt_id, "org_id": org_id,
            "title": body.get("title", "").strip(),
            "type": body.get("type", "atendimento"),
            "assigned_to": int(body["assigned_to"]) if body.get("assigned_to") else None,
            "client_name": body.get("client_name", "").strip() or None,
            "date": body.get("date"),
            "time_start": body.get("time_start") or None,
            "time_end": body.get("time_end") or None,
            "is_virtual": body.get("is_virtual", False),
            "notes": body.get("notes", "").strip() or None,
            **link_params,
        },
    )
    db.commit()
    google_calendar = _sync_google_appointment(db, request.state.org_id, appt_id) if body.get("sync_google") else _local_only_calendar_status()
    return JSONResponse({"success": True, "google_calendar": google_calendar})


@router.delete("/appointments/{appt_id}")
async def delete_appointment(request: Request, appt_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)
    row = db.execute(
        text("SELECT gcal_event_id FROM appointments WHERE id = :id AND org_id = :org_id"),
        {"id": appt_id, "org_id": request.state.org_id},
    ).fetchone()
    gcal_event_id = row[0] if row else None
    db.execute(
        text("DELETE FROM appointments WHERE id = :id AND org_id = :org_id"),
        {"id": appt_id, "org_id": request.state.org_id},
    )
    db.commit()
    if gcal_event_id:
        try:
            google_calendar = GoogleCalendarService(
                db, org_id=getattr(request.state, "org_id", None)
            ).delete_appointment_event(gcal_event_id)
        except Exception as exc:
            logger.warning("Google Calendar delete skipped for appointment %s: %s", appt_id, exc)
            google_calendar = _local_only_calendar_status()
    else:
        google_calendar = _local_only_calendar_status()
    return JSONResponse({"success": True, "google_calendar": google_calendar})
