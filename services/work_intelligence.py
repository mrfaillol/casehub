"""Worker-centered workflow observability for CaseHub.

The feature is default-off and intentionally avoids surveillance primitives:
no keylogging, cursor coordinates, screenshots, screen recording, clipboard,
raw DOM, message bodies, typed text, or raw prompt/log feeds to Maestro.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import bindparam, inspect, text
from sqlalchemy.orm import Session

from config import settings

logger = logging.getLogger(__name__)


TRUTHY = {"1", "true", "yes", "on", "sim"}
MIN_GROUP_SIZE = 3
MAX_BATCH_EVENTS = 20
MAX_METADATA_KEYS = 12
MAX_ROUTE_LENGTH = 255
MAX_SURFACE_LENGTH = 120
MAX_ACTION_LENGTH = 120
MAX_EVENT_AGE_DAYS = 14

CLIENT_EVENT_TYPES = {
    "page_view",
    "page_hide",
    "visibility",
    "heartbeat",
    "action",
    "api_error",
    "ui_error",
    "flow_abandon",
}

FORBIDDEN_EVENT_KEYS = {
    "body",
    "clipboard",
    "clientx",
    "clienty",
    "content",
    "cursor",
    "dom",
    "html",
    "image",
    "innerhtml",
    "key",
    "keys",
    "message",
    "outerhtml",
    "screenshot",
    "screenx",
    "screeny",
    "selector",
    "stack",
    "text",
    "typed",
    "value",
    "x",
    "y",
}

ALLOWED_METADATA_KEYS = {
    "action_id",
    "action_role",
    "duration_ms",
    "error_kind",
    "flow_id",
    "method",
    "module",
    "referrer_route",
    "route",
    "status_code",
    "surface",
    "visible_seconds",
}

TEXT_REDACTIONS = [
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "<email>"),
    (re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), "<cpf>"),
    (re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"), "<cnpj>"),
    (re.compile(r"\bOAB/[A-Z]{2}\s*\d+\b", re.IGNORECASE), "<oab>"),
]


@dataclass(frozen=True)
class SanitizedClientEvent:
    event_type: str
    route: str
    surface: str
    occurred_at: datetime
    duration_ms: int | None
    metadata: dict[str, Any]
    session_id: str


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in TRUTHY


def _json_loads(value: Any) -> Any:
    if value is None or value == "":
        return {}
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _start_of_day(value: date) -> datetime:
    return datetime.combine(value, time.min)


def _table_exists(db: Session, table_name: str) -> bool:
    try:
        return bool(inspect(db.bind).has_table(table_name))
    except Exception:
        return False


def _safe_execute(db: Session, sql: str, params: dict[str, Any] | None = None):
    try:
        stmt = text(sql)
        if params and "excluded_ids" in params:
            stmt = stmt.bindparams(bindparam("excluded_ids", expanding=True))
        return db.execute(stmt, params or {})
    except Exception as exc:
        logger.debug("work intelligence query skipped: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return None


def _scalar(db: Session, sql: str, params: dict[str, Any] | None = None, default=0):
    result = _safe_execute(db, sql, params)
    if result is None:
        return default
    value = result.scalar()
    return default if value is None else value


def _mappings(db: Session, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    result = _safe_execute(db, sql, params)
    if result is None:
        return []
    return [dict(row) for row in result.mappings().all()]


def _load_org_json_settings(db: Session, org_id: int) -> dict[str, Any]:
    if not _table_exists(db, "organizations"):
        return {}
    row = _safe_execute(
        db,
        "SELECT settings FROM organizations WHERE id = :org_id",
        {"org_id": org_id},
    )
    if row is None:
        return {}
    result = row.fetchone()
    if not result:
        return {}
    loaded = _json_loads(result[0])
    return loaded if isinstance(loaded, dict) else {}


def _load_org_settings_table(db: Session, org_id: int) -> dict[str, Any]:
    if not _table_exists(db, "org_settings"):
        return {}
    rows = _mappings(
        db,
        "SELECT key, value FROM org_settings WHERE org_id = :org_id",
        {"org_id": org_id},
    )
    settings_map: dict[str, Any] = {}
    for row in rows:
        key = row.get("key")
        if key:
            settings_map[str(key)] = row.get("value")
    return settings_map


def tenant_work_intelligence_settings(db: Session, org_id: int) -> dict[str, Any]:
    merged = _load_org_json_settings(db, org_id)
    merged.update(_load_org_settings_table(db, org_id))
    return merged


def is_work_intelligence_enabled(db: Session, org_id: int | None) -> bool:
    if not org_id or not bool(getattr(settings, "CASEHUB_WORK_INTELLIGENCE_ENABLED", False)):
        return False
    tenant_settings = tenant_work_intelligence_settings(db, int(org_id))
    return _boolish(tenant_settings.get("work_intelligence_enabled"))


def is_client_events_enabled(db: Session, org_id: int | None) -> bool:
    if not is_work_intelligence_enabled(db, org_id):
        return False
    if not bool(getattr(settings, "CASEHUB_WORK_INTELLIGENCE_CLIENT_EVENTS_ENABLED", False)):
        return False
    tenant_settings = tenant_work_intelligence_settings(db, int(org_id))
    return _boolish(tenant_settings.get("work_intelligence_client_events_enabled"))


def _norm_text(value: Any) -> str:
    return str(value or "").strip().lower()


def is_excluded_user(user: Any) -> bool:
    email = _norm_text(getattr(user, "email", ""))
    name = _norm_text(getattr(user, "name", ""))
    user_type = _norm_text(getattr(user, "user_type", ""))
    probe = " ".join([email, name, user_type])

    if user_type in {"automation", "bot", "developer", "dev", "qa", "test"}:
        return True
    patterns = (
        "casehub_team",
        "casehub",
        "qa claude",
        "user.qa",
        "claude",
        "automation",
        "automacao",
        "bot",
        "dev",
        "developer",
        "teste",
        "test",
    )
    return any(pattern in probe for pattern in patterns)


def excluded_user_ids(db: Session, org_id: int) -> set[int]:
    if not _table_exists(db, "users"):
        return set()
    rows = _mappings(
        db,
        """
        SELECT id, email, name, user_type
        FROM users
        WHERE org_id = :org_id
        """,
        {"org_id": org_id},
    )
    excluded: set[int] = set()
    for row in rows:
        user = type("UserProbe", (), row)
        if is_excluded_user(user):
            try:
                excluded.add(int(row["id"]))
            except (TypeError, ValueError, KeyError):
                pass
    return excluded


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).strip().lower() in FORBIDDEN_EVENT_KEYS:
                return True
            if _contains_forbidden_key(item):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _sanitize_identifier(value: Any, max_len: int = MAX_ACTION_LENGTH) -> str:
    raw = str(value or "").strip()[:max_len]
    return re.sub(r"[^A-Za-z0-9_:/@.\-]+", "_", raw).strip("_")


def _sanitize_route(value: Any) -> str:
    raw = str(value or "").strip()
    raw = raw.split("#", 1)[0].split("?", 1)[0]
    if not raw.startswith("/"):
        raw = "/" + raw if raw else ""
    return raw[:MAX_ROUTE_LENGTH]


def _safe_int(value: Any, min_value: int = 0, max_value: int = 86_400_000) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return max(min_value, min(number, max_value))


def _parse_occurred_at(value: Any) -> datetime:
    now = _utcnow()
    if not value:
        return now
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError):
        return now
    if parsed < now - timedelta(days=MAX_EVENT_AGE_DAYS) or parsed > now + timedelta(minutes=5):
        return now
    return parsed


def sanitize_client_event(payload: dict[str, Any]) -> SanitizedClientEvent:
    if not isinstance(payload, dict):
        raise ValueError("event_must_be_object")
    if _contains_forbidden_key(payload):
        raise ValueError("event_contains_forbidden_sensitive_key")

    event_type = _sanitize_identifier(payload.get("event_type") or payload.get("type"), 80)
    if event_type not in CLIENT_EVENT_TYPES:
        raise ValueError("event_type_not_allowed")

    raw_metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    metadata: dict[str, Any] = {}
    for key in sorted(raw_metadata.keys())[:MAX_METADATA_KEYS]:
        normalized_key = str(key).strip().lower()
        if normalized_key not in ALLOWED_METADATA_KEYS:
            continue
        value = raw_metadata.get(key)
        if normalized_key in {"duration_ms", "visible_seconds", "status_code"}:
            metadata[normalized_key] = _safe_int(value, max_value=86_400_000)
        else:
            metadata[normalized_key] = _sanitize_identifier(value, MAX_ACTION_LENGTH)

    route = _sanitize_route(payload.get("route") or metadata.get("route"))
    surface = _sanitize_identifier(payload.get("surface") or metadata.get("surface"), MAX_SURFACE_LENGTH)
    duration_ms = _safe_int(payload.get("duration_ms") or metadata.get("duration_ms"))
    occurred_at = _parse_occurred_at(payload.get("occurred_at"))
    session_id = _sanitize_identifier(payload.get("session_id") or payload.get("session"), 160)

    return SanitizedClientEvent(
        event_type=event_type,
        route=route,
        surface=surface,
        occurred_at=occurred_at,
        duration_ms=duration_ms,
        metadata={key: value for key, value in metadata.items() if value not in (None, "")},
        session_id=session_id,
    )


def _session_hash(org_id: int, user_id: int | None, session_id: str) -> str:
    secret = (getattr(settings, "SECRET_KEY", "") or "casehub-work-intelligence").encode()
    msg = f"{org_id}:{user_id or 0}:{session_id or ''}".encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def record_client_events(
    db: Session,
    *,
    org_id: int,
    user: Any,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    if not is_client_events_enabled(db, org_id):
        return {"accepted": 0, "rejected": 0, "status": "disabled"}
    if is_excluded_user(user):
        return {"accepted": 0, "rejected": 0, "status": "excluded_user"}

    accepted = 0
    rejected = 0
    user_id = getattr(user, "id", None)
    for payload in (events or [])[:MAX_BATCH_EVENTS]:
        try:
            event = sanitize_client_event(payload)
        except ValueError:
            rejected += 1
            continue
        db.execute(
            text(
                """
                INSERT INTO work_intelligence_events
                    (org_id, user_id, event_type, route, surface, duration_ms,
                     metadata, source, session_hash, occurred_at, created_at)
                VALUES
                    (:org_id, :user_id, :event_type, :route, :surface, :duration_ms,
                     :metadata, 'client', :session_hash, :occurred_at, CURRENT_TIMESTAMP)
                """
            ),
            {
                "org_id": org_id,
                "user_id": user_id,
                "event_type": event.event_type,
                "route": event.route,
                "surface": event.surface,
                "duration_ms": event.duration_ms,
                "metadata": _json_dumps(event.metadata),
                "session_hash": _session_hash(org_id, user_id, event.session_id),
                "occurred_at": event.occurred_at,
            },
        )
        accepted += 1
    db.commit()
    return {"accepted": accepted, "rejected": rejected, "status": "ok"}


def _source_scope_params(org_id: int, since: datetime, excluded_ids: set[int]) -> dict[str, Any]:
    return {"org_id": org_id, "since": since, "excluded_ids": tuple(excluded_ids or {-1})}


def _audit_summary(db: Session, org_id: int, since: datetime, excluded_ids: set[int]) -> dict[str, Any]:
    if not _table_exists(db, "audit_log"):
        return {"total": 0, "by_action": {}, "by_entity": {}}
    rows = _mappings(
        db,
        """
        SELECT action, entity_type, COUNT(*) AS count
        FROM audit_log
        WHERE org_id = :org_id
          AND created_at >= :since
          AND (user_id IS NULL OR user_id NOT IN :excluded_ids)
        GROUP BY action, entity_type
        """,
        _source_scope_params(org_id, since, excluded_ids),
    )
    by_action: Counter[str] = Counter()
    by_entity: Counter[str] = Counter()
    for row in rows:
        count = int(row.get("count") or 0)
        by_action[str(row.get("action") or "unknown")] += count
        by_entity[str(row.get("entity_type") or "unknown")] += count
    return {
        "total": sum(by_action.values()),
        "by_action": dict(by_action),
        "by_entity": dict(by_entity),
    }


def _tasks_summary(db: Session, org_id: int, since: datetime, excluded_ids: set[int]) -> dict[str, Any]:
    if not _table_exists(db, "tasks"):
        return {"total": 0, "completed": 0, "overdue": 0, "wip": 0, "by_status": {}}
    rows = _mappings(
        db,
        """
        SELECT status, COUNT(*) AS count
        FROM tasks
        WHERE org_id = :org_id
          AND created_at >= :since
          AND (assigned_to IS NULL OR assigned_to NOT IN :excluded_ids)
        GROUP BY status
        """,
        _source_scope_params(org_id, since, excluded_ids),
    )
    by_status = {str(row.get("status") or "unknown"): int(row.get("count") or 0) for row in rows}
    overdue = int(
        _scalar(
            db,
            """
            SELECT COUNT(*)
            FROM tasks
            WHERE org_id = :org_id
              AND due_date < CURRENT_DATE
              AND COALESCE(status, '') != 'completed'
              AND (assigned_to IS NULL OR assigned_to NOT IN :excluded_ids)
            """,
            _source_scope_params(org_id, since, excluded_ids),
            0,
        )
    )
    completed = sum(count for status, count in by_status.items() if status in {"completed", "done", "concluido"})
    total = sum(by_status.values())
    return {
        "total": total,
        "completed": completed,
        "overdue": overdue,
        "wip": total - completed,
        "by_status": by_status,
    }


def _prazos_summary(db: Session, org_id: int, since: datetime, excluded_ids: set[int]) -> dict[str, Any]:
    if not _table_exists(db, "prazos_processuais"):
        return {"total": 0, "concluded": 0, "overdue": 0, "upcoming_7d": 0}
    params = _source_scope_params(org_id, since, excluded_ids)
    params["today"] = date.today()
    params["upcoming_end"] = date.today() + timedelta(days=7)
    total = int(
        _scalar(
            db,
            """
            SELECT COUNT(*)
            FROM prazos_processuais
            WHERE org_id = :org_id
              AND (created_at >= :since OR data_vencimento >= CURRENT_DATE)
              AND (responsavel_user_id IS NULL OR responsavel_user_id NOT IN :excluded_ids)
            """,
            params,
            0,
        )
    )
    concluded = int(
        _scalar(
            db,
            """
            SELECT COUNT(*)
            FROM prazos_processuais
            WHERE org_id = :org_id
              AND (status IN ('concluido', 'concluida', 'done', 'completed') OR data_conclusao IS NOT NULL)
              AND (responsavel_user_id IS NULL OR responsavel_user_id NOT IN :excluded_ids)
            """,
            params,
            0,
        )
    )
    overdue = int(
        _scalar(
            db,
            """
            SELECT COUNT(*)
            FROM prazos_processuais
            WHERE org_id = :org_id
              AND data_vencimento < :today
              AND COALESCE(status, '') NOT IN ('concluido', 'concluida', 'done', 'completed')
              AND (responsavel_user_id IS NULL OR responsavel_user_id NOT IN :excluded_ids)
            """,
            params,
            0,
        )
    )
    upcoming = int(
        _scalar(
            db,
            """
            SELECT COUNT(*)
            FROM prazos_processuais
            WHERE org_id = :org_id
              AND data_vencimento >= :today
              AND data_vencimento <= :upcoming_end
              AND COALESCE(status, '') NOT IN ('concluido', 'concluida', 'done', 'completed')
              AND (responsavel_user_id IS NULL OR responsavel_user_id NOT IN :excluded_ids)
            """,
            params,
            0,
        )
    )
    return {"total": total, "concluded": concluded, "overdue": overdue, "upcoming_7d": upcoming}


def _time_entries_summary(db: Session, org_id: int, since: datetime, excluded_ids: set[int]) -> dict[str, Any]:
    if not _table_exists(db, "time_entries"):
        return {"entries": 0, "hours": 0.0}
    rows = _mappings(
        db,
        """
        SELECT COUNT(*) AS entries, COALESCE(SUM(hours), 0) AS hours
        FROM time_entries
        WHERE org_id = :org_id
          AND date >= :since_date
          AND (user_id IS NULL OR user_id NOT IN :excluded_ids)
        """,
        {
            "org_id": org_id,
            "since_date": since.date(),
            "excluded_ids": tuple(excluded_ids or {-1}),
        },
    )
    row = rows[0] if rows else {}
    hours = row.get("hours") or 0
    if isinstance(hours, Decimal):
        hours = float(hours)
    return {"entries": int(row.get("entries") or 0), "hours": float(hours)}


def _client_events_summary(db: Session, org_id: int, since: datetime, excluded_ids: set[int]) -> dict[str, Any]:
    if not _table_exists(db, "work_intelligence_events"):
        return {"total": 0, "by_type": {}, "by_route": {}, "errors": 0, "abandonments": 0}
    rows = _mappings(
        db,
        """
        SELECT event_type, route, COUNT(*) AS count
        FROM work_intelligence_events
        WHERE org_id = :org_id
          AND occurred_at >= :since
          AND (user_id IS NULL OR user_id NOT IN :excluded_ids)
        GROUP BY event_type, route
        """,
        _source_scope_params(org_id, since, excluded_ids),
    )
    by_type: Counter[str] = Counter()
    by_route: Counter[str] = Counter()
    for row in rows:
        count = int(row.get("count") or 0)
        event_type = str(row.get("event_type") or "unknown")
        route = str(row.get("route") or "unknown")
        by_type[event_type] += count
        if route != "unknown":
            by_route[route] += count
    errors = by_type.get("api_error", 0) + by_type.get("ui_error", 0)
    return {
        "total": sum(by_type.values()),
        "by_type": dict(by_type),
        "by_route": dict(by_route.most_common(10)),
        "errors": errors,
        "abandonments": by_type.get("flow_abandon", 0),
    }


def _real_user_count(db: Session, org_id: int, excluded_ids: set[int]) -> int:
    if not _table_exists(db, "users"):
        return 0
    return int(
        _scalar(
            db,
            """
            SELECT COUNT(*)
            FROM users
            WHERE org_id = :org_id
              AND enabled = TRUE
              AND id NOT IN :excluded_ids
            """,
            {"org_id": org_id, "excluded_ids": tuple(excluded_ids or {-1})},
            0,
        )
    )


def _score(summary: dict[str, Any]) -> dict[str, float]:
    tasks = summary["sources"]["tasks"]
    prazos = summary["sources"]["prazos"]
    events = summary["sources"]["client_events"]
    audit = summary["sources"]["audit"]
    active_users = max(int(summary.get("active_real_users") or 0), 1)

    task_total = max(tasks.get("total", 0), 1)
    event_total = max(events.get("total", 0), 1)
    overdue_pressure = (tasks.get("overdue", 0) + prazos.get("overdue", 0)) / max(task_total + prazos.get("total", 0), 1)
    error_pressure = events.get("errors", 0) / event_total
    abandonment_pressure = events.get("abandonments", 0) / event_total
    reopen_pressure = (
        audit.get("by_action", {}).get("reopen", 0)
        + audit.get("by_action", {}).get("auto_update", 0) * 0.05
    ) / max(audit.get("total", 0), 1)
    wip_per_user = tasks.get("wip", 0) / active_users

    friction = min(100.0, (overdue_pressure * 35) + (error_pressure * 25) + (abandonment_pressure * 20) + (reopen_pressure * 20))
    demand_resource = min(100.0, (wip_per_user * 8) + (prazos.get("upcoming_7d", 0) / active_users * 10))
    fragmentation = min(100.0, len(events.get("by_route", {})) * 6 + events.get("abandonments", 0) * 3)
    quality = max(0.0, 100.0 - friction - (reopen_pressure * 25))
    return {
        "friction_index": round(friction, 2),
        "demand_resource_balance": round(demand_resource, 2),
        "fragmentation_signal": round(fragmentation, 2),
        "quality_guard": round(quality, 2),
    }


def generate_insights(summary: dict[str, Any]) -> list[dict[str, Any]]:
    if summary.get("suppressed"):
        return []

    scores = summary.get("scores", {})
    tasks = summary["sources"]["tasks"]
    prazos = summary["sources"]["prazos"]
    events = summary["sources"]["client_events"]
    insights: list[dict[str, Any]] = []

    if scores.get("friction_index", 0) >= 25:
        insights.append(
            {
                "category": "friction",
                "severity": "attention",
                "title": "Friccao operacional acima do normal",
                "body": "O agregado indica atrasos, erros ou abandono de fluxo suficientes para revisar o processo antes de cobrar volume individual.",
                "evidence": {
                    "friction_index": scores.get("friction_index"),
                    "ui_api_errors": events.get("errors"),
                    "flow_abandonments": events.get("abandonments"),
                },
                "source_refs": ["work_intelligence_events", "audit_log"],
            }
        )

    if tasks.get("overdue", 0) or prazos.get("overdue", 0):
        insights.append(
            {
                "category": "deadline_pressure",
                "severity": "risk",
                "title": "Pressao de prazo aparece no fluxo agregado",
                "body": "Ha tarefas ou prazos vencidos no tenant. A resposta recomendada e redistribuir fila, reduzir WIP e melhorar suporte/template antes de ampliar demanda.",
                "evidence": {
                    "tasks_overdue": tasks.get("overdue", 0),
                    "prazos_overdue": prazos.get("overdue", 0),
                    "prazos_next_7d": prazos.get("upcoming_7d", 0),
                },
                "source_refs": ["tasks", "prazos_processuais"],
            }
        )

    if scores.get("demand_resource_balance", 0) >= 35:
        insights.append(
            {
                "category": "demand_resource_balance",
                "severity": "attention",
                "title": "Demanda pode estar acima dos recursos disponiveis",
                "body": "WIP e prazos proximos sugerem necessidade de recurso concreto: responsavel claro, template, automacao ou apoio de equipe.",
                "evidence": {
                    "demand_resource_balance": scores.get("demand_resource_balance"),
                    "wip": tasks.get("wip"),
                    "active_real_users": summary.get("active_real_users"),
                },
                "source_refs": ["tasks", "prazos_processuais"],
            }
        )

    if scores.get("fragmentation_signal", 0) >= 30:
        insights.append(
            {
                "category": "fragmentation",
                "severity": "info",
                "title": "Alternancia entre fluxos merece investigacao",
                "body": "A navegacao agregada indica muitas retomadas ou abandono. O Maestro deve sugerir simplificacao de rotina, nao inferir estado mental.",
                "evidence": {
                    "fragmentation_signal": scores.get("fragmentation_signal"),
                    "top_routes": events.get("by_route", {}),
                },
                "source_refs": ["work_intelligence_events"],
            }
        )

    return insights[:6]


def build_summary(
    db: Session,
    *,
    org_id: int,
    days: int = 7,
    user: Any = None,
    include_disabled: bool = False,
    min_group_size: int = MIN_GROUP_SIZE,
) -> dict[str, Any]:
    days = max(1, min(int(days or 7), 31))
    enabled = is_work_intelligence_enabled(db, org_id)
    client_events_enabled = is_client_events_enabled(db, org_id)
    collection_policy = collection_policy_payload(db, org_id)
    if not enabled and not include_disabled:
        return {
            "enabled": False,
            "client_events_enabled": False,
            "suppressed": True,
            "reason": "feature_disabled",
            "collection_policy": collection_policy,
        }

    since = _utcnow() - timedelta(days=days)
    excluded_ids = excluded_user_ids(db, org_id)
    active_real_users = _real_user_count(db, org_id, excluded_ids)
    suppressed = active_real_users < min_group_size

    sources = {
        "audit": _audit_summary(db, org_id, since, excluded_ids),
        "tasks": _tasks_summary(db, org_id, since, excluded_ids),
        "prazos": _prazos_summary(db, org_id, since, excluded_ids),
        "time_entries": _time_entries_summary(db, org_id, since, excluded_ids),
        "client_events": _client_events_summary(db, org_id, since, excluded_ids),
    }
    summary = {
        "enabled": enabled,
        "client_events_enabled": client_events_enabled,
        "generated_at": _utcnow().isoformat(timespec="seconds") + "Z",
        "window_days": days,
        "org_id": org_id,
        "active_real_users": active_real_users,
        "excluded_user_count": len(excluded_ids),
        "suppressed": suppressed,
        "suppression_reason": "group_too_small" if suppressed else "",
        "min_group_size": min_group_size,
        "sources": sources if not suppressed else {},
        "scores": {},
        "insights": [],
        "collection_policy": collection_policy,
    }
    if suppressed:
        return summary
    summary["scores"] = _score(summary)
    summary["insights"] = generate_insights(summary)
    return summary


def collection_policy_payload(db: Session, org_id: int | None) -> dict[str, Any]:
    tenant_settings = tenant_work_intelligence_settings(db, int(org_id)) if org_id else {}
    return {
        "work_intelligence_enabled": bool(getattr(settings, "CASEHUB_WORK_INTELLIGENCE_ENABLED", False))
        and _boolish(tenant_settings.get("work_intelligence_enabled")),
        "client_events_enabled": bool(getattr(settings, "CASEHUB_WORK_INTELLIGENCE_CLIENT_EVENTS_ENABLED", False))
        and _boolish(tenant_settings.get("work_intelligence_client_events_enabled")),
        "collected_categories": [
            "rotas navegadas",
            "duracao ativa aproximada",
            "visibilidade da pagina",
            "erros de UI/API sem corpo de resposta",
            "acoes semanticas de botoes/rotas",
            "abandono de fluxo",
            "auditoria de CRUD ja existente",
            "tarefas, prazos e lancamentos de tempo agregados",
        ],
        "not_collected": [
            "teclas",
            "texto digitado",
            "coordenadas de cursor",
            "screenshot",
            "gravacao de tela",
            "clipboard",
            "DOM bruto",
            "conteudo de mensagens",
        ],
        "purpose": "melhoria de processo, reducao de friccao operacional e protecao de qualidade do trabalho",
        "disciplinary_use": False,
    }


def build_maestro_context(db: Session, *, org_id: int, user: Any = None, days: int = 7) -> str:
    if not is_work_intelligence_enabled(db, org_id):
        return ""
    summary = build_summary(db, org_id=org_id, days=days, user=user)
    if summary.get("suppressed"):
        return (
            "\n\nWork Intelligence (agregado): ativo, mas omitido do prompt porque "
            f"a coorte real tem menos de {summary.get('min_group_size', MIN_GROUP_SIZE)} usuarios. "
            "Nao inferir produtividade individual."
        )
    lines = [
        "\n\nWork Intelligence (agregado, redigido, sem log cru):",
        f"- Janela: ultimos {summary.get('window_days')} dias; usuarios reais ativos: {summary.get('active_real_users')}; dev/QA/automacoes excluidos: {summary.get('excluded_user_count')}.",
    ]
    scores = summary.get("scores") or {}
    if scores:
        lines.append(
            "- Indices: friccao={friction_index}; demanda/recurso={demand_resource_balance}; fragmentacao={fragmentation_signal}; qualidade={quality_guard}.".format(
                **scores
            )
        )
    insights = summary.get("insights") or []
    if insights:
        lines.append("- Insights explicaveis:")
        for item in insights[:4]:
            lines.append(
                f"  * {item['title']} ({item['category']}/{item['severity']}): {item['body']}"
            )
    lines.append(
        "- Politica: sugerir redistribuicao, template, treinamento ou automacao; nao criar ranking individual, dossie ou conclusao disciplinar."
    )
    return "\n".join(lines)


def refresh_daily_metrics(db: Session, *, org_id: int, metric_day: date | None = None) -> dict[str, Any]:
    metric_day = metric_day or date.today()
    summary = build_summary(
        db,
        org_id=org_id,
        days=1,
        include_disabled=True,
        min_group_size=1,
    )
    if summary.get("suppressed"):
        return {"stored": 0, "suppressed": True}

    db.execute(
        text(
            """
            DELETE FROM work_intelligence_daily_metrics
            WHERE org_id = :org_id AND metric_date = :metric_date
            """
        ),
        {"org_id": org_id, "metric_date": metric_day},
    )
    scores = summary.get("scores") or {}
    sources = summary.get("sources") or {}
    tasks = sources.get("tasks", {})
    events = sources.get("client_events", {})
    db.execute(
        text(
            """
            INSERT INTO work_intelligence_daily_metrics
                (org_id, metric_date, workflow, module, team_key, active_users,
                 event_count, completed_count, error_count, backlog_count,
                 overdue_count, friction_index, demand_resource_score,
                 fragmentation_signal, quality_signal, metrics_json, sources_json,
                 created_at, updated_at)
            VALUES
                (:org_id, :metric_date, 'office_flow', 'aggregate', 'org',
                 :active_users, :event_count, :completed_count, :error_count,
                 :backlog_count, :overdue_count, :friction_index,
                 :demand_resource_score, :fragmentation_signal, :quality_signal,
                 :metrics_json, :sources_json, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        ),
        {
            "org_id": org_id,
            "metric_date": metric_day,
            "active_users": summary.get("active_real_users") or 0,
            "event_count": events.get("total") or 0,
            "completed_count": tasks.get("completed") or 0,
            "error_count": events.get("errors") or 0,
            "backlog_count": tasks.get("wip") or 0,
            "overdue_count": (tasks.get("overdue") or 0) + (sources.get("prazos", {}).get("overdue") or 0),
            "friction_index": scores.get("friction_index") or 0,
            "demand_resource_score": scores.get("demand_resource_balance") or 0,
            "fragmentation_signal": scores.get("fragmentation_signal") or 0,
            "quality_signal": scores.get("quality_guard") or 0,
            "metrics_json": _json_dumps(scores),
            "sources_json": _json_dumps({"source_tables": list(sources.keys())}),
        },
    )
    db.commit()
    return {"stored": 1, "suppressed": False}


def backfill_current_week(db: Session, *, org_id: int) -> dict[str, Any]:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    stored = 0
    suppressed = 0
    current = monday
    while current <= today:
        result = refresh_daily_metrics(db, org_id=org_id, metric_day=current)
        stored += int(result.get("stored") or 0)
        suppressed += 1 if result.get("suppressed") else 0
        current += timedelta(days=1)
    return {"stored_days": stored, "suppressed_days": suppressed, "week_start": monday.isoformat()}


def _redact_free_text(value: Any, limit: int = 500) -> str:
    text_value = str(value or "")[:limit]
    for pattern, replacement in TEXT_REDACTIONS:
        text_value = pattern.sub(replacement, text_value)
    return text_value


def record_feedback(
    db: Session,
    *,
    org_id: int,
    user_id: int | None,
    insight_id: int | None,
    feedback_type: str,
    usefulness: int | None = None,
    comment: str = "",
) -> dict[str, Any]:
    feedback = _sanitize_identifier(feedback_type, 40) or "comment"
    bounded_usefulness = _safe_int(usefulness, min_value=1, max_value=5)
    db.execute(
        text(
            """
            INSERT INTO work_intelligence_feedback
                (org_id, user_id, insight_id, feedback_type, usefulness,
                 comment_redacted, created_at)
            VALUES
                (:org_id, :user_id, :insight_id, :feedback_type, :usefulness,
                 :comment_redacted, CURRENT_TIMESTAMP)
            """
        ),
        {
            "org_id": org_id,
            "user_id": user_id,
            "insight_id": insight_id,
            "feedback_type": feedback,
            "usefulness": bounded_usefulness,
            "comment_redacted": _redact_free_text(comment),
        },
    )
    db.commit()
    return {"ok": True}


def user_transparency_payload(db: Session, *, org_id: int, user: Any) -> dict[str, Any]:
    user_id = getattr(user, "id", None)
    policy = collection_policy_payload(db, org_id)
    categories = {}
    if user_id and _table_exists(db, "work_intelligence_events"):
        rows = _mappings(
            db,
            """
            SELECT event_type, COUNT(*) AS count
            FROM work_intelligence_events
            WHERE org_id = :org_id AND user_id = :user_id
            GROUP BY event_type
            """,
            {"org_id": org_id, "user_id": user_id},
        )
        categories = {str(row.get("event_type")): int(row.get("count") or 0) for row in rows}
    return {
        "excluded": is_excluded_user(user),
        "policy": policy,
        "event_categories": categories,
        "raw_event_access": False,
        "can_contest": True,
    }


def mcp_summary_payload(db: Session, *, org_id: int, days: int = 7) -> dict[str, Any]:
    summary = build_summary(db, org_id=org_id, days=days)
    summary.pop("org_id", None)
    return {
        "kind": "casehub.work_intelligence.summary",
        "summary": summary,
        "privacy": {
            "raw_logs_included": False,
            "individual_ranking": False,
            "small_group_suppression": True,
        },
    }
