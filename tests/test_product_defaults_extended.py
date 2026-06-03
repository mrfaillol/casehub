"""
Test PRODUCT_DEFAULTS in core/app_factory.py — Extended coverage.

Covers:
  - get_product_defaults() returns correct values for immigration and lite
  - Currency, language, timezone, date_format for each product
  - Feature flags for each product
  - Env var overrides via settings.DEFAULT_CURRENCY and DEFAULT_TIMEZONE
  - Template globals injection (currency_symbol, product_features, date_format)
  - Unknown product falls back to immigration defaults
"""
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# PRODUCT_DEFAULTS structure
# ---------------------------------------------------------------------------

class TestProductDefaultsStructure:
    """Test that PRODUCT_DEFAULTS has the expected keys and values."""

    def test_immigration_defaults_currency_usd(self):
        from core.app_factory import PRODUCT_DEFAULTS
        assert PRODUCT_DEFAULTS["immigration"]["currency"] == "USD"

    def test_immigration_defaults_currency_symbol_dollar(self):
        from core.app_factory import PRODUCT_DEFAULTS
        assert PRODUCT_DEFAULTS["immigration"]["currency_symbol"] == "$"

    def test_immigration_defaults_lang_en(self):
        from core.app_factory import PRODUCT_DEFAULTS
        assert PRODUCT_DEFAULTS["immigration"]["default_lang"] == "en"

    def test_immigration_defaults_timezone_new_york(self):
        from core.app_factory import PRODUCT_DEFAULTS
        assert PRODUCT_DEFAULTS["immigration"]["timezone"] == "America/New_York"

    def test_immigration_defaults_date_format_us(self):
        from core.app_factory import PRODUCT_DEFAULTS
        assert PRODUCT_DEFAULTS["immigration"]["date_format"] == "%m/%d/%Y"

    def test_lite_defaults_currency_brl(self):
        from core.app_factory import PRODUCT_DEFAULTS
        assert PRODUCT_DEFAULTS["lite"]["currency"] == "BRL"

    def test_lite_defaults_currency_symbol_real(self):
        from core.app_factory import PRODUCT_DEFAULTS
        assert PRODUCT_DEFAULTS["lite"]["currency_symbol"] == "R$"

    def test_lite_defaults_lang_pt(self):
        from core.app_factory import PRODUCT_DEFAULTS
        assert PRODUCT_DEFAULTS["lite"]["default_lang"] == "pt"

    def test_lite_defaults_timezone_sao_paulo(self):
        from core.app_factory import PRODUCT_DEFAULTS
        assert PRODUCT_DEFAULTS["lite"]["timezone"] == "America/Sao_Paulo"

    def test_lite_defaults_date_format_br(self):
        from core.app_factory import PRODUCT_DEFAULTS
        assert PRODUCT_DEFAULTS["lite"]["date_format"] == "%d/%m/%Y"

    def test_lite_defaults_locale_pt_br(self):
        from core.app_factory import PRODUCT_DEFAULTS
        assert PRODUCT_DEFAULTS["lite"]["currency_locale"] == "pt_BR"

    def test_immigration_defaults_locale_en_us(self):
        from core.app_factory import PRODUCT_DEFAULTS
        assert PRODUCT_DEFAULTS["immigration"]["currency_locale"] == "en_US"


# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------

class TestProductFeatureFlags:
    """Test product-specific feature flags in PRODUCT_DEFAULTS."""

    def test_immigration_has_uscis_tracking(self):
        from core.app_factory import PRODUCT_DEFAULTS
        features = PRODUCT_DEFAULTS["immigration"]["features"]
        assert features["uscis_tracking"] is True

    def test_immigration_has_visa_types(self):
        from core.app_factory import PRODUCT_DEFAULTS
        features = PRODUCT_DEFAULTS["immigration"]["features"]
        assert features["visa_types"] is True

    def test_immigration_has_rfe_management(self):
        from core.app_factory import PRODUCT_DEFAULTS
        features = PRODUCT_DEFAULTS["immigration"]["features"]
        assert features["rfe_management"] is True

    def test_immigration_has_efiling(self):
        from core.app_factory import PRODUCT_DEFAULTS
        features = PRODUCT_DEFAULTS["immigration"]["features"]
        assert features["efiling"] is True

    def test_immigration_has_packet_builder(self):
        from core.app_factory import PRODUCT_DEFAULTS
        features = PRODUCT_DEFAULTS["immigration"]["features"]
        assert features["packet_builder"] is True

    def test_lite_has_processo_tracking(self):
        from core.app_factory import PRODUCT_DEFAULTS
        features = PRODUCT_DEFAULTS["lite"]["features"]
        assert features["processo_tracking"] is True

    def test_lite_has_prazos_processuais(self):
        from core.app_factory import PRODUCT_DEFAULTS
        features = PRODUCT_DEFAULTS["lite"]["features"]
        assert features["prazos_processuais"] is True

    def test_lite_has_oab_lookup(self):
        from core.app_factory import PRODUCT_DEFAULTS
        features = PRODUCT_DEFAULTS["lite"]["features"]
        assert features["oab_lookup"] is True

    def test_lite_has_dark_mode(self):
        from core.app_factory import PRODUCT_DEFAULTS
        features = PRODUCT_DEFAULTS["lite"]["features"]
        assert features["dark_mode"] is True

    def test_lite_no_uscis_tracking(self):
        from core.app_factory import PRODUCT_DEFAULTS
        features = PRODUCT_DEFAULTS["lite"]["features"]
        assert "uscis_tracking" not in features

    def test_immigration_no_processo_tracking(self):
        from core.app_factory import PRODUCT_DEFAULTS
        features = PRODUCT_DEFAULTS["immigration"]["features"]
        assert "processo_tracking" not in features


# ---------------------------------------------------------------------------
# get_product_defaults()
# ---------------------------------------------------------------------------

class TestGetProductDefaults:
    """Test the get_product_defaults() function."""

    def test_immigration_returns_usd(self):
        from core.app_factory import get_product_defaults
        with patch("core.app_factory.settings") as mock_settings:
            mock_settings.DEFAULT_CURRENCY = ""
            mock_settings.DEFAULT_TIMEZONE = ""
            defaults = get_product_defaults("immigration")
        assert defaults["currency"] == "USD"

    def test_lite_returns_brl(self):
        from core.app_factory import get_product_defaults
        with patch("core.app_factory.settings") as mock_settings:
            mock_settings.DEFAULT_CURRENCY = ""
            mock_settings.DEFAULT_TIMEZONE = ""
            defaults = get_product_defaults("lite")
        assert defaults["currency"] == "BRL"

    def test_unknown_product_falls_back_to_immigration(self):
        from core.app_factory import get_product_defaults
        with patch("core.app_factory.settings") as mock_settings:
            mock_settings.DEFAULT_CURRENCY = ""
            mock_settings.DEFAULT_TIMEZONE = ""
            defaults = get_product_defaults("nonexistent")
        assert defaults["currency"] == "USD"
        assert defaults["default_lang"] == "en"

    def test_env_var_overrides_currency(self):
        from core.app_factory import get_product_defaults
        with patch("core.app_factory.settings") as mock_settings:
            mock_settings.DEFAULT_CURRENCY = "EUR"
            mock_settings.DEFAULT_TIMEZONE = ""
            defaults = get_product_defaults("immigration")
        assert defaults["currency"] == "EUR"

    def test_env_var_overrides_timezone(self):
        from core.app_factory import get_product_defaults
        with patch("core.app_factory.settings") as mock_settings:
            mock_settings.DEFAULT_CURRENCY = ""
            mock_settings.DEFAULT_TIMEZONE = "UTC"
            defaults = get_product_defaults("lite")
        assert defaults["timezone"] == "UTC"

    def test_env_override_does_not_mutate_original(self):
        """Overrides should not change the PRODUCT_DEFAULTS dict itself."""
        from core.app_factory import PRODUCT_DEFAULTS, get_product_defaults
        original_currency = PRODUCT_DEFAULTS["immigration"]["currency"]
        with patch("core.app_factory.settings") as mock_settings:
            mock_settings.DEFAULT_CURRENCY = "GBP"
            mock_settings.DEFAULT_TIMEZONE = ""
            get_product_defaults("immigration")
        # Original should be untouched
        assert PRODUCT_DEFAULTS["immigration"]["currency"] == original_currency

    def test_returns_copy_not_reference(self):
        """get_product_defaults should return a copy, not the original dict."""
        from core.app_factory import PRODUCT_DEFAULTS, get_product_defaults
        with patch("core.app_factory.settings") as mock_settings:
            mock_settings.DEFAULT_CURRENCY = ""
            mock_settings.DEFAULT_TIMEZONE = ""
            result = get_product_defaults("immigration")
        # Modifying the result should not affect PRODUCT_DEFAULTS
        result["currency"] = "MODIFIED"
        assert PRODUCT_DEFAULTS["immigration"]["currency"] == "USD"


# ---------------------------------------------------------------------------
# Template globals injection (source inspection)
# ---------------------------------------------------------------------------

class TestTemplateGlobalsInjection:
    """Verify that create_app injects the right globals into Jinja2 templates."""

    def test_create_app_sets_currency_symbol_global(self):
        """create_app source should inject currency_symbol into template globals."""
        import inspect
        from core.app_factory import create_app
        source = inspect.getsource(create_app)
        assert "currency_symbol" in source

    def test_create_app_sets_product_features_global(self):
        import inspect
        from core.app_factory import create_app
        source = inspect.getsource(create_app)
        assert "product_features" in source

    def test_create_app_sets_date_format_global(self):
        import inspect
        from core.app_factory import create_app
        source = inspect.getsource(create_app)
        assert "date_format" in source

    def test_create_app_sets_currency_global(self):
        import inspect
        from core.app_factory import create_app
        source = inspect.getsource(create_app)
        assert '"currency"' in source or "'currency'" in source
