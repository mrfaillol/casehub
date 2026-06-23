"""
CaseHub — Domicílio Judicial Eletrônico (DJE) routes.

Tenant-scoped JSON endpoint to fetch comunicações/intimações from the PDPJ DJE
gateway (services/dje_client.py). Gated behind the default-OFF
``dje_integration`` feature flag (core/feature_flags.py): while OFF the route
returns 404 and no live PDPJ call is ever made.

Auth flow (see services/dje_client.py): OAuth2 client_credentials -> Bearer JWT
to gateway.cloud.pje.jus.br/domicilio-eletronico; per-org credentials from
services/pdpj_credentials.py (no hardcoded secrets); tenantId resolved from
GET /api/v1/eu and sent as a header.

UI is intentionally out of scope — JSON only for now.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from auth import get_current_user
from core import feature_flags
from models import get_db
from services.dje_client import dje_client

logger = logging.getLogger(__name__)

router = APIRouter()

DJE_FLAG = "dje_integration"


def _require_enabled() -> None:
    """404 when the DJE integration flag is OFF (route is inert by default)."""
    if not feature_flags.is_enabled(DJE_FLAG):
        raise HTTPException(status_code=404, detail="Not Found")


def _require_org_id(request: Request) -> int:
    """Resolve the tenant org_id set by TenantMiddleware (no fallback)."""
    org_id = getattr(request.state, "org_id", None)
    if org_id is None:
        raise HTTPException(status_code=400, detail="Tenant não identificado.")
    return int(org_id)


@router.get("/dje/comunicacoes")
async def listar_comunicacoes(
    request: Request,
    status_ciente: Optional[str] = Query(None, alias="statusCiente"),
    data_inicio: Optional[str] = Query(None, alias="dataInicio"),
    data_fim: Optional[str] = Query(None, alias="dataFim"),
    numero_processo: Optional[str] = Query(None, alias="numeroProcesso"),
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Fetch DJE comunicações (intimações) for the current org, behind the flag."""
    _require_enabled()
    # Require an authenticated user (tenant-scoped, same posture as siblings).
    get_current_user(request, db)
    org_id = _require_org_id(request)

    result = await dje_client.listar_comunicacoes(
        org_id,
        status_ciente=status_ciente,
        data_inicio=data_inicio,
        data_fim=data_fim,
        numero_processo=numero_processo,
        page=page,
        size=size,
    )
    return JSONResponse(content=result)
