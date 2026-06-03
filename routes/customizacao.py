"""
CaseHub Lite - Painel de Customizacao
Permite admins personalizarem aparencia, sidebar, widgets e integracoes
sem necessidade de desenvolvedor.
"""
import json
import logging
import os
import shutil

from fastapi import APIRouter, Depends, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db
from auth import get_current_user
from core.template_config import templates, PREFIX, inject_org_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/customizacao", tags=["customizacao"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _require_admin(request: Request, db: Session):
    """Require authenticated admin user."""
    user = get_current_user(request, db)
    if not user or user.user_type != "admin":
        return None
    return user


def _get_org_settings(db: Session, org_id: int) -> dict:
    """Fetch org settings JSONB from organizations table."""
    if not org_id:
        return {}
    result = db.execute(
        text("SELECT settings FROM organizations WHERE id = :id"),
        {"id": org_id},
    ).scalar()
    if result is None:
        return {}
    if isinstance(result, str):
        try:
            return json.loads(result)
        except (json.JSONDecodeError, TypeError):
            return {}
    return dict(result) if result else {}


def _save_org_settings(db: Session, org_id: int, settings_dict: dict):
    """Merge and save settings JSONB for an organization."""
    current = _get_org_settings(db, org_id)
    current.update(settings_dict)
    db.execute(
        text("""
            UPDATE organizations
            SET settings = :settings, updated_at = NOW()
            WHERE id = :org_id
        """),
        {"settings": json.dumps(current), "org_id": org_id},
    )
    db.commit()
    return current


def _clear_tenant_cache(request: Request):
    """Clear TenantMiddleware org cache after changes."""
    try:
        app = request.app
        for middleware in getattr(app, "middleware_stack", []):
            if hasattr(middleware, "clear_cache"):
                middleware.clear_cache()
                break
    except Exception:
        pass


# ---------------------------------------------------------------------------
# GET /admin/customizacao - Main panel
# ---------------------------------------------------------------------------
@router.get("", response_class=HTMLResponse)
async def customizacao_page(request: Request, db: Session = Depends(get_db)):
    """Render the customization panel."""
    user = _require_admin(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    org_id = getattr(getattr(request, "state", None), "org_id", None)
    org_settings = _get_org_settings(db, org_id)
    ctx = inject_org_context(request)

    success = request.query_params.get("success")
    error = request.query_params.get("error")
    tab = request.query_params.get("tab", "aparencia")

    # Audit P0.3: 3 concurrent integration screens collapsed into one.
    # `?tab=integracoes` no longer renders — funnel into /integrations hub
    # so Client ID + Folder ID raw inputs (technical jargon) stay off the
    # admin customization panel.
    if tab == "integracoes":
        return RedirectResponse(url=f"{PREFIX}/integrations", status_code=302)

    return templates.TemplateResponse("app/admin/customizacao.html", {
        "request": request,
        "user": user,
        "org_settings": org_settings,
        "active_tab": tab,
        "success": success,
        "error": error,
        **ctx,
    })


# ---------------------------------------------------------------------------
# POST /admin/customizacao/aparencia
# ---------------------------------------------------------------------------
@router.post("/aparencia", response_class=HTMLResponse)
async def save_aparencia(
    request: Request,
    primary_color: str = Form("#0EA5E9"),
    secondary_color: str = Form("#6366F1"),
    logo_url: str = Form(""),
    org_display_name: str = Form(""),
    favicon_url: str = Form(""),
    logo_file: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    """Save appearance settings."""
    user = _require_admin(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    org_id = getattr(getattr(request, "state", None), "org_id", None)
    if not org_id:
        return RedirectResponse(
            url=f"{PREFIX}/admin/customizacao?error=Sem+contexto+de+organizacao&tab=aparencia",
            status_code=302,
        )

    # Validate colors
    for color in [primary_color, secondary_color]:
        if color and not _is_valid_hex_color(color):
            return RedirectResponse(
                url=f"{PREFIX}/admin/customizacao?error=Formato+de+cor+invalido&tab=aparencia",
                status_code=302,
            )

    try:
        # Handle logo file upload
        logo_file_path = ""
        if logo_file and logo_file.filename:
            # Sentinela T11 fix: per-tenant subdirectory.
            logos_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "uploads",
                f"org_{org_id}",
                "logos",
            )
            os.makedirs(logos_dir, exist_ok=True)

            # Determine extension from uploaded file
            ext = os.path.splitext(logo_file.filename)[1].lower()
            if ext not in (".png", ".jpg", ".jpeg", ".svg", ".webp"):
                ext = ".png"
            dest_filename = f"org_{org_id}{ext}"
            dest_path = os.path.join(logos_dir, dest_filename)

            with open(dest_path, "wb") as f:
                content = await logo_file.read()
                f.write(content)

            # URL stays /uploads/logos/<filename>; the new auth-gated route
            # resolves to the tenant-scoped path.
            logo_file_path = f"/uploads/logos/{dest_filename}"
            logger.info("Logo uploaded for org_id=%s: %s", org_id, dest_path)

        settings_data = {
            "primary_color": primary_color,
            "secondary_color": secondary_color,
            "logo_url": logo_url.strip(),
            "org_display_name": org_display_name.strip(),
            "favicon_url": favicon_url.strip(),
        }

        # If a file was uploaded, set it as logo_file_path (takes precedence in display)
        if logo_file_path:
            settings_data["logo_file_path"] = logo_file_path

        _save_org_settings(db, org_id, settings_data)
        _clear_tenant_cache(request)

        logger.info("Aparencia atualizada org_id=%s por user_id=%s", org_id, user.id)
        return RedirectResponse(
            url=f"{PREFIX}/admin/customizacao?success=Aparencia+salva+com+sucesso&tab=aparencia",
            status_code=302,
        )
    except Exception as e:
        db.rollback()
        logger.error("Erro salvando aparencia org_id=%s: %s", org_id, e)
        return RedirectResponse(
            url=f"{PREFIX}/admin/customizacao?error=Falha+ao+salvar+aparencia&tab=aparencia",
            status_code=302,
        )


# ---------------------------------------------------------------------------
# POST /admin/customizacao/sidebar
# ---------------------------------------------------------------------------
@router.post("/sidebar", response_class=HTMLResponse)
async def save_sidebar(request: Request, db: Session = Depends(get_db)):
    """Save sidebar configuration (order, visibility)."""
    user = _require_admin(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    org_id = getattr(getattr(request, "state", None), "org_id", None)
    if not org_id:
        return RedirectResponse(
            url=f"{PREFIX}/admin/customizacao?error=Sem+contexto+de+organizacao&tab=sidebar",
            status_code=302,
        )

    try:
        form = await request.form()
        sidebar_order = form.get("sidebar_order", "")
        # sidebar_order is a comma-separated list of item keys
        order_list = [s.strip() for s in sidebar_order.split(",") if s.strip()]

        # Visibility: checkboxes named "visible_<key>"
        visible_items = {}
        for key in order_list:
            visible_items[key] = form.get(f"visible_{key}") == "on"

        settings_data = {
            "sidebar_order": order_list,
            "sidebar_visibility": visible_items,
        }
        _save_org_settings(db, org_id, settings_data)
        _clear_tenant_cache(request)

        logger.info("Sidebar atualizada org_id=%s por user_id=%s", org_id, user.id)
        return RedirectResponse(
            url=f"{PREFIX}/admin/customizacao?success=Sidebar+salva+com+sucesso&tab=sidebar",
            status_code=302,
        )
    except Exception as e:
        db.rollback()
        logger.error("Erro salvando sidebar org_id=%s: %s", org_id, e)
        return RedirectResponse(
            url=f"{PREFIX}/admin/customizacao?error=Falha+ao+salvar+sidebar&tab=sidebar",
            status_code=302,
        )


# ---------------------------------------------------------------------------
# POST /admin/customizacao/widgets
# ---------------------------------------------------------------------------
@router.post("/widgets", response_class=HTMLResponse)
async def save_widgets(request: Request, db: Session = Depends(get_db)):
    """Save default widget layout."""
    user = _require_admin(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    org_id = getattr(getattr(request, "state", None), "org_id", None)
    if not org_id:
        return RedirectResponse(
            url=f"{PREFIX}/admin/customizacao?error=Sem+contexto+de+organizacao&tab=widgets",
            status_code=302,
        )

    try:
        form = await request.form()
        widget_keys = [
            "casos_ativos", "tarefas_pendentes", "documentos_recentes",
            "prazos_proximos", "receita_mensal", "grafico_casos",
            "calendario_mini", "atividade_recente",
        ]
        enabled_widgets = {}
        for key in widget_keys:
            enabled_widgets[key] = form.get(f"widget_{key}") == "on"

        settings_data = {"default_widgets": enabled_widgets}
        _save_org_settings(db, org_id, settings_data)
        _clear_tenant_cache(request)

        logger.info("Widgets atualizados org_id=%s por user_id=%s", org_id, user.id)
        return RedirectResponse(
            url=f"{PREFIX}/admin/customizacao?success=Widgets+salvos+com+sucesso&tab=widgets",
            status_code=302,
        )
    except Exception as e:
        db.rollback()
        logger.error("Erro salvando widgets org_id=%s: %s", org_id, e)
        return RedirectResponse(
            url=f"{PREFIX}/admin/customizacao?error=Falha+ao+salvar+widgets&tab=widgets",
            status_code=302,
        )


# ---------------------------------------------------------------------------
# POST /admin/customizacao/notificacoes
# ---------------------------------------------------------------------------
@router.post("/notificacoes", response_class=HTMLResponse)
async def save_notificacoes(request: Request, db: Session = Depends(get_db)):
    """Save notification preferences."""
    user = _require_admin(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    org_id = getattr(getattr(request, "state", None), "org_id", None)
    if not org_id:
        return RedirectResponse(
            url=f"{PREFIX}/admin/customizacao?error=Sem+contexto+de+organizacao&tab=notificacoes",
            status_code=302,
        )

    try:
        form = await request.form()
        settings_data = {
            "notif_email": form.get("notif_email") == "on",
            "notif_inapp": form.get("notif_inapp") == "on",
            "notif_frequency": form.get("notif_frequency", "diario"),
            "notif_prazos": form.get("notif_prazos") == "on",
            "notif_tarefas": form.get("notif_tarefas") == "on",
            "notif_documentos": form.get("notif_documentos") == "on",
        }
        _save_org_settings(db, org_id, settings_data)
        _clear_tenant_cache(request)

        logger.info("Notificacoes atualizadas org_id=%s por user_id=%s", org_id, user.id)
        return RedirectResponse(
            url=f"{PREFIX}/admin/customizacao?success=Notificacoes+salvas+com+sucesso&tab=notificacoes",
            status_code=302,
        )
    except Exception as e:
        db.rollback()
        logger.error("Erro salvando notificacoes org_id=%s: %s", org_id, e)
        return RedirectResponse(
            url=f"{PREFIX}/admin/customizacao?error=Falha+ao+salvar+notificacoes&tab=notificacoes",
            status_code=302,
        )


# ---------------------------------------------------------------------------
# POST /admin/customizacao/integracoes
# ---------------------------------------------------------------------------
@router.post("/integracoes", response_class=HTMLResponse)
async def save_integracoes(request: Request, db: Session = Depends(get_db)):
    """Save integration settings."""
    user = _require_admin(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    org_id = getattr(getattr(request, "state", None), "org_id", None)
    if not org_id:
        return RedirectResponse(
            url=f"{PREFIX}/admin/customizacao?error=Sem+contexto+de+organizacao&tab=integracoes",
            status_code=302,
        )

    try:
        form = await request.form()
        settings_data = {
            "whatsapp_enabled": form.get("whatsapp_enabled") == "on",
            "maestro_enabled": form.get("maestro_enabled") == "on",
            "moskit_enabled": form.get("moskit_enabled") == "on",
            "stripe_enabled": form.get("stripe_enabled") == "on",
            "pdpj_enabled": form.get("pdpj_enabled") == "on",
            "twilio_enabled": form.get("twilio_enabled") == "on",
            "webhooks_enabled": form.get("webhooks_enabled") == "on",
            "integrations_hub_enabled": form.get("integrations_hub_enabled") == "on",
            "gcal_enabled": form.get("gcal_enabled") == "on",
            "gcal_client_id": form.get("gcal_client_id", "").strip(),
            "gdrive_enabled": form.get("gdrive_enabled") == "on",
            "gdrive_folder_id": form.get("gdrive_folder_id", "").strip(),
            "smtp_enabled": form.get("smtp_enabled") == "on",
            "smtp_host": form.get("smtp_host", "").strip(),
            "smtp_port": form.get("smtp_port", "").strip(),
            "smtp_user": form.get("smtp_user", "").strip(),
            "smtp_password": form.get("smtp_password", "").strip(),
        }
        _save_org_settings(db, org_id, settings_data)
        _clear_tenant_cache(request)

        logger.info("Integracoes atualizadas org_id=%s por user_id=%s", org_id, user.id)
        return RedirectResponse(
            url=f"{PREFIX}/admin/customizacao?success=Integracoes+salvas+com+sucesso&tab=integracoes",
            status_code=302,
        )
    except Exception as e:
        db.rollback()
        logger.error("Erro salvando integracoes org_id=%s: %s", org_id, e)
        return RedirectResponse(
            url=f"{PREFIX}/admin/customizacao?error=Falha+ao+salvar+integracoes&tab=integracoes",
            status_code=302,
        )


# ---------------------------------------------------------------------------
# GET /admin/customizacao/api/settings - JSON API
# ---------------------------------------------------------------------------
@router.get("/api/settings")
async def get_settings_api(request: Request, db: Session = Depends(get_db)):
    """Return current org settings as JSON."""
    user = _require_admin(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    org_id = getattr(getattr(request, "state", None), "org_id", None)
    org_settings = _get_org_settings(db, org_id)
    return JSONResponse(org_settings)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------
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
