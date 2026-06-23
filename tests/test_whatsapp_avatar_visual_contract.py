from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_whatsapp_avatar_hidden_fallback_is_force_hidden():
    css = (ROOT / "static/css/templates/whatsapp-chat.css").read_text()

    assert ".wa-avatar [hidden]" in css
    assert ".wa-shell-module .wa-avatar [hidden]" in css
    assert "display: none !important;" in css


def test_whatsapp_photo_avatar_suppresses_initials_fallback():
    css = (ROOT / "static/css/templates/whatsapp-chat.css").read_text()
    js = (ROOT / "static/js/chat.js").read_text()

    assert "wa-avatar--has-photo" not in css
    assert "wa-avatar--has-photo" not in js
    assert "nextElementSibling.hidden=false" in js
    assert "wa-avatar-initials\" hidden" in js
    assert "wa-avatar-fallback\" hidden" in js
