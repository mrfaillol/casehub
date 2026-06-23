"""
CaseHub - Feature Flag Middleware
Checks if the current org's plan includes a required feature.

Usage:
    from middleware.features import require_feature

    @router.get("/ai/lor")
    async def generate_lor(
        request: Request,
        _feature=Depends(require_feature("ai_lor")),
    ):
        ...
"""
import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db

logger = logging.getLogger(__name__)

# Plan -> features mapping (fallback if DB plans table is unreachable).
# Canonical plans (Equipe CaseHub, 28/05/2026): office (R$129) + enterprise (sob consulta).
# Keep feature lists in sync with routes/subscription.PLAN_FEATURES.
# Legacy keys (starter/professional) retained so orgs still stored under them keep
# working until migrated.
_PLAN_FEATURES_FALLBACK = {
    "office": [
        "cases", "clients", "documents", "drive_sync", "email", "tasks",
        "ai_lor", "ai_ps", "package_builder", "crm", "whatsapp", "reports",
    ],
    "enterprise": [
        "cases", "clients", "documents", "drive_sync", "email", "tasks",
        "ai_lor", "ai_ps", "package_builder", "crm", "whatsapp", "reports",
        "sso", "custom_domain", "api_access", "audit", "priority_support",
    ],
    # --- legacy plan keys (pre-2026-05-28) ---
    "starter": [
        "cases", "clients", "documents", "drive_sync", "email", "tasks",
    ],
    "professional": [
        "cases", "clients", "documents", "drive_sync", "email", "tasks",
        "ai_lor", "ai_ps", "package_builder", "crm", "whatsapp", "reports",
    ],
}


def _get_org_features(request: Request, db: Session) -> list:
    """
    Resolve the list of feature strings for the current org.

    Resolution order:
    1. plans table (joined via org.plan)
    2. org.features JSONB field (if it's a list)
    3. Hardcoded fallback based on plan name
    """
    org = getattr(getattr(request, "state", None), "org", None)
    if not org:
        return []

    plan_name = org.get("plan", "office") if isinstance(org, dict) else getattr(org, "plan", "office")

    # Try plans table first
    try:
        row = db.execute(
            text("SELECT features FROM plans WHERE name = :name AND is_active = TRUE LIMIT 1"),
            {"name": plan_name},
        ).first()
        if row and row[0]:
            features = row[0]
            if isinstance(features, list):
                return features
            if isinstance(features, str):
                import json
                return json.loads(features)
    except Exception:
        pass  # Table may not exist yet

    # Fallback: org.features JSONB (if it's a list of strings)
    org_features = org.get("features") if isinstance(org, dict) else getattr(org, "features", None)
    if isinstance(org_features, list):
        return org_features

    # Last resort: hardcoded map (default to the canonical office plan).
    return _PLAN_FEATURES_FALLBACK.get(plan_name, _PLAN_FEATURES_FALLBACK["office"])


def require_feature(feature: str):
    """
    FastAPI dependency factory that checks if the org's plan includes *feature*.

    Raises HTTP 402 if the feature is not available, prompting a plan upgrade.

    Example:
        @router.post("/ai/lor/generate")
        async def gen_lor(
            request: Request,
            _f=Depends(require_feature("ai_lor")),
            db: Session = Depends(get_db),
        ):
            ...
    """

    async def _dependency(
        request: Request,
        db: Session = Depends(get_db),
    ):
        features = _get_org_features(request, db)
        if feature not in features:
            logger.info(
                f"Feature '{feature}' blocked for org "
                f"{getattr(getattr(request, 'state', None), 'org_id', '?')}"
            )
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Upgrade your plan to access this feature: {feature}",
            )
        return True

    return _dependency
