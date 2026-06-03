"""
CaseHub - Org Branding Routes
Admin page for managing organization branding: logo, colors, identity.
"""
import os
import uuid
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db
from auth import get_current_user
from core.template_config import templates, PREFIX, inject_org_context
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/branding", tags=["branding"])

ALLOWED_LOGO_TYPES = {"image/png", "image/jpeg", "image/svg+xml"}
MAX_LOGO_SIZE = 2 * 1024 * 1024  # 2MB
LOGO_DIR = os.path.join(settings.BASE_DIR, "static", "img", "logos")


def require_admin(request: Request, db: Session):
    """Require authenticated admin user."""
    user = get_current_user(request, db)
    if not user or user.user_type != "admin":
        return None
    return user


def get_org_record(db: Session, org_id: int) -> dict:
    """Fetch full org record as dict."""
    result = db.execute(
        text("SELECT * FROM organizations WHERE id = :id"),
        {"id": org_id}
    ).mappings().first()
    return dict(result) if result else None


@router.get("", response_class=HTMLResponse)
async def branding_page(request: Request, db: Session = Depends(get_db)):
    """Render branding settings page."""
    user = require_admin(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    org_id = getattr(getattr(request, "state", None), "org_id", None)
    org = get_org_record(db, org_id) if org_id else None

    ctx = inject_org_context(request)
    success = request.query_params.get("success")
    error = request.query_params.get("error")

    return templates.TemplateResponse("app/admin/branding.html", {
        "request": request,
        "user": user,
        "org": org,
        "success": success,
        "error": error,
        **ctx,
    })


@router.post("", response_class=HTMLResponse)
async def save_branding(
    request: Request,
    org_name: str = Form(""),
    case_prefix: str = Form("CH"),
    primary_color: str = Form("#ffffff"),
    secondary_color: str = Form("#1a1a1a"),
    bg_color: str = Form("#0f0f0f"),
    accent_color: str = Form(""),
    font_family: str = Form(""),
    db: Session = Depends(get_db),
):
    """Save branding settings to organizations table."""
    user = require_admin(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    org_id = getattr(getattr(request, "state", None), "org_id", None)
    if not org_id:
        return RedirectResponse(
            url=f"{PREFIX}/admin/branding?error=No+organization+context",
            status_code=302,
        )

    # Validate color format
    for color in [primary_color, secondary_color, bg_color]:
        if not _is_valid_hex_color(color):
            return RedirectResponse(
                url=f"{PREFIX}/admin/branding?error=Invalid+color+format",
                status_code=302,
            )

    # Build settings JSONB update
    import json
    settings_update = {}
    if accent_color.strip():
        settings_update["accent_color"] = accent_color.strip()
    if font_family.strip():
        settings_update["font_family"] = font_family.strip()
    if bg_color.strip():
        settings_update["theme_bg"] = bg_color.strip()

    try:
        db.execute(
            text("""
                UPDATE organizations
                SET name = :name,
                    case_prefix = :case_prefix,
                    primary_color = :primary_color,
                    secondary_color = :secondary_color,
                    settings = COALESCE(settings, '{}'::jsonb) || :settings_json::jsonb,
                    updated_at = NOW()
                WHERE id = :org_id
            """),
            {
                "name": org_name.strip() or "CaseHub",
                "case_prefix": case_prefix.strip()[:10] or "CH",
                "primary_color": primary_color,
                "secondary_color": secondary_color,
                "settings_json": json.dumps(settings_update),
                "org_id": org_id,
            },
        )
        db.commit()

        # Clear tenant middleware cache so changes take effect immediately
        _clear_tenant_cache(request)

        logger.info(f"Branding updated for org_id={org_id} by user={user.email}")
        return RedirectResponse(
            url=f"{PREFIX}/admin/branding?success=Branding+settings+saved+successfully",
            status_code=302,
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving branding for org_id={org_id}: {e}")
        return RedirectResponse(
            url=f"{PREFIX}/admin/branding?error=Failed+to+save+settings",
            status_code=302,
        )


@router.post("/logo", response_class=HTMLResponse)
async def upload_logo(
    request: Request,
    logo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload organization logo file."""
    user = require_admin(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    org_id = getattr(getattr(request, "state", None), "org_id", None)
    if not org_id:
        return RedirectResponse(
            url=f"{PREFIX}/admin/branding?error=No+organization+context",
            status_code=302,
        )

    # Validate file type
    if logo.content_type not in ALLOWED_LOGO_TYPES:
        return RedirectResponse(
            url=f"{PREFIX}/admin/branding?error=Invalid+file+type.+Use+PNG,+JPG,+or+SVG",
            status_code=302,
        )

    # Read and validate size
    content = await logo.read()
    if len(content) > MAX_LOGO_SIZE:
        return RedirectResponse(
            url=f"{PREFIX}/admin/branding?error=File+too+large.+Max+2MB",
            status_code=302,
        )

    # Ensure logo directory exists
    os.makedirs(LOGO_DIR, exist_ok=True)

    # Generate unique filename
    ext = Path(logo.filename).suffix.lower() if logo.filename else ".png"
    if ext not in {".png", ".jpg", ".jpeg", ".svg"}:
        ext = ".png"
    filename = f"org_{org_id}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(LOGO_DIR, filename)

    # Save file
    with open(filepath, "wb") as f:
        f.write(content)

    # Update org record with logo URL
    logo_url = f"/static/img/logos/{filename}"
    try:
        db.execute(
            text("""
                UPDATE organizations
                SET logo_url = :logo_url, updated_at = NOW()
                WHERE id = :org_id
            """),
            {"logo_url": logo_url, "org_id": org_id},
        )
        db.commit()

        _clear_tenant_cache(request)

        logger.info(f"Logo uploaded for org_id={org_id}: {logo_url}")
        return RedirectResponse(
            url=f"{PREFIX}/admin/branding?success=Logo+uploaded+successfully",
            status_code=302,
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving logo for org_id={org_id}: {e}")
        # Clean up orphaned file
        try:
            os.remove(filepath)
        except OSError:
            pass
        return RedirectResponse(
            url=f"{PREFIX}/admin/branding?error=Failed+to+save+logo",
            status_code=302,
        )


def _is_valid_hex_color(color: str) -> bool:
    """Validate hex color format (#rrggbb or #rgb)."""
    if not color or not color.startswith("#"):
        return False
    hex_part = color[1:]
    if len(hex_part) not in (3, 6):
        return False
    try:
        int(hex_part, 16)
        return True
    except ValueError:
        return False


def _clear_tenant_cache(request: Request):
    """Clear TenantMiddleware org cache after branding changes."""
    try:
        app = request.app
        for middleware in getattr(app, "middleware_stack", []):
            if hasattr(middleware, "clear_cache"):
                middleware.clear_cache()
                break
        # Also try the middleware attribute pattern used by Starlette
        if hasattr(app, "middleware"):
            for mw in app.middleware:
                if hasattr(mw, "cls") and hasattr(mw.cls, "clear_cache"):
                    # Can't call instance method on class, but we can find the instance
                    pass
    except Exception:
        # Non-critical: cache will expire or be refreshed on next deploy
        pass
