"""
CaseHub - Leads Analytics Routes
Extracted from leads.py: metrics, pipeline stats, trends, aging,
funnel conversion, velocity, source attribution, channel engagement,
intelligence summary, and score trends.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from models import get_db
from auth import get_current_user
from config import settings
from services import leads_manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers (shared with leads.py)
# ---------------------------------------------------------------------------
import os

WEBHOOK_API_KEY = os.getenv("CRM_WEBHOOK_API_KEY", "")


class _InternalUser:
    """Sentinel user for internal API key access (n8n, etc.)."""
    email = "system@internal"
    name = "System"
    role = "admin"


def require_user(request: Request, db: Session):
    """Require authenticated user or internal API key, or raise 401."""
    api_key = request.headers.get("x-api-key")
    if api_key and api_key == WEBHOOK_API_KEY:
        return _InternalUser()
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# ---------------------------------------------------------------------------
# Optional analytics service imports
# ---------------------------------------------------------------------------
try:
    from services.lead_analytics import (
        compute_funnel_conversion,
        compute_pipeline_velocity,
        compute_source_attribution,
        compute_channel_engagement,
        compute_intelligence_summary,
        compute_score_trends,
    )
    ANALYTICS_AVAILABLE = True
except Exception as e:
    logger.warning(f"Lead analytics not available: {e}")
    ANALYTICS_AVAILABLE = False

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = APIRouter(tags=["leads-analytics"])


# =============================================================================
# BASIC METRICS
# =============================================================================

@router.get("/metrics")
async def get_metrics(request: Request, db: Session = Depends(get_db)):
    """Get dashboard metrics."""
    user = require_user(request, db)
    data = leads_manager.load_leads()
    return leads_manager.get_metrics(data)


@router.get("/pipeline")
async def get_pipeline(request: Request, db: Session = Depends(get_db)):
    """Get pipeline/funnel metrics."""
    user = require_user(request, db)
    data = leads_manager.load_leads()
    return leads_manager.get_pipeline_metrics(data)


@router.get("/trends")
async def get_trends(
    request: Request,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """Get trend metrics."""
    user = require_user(request, db)
    data = leads_manager.load_leads()
    return leads_manager.get_trend_metrics(data, days=days)


@router.get("/aging")
async def get_aging(request: Request, db: Session = Depends(get_db)):
    """Get lead aging metrics by pipeline stage."""
    user = require_user(request, db)
    data = leads_manager.load_leads()
    return leads_manager.get_aging_metrics(data)


# =============================================================================
# ADVANCED ANALYTICS (from services.lead_analytics)
# =============================================================================

@router.get("/intel/analytics/funnel")
async def analytics_funnel(request: Request, db: Session = Depends(get_db)):
    """Get funnel conversion rates."""
    require_user(request, db)
    if not ANALYTICS_AVAILABLE:
        return JSONResponse({"error": "Analytics not available"}, status_code=503)
    data = leads_manager.load_leads()
    return compute_funnel_conversion(data.get("leads", {}))


@router.get("/intel/analytics/velocity")
async def analytics_velocity(request: Request, db: Session = Depends(get_db)):
    """Get pipeline velocity metrics."""
    require_user(request, db)
    if not ANALYTICS_AVAILABLE:
        return JSONResponse({"error": "Analytics not available"}, status_code=503)
    data = leads_manager.load_leads()
    return compute_pipeline_velocity(data.get("leads", {}))


@router.get("/intel/analytics/sources")
async def analytics_sources(request: Request, db: Session = Depends(get_db)):
    """Get source attribution with conversion rates."""
    require_user(request, db)
    if not ANALYTICS_AVAILABLE:
        return JSONResponse({"error": "Analytics not available"}, status_code=503)
    data = leads_manager.load_leads()
    return compute_source_attribution(data.get("leads", {}))


@router.get("/intel/analytics/channels")
async def analytics_channels(request: Request, db: Session = Depends(get_db)):
    """Get WhatsApp vs Email channel engagement."""
    require_user(request, db)
    if not ANALYTICS_AVAILABLE:
        return JSONResponse({"error": "Analytics not available"}, status_code=503)
    data = leads_manager.load_leads()
    return compute_channel_engagement(data.get("leads", {}))


@router.get("/intel/analytics/summary")
async def analytics_summary(request: Request, db: Session = Depends(get_db)):
    """Get intelligence summary across all leads."""
    require_user(request, db)
    if not ANALYTICS_AVAILABLE:
        return JSONResponse({"error": "Analytics not available"}, status_code=503)
    data = leads_manager.load_leads()
    return compute_intelligence_summary(data.get("leads", {}))


@router.get("/intel/analytics/score-trends")
async def analytics_score_trends(
    request: Request,
    days: int = Query(30, ge=7, le=365),
    db: Session = Depends(get_db),
):
    """Get 4D score trends over time."""
    require_user(request, db)
    if not ANALYTICS_AVAILABLE:
        return JSONResponse({"error": "Analytics not available"}, status_code=503)
    data = leads_manager.load_leads()
    return compute_score_trends(data.get("leads", {}), days=days)
