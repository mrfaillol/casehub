"""Follow-up regressions for org-scoped WhatsApp sends.

Locks the June 2026 Escritorio Demo report:
  * the bot receives X-Org-Id from tenant context;
  * any authenticated org user can send through the org session;
  * disconnected bot states surface as reconnect/QR failures;
  * the Lite send route does not fall back to a default org session.
"""
import asyncio
import json
from types import SimpleNamespace

from sqlalchemy import text

from models.tenant import Organization
from models.whatsapp_clone import WaMessage


class _JsonRequest:
    def __init__(self, body, org_id=4):
        self._body = body
        self.state = SimpleNamespace(org_id=org_id)
        self.headers = {
            "content-type": "application/json",
            "user-agent": "pytest",
        }
        self.client = SimpleNamespace(host="127.0.0.1")

    async def json(self):
        return self._body


def _response_json(resp):
    return json.loads(resp.body.decode("utf-8"))


def _make_org(db, oid=4):
    db.add(Organization(id=oid, uuid=f"uuid-{oid}", name=f"Org {oid}", slug=f"org-{oid}"))
    db.flush()


def _make_audit_table(db):
    db.execute(text("""
        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT,
            entity_type TEXT,
            entity_id INTEGER,
            user_id INTEGER,
            user_email TEXT,
            description TEXT,
            details TEXT,
            ip_address TEXT,
            user_agent TEXT,
            org_id INTEGER,
            created_at TEXT
        )
    """))
    db.commit()


def test_send_message_via_bot_passes_tenant_org_header(monkeypatch):
    import routes.whatsapp_chat as wc

    captured = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {"ok": True, "messageId": "wamid.TEST"}

    class _Client:
        async def post(self, url, json=None, timeout=None, headers=None):
            captured["url"] = url
            captured["headers"] = headers or {}
            return _Resp()

    monkeypatch.setattr(wc, "get_bot_client", lambda: _Client())
    req = SimpleNamespace(state=SimpleNamespace(org_id=4))

    result = asyncio.run(wc.send_message_via_bot("+5511999999999", "oi", request=req))

    assert result["success"] is True
    assert captured["headers"]["X-Org-Id"] == "4"
    assert captured["url"].endswith("/api/send-message")


def test_authorized_non_connector_user_send_persists_and_audits(db, monkeypatch):
    import routes.whatsapp_chat as wc

    _make_org(db)
    _make_audit_table(db)
    actor = SimpleNamespace(id=99, email="pessoa_demo@example.test", user_type="attorney")
    request = _JsonRequest({"phone": "+5511999999999", "message": "oi do PessoaDemo"})

    async def fake_send(phone, message, from_human=False, reply_to_wa_message_id=None, request=None):
        assert from_human is True
        return {"success": True, "ok": True, "messageId": "wamid.EXAMPLE"}

    async def fake_status(request=None):
        return {"connected": True, "status": "ready"}

    monkeypatch.setattr(wc, "get_current_user", lambda req, session: actor)
    monkeypatch.setattr(wc, "get_bot_status", fake_status)
    monkeypatch.setattr(wc, "send_message_via_bot", fake_send)

    resp = asyncio.run(wc.api_send_message(request, db=db))

    assert resp.status_code == 200
    payload = _response_json(resp)
    assert payload["messageId"] == "wamid.EXAMPLE"

    msg = db.query(WaMessage).one()
    assert msg.org_id == 4
    assert msg.from_me is True
    assert msg.body == "oi do PessoaDemo"
    assert msg.wa_message_id == "wamid.EXAMPLE"

    audit = db.execute(text("""
        SELECT action, entity_type, entity_id, user_id, user_email, org_id, details
        FROM audit_log
        WHERE action = 'whatsapp_send'
    """)).fetchone()
    assert audit.action == "whatsapp_send"
    assert audit.entity_type == "wa_message"
    assert audit.entity_id == msg.id
    assert audit.user_id == 99
    assert audit.user_email == "pessoa_demo@example.test"
    assert audit.org_id == 4
    assert "oi do PessoaDemo" not in (audit.details or "")


def test_disconnected_bot_send_returns_reconnect_status(db, monkeypatch):
    import routes.whatsapp_chat as wc

    _make_org(db)
    actor = SimpleNamespace(id=99, email="pessoa_demo@example.test", user_type="attorney")
    request = _JsonRequest({"phone": "+5511999999999", "message": "oi"})

    async def fake_send(phone, message, from_human=False, reply_to_wa_message_id=None, request=None):
        return {"success": False, "ok": False, "error": "WhatsApp client not ready"}

    async def fake_status(request=None):
        return {"connected": True, "status": "ready"}

    monkeypatch.setattr(wc, "get_current_user", lambda req, session: actor)
    monkeypatch.setattr(wc, "get_bot_status", fake_status)
    monkeypatch.setattr(wc, "send_message_via_bot", fake_send)

    resp = asyncio.run(wc.api_send_message(request, db=db))

    assert resp.status_code == 503
    payload = _response_json(resp)
    assert payload["error_code"] == "whatsapp_disconnected"
    assert "QR Code" in payload["error"]
    assert db.query(WaMessage).count() == 0


def test_lite_send_uses_request_org_id(db, monkeypatch):
    import routes.whatsapp_lite as wl
    import services.whatsapp as whatsapp_service

    captured = {}

    class _Service:
        def __init__(self, session, org_id=None):
            captured["org_id"] = org_id

        def send_message(self, phone, message, template_key=None):
            captured["phone"] = phone
            captured["message"] = message
            return {"success": True, "message_id": "wamid.LITE"}

    req = SimpleNamespace(state=SimpleNamespace(org_id=4))
    monkeypatch.setattr(wl, "get_current_user", lambda request, session: object())
    monkeypatch.setattr(whatsapp_service, "WhatsAppService", _Service)

    resp = asyncio.run(wl.send_message(req, phone="+5511999999999", message="oi", template_key=None, db=db))

    assert resp.status_code == 200
    assert _response_json(resp)["message_id"] == "wamid.LITE"
    assert captured["org_id"] == 4
