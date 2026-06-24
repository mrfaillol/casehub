"""Source-contract tests for the lead-funnel (funil) translucent window.

Live-validated on the alpha (2026-06-17), asserted here so a future refactor
can't silently regress the two findings the live check surfaced:
  - the panel is translucent (color-mix over surface-card), no heavy blur
  - the dark backdrop is a fixed dark color via box-shadow spread (NOT
    --surface-inverse, which resolves to a LIGHT color under the dark theme
    and lightened the page instead of dimming it)
  - z-index is a concrete fallback (the --z-modal token resolves to 90 on the
    deployed page, below app chrome)
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static/css/templates/whatsapp-crm.css").read_text()


def _host_rule() -> str:
    """The `#wacPipelineHost { ... }` rule body. Ends at a brace at column 0
    (`\\n}`) so inline braces inside comments (`.wa-sidebar{width:380px}`) don't
    truncate it early."""
    start = CSS.index("#wacPipelineHost {")
    return CSS[start : CSS.index("\n}", start)]


def test_funil_panel_is_translucent_no_blur():
    # painel translúcido a 92% sobre o backdrop, sem blur custoso (perf)
    rule = _host_rule()
    assert "color-mix(in srgb, var(--surface-card, #131c2d) 92%, transparent)" in rule
    # checa USO (propriedade), não menção em comentário
    assert "backdrop-filter:" not in rule and "blur(" not in rule


def test_funil_has_dark_box_shadow_backdrop():
    # backdrop = box-shadow spread full-viewport com cor escura FIXA
    assert "0 0 0 100vmax rgba(8, 12, 22, 0.6)" in _host_rule()


def test_funil_backdrop_does_not_use_surface_inverse():
    # --surface-inverse resolve p/ claro na dark theme → clareava a página.
    # checa USO via var(), não a menção no comentário que explica a escolha.
    assert "var(--surface-inverse" not in _host_rule()


def test_funil_zindex_has_concrete_fallback():
    # token --z-modal resolve p/ 90 na página deployada → fixo concreto
    assert "z-index: 1200" in CSS
    # sem o trap do pseudo-elemento z-index:-1 empurrado atrás da página
    assert "#wacPipelineHost::before" not in CSS
