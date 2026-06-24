from core.template_config import PREFIX
from routes.sso import _normalize_sso_redirect_url


def test_normalize_sso_redirect_rejects_absolute_url():
    assert _normalize_sso_redirect_url("https://evil.example/path") == f"{PREFIX}/"


def test_normalize_sso_redirect_rejects_protocol_relative_url():
    assert _normalize_sso_redirect_url("//evil.example/path") == f"{PREFIX}/"


def test_normalize_sso_redirect_rejects_path_outside_prefix():
    assert _normalize_sso_redirect_url("/admin") == f"{PREFIX}/"


def test_normalize_sso_redirect_preserves_prefixed_path():
    assert _normalize_sso_redirect_url(f"{PREFIX}/dashboard") == f"{PREFIX}/dashboard"


def test_normalize_sso_redirect_normalizes_prefix_root():
    assert _normalize_sso_redirect_url(PREFIX) == f"{PREFIX}/"
