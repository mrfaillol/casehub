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

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

import services.drive_explorer as explorer
import routes.documents as document_routes
import routes.drive_explorer as drive_routes
import routes.integrations as integration_routes
from models import Client, Organization


ROOT_DIR = Path(__file__).resolve().parents[1]


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
    fake.requested_org_ids = []

    def _stub(org_id=None):
        fake.requested_org_ids.append(org_id)
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
    """``page_size`` is clamped to 1..100, matching Drive files.list."""
    fake_drive._files.list_payload = {"files": [], "nextPageToken": None}

    explorer.list_folder("root", page_size=9999)

    assert fake_drive._files.last_list_kwargs["pageSize"] == 100


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


def test_drive_explorer_uses_requested_org_id(fake_drive):
    """The Drive explorer must load the token for the current tenant, not the
    default org. This is what makes subdomains like tenanta.casehub.legal
    use credentials/org_4/drive_token.json after OAuth."""
    fake_drive._files.list_payload = {"files": [], "nextPageToken": None}
    fake_drive._files.get_payloads = {
        "file42": {"id": "file42", "name": "doc.pdf", "mimeType": "application/pdf"},
        "leaf": {"id": "leaf", "name": "doc.pdf", "mimeType": "application/pdf", "parents": []},
    }

    explorer.list_folder("root", org_id=4)
    explorer.get_file("file42", org_id=4)
    explorer.breadcrumb("leaf", org_id=4)

    assert fake_drive.requested_org_ids == [4, 4, 4]


def test_documents_drive_root_prefers_current_org(db, monkeypatch):
    org = Organization(
        id=4,
        uuid="org-tenanta-test",
        name="Escritorio Demo",
        slug="tenanta",
        domain="tenanta.casehub.legal",
        google_drive_root_id="org-drive-root",
    )
    db.add(org)
    db.commit()
    monkeypatch.setattr(document_routes.settings, "GOOGLE_DRIVE_ROOT_ID", "global-root")

    assert document_routes._drive_root_id_for_org(db, 4) == "org-drive-root"
    assert integration_routes._google_drive_root_id(db, 4) == "org-drive-root"
    assert integration_routes._google_drive_root_source(db, 4) == "org"


def test_documents_drive_root_prefers_client_override(db, monkeypatch):
    org = Organization(
        id=4,
        uuid="org-tenanta-test",
        name="Escritorio Demo",
        slug="tenanta",
        domain="tenanta.casehub.legal",
        google_drive_root_id="org-drive-root",
    )
    client = Client(
        org_id=4,
        first_name="Cliente",
        last_name="Com Pasta",
        drive_folder_id="client-drive-root",
    )
    db.add(org)
    db.add(client)
    db.commit()
    db.refresh(client)
    monkeypatch.setattr(document_routes.settings, "GOOGLE_DRIVE_ROOT_ID", "global-root")

    assert (
        document_routes._drive_root_id_for_org(db, 4, client_id=client.id)
        == "client-drive-root"
    )


def test_documents_drive_root_rejects_other_org_client(db):
    client = Client(
        org_id=999,
        first_name="Outra",
        last_name="Org",
        drive_folder_id="other-org-root",
    )
    db.add(client)
    db.commit()
    db.refresh(client)

    with pytest.raises(Exception) as exc_info:
        document_routes._drive_root_id_for_org(db, 4, client_id=client.id)

    assert getattr(exc_info.value, "status_code", None) == 404


def test_documents_drive_root_falls_back_to_global(db, monkeypatch):
    monkeypatch.setattr(document_routes.settings, "GOOGLE_DRIVE_ROOT_ID", "global-root")
    monkeypatch.setattr(integration_routes.settings, "GOOGLE_DRIVE_ROOT_ID", "global-root")

    assert document_routes._drive_root_id_for_org(db, 4) == "global-root"
    assert integration_routes._google_drive_root_id(db, 4) == "global-root"
    assert integration_routes._google_drive_root_source(db, 4) == "global"


def test_documents_drive_root_falls_back_to_my_drive(db, monkeypatch):
    monkeypatch.setattr(document_routes.settings, "GOOGLE_DRIVE_ROOT_ID", "")
    monkeypatch.setattr(integration_routes.settings, "GOOGLE_DRIVE_ROOT_ID", "")

    assert document_routes._drive_root_id_for_org(db, 4) == "root"
    assert integration_routes._google_drive_root_id(db, 4) == ""
    assert integration_routes._google_drive_root_source(db, 4) == "root-fallback"


def test_folder_shortcut_is_serialized_as_navigable_folder(fake_drive):
    """A shortcut to a folder must be clickable as a folder in the Drive UI.

    This is the practical workaround for Drive for desktop's "Computers"
    surface: create a shortcut in My Drive, then browse the target folder ID.
    """
    fake_drive._files.list_payload = {
        "files": [
            {
                "id": "shortcut-1",
                "name": "Pasta sincronizada",
                "mimeType": explorer.DRIVE_SHORTCUT_MIME,
                "shortcutDetails": {
                    "targetId": "folder-target-1",
                    "targetMimeType": explorer.DRIVE_FOLDER_MIME,
                },
            },
        ],
        "nextPageToken": None,
    }

    result = explorer.list_folder("root")
    item = result["items"][0]

    assert item["id"] == "shortcut-1"
    assert item["navigation_id"] == "folder-target-1"
    assert item["is_shortcut"] is True
    assert item["is_folder"] is True
    assert item["shortcut_target_mime_type"] == explorer.DRIVE_FOLDER_MIME


def test_documents_template_uses_shortcut_navigation_id():
    template = (ROOT_DIR / "templates/app/documents/list.html").read_text(encoding="utf-8")

    assert "navigationId" in template
    assert "shortcutTargetMimeType" in template
    assert "candidate.id === id || candidate.navigationId === id" in template


def test_documents_template_preserves_preview_when_file_selected():
    """File selection must not clear the metadata panel immediately after render."""
    template = (ROOT_DIR / "templates/app/documents/list.html").read_text(encoding="utf-8")

    assert "clearAfter(depth, { resetPreview: false });" in template
    assert "renderPreview(item || { id: id, name: button.textContent.trim() });" in template


def test_drive_alias_registered_without_duplicate_ui():
    app_factory = (ROOT_DIR / "core/app_factory.py").read_text(encoding="utf-8")

    assert '@app.get(f"{PREFIX}/drive"' in app_factory
    assert '@app.get(f"{PREFIX}/drive/"' in app_factory
    assert 'target = f"{PREFIX}/documents"' in app_factory
    assert 'RedirectResponse(url=target' in app_factory


def test_google_drive_root_folder_endpoint_persists_org_root(db, monkeypatch):
    org = Organization(
        id=4,
        uuid="org-tenanta-test",
        name="Escritorio Demo",
        slug="tenanta",
        domain="tenanta.casehub.legal",
    )
    db.add(org)
    db.commit()

    request = SimpleNamespace(state=SimpleNamespace(org_id=4))

    async def _form():
        return {
            "drive_root_id": (
                "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQ"
            )
        }

    request.form = _form
    monkeypatch.setattr(
        integration_routes,
        "get_current_user",
        lambda req, session: SimpleNamespace(id=7, user_type="admin"),
    )

    response = asyncio.run(
        integration_routes.google_drive_root_folder(request, db)
    )

    db.refresh(org)
    assert org.google_drive_root_id == "1AbCdEfGhIjKlMnOpQ"
    assert response.status_code == 302
    assert "drive_root_saved=1" in response.headers["location"]


def test_google_drive_root_folder_endpoint_requires_admin(db, monkeypatch):
    request = SimpleNamespace(state=SimpleNamespace(org_id=4))

    async def _form():
        return {"drive_root_id": "1AbCdEfGhIjKlMnOpQ"}

    request.form = _form
    monkeypatch.setattr(
        integration_routes,
        "get_current_user",
        lambda req, session: SimpleNamespace(id=8, user_type="case_worker"),
    )

    response = asyncio.run(
        integration_routes.google_drive_root_folder(request, db)
    )

    assert response.status_code == 302
    assert "drive_error=drive_root_admin_required" in response.headers["location"]


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
            {"emailAddress": "admin@example.com", "displayName": "CaseHub Admin"},
        ],
        "trashed": False,
        "webViewLink": "https://docs.google.com/document/d/file42/edit",
    }

    payload = explorer.get_file("file42")

    assert payload["id"] == "file42"
    assert payload["trashed"] is False
    assert payload["size"] is None
    assert payload["owners"] == [
        {"email": "admin@example.com", "display_name": "CaseHub Admin"},
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
    monkeypatch.setattr(explorer, "get_drive_service", lambda org_id=None: None)

    with pytest.raises(explorer.DriveNotAvailable):
        explorer.list_folder("root")
    with pytest.raises(explorer.DriveNotAvailable):
        explorer.get_file("anything")
    with pytest.raises(explorer.DriveNotAvailable):
        explorer.breadcrumb("anything")


def test_list_route_passes_request_org_id_to_service(monkeypatch):
    """Route layer must propagate TenantMiddleware's org_id into the Drive
    service call; otherwise OAuth succeeds for one tenant but list still checks
    the default tenant token."""
    captured = {}

    monkeypatch.setattr(drive_routes, "_ensure_auth", lambda request, db: (object(), None))

    def _list_folder_stub(folder_id, **kwargs):
        captured["folder_id"] = folder_id
        captured["org_id"] = kwargs.get("org_id")
        return {"items": [], "next_page_token": None}

    monkeypatch.setattr(drive_routes, "list_folder", _list_folder_stub)

    request = SimpleNamespace(state=SimpleNamespace(org_id=4))
    response = asyncio.run(drive_routes.list_drive_folder(request, folder_id="root", db=object()))

    assert response.status_code == 200
    assert captured == {"folder_id": "root", "org_id": 4}


def test_file_route_passes_request_org_id_to_service(monkeypatch):
    captured = {}

    monkeypatch.setattr(drive_routes, "_ensure_auth", lambda request, db: (object(), None))

    def _get_file_stub(file_id, **kwargs):
        captured["file_id"] = file_id
        captured["org_id"] = kwargs.get("org_id")
        return {"id": file_id, "name": "doc.pdf"}

    monkeypatch.setattr(drive_routes, "get_file", _get_file_stub)

    request = SimpleNamespace(state=SimpleNamespace(org_id=4))
    response = asyncio.run(drive_routes.get_drive_file(request, file_id="file42", db=object()))

    assert response.status_code == 200
    assert json.loads(response.body)["id"] == "file42"
    assert captured == {"file_id": "file42", "org_id": 4}


def test_breadcrumb_route_passes_request_org_id_to_service(monkeypatch):
    captured = {}

    monkeypatch.setattr(drive_routes, "_ensure_auth", lambda request, db: (object(), None))

    def _breadcrumb_stub(file_id, **kwargs):
        captured["file_id"] = file_id
        captured["org_id"] = kwargs.get("org_id")
        captured["max_depth"] = kwargs.get("max_depth")
        return [{"id": file_id, "name": "doc.pdf"}]

    monkeypatch.setattr(drive_routes, "breadcrumb", _breadcrumb_stub)

    request = SimpleNamespace(state=SimpleNamespace(org_id=4))
    response = asyncio.run(drive_routes.drive_breadcrumb(
        request,
        file_id="file42",
        max_depth=9,
        db=object(),
    ))

    assert response.status_code == 200
    assert json.loads(response.body)["trail"][0]["id"] == "file42"
    assert captured == {"file_id": "file42", "org_id": 4, "max_depth": 9}


def test_drive_oauth_credentials_fall_back_to_shared_google_client(tmp_path, monkeypatch):
    monkeypatch.setattr(integration_routes.settings, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(integration_routes.settings, "GOOGLE_DRIVE_CREDENTIALS_PATH", "")
    monkeypatch.setattr(integration_routes.settings, "GOOGLE_CALENDAR_CREDENTIALS_PATH", "")
    shared_client = tmp_path / "credentials" / "google_client_secret.json"
    shared_client.parent.mkdir(parents=True)
    shared_client.write_text("{}", encoding="utf-8")

    assert integration_routes._google_drive_credentials_path() == shared_client


def test_drive_oauth_credentials_prefer_explicit_drive_path(tmp_path, monkeypatch):
    drive_client = tmp_path / "drive-client.json"
    shared_client = tmp_path / "credentials" / "google_client_secret.json"
    shared_client.parent.mkdir(parents=True)
    drive_client.write_text("{}", encoding="utf-8")
    shared_client.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(integration_routes.settings, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(
        integration_routes.settings,
        "GOOGLE_DRIVE_CREDENTIALS_PATH",
        str(drive_client),
    )
    monkeypatch.setattr(integration_routes.settings, "GOOGLE_CALENDAR_CREDENTIALS_PATH", "")

    assert integration_routes._google_drive_credentials_path() == drive_client


def test_drive_integration_card_token_without_root_opens_documents(tmp_path, monkeypatch):
    credentials = tmp_path / "google_client_secret.json"
    token = tmp_path / "drive_token.json"
    credentials.write_text("{}", encoding="utf-8")
    token.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(integration_routes.settings, "GOOGLE_DRIVE_ROOT_ID", "")
    monkeypatch.setattr(integration_routes.settings, "GMAIL_OAUTH_ENABLED", False)
    monkeypatch.setattr(
        integration_routes,
        "_google_drive_paths",
        lambda org_id=None: (credentials, token),
    )
    monkeypatch.setattr(
        integration_routes,
        "GoogleCalendarService",
        lambda: SimpleNamespace(
            get_connected_accounts=lambda verify_live=False: [],
            get_client_redirect_uris=lambda: [],
        ),
    )

    cards = integration_routes._integration_cards(org_id=4, db=None)
    drive = next(card for card in cards if card["name"] == "Google Drive")

    assert drive["state"] == "warn"
    assert drive["action_url"].endswith("/documents")
    assert "root_source=root-fallback" in drive["diagnostic"]
