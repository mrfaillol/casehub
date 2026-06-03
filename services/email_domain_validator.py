"""
CaseHub - Email domain validator.

Blocks signup from known disposable / temporary email providers. The list is
non-exhaustive; the goal is to raise the friction floor for abuse, not be a
perfect filter.

Gated: only invoked when settings.SELF_SERVICE_SIGNUP_ENABLED=True.
"""
from __future__ import annotations

import re

DISPOSABLE_DOMAINS = frozenset({
    "mailinator.com",
    "tempmail.com",
    "10minutemail.com",
    "guerrillamail.com",
    "yopmail.com",
    "trashmail.com",
    "throwawaymail.com",
    "sharklasers.com",
    "mailcatch.com",
    "dispostable.com",
    "fakeinbox.com",
    "tempinbox.com",
    "discard.email",
    "getairmail.com",
    "tempmailo.com",
    "tempmail.net",
    "minutemail.com",
    "10minemail.com",
    "maildrop.cc",
    "mailnesia.com",
})

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@([a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})$")


def is_disposable(email: str) -> bool:
    if not email:
        return False
    m = _EMAIL_RE.match(email.strip())
    if not m:
        return False
    return m.group(1).lower() in DISPOSABLE_DOMAINS


def looks_valid(email: str) -> bool:
    if not email:
        return False
    return bool(_EMAIL_RE.match(email.strip()))


def domain_of(email: str) -> str:
    m = _EMAIL_RE.match((email or "").strip())
    return m.group(1).lower() if m else ""
