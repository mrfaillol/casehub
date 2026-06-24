"""
Regression test: document-template rendering MUST be sandboxed.

Background (2026-06-16 Sentinela audit): services/templates_service.py rendered
user-authored template bodies through a bare ``jinja2.Template``, letting any
authenticated tenant user reach RCE via POST /casehub/templates/preview with a
payload like ``{{ cycler.__init__.__globals__.os.popen(...) }}``. The renderer
now uses ``jinja2.sandbox.SandboxedEnvironment``. These tests fail loudly if the
sandbox is ever removed or downgraded back to a bare Environment/Template.
"""
from jinja2.sandbox import SandboxedEnvironment

from services.templates_service import DocumentTemplateService


def _render(payload, context=None):
    # render_template never touches the DB session, so db=None is safe here.
    service = DocumentTemplateService(db=None)
    return service.render_template(payload, context or {})


def test_renderer_is_sandboxed():
    service = DocumentTemplateService(db=None)
    assert isinstance(service.env, SandboxedEnvironment)


def test_ssti_globals_payload_is_blocked():
    payload = "{{ cycler.__init__.__globals__.os.popen('echo PWNED').read() }}"
    out = _render(payload)
    assert "PWNED" not in out
    assert "operation not permitted" in out


def test_ssti_class_traversal_is_blocked():
    payload = "{{ ''.__class__.__mro__[1].__subclasses__() }}"
    out = _render(payload)
    assert "subprocess" not in out
    assert "operation not permitted" in out


def test_legitimate_template_still_renders():
    payload = (
        "Prezado(a) {{ client.full_name }}, processo {{ case.case_number }}. "
        "{{ firm.name }}."
    )
    ctx = {
        "client": {"full_name": "PessoaDemo Silva"},
        "case": {"case_number": "0001234-55.2026"},
        "firm": {"name": "Escritorio Demo"},
    }
    out = _render(payload, ctx)
    assert out == "Prezado(a) PessoaDemo Silva, processo 0001234-55.2026. Escritorio Demo."
