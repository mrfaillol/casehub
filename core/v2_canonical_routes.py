"""
UI Remake — Canonical route handlers (rich templates only).

REGRAS:
1. Sem /v2/* — só canonical paths (/casehub/X direto).
2. Override APENAS rotas com template rico portado em templates/app/.
3. Para qualquer rota sem template rico, NÃO registramos override aqui —
   o legacy router include responde normalmente com a UI legacy intacta.
4. Funcionalidade legacy (WhatsApp, Emails, Tools BR, Letters, Questionnaires,
   USCIS, ILC Tools, Onboarding, Bulk, etc) continua funcionando exatamente
   como antes nas rotas canônicas tradicionais.

Registered BEFORE app.include_router() loop in app_factory.create_app() so
FastAPI first-match-wins makes these win over the legacy router includes
for the specific paths we cover.
"""
from __future__ import annotations
from datetime import date
from typing import Any, Callable, Optional

from fastapi import FastAPI, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from models import get_db
from auth import get_current_user


def register_canonical_routes(app: FastAPI, templates: Any, get_context: Callable, PREFIX: str) -> None:
    """Wire canonical handlers for rich (fully ported) templates only.

    Called from create_app() right after the dashboard handler and BEFORE
    the legacy router include loop.
    """

    def _redirect_login(target: str) -> RedirectResponse:
        return RedirectResponse(url=f"{PREFIX}/login?next={target}", status_code=302)

    async def _delegate_async(legacy_fn, **kwargs) -> dict:
        """Call legacy handler, extract its TemplateResponse.context dict."""
        try:
            import inspect
            coro = legacy_fn(**kwargs)
            response = await coro if inspect.iscoroutine(coro) else coro
            return getattr(response, "context", None) or {}
        except Exception:
            return {}

    # ─────────── Workspace utility surfaces ───────────
    @app.get(f"{PREFIX}/casehub-md", response_class=HTMLResponse)
    async def casehub_md_workspace_canon(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/casehub-md")
        ctx = {
            **get_context(request, db, user=user),
            "user": user,
            "today": date.today(),
            "active_module": "md",
        }
        return templates.TemplateResponse("app/casehub_md/index.html", ctx)

    @app.get(f"{PREFIX}/whatsapp-chat", response_class=HTMLResponse)
    async def whatsapp_chat_workspace_canon(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/whatsapp-chat")
        try:
            from routes.whatsapp_chat import get_bot_status as _get_bot_status
            bot_status = await _get_bot_status()
        except Exception:
            bot_status = {"connected": False, "status": "offline", "ok": False}
        ctx = {
            **get_context(request, db, user=user),
            "user": user,
            "today": date.today(),
            "active_module": "whatsapp",
            "bot_status": bot_status,
        }
        return templates.TemplateResponse("app/whatsapp/chat.html", ctx)

    @app.get(f"{PREFIX}/route-map", response_class=HTMLResponse)
    async def route_map_canon(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/route-map")
        groups = [
            ("Produto", [
                ("Painel", f"{PREFIX}/dashboard"),
                ("Controladoria", f"{PREFIX}/controladoria"),
                ("Agenda", f"{PREFIX}/calendar"),
                ("Kanban", f"{PREFIX}/tasks/kanban"),
                ("Processos", f"{PREFIX}/cases"),
                ("Clientes", f"{PREFIX}/clients"),
                ("WhatsApp Chat", f"{PREFIX}/whatsapp-chat"),
                ("Maestro", f"{PREFIX}/assistente"),
                ("Documentos / Drive", f"{PREFIX}/documents"),
                ("CaseHub.md", f"{PREFIX}/casehub-md"),
            ]),
            ("Operação", [
                ("Financeiro", f"{PREFIX}/billing"),
                ("Faturas", f"{PREFIX}/invoices"),
                ("Pagamentos", f"{PREFIX}/payments"),
                ("Modelos de documentos", f"{PREFIX}/doc-templates"),
                ("Relatórios", f"{PREFIX}/reports"),
                ("Notificações", f"{PREFIX}/notifications"),
            ]),
            ("Conta e Admin", [
                ("Perfil", f"{PREFIX}/profile"),
                ("Configurações", f"{PREFIX}/settings"),
                ("Numeração", f"{PREFIX}/settings/numbering"),
                ("Integrações", f"{PREFIX}/integrations"),
                ("Assinatura", f"{PREFIX}/subscription"),
                ("Admin", f"{PREFIX}/admin"),
                ("Usuários", f"{PREFIX}/admin/users"),
                ("Customização", f"{PREFIX}/admin/customizacao"),
                ("Branding", f"{PREFIX}/admin/branding"),
                ("Design editor", f"{PREFIX}/admin/design-editor"),
            ]),
        ]
        ctx = {
            **get_context(request, db, user=user),
            "user": user,
            "today": date.today(),
            "active_module": "route-map",
            "route_groups": groups,
        }
        return templates.TemplateResponse("app/route_map/index.html", ctx)

    # ─────────── Clients ───────────
    @app.get(f"{PREFIX}/clients/new", response_class=HTMLResponse)
    async def clients_new_canon(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/clients/new")
        try:
            from routes.clients import new_client as _fn
            ctx = await _delegate_async(_fn, request=request, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/clients/form.html", ctx)

    @app.get(f"{PREFIX}/clients/{{client_id}}", response_class=HTMLResponse)
    async def clients_detail_canon(client_id: int, request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/clients/{client_id}")
        try:
            from routes.clients import view_client as _fn
            ctx = await _delegate_async(_fn, client_id=client_id, request=request, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/clients/detail.html", ctx)

    @app.get(f"{PREFIX}/clients/{{client_id}}/edit", response_class=HTMLResponse)
    async def clients_edit_canon(client_id: int, request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/clients/{client_id}/edit")
        try:
            # Legacy fn is exported as `edit_client_form` (not `edit_client`).
            # Importing the wrong name silently dropped ctx → template UndefinedError.
            from routes.clients import edit_client_form as _fn
            ctx = await _delegate_async(_fn, client_id=client_id, request=request, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/clients/form.html", ctx)

    # ─────────── Cases ───────────
    @app.get(f"{PREFIX}/cases/new", response_class=HTMLResponse)
    async def cases_new_canon(request: Request, client_id: Optional[int] = None, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/cases/new")
        try:
            from routes.cases import new_case as _fn
            ctx = await _delegate_async(_fn, request=request, client_id=client_id, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/cases/form.html", ctx)

    @app.get(f"{PREFIX}/cases/{{case_id}}", response_class=HTMLResponse)
    async def cases_detail_canon(case_id: int, request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/cases/{case_id}")
        try:
            from routes.cases import view_case as _fn
            ctx = await _delegate_async(_fn, case_id=case_id, request=request, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/cases/detail.html", ctx)

    @app.get(f"{PREFIX}/cases/{{case_id}}/edit", response_class=HTMLResponse)
    async def cases_edit_canon(case_id: int, request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/cases/{case_id}/edit")
        try:
            # Legacy fn is `edit_case_form` (parity com edit_client_form fix BL-1).
            from routes.cases import edit_case_form as _fn
            ctx = await _delegate_async(_fn, case_id=case_id, request=request, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/cases/form.html", ctx)

    # ─────────── Tasks ───────────
    @app.get(f"{PREFIX}/tasks/new", response_class=HTMLResponse)
    async def tasks_new_canon(
        request: Request,
        client_id: Optional[int] = None,
        case_id: Optional[int] = None,
        db: Session = Depends(get_db),
    ):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/tasks/new")
        try:
            from routes.tasks import new_task as _fn
            ctx = await _delegate_async(_fn, request=request, client_id=client_id, case_id=case_id, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/tasks/form.html", ctx)

    @app.get(f"{PREFIX}/tasks/calendar", response_class=HTMLResponse)
    async def tasks_calendar_canon(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/tasks/calendar")
        from models import Task as _Task
        from models.tenant import tenant_query as _tenant_query
        today_ = date.today()
        tasks = _tenant_query(db, _Task, request.state.org_id).filter(
            _Task.due_date.isnot(None), _Task.status != "completed",
        ).order_by(_Task.due_date.asc()).limit(200).all()
        return templates.TemplateResponse("app/tasks/calendar_view.html", {
            **get_context(request, db, user=user),
            "user": user, "today": today_, "tasks": tasks,
        })

    # ─────────── Invoices ───────────
    @app.get(f"{PREFIX}/invoices", response_class=HTMLResponse)
    async def invoices_list_canon(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/invoices")
        try:
            # Legacy fn is `invoice_list`, not `list_invoices`.
            from routes.invoices import invoice_list as _fn
            ctx = await _delegate_async(_fn, request=request, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/invoices/list.html", ctx)

    @app.get(f"{PREFIX}/invoices/new", response_class=HTMLResponse)
    async def invoices_new_canon(request: Request, case_id: Optional[int] = None, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/invoices/new")
        try:
            # Legacy fn is `new_invoice_form`, not `new_invoice`.
            from routes.invoices import new_invoice_form as _fn
            ctx = await _delegate_async(_fn, request=request, case_id=case_id, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/invoices/form.html", ctx)

    @app.get(f"{PREFIX}/invoices/{{invoice_number}}", response_class=HTMLResponse)
    async def invoices_detail_canon(invoice_number: str, request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/invoices/{invoice_number}")
        try:
            from routes.invoices import view_invoice as _fn
            ctx = await _delegate_async(_fn, invoice_number=invoice_number, request=request, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/invoices/detail.html", ctx)

    @app.get(f"{PREFIX}/invoices/{{invoice_number}}/print", response_class=HTMLResponse)
    async def invoices_print_canon(invoice_number: str, request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/invoices/{invoice_number}/print")
        try:
            from routes.invoices import print_invoice as _fn
            ctx = await _delegate_async(_fn, invoice_number=invoice_number, request=request, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        return templates.TemplateResponse("app/invoices/print.html", ctx)

    # ─────────── Billing sub-routes ───────────
    @app.get(f"{PREFIX}/billing/items/new", response_class=HTMLResponse)
    async def billing_items_new_canon(
        request: Request,
        case_id: Optional[int] = None,
        db: Session = Depends(get_db),
    ):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/billing/items/new")
        try:
            from routes.billing import new_billing_item as _fn
            ctx = await _delegate_async(_fn, request=request, case_id=case_id, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/billing/items_form.html", ctx)

    @app.get(f"{PREFIX}/billing/time/new", response_class=HTMLResponse)
    async def billing_time_new_canon(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/billing/time/new")
        try:
            from routes.billing import new_time_entry as _fn
            ctx = await _delegate_async(_fn, request=request, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/billing/time_form.html", ctx)

    # ─────────── Documents sub-routes ───────────
    @app.get(f"{PREFIX}/documents/upload", response_class=HTMLResponse)
    async def documents_upload_canon(
        request: Request,
        client_id: Optional[int] = None,
        case_id: Optional[int] = None,
        db: Session = Depends(get_db),
    ):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/documents/upload")
        try:
            from routes.documents import upload_form as _fn
            ctx = await _delegate_async(_fn, request=request, client_id=client_id, case_id=case_id, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/documents/upload.html", ctx)

    @app.get(f"{PREFIX}/documents/{{doc_id}}", response_class=HTMLResponse)
    async def documents_detail_canon(doc_id: int, request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/documents/{doc_id}")
        try:
            from routes.documents import view_document as _fn
            ctx = await _delegate_async(_fn, doc_id=doc_id, request=request, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/documents/detail.html", ctx)

    # ─────────── Doc templates ───────────
    @app.get(f"{PREFIX}/doc-templates", response_class=HTMLResponse)
    async def doc_templates_list_canon(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/doc-templates")
        try:
            # Legacy fn is `template_list`, not `list_templates`.
            from routes.doc_templates import template_list as _fn
            ctx = await _delegate_async(_fn, request=request, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/doc_templates/list.html", ctx)

    @app.get(f"{PREFIX}/doc-templates/new", response_class=HTMLResponse)
    async def doc_templates_new_canon(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/doc-templates/new")
        try:
            # Legacy fn is `new_template_form`.
            from routes.doc_templates import new_template_form as _fn
            ctx = await _delegate_async(_fn, request=request, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/doc_templates/form.html", ctx)

    @app.get(f"{PREFIX}/doc-templates/{{template_id}}", response_class=HTMLResponse)
    async def doc_templates_detail_canon(template_id: int, request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/doc-templates/{template_id}")
        try:
            from routes.doc_templates import view_template as _fn
            ctx = await _delegate_async(_fn, template_id=template_id, request=request, db=db)
        except Exception:
            ctx = {"template_data": None}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/doc_templates/detail.html", ctx)

    @app.get(f"{PREFIX}/doc-templates/{{template_id}}/edit", response_class=HTMLResponse)
    async def doc_templates_edit_canon(template_id: int, request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/doc-templates/{template_id}/edit")
        try:
            from routes.doc_templates import edit_template as _fn
            ctx = await _delegate_async(_fn, template_id=template_id, request=request, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/doc_templates/form.html", ctx)

    # ─────────── Payments (Stripe flow rich) ───────────
    @app.get(f"{PREFIX}/payments", response_class=HTMLResponse)
    async def payments_list_canon(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/payments")
        ctx = {**get_context(request, db, user=user), "user": user, "today": date.today()}
        try:
            # Legacy fn is `payment_overview`, not `overview`.
            from routes.payments import payment_overview as _fn  # type: ignore
            extra = await _delegate_async(_fn, request=request, db=db)
            ctx.update(extra)
        except Exception:
            pass
        return templates.TemplateResponse("app/payments/list.html", ctx)

    @app.get(f"{PREFIX}/payments/success", response_class=HTMLResponse)
    async def payments_success_canon(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/payments/success")
        ctx = {**get_context(request, db, user=user), "user": user, "today": date.today()}
        return templates.TemplateResponse("app/payments/success.html", ctx)

    @app.get(f"{PREFIX}/payments/cancel", response_class=HTMLResponse)
    async def payments_cancel_canon(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/payments/cancel")
        ctx = {**get_context(request, db, user=user), "user": user, "today": date.today()}
        return templates.TemplateResponse("app/payments/cancel.html", ctx)

    @app.get(f"{PREFIX}/payments/error", response_class=HTMLResponse)
    async def payments_error_canon(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/payments/error")
        ctx = {**get_context(request, db, user=user), "user": user, "today": date.today()}
        return templates.TemplateResponse("app/payments/error.html", ctx)

    # ─────────── Admin (rich) ───────────
    def _admin_canon(template_name: str, handler_name: str, url_suffix: str):
        async def _impl(request: Request, db: Session = Depends(get_db)):
            user = get_current_user(request, db)
            if not user:
                return _redirect_login(f"{PREFIX}{url_suffix}")
            try:
                from routes import admin as _admin_mod
                fn = getattr(_admin_mod, handler_name, None)
                if fn:
                    ctx = await _delegate_async(fn, request=request, db=db)
                else:
                    ctx = {}
            except Exception:
                ctx = {}
            ctx.setdefault("user", user); ctx.setdefault("today", date.today())
            ctx.update(get_context(request, db, user=user))
            return templates.TemplateResponse(template_name, ctx)
        return _impl

    app.get(f"{PREFIX}/admin", response_class=HTMLResponse)(_admin_canon("app/admin/home.html", "admin_home", "/admin"))
    app.get(f"{PREFIX}/admin/users", response_class=HTMLResponse)(_admin_canon("app/admin/users.html", "list_users", "/admin/users"))
    app.get(f"{PREFIX}/admin/users/new", response_class=HTMLResponse)(_admin_canon("app/admin/user_form.html", "new_user_form", "/admin/users/new"))
    app.get(f"{PREFIX}/admin/settings", response_class=HTMLResponse)(_admin_canon("app/admin/settings.html", "admin_settings", "/admin/settings"))

    @app.get(f"{PREFIX}/admin/branding", response_class=HTMLResponse)
    async def admin_branding_canon(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/admin/branding")
        try:
            from routes.branding import branding_page as _fn
            ctx = await _delegate_async(_fn, request=request, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/admin/branding.html", ctx)

    @app.get(f"{PREFIX}/admin/customizacao", response_class=HTMLResponse)
    async def admin_customizacao_canon(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/admin/customizacao")
        try:
            from routes.customizacao import customizacao_page as _fn
            ctx = await _delegate_async(_fn, request=request, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/admin/customizacao.html", ctx)

    @app.get(f"{PREFIX}/admin/design-editor", response_class=HTMLResponse)
    async def admin_design_editor_canon(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/admin/design-editor")
        try:
            # Legacy fn is `design_editor_page`.
            from routes.design_editor import design_editor_page as _fn
            ctx = await _delegate_async(_fn, request=request, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/admin/design_editor.html", ctx)

    # ─────────── Profile + 2FA + Integrations + Subscription ───────────
    @app.get(f"{PREFIX}/profile", response_class=HTMLResponse)
    async def profile_canon(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/profile")
        try:
            from routes.profile import profile_page as _fn
            ctx = await _delegate_async(_fn, request=request, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/profile/index.html", ctx)

    @app.get(f"{PREFIX}/2fa/setup", response_class=HTMLResponse)
    async def two_factor_setup_canon(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/2fa/setup")
        try:
            from routes.two_factor import setup_2fa_page as _fn
            ctx = await _delegate_async(_fn, request=request, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/two_factor/setup.html", ctx)

    @app.get(f"{PREFIX}/integrations", response_class=HTMLResponse)
    async def integrations_canon(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/integrations")
        try:
            from routes.integrations import _integration_cards
            ctx = {"integrations": _integration_cards()}
        except Exception:
            ctx = {"integrations": []}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.setdefault("active_module", "settings")
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/integrations/index.html", ctx)

    @app.get(f"{PREFIX}/subscription", response_class=HTMLResponse)
    async def subscription_canon(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/subscription")
        try:
            from routes.subscription import subscription_dashboard as _fn
            ctx = await _delegate_async(_fn, request=request, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/subscription/index.html", ctx)

    def _customizacao_redirect(tab: str):
        def _impl():
            return RedirectResponse(url=f"{PREFIX}/admin/customizacao?tab={tab}", status_code=302)
        return _impl

    # `integracoes` tab → canonical /integrations hub (audit P0.3:
    # eliminate 3 concurrent integration screens). 301 permanent so search
    # engines and bookmarks update.
    @app.get(f"{PREFIX}/admin/customizacao/integracoes", include_in_schema=False)
    async def _customizacao_integracoes_to_hub():
        return RedirectResponse(url=f"{PREFIX}/integrations", status_code=301)

    for _customizacao_tab in ("notificacoes", "aparencia", "sidebar", "widgets"):
        app.get(f"{PREFIX}/admin/customizacao/{_customizacao_tab}")(_customizacao_redirect(_customizacao_tab))

    # ─────────── Settings sub ───────────
    @app.get(f"{PREFIX}/settings/numbering", response_class=HTMLResponse)
    async def settings_numbering_canon(request: Request, db: Session = Depends(get_db)):
        user = get_current_user(request, db)
        if not user:
            return _redirect_login(f"{PREFIX}/settings/numbering")
        try:
            from routes.settings import numbering_settings_page as _fn
            ctx = await _delegate_async(_fn, request=request, db=db)
        except Exception:
            ctx = {}
        ctx.setdefault("user", user); ctx.setdefault("today", date.today())
        ctx.update(get_context(request, db, user=user))
        return templates.TemplateResponse("app/settings/numbering.html", ctx)
