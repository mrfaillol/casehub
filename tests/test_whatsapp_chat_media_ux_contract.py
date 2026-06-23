"""Source-contract tests for the WhatsApp chat media/UX hardening.

These assert the wiring in the static assets (where a live browser test is
impossible) so future refactors cannot silently regress:
  - inline images get an onerror fallback + a download affordance
  - documents download instead of only opening
  - the lightbox can download the open image
  - reply/react buttons are styled (discrete), not raw native <button>s
  - message text is pinned to a broad-coverage font stack (glyph hardening)
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "static/js/chat.js").read_text()
CSS = (ROOT / "static/css/templates/whatsapp-chat.css").read_text()
TPL = (ROOT / "templates/app/whatsapp/chat.html").read_text()


# ── Inline images: visible + downloadable ───────────────────────────────
def test_inline_image_has_onerror_fallback():
    assert "onerror=\"waImageError(this" in JS
    assert "function waImageError(" in JS
    assert "wa-media-broken" in JS and ".wa-media-broken" in CSS


def test_inline_image_has_download_button():
    assert "wa-media-download" in JS and ".wa-media-download" in CSS
    assert "function downloadMedia(" in JS
    assert "wa-message-media--image" in JS and ".wa-message-media--image" in CSS


def test_document_has_preview_and_download():
    # the doc row previews (PDF viewer / image lightbox); a separate button downloads
    assert "openDocPreview(" in JS and "function openDocPreview(" in JS
    assert "is-previewable" in JS and ".wa-message-media-doc.is-previewable" in CSS
    assert "wa-doc-download-btn" in JS and ".wa-doc-download-btn {" in CSS


def test_doc_preview_modal_wired():
    assert "id=\"docPreview\"" in TPL
    assert "docPreviewFrame" in TPL and "docPreviewFrame" in JS
    assert ".wa-doc-preview {" in CSS
    assert "function closeDocPreview(" in JS


def test_lightbox_gallery_nav_and_zoom():
    # arrow through every conversation image + zoom
    assert "function lightboxNav(" in JS
    assert "function lightboxToggleZoom(" in JS
    assert "wa-message-media--image img" in JS  # gallery source
    assert "ArrowLeft" in JS and "ArrowRight" in JS
    assert "id=\"lightboxPrev\"" in TPL and "id=\"lightboxNext\"" in TPL
    assert "id=\"lightboxCounter\"" in TPL
    assert ".wa-lightbox img.zoomed" in CSS and ".wa-lightbox-nav" in CSS
    # inline images carry a filename for the gallery
    assert "data-filename=\"${imgName}\"" in JS


def test_lightbox_can_download():
    assert "wa-lightbox-download" in CSS
    assert "id=\"lightboxDownload\"" in TPL
    assert "downloadMedia(this.dataset.src" in TPL


def test_download_has_open_in_tab_fallback():
    # never a dead end: a blocked fetch falls back to opening the URL
    assert "window.open(url, '_blank', 'noopener')" in JS


# ── Discrete reply/react affordance ─────────────────────────────────────
def test_message_actions_are_styled_not_native_pills():
    # the bug: .wa-msg-action-btn had no base rule -> loud native buttons
    assert ".wa-msg-action-btn {" in CSS
    assert ".wa-message-actions {" in CSS
    # hidden until hover/focus on desktop
    assert ".wa-message:hover .wa-message-actions" in CSS
    assert ":focus-within .wa-message-actions" in CSS
    # quiet on touch where hover is impossible
    assert "@media (hover: none)" in CSS


def test_touch_hides_floating_bolinhas_and_menu_has_react():
    # on touch the floating bolinhas are hidden (they overlapped messages on mobile)
    assert ".wa-message-actions { display: none; }" in CSS
    # react stays reachable via the long-press context menu
    assert "openReactionPickerFromMenu()" in TPL
    assert "Reagir" in TPL


def test_togglebot_sends_defined_form():
    # the "Sugestões" toggle threw a ReferenceError (undefined formData) and
    # silently rolled back; it must build phone+enabled (app proxy Form fields)
    block = JS.split("async function toggleBot(", 1)[1].split("\n}", 1)[0]
    assert "new URLSearchParams()" in block
    assert "formData.append('phone'" in block
    assert "formData.append('enabled'" in block


def test_mobile_summary_capped():
    # the conversation summary must not cover the chat on mobile
    assert ".wa-conversation-context:not(.collapsed) .wa-context-body" in CSS
    assert "26vh" in CSS


def test_message_actions_not_aria_hidden():
    # buttons are keyboard-reachable now, so the container must not be hidden
    assert "wa-message-actions\" aria-hidden=\"true\"" not in JS


# ── Paste & drag-drop to attach (WhatsApp Web parity) ───────────────────
def test_paste_and_drop_attach_wired():
    assert "function acceptAttachment(" in JS
    # all sources funnel through the shared validator
    assert "acceptAttachment(" in JS
    # paste handler for images
    assert "addEventListener('paste'" in JS and "clipboardData" in JS
    # drag-drop with overlay
    assert "addEventListener('drop'" in JS
    assert "wa-drop-overlay" in JS and ".wa-drop-overlay {" in CSS
    # reuses the existing composer, not a new send path
    assert "openMediaComposer(file)" in JS


# ── Glyph hardening ─────────────────────────────────────────────────────
def test_message_text_has_broad_font_stack():
    block = CSS.split("\n.wa-message-content {", 1)[1].split("}", 1)[0]
    assert "font-family:" in block
    assert "Emoji" in block  # explicit emoji fallback
    assert "font-variant-ligatures: none" in block
