"""
Test CaseHub Internationalization (i18n) module.

The i18n package (i18n/__init__.py) is the active translation system.
It provides "en" and "pt" translation dictionaries.

Note: A root-level i18n.py file also exists with "en"/"pt-BR" keys
but it is shadowed by the i18n/ package at import time.
"""
import pytest

from i18n import TRANSLATIONS, DEFAULT_LANG, get_translations


# ===================================================================
# Core get_translations tests
# ===================================================================

class TestGetTranslations:
    """Test the get_translations function."""

    def test_get_translations_en(self):
        """get_translations('en') should return English translations."""
        t = get_translations("en")
        assert isinstance(t, dict)
        assert len(t) > 0
        assert t.get("dashboard") == "Dashboard"

    def test_get_translations_pt(self):
        """get_translations('pt') should return Portuguese translations."""
        t = get_translations("pt")
        assert isinstance(t, dict)
        assert len(t) > 0
        assert t.get("dashboard") == "Painel"

    def test_get_translations_unknown_lang_returns_default(self):
        """get_translations with an unknown language should return default."""
        t = get_translations("xx-YY")
        t_default = get_translations(DEFAULT_LANG)
        assert t == t_default

    def test_get_translations_none_returns_default(self):
        """get_translations(None) should return DEFAULT_LANG translations."""
        t = get_translations(None)
        t_default = get_translations(DEFAULT_LANG)
        assert t == t_default

    def test_get_translations_empty_string_returns_default(self):
        """get_translations('') should return default translations."""
        t = get_translations("")
        t_default = get_translations(DEFAULT_LANG)
        assert t == t_default


# ===================================================================
# Language aliases and fallback
# ===================================================================

class TestLanguageFallback:
    """Test language alias handling and fallback behavior."""

    def test_pt_br_maps_to_portuguese(self):
        """get_translations('pt-BR') should use the supported Portuguese short keys."""
        t = get_translations("pt-BR")
        assert t == get_translations("pt")

    def test_default_lang_is_en(self):
        """The default language should be 'en'."""
        assert DEFAULT_LANG == "en"

    def test_supported_languages(self):
        """TRANSLATIONS should include at least 'en' and 'pt'."""
        assert "en" in TRANSLATIONS
        assert "pt" in TRANSLATIONS


# ===================================================================
# Translation parity checks
# ===================================================================

class TestTranslationParity:
    """Ensure all translation dictionaries have matching keys."""

    def test_en_pt_key_parity(self):
        """All keys in 'en' should also exist in 'pt'."""
        en_keys = set(TRANSLATIONS["en"].keys())
        pt_keys = set(TRANSLATIONS["pt"].keys())
        missing_in_pt = en_keys - pt_keys
        assert len(missing_in_pt) == 0, \
            f"Keys in 'en' missing from 'pt': {missing_in_pt}"

    def test_pt_en_key_parity(self):
        """All keys in 'pt' should also exist in 'en' (no orphan translations)."""
        en_keys = set(TRANSLATIONS["en"].keys())
        pt_keys = set(TRANSLATIONS["pt"].keys())
        missing_in_en = pt_keys - en_keys
        assert len(missing_in_en) == 0, \
            f"Keys in 'pt' missing from 'en': {missing_in_en}"

    def test_no_empty_translation_values_en(self):
        """No English translation value should be empty."""
        for key, value in TRANSLATIONS["en"].items():
            assert value, f"Empty translation in 'en' for key '{key}'"

    def test_no_empty_translation_values_pt(self):
        """No Portuguese translation value should be empty."""
        for key, value in TRANSLATIONS["pt"].items():
            assert value, f"Empty translation in 'pt' for key '{key}'"

    def test_all_values_are_strings(self):
        """All translation values should be strings."""
        for lang, translations in TRANSLATIONS.items():
            for key, value in translations.items():
                assert isinstance(value, str), \
                    f"Translation [{lang}][{key}] is {type(value).__name__}, expected str"


# ===================================================================
# Translation content spot-checks
# ===================================================================

class TestTranslationContent:
    """Spot-check specific translation values."""

    def test_en_has_common_keys(self):
        """English translations should have common UI keys."""
        en = TRANSLATIONS["en"]
        expected_keys = ["dashboard", "clients", "cases", "documents", "save",
                         "cancel", "delete", "edit", "search", "status"]
        for key in expected_keys:
            assert key in en, f"Missing expected key '{key}' in 'en'"

    def test_pt_has_common_keys(self):
        """Portuguese translations should have common UI keys."""
        pt = TRANSLATIONS["pt"]
        expected_keys = ["dashboard", "clients", "cases", "documents", "save",
                         "cancel", "delete", "edit", "search", "status"]
        for key in expected_keys:
            assert key in pt, f"Missing expected key '{key}' in 'pt'"

    def test_en_dashboard_is_dashboard(self):
        assert TRANSLATIONS["en"]["dashboard"] == "Dashboard"

    def test_pt_dashboard_is_painel(self):
        assert TRANSLATIONS["pt"]["dashboard"] == "Painel"

    def test_en_save_is_save(self):
        assert TRANSLATIONS["en"]["save"] == "Save"

    def test_pt_save_is_salvar(self):
        assert TRANSLATIONS["pt"]["save"] == "Salvar"

    def test_en_logout(self):
        assert TRANSLATIONS["en"]["logout"] == "Logout"

    def test_pt_logout_is_sair(self):
        assert TRANSLATIONS["pt"]["logout"] == "Sair"
