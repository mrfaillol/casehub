"""Source-contract test for the reply-bar + reaction-picker wiring.

The app chat template (templates/app/whatsapp/chat.html, served at
/casehub/whatsapp-chat) had diverged from templates/whatsapp/chat.html and was
MISSING the #replyBar / #reactionPicker markup that chat.js drives. Result:
  - startReplyTo() crashed (set .textContent of null #replyBarAuthor)
  - openReactionPicker() silently no-op'd (#reactionPicker was null)
so the reply/react bolinhas (and the long-press menu) did nothing. Live-fixed
2026-06-17. Lock the markup + styling so a future refactor can't drop it again.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_TPL = (ROOT / "templates/app/whatsapp/chat.html").read_text()
JS = (ROOT / "static/js/chat.js").read_text()
CSS = (ROOT / "static/css/templates/whatsapp-chat.css").read_text()


def test_app_template_has_reply_bar_markup():
    # the exact ids startReplyTo()/cancelReply() touch
    for needed in ('id="replyBar"', 'id="replyBarAuthor"', 'id="replyBarText"'):
        assert needed in APP_TPL


def test_app_template_has_reaction_picker_markup():
    assert 'id="reactionPicker"' in APP_TPL


def test_js_handlers_target_those_ids():
    # guards against a silent rename drift between JS and template
    assert "getElementById('replyBarAuthor')" in JS
    assert "getElementById('reactionPicker')" in JS


def test_reply_bar_and_picker_are_styled():
    # .show toggles visibility; the picker must be fixed (JS sets clientX/Y coords)
    assert ".wa-reply-bar.show" in CSS
    assert ".wa-reaction-picker.show" in CSS
    pk = CSS[CSS.index(".wa-reaction-picker {") : CSS.index("}", CSS.index(".wa-reaction-picker {"))]
    assert "position: fixed" in pk
