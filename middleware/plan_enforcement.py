"""
CaseHub - Plan Enforcement Middleware
Checks organization plan limits before allowing resource creation.

Runs after TenantMiddleware so request.state.org is available.
On POST to resource-creation endpoints, counts existing records and
compares against the org's plan limits (max_users, max_clients, etc.).
If the limit is reached, returns 403 with a clear upgrade message.
"""
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from models.base import SessionLocal
from models.tenant import tenant_count
from models import User, Client, Case

logger = logging.getLogger(__name__)

# Map POST endpoints to the model they create and the org column that holds the limit.
# Limit value of -1 (or None) means unlimited.
#
# Spec (Victor, 28/05/2026): usuários ILIMITADOS por enquanto em todos os planos.
# A regra de /admin/users/new fica intencionalmente FORA deste mapa para que o
# cadastro de usuários nunca seja bloqueado, independente de valores legados de
# max_users ainda gravados em organizations. Reativar quando houver limite de
# seats por plano (basta reintroduzir a entrada abaixo).
ENFORCEMENT_RULES = {
    # "/admin/users/new": {  # DISABLED — usuários ilimitados por enquanto
    #     "model": User,
    #     "limit_field": "max_users",
    #     "resource_name": "users",
    # },
    "/clients/new": {
        "model": Client,
        "limit_field": "max_clients",
        "resource_name": "clients",
    },
    "/cases/new": {
        "model": Case,
        "limit_field": "max_cases",
        "resource_name": "cases",
    },
}


class PlanEnforcementMiddleware(BaseHTTPMiddleware):
    """Reject POST requests that would exceed the organization's plan limits."""

    async def dispatch(self, request: Request, call_next):
        # Only enforce on POST (resource creation)
        if request.method != "POST":
            return await call_next(request)

        path = request.url.path

        # Find matching rule (strip trailing slash for consistency)
        normalized = path.rstrip("/")
        rule = None
        for endpoint, r in ENFORCEMENT_RULES.items():
            if normalized.endswith(endpoint.rstrip("/")):
                rule = r
                break

        if rule is None:
            return await call_next(request)

        # Need org context (set by TenantMiddleware)
        org = getattr(getattr(request, "state", None), "org", None)
        if not org:
            return await call_next(request)

        org_id = org.get("id") if isinstance(org, dict) else getattr(org, "id", None)
        if not org_id:
            return await call_next(request)

        limit_field = rule["limit_field"]
        if isinstance(org, dict):
            limit = org.get(limit_field, -1)
        else:
            limit = getattr(org, limit_field, -1)

        # -1 or None means unlimited
        if limit is None or int(limit) < 0:
            return await call_next(request)

        limit = int(limit)

        # Count current resources for this org
        db = SessionLocal()
        try:
            current_count = tenant_count(db, rule["model"], org_id)
        except Exception as e:
            logger.error("Plan enforcement count failed: %s", e)
            # Fail open -- don't block the user on DB errors
            return await call_next(request)
        finally:
            db.close()

        if current_count >= limit:
            resource = rule["resource_name"]
            plan_name = (
                org.get("plan", "current")
                if isinstance(org, dict)
                else getattr(org, "plan", "current")
            )
            logger.warning(
                "Plan limit reached: org=%s plan=%s %s=%d/%d",
                org_id, plan_name, resource, current_count, limit,
            )
            return JSONResponse(
                status_code=403,
                content={
                    "detail": (
                        f"Plan limit reached: your {plan_name} plan allows "
                        f"up to {limit} {resource} (currently {current_count}). "
                        f"Please upgrade your plan to add more."
                    ),
                    "error": "plan_limit_reached",
                    "resource": resource,
                    "current": current_count,
                    "limit": limit,
                    "plan": plan_name,
                },
            )

        return await call_next(request)
