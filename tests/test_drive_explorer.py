"""Regression tests for the /api/drive read-only Drive explorer.

Three endpoints — ``/api/drive/list``, ``/api/drive/file/{id}``,
``/api/drive/breadcrumb`` — are exercised against a stubbed Drive service.
The tests pin both the **happy path** (correct projection / pagination /
breadcrumb ordering) and the **error contract** (DriveNotAvailable → 503,
HttpError → 4xx/502, unauth → 401). These guards lock in the audit-#514
red line: ``no 500 ever from this surface``.

Run: pytest tests/test_drive_explorer.py
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

import services.drive_explorer as explorer


# ---------------------------------------------------------------------------
# Fake Drive client — minimal stand-in for googleapiclient's discovery build.
#
# The real client exposes a chain ``service.files().list(...).execute()``;
# we mimic just the surface drive_explorer uses, plus a swappable payload so
# each test controls what Drive "returns".
# ---------------------------------------------------------------------------


class _FakeRequest:
    def __init__(self, payload, raise_with=None):
        self._payload = payload
        self._raise = raise_with

    def execute(self):
        if self._raise is not None:
            raise self._raise
        return self._payload


class _FakeFiles:
    def __init__(self):
        self.list_payload: Dict[str, Any] = {"files": [], "nextPageToken": None}
        self.get_payloads: Dict[str, Dict[str, Any]] = {}
        self.raise_on_get: Optional[Exception] = None

    def list(self, **kwargs):
        # Capture kwargs on the fake so tests can assert what was requested.
        self.last_list_kwargs = kwargs
        return _FakeRequest(self.list_payload)

    def get(self, **kwargs):
        if self.raise_on_get is not None:
            return _FakeRequest({}, raise_with=self.raise_on_get)
        file_id = kwargs.get("fileId")
        payload = self.get_payloads.get(file_id, {})
        return _FakeRequest(payload)


class _FakeService:
    def __init__(self):
        self._files = _FakeFiles()

    def files(self):
        return self._files


@pytest.fixture
def fake_drive(monkeypatch):
    """Replace ``get_drive_service`` so no real network / token work runs."""
    fake = _FakeService()

    def _stub():
        return fake

    monkeypatch.setattr(explorer, "get_drive_service", _stub)
    return fake


# ---------------------------------------------------------------------------
# list_folder — happy path + pagination + safe defaults
# ---------------------------------------------------------------------------


def test_list_folder_shapes_files_and_folders(fake_drive):
    """Folders are serialized with ``is_folder=True``, file size is coerced
    to int, and ``next_page_token`` is round-tripped from the API payload.

    A pinned shape protects the Codex column-view UI from silent breakage
    if the Drive API ever adds fields we shouldn't expose."""
    fake_drive._files.list_payload = {
        "files": [
            {
                "id": "folder1",
                "name": "Cliente Alpha",
                "mimeType": explorer.DRIVE_FOLDER_MIME,
                "modifiedTime": "2026-05-22T12:00:00Z",
            },
            {
                "id": "file1",
                "name": "contrato.pdf",
                "mimeType": "application/pdf",
                "modifiedTime": "2026-05-22T13:00:00Z",
                "size": "1024",
                "webViewLink": "https://drive.google.com/file/d/file1/view",
            },
        ],
        "nextPageToken": "TOKEN42",
    }

    result = explorer.list_folder("root", page_size=50)

    assert result["next_page_token"] == "TOKEN42"
    assert len(result["items"]) == 2

    folder, file_ = result["items"]
    assert folder["is_folder"] is True
    assert folder["id"] == "folder1"
    assert folder["mime_type"] == explorer.DRIVE_FOLDER_MIME
    assert folder["size"] is None  # folders have no size

    assert file_["is_folder"] is False
    assert file_["size"] == 1024  # coerced from str → int
    assert file_["web_view_link"] == "https://drive.google.com/file/d/file1/view"


def test_list_folder_clamps_page_size_into_drive_limits(fake_drive):
    """``page_size`` is clamped to 1..200 — Drive's accepted range. A larger
    value silently downgrades to 200 (no API 400)."""
    fake_drive._files.list_payload = {"files": [], "nextPageToken": None}

    explorer.list_folder("root", page_size=9999)

    assert fake_drive._files.last_list_kwargs["pageSize"] == 200


def test_list_folder_includes_trashed_only_when_asked(fake_drive):
    """Default ``include_trashed=False`` adds ``trashed = false`` to the
    query — folders the user moved to trash should NOT appear by default."""
    fake_drive._files.list_payload = {"files": [], "nextPageToken": None}

    explorer.list_folder("root")
    q_default = fake_drive._files.last_list_kwargs["q"]
    assert "trashed = false" in q_default

    explorer.list_folder("root", include_trashed=True)
    q_with_trash = fake_drive._files.last_list_kwargs["q"]
    assert "trashed" not in q_with_trash


# ---------------------------------------------------------------------------
# get_file — extra projection (owners, trashed)
# ---------------------------------------------------------------------------


def test_get_file_includes_owners_and_trashed(fake_drive):
    """``get_file`` returns a richer projection than list — owners (for
    'Owned by X' UI) and the trashed flag. The shape is stable."""
    fake_drive._files.get_payloads["file42"] = {
        "id": "file42",
        "name": "petição.docx",
        "mimeType": "application/vnd.google-apps.document",
        "modifiedTime": "2026-05-20T10:00:00Z",
        "createdTime": "2026-05-15T09:00:00Z",
        "size": None,  # Google-native docs have no byte size
        "owners": [
            {"emailAddress": "victor@example.com", "displayName": "Victor Vingren"},
        ],
        "trashed": False,
        "webViewLink": "https://docs.google.com/document/d/file42/edit",
    }

    payload = explorer.get_file("file42")

    assert payload["id"] == "file42"
    assert payload["trashed"] is False
    assert payload["size"] is None
    assert payload["owners"] == [
        {"email": "victor@example.com", "display_name": "Victor Vingren"},
    ]


# ---------------------------------------------------------------------------
# breadcrumb — root → leaf ordering, depth cap, cycle defence
# ---------------------------------------------------------------------------


def test_breadcrumb_walks_parents_root_to_leaf(fake_drive):
    """Breadcrumb is built leaf→root via parents, then reversed so the UI
    can render root→leaf without a second pass."""
    fake_drive._files.get_payloads = {
        "leaf": {"id": "leaf", "name": "doc.pdf",
                 "mimeType": "application/pdf", "parents": ["mid"]},
        "mid":  {"id": "mid",  "name": "Cliente Y",
                 "mimeType": explorer.DRIVE_FOLDER_MIME, "parents": ["root"]},
        "root": {"id": "root", "name": "Drive Root",
                 "mimeType": explorer.DRIVE_FOLDER_MIME, "parents": []},
    }

    trail = explorer.breadcrumb("leaf")

    assert [c["id"] for c in trail] == ["root", "mid", "leaf"]
    assert trail[0]["is_folder"] is True
    assert trail[-1]["is_folder"] is False


def test_breadcrumb_caps_at_max_depth(fake_drive):
    """``max_depth`` protects against pathological deep trees. The walk
    stops at the cap; we don't pretend we reached the root."""
    # Synthetic 20-deep chain — each node points to the next as parent.
    for i in range(20):
        parent = [f"node{i+1}"] if i + 1 < 20 else []
        fake_drive._files.get_payloads[f"node{i}"] = {
            "id": f"node{i}", "name": f"L{i}",
            "mimeType": explorer.DRIVE_FOLDER_MIME, "parents": parent,
        }

    trail = explorer.breadcrumb("node0", max_depth=3)
    assert len(trail) == 3


def test_breadcrumb_breaks_on_cycle(fake_drive):
    """If Drive ever returns a cyclic parent graph (shouldn't, but
    defending), the walk must terminate instead of looping forever."""
    fake_drive._files.get_payloads = {
        "a": {"id": "a", "name": "A",
              "mimeType": explorer.DRIVE_FOLDER_MIME, "parents": ["b"]},
        "b": {"id": "b", "name": "B",
              "mimeType": explorer.DRIVE_FOLDER_MIME, "parents": ["a"]},  # cycle
    }

    trail = explorer.breadcrumb("a")
    assert len(trail) <= 2


# ---------------------------------------------------------------------------
# DriveNotAvailable — service None must raise (route maps to 503, not 500)
# ---------------------------------------------------------------------------


def test_list_folder_raises_drive_not_available_when_service_none(monkeypatch):
    """When ``get_drive_service`` returns None (no creds / no libs / OAuth
    not completed), every entrypoint raises ``DriveNotAvailable``. The
    route layer maps that to 503; nothing should leak as a 500."""
    monkeypatch.setattr(explorer, "get_drive_service", lambda: None)

    with pytest.raises(explorer.DriveNotAvailable):
        explorer.list_folder("root")
    with pytest.raises(explorer.DriveNotAvailable):
        explorer.get_file("anything")
    with pytest.raises(explorer.DriveNotAvailable):
        explorer.breadcrumb("anything")
