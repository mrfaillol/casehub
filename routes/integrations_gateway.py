"""Admin-only sanitized status for the CaseHub-owned integrations gateway.

Default-off. This route reports provider configuration state only: every
registry provider is disabled, no live provider call is made, and no
credential ref or secret value is serialized into the response. Promoting any
provider to live calls is a separate, Council-gated slice — see
``docs/integrations/casehub-integrations-gateway.md``.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from auth import get_current_user
from config import settings
from models import get_db
from services.audit import log_action
from services.integrations_gateway import build_provider_status, get_default_provider_configs
from services.integrations_gateway.credentials import EnvCredentialStore

router = APIRouter(prefix="/integrations/gateway", tags=["integrations-gateway"])


@router.get("/status")
async def gateway_status(request: Request, db: Session = Depends(get_db)):
    """Return sanitized, admin-only status for every registered gateway provider."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "auth_required"})
    if getattr(user, "user_type", None) != "admin":
        return JSONResponse(status_code=403, content={"error": "admin_required"})

    store = EnvCredentialStore()
    providers = []
    for provider in get_default_provider_configs():
        status = build_provider_status(provider)
        # `configured` reflects whether the runtime credential ref resolves to a
        # present secret. The ref string and the value itself are never serialized.
        status["configured"] = store.resolve(provider.credential_ref).present
        providers.append(status)

    payload = {
        "gateway_enabled": settings.CASEHUB_INTEGRATIONS_GATEWAY_ENABLED,
        "default_off": not settings.CASEHUB_INTEGRATIONS_GATEWAY_ENABLED,
        "provider_count": len(providers),
        "providers": providers,
    }

    log_action(
        db,
        action="gateway.status.read",
        entity_type="integration_gateway",
        user_id=user.id,
        user_email=user.email,
        description="Admin viewed integrations gateway provider status",
        details={
            "provider_count": len(providers),
            "gateway_enabled": settings.CASEHUB_INTEGRATIONS_GATEWAY_ENABLED,
        },
        request=request,
    )
    return JSONResponse(content=payload)
