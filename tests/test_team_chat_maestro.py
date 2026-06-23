import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import text

import routes.team_messages as tm


def test_maestro_trigger_helpers_strip_mention():
    assert tm._contains_maestro_mention("@maestro revise este prazo")
    assert tm._contains_maestro_mention("UsuarioDemo, chama @Maestro nisso")
    assert not tm._contains_maestro_mention("maestro sem arroba")
    assert tm._strip_maestro_mention("@maestro revise este prazo") == "revise este prazo"
    assert "Analise a conversa" in tm._strip_maestro_mention("@maestro")


def test_team_chat_created_at_serializes_naive_database_time_as_utc():
    assert tm._utc_iso(datetime(2026, 6, 5, 3, 50, 0)) == "2026-06-05T03:50:00Z"
    assert tm._utc_iso(datetime(2026, 6, 5, 3, 50, 0, tzinfo=timezone.utc)) == "2026-06-05T03:50:00Z"


def test_team_history_for_maestro_is_channel_and_org_scoped(db):
    tm._ensure_schema(db)
    db.execute(text(
        "INSERT INTO team_channels (org_id, name, kind, created_by) VALUES (1, '#equipe', 'channel', 7)"
    ))
    cid = int(db.execute(text("SELECT MAX(id) FROM team_channels")).scalar())
    db.execute(text(
        "INSERT INTO team_channels (org_id, name, kind, created_by) VALUES (2, '#equipe', 'channel', 8)"
    ))
    other_cid = int(db.execute(text("SELECT MAX(id) FROM team_channels")).scalar())
    db.execute(text("""
        INSERT INTO team_messages (org_id, channel_id, user_id, body, actor_type, actor_label)
        VALUES
            (1, :cid, 7, 'primeira mensagem', 'user', NULL),
            (1, :cid, 7, 'resposta anterior', 'maestro', 'Maestro'),
            (2, :other, 8, 'nao pode vazar', 'user', NULL)
    """), {"cid": cid, "other": other_cid})
    db.commit()

    before_id = int(db.execute(
        text("SELECT MAX(id) + 1 FROM team_messages WHERE org_id = 1 AND channel_id = :cid"),
        {"cid": cid},
    ).scalar())

    history = tm._team_history_for_maestro(db, 1, cid, before_id)

    assert history == [
        {"role": "user", "content": "Equipe: primeira mensagem"},
        {"role": "assistant", "content": "resposta anterior"},
    ]
    assert "nao pode vazar" not in str(history)


def test_post_message_with_maestro_mention_appends_actor_response(db, monkeypatch):
    tm._ensure_schema(db)
    user = SimpleNamespace(id=7, org_id=1, name="Equipe CaseHub")
    cid = tm._ensure_default_channel(db, 1, user.id)

    async def fake_reply(db_arg, request_arg, **kwargs):
        db_arg.execute(text("""
            INSERT INTO team_messages (org_id, channel_id, user_id, body, actor_type, actor_label)
            VALUES (:o, :c, :u, 'Resposta controlada', 'maestro', 'Maestro')
        """), {"o": kwargs["org_id"], "c": kwargs["cid"], "u": user.id})
        db_arg.commit()
        return int(db_arg.execute(text("SELECT MAX(id) FROM team_messages")).scalar())

    monkeypatch.setattr(tm, "get_current_user", lambda request, db: user)
    monkeypatch.setattr(tm, "_post_maestro_reply", fake_reply)

    class Request:
        state = SimpleNamespace(org_id=1)

        async def json(self):
            return {"body": "@maestro quais proximos passos?"}

    response = asyncio.run(tm.post_message(cid, Request(), db))
    payload = json.loads(response.body)

    assert payload["ok"] is True
    assert payload["maestro_id"] > payload["id"]
    actor = db.execute(
        text("SELECT actor_type, actor_label, body FROM team_messages WHERE id = :id"),
        {"id": payload["maestro_id"]},
    ).fetchone()
    assert actor == ("maestro", "Maestro", "Resposta controlada")
