"""
Test CaseHub App Factory (core/app_factory.py).
Validates that create_app produces correctly configured FastAPI instances
for each product vertical and includes the expected routers.
"""
import os
import pytest
import asyncio
from unittest.mock import patch, MagicMock
from fastapi import FastAPI


class TestCreateApp:
    """Test create_app returns properly configured FastAPI instances."""

    def test_create_app_immigration_returns_fastapi(self):
        """create_app('immigration') should return a FastAPI instance."""
        from core.app_factory import create_app
        with patch("core.app_factory.StaticFiles"), \
             patch("core.app_factory.Jinja2Templates"):
            app = create_app("immigration")
        assert isinstance(app, FastAPI)

    def test_create_app_lite_returns_fastapi(self):
        """create_app('lite') should return a FastAPI instance."""
        from core.app_factory import create_app
        with patch("core.app_factory.StaticFiles"), \
             patch("core.app_factory.Jinja2Templates"):
            app = create_app("lite")
        assert isinstance(app, FastAPI)

    def test_create_app_unknown_product_raises(self):
        """create_app with an unknown product should raise ValueError."""
        from core.app_factory import create_app
        with pytest.raises(ValueError, match="Unknown product"):
            create_app("nonexistent_product")

    def test_immigration_app_version(self):
        """Immigration app should have version 2.0.0."""
        from core.app_factory import create_app
        with patch("core.app_factory.StaticFiles"), \
             patch("core.app_factory.Jinja2Templates"):
            app = create_app("immigration")
        assert app.version == "2.0.0"

    def test_lite_app_description_mentions_lite(self):
        """Lite app description should mention 'lite'."""
        from core.app_factory import create_app
        with patch("core.app_factory.StaticFiles"), \
             patch("core.app_factory.Jinja2Templates"):
            app = create_app("lite")
        assert "lite" in app.description.lower()

    def test_casehub_prefix_root_route_is_registered(self):
        """/casehub should be a canonical entrypoint, not a 404."""
        from core.app_factory import create_app
        with patch("core.app_factory.StaticFiles"), \
             patch("core.app_factory.Jinja2Templates"):
            app = create_app("lite")
        paths = {route.path for route in app.routes}
        assert "/casehub" in paths
        assert "/casehub/" in paths

    def test_casehub_healthz_returns_deploy_marker(self):
        """/casehub/healthz should be usable by VS-prod GitOps health checks."""
        from core.app_factory import create_app

        class FakeDb:
            def execute(self, *_args, **_kwargs):
                return MagicMock(scalar=lambda: 1)

            def close(self):
                pass

        def fake_get_db():
            yield FakeDb()

        with patch("core.app_factory.StaticFiles"), \
             patch("core.app_factory.Jinja2Templates"), \
             patch("core.app_factory.get_db", fake_get_db), \
             patch("core.app_factory.os.path.exists", return_value=True):
            app = create_app("lite")
            route = next(route for route in app.routes if route.path == "/casehub/healthz")
            response = asyncio.run(route.endpoint())

        assert response.status_code == 200
        assert response.body
        assert b"casehub-live-v1" in response.body


class TestRouterSets:
    """Test that products get the correct router sets."""

    def test_core_routers_defined(self):
        """CORE_ROUTERS should be a non-empty list."""
        from core.app_factory import CORE_ROUTERS
        assert isinstance(CORE_ROUTERS, list)
        assert len(CORE_ROUTERS) > 0

    def test_immigration_routers_defined(self):
        """IMMIGRATION_ROUTERS should be a non-empty list."""
        from core.app_factory import IMMIGRATION_ROUTERS
        assert isinstance(IMMIGRATION_ROUTERS, list)
        assert len(IMMIGRATION_ROUTERS) > 0

    def test_immigration_product_includes_core(self):
        """Immigration product should include all core routers."""
        from core.app_factory import PRODUCT_ROUTERS, CORE_ROUTERS
        immigration_routers = PRODUCT_ROUTERS["immigration"]
        for router_name in CORE_ROUTERS:
            assert router_name in immigration_routers, \
                f"Core router '{router_name}' missing from immigration product"

    def test_lite_product_includes_core(self):
        """Lite product should include all core routers."""
        from core.app_factory import PRODUCT_ROUTERS, CORE_ROUTERS
        lite_routers = PRODUCT_ROUTERS["lite"]
        for router_name in CORE_ROUTERS:
            assert router_name in lite_routers, \
                f"Core router '{router_name}' missing from lite product"

    def test_immigration_routers_in_immigration_product(self):
        """Immigration product should include all immigration-specific routers."""
        from core.app_factory import PRODUCT_ROUTERS, IMMIGRATION_ROUTERS
        immigration_product_routers = PRODUCT_ROUTERS["immigration"]
        for router_name in IMMIGRATION_ROUTERS:
            assert router_name in immigration_product_routers, \
                f"Immigration router '{router_name}' missing from immigration product"

    def test_immigration_routers_not_in_lite_product(self):
        """Lite product should NOT include immigration-specific routers."""
        from core.app_factory import PRODUCT_ROUTERS, IMMIGRATION_ROUTERS
        lite_routers = PRODUCT_ROUTERS["lite"]
        clone_shared = {
            "whatsapp_chat",
            "whatsapp_proxy",
            "whatsapp_crm",
            "whatsapp_inbound",
        }
        for router_name in IMMIGRATION_ROUTERS:
            if router_name in clone_shared:
                continue
            assert router_name not in lite_routers, \
                f"Immigration router '{router_name}' should not be in lite product"

    def test_lite_product_excludes_whatsapp_chat_router_by_default(self):
        """Lite defaults must not expose the full WhatsApp bot-control surface."""
        from core.app_factory import PRODUCT_ROUTERS
        assert "whatsapp_chat" not in PRODUCT_ROUTERS["lite"]
        assert "whatsapp_lite" in PRODUCT_ROUTERS["lite"]

    def test_uscis_router_only_in_immigration(self):
        """USCIS router should be in immigration but not in lite."""
        from core.app_factory import PRODUCT_ROUTERS
        assert "uscis" in PRODUCT_ROUTERS["immigration"]
        assert "uscis" not in PRODUCT_ROUTERS["lite"]

    def test_efiling_router_only_in_immigration(self):
        """E-filing router should be in immigration but not in lite."""
        from core.app_factory import PRODUCT_ROUTERS
        assert "efiling" in PRODUCT_ROUTERS["immigration"]
        assert "efiling" not in PRODUCT_ROUTERS["lite"]

    def test_whatsapp_clone_bridge_mounted_with_clone_products(self):
        """The WhatsApp clone stack must include its HMAC inbound bridge."""
        from core.app_factory import CORE_ROUTERS, PRODUCT_ROUTERS

        assert "whatsapp_inbound" not in CORE_ROUTERS
        for product in ("immigration", "lite", "whitelabel"):
            assert "whatsapp_chat" in PRODUCT_ROUTERS[product]
            assert "whatsapp_proxy" in PRODUCT_ROUTERS[product]
            assert "whatsapp_crm" in PRODUCT_ROUTERS[product]
            assert "whatsapp_inbound" in PRODUCT_ROUTERS[product]

    def test_clients_router_in_both_products(self):
        """Clients router should be in both products."""
        from core.app_factory import PRODUCT_ROUTERS
        assert "clients" in PRODUCT_ROUTERS["immigration"]
        assert "clients" in PRODUCT_ROUTERS["lite"]

    def test_cases_router_in_both_products(self):
        """Cases router should be in both products."""
        from core.app_factory import PRODUCT_ROUTERS
        assert "cases" in PRODUCT_ROUTERS["immigration"]
        assert "cases" in PRODUCT_ROUTERS["lite"]

    def test_processes_router_in_both_products(self):
        """Process templates are part of the shared cadastro/processos gate."""
        from core.app_factory import CORE_ROUTERS, PRODUCT_ROUTERS
        assert "processes" in CORE_ROUTERS
        assert "processes" in PRODUCT_ROUTERS["immigration"]
        assert "processes" in PRODUCT_ROUTERS["lite"]


class TestCASEHUBProductEnv:
    """Test that CASEHUB_PRODUCT env var is respected by product app modules."""

    def test_immigration_app_module_creates_immigration(self):
        """products/immigration/app.py should create an immigration app."""
        # The product app modules call create_app with hardcoded product name.
        # We verify the contract by checking that PRODUCT_ROUTERS has the
        # expected keys used by those modules.
        from core.app_factory import PRODUCT_ROUTERS
        assert "immigration" in PRODUCT_ROUTERS
        assert "lite" in PRODUCT_ROUTERS

    def test_product_routers_keys_match_expected(self):
        """PRODUCT_ROUTERS should have exactly the expected product keys."""
        from core.app_factory import PRODUCT_ROUTERS
        expected = {"immigration", "lite", "whitelabel"}
        assert set(PRODUCT_ROUTERS.keys()) == expected

    def test_lite_product_declares_browser_basic_shell(self):
        """Lite should advertise the Basic browser-like shell defaults."""
        from core.app_factory import get_product_defaults
        features = get_product_defaults("lite")["features"]
        assert features["browser_basic_shell"] is True
        assert features["neumorphic_core"] is True
        assert features["hub_tabs"] is False

    def test_org_features_json_string_is_accepted(self):
        """SQLite/local smokes may return JSON fields as strings."""
        from core.template_config import inject_org_context

        request = MagicMock()
        request.state.org = {
            "name": "Test Org",
            "slug": "default",
            "features": '{"hub_tabs": true}',
            "settings": "{}",
        }
        request.state.user = None
        request.app.state.product = "lite"

        ctx = inject_org_context(request)
        assert ctx["org_features"]["browser_basic_shell"] is True
        assert ctx["org_features"]["hub_tabs"] is True
        assert ctx["ui_theme"] == "neuromorphic"
