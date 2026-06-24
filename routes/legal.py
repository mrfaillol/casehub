"""
CaseHub - Legal pages (public, no auth required)
/privacy and /terms — required for Google OAuth verification.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from core.template_config import templates

router = APIRouter(tags=["legal"])


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_policy(request: Request):
    return templates.TemplateResponse("legal/privacy.html", {"request": request})


@router.get("/terms", response_class=HTMLResponse)
async def terms_of_service(request: Request):
    return templates.TemplateResponse("legal/terms.html", {"request": request})
