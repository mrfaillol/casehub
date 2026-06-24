"""Short-lived, signed step-up verification marker (T10 / #805, CWE-308).

CaseHub auth is a stateless JWT cookie; there is NO SessionMiddleware, so there
is nowhere server-side to record "this session passed a fresh 2FA challenge".
This module provides a small, self-contained signed cookie that proves a user
verified a TOTP code *recently*:

    payload = "<user_id>:<issued_at_epoch>"
    cookie  = "<payload>.<hex_hmac_sha256(payload, key)>"

The key is derived from ``settings.SECRET_KEY`` (the same secret already used to
sign JWTs), namespaced so the step-up signature can never be confused with any
other use of the secret. Verification is constant-time (``hmac.compare_digest``)
and re-checks both the binding (user id) and the freshness (TTL) on every read.

NO NEW DEPENDENCY: ``itsdangerous`` is not declared in requirements
(requirements.txt / requirements-lite.txt only pull pyotp for 2FA), so we use
the stdlib ``hmac`` + ``hashlib`` + ``time`` rather than adding a package.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time

logger = logging.getLogger(__name__)

# Cookie that carries the signed step-up marker.
STEPUP_COOKIE_NAME = "sa_2fa_stepup"

# How long a fresh verification is honoured before a new challenge is required.
STEPUP_TTL_SECONDS = 600  # 10 minutes

# Namespacing so this HMAC use can never collide with JWT signing etc.
_KEY_NAMESPACE = b"casehub.superadmin.2fa.stepup.v1"

_SEP = "."


def _signing_key() -> bytes:
    """Derive a dedicated signing key from the app SECRET_KEY.

    Imported lazily so this module has no import-time dependency on settings
    (keeps it trivially unit-testable and avoids import cycles).
    """
    from config import settings

    secret = (settings.SECRET_KEY or "").encode("utf-8")
    return hmac.new(_KEY_NAMESPACE, secret, hashlib.sha256).digest()


def _sign(payload: str) -> str:
    return hmac.new(_signing_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def issue_token(user_id: int, *, now: float | None = None) -> str:
    """Mint a signed step-up token bound to ``user_id`` and the current time."""
    issued_at = int(now if now is not None else time.time())
    payload = f"{int(user_id)}:{issued_at}"
    return f"{payload}{_SEP}{_sign(payload)}"


def verify_token(
    token: str | None,
    user_id: int,
    *,
    ttl: int = STEPUP_TTL_SECONDS,
    now: float | None = None,
) -> bool:
    """Return True only if ``token`` is a valid, unexpired, user-bound marker.

    Rejects (returns False) on: missing/malformed token, bad signature
    (tampered), wrong user id (stolen/cross-user), or expired TTL. Never raises
    on bad input — a hostile cookie must read as "no valid step-up", which the
    caller turns into a guided re-challenge (never a lockout).
    """
    if not token:
        return False
    try:
        payload, _, sig = token.rpartition(_SEP)
        if not payload or not sig:
            return False

        expected = _sign(payload)
        # Constant-time compare; both args are hex strings of equal length.
        if not hmac.compare_digest(sig, expected):
            return False

        uid_str, _, issued_str = payload.partition(":")
        token_uid = int(uid_str)
        issued_at = int(issued_str)
    except (ValueError, TypeError):
        return False

    # Binding: the marker must belong to THIS user (defeats a stolen/replayed
    # cookie from another superadmin).
    if token_uid != int(user_id):
        return False

    # Freshness: reject expired markers. Also reject "from the future" beyond a
    # small clock-skew grace, so a forged future timestamp can't extend the TTL.
    current = now if now is not None else time.time()
    age = current - issued_at
    if age > ttl:
        return False
    if age < -30:  # >30s in the future => not a marker we issued
        return False

    return True
