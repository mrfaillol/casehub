"""
CaseHub - Team Chat interno (chat da equipe, org-scoped + SEGURO).

Substitui o MVP inseguro routes/team_chat.py, que persistia num JSON global,
tinha auth fallback {'id': 1} e ZERO filtro de org_id (vazava mensagens entre
tenants). Aqui TUDO e' filtrado por org_id, a auth e' a real (auth.get_current_user)
e o acesso a um canal valida PERTENCIMENTO ao canal (membership), nao so' a' org.

Fase 1: canal #equipe (todos da org).
Fase 2 (este arquivo): DMs 1-a-1 (kind='dm') + lista de membros.

RED LINE de seguranca (ruling 2026-05-29 / plano frente 3 PR C): um canal 'dm'
e' privado entre 2 pessoas. get/post/read SO sao permitidos a membros explicitos
do canal — senao um usuario da mesma org leria o DM de colegas. Canal publico
('channel') da org permite auto-join de qualquer membro da org.
"""
from fastapi import APIRouter, Depends, Request, UploadFile, File
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import logging
import os
import re
import uuid

from models import get_db
from auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/team-chat", tags=["team-chat"])

MAX_BODY = 2000
DEFAULT_CHANNEL = "#equipe"

# Virtual user id of the Maestro IA inside team chat. Negative so it can never
# collide with a real users.id (always positive). Used as the author of the
# assistant's replies and as the "other member" of a Maestro DM.
MAESTRO_UID = -1

# @Maestro mention detector for the #equipe (public) channel. Matches "@maestro"
# / "@Maestro IA" / "@maestro," case-insensitively, only as a whole word so a
# stray "email@maestro.x" never triggers it. In a Maestro DM the mention is not
# required (every message there is for the Maestro); this is the trigger for the
# shared team channel ("bandeja"), where the user expects @Maestro to answer.
MAESTRO_MENTION_RE = re.compile(r"(?:^|\s)@maestro\b", re.IGNORECASE)
MAESTRO_TRIGGER_RE = MAESTRO_MENTION_RE
MAESTRO_ACTOR_TYPE = "maestro"
MAESTRO_ACTOR_LABEL = "Maestro"
MAX_MAESTRO_TEAM_HISTORY = 8

# --- Midia (Fase 3): upload de imagem/audio/arquivo no chat ---
# Reusa o storage/serve auth+tenant do routes/uploads.py (kind 'team_chat').
# Layout: uploads/org_<org_id>/team_chat/<uuid>.<ext>. Servido por
# /uploads/team_chat/<filename> com checagem de MEMBERSHIP (uploads.py:_check_team_chat).
UPLOADS_ROOT = Path(os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")).resolve()
MEDIA_KIND = "team_chat"
MAX_MEDIA_SIZE = 25 * 1024 * 1024  # 25MB
# Extensoes aceitas -> classe de midia (image|audio|file).
MEDIA_EXT = {
    ".jpg": "image", ".jpeg": "image", ".png": "image", ".gif": "image", ".webp": "image",
    ".mp3": "audio", ".ogg": "audio", ".oga": "audio", ".opus": "audio", ".m4a": "audio",
    ".wav": "audio", ".webm": "audio", ".aac": "audio",
    ".pdf": "file", ".doc": "file", ".docx": "file", ".xls": "file", ".xlsx": "file",
    ".txt": "file", ".csv": "file", ".zip": "file",
}
# MIMEs de documento aceitos (alem de image/* e audio/* e video/webm, validados por prefixo).
MEDIA_DOC_MIME = {
    "application/pdf", "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain", "text/csv", "application/zip",
}


def _dialect_name(db) -> str:
    bind = db.get_bind()
    return bind.dialect.name if bind is not None else "sqlite"


def _utc_now_sql(db) -> str:
    """SQL expression that stores a UTC wall-clock value in TIMESTAMP columns."""
    return "CURRENT_TIMESTAMP AT TIME ZONE 'UTC'" if _dialect_name(db) == "postgresql" else "CURRENT_TIMESTAMP"


def _created_at_utc_iso(value) -> str:
    """Serialize team-chat timestamps as explicit UTC ISO strings.

    team_messages.created_at is a legacy TIMESTAMP column. Existing alpha rows
    are UTC wall-clock values without tzinfo, which caused the UI to display
    22:07 when Victor sent at 19:07 BRT. Treat naive values as UTC and make the
    API contract explicit with a trailing Z.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return ""
        normalized = raw.replace(" ", "T")
        try:
            if normalized.endswith(("Z", "z")):
                dt = datetime.fromisoformat(normalized[:-1] + "+00:00")
            elif re.search(r"[+-]\d{2}:?\d{2}$", normalized):
                dt = datetime.fromisoformat(normalized)
            else:
                dt = datetime.fromisoformat(normalized)
                dt = dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return normalized if re.search(r"(?:[zZ]|[+-]\d{2}:?\d{2})$", normalized) else normalized + "Z"
    elif isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    else:
        return str(value)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_iso(value) -> str:
    return _created_at_utc_iso(value)


def _insert_team_message(db, *, org_id: int, channel_id: int, user_id: int, body: str,
                         attachment_path=None, attachment_name=None,
                         attachment_kind=None, attachment_mime=None,
                         actor_type=None, actor_label=None) -> None:
    columns = ["org_id", "channel_id", "user_id", "body", "created_at"]
    values = [":o", ":c", ":u", ":b", _utc_now_sql(db)]
    params = {"o": org_id, "c": channel_id, "u": user_id, "b": body}
    if actor_type is None and int(user_id) == MAESTRO_UID:
        actor_type = MAESTRO_ACTOR_TYPE
        actor_label = actor_label or MAESTRO_ACTOR_LABEL
    if actor_type is not None or actor_label is not None:
        columns.extend(["actor_type", "actor_label"])
        values.extend([":at", ":al"])
        params.update({"at": actor_type or "user", "al": actor_label})
    if any(v for v in (attachment_path, attachment_name, attachment_kind, attachment_mime)):
        columns.extend(["attachment_path", "attachment_name", "attachment_kind", "attachment_mime"])
        values.extend([":ap", ":an", ":ak", ":am"])
        params.update({
            "ap": attachment_path,
            "an": attachment_name,
            "ak": attachment_kind,
            "am": attachment_mime,
        })
    db.execute(text(
        f"INSERT INTO team_messages ({', '.join(columns)}) VALUES ({', '.join(values)})"
    ), params)


def _org_id(request: Request, user) -> int:
    oid = getattr(getattr(request, "state", None), "org_id", None)
    if oid:
        return int(oid)
    return int(getattr(user, "org_id", 0) or 0)


def _ensure_schema(db):
    """Cria as tabelas se nao existirem (idempotente). Dialect-aware: SERIAL no
    Postgres (prod/alpha), AUTOINCREMENT no SQLite (dev)."""
    bind = db.get_bind()
    dialect = _dialect_name(db)
    pk = "SERIAL PRIMARY KEY" if dialect == "postgresql" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    ts = f"TIMESTAMP DEFAULT ({_utc_now_sql(db)})" if dialect == "postgresql" else "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    db.execute(text(f"""
        CREATE TABLE IF NOT EXISTS team_channels (
            id {pk},
            org_id INTEGER NOT NULL,
            name VARCHAR(120) NOT NULL,
            kind VARCHAR(20) NOT NULL DEFAULT 'channel',
            created_by INTEGER,
            created_at {ts}
        )"""))
    db.execute(text(f"""
        CREATE TABLE IF NOT EXISTS team_messages (
            id {pk},
            org_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            body TEXT NOT NULL,
            created_at {ts}
        )"""))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS org_settings (
            org_id INTEGER NOT NULL,
            key VARCHAR(120) NOT NULL,
            value TEXT,
            PRIMARY KEY (org_id, key)
        )"""))
    db.execute(text(f"""
        CREATE TABLE IF NOT EXISTS team_channel_members (
            id {pk},
            org_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            last_read_message_id INTEGER DEFAULT 0,
            UNIQUE(channel_id, user_id)
        )"""))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_team_messages_chan ON team_messages (org_id, channel_id, id)"
    ))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_team_channels_org_kind ON team_channels (org_id, kind, name)"
    ))
    # Fase 3: colunas de anexo em team_messages (idempotente, dialect-aware).
    # Os nomes/DDL sao constantes internas (nunca input de usuario) -> sem SQLi.
    for _col, _ddl in (
        ("actor_type", "VARCHAR(30) DEFAULT 'user'"),
        ("actor_label", "VARCHAR(120)"),
        ("attachment_path", "VARCHAR(255)"),
        ("attachment_name", "VARCHAR(255)"),
        ("attachment_kind", "VARCHAR(20)"),
        ("attachment_mime", "VARCHAR(120)"),
    ):
        try:
            if dialect == "postgresql":
                _ex = db.execute(text(
                    "SELECT 1 FROM information_schema.columns WHERE table_name = 'team_messages' AND column_name = :c"
                ), {"c": _col}).first()
            else:
                _ex = any(r[1] == _col for r in db.execute(text("PRAGMA table_info(team_messages)")).fetchall())
            if not _ex:
                db.execute(text(f"ALTER TABLE team_messages ADD COLUMN {_col} {_ddl}"))
        except Exception:
            db.rollback()
    db.commit()


def _is_member(db, cid: int, user_id: int) -> bool:
    return db.execute(
        text("SELECT 1 FROM team_channel_members WHERE channel_id = :c AND user_id = :u"),
        {"c": cid, "u": user_id},
    ).fetchone() is not None


def _add_member(db, org_id: int, cid: int, user_id: int):
    if not _is_member(db, cid, user_id):
        db.execute(
            text("INSERT INTO team_channel_members (org_id, channel_id, user_id, last_read_message_id) VALUES (:o, :c, :u, 0)"),
            {"o": org_id, "c": cid, "u": user_id},
        )
        db.commit()


def _assert_channel_access(db, cid: int, org_id: int, user_id: int):
    """RED LINE de tenancy + privacidade. Retorna o kind do canal se o usuario
    PODE acessar; None (=> 403) caso contrario.
    - Canal nao existe / org diferente -> None.
    - kind='channel' (publico da org): qualquer membro da org entra (auto-join).
    - kind='dm' (privado): SO membros explicitos. Sem isso, um usuario da mesma
      org leria DM de colegas chutando o channel_id.
    """
    ch = db.execute(
        text("SELECT kind FROM team_channels WHERE id = :c AND org_id = :o"),
        {"c": cid, "o": org_id},
    ).fetchone()
    if not ch:
        return None
    kind = ch[0]
    if kind == "dm":
        return "dm" if _is_member(db, cid, user_id) else None
    # canal publico da org -> auto-join idempotente
    _add_member(db, org_id, cid, user_id)
    return kind


def _unread(db, org_id: int, cid: int, user_id: int) -> int:
    lr = db.execute(
        text("SELECT last_read_message_id FROM team_channel_members WHERE channel_id = :c AND user_id = :u"),
        {"c": cid, "u": user_id},
    ).fetchone()
    last_read = int(lr[0]) if lr and lr[0] is not None else 0
    return int(db.execute(
        text("SELECT COUNT(*) FROM team_messages WHERE org_id = :o AND channel_id = :c AND id > :lr AND user_id <> :u"),
        {"o": org_id, "c": cid, "lr": last_read, "u": user_id},
    ).scalar() or 0)


def _ensure_default_channel(db, org_id: int, user_id: int) -> int:
    """Garante 1 canal #equipe por org + o usuario como membro. Retorna o channel_id."""
    row = db.execute(
        text("SELECT id FROM team_channels WHERE org_id = :o AND kind = 'channel' ORDER BY id LIMIT 1"),
        {"o": org_id},
    ).fetchone()
    if row:
        cid = int(row[0])
    else:
        db.execute(
            text("INSERT INTO team_channels (org_id, name, kind, created_by) VALUES (:o, :n, 'channel', :u)"),
            {"o": org_id, "n": DEFAULT_CHANNEL, "u": user_id},
        )
        db.commit()
        cid = int(db.execute(
            text("SELECT id FROM team_channels WHERE org_id = :o AND kind = 'channel' ORDER BY id LIMIT 1"),
            {"o": org_id},
        ).fetchone()[0])
    _add_member(db, org_id, cid, user_id)
    return cid


def post_system_message_to_equipe(db, org_id: int, user_id: int, body: str) -> int:
    """Posta uma mensagem no canal #equipe da org, como `user_id`, reusando o
    mesmo schema/canal/membership do chat real (NAO duplica o sistema de chat).

    Usado por fluxos que querem "avisar no chat de equipe" (ex.: criar prazo com
    a opcao notificar_chat). Org-scoped por construcao: o channel_id e' resolvido
    a partir de org_id via _ensure_default_channel. Best-effort: nunca derruba o
    fluxo chamador — em erro, faz rollback e retorna 0.

    Retorna o id da mensagem criada (0 em caso de falha)."""
    try:
        body = str(body or "").strip()[:MAX_BODY]
        if not body:
            return 0
        _ensure_schema(db)
        cid = _ensure_default_channel(db, int(org_id), int(user_id))
        _insert_team_message(db, org_id=int(org_id), channel_id=cid, user_id=int(user_id), body=body)
        db.commit()
        new_id = db.execute(
            text("SELECT MAX(id) FROM team_messages WHERE org_id = :o AND channel_id = :c"),
            {"o": int(org_id), "c": cid},
        ).scalar() or 0
        # O autor ja "leu" a propria mensagem (nao gera badge pra ele mesmo).
        db.execute(
            text("UPDATE team_channel_members SET last_read_message_id = :m WHERE channel_id = :c AND user_id = :u"),
            {"m": new_id, "c": cid, "u": int(user_id)},
        )
        db.commit()
        return int(new_id)
    except Exception as e:  # best-effort: nunca quebra o fluxo de criar prazo
        try:
            db.rollback()
        except Exception:
            pass
        logger.error("Falha ao postar mensagem de sistema no #equipe: %s", e)
        return 0


def _dm_channel(db, org_id: int, me: int, other: int) -> int:
    """Find-or-create do canal DM entre 2 usuarios. Nome canonico dm:<min>:<max>
    (unico por par dentro da org). Garante os 2 membros."""
    a, b = (me, other) if me < other else (other, me)
    name = f"dm:{a}:{b}"
    row = db.execute(
        text("SELECT id FROM team_channels WHERE org_id = :o AND kind = 'dm' AND name = :n"),
        {"o": org_id, "n": name},
    ).fetchone()
    if row:
        cid = int(row[0])
    else:
        db.execute(
            text("INSERT INTO team_channels (org_id, name, kind, created_by) VALUES (:o, :n, 'dm', :u)"),
            {"o": org_id, "n": name, "u": me},
        )
        db.commit()
        cid = int(db.execute(
            text("SELECT id FROM team_channels WHERE org_id = :o AND kind = 'dm' AND name = :n"),
            {"o": org_id, "n": name},
        ).fetchone()[0])
    _add_member(db, org_id, cid, a)
    _add_member(db, org_id, cid, b)
    return cid


def _other_dm_name(db, cid: int, user_id: int) -> str:
    other_member = db.execute(
        text("SELECT user_id FROM team_channel_members WHERE channel_id = :c AND user_id <> :u LIMIT 1"),
        {"c": cid, "u": user_id}
    ).scalar()
    if other_member == -1:
        return "Maestro IA 🪄"
    return db.execute(
        text("""
            SELECT COALESCE(u.name, u.email, 'Usuario')
            FROM team_channel_members mm
            JOIN users u ON u.id = mm.user_id
            WHERE mm.channel_id = :c AND mm.user_id <> :u
            LIMIT 1
        """),
        {"c": cid, "u": user_id},
    ).scalar() or "DM"


def _other_dm_peer(db, cid: int, user_id: int) -> dict:
    """Retorna name, color e photo_url do peer do DM (para exibir no botão da aba)."""
    other_id = db.execute(
        text("SELECT user_id FROM team_channel_members WHERE channel_id = :c AND user_id <> :u LIMIT 1"),
        {"c": cid, "u": user_id}
    ).scalar()
    if other_id == -1:
        return {"name": "Maestro IA 🪄", "color": "#7c3aed", "photo_url": "/static/img/maestro.png"}
    row = db.execute(
        text("""
            SELECT COALESCE(u.name, u.email, 'Usuario'), COALESCE(u.color, '#6b7280'), COALESCE(u.photo_url, '')
            FROM team_channel_members mm
            JOIN users u ON u.id = mm.user_id
            WHERE mm.channel_id = :c AND mm.user_id <> :u
            LIMIT 1
        """),
        {"c": cid, "u": user_id},
    ).fetchone()
    if row:
        return {"name": row[0], "color": row[1], "photo_url": row[2]}
    return {"name": "DM", "color": "#6b7280", "photo_url": ""}


def _contains_maestro_mention(body: str) -> bool:
    return bool(MAESTRO_TRIGGER_RE.search(body or ""))


def _strip_maestro_mention(body: str) -> str:
    cleaned = MAESTRO_TRIGGER_RE.sub(" ", body or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "Analise a conversa recente e sugira o proximo passo."


def _maestro_enabled(db: Session, org_id: int) -> bool:
    try:
        row = db.execute(
            text("SELECT value FROM org_settings WHERE org_id = :oid AND key = 'maestro_enabled'"),
            {"oid": org_id},
        ).fetchone()
        if row:
            return str(row[0]).lower() in {"true", "1", "yes", "on"}
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    return True


def _team_history_for_maestro(db: Session, org_id: int, cid: int, before_id: int) -> list[dict]:
    rows = db.execute(
        text("""
            SELECT m.body,
                   COALESCE(m.actor_type, CASE WHEN m.user_id = :maestro_uid THEN :maestro_actor ELSE 'user' END) AS actor_type,
                   m.actor_label,
                   u.name
            FROM team_messages m
            LEFT JOIN users u ON u.id = m.user_id AND u.org_id = :o
            WHERE m.org_id = :o AND m.channel_id = :c AND m.id < :before_id
            ORDER BY m.id DESC
            LIMIT :limit
        """),
        {
            "o": org_id,
            "c": cid,
            "before_id": before_id,
            "limit": MAX_MAESTRO_TEAM_HISTORY,
            "maestro_uid": MAESTRO_UID,
            "maestro_actor": MAESTRO_ACTOR_TYPE,
        },
    ).fetchall()
    history = []
    for row in reversed(rows):
        body = str(row[0] or "").strip()
        if not body:
            continue
        actor_type = row[1] or "user"
        if actor_type == MAESTRO_ACTOR_TYPE:
            history.append({"role": "assistant", "content": body})
        else:
            label = row[2] or row[3] or "Equipe"
            history.append({"role": "user", "content": f"{label}: {body}"})
    return history


def _sha256_text(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8", errors="replace")).hexdigest()


def _record_team_maestro_inference(
    db: Session,
    *,
    org_id: int,
    user_id: int,
    message: str,
    response: str,
    model: str,
    provider: str,
    status: str,
) -> None:
    try:
        db.execute(text("""
            INSERT INTO maestro_inferences
                (org_id, user_id, message_sha256, response_sha256, model, provider, status)
            VALUES
                (:org_id, :user_id, :message_hash, :response_hash, :model, :provider, :status)
        """), {
            "org_id": org_id,
            "user_id": user_id,
            "message_hash": _sha256_text(message),
            "response_hash": _sha256_text(response),
            "model": model or "",
            "provider": provider or "ollama",
            "status": status or "",
        })
        db.commit()
    except Exception as exc:
        logger.debug("Team chat Maestro inference audit skipped: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass


@router.get("/channels")
async def list_channels(request: Request, db: Session = Depends(get_db)):
    """Lista os canais do usuario: #equipe + DMs de que ele participa, com nao-lidas."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)
    org_id = _org_id(request, user)
    _ensure_schema(db)
    cid = _ensure_default_channel(db, org_id, user.id)
    channels = [{"id": cid, "name": DEFAULT_CHANNEL, "kind": "channel", "unread": _unread(db, org_id, cid, user.id)}]
    dms = db.execute(
        text("""
            SELECT c.id FROM team_channels c
            JOIN team_channel_members m ON m.channel_id = c.id AND m.user_id = :u
            WHERE c.org_id = :o AND c.kind = 'dm'
            ORDER BY c.id
        """),
        {"o": org_id, "u": user.id},
    ).fetchall()
    for d in dms:
        dcid = int(d[0])
        peer = _other_dm_peer(db, dcid, user.id)
        channels.append({
            "id": dcid,
            "name": peer["name"],
            "kind": "dm",
            "unread": _unread(db, org_id, dcid, user.id),
            "peer_photo_url": peer["photo_url"],
            "peer_color": peer["color"],
        })
    return JSONResponse({"channels": channels})


@router.post("/dm")
async def open_dm(request: Request, db: Session = Depends(get_db)):
    """Abre (ou reusa) um DM 1-a-1 com outro usuario da MESMA org."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)
    org_id = _org_id(request, user)
    _ensure_schema(db)
    try:
        data = await request.json()
    except Exception:
        data = {}
    try:
        other = int((data or {}).get("user_id") or 0)
    except (TypeError, ValueError):
        other = 0
    if other == 0 or other == user.id:
        return JSONResponse({"error": "Usuario invalido"}, status_code=400)
    if other == -1:
        cid = _dm_channel(db, org_id, user.id, -1)
        return JSONResponse({"ok": True, "channel_id": cid, "name": "Maestro IA 🪄", "kind": "dm"})
    # target tem que ser da MESMA org + habilitado (impede DM cross-org / com inexistente)
    tgt = db.execute(
        text("SELECT id, name, email FROM users WHERE id = :u AND org_id = :o AND COALESCE(enabled, TRUE) = TRUE"),
        {"u": other, "o": org_id},
    ).fetchone()
    if not tgt:
        return JSONResponse({"error": "Usuario nao encontrado na sua equipe"}, status_code=404)
    cid = _dm_channel(db, org_id, user.id, other)
    return JSONResponse({"ok": True, "channel_id": cid, "name": tgt[1] or tgt[2] or "Usuario", "kind": "dm"})


@router.get("/channels/{cid}/messages")
async def get_messages(cid: int, request: Request, since: int = 0, db: Session = Depends(get_db)):
    """Mensagens do canal a partir de `since`. Org-scoped + membership (DM = privado)."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)
    org_id = _org_id(request, user)
    _ensure_schema(db)
    if _assert_channel_access(db, cid, org_id, user.id) is None:
        return JSONResponse({"error": "Sem acesso a este canal"}, status_code=403)
    rows = db.execute(
        text("""
            SELECT m.id, m.user_id, m.body, m.created_at, u.name, u.color, u.photo_url,
                   m.attachment_path, m.attachment_name, m.attachment_kind, m.attachment_mime,
                   m.actor_type, m.actor_label
            FROM team_messages m
            LEFT JOIN users u ON u.id = m.user_id
            WHERE m.org_id = :o AND m.channel_id = :c AND m.id > :since
            ORDER BY m.id ASC
            LIMIT 200
        """),
        {"o": org_id, "c": cid, "since": int(since or 0)},
    ).fetchall()
    msgs = []
    for r in rows:
        actor_type = r[11] or (MAESTRO_ACTOR_TYPE if r[1] == MAESTRO_UID else "user")
        actor_label = r[12] or ("Maestro IA 🪄" if actor_type == MAESTRO_ACTOR_TYPE else "")
        msgs.append({
            "id": r[0],
            "user_id": r[1],
            "body": r[2],
            "created_at": _created_at_utc_iso(r[3]),
            "author": actor_label or r[4] or "Usuario",
            "color": r[5] or ("#1C2447" if actor_type == MAESTRO_ACTOR_TYPE else "#6D9EEB"),
            "photo_url": r[6] or ("/static/img/maestro.png" if actor_type == MAESTRO_ACTOR_TYPE else ""),
            "mine": actor_type == "user" and r[1] == user.id,
            "actor_type": actor_type,
            "is_maestro": actor_type == MAESTRO_ACTOR_TYPE,
            "attachment_url": ("/uploads/" + MEDIA_KIND + "/" + os.path.basename(r[7])) if r[7] else "",
            "attachment_name": r[8] or "",
            "attachment_kind": r[9] or "",
            "attachment_mime": r[10] or "",
        })
    return JSONResponse({"channel_id": cid, "messages": msgs})


def _org_personality_prompt(db, org_id) -> str:
    """Org-global Maestro system_prompt override (key 'maestro_personality').

    Reused so the team-chat Maestro talks in the same firm voice the /assistente
    chat uses. Best-effort: any error -> empty string (default voice). Strictly
    org-scoped (filters by org_id)."""
    try:
        row = db.execute(
            text("SELECT value FROM org_settings WHERE org_id = :oid AND key = 'maestro_personality'"),
            {"oid": org_id},
        ).fetchone()
        if row and row[0]:
            import json as _json
            data = _json.loads(row[0])
            return str(data.get("system_prompt") or "").strip()
    except Exception:
        # Uma query best-effort que falha (ex: tabela ausente) NÃO pode deixar a
        # transação abortada, senão o SELECT seguinte (histórico) quebra e o
        # Maestro fica mudo. Rollback recupera a sessão; voz default segue.
        try:
            db.rollback()
        except Exception:
            pass
    return ""


async def _post_maestro_reply(
    db: Session,
    request: Request,
    *,
    org_id: int,
    cid: int,
    user,
    trigger_body: str,
    before_id: int,
) -> int:
    """Generate a Maestro IA reply in the same authorized channel."""
    response_text = ""
    model = ""
    provider = "ollama"
    status = ""
    try:
        if not _maestro_enabled(db, org_id):
            response_text = "Maestro esta desativado para este tenant."
            status = "disabled"
        else:
            from services.maestro_lite import MaestroLite, get_client_context, repo_aware_enabled
            from services.maestro_policy import resolve_maestro_policy
            from core.template_config import inject_org_context

            policy = resolve_maestro_policy(db, org_id)
            org_ctx = inject_org_context(request)
            org_name = org_ctx.get("org_name", "CaseHub")
            maestro = MaestroLite(org_name=org_name, ollama_url=policy.ollama_url, model=policy.model)
            provider = policy.provider

            sys_prompt = _org_personality_prompt(db, org_id)
            if sys_prompt:
                maestro.system_prompt = sys_prompt

            clean_message = _strip_maestro_mention(trigger_body)
            firm_context = maestro.get_firm_context(db, org_id)
            cc_row = db.execute(
                text("SELECT value FROM org_settings WHERE org_id = :oid AND key = 'maestro_context'"),
                {"oid": org_id},
            ).fetchone()
            full_context = firm_context
            if cc_row and cc_row[0]:
                full_context += f"\n\nInformações adicionais do escritório:\n{cc_row[0]}"
            full_context += (
                "\n\nContexto operacional: voce esta respondendo dentro do chat de equipe do CaseHub. "
                "Seja direto, proponha proximas acoes e nao execute mudancas sem comando explicito do usuario."
            )
            full_context += get_client_context(db, org_id, clean_message)

            repo_context = None
            try:
                if repo_aware_enabled():
                    from services.maestro_repo_index import retrieve_repo_context
                    repo_context = retrieve_repo_context(clean_message)
            except Exception as exc:
                logger.warning("team-chat repo-aware retrieval failed: %s", exc)

            ai_result = await maestro.chat(
                clean_message,
                context=full_context,
                history=_team_history_for_maestro(db, org_id, cid, before_id),
                repo_context=repo_context,
            )
            response_text = ai_result.get("response") or "Desculpe, tive um problema ao processar sua solicitação."
            model = ai_result.get("model", "")
            status = ai_result.get("status", "")

        _insert_team_message(
            db,
            org_id=org_id,
            channel_id=cid,
            user_id=MAESTRO_UID,
            body=response_text[:MAX_BODY],
            actor_type=MAESTRO_ACTOR_TYPE,
            actor_label=MAESTRO_ACTOR_LABEL,
        )
        db.commit()
        new_msg_id = int(db.execute(
            text("SELECT MAX(id) FROM team_messages WHERE org_id = :o AND channel_id = :c"),
            {"o": org_id, "c": cid},
        ).scalar() or 0)
        db.execute(
            text("UPDATE team_channel_members SET last_read_message_id = :m WHERE channel_id = :c AND user_id = :mu"),
            {"m": new_msg_id, "c": cid, "mu": MAESTRO_UID},
        )
        db.commit()
        _record_team_maestro_inference(
            db,
            org_id=org_id,
            user_id=int(getattr(user, "id", 0) or 0),
            message=trigger_body,
            response=response_text,
            model=model,
            provider=provider,
            status=status,
        )
        return new_msg_id
    except Exception as e:
        logger.error("Erro ao chamar o Maestro IA no Team Chat: %s", e)
        try:
            _insert_team_message(
                db,
                org_id=org_id,
                channel_id=cid,
                user_id=MAESTRO_UID,
                body="*(Maestro IA indisponível no momento. Por favor, verifique se o serviço local do Ollama está ativo.)*",
                actor_type=MAESTRO_ACTOR_TYPE,
                actor_label=MAESTRO_ACTOR_LABEL,
            )
            db.commit()
            return int(db.execute(
                text("SELECT MAX(id) FROM team_messages WHERE org_id = :o AND channel_id = :c"),
                {"o": org_id, "c": cid},
            ).scalar() or 0)
        except Exception:
            db.rollback()
        return 0


@router.post("/channels/{cid}/messages")
async def post_message(cid: int, request: Request, db: Session = Depends(get_db)):
    """Envia mensagem no canal. Org-scoped + membership (DM = privado)."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)
    org_id = _org_id(request, user)
    _ensure_schema(db)
    if _assert_channel_access(db, cid, org_id, user.id) is None:
        return JSONResponse({"error": "Sem acesso a este canal"}, status_code=403)
    try:
        data = await request.json()
    except Exception:
        data = {}
    body = str((data or {}).get("body") or "").strip()[:MAX_BODY]
    if not body:
        return JSONResponse({"error": "Mensagem vazia"}, status_code=400)
    _insert_team_message(db, org_id=org_id, channel_id=cid, user_id=user.id, body=body)
    db.commit()
    new_id = db.execute(
        text("SELECT MAX(id) FROM team_messages WHERE org_id = :o AND channel_id = :c"),
        {"o": org_id, "c": cid},
    ).scalar() or 0
    db.execute(
        text("UPDATE team_channel_members SET last_read_message_id = :m WHERE channel_id = :c AND user_id = :u"),
        {"m": new_id, "c": cid, "u": user.id},
    )
    db.commit()

    # --- Roteamento para o Maestro IA (org-scoped, reusa maestro_lite) ---
    # Dispara em DOIS casos:
    #   (1) DM com o Maestro: o outro membro do canal é a conta virtual (-1) —
    #       toda mensagem ali é para o Maestro (mantém o comportamento antigo).
    #   (2) Menção @Maestro no canal de equipe (#equipe / "bandeja"): o usuário
    #       escreve "@Maestro ..." e espera resposta. Antes isso era IGNORADO —
    #       este é o bug "Maestro não responde no chat de equipe". O autor já é
    #       membro do canal (passou pelo _assert_channel_access acima), então
    #       não há furo de tenancy: a resposta cai no mesmo canal/org.
    other_member = db.execute(
        text("SELECT user_id FROM team_channel_members WHERE channel_id = :c AND user_id <> :u LIMIT 1"),
        {"c": cid, "u": user.id}
    ).scalar()

    is_maestro_dm = (other_member == MAESTRO_UID)
    is_mention = bool(MAESTRO_MENTION_RE.search(body or "")) and user.id != MAESTRO_UID
    maestro_id = 0
    if is_maestro_dm or is_mention:
        maestro_id = await _post_maestro_reply(
            db,
            request,
            org_id=org_id,
            cid=cid,
            user=user,
            trigger_body=body,
            before_id=int(new_id),
        )

    return JSONResponse({"ok": True, "id": int(new_id), "maestro_id": int(maestro_id or 0)})


@router.post("/channels/{cid}/read")
async def mark_read(cid: int, request: Request, db: Session = Depends(get_db)):
    """Marca o canal como lido ate a ultima mensagem (zera o badge). Membership obrigatoria."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)
    org_id = _org_id(request, user)
    _ensure_schema(db)
    if _assert_channel_access(db, cid, org_id, user.id) is None:
        return JSONResponse({"error": "Sem acesso a este canal"}, status_code=403)
    last_id = db.execute(
        text("SELECT COALESCE(MAX(id), 0) FROM team_messages WHERE org_id = :o AND channel_id = :c"),
        {"o": org_id, "c": cid},
    ).scalar() or 0
    db.execute(
        text("UPDATE team_channel_members SET last_read_message_id = :m WHERE channel_id = :c AND user_id = :u"),
        {"m": last_id, "c": cid, "u": user.id},
    )
    db.commit()
    return JSONResponse({"ok": True, "last_read": int(last_id)})


@router.get("/members")
async def members(request: Request, db: Session = Depends(get_db)):
    """Lista os usuarios da org (para a lista de membros / iniciar DM). Exclui o proprio."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)
    org_id = _org_id(request, user)
    rows = db.execute(
        text("SELECT id, name, email, color, photo_url FROM users WHERE org_id = :o AND COALESCE(enabled, TRUE) = TRUE AND id <> :me ORDER BY name"),
        {"o": org_id, "me": user.id},
    ).fetchall()
    members_list = [{
        "id": r[0],
        "name": r[1] or r[2] or "Usuario",
        "color": r[3] or "#6D9EEB",
        "photo_url": r[4] or "",
    } for r in rows]
    # Injetar o assistente como membro selecionável (Onda de melhorias/Maestro Team Chat)
    members_list.insert(0, {
        "id": -1,
        "name": "Maestro IA 🪄",
        "color": "#1C2447",
        "photo_url": "/static/img/maestro.png",
    })
    return JSONResponse({"members": members_list})


@router.post("/channels/{cid}/upload")
async def upload_media(cid: int, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Anexa imagem/audio/arquivo num canal. MESMA membership do texto (DM = privado).
    Valida nome (anti path-traversal) + extensao (whitelist) + conteudo (magic sniff) +
    tamanho (25MB). Salva em uploads/org_<org>/team_chat/<uuid>.<ext> e cria a mensagem."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)
    org_id = _org_id(request, user)
    _ensure_schema(db)
    if _assert_channel_access(db, cid, org_id, user.id) is None:
        return JSONResponse({"error": "Sem acesso a este canal"}, status_code=403)

    raw_name = os.path.basename(file.filename or "arquivo")
    raw_name = re.sub(r"[^\w\s\-\.]", "_", raw_name)[:120]
    if not raw_name or ".." in raw_name or "/" in raw_name or "\\" in raw_name:
        return JSONResponse({"error": "Nome de arquivo invalido"}, status_code=400)
    ext = os.path.splitext(raw_name)[1].lower()
    kind = MEDIA_EXT.get(ext)
    if not kind:
        return JSONResponse({"error": "Tipo de arquivo nao permitido"}, status_code=400)

    content = await file.read()
    if not content:
        return JSONResponse({"error": "Arquivo vazio"}, status_code=400)
    if len(content) > MAX_MEDIA_SIZE:
        return JSONResponse({"error": "Arquivo muito grande (max 25MB)"}, status_code=413)

    # Sniff de conteudo: a extensao pode mentir. image/* e audio/* por prefixo, docs por allowlist.
    try:
        import magic
        detected = magic.from_buffer(content[:4096], mime=True) or ""
        _allowed = (detected.startswith(("image/", "audio/")) or detected == "video/webm" or detected in MEDIA_DOC_MIME)
        # Bloqueia SVG explicitamente (XSS defense-in-depth — Sentinela 2026-05-29-team-chat-media).
        if (not _allowed) or detected == "image/svg+xml":
            return JSONResponse({"error": "Conteudo do arquivo nao permitido"}, status_code=400)
    except ImportError:
        detected = (file.content_type or "application/octet-stream")[:120]

    # Path seguro: org_id e int, MEDIA_KIND e constante, nome = uuid -> sem traversal.
    dest_dir = (UPLOADS_ROOT / f"org_{int(org_id)}" / MEDIA_KIND)
    try:
        dest_dir.resolve().relative_to(UPLOADS_ROOT)
    except (ValueError, OSError):
        return JSONResponse({"error": "Caminho invalido"}, status_code=400)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid.uuid4().hex}{ext}"
    dest = dest_dir / stored
    with open(dest, "wb") as fh:
        fh.write(content)

    _insert_team_message(
        db,
        org_id=org_id,
        channel_id=cid,
        user_id=user.id,
        body="",
        attachment_path=str(dest),
        attachment_name=raw_name,
        attachment_kind=kind,
        attachment_mime=detected[:120],
    )
    db.commit()
    new_id = db.execute(
        text("SELECT MAX(id) FROM team_messages WHERE org_id = :o AND channel_id = :c"),
        {"o": org_id, "c": cid},
    ).scalar() or 0
    db.execute(
        text("UPDATE team_channel_members SET last_read_message_id = :m WHERE channel_id = :c AND user_id = :u"),
        {"m": new_id, "c": cid, "u": user.id},
    )
    db.commit()
    return JSONResponse({
        "ok": True, "id": int(new_id),
        "attachment_url": "/uploads/" + MEDIA_KIND + "/" + stored,
        "attachment_kind": kind, "attachment_name": raw_name,
    })
