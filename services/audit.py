"""
CaseHub - Audit Logging Service
Logs user actions to the audit_log table for monitoring.

Includes:
  - Manual logging helpers (log_action, log_login, etc.)
  - SQLAlchemy event listeners for automatic CRUD audit on all models
"""
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from contextvars import ContextVar
from sqlalchemy import text, event, inspect
from sqlalchemy.orm import Session
from fastapi import Request

logger = logging.getLogger(__name__)

# Context variables to carry request info into SQLAlchemy event handlers
# These are set by AuditContextMiddleware (see setup_audit_middleware)
_audit_user_id: ContextVar[Optional[int]] = ContextVar("audit_user_id", default=None)
_audit_user_email: ContextVar[Optional[str]] = ContextVar("audit_user_email", default=None)
_audit_org_id: ContextVar[Optional[int]] = ContextVar("audit_org_id", default=None)
_audit_ip: ContextVar[Optional[str]] = ContextVar("audit_ip", default=None)
_audit_user_agent: ContextVar[Optional[str]] = ContextVar("audit_user_agent", default=None)


def log_action(
    db: Session,
    action: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    user_id: Optional[int] = None,
    user_email: Optional[str] = None,
    description: str = "",
    details: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None
):
    """
    Log an action to the audit_log table.

    Args:
        db: Database session
        action: Action type (login, create, update, delete, etc.)
        entity_type: Type of entity (user, client, case, email, etc.)
        entity_id: ID of the entity (optional)
        user_id: ID of the user performing the action
        user_email: Email of the user performing the action
        description: Human-readable description of the action
        details: Additional JSON details
        request: FastAPI request object for IP/user-agent
    """
    try:
        ip_address = None
        user_agent = None

        if request:
            # Get client IP (handle proxy headers)
            ip_address = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            if not ip_address:
                ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent", "")[:500]  # Limit length

        db.execute(text("""
            INSERT INTO audit_log (
                action, entity_type, entity_id, user_id, user_email,
                description, details, ip_address, user_agent, created_at
            )
            VALUES (
                :action, :entity_type, :entity_id, :user_id, :user_email,
                :description, :details, :ip_address, :user_agent, NOW()
            )
        """), {
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "user_id": user_id,
            "user_email": user_email,
            "description": description,
            "details": json.dumps(details) if details else None,
            "ip_address": ip_address,
            "user_agent": user_agent,
        })
        db.commit()

    except Exception as e:
        logger.critical(f"AUDIT LOGGING FAILED: {e}")
        # Don't raise - audit logging should never break the main flow


def log_login(db: Session, user_id: int, user_email: str, success: bool, request: Request = None):
    """Log a login attempt"""
    log_action(
        db=db,
        action="login_success" if success else "login_failed",
        entity_type="user",
        entity_id=user_id,
        user_id=user_id,
        user_email=user_email,
        description=f"User {'logged in successfully' if success else 'failed to log in'}",
        request=request
    )


def log_password_change(db: Session, user_id: int, user_email: str, request: Request = None):
    """Log a password change"""
    log_action(
        db=db,
        action="password_change",
        entity_type="user",
        entity_id=user_id,
        user_id=user_id,
        user_email=user_email,
        description="User changed their password",
        request=request
    )


def log_entity_create(db: Session, entity_type: str, entity_id: int,
                      user_id: int, user_email: str, entity_name: str = "",
                      request: Request = None):
    """Log entity creation (client, case, etc.)"""
    log_action(
        db=db,
        action="create",
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        user_email=user_email,
        description=f"Created {entity_type}: {entity_name}",
        request=request
    )


def log_entity_update(db: Session, entity_type: str, entity_id: int,
                      user_id: int, user_email: str, entity_name: str = "",
                      changes: Dict[str, Any] = None, request: Request = None):
    """Log entity update"""
    log_action(
        db=db,
        action="update",
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        user_email=user_email,
        description=f"Updated {entity_type}: {entity_name}",
        details={"changes": changes} if changes else None,
        request=request
    )


def log_entity_delete(db: Session, entity_type: str, entity_id: int,
                      user_id: int, user_email: str, entity_name: str = "",
                      request: Request = None):
    """Log entity deletion"""
    log_action(
        db=db,
        action="delete",
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        user_email=user_email,
        description=f"Deleted {entity_type}: {entity_name}",
        request=request
    )


# ==========================================================================
# SQLAlchemy Event Listeners - Automatic CRUD Audit
# ==========================================================================

# Tables to skip auditing (internal / high-volume tables)
_SKIP_TABLES = {"audit_log", "password_reset_tokens", "backup_codes", "sso_states"}

# Sensitive columns whose values should be redacted
_REDACTED_COLUMNS = {"password_hash", "totp_secret", "smtp_pass", "access_token", "refresh_token"}


def _serialize_value(val):
    """Convert a value to a JSON-safe representation."""
    if val is None:
        return None
    if isinstance(val, (str, int, float, bool)):
        return val
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


def _get_entity_id(instance):
    """Try to get the primary key of an ORM instance."""
    mapper = inspect(type(instance))
    pk_cols = mapper.primary_key
    if pk_cols:
        return getattr(instance, pk_cols[0].name, None)
    return None


def _write_audit_row(session, action, entity_type, entity_id, old_value, new_value, description=""):
    """Write an audit log row using a raw INSERT (to avoid recursive triggers)."""
    try:
        user_id = _audit_user_id.get()
        user_email = _audit_user_email.get()
        ip_address = _audit_ip.get()
        user_agent = _audit_user_agent.get()
        org_id = _audit_org_id.get()

        details = {}
        if old_value:
            details["old_value"] = old_value
        if new_value:
            details["new_value"] = new_value

        session.execute(text("""
            INSERT INTO audit_log (
                action, entity_type, entity_id, user_id, user_email,
                description, details, ip_address, user_agent, created_at
            )
            VALUES (
                :action, :entity_type, :entity_id, :user_id, :user_email,
                :description, :details, :ip_address, :user_agent, NOW()
            )
        """), {
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "user_id": user_id,
            "user_email": user_email,
            "description": description,
            "details": json.dumps(details) if details else None,
            "ip_address": ip_address,
            "user_agent": user_agent,
        })
    except Exception as e:
        logger.debug(f"Auto-audit write failed (non-fatal): {e}")


def _after_insert(mapper, connection, target):
    """SQLAlchemy after_insert event handler."""
    table_name = target.__tablename__
    if table_name in _SKIP_TABLES:
        return

    entity_id = _get_entity_id(target)

    # Build new_value dict from all columns
    new_value = {}
    for col in inspect(type(target)).columns:
        col_name = col.key
        if col_name in _REDACTED_COLUMNS:
            new_value[col_name] = "***REDACTED***"
        else:
            new_value[col_name] = _serialize_value(getattr(target, col_name, None))

    # Use the connection's underlying session to write (same transaction)
    from sqlalchemy.orm import Session as OrmSession
    session = OrmSession.object_session(target)
    if session:
        _write_audit_row(
            session,
            action="auto_create",
            entity_type=table_name,
            entity_id=entity_id,
            old_value=None,
            new_value=new_value,
            description=f"Created {table_name} #{entity_id}",
        )


def _after_update(mapper, connection, target):
    """SQLAlchemy after_update event handler."""
    table_name = target.__tablename__
    if table_name in _SKIP_TABLES:
        return

    entity_id = _get_entity_id(target)
    insp = inspect(target)

    old_value = {}
    new_value = {}
    changed = False

    for attr in insp.attrs:
        hist = attr.history
        if hist.has_changes():
            col_name = attr.key
            if col_name in _REDACTED_COLUMNS:
                old_value[col_name] = "***REDACTED***"
                new_value[col_name] = "***REDACTED***"
            else:
                old_val = hist.deleted[0] if hist.deleted else None
                new_val = hist.added[0] if hist.added else None
                old_value[col_name] = _serialize_value(old_val)
                new_value[col_name] = _serialize_value(new_val)
            changed = True

    if not changed:
        return

    from sqlalchemy.orm import Session as OrmSession
    session = OrmSession.object_session(target)
    if session:
        _write_audit_row(
            session,
            action="auto_update",
            entity_type=table_name,
            entity_id=entity_id,
            old_value=old_value,
            new_value=new_value,
            description=f"Updated {table_name} #{entity_id}: {', '.join(old_value.keys())}",
        )


def _after_delete(mapper, connection, target):
    """SQLAlchemy after_delete event handler."""
    table_name = target.__tablename__
    if table_name in _SKIP_TABLES:
        return

    entity_id = _get_entity_id(target)

    old_value = {}
    for col in inspect(type(target)).columns:
        col_name = col.key
        if col_name in _REDACTED_COLUMNS:
            old_value[col_name] = "***REDACTED***"
        else:
            old_value[col_name] = _serialize_value(getattr(target, col_name, None))

    from sqlalchemy.orm import Session as OrmSession
    session = OrmSession.object_session(target)
    if session:
        _write_audit_row(
            session,
            action="auto_delete",
            entity_type=table_name,
            entity_id=entity_id,
            old_value=old_value,
            new_value=None,
            description=f"Deleted {table_name} #{entity_id}",
        )


def setup_audit_listeners(base_class):
    """
    Register SQLAlchemy event listeners on all mapped models that inherit from Base.

    Call this once after all models are imported, e.g. in app startup:

        from models.base import Base
        from services.audit import setup_audit_listeners
        setup_audit_listeners(Base)
    """
    for mapper in base_class.registry.mappers:
        cls = mapper.class_
        table_name = getattr(cls, "__tablename__", None)
        if table_name and table_name not in _SKIP_TABLES:
            event.listen(cls, "after_insert", _after_insert)
            event.listen(cls, "after_update", _after_update)
            event.listen(cls, "after_delete", _after_delete)
    logger.info("Audit event listeners registered on all models")


def set_audit_context(
    user_id: Optional[int] = None,
    user_email: Optional[str] = None,
    org_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
):
    """
    Set the audit context for the current request (via context variables).
    Called by AuditContextMiddleware or manually in background tasks.
    """
    _audit_user_id.set(user_id)
    _audit_user_email.set(user_email)
    _audit_org_id.set(org_id)
    _audit_ip.set(ip_address)
    _audit_user_agent.set(user_agent)
