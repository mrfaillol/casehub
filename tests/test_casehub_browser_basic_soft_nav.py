from pathlib import Path


def test_soft_navigation_syncs_route_inline_styles():
    source = Path("static/js/casehub-browser-basic.js").read_text(encoding="utf-8")

    assert "syncRouteStyles(nextDoc);" in source
    assert "style[data-casehub-soft-style]" in source
    assert "qsa('style', doc.head)" in source
    assert "data-casehub-soft-style" in source
    assert "loadMissingStyles(doc);" in source
