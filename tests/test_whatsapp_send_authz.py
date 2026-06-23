"""Send-path contract for the WhatsApp clone (routes/whatsapp_chat.py).

Covers the org-4 alpha follow-up (handoff 019ec968): sending must be scoped to
the TENANT, not to the human profile that scanned the QR, and failures must be
differentiated so the operator UI stops showing a dead-end "Failed to send
message".

These exercise `_dispatch_human_send` directly (the shared core of /api/send and
/api/send-message) so the JSON/Form parsing layer is out of scope here.

Run: pytest tests/test_whatsapp_send_authz.py
"""
import asyncio
import json
from types import SimpleNamespace

import pytest

import routes.whatsapp_chat as wc
from models.whatsapp_clone import WaMessage


def _request(org_id=4):
    """Minimal request stub. state.org_id drives the send path; headers/client
    are read by the best-effort audit trail (_audit_outgoing_send) once a send
    is attributed to a user, so stub them to keep the audit path exception-free."""
    return SimpleNamespace(
        state=SimpleNamespace(org_id=org_id),
        headers={"x-forwarded-for": "127.0.0.1", "user-agent": "pytest"},
        client=SimpleNamespace(host="127.0.0.1"),
    )


def _user(uid, org_id=4, user_type="attorney"):
    return SimpleNamespace(id=uid, org_id=org_id, user_type=user_type, email=f"u{uid}@vs.test")


def _patch(monkeypatch, *, user, connected=True, send_result=None):
    """Wire get_current_user / get_bot_status / send_message_via_bot stubs."""
    monkeypatch.setattr(wc, "get_current_user", lambda request, db: user)

    async def fake_status(request=None):
        return {"connected": connected, "status": "ready" if connected else "offline"}

    monkeypatch.setattr(wc, "get_bot_status", fake_status)

    calls = {"sent": 0}

    async def fake_send(phone, message, *a, **k):
        calls["sent"] += 1
        return send_result if send_result is not None else {
            "success": True, "ok": True, "messageId": "WAMID-1", "error": None,
        }

    monkeypatch.setattr(wc, "send_message_via_bot", fake_send)
    return calls


def _body(response):
    return json.loads(bytes(response.body).decode())


def _run(db, request, user_phone="5511988887777", message="oi"):
    return asyncio.run(
        wc._dispatch_human_send(request, db, user_phone, message, None, None)
    )


# ---------------------------------------------------------------------------
# Criterion 1 + 2: any authorized org user can send; message is attributed.
# ---------------------------------------------------------------------------
def test_authorized_user_sends_and_is_attributed(db, monkeypatch):
    user = _user(10)
    _patch(monkeypatch, user=user)

    resp = _run(db, _request(org_id=4))

    assert resp.status_code == 200
    rows = db.query(WaMessage).filter(WaMessage.org_id == 4).all()
    assert len(rows) == 1
    assert rows[0].direction == "outgoing"
    assert rows[0].sent_by_user_id == 10


def test_non_connector_user_can_send(db, monkeypatch):
    """The user sending need NOT be the one who scanned the QR — the send path
    references no 'connector' identity, only the tenant org. A second org user
    sends successfully and the row is attributed to *them*."""
    sender = _user(20)  # different person from whoever paired the device
    _patch(monkeypatch, user=sender)

    resp = _run(db, _request(org_id=4))

    assert resp.status_code == 200
    row = db.query(WaMessage).filter(WaMessage.org_id == 4).one()
    assert row.sent_by_user_id == 20


def test_send_is_org_scoped(db, monkeypatch):
    _patch(monkeypatch, user=_user(10, org_id=4))

    _run(db, _request(org_id=4))

    assert db.query(WaMessage).filter(WaMessage.org_id == 4).count() == 1
    assert db.query(WaMessage).filter(WaMessage.org_id == 5).count() == 0


# ---------------------------------------------------------------------------
# Criterion 3: disconnected session → specific error, nothing persisted.
# ---------------------------------------------------------------------------
def test_disconnected_session_returns_specific_error(db, monkeypatch):
    calls = _patch(monkeypatch, user=_user(10), connected=False)

    resp = _run(db, _request(org_id=4))

    assert resp.status_code == 503
    body = _body(resp)
    assert body["error_code"] == "whatsapp_disconnected"
    assert "QR" in body["error"]
    assert calls["sent"] == 0  # never reached the bot
    assert db.query(WaMessage).count() == 0  # no phantom outgoing row


def test_dropped_session_during_send_is_reclassified(db, monkeypatch):
    """Pre-flight said ready, but the send itself failed with a session-drop
    error → reclassified to whatsapp_disconnected (not a generic send_failed)."""
    _patch(monkeypatch, user=_user(10),
           send_result={"success": False, "ok": False, "messageId": None,
                        "error": "Session closed"})

    resp = _run(db, _request(org_id=4))

    assert resp.status_code == 503
    assert _body(resp)["error_code"] == "whatsapp_disconnected"


def test_generic_send_failure_is_send_failed(db, monkeypatch):
    _patch(monkeypatch, user=_user(10),
           send_result={"success": False, "ok": False, "messageId": None,
                        "error": "boom"})

    resp = _run(db, _request(org_id=4))

    assert resp.status_code == 502
    body = _body(resp)
    assert body["error_code"] == "send_failed"
    assert body["error"] == "boom"


# ---------------------------------------------------------------------------
# Criterion 4: a role without whatsapp.send gets a permission error, not a bot
# error — and the bot is never called.
# ---------------------------------------------------------------------------
def test_forbidden_role_returns_permission_error(db, monkeypatch):
    calls = _patch(monkeypatch, user=_user(99, user_type="guest"))

    resp = _run(db, _request(org_id=4))

    assert resp.status_code == 403
    assert _body(resp)["error_code"] == "forbidden"
    assert calls["sent"] == 0


def test_unauthenticated_returns_401(db, monkeypatch):
    _patch(monkeypatch, user=None)

    resp = _run(db, _request(org_id=4))

    assert resp.status_code == 401
    assert _body(resp)["error_code"] == "unauthorized"
