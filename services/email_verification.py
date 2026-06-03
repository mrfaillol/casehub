"""
CaseHub - Email verification token issuance + consumption.

Used by self-service signup (Fatia B). Tokens are 256-bit URL-safe randoms,
stored in `email_verifications` (created by migration 2026-05-24).

Gated: only invoked when settings.SELF_SERVICE_SIGNUP_ENABLED=True.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings

logger = logging.getLogger(__name__)


def issue_token(
    db: Session,
    user_id: int,
    email: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    ttl_hours: Optional[int] = None,
) -> str:
    """Generate + persist a verification token; return the bare token string."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=ttl_hours or settings.EMAIL_VERIFY_TOKEN_TTL_HOURS)

    db.execute(
        text("""
            INSERT INTO email_verifications (user_id, token, email, expires_at, ip_address, user_agent)
            VALUES (:user_id, :token, :email, :expires_at, :ip, :ua)
        """),
        {
            "user_id": user_id,
            "token": token,
            "email": email,
            "expires_at": expires_at,
            "ip": ip_address,
            "ua": user_agent,
        },
    )
    db.commit()
    return token


def consume_token(db: Session, token: str) -> Optional[dict]:
    """Atomically validate + consume a token.

    Returns the row dict if valid + previously unconsumed; None otherwise.
    """
    if not token:
        return None

    result = db.execute(
        text("""
            UPDATE email_verifications
               SET consumed_at = NOW()
             WHERE token = :token
               AND consumed_at IS NULL
               AND expires_at > NOW()
            RETURNING user_id, email, expires_at, consumed_at
        """),
        {"token": token},
    ).mappings().first()

    if not result:
        return None

    db.commit()
    return dict(result)


def latest_pending_for_user(db: Session, user_id: int) -> Optional[dict]:
    """Inspect helper — return the most recent unconsumed token (or None)."""
    result = db.execute(
        text("""
            SELECT id, token, email, expires_at, created_at
              FROM email_verifications
             WHERE user_id = :user_id
               AND consumed_at IS NULL
               AND expires_at > NOW()
          ORDER BY id DESC
             LIMIT 1
        """),
        {"user_id": user_id},
    ).mappings().first()
    return dict(result) if result else None
