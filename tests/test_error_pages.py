"""
Test CaseHub Error Page Rendering (core/app_factory.py exception handlers).

Validates:
  - 404, 403, 500 error pages render HTML (not JSON)
  - Error pages contain expected content (links, messages)
  - Error pages use org branding when available
  - Error template files exist and have expected structure
"""
import os
import pytest
from unittest.mock import patch, MagicMock
from starlette.requests import Request


def _request_with_accept(accept: str, query_string: bytes = b"") -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/casehub/dashboard",
        "query_string": query_string,
        "headers": [(b"accept", accept.encode("utf-8")), (b"host", b"testserver")],
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
    })


# ---------------------------------------------------------------------------
# Template file existence and content
# ---------------------------------------------------------------------------

class TestErrorTemplateFiles:
    """Verify error template files exist and contain expected content."""

    TEMPLATE_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "templates", "errors",
    )

    def test_404_template_exists(self):
        """templates/errors/404.html must exist."""
        path = os.path.join(self.TEMPLATE_DIR, "404.html")
        assert os.path.isfile(path), f"Missing: {path}"

    def test_403_template_exists(self):
        """templates/errors/403.html must exist."""
        path = os.path.join(self.TEMPLATE_DIR, "403.html")
        assert os.path.isfile(path), f"Missing: {path}"

    def test_500_template_exists(self):
        """templates/errors/500.html must exist."""
        path = os.path.join(self.TEMPLATE_DIR, "500.html")
        assert os.path.isfile(path), f"Missing: {path}"

    def test_404_has_dashboard_link(self):
        """404 page must contain a 'Go to Dashboard' link."""
        path = os.path.join(self.TEMPLATE_DIR, "404.html")
        with open(path) as f:
            content = f.read()
        assert "/dashboard" in content
        assert "go_dashboard" in content.lower() or "Go to Dashboard" in content

    def test_403_has_upgrade_plan_link(self):
        """403 page must contain a plan upgrade link/button."""
        path = os.path.join(self.TEMPLATE_DIR, "403.html")
        with open(path) as f:
            content = f.read()
        assert "upgrade" in content.lower()
        assert "/subscription" in content

    def test_500_has_contact_info(self):
        """500 page must show contact/support info."""
        path = os.path.join(self.TEMPLATE_DIR, "500.html")
        with open(path) as f:
            content = f.read()
        assert "contact" in content.lower() or "support" in content.lower()
        assert "org_email" in content

    def test_500_retry_preserves_query_target(self):
        """500 page retry action should use the request path with query string."""
        path = os.path.join(self.TEMPLATE_DIR, "500.html")
        with open(path) as f:
            content = f.read()
        assert "retry_url" in content
        assert "request.url.path" not in content

    def test_500_uses_i18n_keys(self):
        """500 page user-facing copy should flow through i18n keys."""
        path = os.path.join(self.TEMPLATE_DIR, "500.html")
        with open(path) as f:
            content = f.read()
        assert "error.reference" in content
        assert "error.try_again" in content

    def test_404_uses_org_branding(self):
        """404 page should reference org_name for branding."""
        path = os.path.join(self.TEMPLATE_DIR, "404.html")
        with open(path) as f:
            content = f.read()
        assert "org_name" in content
        assert ("static/img/logo/" + "logo.svg") not in content
        assert ("static/img/logo/" + "logo.png") not in content

    def test_403_uses_org_branding(self):
        """403 page should reference org_name for branding."""
        path = os.path.join(self.TEMPLATE_DIR, "403.html")
        with open(path) as f:
            content = f.read()
        assert "org_name" in content

    def test_500_uses_org_branding(self):
        """500 page should reference org_name for branding."""
        path = os.path.join(self.TEMPLATE_DIR, "500.html")
        with open(path) as f:
            content = f.read()
        assert "org_name" in content


# ---------------------------------------------------------------------------
# Exception handler source inspection
# ---------------------------------------------------------------------------

class TestExceptionHandlerRegistration:
    """Verify the exception handler in app_factory dispatches to correct templates."""

    def _get_handler_source(self):
        """Read the exception handler source from app_factory.py."""
        factory_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "core", "app_factory.py",
        )
        with open(factory_path) as f:
            return f.read()

    def test_handler_catches_404(self):
        """Exception handler must check for status_code == 404."""
        source = self._get_handler_source()
        assert "exc.status_code == 404" in source

    def test_handler_renders_404_template(self):
        """Exception handler must render errors/404.html for 404."""
        source = self._get_handler_source()
        assert 'errors/404.html' in source

    def test_handler_catches_403(self):
        """Exception handler must check for status_code == 403."""
        source = self._get_handler_source()
        assert "exc.status_code == 403" in source

    def test_handler_renders_403_template(self):
        """Exception handler must render errors/403.html for 403."""
        source = self._get_handler_source()
        assert 'errors/403.html' in source

    def test_handler_catches_500(self):
        """Exception handler must handle 500+ status codes."""
        source = self._get_handler_source()
        assert "exc.status_code >= 500" in source

    def test_handler_renders_500_template(self):
        """Exception handler must render errors/500.html for 500."""
        source = self._get_handler_source()
        assert 'errors/500.html' in source

    def test_handler_injects_org_context(self):
        """Exception handler must call inject_org_context for branding."""
        source = self._get_handler_source()
        assert "inject_org_context" in source

    def test_handler_prefers_json_accept(self):
        """Mixed Accept headers should prefer explicit application/json over HTML."""
        source = self._get_handler_source()
        assert "_wants_html_response" in source
        assert "application/json" in source
        assert "html_specificity > json_specificity" in source

    def test_handler_adds_error_ref_to_http_500_json(self):
        """HTTPException 500+ JSON responses should include error_ref."""
        source = self._get_handler_source()
        assert "exc.status_code >= 500" in source
        assert '"error_ref": error_ref' in source
        assert '"detail": "Internal Server Error"' in source

    def test_handler_wraps_500_template_rendering(self):
        """500 template rendering should have a minimal fallback."""
        source = self._get_handler_source()
        assert "_minimal_500_html" in source
        assert "Failed to render 500 template" in source

    def test_handler_passes_detail(self):
        """Exception handler must pass exc.detail to the template context."""
        source = self._get_handler_source()
        assert "exc.detail" in source

    def test_public_error_context_clears_global_contact_fallback(self):
        """Public errors must not inherit tenant contact globals by accident."""
        from core.app_factory import _sanitize_public_error_context

        ctx = _sanitize_public_error_context({"ui_theme": "neuromorphic"})

        assert ctx["org_email"] == ""
        assert ctx["org_phone"] == ""
        assert ctx["org_domain"] == ""

    def test_tenant_error_context_preserves_explicit_contact(self):
        """Resolved tenant context should keep its own support contact."""
        from core.app_factory import _sanitize_public_error_context

        ctx = _sanitize_public_error_context({
            "org_email": "tenant@example.com",
            "org_phone": "+55 32 0000-0000",
            "org_domain": "tenant.example.com",
        })

        assert ctx["org_email"] == "tenant@example.com"
        assert ctx["org_phone"] == "+55 32 0000-0000"
        assert ctx["org_domain"] == "tenant.example.com"


class TestErrorAcceptHelpers:
    """Verify the error-page helper behavior without running the whole app."""

    def test_prefers_json_when_json_q_is_higher(self):
        from core.app_factory import _wants_html_response

        request = _request_with_accept("application/json, text/html;q=0.1")
        assert _wants_html_response(request) is False

    def test_prefers_json_when_wildcard_q_is_higher_than_html(self):
        from core.app_factory import _wants_html_response

        request = _request_with_accept("text/html;q=0.1, */*;q=0.9")
        assert _wants_html_response(request) is False

    def test_prefers_html_when_explicit_html_ties_wildcard(self):
        from core.app_factory import _wants_html_response

        request = _request_with_accept("text/html, */*")
        assert _wants_html_response(request) is True

    def test_prefers_html_when_json_specific_q_is_lower_than_wildcard(self):
        from core.app_factory import _wants_html_response

        request = _request_with_accept("application/json;q=0.1, */*;q=0.9, text/html;q=0.5")
        assert _wants_html_response(request) is True

    def test_treats_text_wildcard_as_html_capable(self):
        from core.app_factory import _wants_html_response

        request = _request_with_accept("text/*;q=1, application/json;q=0.5")
        assert _wants_html_response(request) is True

    def test_prefers_json_for_problem_json_media_type(self):
        from core.app_factory import _wants_html_response

        request = _request_with_accept("application/problem+json, text/html;q=0.1")
        assert _wants_html_response(request) is False

    def test_prefers_html_when_html_q_is_higher(self):
        from core.app_factory import _wants_html_response

        request = _request_with_accept("text/html, application/json;q=0.1")
        assert _wants_html_response(request) is True

    def test_retry_url_preserves_query_string(self):
        from core.app_factory import _request_path_with_query

        request = _request_with_accept("text/html", b"page=2&filter=open")
        assert _request_path_with_query(request) == "/casehub/dashboard?page=2&filter=open"
