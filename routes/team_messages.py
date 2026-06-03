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
from pathlib import Path
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


def _org_id(request: Request, user) -> int:
    oid = getattr(getattr(request, "state", None), "org_id", None)
    if oid:
        return int(oid)
    return int(getattr(user, "org_id", 0) or 0)


def _ensure_schema(db):
    """Cria as tabelas se nao existirem (idempotente). Dialect-aware: SERIAL no
    Postgres (prod/alpha), AUTOINCREMENT no SQLite (dev)."""
    bind = db.get_bind()
    dialect = bind.dialect.name if bind is not None else "sqlite"
    pk = "SERIAL PRIMARY KEY" if dialect == "postgresql" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    ts = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
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
        channels.append({
            "id": dcid,
            "name": _other_dm_name(db, dcid, user.id),
            "kind": "dm",
            "unread": _unread(db, org_id, dcid, user.id),
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
    if other <= 0 or other == user.id:
        return JSONResponse({"error": "Usuario invalido"}, status_code=400)
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
                   m.attachment_path, m.attachment_name, m.attachment_kind, m.attachment_mime
            FROM team_messages m
            LEFT JOIN users u ON u.id = m.user_id
            WHERE m.org_id = :o AND m.channel_id = :c AND m.id > :since
            ORDER BY m.id ASC
            LIMIT 200
        """),
        {"o": org_id, "c": cid, "since": int(since or 0)},
    ).fetchall()
    msgs = [{
        "id": r[0],
        "user_id": r[1],
        "body": r[2],
        "created_at": str(r[3]) if r[3] is not None else "",
        "author": r[4] or "Usuario",
        "color": r[5] or "#6D9EEB",
        "photo_url": r[6] or "",
        "mine": r[1] == user.id,
        "attachment_url": ("/uploads/" + MEDIA_KIND + "/" + os.path.basename(r[7])) if r[7] else "",
        "attachment_name": r[8] or "",
        "attachment_kind": r[9] or "",
        "attachment_mime": r[10] or "",
    } for r in rows]
    return JSONResponse({"channel_id": cid, "messages": msgs})


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
    db.execute(
        text("INSERT INTO team_messages (org_id, channel_id, user_id, body) VALUES (:o, :c, :u, :b)"),
        {"o": org_id, "c": cid, "u": user.id, "b": body},
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
    return JSONResponse({"ok": True, "id": int(new_id)})


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
    return JSONResponse({"members": [{
        "id": r[0],
        "name": r[1] or r[2] or "Usuario",
        "color": r[3] or "#6D9EEB",
        "photo_url": r[4] or "",
    } for r in rows]})


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

    db.execute(
        text("""INSERT INTO team_messages
                (org_id, channel_id, user_id, body, attachment_path, attachment_name, attachment_kind, attachment_mime)
                VALUES (:o, :c, :u, '', :ap, :an, :ak, :am)"""),
        {"o": org_id, "c": cid, "u": user.id, "ap": str(dest), "an": raw_name, "ak": kind, "am": detected[:120]},
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
