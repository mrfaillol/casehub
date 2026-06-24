"""Source-contract: a lista de conversas contém o próprio scroll.

No mobile o layout é empilhado (lista acima, conversa abaixo) e a página também
rola; sem overscroll-behavior o gesto de rolar a lista vazava para a página e
parecia que "a lista não scrolla". Live-validado 2026-06-17 (lista rolou,
window.scrollY ficou 0). Trava pra não regredir.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static/css/templates/whatsapp-chat.css").read_text()
MANIFEST = json.loads((ROOT / "static/assets/dashboard-manifest.json").read_text())


def _rule(sel):
    start = CSS.index(sel + " {")
    return CSS[start:CSS.index("}", start)]


def _shell_mobile_rule(sel):
    shell_skin_start = CSS.index(".wa-shell-module .wa-qr-code {")
    mobile_start = CSS.index("@media (max-width: 768px)", shell_skin_start)
    start = CSS.index(sel + " {", mobile_start)
    return CSS[start:CSS.index("}", start)]


def test_conversations_contains_its_scroll():
    rule = _rule(".wa-conversations")
    assert "overflow-y: auto" in rule
    assert "overscroll-behavior: contain" in rule
    assert "touch-action: pan-y" in rule


def test_mobile_shell_has_viewport_height_not_document_height():
    rule = _shell_mobile_rule(".wa-shell-module .wa-app")
    assert "--wa-mobile-chrome-offset" in CSS
    assert "height: auto" not in rule
    assert "height: calc(100dvh - var(--wa-mobile-chrome-offset))" in rule
    assert "min-height: 0" in rule
    assert "max-height: calc(100dvh - var(--wa-mobile-chrome-offset))" in rule
    assert "overscroll-behavior: contain" in rule


def test_mobile_shell_scroll_regions_are_contained():
    main = _shell_mobile_rule(".wa-shell-module .wa-main")
    sidebar = _shell_mobile_rule(".wa-shell-module .wa-sidebar")
    conversations = _shell_mobile_rule(".wa-shell-module .wa-conversations")
    qr = _shell_mobile_rule(".wa-shell-module .wa-qr-container")

    assert "min-height: 0" in main
    assert "overflow: hidden" in main
    assert "flex: 0 0 clamp(320px, 68%, 480px)" in sidebar
    assert "max-height: 68%" in sidebar
    assert "overflow: hidden" in sidebar
    assert "overflow-y: auto" in conversations
    assert "-webkit-overflow-scrolling: touch" in conversations
    assert "overscroll-behavior: contain" in conversations
    assert "touch-action: pan-y" in conversations
    assert "overflow-y: auto" in qr
    assert "overscroll-behavior: contain" in qr


def test_whatsapp_chat_css_manifest_hash_matches_file():
    css = (ROOT / "static/css/templates/whatsapp-chat.css").read_text()
    expected = hashlib.sha256(css.encode()).hexdigest()[:12]
    actual = MANIFEST["assets"]["css/templates/whatsapp-chat.css"]["hash"]
    assert actual == expected
