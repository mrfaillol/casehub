"""
CaseHub - RBAC Permissions Middleware
Role-based access control with wildcard permission matching.

Usage:
    from middleware.permissions import require_permission

    @router.get("/cases")
    async def list_cases(user: User = Depends(require_permission("cases.view"))):
        ...
"""
import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from models import get_db, User
from auth import get_current_user_api

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Role -> Permission map
# ---------------------------------------------------------------------------
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "superadmin": ["*"],
    "admin": [
        "org.*", "admin.*", "billing.*", "reports.*", "settings.*",
        "cases.*", "clients.*", "documents.*", "tasks.*", "emails.*",
        "intake.*", "calendar.*",
    ],
    "attorney": [
        "cases.*", "clients.*", "documents.*", "billing.*",
        "reports.view", "tasks.*", "emails.*",
    ],
    "paralegal": [
        "cases.view", "cases.edit", "clients.view", "clients.edit",
        "documents.*", "tasks.*", "intake.*", "emails.view",
    ],
    "case_worker": [
        "cases.view", "cases.edit", "clients.view", "clients.edit",
        "documents.*", "tasks.*", "intake.*", "emails.view",
    ],
    "assistant": [
        "cases.view", "clients.view", "tasks.view", "tasks.edit",
        "calendar.*", "documents.view",
    ],
}


def _permission_matches(granted: str, required: str) -> bool:
    """
    Check whether a single granted permission satisfies the required one.

    Rules:
        "*"          matches everything
        "cases.*"    matches "cases.view", "cases.edit", "cases.delete", etc.
        "cases.view" matches only "cases.view"
    """
    if granted == "*":
        return True
    if granted == required:
        return True
    # Wildcard at the end: "cases.*" should match "cases.<anything>"
    if granted.endswith(".*"):
        prefix = granted[:-1]  # "cases."
        if required.startswith(prefix):
            return True
    return False


def has_permission(role: str, required_permission: str) -> bool:
    """Check if a role has a specific permission."""
    granted_perms = ROLE_PERMISSIONS.get(role, [])
    return any(_permission_matches(g, required_permission) for g in granted_perms)


def _log_access_denied(
    user: Optional[User],
    permission: str,
    request: Optional[Request] = None,
):
    """Log a denied access attempt to the audit log (best-effort)."""
    try:
        from models.base import SessionLocal
        from services.audit import log_action

        db = SessionLocal()
        try:
            log_action(
                db=db,
                action="access_denied",
                entity_type="permission",
                user_id=user.id if user else None,
                user_email=user.email if user else None,
                description=f"Permission denied: {permission} (role={user.user_type if user else 'none'})",
                details={"permission": permission, "role": user.user_type if user else None},
                request=request,
            )
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Failed to audit access denial: {e}")


# ---------------------------------------------------------------------------
# FastAPI dependency factory
# ---------------------------------------------------------------------------
bearer_scheme = HTTPBearer(auto_error=False)


def require_permission(permission: str):
    """
    Returns a FastAPI dependency that enforces the given permission.

    Example:
        @router.get("/cases")
        async def list_cases(user: User = Depends(require_permission("cases.view"))):
            ...
    """

    async def _dependency(
        request: Request,
        credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
        db: Session = Depends(get_db),
    ) -> User:
        # Reuse existing auth to get the user
        user = get_current_user_api(request, credentials, db)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.enabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account disabled",
            )

        role = user.user_type or ""
        if not has_permission(role, permission):
            _log_access_denied(user, permission, request)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}",
            )

        return user

    return _dependency
