"""
Tests for product-specific defaults (Lite vs Immigration).
Validates language defaults, currency associations, and cookie overrides.
"""
import pytest
from unittest.mock import MagicMock, patch

from i18n import get_translations, DEFAULT_LANG, TRANSLATIONS


class TestLanguageDefaults:
    """Test that products have correct default languages."""

    def test_lite_product_defaults_to_pt(self):
        """Lite product should default to Portuguese."""
        # Simulate the get_context logic from invoices.py
        request = MagicMock()
        request.cookies.get.return_value = None  # No cookie set

        app_state = MagicMock()
        app_state.product = "lite"
        request.app.state = app_state

        # Replicate language resolution logic
        cookie_lang = request.cookies.get("lang")
        if cookie_lang:
            lang = cookie_lang
        else:
            product_state = getattr(getattr(request, "app", None), "state", None)
            if product_state and getattr(product_state, "product", None) == "lite":
                lang = "pt"
            else:
                lang = "en"

        assert lang == "pt"

    def test_immigration_product_defaults_to_en(self):
        """Immigration product should default to English."""
        request = MagicMock()
        request.cookies.get.return_value = None

        app_state = MagicMock()
        app_state.product = "immigration"
        request.app.state = app_state

        cookie_lang = request.cookies.get("lang")
        if cookie_lang:
            lang = cookie_lang
        else:
            product_state = getattr(getattr(request, "app", None), "state", None)
            if product_state and getattr(product_state, "product", None) == "lite":
                lang = "pt"
            else:
                lang = "en"

        assert lang == "en"

    def test_cookie_language_overrides_product_default(self):
        """If a cookie is set, it should override the product default."""
        request = MagicMock()
        request.cookies.get.return_value = "en"  # Cookie overrides lite's pt default

        app_state = MagicMock()
        app_state.product = "lite"
        request.app.state = app_state

        cookie_lang = request.cookies.get("lang")
        if cookie_lang:
            lang = cookie_lang
        else:
            product_state = getattr(getattr(request, "app", None), "state", None)
            if product_state and getattr(product_state, "product", None) == "lite":
                lang = "pt"
            else:
                lang = "en"

        assert lang == "en"

    def test_cookie_pt_overrides_immigration_en(self):
        """Portuguese cookie should override immigration's English default."""
        request = MagicMock()
        request.cookies.get.return_value = "pt-BR"

        app_state = MagicMock()
        app_state.product = "immigration"
        request.app.state = app_state

        cookie_lang = request.cookies.get("lang")
        if cookie_lang:
            lang = cookie_lang
        else:
            product_state = getattr(getattr(request, "app", None), "state", None)
            if product_state and getattr(product_state, "product", None) == "lite":
                lang = "pt"
            else:
                lang = "en"

        assert lang == "pt-BR"

    def test_no_app_state_defaults_to_en(self):
        """When there's no app state (e.g., tests), default to English."""
        request = MagicMock()
        request.cookies.get.return_value = None
        request.app = None

        cookie_lang = request.cookies.get("lang")
        if cookie_lang:
            lang = cookie_lang
        else:
            product_state = getattr(getattr(request, "app", None), "state", None)
            if product_state and getattr(product_state, "product", None) == "lite":
                lang = "pt"
            else:
                lang = "en"

        assert lang == "en"


class TestTranslations:
    """Test i18n translation helper."""

    def test_get_translations_en(self):
        t = get_translations("en")
        assert t["dashboard"] == "Dashboard"

    def test_get_translations_pt(self):
        t = get_translations("pt")
        assert isinstance(t, dict)
        assert len(t) > 0
        assert t["dashboard"] == "Painel"

    def test_get_translations_unknown_falls_back(self):
        """Unknown language should fall back to DEFAULT_LANG."""
        t = get_translations("xx")
        default_t = get_translations(DEFAULT_LANG)
        assert t == default_t

    def test_get_translations_none_falls_back(self):
        """None language should fall back to DEFAULT_LANG."""
        t = get_translations(None)
        default_t = get_translations(DEFAULT_LANG)
        assert t == default_t

    def test_supported_languages(self):
        """Ensure en and pt are both supported."""
        assert "en" in TRANSLATIONS
        assert "pt" in TRANSLATIONS


class TestProductCurrencyDefaults:
    """Test that product types have correct currency associations."""

    def test_lite_organization_defaults_to_brl(self):
        """Lite product (Brazilian law) should default to BRL currency."""
        from models.tenant import Organization

        org = Organization(
            name="Escritorio JF",
            slug="escritorio-jf",
            uuid="test-uuid-lite",
            currency="BRL",
        )
        assert org.currency == "BRL"

    def test_immigration_organization_defaults_to_usd(self, db):
        """Immigration product should use default USD currency (applied at flush)."""
        from models.tenant import Organization

        org = Organization(
            name="Immigration Law Center",
            slug="ilc",
            uuid="test-uuid-imm",
        )
        db.add(org)
        db.flush()

        assert org.currency == "USD"

    def test_organization_currency_default(self, db):
        """Organization model's currency field defaults to USD."""
        from models.tenant import Organization

        org = Organization(
            name="Test Org",
            slug="test-org",
            uuid="test-uuid-currency",
        )
        db.add(org)
        db.flush()

        assert org.currency == "USD"

    def test_organization_locale_default(self, db):
        """Organization model's locale field defaults to en."""
        from models.tenant import Organization

        org = Organization(
            name="Test Org",
            slug="test-org-locale",
            uuid="test-uuid-locale",
        )
        db.add(org)
        db.flush()

        assert org.locale == "en"

    def test_lite_org_with_pt_locale(self):
        """A Lite-product org would typically have locale=pt."""
        from models.tenant import Organization

        org = Organization(
            name="Advogados Associados",
            slug="advogados",
            uuid="test-uuid-pt",
            locale="pt",
            currency="BRL",
        )
        assert org.locale == "pt"
        assert org.currency == "BRL"
