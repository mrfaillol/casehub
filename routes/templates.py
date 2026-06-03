"""
CaseHub - Email Templates API
Reads templates from whatsapp-bot/agent-templates.js
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from models import get_db
from auth import get_current_user
import logging
import re
import os
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix=f"{settings.PREFIX}/api", tags=["templates"])

# Path to agent templates
TEMPLATES_PATH = os.path.join(settings.BASE_DIR, "..", "whatsapp-bot", "agent-templates.js")

# Cache for parsed templates
_templates_cache = None
_templates_mtime = None


def parse_agent_templates():
    """Parse the agent-templates.js file and extract templates"""
    global _templates_cache, _templates_mtime

    # Check if file has been modified
    try:
        current_mtime = os.path.getmtime(TEMPLATES_PATH)
        if _templates_cache is not None and _templates_mtime == current_mtime:
            return _templates_cache
        _templates_mtime = current_mtime
    except Exception as e:
        logger.error("Failed to check templates file mtime: %s", e)

    templates = {}

    try:
        with open(TEMPLATES_PATH, 'r', encoding='utf-8') as f:
            content = f.read()

        # Find all template definitions
        # Pattern: template_name: { en: `...`, pt: `...`, es: `...` }
        template_pattern = r'(\w+):\s*\{\s*en:\s*`([^`]*)`\s*,\s*pt:\s*`([^`]*)`\s*,\s*es:\s*`([^`]*)`'

        matches = re.findall(template_pattern, content, re.DOTALL)

        for match in matches:
            name, en_text, pt_text, es_text = match
            # Convert snake_case to readable name
            display_name = name.replace('_', ' ').title()

            templates[name] = {
                "name": display_name,
                "key": name,
                "en": en_text.strip(),
                "pt": pt_text.strip(),
                "es": es_text.strip()
            }

        _templates_cache = templates
        return templates

    except Exception as e:
        logger.error("Error parsing templates: %s", e)
        return {}


def get_template_names():
    """Get list of template names for display"""
    templates = parse_agent_templates()
    return [
        {"key": key, "name": val["name"]}
        for key, val in templates.items()
    ]


@router.get("/email-templates")
async def get_email_templates(request: Request, lang: str = Query("en", description="Language: en, pt, or es"), db: Session = Depends(get_db)):
    """
    Get all email templates.

    Returns templates from agent-templates.js with support for EN/PT/ES.
    """
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    templates = parse_agent_templates()

    # Format for frontend
    result = {}
    for key, template in templates.items():
        result[key] = {
            "name": template["name"],
            "content": template.get(lang, template.get("en", ""))
        }

    return JSONResponse({
        "success": True,
        "templates": result,
        "languages": ["en", "pt", "es"],
        "count": len(result)
    })


@router.get("/email-templates/{template_key}")
async def get_single_template(template_key: str, request: Request, lang: str = Query("en"), db: Session = Depends(get_db)):
    """Get a single template by key"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    templates = parse_agent_templates()

    if template_key not in templates:
        return JSONResponse({
            "success": False,
            "error": f"Template '{template_key}' not found"
        }, status_code=404)

    template = templates[template_key]
    return JSONResponse({
        "success": True,
        "template": {
            "key": template_key,
            "name": template["name"],
            "content": template.get(lang, template.get("en", "")),
            "all_languages": {
                "en": template.get("en", ""),
                "pt": template.get("pt", ""),
                "es": template.get("es", "")
            }
        }
    })


@router.get("/email-templates-list")
async def list_templates(request: Request, db: Session = Depends(get_db)):
    """Get just the list of template names (for populating dropdowns)"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return JSONResponse({
        "success": True,
        "templates": get_template_names()
    })
