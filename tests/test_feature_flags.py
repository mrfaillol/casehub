"""Unit tests for core.feature_flags (default-OFF policy, #800).

Covers: registry default is OFF, env-var truthy parsing (ON), explicit OFF /
garbage values, unknown-flag safe fallback, and the policy invariant that
EVERY registered flag defaults to False.
"""
import os
from unittest.mock import patch

from core import feature_flags
from core.feature_flags import REGISTRY, is_enabled

FLAG = "secondary_calendar_sync"
ENV = "CASEHUB_FF_SECONDARY_CALENDAR_SYNC"


def _clear_env():
    return patch.dict(os.environ, {}, clear=False)


class TestDefaultOff:
    def test_registered_flag_defaults_off_when_env_unset(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ENV, None)
            assert is_enabled(FLAG) is False

    def test_every_registered_flag_defaults_off(self):
        # Policy invariant: a "[deploy gated]" flag MUST default OFF.
        for name, flag in REGISTRY.items():
            assert flag.default is False, f"{name} must default OFF"


class TestEnvOverrideOn:
    def test_truthy_values_enable(self):
        for value in ("1", "true", "TRUE", "on", "On", "yes", "YES", " true "):
            with patch.dict(os.environ, {ENV: value}, clear=False):
                assert is_enabled(FLAG) is True, f"{value!r} should enable"


class TestEnvOverrideOff:
    def test_falsey_and_garbage_values_stay_off(self):
        for value in ("0", "false", "off", "no", "", "maybe", "2"):
            with patch.dict(os.environ, {ENV: value}, clear=False):
                assert is_enabled(FLAG) is False, f"{value!r} should stay OFF"


class TestUnknownFlag:
    def test_unknown_flag_logs_and_returns_false(self, caplog):
        with caplog.at_level("WARNING"):
            assert is_enabled("does_not_exist") is False
        assert any("Unknown feature flag" in r.message for r in caplog.records)

    def test_unknown_flag_ignores_matching_env_var(self):
        # Even if someone sets the env var, an unregistered flag stays OFF.
        with patch.dict(os.environ, {"CASEHUB_FF_DOES_NOT_EXIST": "1"}, clear=False):
            assert is_enabled("does_not_exist") is False


class TestEnvVarNaming:
    def test_env_var_name_is_prefixed_uppercase(self):
        assert feature_flags._env_var_name(FLAG) == ENV
