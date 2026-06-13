"""
CaseHub - Email module access gate (gestor-only)

The Emails module is restricted to managers (``user_type`` in
``admin`` / ``superadmin``). Non-managers (attorney, paralegal,
case_worker, staff, ...) do NOT get a raw 403; instead the main list
page renders a friendly "request access" screen with a button that
files an in-app notification to the org's managers.

All gating is server-side and org-scoped. The shared helpers here are
imported by routes/emails.py, emails_compose.py and emails_sync.py so
the rule lives in exactly one place.
"""
import logging
from typing import Optional, Tuple

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_

from auth import get_current_user
from models.user import User
from models.tenant import tenant_query
from core.template_config import templates, PREFIX, inject_org_context

logger = logging.getLogger(__name__)

# Manager roles allowed to use the Emails module.
EMAIL_MANAGER_ROLES = ("admin", "superadmin")


def is_email_manager(user) -> bool:
    """True when the user holds a manager role allowed to use Emails."""
    if not user:
        return False
    user_type = (getattr(user, "user_type", "") or "").lower()
    return user_type in EMAIL_MANAGER_ROLES


def require_email_access(request: Request, db: Session):
    """
    Resolve the current user and enforce the gestor-only gate for HTML pages.

    Returns a tuple ``(user, blocking_response)``:
      * not logged in  -> (None, RedirectResponse to /login)
      * logged, manager -> (user, None)   # proceed
      * logged, non-mgr -> (user, HTMLResponse)  # "request access" screen
    """
    user = get_current_user(request, db)
    if not user:
        return None, RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    if is_email_manager(user):
        return user, None

    # Non-manager: render the request-access screen instead of a bare 403.
    pending = _has_pending_request(request, db, user)
    ctx = {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        **inject_org_context(request, user),
        "already_requested": pending,
    }
    return user, templates.TemplateResponse(
        "app/emails/request_access.html", ctx, status_code=403
    )


def require_email_access_api(request: Request, db: Session):
    """
    API/POST variant of the gate. Returns ``(user, blocking_response)`` where
    blocking_response is a JSON 403 (or login redirect) for non-managers.
    """
    user = get_current_user(request, db)
    if not user:
        return None, RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    if is_email_manager(user):
        return user, None
    return user, JSONResponse(
        status_code=403,
        content={"error": "forbidden", "detail": "Acesso ao e-mail restrito a gestores."},
    )


def _request_title(user) -> str:
    name = (getattr(user, "name", "") or getattr(user, "email", "") or "Um usuário").strip()
    return f"{name} solicitou acesso ao módulo de E-mail"[:255]


def _has_pending_request(request: Request, db: Session, user) -> bool:
    """
    Idempotency check: has this user already filed an *unread* email-access
    request notification recently? Avoids flooding managers on repeat clicks.
    Scoped to the requesting user's org and to the access-request title.
    """
    try:
        from models.notification import Notification

        title = _request_title(user)
        q = (
            db.query(Notification)
            .filter(Notification.notification_type == "email_access_request")
            .filter(Notification.title == title)
            .filter(or_(Notification.is_read == False, Notification.is_read.is_(None)))  # noqa: E712
        )
        org_id = getattr(request.state, "org_id", None)
        if org_id is not None:
            q = q.filter(or_(Notification.org_id == org_id, Notification.org_id.is_(None)))
        return db.query(q.exists()).scalar() or False
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("[EMAIL GATE] pending-request check failed: %s", exc)
        return False


def file_email_access_request(request: Request, db: Session, user) -> Tuple[bool, bool]:
    """
    Create an in-app notification for every manager in the requesting user's
    org. Idempotent: if an unread request from this user already exists, no
    new notifications are created.

    Returns ``(created, already_pending)``.
    """
    from models.notification import Notification
    from services.notifications.in_app import create_notification

    if _has_pending_request(request, db, user):
        return False, True

    org_id = getattr(request.state, "org_id", None)
    title = _request_title(user)
    requester = (getattr(user, "name", "") or getattr(user, "email", "") or "Usuário").strip()
    requester_email = (getattr(user, "email", "") or "").strip()
    message = (
        f"{requester}"
        + (f" ({requester_email})" if requester_email else "")
        + " pediu acesso ao módulo de E-mail. Conceda promovendo o usuário a "
        "gestor (admin) em Admin › Usuários, se apropriado."
    )

    # Managers of this org (org-scoped). Fall back to no recipients silently.
    try:
        managers = (
            tenant_query(db, User, org_id)
            .filter(User.enabled == True)  # noqa: E712
            .filter(User.user_type.in_(EMAIL_MANAGER_ROLES))
            .all()
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("[EMAIL GATE] manager lookup failed: %s", exc)
        managers = []

    created_any = False
    for mgr in managers:
        notif = create_notification(
            db=db,
            user_id=mgr.id,
            title=title,
            notification_type="email_access_request",
            message=message,
            severity="info",
            action_url=f"{PREFIX}/admin/users",
        )
        if notif:
            # Stamp org so the notification stays tenant-scoped.
            if org_id is not None and getattr(notif, "org_id", None) is None:
                notif.org_id = org_id
            created_any = True

    if created_any:
        try:
            db.commit()
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("[EMAIL GATE] commit failed for access request: %s", exc)
            db.rollback()
            return False, False

    return created_any, False
