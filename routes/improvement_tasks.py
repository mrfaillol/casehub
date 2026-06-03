"""
CaseHub - Improvement Tasks API

POST /casehub/api/v1/improvement-tasks    receive task from app.example.com
GET  /casehub/api/v1/improvement-tasks    list tasks (auth required)
GET  /casehub/api/v1/improvement-tasks/{id}  task detail

Default-off: all endpoints return 503 unless CASEHUB_IMPROVEMENT_TASKS_ENABLED=1.
This satisfies the github-vigil governance envelope (no /casehub/api/v1
contract change "live" until secret-store gates exist; activation must be
deliberate via env var on the host).

Auth: HMAC-SHA256 via X-CMD-Ingest-Signature header (preferred for service-to-service)
      OR JWT cookie with admin user (fallback for human ops)

Authority: trabalho-workspace ruling 2026-05-06-cmd-control-center-activation
"""
import hashlib
import hmac
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from models import get_db, User
from models.improvement_task import ImprovementTask
from auth import get_current_user
from config import settings
from services import improvement_task_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/improvement-tasks", tags=["improvement-tasks"])


def _env_or_setting(name: str) -> str:
    value = os.getenv(name)
    if value is not None:
        return value
    return getattr(settings, name, "") or ""


def _is_enabled() -> bool:
    """Default-off feature flag. Operator must export
    CASEHUB_IMPROVEMENT_TASKS_ENABLED=1 to activate the receiver.
    Live env overrides win, while centralized settings keep .env deployments
    aligned with preflight."""
    value = _env_or_setting("CASEHUB_IMPROVEMENT_TASKS_ENABLED")
    return (value or "").lower() in {"1", "true", "yes", "on"}


def _hmac_key() -> Optional[str]:
    return (
        _env_or_setting("CASEHUB_IMPROVEMENT_HMAC_KEY")
        or _env_or_setting("CASEHUB_OPS_HMAC_KEY")
    )


def _verify_hmac(raw_body: bytes, signature: Optional[str]) -> bool:
    key = _hmac_key()
    if not key:
        # Compat mode: no key configured. Caller still needs JWT admin in that case.
        return False
    if not signature or len(signature) < 16:
        return False
    expected = hmac.new(key.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _require_service_auth(request: Request, raw_body: bytes, db: Session) -> str:
    """
    Returns auth method used: 'hmac' or 'jwt-admin'.
    Raises HTTPException 401 if neither is satisfied. Admin-only by design:
    this endpoint never serves non-admin users on the JWT path, even if the
    HMAC key is missing.
    """
    sig = request.headers.get("x-cmd-ingest-signature") or request.headers.get("x-ingest-signature")
    if sig and _verify_hmac(raw_body, sig):
        return "hmac"
    user = get_current_user(request, db)
    if user and user.user_type == "admin":
        return "jwt-admin"
    raise HTTPException(status_code=401, detail="HMAC signature or admin JWT required")


def _require_enabled():
    """Raise 503 when the feature flag is off. Use as a leading guard in handlers."""
    if not _is_enabled():
        raise HTTPException(
            status_code=503,
            detail="improvement-tasks receiver is disabled (set CASEHUB_IMPROVEMENT_TASKS_ENABLED=1 to activate)",
        )


@router.post("")
async def receive_improvement_task(request: Request, db: Session = Depends(get_db)):
    """Receive an improvement task pushed by app.example.com intake-triage."""
    _require_enabled()

    raw_body = await request.body()
    if len(raw_body) > 262144:  # 256KB cap
        raise HTTPException(status_code=413, detail="payload too large (cap: 256KB)")

    auth_method = _require_service_auth(request, raw_body, db)

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid JSON")

    envelope_ref = body.get("envelope_ref") or body.get("id")
    if not envelope_ref or not isinstance(envelope_ref, str) or len(envelope_ref) > 120:
        raise HTTPException(status_code=400, detail="envelope_ref required (string <=120 chars)")

    kind = body.get("kind")
    if not kind or not isinstance(kind, str) or not kind.replace("-", "").isalnum() or kind != kind.lower():
        raise HTTPException(status_code=400, detail="kind required (lowercase ascii [a-z0-9-])")

    title = body.get("title") or body.get("summary") or f"{kind} (untitled)"
    summary = body.get("summary")
    payload = body.get("payload") or {}
    requested_runtime = body.get("requested_runtime")
    skill = body.get("skill")
    priority = body.get("priority", "P2")
    source = body.get("source", "ingest:command-center")
    payload_hash = body.get("payload_hash_sha256") or hashlib.sha256(raw_body).hexdigest()

    # Idempotency: if envelope_ref already exists, return existing
    existing = improvement_task_service.find_by_envelope_ref(db, envelope_ref)
    if existing:
        return JSONResponse(
            {
                "ok": True,
                "task_id": existing.id,
                "status": existing.status,
                "duplicate": True,
                "received_at": existing.received_at.isoformat() if existing.received_at else None,
            },
            status_code=200,
        )

    org_id = None
    if hasattr(request.state, "org_id"):
        org_id = request.state.org_id

    task = improvement_task_service.create_task(
        db,
        envelope_ref=envelope_ref,
        kind=kind,
        title=title,
        summary=summary,
        payload=payload,
        payload_hash_sha256=payload_hash,
        requested_runtime=requested_runtime,
        skill=skill,
        priority=priority,
        source=source,
        org_id=org_id,
    )

    logger.info(
        "improvement_task received: id=%s envelope_ref=%s kind=%s status=%s halt=%s auth=%s",
        task.id, envelope_ref, kind, task.status, task.halt_blocked, auth_method,
    )

    return JSONResponse(
        {
            "ok": True,
            "task_id": task.id,
            "envelope_ref": task.envelope_ref,
            "status": task.status,
            "halt_blocked": task.halt_blocked,
            "received_at": task.received_at.isoformat() if task.received_at else None,
            "dispatch_url": None,  # populated when dispatched
        },
        status_code=201,
    )


@router.get("")
async def list_improvement_tasks(
    request: Request,
    status: Optional[str] = None,
    kind: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """List improvement tasks for the current tenant. Admin-only."""
    _require_enabled()

    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="auth required")
    if user.user_type != "admin":
        raise HTTPException(status_code=403, detail="admin only")

    # Scope by the JWT-bound user.org_id, NOT request.state.org_id:
    # TenantMiddleware honors a caller-supplied X-Org-Id header before the JWT,
    # so request.state is attacker-controllable for any authenticated cookie
    # holder. user.org_id comes from the User model (loaded via JWT email).
    #
    # No "superadmin" role exists in this codebase (UserType is admin/attorney/
    # case_worker/paralegal). The startup-created default admin has NULL
    # org_id, which would otherwise become a cross-tenant view. Reject it here.
    if user.org_id is None:
        raise HTTPException(status_code=403, detail="admin must be scoped to an organization")
    org_id = user.org_id

    # Clamp limit to [1, 500]: negative values would let the caller bypass the
    # cap (SQLite treats LIMIT -1 as unbounded; PostgreSQL errors on negative).
    if limit < 1:
        limit = 1
    if limit > 500:
        limit = 500

    tasks = improvement_task_service.list_by_tenant(
        db, org_id=org_id, status=status, kind=kind, limit=limit
    )
    return JSONResponse([t.to_dict() for t in tasks])


@router.get("/{task_id}")
async def get_improvement_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    """Detail view of a single improvement task. Admin-only, tenant-scoped."""
    _require_enabled()

    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="auth required")
    if user.user_type != "admin":
        raise HTTPException(status_code=403, detail="admin only")

    # Same JWT-bound scoping as list endpoint - see comment there.
    if user.org_id is None:
        raise HTTPException(status_code=403, detail="admin must be scoped to an organization")
    org_id = user.org_id

    query = db.query(ImprovementTask).filter(ImprovementTask.id == task_id)
    query = query.filter(ImprovementTask.org_id == org_id)
    task = query.first()
    if not task:
        raise HTTPException(status_code=404, detail="task not found")

    return JSONResponse(task.to_dict())
