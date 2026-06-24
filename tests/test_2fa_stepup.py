"""Tests for step-up 2FA verification (T10 real fix, issue #805 / CWE-308).

Covers two layers:
  1. core.stepup — the signed, short-lived, user-bound marker (sign/verify,
     tamper / wrong-user / expiry rejection).
  2. routes.two_factor.step_up_verify — POST /2fa/step-up: a good TOTP code sets
     the signed cookie (302 -> next); a bad code returns 400 and sets no cookie.

The enforcement-side behavior (enrolled + no/expired/tampered/other-user cookie
-> redirect to challenge; valid cookie -> allowed) is covered in
tests/test_superadmin_2fa_enforcement.py.
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.stepup import (
    STEPUP_COOKIE_NAME,
    STEPUP_TTL_SECONDS,
    issue_token,
    verify_token,
)


# ── core.stepup signing primitive ─────────────────────────────────────────

class TestStepUpToken:
    def test_roundtrip_valid(self):
        tok = issue_token(7)
        assert verify_token(tok, 7) is True

    def test_missing_token_rejected(self):
        assert verify_token(None, 7) is False
        assert verify_token("", 7) is False

    def test_malformed_token_rejected(self):
        assert verify_token("garbage", 7) is False
        assert verify_token("no-dot-here", 7) is False
        assert verify_token("1:123.", 7) is False  # empty signature

    def test_tampered_signature_rejected(self):
        tok = issue_token(7)
        assert verify_token(tok + "00", 7) is False
        payload, _, sig = tok.rpartition(".")
        assert verify_token(f"{payload}.{'0' * len(sig)}", 7) is False

    def test_tampered_payload_rejected(self):
        # Re-using the signature with a different user id must fail (binding).
        tok = issue_token(7)
        payload, _, sig = tok.rpartition(".")
        issued = payload.split(":")[1]
        forged = f"8:{issued}.{sig}"
        assert verify_token(forged, 8) is False

    def test_wrong_user_rejected(self):
        tok = issue_token(7)
        assert verify_token(tok, 8) is False

    def test_expired_rejected(self):
        old = issue_token(7, now=time.time() - (STEPUP_TTL_SECONDS + 60))
        assert verify_token(old, 7) is False

    def test_fresh_within_ttl_accepted(self):
        recent = issue_token(7, now=time.time() - (STEPUP_TTL_SECONDS - 5))
        assert verify_token(recent, 7) is True

    def test_far_future_timestamp_rejected(self):
        future = issue_token(7, now=time.time() + 600)
        assert verify_token(future, 7) is False

    def test_signature_depends_on_secret(self):
        """A token signed under a different SECRET_KEY must not verify."""
        tok = issue_token(7)
        # Re-import-free: patch settings and clear the lazily-derived nothing —
        # _signing_key reads settings.SECRET_KEY on every call.
        with patch("config.settings") as fake_settings:
            fake_settings.SECRET_KEY = "a-totally-different-secret-value-xxxx"
            assert verify_token(tok, 7) is False


# ── POST /2fa/step-up endpoint ─────────────────────────────────────────────

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _user(uid=1, email="root@casehub.legal"):
    return SimpleNamespace(id=uid, email=email, user_type="superadmin")


class TestStepUpVerifyEndpoint:
    def test_good_code_sets_signed_cookie_and_redirects(self):
        from routes import two_factor as tf

        user = _user()
        request = MagicMock()
        db = MagicMock()
        with patch.object(tf, "get_current_user", return_value=user), patch.object(
            tf, "TwoFactorService"
        ) as svc:
            svc.return_value.verify_code.return_value = True
            resp = _run(
                tf.step_up_verify(
                    request, code="123456", next="/casehub/superadmin/orgs/3", db=db
                )
            )

        assert resp.status_code == 302
        assert resp.headers["location"] == "/casehub/superadmin/orgs/3"
        set_cookie = resp.headers.get("set-cookie", "")
        assert STEPUP_COOKIE_NAME in set_cookie
        assert "HttpOnly" in set_cookie
        assert "lax" in set_cookie.lower()
        # The cookie value must be a valid, user-bound marker.
        # Extract "<name>=<value>;" from the Set-Cookie header.
        val = set_cookie.split(STEPUP_COOKIE_NAME + "=", 1)[1].split(";", 1)[0]
        assert verify_token(val, user.id) is True

    def test_bad_code_returns_400_and_no_cookie(self):
        from routes import two_factor as tf

        user = _user()
        request = MagicMock()
        db = MagicMock()
        with patch.object(tf, "get_current_user", return_value=user), patch.object(
            tf, "TwoFactorService"
        ) as svc:
            svc.return_value.verify_code.return_value = False
            resp = _run(tf.step_up_verify(request, code="000000", next="", db=db))

        assert resp.status_code == 400
        assert STEPUP_COOKIE_NAME not in resp.headers.get("set-cookie", "")

    def test_unauthenticated_returns_401(self):
        from routes import two_factor as tf

        request = MagicMock()
        db = MagicMock()
        with patch.object(tf, "get_current_user", return_value=None):
            resp = _run(tf.step_up_verify(request, code="123456", next="", db=db))
        assert resp.status_code == 401

    def test_open_redirect_blocked(self):
        """A non-local `next` must be replaced with a safe local default."""
        from routes import two_factor as tf

        user = _user()
        request = MagicMock()
        db = MagicMock()
        with patch.object(tf, "get_current_user", return_value=user), patch.object(
            tf, "TwoFactorService"
        ) as svc:
            svc.return_value.verify_code.return_value = True
            resp = _run(
                tf.step_up_verify(
                    request, code="123456", next="https://evil.example/", db=db
                )
            )
        assert resp.status_code == 302
        assert "evil.example" not in resp.headers["location"]
        assert resp.headers["location"].startswith("/")
