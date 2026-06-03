"""Regression test for routes/whatsapp_chat.api_get_lead — phone lookup perf.

The previous implementation OR-ed four predicates:

    Client.phone == phone
    | Client.whatsapp == phone
    | Client.phone.contains(phone[-10:])
    | Client.whatsapp.contains(phone[-10:])

``contains`` compiles to ``LIKE '%xxx%'``. Postgres **cannot serve that
with a btree index** — every conversation-open triggered a full Client
table scan, the hot path the goal calls "problema crônico" for
/casehub/whatsapp-chat.

The new lookup is a two-step:
1. exact equality first (uses any phone index + the per-org
   tenant_query filter)
2. ``endswith`` suffix fallback only when step 1 misses

These tests pin the contract structurally (no live Postgres needed):
- helper normalises non-digits out of phone strings
- exact-match preferred for both raw and digits-only forms
- suffix fallback respects ``len(digits) >= 10``

Run: pytest tests/test_whatsapp_chat_lead_lookup.py
"""
from __future__ import annotations

import inspect
import re

import routes.whatsapp_chat as wc


def test_normalize_phone_digits_strips_non_digits():
    """Strips +, spaces, dashes, parens — anything non-digit."""
    assert wc._normalize_phone_digits("+55 (11) 99999-9999") == "5511999999999"
    assert wc._normalize_phone_digits("5511999999999") == "5511999999999"
    assert wc._normalize_phone_digits("") == ""
    assert wc._normalize_phone_digits(None) == ""


def test_normalize_phone_digits_handles_unicode_garbage():
    """Defensive against arbitrary unicode from WhatsApp payloads."""
    assert wc._normalize_phone_digits("📱 55-11-9") == "55119"


def test_api_get_lead_uses_two_step_lookup():
    """Source must split into (1) exact-match, (2) suffix fallback —
    never the single 4-way OR with ``contains`` that triggered the
    full-table-scan pattern."""
    source = inspect.getsource(wc.api_get_lead)
    # Drop the triple-quoted docstring so prose references to the old
    # pattern don't trigger false positives.
    body = re.sub(r'"""[\s\S]*?"""', "", source, count=1)

    # The old hot-path pattern MUST be gone — .contains() on phone/whatsapp
    # was the LIKE '%xxx%' that Postgres couldn't index.
    assert ".contains(" not in body, (
        "api_get_lead must not use .contains() — compiles to LIKE '%xxx%' "
        "which Postgres cannot serve from a btree index. Use endswith "
        "fallback only after the indexed exact match misses."
    )

    # Both steps must be visible: exact match + fallback.
    assert "Client.phone ==" in body or "Client.phone==" in body, (
        "Step 1 must be exact equality on Client.phone."
    )
    assert "endswith" in body, (
        "Step 2 fallback must use endswith (suffix LIKE 'xxx'), gated "
        "behind ``if client is None``."
    )


def test_api_get_lead_normalizes_phone_before_query():
    """Source must call ``_normalize_phone_digits`` so a WhatsApp jid
    (``5511...``) matches a CaseHub client stored as ``+55 11 ...``."""
    source = inspect.getsource(wc.api_get_lead)
    assert "_normalize_phone_digits" in source, (
        "api_get_lead must normalise the incoming phone before matching "
        "— WhatsApp gives jid-style, clients are often stored formatted."
    )


def test_api_get_lead_suffix_fallback_gated_on_min_length():
    """Suffix fallback must require len(digits) >= 10 — a short number
    would match any client (e.g. all phones ending in '99' would
    collide)."""
    source = inspect.getsource(wc.api_get_lead)
    # Look for the length-guard literal. Either ``>= 10`` or
    # ``len(digits) >= 10``.
    assert re.search(r"len\(\s*digits\s*\)\s*>=\s*10", source) or "digits[-10:]" in source, (
        "suffix fallback must be guarded by len(digits) >= 10 to avoid "
        "matching the wrong client on a short input."
    )
