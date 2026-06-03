"""Regression test for routes/emails.list_emails — sidecar query defensive.

Self-hosted P0 smoke (PR #588) revealed that list_emails 500s on a
fresh deploy even with PR #558's defensive wrapper on the main
email-list query. The reason: TWO MORE raw-SQL queries below the
fix — ``email_accounts`` SELECT (line 138) and ``email_messages``
DISTINCT folders (line 143) — were unprotected and crashed when the
tables were missing.

This change wraps both sidecar queries in try/except + db.rollback().
The page degrades to "no accounts" + "no synced folders" instead of
500. Same defect class as portal_access (PR #572), unified_messages
(PR #589).

Run: pytest tests/test_emails_list_sidecar_defensive.py
"""
from __future__ import annotations

import inspect
import re

import routes.emails as emails_route


def _strip_comments_and_docstrings(source: str) -> str:
    """Drop docstring + line comments so structural assertions check
    executable code only."""
    source = re.sub(r'"""[\s\S]*?"""', "", source, count=1)
    lines = []
    for line in source.splitlines():
        lines.append(re.sub(r"\s*#.*$", "", line))
    return "\n".join(lines)


def test_list_emails_wraps_email_accounts_select():
    """The ``SELECT ... FROM email_accounts`` sidecar query must be
    wrapped in try/except (OperationalError, ProgrammingError) so a
    missing email_accounts table degrades to ``accounts = []``
    instead of 500."""
    source = inspect.getsource(emails_route.list_emails)
    body = _strip_comments_and_docstrings(source)

    # The fix shape: ``try:`` block guarding the email_accounts SELECT,
    # ``except (OperationalError, ProgrammingError) as exc:`` handler.
    # Find the email_accounts SELECT line and assert that try/except
    # surrounds it (heuristic: 'try:' appears within 5 lines above).
    lines = body.splitlines()
    accounts_line = None
    for i, line in enumerate(lines):
        if "FROM email_accounts" in line:
            accounts_line = i
            break
    assert accounts_line is not None, (
        "list_emails must still query email_accounts — sidecar removed?"
    )
    window = "\n".join(lines[max(0, accounts_line - 10):accounts_line])
    assert "try:" in window, (
        f"email_accounts SELECT at line {accounts_line} must be inside a "
        "try block. Otherwise a missing table re-introduces the 500."
    )


def test_list_emails_wraps_email_messages_distinct_folders():
    """The ``SELECT DISTINCT folder FROM email_messages`` sidecar must
    also be defensive — degrades to ``synced_folders = []``."""
    source = inspect.getsource(emails_route.list_emails)
    body = _strip_comments_and_docstrings(source)

    lines = body.splitlines()
    folders_line = None
    for i, line in enumerate(lines):
        # The sidecar is specifically the DISTINCT folder query —
        # not the main email-list SELECT (which also references
        # email_messages but is the original PR #558 try-block).
        if "DISTINCT folder FROM email_messages" in line:
            folders_line = i
            break
    assert folders_line is not None, (
        "list_emails must still query 'SELECT DISTINCT folder FROM "
        "email_messages' — sidecar removed?"
    )
    window = "\n".join(lines[max(0, folders_line - 10):folders_line])
    assert "try:" in window, (
        f"DISTINCT folder SELECT at line {folders_line} must be inside a "
        "try block. Otherwise a missing table re-introduces the 500."
    )


def test_list_emails_imports_sqlalchemy_exc_classes():
    """Imports must include OperationalError + ProgrammingError so the
    except clauses compile and catch the right exceptions."""
    module_source = inspect.getsource(emails_route)
    assert "from sqlalchemy.exc import" in module_source
    assert "OperationalError" in module_source
    assert "ProgrammingError" in module_source
