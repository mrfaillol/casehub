"""Regression tests for routes/notifications_api.whatsapp_message_notification.

Same defect class as PR #579 (routes/whatsapp_chat.api_get_lead): the
webhook used a single OR of two ``.contains()`` predicates on
``Client.phone`` / ``Client.whatsapp``. ``contains`` compiles to
``LIKE '%xxx%'``, Postgres cannot serve from a btree index, every
inbound WhatsApp message triggered a full Client table scan in the
per-org subset.

This webhook is hotter than ``api_get_lead`` — it fires PER inbound
message, not per conversation open.

These tests pin the new two-step lookup structurally:

- Source no longer uses ``.contains()`` on phone/whatsapp.
- Source still defines ``phone_normalized`` and tries exact match
  first.
- Source has an ``endswith`` fallback gated on ``len(phone_normalized)
  >= 10`` so short numbers cannot collide.

Run: pytest tests/test_notifications_api_wa_lookup.py
"""
from __future__ import annotations

import inspect
import re

import routes.notifications_api as nap


def _strip_comments_and_docstrings(source: str) -> str:
    """Remove # comments and triple-quoted docstrings from a Python
    source string so structural assertions check executable code only.

    Naive — does not parse the AST — but enough for our case because
    the handler never embeds ``#`` in a string literal."""
    # Strip docstring (first triple-quoted block in the handler body).
    source = re.sub(r'"""[\s\S]*?"""', "", source, count=1)
    # Strip line comments. A '#' inside a string literal would be a
    # false hit; the handler does not use that pattern.
    lines = []
    for line in source.splitlines():
        stripped = re.sub(r"\s*#.*$", "", line)
        lines.append(stripped)
    return "\n".join(lines)


def test_handler_no_longer_uses_unindexable_contains():
    """``.contains()`` on phone/whatsapp compiles to ``LIKE '%xxx%'`` —
    not servable from a btree index. The handler must not use it on
    these columns; ``endswith`` (``LIKE 'xxx'``) is the acceptable
    fallback because it is gated behind an indexed exact match."""
    source = inspect.getsource(nap.whatsapp_message_notification)
    body = _strip_comments_and_docstrings(source)

    assert "Client.phone.contains" not in body, (
        "whatsapp_message_notification must NOT use Client.phone.contains "
        "— LIKE '%xxx%' triggers a full Client table scan per inbound "
        "message. Use exact match first + endswith fallback."
    )
    assert "Client.whatsapp.contains" not in body, (
        "Same rationale for Client.whatsapp.contains."
    )


def test_handler_does_exact_match_first():
    """Step 1 of the new lookup must be an indexed equality predicate."""
    source = inspect.getsource(nap.whatsapp_message_notification)
    # Exact-match step must include Client.phone == something AND
    # Client.whatsapp == something.
    assert "Client.phone ==" in source or "Client.phone==" in source, (
        "Step 1 (exact match) must include Client.phone == phone."
    )
    assert "Client.whatsapp ==" in source or "Client.whatsapp==" in source, (
        "Step 1 (exact match) must include Client.whatsapp == phone."
    )


def test_handler_has_endswith_fallback_gated_on_min_length():
    """Step 2 fallback is ``endswith`` but must be gated on
    ``len(phone_normalized) >= 10`` so a short number cannot match the
    wrong client (e.g. all phones ending in ``99``)."""
    source = inspect.getsource(nap.whatsapp_message_notification)
    assert "endswith" in source, "Step 2 fallback must use endswith."
    assert re.search(r"len\(\s*phone_normalized\s*\)\s*>=\s*10", source), (
        "endswith fallback must be guarded by len(phone_normalized) >= 10 "
        "to avoid matching the wrong client on a short input."
    )


def test_handler_still_normalises_phone_before_query():
    """phone_normalized line must remain — the digits-only form is what
    the exact-match step compares against."""
    source = inspect.getsource(nap.whatsapp_message_notification)
    # The original normalisation used .replace() of "+", "-", " ". Keep it.
    assert 'phone_normalized = phone.replace("+"' in source or \
        "phone_normalized = phone.replace('+'" in source, (
        "Handler must keep the phone_normalized = phone.replace(...) line."
    )
