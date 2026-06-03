"""
CaseHub - Cloudflare Turnstile captcha wrapper.

Used by self-service signup (Fatia B). Verifies the cf-turnstile-response token
against Cloudflare's siteverify endpoint. When CF_TURNSTILE_SECRET_KEY is empty
(dev mode), validation auto-passes; production MUST set the key.

Gated: only invoked when settings.SELF_SERVICE_SIGNUP_ENABLED=True (which itself
is gated by a Council ruling).
"""
from __future__ import annotations

import logging
import urllib.parse
import urllib.request
import json
from dataclasses import dataclass
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

_TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


@dataclass
class CaptchaResult:
    success: bool
    score: Optional[float] = None
    error_codes: Optional[list] = None
    dev_bypass: bool = False

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "score": self.score,
            "error_codes": self.error_codes or [],
            "dev_bypass": self.dev_bypass,
        }


def is_enabled() -> bool:
    return bool(settings.CF_TURNSTILE_SECRET_KEY)


def verify(token: str, remote_ip: Optional[str] = None, timeout: float = 5.0) -> CaptchaResult:
    """Verify a Turnstile token. Dev mode (no secret) auto-passes with audit log."""
    if not is_enabled():
        logger.warning("captcha verify called with empty CF_TURNSTILE_SECRET_KEY — bypassing (dev mode)")
        return CaptchaResult(success=True, dev_bypass=True)

    if not token:
        return CaptchaResult(success=False, error_codes=["missing-input-response"])

    data = {
        "secret": settings.CF_TURNSTILE_SECRET_KEY,
        "response": token,
    }
    if remote_ip:
        data["remoteip"] = remote_ip

    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(_TURNSTILE_VERIFY_URL, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.error(f"captcha verify network error: {e}")
        return CaptchaResult(success=False, error_codes=["network-error"])

    return CaptchaResult(
        success=bool(payload.get("success")),
        error_codes=payload.get("error-codes") or [],
    )
