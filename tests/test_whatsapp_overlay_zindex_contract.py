"""Source-contract: overlays do whatsapp-chat ficam acima da chrome do OS.

Na página deployada (.wa-shell-module) os tokens --z-* não resolvem (--z-popover,
--z-tooltip = undefined) e --surface-inverse resolve para uma COR CLARA na dark
theme. Isso deixava popovers/modais COBERTOS pela bottom nav do OS (z:65) e com
backdrop claro. Fixes (live-validados 2026-06-17): fallback concreto de z-index
nos popovers + backdrop escuro fixo. Cache-bust do manifest pra os fixes
chegarem ao usuário (o hash estava congelado em '20260609-neu').
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static/css/templates/whatsapp-chat.css").read_text()
MANIFEST = json.loads((ROOT / "static/assets/dashboard-manifest.json").read_text())


def test_popovers_have_concrete_zindex_fallback():
    # --z-popover é undefined na página → precisa de fallback acima da OS chrome
    assert "z-index: var(--z-popover);" not in CSS
    assert CSS.count("z-index: var(--z-popover, 1500);") >= 3


def test_backdrops_use_concrete_dark_not_surface_inverse():
    # --surface-inverse resolve claro na dark theme → clareava em vez de escurecer
    assert "var(--surface-inverse" not in CSS


def test_whatsapp_chat_css_cache_hash_was_bumped():
    h = MANIFEST["assets"]["css/templates/whatsapp-chat.css"]["hash"]
    assert h != "20260609-neu", "cache hash congelado — fixes de CSS não chegam ao browser"
