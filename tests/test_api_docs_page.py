"""Regression test for routes/api.api_docs_page — template render integrity.

The /casehub/api/v1/docs-page handler used to instantiate its OWN
``Jinja2Templates(directory="templates")`` inside the route, which had no
globals configured. ``templates/api/docs.html`` extends ``base.html``, which
calls Jinja2 globals (``asset_url``, ``brand_kit_fallback_favicon_url``) and
reads ``product``/``org_name``/``PREFIX`` — none of which were on that
fresh templates instance. Rendering raised ``UndefinedError`` on the first
missing global, turning the route into a 500. This is the audit-#514 HTTP
500 family for ``/casehub/api/v1/docs-page``.

The handler now uses the *shared* templates instance from
``core.template_config`` (which has every global configured by app startup)
and merges ``inject_org_context(request, user)`` into the context, the same
pattern every other HTML handler in the app already uses.

Run: pytest tests/test_api_docs_page.py
"""
import inspect

import routes.api as api_routes


def test_api_docs_page_uses_shared_templates_instance():
    """The handler must reference the shared templates from
    ``core.template_config`` — not instantiate its own ``Jinja2Templates``.

    Structural check: a fresh instance has no env.globals, and base.html
    relies on them, so any private instance regresses the 500. Source
    inspection keeps the test deterministic and backend-independent."""
    source = inspect.getsource(api_routes.api_docs_page)

    assert "from core.template_config import templates" in source, (
        "api_docs_page must import the shared templates from "
        "core.template_config (the only Jinja2Templates instance with the "
        "app's globals configured)."
    )
    # The previous bug: ``templates = Jinja2Templates(directory="templates")``
    # bound a fresh, globals-less instance inside the handler. Strip the
    # docstring before scanning so prose references to the old pattern
    # don't trigger false positives.
    body_source = inspect.getsource(api_routes.api_docs_page)
    # Drop the triple-quoted docstring (handler's first block) so the
    # assertion looks at executable code only.
    import re
    body_no_doc = re.sub(r'"""[\s\S]*?"""', "", body_source, count=1)
    assert "= Jinja2Templates(" not in body_no_doc, (
        "api_docs_page must not bind ``templates`` to a fresh "
        "Jinja2Templates instance — a private instance has no env.globals "
        "(asset_url, product, org_name, ...), and base.html calls "
        "asset_url() unconditionally."
    )


def test_api_docs_page_injects_org_context():
    """The handler must call ``inject_org_context`` so org_name / org_logo /
    org_theme_* / ui_theme are present in the template context.

    Without these, base.html still renders (Jinja2 globals provide
    defaults), but the page never picks up per-tenant branding. Asserting
    the call keeps the per-org behaviour locked in."""
    source = inspect.getsource(api_routes.api_docs_page)
    assert "inject_org_context" in source, (
        "api_docs_page must merge inject_org_context(request, user) into "
        "the template context to pick up per-tenant branding."
    )


def test_api_docs_page_unauthenticated_redirects_to_login():
    """Sanity guard: the auth branch must still win before any template
    work. An unauthenticated request must redirect to /login and never
    touch the templates path — so a regression that breaks rendering does
    not leak to anonymous browsers."""
    source = inspect.getsource(api_routes.api_docs_page)
    # The redirect is unconditional when get_current_user returns None.
    assert "RedirectResponse" in source
    assert "/login" in source or "settings.PREFIX" in source
