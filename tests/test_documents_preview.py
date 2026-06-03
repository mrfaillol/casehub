"""
CaseHub - Documents inline preview tests (issue #287)

Covers `routes.documents.preview_document` — the existing route consumed by the
inline preview modal in `templates/documents/list.html`. The frontend
work in #287 switched onclick handlers from `/download` to `/preview`, which
makes verifying the route's `Content-Disposition: inline` behavior load-bearing.
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# The route module pulls in `config` which hits `SystemExit` when DATABASE_URL
# is unset, and `ImportError` when one of the known optional deps below is
# missing. Anything else MUST surface as a test failure so real regressions
# (RuntimeError from broken init, AttributeError from refactor, ImportError
# from a renamed symbol in `routes.documents` itself, etc.) don't get masked.
#
# Codex 2026-05-08 P2 round 3: catch-all ImportError still too broad — match
# the specific missing-dep module names instead.
_KNOWN_OPTIONAL_DEPS = {
    "pydantic_settings",   # casehub config.py
    "bcrypt",              # auth.py
    "cryptography",        # encryption stack
    "_cffi_backend",       # cryptography sub-dep
    "sqlalchemy",          # if dropped from sandbox
    "fastapi",             # paranoia — should be present
    "starlette",           # paranoia
}
try:
    from routes import documents as documents_route
    from fastapi import HTTPException as http_exc
    _ROUTE_AVAILABLE = True
except SystemExit:  # pragma: no cover — config.py exits when DATABASE_URL missing
    documents_route = None
    http_exc = None
    _ROUTE_AVAILABLE = False
except ImportError as _err:  # pragma: no cover
    # Only swallow if the missing module is a known optional dep. Anything
    # else (renamed symbol inside routes.documents, broken local import,
    # circular import bug) re-raises and the test class fails to load —
    # which surfaces in CI as the route tests being treated as errors,
    # which is what we want.
    _missing = getattr(_err, "name", None) or ""
    if _missing.split(".")[0] not in _KNOWN_OPTIONAL_DEPS:
        raise
    documents_route = None
    http_exc = None
    _ROUTE_AVAILABLE = False


pytestmark_route = pytest.mark.skipif(
    not _ROUTE_AVAILABLE,
    reason="routes.documents not importable in this environment",
)


@pytestmark_route
class TestPreviewRoute:
    """Unit tests for routes.documents.preview_document."""

    @pytest.fixture
    def request_obj(self):
        request = MagicMock()
        request.state.org_id = 1
        return request

    @pytest.fixture
    def db(self):
        return MagicMock()

    @pytest.fixture
    def real_pdf(self, tmp_path):
        p = tmp_path / "doc.pdf"
        p.write_bytes(b"%PDF-1.4\n%fake-pdf-for-test\n")
        return str(p)

    def _doc(self, *, file_path, mime="application/pdf", name="x.pdf"):
        d = MagicMock()
        d.id = 42
        d.name = name
        d.file_path = file_path
        d.local_path = None
        d.mime_type = mime
        return d

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, request_obj, db):
        with patch.object(documents_route, "get_current_user", return_value=None):
            with pytest.raises(http_exc) as exc:
                await documents_route.preview_document(request_obj, 1, db)
            assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_doc_not_found_returns_404(self, request_obj, db):
        tenant_query_mock = MagicMock()
        tenant_query_mock.filter.return_value.first.return_value = None
        with patch.object(documents_route, "get_current_user", return_value=MagicMock()), \
             patch.object(documents_route, "tenant_query", return_value=tenant_query_mock):
            with pytest.raises(http_exc) as exc:
                await documents_route.preview_document(request_obj, 999, db)
            assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_file_missing_returns_404(self, request_obj, db, tmp_path):
        doc = self._doc(file_path=str(tmp_path / "does-not-exist.pdf"))
        tenant_query_mock = MagicMock()
        tenant_query_mock.filter.return_value.first.return_value = doc
        with patch.object(documents_route, "get_current_user", return_value=MagicMock()), \
             patch.object(documents_route, "tenant_query", return_value=tenant_query_mock):
            with pytest.raises(http_exc) as exc:
                await documents_route.preview_document(request_obj, 1, db)
            assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_path_traversal_returns_403(self, request_obj, db, real_pdf):
        # File exists but lives outside UPLOAD_DIR — must be rejected.
        doc = self._doc(file_path=real_pdf)
        tenant_query_mock = MagicMock()
        tenant_query_mock.filter.return_value.first.return_value = doc
        with patch.object(documents_route, "get_current_user", return_value=MagicMock()), \
             patch.object(documents_route, "tenant_query", return_value=tenant_query_mock), \
             patch.object(documents_route, "UPLOAD_DIR", "/var/casehub/uploads-fake"):
            with pytest.raises(http_exc) as exc:
                await documents_route.preview_document(request_obj, 1, db)
            assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_valid_pdf_returns_inline(self, request_obj, db, real_pdf):
        doc = self._doc(file_path=real_pdf)
        tenant_query_mock = MagicMock()
        tenant_query_mock.filter.return_value.first.return_value = doc
        upload_dir = os.path.dirname(real_pdf)
        with patch.object(documents_route, "get_current_user", return_value=MagicMock()), \
             patch.object(documents_route, "tenant_query", return_value=tenant_query_mock), \
             patch.object(documents_route, "UPLOAD_DIR", upload_dir):
            response = await documents_route.preview_document(request_obj, 1, db)

        assert response.headers["content-disposition"].lower() == "inline"
        assert response.media_type == "application/pdf"

    @pytest.mark.asyncio
    async def test_falls_back_to_local_path(self, request_obj, db, real_pdf):
        # file_path missing → falls back to local_path (route line ~297).
        doc = self._doc(file_path="/nonexistent")
        doc.local_path = real_pdf
        tenant_query_mock = MagicMock()
        tenant_query_mock.filter.return_value.first.return_value = doc
        upload_dir = os.path.dirname(real_pdf)
        with patch.object(documents_route, "get_current_user", return_value=MagicMock()), \
             patch.object(documents_route, "tenant_query", return_value=tenant_query_mock), \
             patch.object(documents_route, "UPLOAD_DIR", upload_dir):
            response = await documents_route.preview_document(request_obj, 1, db)

        assert response.headers["content-disposition"].lower() == "inline"

    @pytest.mark.asyncio
    async def test_image_mime_propagates(self, request_obj, db, tmp_path):
        png = tmp_path / "img.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        doc = self._doc(file_path=str(png), mime="image/png", name="img.png")
        tenant_query_mock = MagicMock()
        tenant_query_mock.filter.return_value.first.return_value = doc
        with patch.object(documents_route, "get_current_user", return_value=MagicMock()), \
             patch.object(documents_route, "tenant_query", return_value=tenant_query_mock), \
             patch.object(documents_route, "UPLOAD_DIR", str(tmp_path)):
            response = await documents_route.preview_document(request_obj, 1, db)

        assert response.media_type == "image/png"
        assert response.headers["content-disposition"].lower() == "inline"


class TestStaticAssetsExist:
    """Verify the static assets the template references actually ship."""

    REPO_ROOT = Path(__file__).resolve().parent.parent

    def test_preview_js_present(self):
        assert (self.REPO_ROOT / "static" / "js" / "documents-preview.js").exists()

    def test_preview_css_present(self):
        assert (self.REPO_ROOT / "static" / "css" / "documents-preview.css").exists()

    def test_template_uses_data_preview_trigger(self):
        """Server-rendered triggers use [data-preview-trigger] + dataset
        instead of inline onclick (Codex P1 fix on PR #295). Verifies the
        markup pattern is in place and that all triggers reference /preview."""
        html = (self.REPO_ROOT / "templates" / "documents" / "list.html").read_text()
        assert "data-preview-trigger" in html, "preview trigger pattern missing"
        # No inline onclick="openPreview(...)" left in server-rendered markup.
        assert 'onclick="openPreview(' not in html, "inline onclick onPreview survives — pattern not migrated"
        # Every data-preview-url must point to /preview, never /download.
        for line in html.splitlines():
            if "data-preview-url=" not in line:
                continue
            assert "/preview" in line, f"data-preview-url missing /preview: {line.strip()}"

    def test_template_has_aria_labelledby(self):
        html = (self.REPO_ROOT / "templates" / "documents" / "list.html").read_text()
        assert 'aria-labelledby="previewTitle"' in html

    def test_preview_js_has_delegation(self):
        """JS must implement [data-preview-trigger] event delegation so the
        markup-side migration off inline onclick actually works."""
        js = (self.REPO_ROOT / "static" / "js" / "documents-preview.js").read_text()
        assert "data-preview-trigger" in js, "delegation listener missing"
        assert "previewUrl" in js, "dataset.previewUrl not consumed"
