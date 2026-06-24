"""Source-contract: o preview de PDF é um popup contido/centralizado, não fullscreen."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "static/css/templates/whatsapp-chat.css").read_text()
TPL = (ROOT / "templates/app/whatsapp/chat.html").read_text()

def test_markup_has_window_wrapper_and_close():
    assert 'class="wa-doc-preview-window"' in TPL
    assert 'wa-doc-preview-close' in TPL

def test_backdrop_centers_window_not_fullscreen_panel():
    rule = CSS[CSS.index('.wa-doc-preview {'):CSS.index('}', CSS.index('.wa-doc-preview {'))]
    assert 'align-items: center' in rule and 'justify-content: center' in rule
    assert 'flex-direction: column' not in rule  # não é mais o painel fullscreen

def test_window_is_bounded():
    win = CSS[CSS.index('.wa-doc-preview-window {'):CSS.index('}', CSS.index('.wa-doc-preview-window {'))]
    assert 'width: min(900px' in win and 'border-radius' in win and 'box-shadow' in win
