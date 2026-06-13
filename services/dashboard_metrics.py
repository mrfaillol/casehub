"""
Dashboard metric and widget cache helpers.

The Lite dashboard shell should not run the legacy aggregate block on page
render. Widget HTML and legacy dashboard data are cached with a short TTL keyed
by product/org/user so repeated requests inside the same minute avoid duplicate
database work.
"""
import json
import re
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Callable

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, text

from config import settings
_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

from models import BillingItem, Case, Client, Document, Reminder, Task, TimeEntry, User
from models.tenant import tenant_query

logger = logging.getLogger(__name__)

_CACHE_MISSING = object()
_memory_cache = {}
_memory_lock = threading.Lock()
_redis_client = None
_redis_checked = False


def _ttl_seconds(ttl_seconds: int | None = None) -> int:
    return max(1, int(ttl_seconds or settings.DASHBOARD_CACHE_TTL_SECONDS or 60))


def _cache_key(*parts) -> str:
    return "casehub:dashboard:" + ":".join(str(part).replace(":", "_") for part in parts)


def _memory_get(key: str):
    now = time.monotonic()
    with _memory_lock:
        item = _memory_cache.get(key)
        if not item:
            return _CACHE_MISSING
        expires_at, value = item
        if expires_at <= now:
            _memory_cache.pop(key, None)
            return _CACHE_MISSING
        return value


def _memory_set(key: str, value, ttl_seconds: int | None = None):
    with _memory_lock:
        _memory_cache[key] = (time.monotonic() + _ttl_seconds(ttl_seconds), value)


def _redis():
    global _redis_checked, _redis_client

    if _redis_checked:
        return _redis_client

    _redis_checked = True
    redis_url = settings.REDIS_URL
    if not redis_url:
        return None

    try:
        import redis

        client = redis.from_url(redis_url, socket_connect_timeout=0.2, socket_timeout=0.2)
        client.ping()
        _redis_client = client
    except Exception as exc:
        logger.warning("Dashboard Redis cache unavailable; falling back to memory: %s", exc)
        _redis_client = None
    return _redis_client


def _redis_get_text(key: str):
    client = _redis()
    if not client:
        return _CACHE_MISSING
    try:
        value = client.get(key)
    except Exception as exc:
        logger.warning("Dashboard Redis cache read failed for %s: %s", key, exc)
        return _CACHE_MISSING
    if value is None:
        return _CACHE_MISSING
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def _redis_set_text(key: str, value: str, ttl_seconds: int | None = None):
    client = _redis()
    if not client:
        return
    try:
        client.setex(key, _ttl_seconds(ttl_seconds), value)
    except Exception as exc:
        logger.warning("Dashboard Redis cache write failed for %s: %s", key, exc)


def _redis_get_json(key: str):
    raw = _redis_get_text(key)
    if raw is _CACHE_MISSING:
        return _CACHE_MISSING
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        logger.warning("Dashboard Redis cache contained invalid JSON for %s: %s", key, exc)
        return _CACHE_MISSING


def _redis_set_json(key: str, value, ttl_seconds: int):
    client = _redis()
    if not client:
        return
    try:
        client.setex(key, _ttl_seconds(ttl_seconds), json.dumps(value, default=str))
    except Exception as exc:
        logger.warning("Dashboard Redis cache JSON write failed for %s: %s", key, exc)


def _cached_json_value(key: str, ttl_seconds: int, renderer: Callable[[], dict]) -> dict:
    cached = _redis_get_json(key)
    if cached is not _CACHE_MISSING:
        return cached

    cached = _memory_get(key)
    if cached is not _CACHE_MISSING:
        return cached

    value = renderer()
    _memory_set(key, value, ttl_seconds=ttl_seconds)
    _redis_set_json(key, value, ttl_seconds=ttl_seconds)
    return value


def cached_widget_html(widget_id: str, org_id, user_id, renderer: Callable[[], str]) -> str:
    key = _cache_key("widget", org_id, user_id, widget_id)
    return _cached_text_value(key, _ttl_seconds(), renderer)


def cached_basic_dashboard_html(org_id, user_id, today, variant: str, renderer: Callable[[], str]) -> str:
    key = _cache_key("basic-html", org_id, user_id, today.isoformat(), variant)
    return _cached_text_value(key, _ttl_seconds(), renderer)


def _cached_text_value(key: str, ttl_seconds: int, renderer: Callable[[], str]) -> str:
    cached = _memory_get(key)
    if cached is not _CACHE_MISSING:
        return cached

    cached = _redis_get_text(key)
    if cached is not _CACHE_MISSING:
        _memory_set(key, cached, ttl_seconds=ttl_seconds)
        return cached

    html = renderer()
    _memory_set(key, html, ttl_seconds=ttl_seconds)
    _redis_set_text(key, html, ttl_seconds=ttl_seconds)
    return html


def _pct_delta(current: float, previous: float) -> dict:
    if previous:
        pct = ((current - previous) / previous) * 100
        return {
            "label": f"{pct:+.0f}%",
            "direction": "up" if pct >= 0 else "down",
        }
    if current:
        return {"label": "+100%", "direction": "up"}
    return {"label": "0%", "direction": "flat"}


def _status_label(status: str) -> tuple[str, str]:
    normalized = (status or "ativo").lower()
    if normalized in {"closed", "approved", "denied", "concluido", "concluído", "finalizado"}:
        return "Fechado", "closed"
    if normalized in {"review", "revisao", "revisão", "rfe"}:
        return "Revisão", "review"
    return "Ativo", "active"


def _initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "CH"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _sparkline(values: list[float], width: int = 100, height: int = 24) -> dict:
    if not values:
        values = [0, 0]
    if len(values) == 1:
        values = [values[0], values[0]]
    max_v = max(values)
    min_v = min(values)
    span = max(max_v - min_v, 1)
    step = width / (len(values) - 1)
    points = []
    for i, value in enumerate(values):
        x = i * step
        y = height - ((value - min_v) / span) * (height - 2) - 1
        points.append(f"{x:.1f},{y:.1f}")
    return {
        "points": " ".join(points),
        "area": f"0,{height} {' '.join(points)} {width},{height}",
        "trend": "down" if values[-1] < values[0] else "up" if values[-1] > values[0] else "flat",
    }


def _chart(values: list[float], labels: list[str], target: float = 24.0) -> dict:
    width = 600
    height = 200
    pad = 30
    if not values:
        values = [0.0] * 14
    max_v = max(max(values), target, 1)
    min_v = min(min(values), 0)
    span = max(max_v - min_v, 1)
    step = (width - pad * 2) / max(len(values) - 1, 1)

    def y_scale(value: float) -> float:
        return height - pad - ((value - min_v) / span) * (height - pad * 2)

    points = [
        {
            "x": round(pad + (i * step), 1),
            "y": round(y_scale(value), 1),
            "value": value,
        }
        for i, value in enumerate(values)
    ]
    line = " ".join(f"{p['x']},{p['y']}" for p in points)
    return {
        "points": line,
        "area": f"{pad},{height - pad} {line} {points[-1]['x']},{height - pad}",
        "dots": points,
        "target_y": round(y_scale(target), 1),
        "labels": [
            {"x": points[i]["x"], "label": labels[i]}
            for i in range(len(points))
            if i in {0, 3, 6, 9, 12, len(points) - 1}
        ],
        "grid": [
            {"label": f"{int(value)}h", "y": round(y_scale(value), 1)}
            for value in [min_v, (min_v + max_v) / 2, max_v]
        ],
    }


def _pt_date_label(day) -> str:
    weekdays = [
        "segunda-feira",
        "terça-feira",
        "quarta-feira",
        "quinta-feira",
        "sexta-feira",
        "sábado",
        "domingo",
    ]
    return f"{weekdays[day.weekday()].title()}, {day.strftime('%d/%m/%Y')}"


def get_basic_dashboard_context(db, org_id, user_id, today, user=None) -> dict:
    """Build the Basic dashboard rescue panel with real data and safe fallbacks."""
    key = _cache_key("basic-panel", org_id, user_id, today.isoformat())
    return _cached_json_value(
        key,
        _ttl_seconds(),
        lambda: _build_basic_dashboard_context(db, org_id, today, user=user),
    )


def _build_basic_dashboard_context(db, org_id, today, user=None) -> dict:
    fourteen_days_ago = today - timedelta(days=13)
    previous_start = today - timedelta(days=27)
    previous_end = today - timedelta(days=14)
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    month_start = today.replace(day=1)
    previous_month_start = (month_start - relativedelta(months=1)).replace(day=1)
    previous_month_end = month_start - timedelta(days=1)

    new_cases = tenant_query(db, Case, org_id).filter(Case.created_at >= fourteen_days_ago).count()
    previous_cases = tenant_query(db, Case, org_id).filter(
        Case.created_at >= previous_start,
        Case.created_at <= previous_end,
    ).count()
    closed_statuses = ["approved", "denied", "closed", "concluido", "concluído", "finalizado"]
    closed_month = tenant_query(db, Case, org_id).filter(
        Case.status.in_(closed_statuses),
        Case.updated_at >= month_start,
    ).count()
    closed_previous = tenant_query(db, Case, org_id).filter(
        Case.status.in_(closed_statuses),
        Case.updated_at >= previous_month_start,
        Case.updated_at <= previous_month_end,
    ).count()

    def _appointment_count(start_day, end_day, appt_type=None) -> int:
        try:
            sql = """
                SELECT COUNT(*)
                FROM appointments
                WHERE org_id = :org_id
                  AND date >= :start_day
                  AND date <= :end_day
            """
            params = {"org_id": org_id, "start_day": start_day, "end_day": end_day}
            if appt_type is not None:
                sql += " AND type = :appt_type"
                params["appt_type"] = appt_type
            return db.execute(text(sql), params).scalar() or 0
        except Exception as exc:
            logger.warning("Basic dashboard appointments unavailable: %s", exc)
            return 0

    appointment_week = _appointment_count(week_start, week_end)
    appointment_previous = _appointment_count(week_start - timedelta(days=7), week_end - timedelta(days=7))
    # Audiências: appointments com type 'audiencia' (taxonomia migrations/2026-04-06_appointments.sql)
    hearing_week = _appointment_count(week_start, week_end, appt_type="audiencia")
    hearing_previous = _appointment_count(
        week_start - timedelta(days=7), week_end - timedelta(days=7), appt_type="audiencia"
    )

    case_series = []
    appointment_series = []
    hearing_series = []
    closed_series = []
    day_labels = []
    for offset in range(13, -1, -1):
        day = today - timedelta(days=offset)
        next_day = day + timedelta(days=1)
        day_labels.append("hoje" if day == today else day.strftime("%d/%m"))
        case_series.append(tenant_query(db, Case, org_id).filter(
            Case.created_at >= day,
            Case.created_at < next_day,
        ).count())
        appointment_series.append(float(_appointment_count(day, day)))
        hearing_series.append(float(_appointment_count(day, day, appt_type="audiencia")))
        closed_series.append(tenant_query(db, Case, org_id).filter(
            Case.status.in_(closed_statuses),
            Case.updated_at >= day,
            Case.updated_at < next_day,
        ).count())

    pending_tasks = tenant_query(db, Task, org_id).filter(
        Task.status != "completed",
    ).order_by(Task.due_date.asc().nullslast(), Task.created_at.desc()).limit(5).all()
    tasks_today = []
    for task in pending_tasks:
        due = task.due_date
        case_ref = "Sem processo"
        if task.case:
            case_ref = task.case.case_number or task.case.numero_processo or f"CASE-{task.case.id:04d}"
        elif task.client:
            case_ref = task.client.full_name
        tasks_today.append({
            "title": task.title or "Tarefa sem título",
            "case_ref": case_ref,
            "due": due.strftime("%d/%m") if due else "sem data",
            "overdue": bool(due and due < today),
            "done": False,
        })

    deadlines_week = []
    try:
        rows = db.execute(
            text("""
                SELECT p.id, p.tipo, p.data_vencimento, p.descricao,
                       COALESCE(p.processo_override, c.case_number, c.numero_processo, 'Sem processo') AS processo,
                       COALESCE(c.case_name, CONCAT(cl.first_name, ' ', cl.last_name), '') AS case_name
                FROM prazos_processuais p
                LEFT JOIN cases c ON c.id = p.case_id
                LEFT JOIN clients cl ON cl.id = c.client_id
                WHERE p.org_id = :org_id
                  AND COALESCE(p.status, 'pendente') NOT IN ('concluido', 'concluído', 'cancelado')
                  AND p.data_vencimento BETWEEN :start AND :end
                ORDER BY p.data_vencimento ASC
                LIMIT 5
            """),
            {"org_id": org_id, "start": today, "end": today + timedelta(days=7)},
        ).fetchall()
        for row in rows:
            venc = row.data_vencimento
            deadlines_week.append({
                "day": venc.day,
                "month": venc.strftime("%b"),
                "title": row.tipo or "Prazo processual",
                "case_ref": f"{row.processo} · {row.case_name}".strip(" ·"),
                "urgent": (venc - today).days <= 2,
            })
    except Exception as exc:
        logger.warning("Basic dashboard deadlines unavailable: %s", exc)

    if not deadlines_week:
        reminders = tenant_query(db, Reminder, org_id).filter(
            Reminder.is_completed.is_(False),
            Reminder.due_date >= datetime.combine(today, datetime.min.time()),
            Reminder.due_date <= datetime.combine(today + timedelta(days=7), datetime.max.time()),
        ).order_by(Reminder.due_date.asc()).limit(5).all()
        for reminder in reminders:
            due = reminder.due_date.date()
            deadlines_week.append({
                "day": due.day,
                "month": due.strftime("%b"),
                "title": reminder.title or "Lembrete",
                "case_ref": reminder.description or "Agenda",
                "urgent": (due - today).days <= 2,
            })

    # Audiências próximas (semana corrente) — appointments com type 'audiencia'.
    hearings_week = []
    try:
        hearing_rows = db.execute(
            text("""
                SELECT a.title, a.date, a.time_start, a.client_name,
                       COALESCE(c.case_number, c.numero_processo, '') AS processo
                FROM appointments a
                LEFT JOIN cases c ON c.id = a.case_id
                WHERE a.org_id = :org_id
                  AND a.type = 'audiencia'
                  AND a.date BETWEEN :start AND :end
                ORDER BY a.date ASC, a.time_start ASC NULLS LAST
                LIMIT 5
            """),
            {"org_id": org_id, "start": today, "end": today + timedelta(days=7)},
        ).fetchall()
        for row in hearing_rows:
            hdate = row.date
            ref_bits = [b for b in (row.processo, row.client_name) if b]
            hearings_week.append({
                "day": hdate.day,
                "month": hdate.strftime("%b"),
                "title": row.title or "Audiência",
                "case_ref": " · ".join(ref_bits) or "Sem processo",
                "time": row.time_start.strftime("%H:%M") if row.time_start else "",
                "urgent": (hdate - today).days <= 2,
            })
    except Exception as exc:
        logger.warning("Basic dashboard hearings unavailable: %s", exc)

    # Presença real (não mais fake): só usuários com last_activity nos últimos
    # 5 minutos contam como "online agora". Usa o timestamp real de cada um —
    # nada de cravar now() em todo mundo. Quem nunca foi visto (last_activity
    # NULL) ou está parado >5min simplesmente não aparece.
    now = datetime.now()
    presence_window = now - timedelta(minutes=5)
    team = []
    try:
        online_users = (
            tenant_query(db, User, org_id)
            .filter(User.enabled.is_(True))
            .filter(User.last_activity.isnot(None))
            .filter(User.last_activity >= presence_window)
            .order_by(User.last_activity.desc())
            .limit(8)
            .all()
        )
    except Exception as exc:
        # Coluna pode não existir até a migration ser aplicada — degrada para
        # lista vazia (estado honesto "Ninguém online agora") em vez de 500.
        logger.warning("Real presence unavailable (last_activity): %s", exc)
        online_users = []
    for member in online_users:
        display_name = member.name or ""
        seen = member.last_activity or now
        member_color = getattr(member, "color", None) or "#1C2447"
        if not _HEX_COLOR.match(str(member_color)):
            member_color = "#1C2447"
        team.append({
            "initials": _initials(display_name),
            "photo_url": member.photo_url,
            "color": member_color,
            "name": display_name,
            "city": member.department or "Escritório",
            "hour": seen.hour,
            "minute": seen.minute,
            "status": "online",
        })

    # Atividade/auditoria do escritório: NÃO vazar para advogado/estagiário/staff.
    # Só gestor (admin) e superadmin recebem dados; demais cargos ficam com a
    # lista vazia (e o card é ocultado no template por gating de user_type).
    user_type = getattr(user, "user_type", None)
    activity = []
    if user_type in ("admin", "superadmin"):
        recent_clients = tenant_query(db, Client, org_id).order_by(Client.created_at.desc()).limit(3).all()
        for client in recent_clients:
            activity.append({
                "time": client.created_at.strftime("%d/%m") if client.created_at else "recente",
                "actor": "Sistema",
                "verb": "cadastrou cliente",
                "target": client.full_name,
            })
        for task in pending_tasks[:3]:
            activity.append({
                "time": task.created_at.strftime("%d/%m") if task.created_at else "recente",
                "actor": task.assignee.name.split()[0] if task.assignee else "Equipe",
                "verb": "tem tarefa",
                "target": task.title or "sem título",
            })

    recent_case_rows = tenant_query(db, Case, org_id).order_by(Case.updated_at.desc().nullslast(), Case.created_at.desc()).limit(8).all()
    recent_cases = []
    for case in recent_case_rows:
        status_label, status_variant = _status_label(case.status)
        client_name = case.client.full_name if case.client else "Sem cliente"
        next_date = "—"
        try:
            next_prazo = db.execute(
                text("""
                    SELECT data_vencimento
                    FROM prazos_processuais
                    WHERE org_id = :org_id
                      AND case_id = :case_id
                      AND COALESCE(status, 'pendente') NOT IN ('concluido', 'concluído', 'cancelado')
                    ORDER BY data_vencimento ASC
                    LIMIT 1
                """),
                {"org_id": org_id, "case_id": case.id},
            ).fetchone()
            if next_prazo and next_prazo.data_vencimento:
                next_date = next_prazo.data_vencimento.strftime("%d/%m")
        except Exception:
            pass
        recent_cases.append({
            "ref": case.case_number or case.numero_processo or f"CASE-{case.id:04d}",
            "title": case.case_name or case.tipo_acao or "Processo sem título",
            "client": client_name,
            "status": status_variant,
            "status_label": status_label,
            "last_activity": case.updated_at.strftime("%d/%m") if case.updated_at else "Cadastro",
            "next_date": next_date,
        })

    # Totais para os KPIs operacionais (não limitados às 5 linhas dos cards).
    open_tasks_total = tenant_query(db, Task, org_id).filter(Task.status != "completed").count()
    overdue_tasks_total = tenant_query(db, Task, org_id).filter(
        Task.status != "completed",
        Task.due_date.isnot(None),
        Task.due_date < today,
    ).count()
    deadlines_week_total = len(deadlines_week)
    today_appointments = _appointment_count(today, today)

    dashboard = {
        "user_first_name": (user.name.split()[0] if user and user.name else "Doutor"),
        "date_label": _pt_date_label(today),
        # KPIs reordenados (Example User/Maria 02/06): operação do dia em destaque
        # — tarefas, compromissos do dia, prazos, audiências — e os indicadores
        # de volume (novos casos / casos fechados) rebaixados a secundário.
        "metrics": [
            {
                "label": "Tarefas em aberto",
                "route": "/tasks/kanban", "go_label": "Ir para tarefas",
                "value": open_tasks_total,
                "unit": "",
                "secondary": False,
                "delta": {
                    "label": (f"{overdue_tasks_total} atrasadas" if overdue_tasks_total else "em dia"),
                    "direction": ("down" if overdue_tasks_total else "flat"),
                },
                "sparkline": None,
            },
            {
                "label": "Compromissos (hoje)",
                "route": "/calendar/agenda", "go_label": "Ir para agenda",
                "value": today_appointments,
                "unit": "",
                "secondary": False,
                "delta": {
                    "label": f"{appointment_week} na semana",
                    "direction": "flat",
                },
                "sparkline": _sparkline([float(v) for v in appointment_series]),
            },
            {
                "label": "Prazos (7 dias)",
                "route": "/controladoria", "go_label": "Ir para prazos",
                "value": deadlines_week_total,
                "unit": "",
                "secondary": False,
                "delta": {
                    "label": "vencimentos próximos",
                    "direction": "flat",
                },
                "sparkline": None,
            },
            {
                "label": "Audiências (semana)",
                "route": "/calendar/agenda", "go_label": "Ir para agenda",
                "value": hearing_week,
                "unit": "",
                "secondary": False,
                "delta": _pct_delta(float(hearing_week), float(hearing_previous)),
                "sparkline": _sparkline([float(v) for v in hearing_series]),
            },
            {
                "label": "Novos casos (14d)",
                "route": "/cases", "go_label": "Ver processos",
                "value": new_cases,
                "unit": "",
                "secondary": True,
                "delta": _pct_delta(float(new_cases), float(previous_cases)),
                "sparkline": _sparkline([float(v) for v in case_series]),
            },
            {
                "label": "Casos fechados (mês)",
                "route": "/cases", "go_label": "Ver processos",
                "value": closed_month,
                "unit": "",
                "secondary": True,
                "delta": _pct_delta(float(closed_month), float(closed_previous)),
                "sparkline": _sparkline([float(v) for v in closed_series]),
            },
        ],
        "tasks_today": tasks_today,
        "deadlines_week": deadlines_week,
        "hearings_week": hearings_week,
        "team": team,
        "activity": activity[:6],
        "recent_cases": recent_cases,
        "operations_chart": _chart([float(v) for v in appointment_series], day_labels, target=max(float(appointment_week), 1.0)),
        "maestro_summary": {
            "title": "Resumo do Maestro",
            "text": (
                "Priorize o que vence primeiro: prazos críticos, compromissos da semana "
                "e tarefas sem responsável claro."
            ),
            "bullets": [
                f"{open_tasks_total} tarefas em aberto ({overdue_tasks_total} atrasadas).",
                f"{len(deadlines_week)} prazos ou lembretes nos próximos 7 dias.",
                f"{hearing_week} audiências e {appointment_week} compromissos nesta semana.",
                f"{closed_month} casos fechados no mês.",
            ],
        },
    }
    context = {"basic_dashboard": dashboard}
    return context


def get_legacy_dashboard_context(db, org_id, user_id, today, product: str) -> dict:
    """
    Build the legacy dashboard aggregate context.

    This path is intentionally not used by the Lite dashboard shell. It remains
    available for immigration/whitelabel dashboards and is cached in process
    because it contains ORM objects consumed by existing templates.
    """
    key = _cache_key("context", product, org_id, user_id, today.isoformat())
    cached = _memory_get(key)
    if cached is not _CACHE_MISSING:
        return cached

    first_day_of_month = today.replace(day=1)
    thirty_days_from_now = today + timedelta(days=30)

    total_clients = tenant_query(db, Client, org_id).count()
    total_cases = tenant_query(db, Case, org_id).count()
    active_cases = tenant_query(db, Case, org_id).filter(
        Case.status.notin_(["approved", "denied", "closed"])
    ).count()
    rfe_cases = tenant_query(db, Case, org_id).filter(Case.status == "rfe").count()
    total_documents = tenant_query(db, Document, org_id).count()

    new_clients_month = tenant_query(db, Client, org_id).filter(
        Client.created_at >= first_day_of_month
    ).count()
    new_cases_month = tenant_query(db, Case, org_id).filter(
        Case.created_at >= first_day_of_month
    ).count()

    pending_tasks = tenant_query(db, Task, org_id).filter(Task.status != "completed").count()
    overdue_tasks = tenant_query(db, Task, org_id).filter(
        Task.status != "completed",
        Task.due_date < today,
    ).count()

    recent_clients = tenant_query(db, Client, org_id).order_by(Client.created_at.desc()).limit(5).all()
    recent_cases = tenant_query(db, Case, org_id).order_by(Case.created_at.desc()).limit(5).all()

    upcoming_tasks = tenant_query(db, Task, org_id).filter(
        Task.status != "completed"
    ).order_by(Task.due_date.asc().nullslast()).limit(5).all()

    cases_attention = tenant_query(db, Case, org_id).filter(
        Case.status == "rfe"
    ).order_by(Case.updated_at.desc()).limit(5).all()

    expiring_soon = tenant_query(db, Case, org_id).filter(
        Case.expiration_date.isnot(None),
        Case.expiration_date <= thirty_days_from_now,
        Case.expiration_date >= today,
        Case.status.notin_(["approved", "denied", "closed"]),
    ).order_by(Case.expiration_date.asc()).limit(5).all()

    try:
        total_paid = db.query(func.sum(BillingItem.amount)).filter(
            BillingItem.org_id == org_id,
            BillingItem.status == "paid",
            BillingItem.paid_date >= first_day_of_month,
        ).scalar() or 0

        pending_revenue = db.query(func.sum(BillingItem.amount)).filter(
            BillingItem.org_id == org_id,
            BillingItem.status.in_(["pending", "invoiced"]),
        ).scalar() or 0

        hours_logged = db.query(func.sum(TimeEntry.hours)).filter(
            TimeEntry.org_id == org_id,
            TimeEntry.date >= first_day_of_month,
        ).scalar() or 0
    except Exception:
        total_paid = 0
        pending_revenue = 0
        hours_logged = 0

    trend_months = []
    trend_counts = []
    for i in range(5, -1, -1):
        month_date = today - relativedelta(months=i)
        month_start = month_date.replace(day=1)
        if i > 0:
            month_end = (month_date + relativedelta(months=1)).replace(day=1) - timedelta(days=1)
        else:
            month_end = today

        count = tenant_query(db, Case, org_id).filter(
            Case.created_at >= month_start,
            Case.created_at <= month_end,
        ).count()

        trend_months.append(month_date.strftime("%b"))
        trend_counts.append(count)

    case_status_query = db.query(Case.status, func.count(Case.id)).filter(
        Case.org_id == org_id
    ).group_by(Case.status).all()
    case_stats = {s: c for s, c in case_status_query}

    visa_type_query = db.query(Case.visa_type, func.count(Case.id)).filter(
        Case.org_id == org_id,
        Case.visa_type.isnot(None),
        Case.visa_type != "",
    ).group_by(Case.visa_type).order_by(func.count(Case.id).desc()).limit(7).all()
    visa_types = [vt[0] if vt[0] else "Other" for vt in visa_type_query]
    visa_counts = [vt[1] for vt in visa_type_query]

    context = {
        "stats": {
            "total_clients": total_clients,
            "total_cases": total_cases,
            "active_cases": active_cases,
            "rfe_cases": rfe_cases,
            "total_documents": total_documents,
            "pending_tasks": pending_tasks,
            "overdue_tasks": overdue_tasks,
            "new_clients_month": new_clients_month,
            "new_cases_month": new_cases_month,
        },
        "recent_clients": recent_clients,
        "recent_cases": recent_cases,
        "upcoming_tasks": upcoming_tasks,
        "cases_attention": cases_attention,
        "expiring_soon": expiring_soon,
        "revenue": {
            "total_paid": float(total_paid),
            "pending": float(pending_revenue),
            "hours_logged": float(hours_logged),
        },
        "trend_months": trend_months,
        "trend_counts": trend_counts,
        "case_stats": case_stats,
        "visa_types": visa_types,
        "visa_counts": visa_counts,
    }
    _memory_set(key, context)
    return context


def clear_dashboard_cache() -> None:
    with _memory_lock:
        _memory_cache.clear()
