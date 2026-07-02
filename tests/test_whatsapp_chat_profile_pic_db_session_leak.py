"""Regression test for the DB-session-leak-across-slow-await bug class
(same incident class as tests/test_whatsapp_crm_ai_db_session_leak.py).

Root cause: routes/whatsapp_chat.py's profile-picture proxy endpoints
(`profile_pic_proxy`, `profile_pics_batch_proxy`, `profile_photo_proxy`) ran
`get_current_user(request, db)` — a `SELECT ... FROM users ...` through the
request's SQLAlchemy session — and then `await`-ed a slow external HTTP call
(WhatsApp-bot proxy; WhatsApp CDN photo fetch) WITHOUT releasing that session
first. Because the session's implicit transaction had already touched
`users`, it sat "idle in transaction" for the whole external round-trip,
holding a lock on `users` — which every authenticated request touches via
get_current_user. Under a slow/restarting whatsapp-bot container this can
queue behind a concurrent schema-ensure ALTER TABLE and take the whole site
down.

These tests assert the fix by ordering: the DB session must be `.close()`d
before the (mocked) external call is awaited.
"""
import asyncio
import json

import pytest

import routes.whatsapp_chat as wchat
from models.tenant import Organization
from models.whatsapp_clone import WaContact

_ORG_ID = 502


class _Req:
    """Minimal Request stub: tenant org_id on .state, no cookies needed."""

    def __init__(self, org_id):
        self.state = type("S", (), {"org_id": org_id})()
        self.cookies = {}

    async def json(self):
        return {}


def _body(resp):
    return json.loads(resp.body)


@pytest.fixture()
def seeded_contact(db):
    db.add(Organization(id=_ORG_ID, uuid="u-chat-leak", name="Org Chat Leak", slug="org-chat-leak"))
    db.flush()
    db.add(WaContact(org_id=_ORG_ID, phone="+5511999990001", display_name="Cliente Teste"))
    db.commit()
    return db


def _spy_on_close(session, order, label="db.close"):
    """Wrap session.close so tests can assert call order vs. the bot call."""
    original_close = session.close

    def _spy(*args, **kwargs):
        order.append(label)
        return original_close(*args, **kwargs)

    session.close = _spy
    return session


@pytest.fixture()
def mock_auth(monkeypatch):
    user = type("U", (), {"org_id": _ORG_ID, "organization_id": _ORG_ID})()
    monkeypatch.setattr(wchat, "get_current_user", lambda req, s: user)
    return user


class _FakeBotResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _fake_bot_client_factory(order, payload):
    class _FakeBotClient:
        async def get(self, url, timeout=None, headers=None):
            order.append("bot_call")
            return _FakeBotResponse(payload)

        async def post(self, url, json=None, timeout=None, headers=None):
            order.append("bot_call")
            return _FakeBotResponse(payload)

    return _FakeBotClient()


def test_profile_pic_proxy_closes_db_before_bot_call(seeded_contact, monkeypatch, mock_auth):
    """GET /api/profile-pic/{phone} — hit whenever a WhatsApp avatar is
    missing from cache; must not hold `users` locked across the bot call."""
    db = seeded_contact
    order = []
    _spy_on_close(db, order)
    payload = {"url": "https://pps.whatsapp.net/v/t1/abc.jpg"}
    monkeypatch.setattr(wchat, "get_bot_client", lambda: _fake_bot_client_factory(order, payload))

    resp = asyncio.run(wchat.profile_pic_proxy(phone="+5511999990001", request=_Req(_ORG_ID), db=db))
    payload_out = _body(resp)

    assert order == ["db.close", "bot_call"], (
        "profile_pic_proxy must release its DB session before awaiting the "
        "WhatsApp-bot HTTP call, or a slow/stuck bot leaves an "
        "idle-in-transaction Postgres session holding a lock on `users`."
    )
    assert payload_out["phone"] == "+5511999990001"
    assert payload_out["url"]  # proxied URL was produced


def test_profile_pics_batch_proxy_closes_db_before_bot_call(seeded_contact, monkeypatch, mock_auth):
    """POST /api/profile-pics — the WhatsApp chat UI polls this in a loop for
    every visible conversation."""
    db = seeded_contact
    order = []
    _spy_on_close(db, order)
    payload = {
        "profiles": [
            {"phone": "+5511999990001", "url": "https://pps.whatsapp.net/v/t1/abc.jpg"},
        ]
    }
    monkeypatch.setattr(wchat, "get_bot_client", lambda: _fake_bot_client_factory(order, payload))

    resp = asyncio.run(wchat.profile_pics_batch_proxy(request=_Req(_ORG_ID), db=db))
    payload_out = _body(resp)

    assert order == ["db.close", "bot_call"], (
        "profile_pics_batch_proxy must release its DB session before "
        "awaiting the WhatsApp-bot HTTP call."
    )
    assert payload_out.get("updated") == 1


def test_profile_photo_proxy_closes_db_before_fetch(seeded_contact, monkeypatch, mock_auth):
    """GET /api/profile-photo/{phone} — serves the cached avatar bytes;
    must release DB before the (slow) CDN image fetch."""
    db = seeded_contact
    order = []
    _spy_on_close(db, order)

    # Force a cache-miss on the first fetch so the fresh-url refresh path
    # (which mutates contact state) also gets exercised.
    async def _fake_fetch_bytes(url):
        order.append("photo_fetch")
        if url == "https://pps.whatsapp.net/v/t1/fresh.jpg":
            return b"bytes", "image/jpeg"
        return None

    async def _fake_fetch_fresh_url(phone_key, request):
        order.append("bot_refresh_call")
        return "https://pps.whatsapp.net/v/t1/fresh.jpg"

    monkeypatch.setattr(wchat, "_fetch_profile_photo_bytes", _fake_fetch_bytes)
    monkeypatch.setattr(wchat, "_fetch_fresh_profile_pic_url", _fake_fetch_fresh_url)

    # No cached URL yet -> _fetch_profile_photo_bytes(url) branch is skipped,
    # straight to the refresh path.
    resp = asyncio.run(wchat.profile_photo_proxy(phone="+5511999990001", request=_Req(_ORG_ID), db=db))

    assert "db.close" in order
    close_index = order.index("db.close")
    assert all(
        order.index(call) > close_index
        for call in ("bot_refresh_call", "photo_fetch")
        if call in order
    ), "db.close() must happen before any external fetch, not after"
    assert resp.status_code == 200
    assert resp.body == b"bytes"

    # The refreshed URL was persisted via a fresh query+update (not a stale
    # ORM-object mutation on the now-detached `contact` instance).
    updated = db.query(WaContact).filter(WaContact.phone == "+5511999990001").first()
    assert updated.profile_pic_url == "https://pps.whatsapp.net/v/t1/fresh.jpg"
