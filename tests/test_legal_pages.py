"""HTTP-layer tests for the public legal pages (#786 / T13).

Google's OAuth consent-screen verification probes the bare /privacy and
/terms URLs and is smoother when they answer HTTP 200 *directly* (no
301/302 redirect). These tests guard that the apex-level routes serve the
legal templates 200-direct and that the /static/legal/*.html files stay
reachable.
"""
import pytest
from fastapi.testclient import TestClient

from core.app_factory import create_app


@pytest.fixture
def client():
    app = create_app("lite")
    return TestClient(app, follow_redirects=False)


@pytest.mark.parametrize("path", ["/privacy", "/terms"])
def test_legal_page_is_200_direct_html(client, path):
    """Bare /privacy and /terms must return 200 HTML directly (no redirect)."""
    resp = client.get(path)
    assert resp.status_code == 200, f"{path} returned {resp.status_code}, expected 200 (no redirect)"
    assert "text/html" in resp.headers.get("content-type", "")


@pytest.mark.parametrize(
    "path",
    ["/privacy-policy", "/politica-de-privacidade", "/termos"],
)
def test_legal_aliases_are_200_direct(client, path):
    """Policy/pt-BR aliases also serve 200-direct."""
    resp = client.get(path)
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


@pytest.mark.parametrize(
    "path",
    ["/static/legal/privacy.html", "/static/legal/terms.html"],
)
def test_static_legal_files_still_served(client, path):
    """The static legal HTML files must remain reachable (not removed)."""
    resp = client.get(path)
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
