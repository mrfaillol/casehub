"""Regression tests for the goal-listed healthcheck aliases.

The goal frente A lists three canonical healthcheck endpoints:

  - /casehub/health
  - /casehub/oauth/pdpj/status
  - /casehub/google/status

Before this change, only the third existed (and only auth-gated). The
other two returned 404, so the goal text was lying about coverage.
This change adds:

  - /casehub/health -> same payload as /casehub/healthz (alias)
  - /casehub/google/status -> deploy-level "is the integration
    configured at all" probe; per-user OAuth status stays at the
    existing /casehub/google-calendar/status

Tests pin the structural contract — no live network needed.

Run: pytest tests/test_healthcheck_aliases.py
"""
from __future__ import annotations

import inspect
import re

import core.app_factory as af


def _strip_comments_and_docstrings(source: str) -> str:
    """Drop docstring + line comments so structural assertions check
    executable code only."""
    source = re.sub(r'"""[\s\S]*?"""', "", source, count=1)
    lines = []
    for line in source.splitlines():
        lines.append(re.sub(r"\s*#.*$", "", line))
    return "\n".join(lines)


def test_create_app_defines_casehub_health_alias():
    """``/casehub/health`` must be a route handler in create_app —
    matches the goal's healthcheck probe list."""
    source = _strip_comments_and_docstrings(inspect.getsource(af.create_app))

    # The route registration line uses an f-string with PREFIX.
    assert 'f"{PREFIX}/health"' in source, (
        'create_app must register @app.get(f"{PREFIX}/health") as an '
        "alias for /casehub/healthz so the goal-listed probe URL doesn't 404."
    )


def test_create_app_defines_casehub_google_status():
    """``/casehub/google/status`` must be a route handler in create_app
    so the goal-listed probe URL doesn't 404."""
    source = _strip_comments_and_docstrings(inspect.getsource(af.create_app))
    assert 'f"{PREFIX}/google/status"' in source, (
        'create_app must register @app.get(f"{PREFIX}/google/status") so '
        "the goal-listed probe URL doesn't 404."
    )


def test_google_status_handler_is_deploy_level_not_per_user():
    """The handler must NOT expose per-user OAuth state at this
    UN-authenticated endpoint. It must report only ``configured`` (env
    presence) and point callers to the per-user endpoint for the
    auth-gated state."""
    source = _strip_comments_and_docstrings(inspect.getsource(af.create_app))

    # Look at the slice around the google/status registration
    m = re.search(
        r'f"\{PREFIX\}/google/status"[\s\S]{0,1500}',
        source,
    )
    assert m, "Could not locate google/status handler block in source."
    block = m.group(0)

    # The handler returns ``configured`` flag (deploy-level)
    assert '"configured"' in block, (
        "google/status response must include the deploy-level "
        '"configured" flag (not per-user state).'
    )
    # And points to the per-user endpoint
    assert "per_user_status_endpoint" in block, (
        "google/status response must point callers to "
        "/casehub/google-calendar/status for per-user OAuth state — "
        "keeps the auth boundary honest."
    )


def test_health_alias_returns_same_payload_shape_as_healthz():
    """The alias handler must build its payload from
    ``_health_payload(include_marker=True)`` — same source of truth as
    healthz. A regression that built a separate payload would drift.
    """
    source = _strip_comments_and_docstrings(inspect.getsource(af.create_app))
    # Slice the alias handler block.
    m = re.search(
        r'f"\{PREFIX\}/health"\)[\s\S]{0,800}',
        source,
    )
    assert m, "Could not locate /casehub/health alias block."
    block = m.group(0)
    assert "_health_payload(include_marker=True)" in block, (
        "The /casehub/health alias must call _health_payload(include_marker=True) "
        "— same call as /casehub/healthz, single source of truth."
    )
