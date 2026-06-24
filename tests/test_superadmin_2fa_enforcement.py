"""Tests for 2FA enforcement on sensitive superadmin paths (issue #805 / T10, CWE-308).

The enforcement lives in ``routes.superadmin.enforce_superadmin_2fa`` and is
gated by the default-OFF feature flag ``superadmin_2fa_enforcement`` (env var
``CASEHUB_FF_SUPERADMIN_2FA_ENFORCEMENT``).

HARD SAFETY CONTRACT under test (must never regress):
  (a) Flag OFF (default = current prod) -> guard returns None: sensitive
      superadmin paths behave EXACTLY as before, no new 2FA requirement, and
      a superadmin can NEVER be locked out.
  (b) Flag ON + superadmin has 2FA enrolled -> guard returns None (allowed).
  (c) Flag ON + superadmin NOT enrolled -> guard returns a RedirectResponse to
      the 2FA setup page (enrollment grace) — NOT a 403 hard lockout / dead-end.
  (d) Flag ON but 2FA state cannot be read -> guard returns None (fail-open so
      the only platform admin is never locked out).
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from fastapi.responses import RedirectResponse

from core.feature_flags import REGISTRY
from core.stepup import STEPUP_COOKIE_NAME, issue_token
from routes.superadmin import enforce_superadmin_2fa, SUPERADMIN_2FA_FLAG

ENV = "CASEHUB_FF_SUPERADMIN_2FA_ENFORCEMENT"


def _superadmin(user_id=1, email="root@casehub.legal"):
    return SimpleNamespace(id=user_id, email=email, user_type="superadmin")


def _request(cookies=None, path="/casehub/superadmin/impersonate/9"):
    """A minimal request double with a cookies dict and a URL path."""
    req = MagicMock()
    req.cookies = cookies or {}
    req.url = SimpleNamespace(path=path)
    return req


def _flag_off():
    """Force the flag OFF regardless of ambient environment."""
    return patch.dict(os.environ, {ENV: "0"}, clear=False)


def _flag_on():
    return patch.dict(os.environ, {ENV: "1"}, clear=False)


class TestFlagRegistered:
    def test_flag_is_registered_and_defaults_off(self):
        assert SUPERADMIN_2FA_FLAG in REGISTRY
        assert REGISTRY[SUPERADMIN_2FA_FLAG].default is False


class TestFlagOffUnchanged:
    def test_flag_off_returns_none_even_when_not_enrolled(self):
        """(a) Flag OFF = current behavior; never blocks, never redirects."""
        request = MagicMock()
        db = MagicMock()
        with _flag_off(), patch(
            "services.two_factor.TwoFactorService"
        ) as svc:
            # Even if 2FA is not enrolled, OFF must short-circuit before any check.
            svc.return_value.is_2fa_required.return_value = False
            result = enforce_superadmin_2fa(request, db, _superadmin())
        assert result is None
        # Flag OFF must not even consult 2FA state.
        svc.return_value.is_2fa_required.assert_not_called()


class TestFlagOnEnrolled:
    def test_flag_on_enrolled_with_valid_stepup_is_allowed(self):
        """(b) Flag ON + enrolled + fresh signed step-up cookie -> allowed (None)."""
        user = _superadmin()
        cookie = issue_token(user.id)
        request = _request(cookies={STEPUP_COOKIE_NAME: cookie})
        db = MagicMock()
        with _flag_on(), patch("services.two_factor.TwoFactorService") as svc:
            svc.return_value.is_2fa_required.return_value = True
            result = enforce_superadmin_2fa(request, db, user)
        assert result is None

    def test_flag_on_enrolled_without_stepup_redirects_to_challenge(self):
        """(b') Flag ON + enrolled but NO step-up cookie -> redirect to challenge
        (NOT a 403; enrollment alone is no longer sufficient — real T10 fix)."""
        user = _superadmin()
        request = _request(cookies={})
        db = MagicMock()
        with _flag_on(), patch("services.two_factor.TwoFactorService") as svc:
            svc.return_value.is_2fa_required.return_value = True
            result = enforce_superadmin_2fa(request, db, user)
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        location = result.headers["location"]
        assert "/2fa/step-up" in location
        assert "403" not in location
        # the original path is preserved so the user is bounced back after verifying
        assert "next=" in location

    def test_flag_on_enrolled_with_tampered_cookie_redirects(self):
        """(b'') Tampered signature -> rejected -> re-challenge."""
        user = _superadmin()
        bad = issue_token(user.id) + "deadbeef"
        request = _request(cookies={STEPUP_COOKIE_NAME: bad})
        db = MagicMock()
        with _flag_on(), patch("services.two_factor.TwoFactorService") as svc:
            svc.return_value.is_2fa_required.return_value = True
            result = enforce_superadmin_2fa(request, db, user)
        assert isinstance(result, RedirectResponse)
        assert "/2fa/step-up" in result.headers["location"]

    def test_flag_on_enrolled_with_other_user_cookie_redirects(self):
        """(b''') A valid cookie minted for a DIFFERENT user must not pass
        (defeats a stolen/replayed cross-user step-up cookie)."""
        attacker = _superadmin(user_id=2)
        other_cookie = issue_token(99)  # minted for someone else
        request = _request(cookies={STEPUP_COOKIE_NAME: other_cookie})
        db = MagicMock()
        with _flag_on(), patch("services.two_factor.TwoFactorService") as svc:
            svc.return_value.is_2fa_required.return_value = True
            result = enforce_superadmin_2fa(request, db, attacker)
        assert isinstance(result, RedirectResponse)
        assert "/2fa/step-up" in result.headers["location"]

    def test_flag_on_enrolled_with_expired_cookie_redirects(self):
        """(b'''') An expired step-up cookie must not pass -> re-challenge."""
        import time

        user = _superadmin()
        expired = issue_token(user.id, now=time.time() - 10_000)  # well past TTL
        request = _request(cookies={STEPUP_COOKIE_NAME: expired})
        db = MagicMock()
        with _flag_on(), patch("services.two_factor.TwoFactorService") as svc:
            svc.return_value.is_2fa_required.return_value = True
            result = enforce_superadmin_2fa(request, db, user)
        assert isinstance(result, RedirectResponse)
        assert "/2fa/step-up" in result.headers["location"]


class TestFlagOnNotEnrolledGrace:
    def test_flag_on_not_enrolled_redirects_to_setup_not_403(self):
        """(c) Flag ON + not enrolled -> redirect to setup, NOT a hard 403."""
        request = MagicMock()
        db = MagicMock()
        with _flag_on(), patch("services.two_factor.TwoFactorService") as svc:
            svc.return_value.is_2fa_required.return_value = False
            result = enforce_superadmin_2fa(request, db, _superadmin())

        assert isinstance(result, RedirectResponse)
        # Graceful guided enrollment: a temporary redirect, never a 403 dead-end.
        assert result.status_code == 302
        location = result.headers["location"]
        assert "/2fa/setup" in location
        # Sanity: the no-lockout guarantee — it points at setup, not at a deny page.
        assert "403" not in location


class TestFailOpenNeverLocksOut:
    def test_flag_on_db_error_fails_open(self):
        """(d) Flag ON + transient DB error reading 2FA state -> allow (no lockout).

        Sentinela PR #806: fail-open is scoped to SQLAlchemyError only, so a DB
        hiccup never locks out the single platform admin.
        """
        from sqlalchemy.exc import OperationalError

        request = MagicMock()
        db = MagicMock()
        with _flag_on(), patch("services.two_factor.TwoFactorService") as svc:
            svc.return_value.is_2fa_required.side_effect = OperationalError(
                "SELECT totp_enabled", {}, Exception("db down")
            )
            result = enforce_superadmin_2fa(request, db, _superadmin())
        assert result is None

    def test_flag_on_non_db_error_propagates(self):
        """(d') Flag ON + a NON-DB error (e.g. code/schema drift) must NOT be
        silently swallowed as allow — it propagates loudly so the control can't
        be permanently disabled in silence (Sentinela PR #806)."""
        request = MagicMock()
        db = MagicMock()
        with _flag_on(), patch("services.two_factor.TwoFactorService") as svc:
            svc.return_value.is_2fa_required.side_effect = AttributeError("drift")
            with pytest.raises(AttributeError):
                enforce_superadmin_2fa(request, db, _superadmin())
