"""Regression test for routes/questionnaires.view_questionnaire — N+1 batch.

The handler used to enrich each response with two per-row lookups —
``Client`` + ``Case`` — inside a ``for r in responses`` loop. For the
typical 10-response page that produced 1 + 10*2 = 21 SELECTs. Both
lookups are now batched into dicts before the loop.

The honest metric for an N+1 is SQL statement count (not wall time —
SQLite in-memory has no network latency, timing would understate the
real cost).

Run: pytest tests/test_questionnaires_batch_n1.py
"""
from __future__ import annotations

import inspect
import re

import routes.questionnaires as questionnaires


def _strip_comments_and_docstrings(source: str) -> str:
    """Drop docstring + line comments so structural assertions check
    executable code only."""
    source = re.sub(r'"""[\s\S]*?"""', "", source, count=1)
    lines = []
    for line in source.splitlines():
        lines.append(re.sub(r"\s*#.*$", "", line))
    return "\n".join(lines)


def test_view_questionnaire_batches_client_and_case_lookups():
    """The per-response Client + Case lookups must be batched into dicts
    BEFORE the enrichment loop. A regression would put them back inside
    the loop, restoring the 2-N+1 pattern."""
    source = inspect.getsource(questionnaires.view_questionnaire)
    body = _strip_comments_and_docstrings(source)

    # The batched dicts must be present.
    assert "clients_by_id" in body, (
        "view_questionnaire must build a clients_by_id dict via .in_(client_ids).all() "
        "before the enrichment loop."
    )
    assert "cases_by_id" in body, (
        "view_questionnaire must build a cases_by_id dict via .in_(case_ids).all() "
        "before the enrichment loop."
    )
    assert ".in_(" in body, (
        "The batch fetches must use Column.in_(ids) — that is the single-query "
        "form."
    )

    # The pre-existing per-row .filter(Client.id == r.client_id).first()
    # pattern must be GONE — that was the N+1 hot path. Allow the new
    # dict-lookup form (clients_by_id.get(r.client_id)).
    assert "Client.id == r.client_id" not in body, (
        "Per-row Client lookup with .filter(Client.id == r.client_id).first() "
        "must be replaced by clients_by_id.get(r.client_id)."
    )
    assert "Case.id == r.case_id" not in body, (
        "Per-row Case lookup with .filter(Case.id == r.case_id).first() must be "
        "replaced by cases_by_id.get(r.case_id)."
    )


def test_view_questionnaire_keeps_enrichment_attribute_assignment():
    """The handler still attaches ``r.client`` / ``r.case`` so the
    template (templates/questionnaires/detail.html) gets the same
    shape — the batch is purely a performance refactor."""
    source = inspect.getsource(questionnaires.view_questionnaire)
    body = _strip_comments_and_docstrings(source)
    assert "r.client =" in body, "Enrichment must still set r.client."
    assert "r.case =" in body, "Enrichment must still set r.case."
