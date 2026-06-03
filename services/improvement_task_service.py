"""
CaseHub - Improvement Task Service

Idempotent ingestion of improvement tasks pushed by the external Command Center.
Authority: ruling 2026-05-06-cmd-control-center-activation

Transaction discipline: this module uses db.flush() instead of db.commit().
The get_db() dependency in models/base.py owns the transaction lifecycle
(commit on success, rollback on exception), so we let the request scope
decide when to commit. flush() makes data visible to subsequent queries
within the same session and assigns autoincrement ids.
"""
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy.orm import Session

from models.improvement_task import ImprovementTask


# kinds blocked by casehub HALT (issue #134, template-refactor) - only template-refactor for now
HALT_BLOCKED_KINDS = {"template-refactor"}


def is_halt_blocked(kind: str) -> bool:
    """Return True if the kind is currently blocked by an active HALT."""
    return kind in HALT_BLOCKED_KINDS


def find_by_envelope_ref(db: Session, envelope_ref: str) -> Optional[ImprovementTask]:
    return db.query(ImprovementTask).filter(ImprovementTask.envelope_ref == envelope_ref).first()


def create_task(
    db: Session,
    *,
    envelope_ref: str,
    kind: str,
    title: str,
    summary: Optional[str] = None,
    payload: Optional[dict] = None,
    payload_hash_sha256: Optional[str] = None,
    requested_runtime: Optional[str] = None,
    skill: Optional[str] = None,
    priority: str = "P2",
    source: str = "ingest:command-center",
    org_id: Optional[int] = None,
) -> ImprovementTask:
    """
    Create an improvement_task. Idempotent on envelope_ref:
    if a task with the same envelope_ref already exists, return it unchanged.
    """
    existing = find_by_envelope_ref(db, envelope_ref)
    if existing:
        return existing

    halt_blocked = is_halt_blocked(kind)
    task = ImprovementTask(
        org_id=org_id,
        envelope_ref=envelope_ref,
        source=source,
        requested_runtime=requested_runtime,
        skill=skill,
        kind=kind,
        title=title[:255],
        summary=summary,
        payload=payload,
        payload_hash_sha256=payload_hash_sha256,
        priority=priority if priority in {"P0", "P1", "P2", "P3"} else "P2",
        status="received" if not halt_blocked else "quarantined",
        halt_blocked=halt_blocked,
        failure_reason="HALT active for kind=" + kind if halt_blocked else None,
    )
    db.add(task)
    db.flush()
    db.refresh(task)
    return task


def list_by_tenant(
    db: Session,
    org_id: Optional[int] = None,
    status: Optional[str] = None,
    kind: Optional[str] = None,
    limit: int = 100,
) -> List[ImprovementTask]:
    q = db.query(ImprovementTask)
    if org_id is not None:
        q = q.filter(ImprovementTask.org_id == org_id)
    if status:
        q = q.filter(ImprovementTask.status == status)
    if kind:
        q = q.filter(ImprovementTask.kind == kind)
    return q.order_by(ImprovementTask.received_at.desc()).limit(limit).all()


def mark_dispatched(db: Session, task_id: int, dispatch_url: str) -> Optional[ImprovementTask]:
    task = db.query(ImprovementTask).filter(ImprovementTask.id == task_id).first()
    if not task:
        return None
    task.status = "dispatched"
    task.dispatch_url = dispatch_url[:500]
    task.dispatched_at = datetime.now(timezone.utc)
    db.flush()
    db.refresh(task)
    return task


def mark_completed(db: Session, task_id: int) -> Optional[ImprovementTask]:
    task = db.query(ImprovementTask).filter(ImprovementTask.id == task_id).first()
    if not task:
        return None
    task.status = "done"
    task.completed_at = datetime.now(timezone.utc)
    db.flush()
    db.refresh(task)
    return task


def mark_failed(db: Session, task_id: int, reason: str) -> Optional[ImprovementTask]:
    task = db.query(ImprovementTask).filter(ImprovementTask.id == task_id).first()
    if not task:
        return None
    task.status = "failed"
    task.failure_reason = reason[:1000]
    db.flush()
    db.refresh(task)
    return task
