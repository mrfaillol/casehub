"""Unit tests for the WhatsApp Web clone backend (WS-A).

Covers:
  * whatsapp_clone_service — upsert/record/query/dedup/status-ticks, tenant scoping.
  * routes/whatsapp_proxy — auth gate + transparent forwarding (bot HTTP mocked).
  * routes/whatsapp_chat — CASEHUB_WHATSAPP_CLONE_ENABLED flag → router prefix.

Style mirrors tests/test_whatsapp_inbound.py. DB tests use the in-memory SQLite
session from conftest.py (the wa_* ORM models are created by metadata.create_all).

Run: pytest tests/test_whatsapp_clone.py
"""
import importlib
from datetime import datetime, timedelta, timezone

import pytest

from models.tenant import Organization
from models.notification import Notification
from models.user import User
from models.whatsapp_clone import WaContact, WaConversation, WaMessage
from services import whatsapp_clone_service as svc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _make_org(db, oid=1, slug="org-a"):
    org = Organization(id=oid, uuid=f"uuid-{oid}", name=f"Org {oid}", slug=slug)
    db.add(org)
    db.flush()
    return org


def _make_user(db, uid=1, org_id=1, email="staff@example.test"):
    user = User(
        id=uid,
        org_id=org_id,
        email=email,
        name=f"Staff {uid}",
        password_hash="test",
        user_type="admin",
        enabled=True,
    )
    db.add(user)
    db.flush()
    return user


# ---------------------------------------------------------------------------
# normalize_phone
# ---------------------------------------------------------------------------
def test_normalize_phone_variants():
    assert svc.normalize_phone("+55 (11) 99999-9999") == "+5511999999999"
    assert svc.normalize_phone("5511999999999@c.us") == "+5511999999999"
    assert svc.normalize_phone("5511999999999") == "+5511999999999"
    assert svc.normalize_phone("123456@g.us") == "+123456"
    assert svc.normalize_phone("") == ""
    assert svc.normalize_phone(None) == ""


# ---------------------------------------------------------------------------
# upsert_contact / upsert_conversation
# ---------------------------------------------------------------------------
def test_upsert_contact_creates_then_updates(db):
    _make_org(db)
    c1 = svc.upsert_contact(db, org_id=1, phone="5511999999999", display_name="Alice")
    assert c1.id is not None
    assert c1.phone == "+5511999999999"
    assert c1.display_name == "Alice"

    # Re-upsert same (org, phone) updates the same row, not a new one.
    c2 = svc.upsert_contact(db, org_id=1, phone="+55 11 99999-9999", display_name="Alice B.")
    assert c2.id == c1.id
    assert c2.display_name == "Alice B."
    assert db.query(WaContact).count() == 1


def test_upsert_contact_requires_org_and_phone(db):
    _make_org(db)
    with pytest.raises(ValueError):
        svc.upsert_contact(db, org_id=0, phone="5511999999999")
    with pytest.raises(ValueError):
        svc.upsert_contact(db, org_id=1, phone="")


def test_upsert_conversation_is_idempotent(db):
    _make_org(db)
    contact = svc.upsert_contact(db, org_id=1, phone="5511999999999")
    conv1 = svc.upsert_conversation(db, org_id=1, contact_id=contact.id)
    conv2 = svc.upsert_conversation(db, org_id=1, contact_id=contact.id)
    assert conv1.id == conv2.id
    assert db.query(WaConversation).count() == 1


# ---------------------------------------------------------------------------
# record_message
# ---------------------------------------------------------------------------
def test_record_message_creates_thread_and_bumps_conversation(db):
    _make_org(db)
    msg = svc.record_message(
        db, org_id=1, phone="5511999999999", body="oi", direction="incoming",
        wa_message_id="WAMID-1",
    )
    assert msg.id is not None
    assert msg.direction == "incoming"
    assert msg.from_me is False

    conv = db.query(WaConversation).one()
    assert conv.last_message_id == msg.id
    assert conv.last_message_at is not None
    assert conv.unread_count == 1  # incoming bumps unread


def test_record_message_dedups_by_wa_message_id(db):
    _make_org(db)
    m1 = svc.record_message(db, org_id=1, phone="5511999999999", body="hi", wa_message_id="DUP-1")
    m2 = svc.record_message(db, org_id=1, phone="5511999999999", body="hi again", wa_message_id="DUP-1")
    assert m1.id == m2.id
    assert db.query(WaMessage).count() == 1
    # Unread incremented only once (second call was a dedup no-op).
    assert db.query(WaConversation).one().unread_count == 1


def test_record_message_outgoing_does_not_bump_unread(db):
    _make_org(db)
    svc.record_message(db, org_id=1, phone="5511999999999", body="reply",
                       direction="outgoing", wa_message_id="OUT-1")
    conv = db.query(WaConversation).one()
    assert conv.unread_count == 0
    msg = db.query(WaMessage).one()
    assert msg.from_me is True
    assert msg.status == "sent"


def test_record_message_tenant_isolation(db):
    _make_org(db, oid=1, slug="org-a")
    _make_org(db, oid=2, slug="org-b")
    svc.record_message(db, org_id=1, phone="5511999999999", body="org1", wa_message_id="A")
    svc.record_message(db, org_id=2, phone="5511999999999", body="org2", wa_message_id="A")
    # Same phone + same wa_message_id, different orgs → two distinct rows.
    assert db.query(WaMessage).count() == 2
    assert len(svc.list_conversations(db, org_id=1)) == 1
    assert len(svc.list_conversations(db, org_id=2)) == 1


# ---------------------------------------------------------------------------
# update_message_status (ticks from bot message_ack)
# ---------------------------------------------------------------------------
def test_update_message_status_advances_forward_only(db):
    _make_org(db)
    svc.record_message(db, org_id=1, phone="5511999999999", body="hi",
                       direction="outgoing", wa_message_id="ACK-1", status="sent")

    # ack=2 -> delivered
    m = svc.update_message_status(db, org_id=1, wa_message_id="ACK-1", ack=2)
    assert m.status == "delivered"
    # ack=3 -> read
    m = svc.update_message_status(db, org_id=1, wa_message_id="ACK-1", ack=3)
    assert m.status == "read"
    # stale ack=1 (sent) must NOT regress a read message
    m = svc.update_message_status(db, org_id=1, wa_message_id="ACK-1", ack=1)
    assert m.status == "read"


def test_update_message_status_unknown_id_returns_none(db):
    _make_org(db)
    assert svc.update_message_status(db, org_id=1, wa_message_id="NOPE", ack=2) is None


def test_status_from_ack_mapping():
    assert WaMessage.status_from_ack(0) == "pending"
    assert WaMessage.status_from_ack(1) == "sent"
    assert WaMessage.status_from_ack(2) == "delivered"
    assert WaMessage.status_from_ack(3) == "read"
    assert WaMessage.status_from_ack(4) == "played"
    assert WaMessage.status_from_ack("garbage") == "sent"


# ---------------------------------------------------------------------------
# list_conversations / list_messages — chat.js contract shape
# ---------------------------------------------------------------------------
def test_list_conversations_shape_matches_frontend_contract(db):
    _make_org(db)
    svc.record_message(db, org_id=1, phone="5511999999999", body="latest",
                       wa_message_id="C-1", display_name="Bob",
                       profile_pic_url="https://pps.whatsapp.net/avatar.jpg")
    convs = svc.list_conversations(db, org_id=1)
    assert len(convs) == 1
    c = convs[0]
    # Keys static/js/chat.js renderConversations() reads.
    for key in ("phone", "name", "lastMessage", "lastMessageTime",
                "unread", "from_bot", "bot_enabled", "human_takeover",
                "contact_type", "updated_at"):
        assert key in c, f"missing conversation key: {key}"
    assert c["phone"] == "+5511999999999"
    assert c["name"] == "Bob"
    assert c["whatsapp_name"] == "Bob"
    assert c["profilePic"] == "https://pps.whatsapp.net/avatar.jpg"
    assert c["lastMessage"] == "latest"
    assert c["unread"] == 1


def test_list_conversations_ordered_by_recency(db):
    _make_org(db)
    old = datetime.now(tz=timezone.utc) - timedelta(hours=2)
    new = datetime.now(tz=timezone.utc)
    svc.record_message(db, org_id=1, phone="5511111111111", body="old",
                       wa_message_id="O", sent_at=old)
    svc.record_message(db, org_id=1, phone="5522222222222", body="new",
                       wa_message_id="N", sent_at=new)
    convs = svc.list_conversations(db, org_id=1)
    assert convs[0]["phone"] == "+5522222222222"  # newest first
    assert convs[1]["phone"] == "+5511111111111"


def test_list_conversations_no_n_plus_one(db):
    """list_conversations must batch last-message lookups, not query per row."""
    from sqlalchemy import event

    _make_org(db)
    for i in range(6):
        svc.record_message(
            db, org_id=1, phone=f"55119000000{i:02d}", body=f"msg {i}",
            wa_message_id=f"NPO-{i}",
        )

    selects: list = []
    bind = db.get_bind()

    def _count(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(bind, "before_cursor_execute", _count)
    try:
        convs = svc.list_conversations(db, org_id=1)
    finally:
        event.remove(bind, "before_cursor_execute", _count)

    assert len(convs) == 6
    # 1 SELECT for the conversation+contact join, 1 for the batched last
    # messages. The old per-row last-message lookup (N+1) would be 7+.
    assert len(selects) <= 3, f"N+1 regressed: {len(selects)} SELECTs for 6 conversations"


def test_list_messages_shape_and_order(db):
    _make_org(db)
    t0 = datetime.now(tz=timezone.utc) - timedelta(minutes=5)
    t1 = datetime.now(tz=timezone.utc)
    svc.record_message(db, org_id=1, phone="5511999999999", body="first",
                       direction="incoming", wa_message_id="M-1", sent_at=t0)
    svc.record_message(db, org_id=1, phone="5511999999999", body="second",
                       direction="outgoing", wa_message_id="M-2", sent_at=t1)
    msgs = svc.list_messages(db, org_id=1, phone="5511999999999")
    assert len(msgs) == 2
    # oldest-first
    assert msgs[0]["content"] == "first"
    assert msgs[1]["content"] == "second"
    # chat.js role mapping: incoming->user, outgoing->assistant
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    # contract keys
    for key in ("id", "role", "content", "created_at", "ack", "hasMedia"):
        assert key in msgs[0], f"missing message key: {key}"


def test_list_messages_uses_sent_at_not_insert_order(db):
    _make_org(db)
    older = datetime.now(tz=timezone.utc) - timedelta(minutes=10)
    newer = datetime.now(tz=timezone.utc)
    svc.record_message(db, org_id=1, phone="5511999999999", body="newer",
                       direction="incoming", wa_message_id="ORDER-NEW", sent_at=newer)
    svc.record_message(db, org_id=1, phone="5511999999999", body="older",
                       direction="incoming", wa_message_id="ORDER-OLD", sent_at=older)

    msgs = svc.list_messages(db, org_id=1, phone="+55 11 99999-9999")

    assert [m["content"] for m in msgs] == ["older", "newer"]


def test_list_messages_unknown_phone_returns_empty(db):
    _make_org(db)
    assert svc.list_messages(db, org_id=1, phone="5500000000000") == []


def test_list_queries_reject_missing_org():
    # No DB needed: org_id=0/None short-circuits.
    assert svc.list_conversations(None, org_id=0) == []
    assert svc.list_messages(None, org_id=0, phone="x") == []


# ---------------------------------------------------------------------------
# mark_conversation_read / set_bot_enabled
# ---------------------------------------------------------------------------
def test_mark_conversation_read_resets_unread(db):
    _make_org(db)
    svc.record_message(db, org_id=1, phone="5511999999999", body="a", wa_message_id="R-1")
    svc.record_message(db, org_id=1, phone="5511999999999", body="b", wa_message_id="R-2")
    assert db.query(WaConversation).one().unread_count == 2
    assert svc.mark_conversation_read(db, org_id=1, phone="5511999999999") is True
    assert db.query(WaConversation).one().unread_count == 0


def test_set_bot_enabled_toggles_human_takeover(db):
    _make_org(db)
    svc.record_message(db, org_id=1, phone="5511999999999", body="x", wa_message_id="B-1")
    assert svc.set_bot_enabled(db, org_id=1, phone="5511999999999",
                               enabled=False, human_takeover=True) is True
    conv = db.query(WaConversation).one()
    assert conv.bot_enabled is False
    assert conv.human_takeover is True


# ---------------------------------------------------------------------------
# inbound mirror
# ---------------------------------------------------------------------------
def test_mirror_inbound_to_clone_skips_without_org(db):
    from services.whatsapp_inbound_service import mirror_inbound_to_clone
    # Ambiguous match → org_id None → mirror skipped, no row, no raise.
    assert mirror_inbound_to_clone(db, org_id=None, from_phone="5511999999999",
                                   message="hi") is None
    assert db.query(WaMessage).count() == 0


def test_mirror_inbound_to_clone_records_message(db):
    _make_org(db)
    from services.whatsapp_inbound_service import mirror_inbound_to_clone
    mid = mirror_inbound_to_clone(
        db, org_id=1, from_phone="5511999999999", message="preciso de ajuda",
        media_type="text", raw_payload={"wa_message_id": "INB-1", "pushname": "Carla"},
    )
    assert mid is not None
    msg = db.query(WaMessage).one()
    assert msg.wa_message_id == "INB-1"
    assert msg.direction == "incoming"
    contact = db.query(WaContact).one()
    assert contact.display_name == "Carla"


def test_mirror_inbound_to_clone_notifies_staff_for_new_lead(db):
    _make_org(db)
    _make_user(db)
    from services.whatsapp_inbound_service import mirror_inbound_to_clone

    mid = mirror_inbound_to_clone(
        db,
        org_id=1,
        from_phone="5511988887777",
        message="Quero agendar uma consulta",
        media_type="text",
        raw_payload={"wa_message_id": "NEW-LEAD-1", "pushname": "Marina"},
    )

    assert mid is not None
    notif = db.query(Notification).one()
    assert notif.org_id == 1
    assert notif.user_id == 1
    assert notif.notification_type == "whatsapp_new_lead"
    assert notif.severity == "warning"
    assert "Marina" in notif.title
    assert notif.action_url.startswith("/casehub/whatsapp-chat?phone=")


def test_mirror_inbound_to_clone_notifies_new_lead_once_per_contact(db):
    _make_org(db)
    _make_user(db)
    from services.whatsapp_inbound_service import mirror_inbound_to_clone

    for i in range(2):
        mirror_inbound_to_clone(
            db,
            org_id=1,
            from_phone="5511977776666",
            message=f"mensagem {i}",
            media_type="text",
            raw_payload={"wa_message_id": f"NEW-LEAD-DEDUP-{i}", "pushname": "Rafa"},
        )

    assert db.query(WaMessage).count() == 2
    assert db.query(Notification).count() == 1


# ===========================================================================
# routes/whatsapp_proxy — auth gate + transparent forwarding
# ===========================================================================
class _FakeResp:
    def __init__(self, status=200, content=b'{"ok": true}', ctype="application/json"):
        self.status_code = status
        self.content = content
        self.headers = {"content-type": ctype}


class _FakeAsyncClient:
    """Minimal stand-in for httpx.AsyncClient used by the proxy."""
    last_request = None

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def request(self, method, url, **kwargs):
        _FakeAsyncClient.last_request = {"method": method, "url": url, **kwargs}
        return _FakeResp()


@pytest.fixture
def proxy_app(monkeypatch):
    """A FastAPI app with only the proxy router + dependency overrides."""
    from fastapi import FastAPI
    import routes.whatsapp_proxy as wp
    from models import get_db
    from auth import get_current_user

    monkeypatch.setattr(wp.httpx, "AsyncClient", _FakeAsyncClient)

    app = FastAPI()
    app.include_router(wp.router)

    # Override DB so no real DB / session is needed. Must be a generator
    # dependency (FastAPI yields from it), mirroring the real models.get_db.
    def _fake_db():
        yield _DummyDB()

    app.dependency_overrides[get_db] = _fake_db
    return app, wp


class _DummyDB:
    def close(self):
        pass


def test_proxy_requires_auth(proxy_app, monkeypatch):
    from fastapi.testclient import TestClient
    app, wp = proxy_app
    # get_current_user returns None → 401.
    monkeypatch.setattr(wp, "get_current_user", lambda request, db: None)
    client = TestClient(app)
    resp = client.get("/whatsapp-api/api/status")
    assert resp.status_code == 401


def test_proxy_forwards_to_bot(proxy_app, monkeypatch):
    from fastapi.testclient import TestClient
    app, wp = proxy_app
    monkeypatch.setattr(wp, "get_current_user", lambda request, db: object())
    client = TestClient(app)
    resp = client.get("/whatsapp-api/api/qr")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    # The path was forwarded verbatim to the configured bot URL.
    fwd = _FakeAsyncClient.last_request
    assert fwd is not None
    assert fwd["method"] == "GET"
    assert fwd["url"].endswith("/api/qr")


def test_proxy_forwards_post_body(proxy_app, monkeypatch):
    from fastapi.testclient import TestClient
    app, wp = proxy_app
    monkeypatch.setattr(wp, "get_current_user", lambda request, db: object())
    client = TestClient(app)
    resp = client.post("/whatsapp-api/api/send", json={"phone": "x", "message": "hi"})
    assert resp.status_code == 200
    fwd = _FakeAsyncClient.last_request
    assert fwd["method"] == "POST"
    assert fwd["url"].endswith("/api/send")
    assert fwd["content"] is not None


# ===========================================================================
# routes/whatsapp_chat — CASEHUB_WHATSAPP_CLONE_ENABLED flag
# ===========================================================================
def test_clone_flag_off_keeps_legacy_prefix(monkeypatch):
    monkeypatch.delenv("CASEHUB_WHATSAPP_CLONE_ENABLED", raising=False)
    import routes.whatsapp_chat as wc
    wc = importlib.reload(wc)
    assert wc.whatsapp_clone_enabled() is False
    assert wc.ROUTER_PREFIX == "/whatsapp-chat"
    assert wc.router.prefix == "/whatsapp-chat"
    # No redirect router when the clone is on the legacy alias.
    assert not hasattr(wc, "pages_router")


def test_clone_flag_on_swaps_prefix_and_adds_redirect(monkeypatch):
    monkeypatch.setenv("CASEHUB_WHATSAPP_CLONE_ENABLED", "true")
    import routes.whatsapp_chat as wc
    wc = importlib.reload(wc)
    try:
        assert wc.whatsapp_clone_enabled() is True
        assert wc.ROUTER_PREFIX == "/whatsapp"
        assert wc.router.prefix == "/whatsapp"
        # Redirect router exists and targets the legacy alias.
        assert hasattr(wc, "pages_router")
        assert wc.pages_router.prefix == "/whatsapp-chat"
    finally:
        # Reload back to the safe default so test ordering stays clean.
        monkeypatch.delenv("CASEHUB_WHATSAPP_CLONE_ENABLED", raising=False)
        importlib.reload(wc)


def test_clone_flag_accepts_truthy_strings(monkeypatch):
    import routes.whatsapp_chat as wc
    for truthy in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("CASEHUB_WHATSAPP_CLONE_ENABLED", truthy)
        assert wc.whatsapp_clone_enabled() is True
    for falsy in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("CASEHUB_WHATSAPP_CLONE_ENABLED", falsy)
        assert wc.whatsapp_clone_enabled() is False
    monkeypatch.delenv("CASEHUB_WHATSAPP_CLONE_ENABLED", raising=False)
