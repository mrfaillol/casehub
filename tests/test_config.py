"""
Test CaseHub Configuration (config.py).
Validates that Settings enforces required fields and produces correct defaults.
"""
import os
import pytest
from unittest.mock import patch


class TestSettingsRequiredFields:
    """Test that Settings enforces SECRET_KEY and DATABASE_URL."""

    def test_secret_key_must_be_set(self):
        """Settings should reject an empty SECRET_KEY (calls sys.exit)."""
        # The validator calls sys.exit(1) when SECRET_KEY is empty.
        # We need to catch SystemExit rather than ValidationError.
        import importlib
        env = {
            "SECRET_KEY": "",
            "DATABASE_URL": "sqlite:///test.db",
        }
        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(SystemExit):
                # Force re-import to trigger validation
                import config as _cfg
                importlib.reload(_cfg)

    def test_settings_accepts_valid_secret_key(self):
        """Settings should accept a non-empty SECRET_KEY."""
        from config import settings
        # conftest.py already sets SECRET_KEY to a valid value
        assert settings.SECRET_KEY is not None
        assert len(settings.SECRET_KEY) > 0

    def test_settings_has_database_url(self):
        """Settings should have a non-empty DATABASE_URL."""
        from config import settings
        assert settings.DATABASE_URL is not None
        assert len(settings.DATABASE_URL) > 0


class TestSettingsDefaults:
    """Test that Settings has sensible defaults."""

    def test_default_org_name(self):
        from config import settings
        assert settings.ORG_NAME is not None
        assert len(settings.ORG_NAME) > 0

    def test_default_case_prefix(self):
        from config import settings
        assert settings.CASE_PREFIX == "CH"

    def test_default_host(self):
        from config import settings
        assert settings.HOST == "0.0.0.0"

    def test_default_port(self):
        from config import settings
        assert settings.PORT == 8001

    def test_default_smtp_port(self):
        from config import settings
        assert settings.SMTP_PORT == 587

    def test_default_access_token_minutes(self):
        from config import settings
        assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 480

    def test_default_cookie_name(self):
        from config import settings
        assert settings.COOKIE_NAME == "casehub_token"


class TestSettingsProperties:
    """Test computed properties on Settings."""

    def test_upload_path_fallback(self):
        """When UPLOAD_DIR is empty, upload_path should use BASE_DIR/uploads."""
        from config import settings
        if not settings.UPLOAD_DIR:
            assert settings.upload_path.endswith("uploads")
            assert os.path.isabs(settings.upload_path)

    def test_from_email_contains_org_name(self):
        """from_email should include the org name or SMTP_FROM_NAME."""
        from config import settings
        from_email = settings.from_email
        # Should contain either SMTP_FROM_NAME or ORG_NAME
        assert settings.SMTP_FROM_NAME in from_email or settings.ORG_NAME in from_email


class TestSettingsExtraIgnored:
    """Test that Settings ignores extra env vars (Config.extra = 'ignore')."""

    def test_extra_env_var_does_not_crash(self):
        """Setting an unknown env var should not cause Settings to fail."""
        with patch.dict(os.environ, {"CASEHUB_UNKNOWN_VAR": "test"}, clear=False):
            from config import Settings
            # This should not raise
            s = Settings()
            assert s.SECRET_KEY is not None
