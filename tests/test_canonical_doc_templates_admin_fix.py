"""Regression: 3 canonical routes in core/v2_canonical_routes.py silently
degraded because they imported/getattr'd a function name that doesn't exist
in the target module — the broad `except Exception` (or bare
`getattr(..., None)`) swallowed the failure and rendered a degraded/empty
context instead of erroring, so the page rendered 200 OK with no real data.

  1. ``doc_templates_detail_canon`` (``/casehub/doc-templates/{id}``)
     imported ``routes.doc_templates.view_template`` — that name never
     existed in ``routes/doc_templates.py`` (only ``template_list``,
     ``new_template_form``, ``create_template``, ``edit_template_form``,
     ``update_template``, ``delete_template``, ``generate_document_form``,
     ``generate_document``, ``preview_template``,
     ``install_default_templates`` were defined there — no single-template
     detail handler existed at all). Fixed by adding a real ``view_template``
     handler to ``routes/doc_templates.py`` (tenant-scoped SELECT, same
     IDOR-safe predicate as ``edit_template_form``). Bonus: this also fixes
     an independent dead link — ``templates/app/doc_templates/list.html``
     links every row to ``{PREFIX}/templates/{id}`` (the legacy path), and no
     route ever answered that path either; the same new handler covers it.
  2. ``doc_templates_edit_canon`` (``/casehub/doc-templates/{id}/edit``)
     imported ``routes.doc_templates.edit_template`` — the real name is
     ``edit_template_form``. Fixed by correcting the import.
  3. ``_admin_canon("app/admin/settings.html", "admin_settings", ...)``
     (``/casehub/admin/settings``) did
     ``getattr(routes.admin, "admin_settings", None)`` — the real function is
     named ``settings``. Fixed by passing the correct handler name.

These tests build the REAL app via ``core.app_factory.create_app()`` (same
call production uses) and confirm each canonical route now renders the
delegated handler's real output, not the degraded/empty fallback.
"""
from __future__ import annotations

import os
import uuid as _uuid

os.environ.setdefault("CASEHUB_PRODUCT", "lite")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-doctpl-canon-32chars!")
os.environ.setdefault(
    "ENCRYPTION_KEY",
    "dGVzdC1lbmNyeXB0aW9uLWtleS1mb3ItdGVzdHMxMjM=",
)

import bcrypt
import pytest


@pytest.fixture(scope="module")
def app_and_client():
    from fastapi.testclient import TestClient
    from core.app_factory import create_app

    app = create_app("lite")
    with TestClient(
        app,
        follow_redirects=False,
        headers={"host": "doctplcanon.casehub.legal"},
    ) as client:
        yield app, client


@pytest.fixture(scope="module")
def seeded_user(app_and_client) -> dict:
    from models.base import SessionLocal
    from models.tenant import Organization
    from models.user import User

    email = "smoke@doctplcanon.test"
    password = "DocTplCanonSmoke!2026"

    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == "doctplcanon").first()
        if org is None:
            org = Organization(
                uuid=str(_uuid.uuid4()),
                name="Doc Tpl Canon Smoke Org",
                slug="doctplcanon",
                domain="doctplcanon.casehub.legal",
                is_active=True,
            )
            db.add(org)
            db.flush()

        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(
                email=email,
                name="Doc Tpl Canon Smoke",
                password_hash=bcrypt.hashpw(
                    password.encode("utf-8"), bcrypt.gensalt()
                ).decode("utf-8"),
                user_type="admin",
                enabled=True,
                must_change_password=False,
                org_id=org.id,
            )
            db.add(user)
        db.commit()
        org_id = org.id
    finally:
        db.close()

    return {"email": email, "password": password, "org_id": org_id}


def _login(client, creds: dict):
    resp = client.post(
        "/casehub/login",
        data={"email": creds["email"], "password": creds["password"]},
    )
    return resp.cookies.get("casehub_token")


@pytest.fixture
def seeded_doc_template(app_and_client, seeded_user) -> dict:
    """Create `document_templates` (raw-SQL-only table, never bootstrapped by
    any migration or ORM model) and seed one row scoped to the smoke org, so
    the detail/edit canonical routes have a real row to fetch instead of
    always hitting the not-found/degraded path.
    """
    from sqlalchemy import text as _sql_text
    from models.base import SessionLocal

    db = SessionLocal()
    try:
        db.execute(_sql_text("""
            CREATE TABLE IF NOT EXISTS document_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_id INTEGER,
                name TEXT,
                category TEXT,
                description TEXT,
                content TEXT,
                created_by INTEGER,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        """))
        db.commit()

        name = "Canon Fix Template"
        existing = db.execute(
            _sql_text("SELECT id FROM document_templates WHERE org_id = :org_id AND name = :name"),
            {"org_id": seeded_user["org_id"], "name": name},
        ).fetchone()
        if existing:
            template_id = existing[0]
        else:
            result = db.execute(
                _sql_text("""
                    INSERT INTO document_templates
                        (org_id, name, category, description, content, created_by, created_at)
                    VALUES
                        (:org_id, :name, :category, :description, :content, :created_by, :created_at)
                """),
                {
                    "org_id": seeded_user["org_id"],
                    "name": name,
                    "category": "contracts",
                    "description": "Seeded by test_canonical_doc_templates_admin_fix",
                    "content": "Prezado {{ client.full_name }}, segue o contrato.",
                    "created_by": None,
                    "created_at": None,
                },
            )
            db.commit()
            template_id = result.lastrowid
    finally:
        db.close()

    return {"template_id": template_id, "name": name}


def test_doc_templates_detail_canon_renders_real_data(
    app_and_client, seeded_user, seeded_doc_template,
):
    """Finding #1: before the fix, `view_template` never existed, so
    `doc_templates_detail_canon` always fell back to
    ``ctx={"template_data": None}`` and rendered the empty state regardless
    of the id in the URL. Confirm it now renders the seeded template's real
    name/content, not the empty-state copy."""
    _, client = app_and_client
    _login(client, seeded_user)

    resp = client.get(f"/casehub/doc-templates/{seeded_doc_template['template_id']}")

    assert resp.status_code == 200, resp.text
    assert seeded_doc_template["name"] in resp.text, (
        "doc_templates_detail_canon did not render the real template name — "
        "still falling back to the degraded/empty template_data=None state."
    )
    assert "Prezado" in resp.text, (
        "doc_templates_detail_canon did not render the real template "
        "content — still falling back to the degraded state."
    )


def test_doc_templates_edit_canon_renders_real_data(
    app_and_client, seeded_user, seeded_doc_template,
):
    """Finding #2: before the fix, the import of `edit_template` always
    ImportErrored, so `doc_templates_edit_canon` always rendered a BLANK
    "create new" form (`template_data` undefined) instead of the template
    actually being edited. Confirm it now renders the seeded template's real
    name pre-filled into the edit form."""
    _, client = app_and_client
    _login(client, seeded_user)

    resp = client.get(f"/casehub/doc-templates/{seeded_doc_template['template_id']}/edit")

    assert resp.status_code == 200, resp.text
    assert seeded_doc_template["name"] in resp.text, (
        "doc_templates_edit_canon did not render the real template being "
        "edited — still falling back to a blank 'create new' form."
    )


def test_admin_settings_canon_actually_invokes_real_delegate(
    app_and_client, seeded_user, monkeypatch,
):
    """Finding #3: before the fix, ``getattr(routes.admin, "admin_settings",
    None)`` always returned ``None`` (no exception at all — a silent no-op),
    so ``routes.admin.settings()`` was NEVER called for
    ``/casehub/admin/settings``. A response-body assertion alone can't
    distinguish "the real handler ran and added nothing" from "the real
    handler never ran", so this test proves causation directly: monkeypatch
    ``routes.admin.settings`` with a spy, hit the canonical route, and assert
    the spy actually executed."""
    import routes.admin as _admin_mod

    calls = []
    _real_settings = _admin_mod.settings

    async def _spy_settings(request, db=None):
        calls.append(1)
        return await _real_settings(request, db)

    monkeypatch.setattr(_admin_mod, "settings", _spy_settings)

    _, client = app_and_client
    _login(client, seeded_user)

    resp = client.get("/casehub/admin/settings")

    assert resp.status_code == 200, resp.text
    assert calls, (
        "routes.admin.settings was never invoked — the canonical "
        "/casehub/admin/settings route is still resolving the getattr "
        "target to None (pre-fix behavior: getattr(routes.admin, "
        "'admin_settings', None))."
    )
