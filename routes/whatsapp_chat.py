"""
CaseHub - WhatsApp Chat Interface (web.whatsapp.com clone)
Full WhatsApp-style chat interface with bot control.

Routing / the CASEHUB_WHATSAPP_CLONE_ENABLED flag
-------------------------------------------------
This router is the WhatsApp Web *clone*. The legacy Lite dashboard lives in
routes/whatsapp_lite.py and also wants the /whatsapp prefix — only one router
can own a prefix root, so the swap is gated behind a config flag with a
conservative default:

  * flag OFF (default): clone mounts at /whatsapp-chat; whatsapp_lite keeps
    /whatsapp (old dashboard). Nothing changes vs. today — safe.
  * flag ON: clone mounts at /whatsapp and owns the root; the old dashboard is
    served by THIS router at /whatsapp/dashboard; /whatsapp-chat 301-redirects
    to /whatsapp.

Flipping the flag in prod is a deploy-topology change → requires a Council
ruling (see plan §Governança). This module only builds the mechanism; the
default is OFF so merging it is inert.

Flag source: env var CASEHUB_WHATSAPP_CLONE_ENABLED ("1"/"true"/"yes"/"on").
Read via os.getenv so config.py (owned by another workstream) is untouched.

/api/conversations and /api/messages/{phone} are PERSISTENCE-BACKED (wa_* tables
via services.whatsapp_clone_service). /api/status, /api/qr, /api/send and
/api/bot-control still proxy the bot. The JSON response shapes are unchanged —
static/js/chat.js depends on them.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, List
import base64
import binascii
import logging
import os
import re
import httpx
import json
from urllib.parse import quote, urlparse

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, Request, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy import or_, text

from models import get_db, Client
from auth import get_current_user
from middleware.permissions import has_permission
from models.tenant import tenant_query
from i18n import get_translations
from services.moskit import moskit_service
from services import whatsapp_clone_service
from services.whatsapp_bot_client import get_bot_client
from config import settings
from core.template_config import templates, PREFIX, inject_org_context

# WhatsApp Bot server URL
WHATSAPP_BOT_URL = settings.WHATSAPP_BOT_URL


def _bot_headers(request: Optional[Request]) -> dict:
    """Build HTTP headers for direct bot calls (bypassing whatsapp_proxy).

    Multi-session per-tenant (F29, 2026-05-27): every direct call to the bot
    must carry X-Org-Id so the bot's WhatsAppManager dispatches to the right
    tenant's whatsapp-web.js session. The browser does NOT send this header —
    TenantMiddleware put the resolved tenant on request.state.org_id and we
    surface it here. Missing tenant context -> empty dict (bot falls back to
    CASEHUB_DEFAULT_ORG_ID).
    """
    if request is None:
        return {}
    org_id = getattr(getattr(request, "state", None), "org_id", None)
    if org_id is None:
        return {}
    return {"X-Org-Id": str(org_id)}


def whatsapp_clone_enabled() -> bool:
    """True when the clone should own the /whatsapp root (default: False).

    Conservative default — flipping this in prod needs a Council ruling.
    """
    raw = os.getenv("CASEHUB_WHATSAPP_CLONE_ENABLED", "")
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


# The clone owns /whatsapp only when the flag is ON; otherwise it stays on the
# legacy /whatsapp-chat alias so whatsapp_lite keeps the /whatsapp dashboard.
_CLONE_ENABLED = whatsapp_clone_enabled()
ROUTER_PREFIX = "/whatsapp" if _CLONE_ENABLED else "/whatsapp-chat"

router = APIRouter(prefix=ROUTER_PREFIX, tags=["whatsapp-chat"])


# Cache-bust dos assets do clone. chat.html carregava chat.js / *.css sem
# versionamento — apos um deploy o browser servia a versao velha do cache
# (sintoma: front preso em "Connecting..."/"Carregando..."). _ASSET_V e o
# maior mtime entre os assets; muda a cada deploy que toca esses arquivos.
def _asset_version() -> str:
    mtimes = []
    for p in (
        "static/js/chat.js",
        "static/js/whatsapp-crm.js",
        "static/css/templates/whatsapp-chat.css",
        "static/css/templates/whatsapp-crm.css",
    ):
        try:
            mtimes.append(os.path.getmtime(p))
        except OSError:
            pass
    return str(int(max(mtimes))) if mtimes else "0"


_ASSET_V = _asset_version()


def _request_org_id(request: Request) -> Optional[int]:
    """Resolve the tenant org_id from request state (set by tenancy middleware)."""
    return getattr(getattr(request, "state", None), "org_id", None)


def _failure_status_for_send(result: dict) -> int:
    """HTTP status for a failed operator send."""
    err = str((result or {}).get("error") or "").lower()
    if any(token in err for token in (
        "not ready", "disconnected", "awaiting_scan", "qr", "session",
        "not connected", "client closed", "connection",
    )):
        return 503
    return 502


def _audit_outgoing_send(
    db: Session,
    request: Request,
    actor_user,
    message_row,
    phone: str,
    wa_message_id: Optional[str],
    *,
    kind: str = "text",
) -> None:
    """Best-effort audit trail for human WhatsApp sends.

    The message body stays out of audit_log; the conversation content already
    lives in wa_messages. This gives compliance user/org attribution without
    duplicating privileged client communications in the audit table.
    """
    if actor_user is None:
        return
    try:
        ip_address = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if not ip_address and getattr(request, "client", None):
            ip_address = request.client.host
        user_agent = request.headers.get("user-agent", "")[:500]
        details = {
            "phone": whatsapp_clone_service.normalize_phone(phone) or phone,
            "wa_message_id": wa_message_id,
            "kind": kind,
        }
        db.execute(text("""
            INSERT INTO audit_log (
                action, entity_type, entity_id, user_id, user_email,
                description, details, ip_address, user_agent, org_id, created_at
            )
            VALUES (
                :action, :entity_type, :entity_id, :user_id, :user_email,
                :description, :details, :ip_address, :user_agent, :org_id,
                CURRENT_TIMESTAMP
            )
        """), {
            "action": "whatsapp_send",
            "entity_type": "wa_message",
            "entity_id": getattr(message_row, "id", None),
            "user_id": getattr(actor_user, "id", None),
            "user_email": getattr(actor_user, "email", None),
            "description": "WhatsApp message sent by CaseHub user",
            "details": json.dumps(details),
            "ip_address": ip_address or None,
            "user_agent": user_agent or None,
            "org_id": _request_org_id(request),
        })
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("WhatsApp send audit skipped: %s", e)
        try:
            db.rollback()
        except Exception:
            pass


def get_context(request: Request, db: Session, **kwargs):
    """Build template context."""
    product_state = getattr(getattr(request, "app", None), "state", None)
    lang = request.cookies.get("lang") or ("pt" if product_state and getattr(product_state, "product", None) == "lite" else "en")
    user = get_current_user(request, db)
    org_ctx = inject_org_context(request, user=user)
    return {
        "request": request,
        "PREFIX": PREFIX,
        "lang": lang,
        "t": get_translations(lang),
        "user": user,
        **org_ctx,
        **kwargs
    }


async def get_bot_conversations(request: Optional[Request] = None):
    """Fetch conversations from WhatsApp bot (tenant-aware)."""
    try:
        client = get_bot_client()
        response = await client.get(
            f"{WHATSAPP_BOT_URL}/api/conversations",
            timeout=10.0,
            headers=_bot_headers(request),
            params={"profilePics": "1"},
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logger.error("Error fetching conversations: %s", e)
    return []


async def get_bot_messages(phone: str, limit: int = 100, request: Optional[Request] = None):
    """Fetch messages for a phone from WhatsApp bot (tenant-aware)."""
    try:
        client = get_bot_client()
        response = await client.get(
            f"{WHATSAPP_BOT_URL}/api/messages/{phone}",
            params={"limit": limit},
            timeout=10.0,
            headers=_bot_headers(request),
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logger.error("Error fetching messages: %s", e)
    return []


def _coerce_history_limit(value, default: int = 200) -> int:
    try:
        n = int(value if value is not None else default)
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, 200))


def _parse_bot_message_datetime(value) -> Optional[datetime]:
    """Parse whatsapp-web.js payload timestamps into aware UTC datetimes."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 10_000_000_000:
            ts = ts / 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    raw = str(value).strip()
    if not raw:
        return None
    if raw.isdigit():
        return _parse_bot_message_datetime(int(raw))
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _message_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in (
        "1", "true", "yes", "out", "outgoing", "assistant",
    )


def _bot_message_id(data: dict) -> Optional[str]:
    raw = data.get("wa_message_id") or data.get("wid") or data.get("id")
    raw = str(raw).strip() if raw is not None else ""
    return raw or None


def _bot_message_status(data: dict) -> str:
    status = str(data.get("status") or "").strip().lower()
    if status in ("pending", "sent", "delivered", "read", "played", "failed"):
        return status
    from models.whatsapp_clone import WaMessage
    return WaMessage.status_from_ack(data.get("ack"))


def _persist_bot_history_message(db: Session, *, org_id: int, phone: str, data: dict):
    role = str(data.get("role") or "").strip().lower()
    direction = str(data.get("direction") or "").strip().lower()
    from_me = (
        _message_bool(data.get("from_me"))
        or _message_bool(data.get("fromMe"))
        or role == "assistant"
        or direction in ("out", "outgoing")
    )
    content = (
        data.get("content")
        or data.get("body")
        or data.get("message")
        or data.get("caption")
        or ""
    )
    media_type = (
        data.get("media_type")
        or data.get("type")
        or ("text" if not data.get("hasMedia") else "document")
    )
    sent_at = _parse_bot_message_datetime(
        data.get("sent_at") or data.get("created_at") or data.get("timestamp")
    )
    return whatsapp_clone_service.record_message(
        db,
        org_id=org_id,
        phone=data.get("phone") or phone,
        body=content,
        direction="outgoing" if from_me else "incoming",
        wa_message_id=_bot_message_id(data),
        media_type=media_type or "text",
        media_url=data.get("media_url") or data.get("mediaUrl"),
        media_mime=data.get("mimetype") or data.get("media_mime") or data.get("mimeType"),
        media_filename=data.get("filename") or data.get("media_filename"),
        status=_bot_message_status(data),
        from_me=from_me,
        author_phone=data.get("author_phone") or data.get("author") or data.get("phone") or phone,
        sent_at=sent_at,
        increment_unread=False,
        commit=False,
    )


async def get_lead_info(phone: str, request: Optional[Request] = None):
    """Fetch lead info from WhatsApp bot (tenant-aware)."""
    try:
        client = get_bot_client()
        response = await client.get(
            f"{WHATSAPP_BOT_URL}/api/lead/{phone}",
            timeout=10.0,
            headers=_bot_headers(request),
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logger.error("Error fetching lead: %s", e)
    return None


async def send_message_via_bot(
    phone: str,
    message: str,
    from_human: bool = False,
    reply_to_wa_message_id: Optional[str] = None,
    request: Optional[Request] = None,
):
    """Envia mensagem pelo bot WhatsApp.

    A rota do bot e POST /api/send-message (services/whatsapp-bot/routes/health.js)
    e responde {ok, messageId}. Antes apontava para /api/send (inexistente) — o
    bot devolvia 404 e o envio falhava silenciosamente. Retorno normalizado:
    {success, ok, messageId, error}.
    """
    try:
        client = get_bot_client()
        response = await client.post(
            f"{WHATSAPP_BOT_URL}/api/send-message",
            json={
                "phone": phone,
                "message": message,
                "fromHuman": from_human,
                "reply_to_wa_message_id": reply_to_wa_message_id,
            },
            timeout=30.0,
            headers=_bot_headers(request),
        )
        data = {}
        try:
            data = response.json()
        except ValueError:
            data = {}
        ok = bool(data.get("ok") or data.get("success")) and response.status_code < 400
        return {
            "success": ok,
            "ok": ok,
            "messageId": data.get("messageId"),
            "error": None if ok else (data.get("error") or f"bot HTTP {response.status_code}"),
        }
    except Exception as e:
        logger.error("Error sending message: %s", e)
        return {"success": False, "ok": False, "messageId": None, "error": str(e)}


def _persist_outgoing(
    db: Session,
    request: Request,
    phone: str,
    message: str,
    result: dict,
    reply_to_message_id: Optional[int] = None,
    actor_user=None,
    sent_by_user_id: Optional[int] = None,
):
    """Grava em wa_messages a mensagem que o operador acabou de enviar.

    O bot so escuta o evento `message` (entrada) e nao ecoa as saidas — sem
    isto a mensagem enviada some ao recarregar e nunca recebe ticks.
    Nao-fatal: uma falha de persistencia nao pode quebrar o envio.
    """
    if isinstance(result, dict) and result.get("success") is False:
        return
    try:
        org_id = _request_org_id(request)
        if not org_id:
            return
        wa_mid = None
        if isinstance(result, dict):
            wa_mid = result.get("messageId") or result.get("id") or result.get("wa_message_id")
        msg = whatsapp_clone_service.record_message(
            db,
            org_id=org_id,
            phone=phone,
            body=message,
            direction="outgoing",
            wa_message_id=wa_mid,
            status="sent",
            reply_to_message_id=reply_to_message_id,
            sent_by_user_id=sent_by_user_id,
        )
        _audit_outgoing_send(db, request, actor_user, msg, phone, wa_mid, kind="text")
    except Exception as e:
        logger.warning("Falha ao persistir mensagem enviada para %s: %s", phone, e)
        try:
            db.rollback()
        except Exception:
            pass


def _media_type_from_mime(mime: str) -> str:
    """Coarse media_type bucket for wa_messages from a MIME type."""
    m = (mime or "").split(";")[0].strip().lower()
    if m.startswith("image/"):
        return "image"
    if m.startswith("video/"):
        return "video"
    if m.startswith("audio/"):
        return "audio"
    return "document"


def _clone_media_url(media_file: Optional[str]) -> Optional[str]:
    """Public, auth-gated path the clone uses to fetch a media binary.

    Absolute from the domain root so the <img>/<video>/<audio> src resolves
    regardless of the current page. Served by GET /api/media/{filename}.
    """
    if not media_file:
        return None
    return f"{PREFIX}{ROUTER_PREFIX}/api/media/{media_file}"


def _persist_outgoing_media(
    db: Session, request: Request, phone: str, caption: str,
    result: dict, mime: str, filename: Optional[str], actor_user=None,
):
    """Grava em wa_messages a midia que o operador acabou de enviar.

    Espelha _persist_outgoing para o caso de midia: o balao de saida precisa
    da media_url para o clone renderizar o preview. Nao-fatal.
    """
    try:
        org_id = _request_org_id(request)
        if not org_id:
            return
        media_file = None
        wa_mid = None
        if isinstance(result, dict):
            media_file = (
                result.get("media_file")
                or result.get("mediaFile")
                or result.get("filename")
            )
            wa_mid = result.get("messageId") or result.get("id") or result.get("wa_message_id")
        msg = whatsapp_clone_service.record_message(
            db,
            org_id=org_id,
            phone=phone,
            body=caption or "",
            direction="outgoing",
            wa_message_id=wa_mid,
            media_type=_media_type_from_mime(mime),
            media_url=_clone_media_url(media_file),
            media_mime=(mime or "").split(";")[0].strip() or None,
            media_filename=filename or None,
            status="sent",
        )
        _audit_outgoing_send(db, request, actor_user, msg, phone, wa_mid, kind="media")
    except Exception as e:
        logger.warning("Falha ao persistir midia enviada para %s: %s", phone, e)
        try:
            db.rollback()
        except Exception:
            pass


# Path-traversal guard da rota /api/media: so um nome de arquivo simples.
_MEDIA_FILENAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


async def set_bot_control(phone: str, bot_enabled: bool, request: Optional[Request] = None):
    """Enable/disable bot for a conversation (tenant-aware)."""
    try:
        client = get_bot_client()
        response = await client.post(
            f"{WHATSAPP_BOT_URL}/api/bot-control",
            json={
                "phone": phone,
                "botEnabled": bot_enabled
            },
            timeout=10.0,
            headers=_bot_headers(request),
        )
        return response.json()
    except Exception as e:
        logger.error("Error setting bot control: %s", e)
        return {"success": False, "error": str(e)}


async def get_bot_status(request: Optional[Request] = None):
    """Get WhatsApp bot connection status (tenant-aware)."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            headers = _bot_headers(request)
            response = await client.get(f"{WHATSAPP_BOT_URL}/api/status", headers=headers)
            if response.status_code == 404:
                response = await client.get(f"{WHATSAPP_BOT_URL}/health", headers=headers)
            response.raise_for_status()
            data = response.json()
            ready = bool(
                data.get("isReady")
                or data.get("connected")
                or data.get("ready")
                or data.get("ok")
                or data.get("status") == "ready"
            )
            # Normalizar resposta para frontend
            return {
                "connected": ready,
                "status": data.get("status", "ready" if ready else "unknown"),
                "ok": ready,
                "version": data.get("version", "-"),
                "isReady": ready,
            }
    except httpx.TimeoutException:
        logger.warning("[BOT-STATUS] Timeout ao conectar com bot")
        return {"connected": False, "status": "timeout", "ok": False}
    except httpx.HTTPStatusError as e:
        logger.error("[BOT-STATUS] Erro HTTP: %s", e)
        return {"connected": False, "status": "error", "ok": False}
    except Exception as e:
        logger.error("[BOT-STATUS] Erro: %s", e)
        return {"connected": False, "status": "offline", "ok": False}


def _current_org_id(request: Request, user) -> Optional[int]:
    return (
        getattr(getattr(request, "state", None), "org_id", None)
        or getattr(user, "org_id", None)
        or getattr(user, "organization_id", None)
    )


_PROFILE_PHOTO_HOST_SUFFIXES = (
    "whatsapp.net",
    "whatsapp.com",
    "fbcdn.net",
    "fbsbx.com",
)
_PROFILE_PHOTO_DATA_RE = re.compile(r"^data:(image/(?:jpeg|jpg|png|webp));base64,([A-Za-z0-9+/=\s]+)$")
_MAX_PROFILE_PHOTO_DATA_URL_CHARS = 400_000


def _is_allowed_profile_photo_url(url: str) -> bool:
    raw = str(url or "")
    if raw.startswith("data:"):
        return len(raw) <= _MAX_PROFILE_PHOTO_DATA_URL_CHARS and bool(_PROFILE_PHOTO_DATA_RE.match(raw))
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        return False
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in _PROFILE_PHOTO_HOST_SUFFIXES)


def _profile_photo_proxy_url(phone: str) -> str:
    return f"{PREFIX}{ROUTER_PREFIX}/api/profile-photo/{quote(str(phone or ''), safe='')}"


def _proxy_conversation_profile_photos(conversations: list[dict]) -> list[dict]:
    """Keep short-lived WhatsApp CDN photo URLs off the DOM."""
    for conv in conversations or []:
        raw = conv.get("profilePic") or conv.get("profile_pic_url")
        if not raw or not _is_allowed_profile_photo_url(str(raw)):
            continue
        phone = conv.get("phone")
        if phone:
            conv["profilePic"] = _profile_photo_proxy_url(phone)
    return conversations


def _profile_pic_payload_url(phone: str, url: Optional[str]) -> Optional[str]:
    if not phone or not url or not _is_allowed_profile_photo_url(url):
        return None
    phone_key = whatsapp_clone_service.normalize_phone(phone) or str(phone)
    return _profile_photo_proxy_url(phone_key)


def _json_time(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _local_conversations(db: Session, org_id: Optional[int]) -> list[dict]:
    """Build the chat list from CaseHub's persisted WhatsApp messages.

    The lite WhatsApp bot owns the live connection while FastAPI owns the
    message archive. If the bot has no conversation endpoint, this keeps the
    product surface populated from real CaseHub data instead of showing a
    misleading blank state.
    """
    if not org_id:
        return []
    try:
        rows = db.execute(
            text(
                """
                SELECT id, phone, from_phone, direction, message, status,
                       client_id, inbound_processed_at, created_at
                FROM whatsapp_messages
                WHERE org_id = :org_id AND phone IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 500
                """
            ),
            {"org_id": org_id},
        ).mappings().all()
    except Exception as exc:  # noqa: BLE001 - optional legacy table
        logger.warning("WhatsApp local conversation fallback unavailable: %s", exc)
        db.rollback()
        return []

    by_phone: dict[str, dict] = {}
    for row in rows:
        phone = row.get("from_phone") or row.get("phone")
        if not phone:
            continue
        item = by_phone.setdefault(
            phone,
            {
                "phone": phone,
                "name": phone,
                "whatsapp_name": phone,
                "lastMessage": row.get("message") or "",
                "lastMessageTime": _json_time(row.get("created_at")),
                "updated_at": _json_time(row.get("created_at")),
                "unread": 0,
                "from_bot": 1,
                "bot_enabled": True,
                "human_takeover": False,
                "never_contact": False,
                "source": "casehub",
            },
        )
        if row.get("direction") == "incoming":
            item["from_bot"] = 0
            if row.get("inbound_processed_at") is None:
                item["unread"] = int(item.get("unread") or 0) + 1
    return list(by_phone.values())


def _local_messages(db: Session, org_id: Optional[int], phone: str, limit: int = 100) -> list[dict]:
    if not org_id:
        return []
    try:
        rows = db.execute(
            text(
                """
                SELECT id, phone, from_phone, direction, message, status,
                       client_id, media_type, raw_payload, created_at
                FROM whatsapp_messages
                WHERE org_id = :org_id
                  AND (phone = :phone OR from_phone = :phone)
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"org_id": org_id, "phone": phone, "limit": int(limit)},
        ).mappings().all()
    except Exception as exc:  # noqa: BLE001 - optional legacy table
        logger.warning("WhatsApp local message fallback unavailable: %s", exc)
        db.rollback()
        return []

    messages = []
    for row in reversed(rows):
        direction = row.get("direction") or "outgoing"
        messages.append(
            {
                "id": row.get("id"),
                "phone": row.get("from_phone") or row.get("phone"),
                "role": "user" if direction == "incoming" else "assistant",
                "content": row.get("message") or "",
                "status": row.get("status") or ("received" if direction == "incoming" else "sent"),
                "created_at": _json_time(row.get("created_at")),
                "media_type": row.get("media_type"),
                "ack": 2 if direction != "incoming" else None,
                "source": "casehub",
            }
        )
    return messages


@router.get("", response_class=HTMLResponse)
async def chat_interface(request: Request, db: Session = Depends(get_db)):
    """Main WhatsApp chat interface (the web.whatsapp.com clone)."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # NAO bloquear o render no status do bot. get_bot_status() faz uma chamada
    # httpx de ate 15s ao bot — no cold start isso travava a aba WhatsApp
    # inteira. O front busca o status sozinho via /api/status (checkStatus)
    # logo apos carregar; chat.html nao usa bot_status.
    response = templates.TemplateResponse("app/whatsapp/chat.html", {
        **get_context(request, db),
        # chat.js builds WA_API_BASE from PREFIX + this — so every /api/* call
        # lands on THIS router (the complete API), flag-aware automatically.
        "wa_router_prefix": ROUTER_PREFIX,
        "asset_v": _ASSET_V,
    })
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@router.get("/dashboard", response_class=HTMLResponse)
async def legacy_dashboard(request: Request, db: Session = Depends(get_db)):
    """Legacy Lite WhatsApp dashboard.

    Only meaningful when the clone flag is ON (clone owns /whatsapp, so the old
    dashboard needs a new home at /whatsapp/dashboard). When the flag is OFF the
    legacy whatsapp_lite router still serves /whatsapp directly and this is just
    a harmless extra alias under /whatsapp-chat/dashboard.
    """
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Render the legacy dashboard template. Data assembly mirrors whatsapp_lite.
    stats = {"hoje": 0, "semana": 0, "mes": 0, "total": 0}
    recent = []
    org_id = _request_org_id(request)
    try:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=now.weekday())
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        row = db.execute(text("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN created_at >= :today THEN 1 ELSE 0 END) AS hoje,
                   SUM(CASE WHEN created_at >= :week THEN 1 ELSE 0 END) AS semana,
                   SUM(CASE WHEN created_at >= :month THEN 1 ELSE 0 END) AS mes
            FROM whatsapp_messages
            WHERE org_id = :org_id
        """), {"org_id": org_id, "today": today_start, "week": week_start, "month": month_start}).fetchone()
        if row:
            stats = {"total": row.total or 0, "hoje": row.hoje or 0,
                     "semana": row.semana or 0, "mes": row.mes or 0}
        recent = db.execute(text(
            "SELECT * FROM whatsapp_messages WHERE org_id = :org_id ORDER BY created_at DESC LIMIT 10"
        ), {"org_id": org_id}).fetchall()
    except Exception as e:
        logger.warning("legacy_dashboard stats failed: %s", e)
        db.rollback()

    clients = tenant_query(db, Client, org_id).filter(
        Client.whatsapp.isnot(None), Client.whatsapp != ""
    ).order_by(Client.first_name).all()
    try:
        from routes.whatsapp_lite import TEMPLATES_BR
    except Exception:  # noqa: BLE001
        TEMPLATES_BR = {}

    return templates.TemplateResponse("app/whatsapp/lite_dashboard.html", {
        **get_context(request, db),
        "stats": stats,
        "recent": recent,
        "clients": clients,
        "templates_br": TEMPLATES_BR,
    })


@router.get("/api/conversations")
async def api_get_conversations(request: Request, db: Session = Depends(get_db)):
    """List conversations — persistence-backed (wa_conversations / wa_contacts).

    Returns a JSON array; each item carries the exact keys static/js/chat.js
    renderConversations() reads: phone, name, profilePic, lastMessage,
    lastMessageTime, last_message_at, updated_at, unread, from_bot, bot_enabled,
    human_takeover, contact_type, client_id, tags. Tenant-scoped by org_id.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    org_id = _current_org_id(request, user)
    # Persistence-backed source: list_conversations resolves the contact NAME
    # (linked Client > WhatsApp display_name > phone) and the owner badge, which
    # the bot proxy / legacy fallback do not. Fall back only if the DB mirror is
    # empty (e.g. before any inbound was mirrored for this org).
    try:
        conversations = whatsapp_clone_service.list_conversations(db, org_id=org_id)
    except Exception as e:  # noqa: BLE001 — resilience: never 500 the chat sidebar.
        logger.warning("api_get_conversations: list_conversations failed, falling back: %s", e)
        db.rollback()
        conversations = []
    if not conversations:
        conversations = await get_bot_conversations(request=request)
        if not conversations:
            conversations = _local_conversations(db, org_id)
    return JSONResponse(_proxy_conversation_profile_photos(conversations))


async def _fetch_fresh_profile_pic_url(phone: str, request: Request) -> Optional[str]:
    try:
        client = get_bot_client()
        response = await client.get(
            f"{WHATSAPP_BOT_URL}/api/profile-pic/{quote(str(phone), safe='')}",
            timeout=10.0,
            headers=_bot_headers(request),
        )
        data = response.json() if response.status_code < 500 else {}
    except Exception as exc:  # noqa: BLE001
        logger.debug("profile-photo refresh skipped for %s: %s", phone, exc)
        return None
    url = (
        data.get("url")
        or data.get("profilePic")
        or data.get("profile_pic_url")
        or data.get("profilePicUrl")
    )
    return url if url and _is_allowed_profile_photo_url(url) else None


async def _fetch_profile_photo_bytes(url: str):
    if not _is_allowed_profile_photo_url(url):
        return None
    if str(url).startswith("data:"):
        match = _PROFILE_PHOTO_DATA_RE.match(str(url))
        if not match:
            return None
        media_type = "image/jpeg" if match.group(1) == "image/jpg" else match.group(1)
        try:
            body = base64.b64decode(re.sub(r"\s+", "", match.group(2)), validate=True)
        except (binascii.Error, ValueError):
            return None
        return body, media_type
    try:
        timeout = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={
                    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                    "User-Agent": "CaseHub/1.0 profile-photo-proxy",
                },
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("profile-photo fetch failed: %s", exc)
        return None
    ctype = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
    if response.status_code >= 400 or not ctype.startswith("image/"):
        return None
    return response.content, ctype


@router.get("/api/profile-photo/{phone}")
async def profile_photo_proxy(phone: str, request: Request, db: Session = Depends(get_db)):
    """Serve a WhatsApp contact photo through CaseHub.

    Stored WhatsApp CDN URLs are signed and short-lived. This tenant-scoped
    endpoint keeps the DOM on a stable CaseHub URL, fetches the image
    server-side, and refreshes the stored URL from the bot when needed.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _current_org_id(request, user)
    phone_key = whatsapp_clone_service.normalize_phone(phone)
    if not org_id or not phone_key:
        return Response(status_code=404)

    from models.whatsapp_clone import WaContact

    contact = (
        db.query(WaContact)
        .filter(WaContact.org_id == org_id, WaContact.phone == phone_key)
        .first()
    )
    if contact is None:
        return Response(status_code=404)

    url = contact.profile_pic_url if _is_allowed_profile_photo_url(contact.profile_pic_url or "") else None
    # Incident 2026-07-01 (prod outage, `users` table locked ~22min): release
    # the DB session before the slow external photo fetch(es) — a WhatsApp
    # CDN read (up to 15s) plus, on cache miss, a bot round-trip — so this
    # request doesn't sit idle-in-transaction holding a lock on `users`/
    # `wa_contacts` for the duration. Same fix as profile_pic_proxy /
    # profile_pics_batch_proxy below and the whatsapp_crm.py AI endpoints.
    # The pending contact refresh below re-queries by (org_id, phone_key)
    # instead of mutating the now-detached `contact` instance, so it works
    # correctly against the session's transparently-reopened connection.
    db.close()
    fetched = await _fetch_profile_photo_bytes(url) if url else None
    if fetched is None:
        fresh_url = await _fetch_fresh_profile_pic_url(phone_key, request)
        if fresh_url:
            try:
                db.query(WaContact).filter(
                    WaContact.org_id == org_id, WaContact.phone == phone_key
                ).update({"profile_pic_url": fresh_url})
                db.commit()
            except Exception:
                db.rollback()
            fetched = await _fetch_profile_photo_bytes(fresh_url)
    if fetched is None:
        return Response(status_code=404)

    body, media_type = fetched
    return Response(
        content=body,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=21600"},
    )


@router.get("/api/messages/{phone}")
async def api_get_messages(
    request: Request,
    phone: str,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Messages for a conversation — persistence-backed (wa_messages).

    Returns a JSON array, oldest-first; each item carries the keys
    static/js/chat.js renderWhatsAppMessages() reads: id, role
    ('user'|'assistant'), content, created_at, ack, media_type/media_url/
    mimetype/filename, hasMedia. Tenant-scoped by org_id.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    org_id = _current_org_id(request, user)
    try:
        messages = whatsapp_clone_service.list_messages(
            db, org_id=org_id, phone=phone, limit=limit
        )
    except Exception as e:  # noqa: BLE001 — resilience: never 500 the chat pane.
        logger.warning("api_get_messages: list_messages failed, falling back: %s", e)
        db.rollback()
        messages = []
    if not messages:
        messages = await get_bot_messages(phone, limit, request=request)
    if not messages:
        messages = _local_messages(db, org_id, phone, limit)
    return JSONResponse(messages)


def _normalize_phone_digits(value: str) -> str:
    """Strip non-digits for cross-format phone matching.

    WhatsApp gives us phone numbers in jid-style (e.g. ``55119...``)
    while CaseHub clients may store ``+55 11 99999-9999``,
    ``11 99999-9999`` or other human formats. Normalising both sides to
    digits-only lets ``endswith`` / ``==`` work without ``LIKE '%...%'``
    full scans.
    """
    import re
    return re.sub(r"\D", "", value or "")


@router.get("/api/lead/{phone}")
async def api_get_lead(request: Request, phone: str, db: Session = Depends(get_db)):
    """Get lead info.

    Perf note (goal frente A2 — ``/casehub/whatsapp-chat`` "abertura de
    conversa" hot path): the previous lookup OR-ed two equality checks
    with two ``Client.phone.contains(phone[-10:])`` predicates.
    ``contains`` compiles to ``LIKE '%xxx%'``, which Postgres **cannot
    serve with an index** — every conversation-open triggered a full
    Client table scan, scaling with the firm's client list. Two-step
    lookup now: (1) exact equality first (uses the existing
    ``email_index`` family + any phone index), (2) suffix fallback only
    when the exact lookup misses, and the fallback uses ``endswith``
    (``LIKE 'xxx'`` is still a scan in Postgres, but at least we only
    pay it on cache-miss, and the cardinality is the per-org Clients
    subset, not the whole table).
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    lead = await get_lead_info(phone, request=request)

    org_id = request.state.org_id

    # Step 1: exact-match (indexed). Try both the raw and the
    # digits-only form so a user who stored ``+55 11 999`` and a
    # WhatsApp event for ``5511999`` both resolve.
    digits = _normalize_phone_digits(phone)
    client = (
        tenant_query(db, Client, org_id)
        .filter(
            or_(
                Client.phone == phone,
                Client.whatsapp == phone,
                Client.phone == digits,
                Client.whatsapp == digits,
            )
        )
        .first()
    )

    # Step 2: suffix fallback only when exact missed and we have a real
    # last-10-digit suffix to match. Bound the cost to the per-org
    # Clients subset (the tenant_query already filters on org_id).
    if client is None and len(digits) >= 10:
        suffix = digits[-10:]
        # ``endswith`` -> ``LIKE 'xxx'`` -> not indexable in Postgres,
        # but the row set is the per-org Clients subset which is small.
        client = (
            tenant_query(db, Client, org_id)
            .filter(
                or_(
                    Client.phone.endswith(suffix),
                    Client.whatsapp.endswith(suffix),
                )
            )
            .first()
        )

    return JSONResponse({
        "lead": lead,
        "client": {
            "id": client.id,
            "name": f"{client.first_name} {client.last_name}",
            "email": client.email
        } if client else None
    })


# --- Human send: shared error contract -----------------------------------
# static/js/chat.js#sendMessage switches on `error_code` to show a specific
# message instead of the old dead-end generic "Failed to send message".
_SEND_DISCONNECTED_MSG = (
    "WhatsApp desconectado. Abra a tela de WhatsApp e leia o QR Code para reconectar."
)
_SEND_FORBIDDEN_MSG = "Você não tem permissão para enviar mensagens no WhatsApp."

# whatsapp-web.js / bot failure strings that really mean "session not live",
# even when /api/status briefly reported ready (realState=RECONNECTING).
_DISCONNECT_MARKERS = (
    "not ready", "not connected", "session closed", "disconnected",
    "no session", "evaluation failed", "protocol error", "target closed",
)


def _looks_disconnected(error: Optional[str]) -> bool:
    e = (error or "").lower()
    return any(m in e for m in _DISCONNECT_MARKERS)


async def _parse_send_body(request: Request):
    """Pull (phone, message, reply_to_message_id, reply_to_wa_message_id) from a
    JSON or form-encoded send request."""
    content_type = request.headers.get("content-type", "")
    data = {}
    try:
        if "application/json" in content_type:
            parsed = await request.json()
            if isinstance(parsed, dict):
                data = parsed
        else:
            data = await request.form()
    except Exception:
        # Malformed/empty body or a non-dict JSON payload: treat as no fields.
        # _dispatch_human_send then returns 400 bad_request, not a 500.
        pass
    return (
        data.get("phone"),
        data.get("message"),
        data.get("reply_to_message_id"),
        data.get("reply_to_wa_message_id"),
    )


async def _dispatch_human_send(
    request: Request,
    db: Session,
    phone: Optional[str],
    message: Optional[str],
    reply_to_message_id,
    reply_to_wa_message_id,
) -> JSONResponse:
    """Shared send path for /api/send + /api/send-message.

    Differentiates the failure modes the operator UI must distinguish:
      * 401 unauthorized          — not logged in
      * 403 forbidden             — authenticated but lacks whatsapp.send
      * 400 bad_request           — missing phone/message
      * 503 whatsapp_disconnected — the org session is not live (scan QR)
      * 502 send_failed           — bot reachable but the send itself failed

    Sending is scoped to request.state.org_id (the tenant), NOT to the human
    who scanned the QR: any org user with whatsapp.send can send, and the
    message is attributed to them via sent_by_user_id.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(
            {"ok": False, "success": False, "error_code": "unauthorized",
             "error": "Unauthorized"},
            status_code=401,
        )
    if not has_permission(getattr(user, "user_type", "") or "", "whatsapp.send"):
        return JSONResponse(
            {"ok": False, "success": False, "error_code": "forbidden",
             "error": _SEND_FORBIDDEN_MSG},
            status_code=403,
        )
    if not phone or not message:
        return JSONResponse(
            {"ok": False, "success": False, "error_code": "bad_request",
             "error": "phone and message required"},
            status_code=400,
        )

    # Pre-flight: a clearly-offline org session surfaces a "scan QR" error
    # instead of a generic failure. get_bot_status is tenant-aware (X-Org-Id).
    status = await get_bot_status(request=request)
    if not status.get("connected"):
        return JSONResponse(
            {"ok": False, "success": False, "error_code": "whatsapp_disconnected",
             "error": _SEND_DISCONNECTED_MSG, "bot_status": status.get("status")},
            status_code=503,
        )

    try:
        reply_to_pk = int(reply_to_message_id) if reply_to_message_id else None
    except (TypeError, ValueError):
        reply_to_pk = None

    result = await send_message_via_bot(
        phone, message, from_human=True,
        reply_to_wa_message_id=reply_to_wa_message_id, request=request,
    )
    if result.get("success"):
        _persist_outgoing(
            db, request, phone, message, result,
            reply_to_message_id=reply_to_pk, actor_user=user,
            sent_by_user_id=getattr(user, "id", None),
        )
        return JSONResponse(result, status_code=200)

    # Bot was reachable at pre-flight but the send failed. If the error smells
    # like a dropped session, label it disconnected so the UI nudges a
    # reconnect rather than showing a dead-end generic error.
    if _looks_disconnected(result.get("error")):
        return JSONResponse(
            {**result, "error_code": "whatsapp_disconnected", "error": _SEND_DISCONNECTED_MSG},
            status_code=503,
        )
    return JSONResponse({**result, "error_code": "send_failed"}, status_code=502)


@router.post("/api/send")
async def api_send_message(request: Request, db: Session = Depends(get_db)):
    """Send message as human operator (accepts JSON or Form)."""
    phone, message, reply_to_message_id, reply_to_wa_message_id = await _parse_send_body(request)
    return await _dispatch_human_send(
        request, db, phone, message, reply_to_message_id, reply_to_wa_message_id,
    )


@router.post("/api/send-message")
async def api_send_message_alias(request: Request, db: Session = Depends(get_db)):
    """Send message as human operator (alias for /api/send, accepts JSON or Form)."""
    phone, message, reply_to_message_id, reply_to_wa_message_id = await _parse_send_body(request)
    return await _dispatch_human_send(
        request, db, phone, message, reply_to_message_id, reply_to_wa_message_id,
    )


@router.post("/api/react")
async def api_react(request: Request, db: Session = Depends(get_db)):
    """Persist a reaction on a tenant-owned WhatsApp-clone message."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"error": "No org context"}, status_code=400)

    body = await request.json()
    message_id = body.get("message_id")
    emoji = (body.get("emoji") or "").strip()
    if not message_id or not emoji:
        return JSONResponse({"error": "message_id and emoji required"}, status_code=400)

    from models.whatsapp_clone import WaMessage

    filters = [WaMessage.org_id == org_id]
    try:
        filters.append((WaMessage.id == int(message_id)) | (WaMessage.wa_message_id == str(message_id)))
    except (TypeError, ValueError):
        filters.append(WaMessage.wa_message_id == str(message_id))

    msg = db.query(WaMessage).filter(*filters).first()
    if not msg:
        return JSONResponse({"error": "message not found"}, status_code=404)

    reactions = list(msg.reactions or [])
    reactions.append({
        "emoji": emoji[:16],
        "from_me": True,
        "user_id": user.id,
        "created_at": datetime.utcnow().isoformat(),
    })
    msg.reactions = reactions
    db.commit()
    return JSONResponse({"success": True, "reactions": reactions})


@router.post("/api/bot-control")
async def api_set_bot_control(
    request: Request,
    phone: str = Form(...),
    enabled: bool = Form(...),
    db: Session = Depends(get_db)
):
    """Enable/disable bot for a conversation.

    Proxies to the bot AND persists the per-conversation toggle into
    wa_conversations so the clone's conversation list reflects it.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    org_id = _request_org_id(request)
    if org_id:
        try:
            whatsapp_clone_service.set_bot_enabled(
                db, org_id=org_id, phone=phone, enabled=enabled,
                human_takeover=not enabled,
            )
        except Exception as e:
            logger.warning("bot-control persistence failed: %s", e)
            db.rollback()

    result = await set_bot_control(phone, enabled, request=request)
    return JSONResponse(result)


@router.post("/api/mark-read/{phone}")
async def api_mark_read(request: Request, phone: str, db: Session = Depends(get_db)):
    """Reset unread_count for a conversation (persistence-backed)."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    org_id = _request_org_id(request)
    ok = False
    if org_id:
        try:
            ok = whatsapp_clone_service.mark_conversation_read(db, org_id=org_id, phone=phone)
        except Exception as e:
            logger.warning("mark-read persistence failed: %s", e)
            db.rollback()
    return JSONResponse({"success": ok})


@router.post("/api/history/backfill/{phone}")
async def api_backfill_history(
    request: Request,
    phone: str,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    """Fetch currently exposed WhatsApp Web history and persist missing rows.

    This is an explicit operator action, not a reconnect path: it never wipes
    LocalAuth, never restarts the bot and never marks old imported messages as
    unread. WhatsApp Web may expose only part of the old device history; for
    older gaps the phone export importer remains the safer path.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"success": False, "error": "No org context"}, status_code=400)

    body = {}
    if "application/json" in (request.headers.get("content-type") or ""):
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
    limit = _coerce_history_limit(body.get("limit") if isinstance(body, dict) else limit, default=limit)

    before = whatsapp_clone_service.count_messages(db, org_id=org_id, phone=phone)
    messages = await get_bot_messages(phone, limit, request=request)
    if not isinstance(messages, list):
        return JSONResponse({
            "success": False,
            "fetched": 0,
            "stored": 0,
            "total": before,
            "error": "Bot did not return a message list",
        }, status_code=502)

    skipped = 0
    try:
        for item in messages:
            if not isinstance(item, dict):
                skipped += 1
                continue
            _persist_bot_history_message(db, org_id=org_id, phone=phone, data=item)
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning("history backfill failed for org=%s phone=%s: %s", org_id, phone, e)
        return JSONResponse({
            "success": False,
            "fetched": len(messages),
            "stored": 0,
            "total": before,
            "error": "Failed to persist history",
        }, status_code=500)

    after = whatsapp_clone_service.count_messages(db, org_id=org_id, phone=phone)
    return JSONResponse({
        "success": True,
        "phone": whatsapp_clone_service.normalize_phone(phone) or phone,
        "limit": limit,
        "fetched": len(messages),
        "stored": max(0, after - before),
        "skipped": skipped,
        "total": after,
    })


@router.get("/api/status")
async def api_get_status(request: Request, db: Session = Depends(get_db)):
    """Get WhatsApp bot status"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    status = await get_bot_status(request=request)
    return JSONResponse(status)


@router.post("/api/disconnect")
async def api_disconnect(request: Request, db: Session = Depends(get_db)):
    """Disconnect WhatsApp session for this tenant (LGPD right of revocation)."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        client = get_bot_client()
        headers = _bot_headers(request)
        # Bot logout endpoint scoped to X-Org-Id session
        response = await client.post(
            f"{WHATSAPP_BOT_URL}/api/logout",
            headers=headers,
            timeout=15.0,
        )
        if response.status_code in (200, 204):
            return JSONResponse({"success": True, "message": "WhatsApp desconectado"})
        # Some bots use /api/disconnect; try both
        response = await client.post(
            f"{WHATSAPP_BOT_URL}/api/disconnect",
            headers=headers,
            timeout=15.0,
        )
        if response.status_code in (200, 204):
            return JSONResponse({"success": True, "message": "WhatsApp desconectado"})
        return JSONResponse(
            {"success": False, "error": f"Bot retornou {response.status_code}"},
            status_code=502,
        )
    except Exception as e:
        logger.error("Error disconnecting WhatsApp: %s", e)
        return JSONResponse(
            {"success": False, "error": "Bot indisponível no momento"},
            status_code=503,
        )


# Bot session states from which a QR will NEVER spontaneously appear without a
# (re)initialization. The autostarted default org (apex, org 1) can land here
# after a stale persisted session or a failed auth, whereas a freshly
# lazy-initialized tenant session (e.g. tenanta on first hit) reliably
# emits a QR. We force-heal these so the apex behaves like the subdomain.
#   - "disconnected" / "auth_failed": terminal, needs soft reconnect.
#   - "" / "unknown" / "offline": bot has no live session object for this org.
# Deliberately EXCLUDED: "ready" (connected — never wipe), "awaiting_scan" /
# "awaiting_pairing" (QR/code already in flight) and "authenticated" /
# "initializing" / "reconnecting" (transient handshake that resolves to ready
# within seconds; the bot's own 60s ready-timeout reinits if it stalls). Wiping
# those would destroy a session that was about to connect.
_QR_STALE_STATUSES = {"disconnected", "auth_failed", "offline", "unknown", ""}


async def _bot_qr_payload(client, headers: dict) -> Optional[dict]:
    """Fetch the bot's /api/qr rich payload (qr + status + isReady). None on error."""
    try:
        response = await client.get(f"{WHATSAPP_BOT_URL}/api/qr", timeout=10.0, headers=headers)
        if response.status_code == 200 and "application/json" in response.headers.get("content-type", ""):
            return response.json()
    except Exception as e:
        logger.error("Error fetching QR payload: %s", e)
    return None


@router.get("/api/qr")
async def api_get_qr(request: Request, db: Session = Depends(get_db)):
    """Get QR code for WhatsApp connection (tenant-aware, self-healing).

    Apex/default-org bug-fix (2026-05-29): the bot autostarts only the default
    org (CASEHUB_AUTOSTART_ORGS, default "1") at boot. If that session is stale
    (persisted-but-invalid LocalAuth, auth_failed, or an "authenticated" state
    whose `ready` never fired) the bot returns qr=null forever and the apex
    user never sees a QR — while a subdomain tenant (lazy-initialized on first
    request) always gets a fresh QR. We detect that dead state and POST
    /api/reconnect (bot softReconnect → preserves LocalAuth and emits QR only
    when the saved session cannot reconnect), then re-read. tenanta
    (already awaiting_scan/ready) never hits this branch, so its working flow is
    untouched.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        client = get_bot_client()
        headers = _bot_headers(request)

        data = await _bot_qr_payload(client, headers)
        if data is not None:
            has_qr = bool(data.get("qr"))
            ready = bool(data.get("isReady") or data.get("connected") or data.get("ready"))
            status = str(data.get("status") or "").lower()

            # Healthy: QR present, or already connected → return as-is. The
            # frontend shim distinguishes these via isReady/status.
            if has_qr or ready:
                return JSONResponse(data)

            # Dead session for this org → force a fresh QR once, then re-read.
            if status in _QR_STALE_STATUSES:
                logger.info(
                    "[QR] org=%s stale session (status=%r, no qr) — forcing reinit",
                    headers.get("X-Org-Id", "default"), status or "<empty>",
                )
                try:
                    await client.post(
                        f"{WHATSAPP_BOT_URL}/api/reconnect",
                        timeout=35.0,
                        headers=headers,
                    )
                except Exception as e:
                    # Reinit best-effort — never 500 the QR page.
                    logger.warning("[QR] reinit POST failed for org=%s: %s",
                                   headers.get("X-Org-Id", "default"), e)
                refreshed = await _bot_qr_payload(client, headers)
                if refreshed is not None:
                    return JSONResponse(refreshed)

            # Initializing/awaiting but no QR yet (cold start): return the rich
            # payload so the shim shows the spinner + auto-retries.
            return JSONResponse(data)

        # JSON endpoint unavailable — fall back to the HTML /qr scraper.
        response = await client.get(f"{WHATSAPP_BOT_URL}/qr", timeout=10.0, headers=headers)
        if response.status_code == 200:
            html = response.text
            # Extract base64 QR from HTML: <img src='data:image/png;base64,...'>
            import re
            match = re.search(r"src=['\"]?(data:image/png;base64,[^'\"]+)['\"]?", html)
            if match:
                return JSONResponse({"qr": match.group(1)})
    except Exception as e:
        logger.error("Error fetching QR: %s", e)
    return JSONResponse({"qr": None})


@router.post("/api/pairing-code")
async def api_request_pairing_code(request: Request, db: Session = Depends(get_db)):
    """Request a pairing code for WhatsApp connection"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        # Get phone from JSON body
        body = await request.json()
        phone = body.get("phone", "")

        if not phone:
            return JSONResponse({"success": False, "error": "Phone number is required"})

        client = get_bot_client()
        response = await client.post(
            f"{WHATSAPP_BOT_URL}/pairing-code",
            json={"phone": phone},
            timeout=60.0,
            headers=_bot_headers(request),
        )

        if response.status_code == 200:
            data = response.json()
            return JSONResponse(data)
        else:
            return JSONResponse({
                "success": False,
                "error": f"Bot returned status {response.status_code}"
            })

    except httpx.TimeoutException:
        return JSONResponse({
            "success": False,
            "error": "Request timed out. The pairing code may still be generating."
        })
    except Exception as e:
        logger.error("Error requesting pairing code: %s", e)
        return JSONResponse({"success": False, "error": str(e)})


@router.post("/api/reconnect")
async def api_reconnect(request: Request, db: Session = Depends(get_db)):
    """Ask the bot to reconnect this tenant while preserving the saved session."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        client = get_bot_client()
        response = await client.post(
            f"{WHATSAPP_BOT_URL}/api/reconnect", timeout=35.0,
            headers=_bot_headers(request),
        )
        if response.status_code == 200:
            return JSONResponse(response.json())
        return JSONResponse(
            {"success": False, "error": f"Bot retornou {response.status_code}"},
            status_code=502,
        )
    except Exception as e:
        logger.error("Error reconnecting: %s", e)
    return JSONResponse({"success": False, "error": "Failed to reconnect"}, status_code=503)


# ============================================
# LEADS FROM MOSKIT
# ============================================

@router.get("/api/leads")
async def api_get_leads(request: Request, db: Session = Depends(get_db)):
    """Get leads from Moskit with [LEAD prefix"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    result = await moskit_service.search_leads("[LEAD")
    if not result.get("success"):
        return JSONResponse({"error": result.get("error", "Failed to fetch leads")}, status_code=500)

    return JSONResponse({
        "leads": result.get("data", []),
        "total": result.get("total", 0)
    })


# ============================================
# BOT CONTROL - GLOBAL SETTINGS
# ============================================

@router.get("/api/bot/settings")
async def api_get_bot_settings(request: Request, db: Session = Depends(get_db)):
    """Get global bot settings"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        client = get_bot_client()
        response = await client.get(
            f"{WHATSAPP_BOT_URL}/api/admin/bot-status", timeout=10.0,
            headers=_bot_headers(request),
        )
        if response.status_code == 200:
            return JSONResponse(response.json())
    except Exception as e:
        logger.error("Error getting bot settings: %s", e)

    # Default settings if bot doesn't respond
    return JSONResponse({
        "enabled": True,
        "mode": "auto",
        "templates": [
            {"id": "greeting", "name": "Saudação", "text": "Olá! Como posso ajudá-lo hoje?"},
            {"id": "ask_info", "name": "Pedir Informações", "text": "Para melhor atendê-lo, preciso de algumas informações..."},
            {"id": "offer_free", "name": "Consulta Grátis", "text": "Temos uma consulta gratuita disponível para você!"},
            {"id": "offer_paid", "name": "Consulta Paga", "text": "Oferecemos consultas com nossos advogados especializados."},
            {"id": "goodbye", "name": "Despedida", "text": "Obrigado pelo contato! Estamos à disposição."}
        ]
    })


@router.post("/api/bot/settings")
async def api_update_bot_settings(request: Request, db: Session = Depends(get_db)):
    """Update global bot settings"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        body = await request.json()

        client = get_bot_client()
        response = await client.post(
            f"{WHATSAPP_BOT_URL}/api/bot/settings",
            json=body,
            timeout=10.0,
            headers=_bot_headers(request),
        )
        if response.status_code == 200:
            return JSONResponse(response.json())

    except Exception as e:
        logger.error("Error updating bot settings: %s", e)

    return JSONResponse({"success": False, "error": "Failed to update settings"})


@router.post("/api/bot/toggle")
async def api_toggle_bot(request: Request, db: Session = Depends(get_db)):
    """Toggle bot on/off globally"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        client = get_bot_client()
        headers = _bot_headers(request)
        # Buscar status atual para toggle correto
        status_resp = await client.get(
            f"{WHATSAPP_BOT_URL}/api/admin/bot-status", timeout=10.0,
            headers=headers,
        )
        status = status_resp.json()
        is_on = status.get("globalEnabled", True) and not status.get("hardOff", False)
        response = await client.post(
            f"{WHATSAPP_BOT_URL}/api/admin/bot-global-toggle",
            json={"enabled": not is_on, "updatedBy": f"CaseHub ({user.username})"},
            timeout=10.0,
            headers=headers,
        )
        if response.status_code == 200:
            return JSONResponse(response.json())
    except Exception as e:
        logger.error("Error toggling bot: %s", e)

    return JSONResponse({"success": False, "error": "Failed to toggle bot"})


@router.get("/api/bot/analytics")
async def api_get_bot_analytics(request: Request, days: int = 30, db: Session = Depends(get_db)):
    """Get bot analytics from the WhatsApp chatbot"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    analytics = {
        "totalConversations": 0,
        "messagesSent": 0,
        "leadsCapturad": 0,
        "avgResponseTime": "-",
        "visaInterest": [],
        "languageDistribution": [],
        "recentActivity": []
    }

    try:
        client = get_bot_client()
        headers = _bot_headers(request)
        # Get metrics from chatbot
        metrics_response = await client.get(
            f"{WHATSAPP_BOT_URL}/api/metrics",
            params={"days": days},
            timeout=15.0,
            headers=headers,
        )

        if metrics_response.status_code == 200:
            data = metrics_response.json()
            metrics = data.get("metrics", {})

            analytics["totalConversations"] = metrics.get("totalLeads", 0)
            analytics["leadsCapturad"] = metrics.get("totalLeads", 0)

            # Visa interest distribution
            leads_by_interest = metrics.get("leadsByInterest", [])
            total_interest = sum(item.get("count", 0) for item in leads_by_interest)
            if total_interest > 0:
                analytics["visaInterest"] = [
                    {
                        "type": item.get("visa_interest", "Other"),
                        "count": item.get("count", 0),
                        "percentage": round(item.get("count", 0) / total_interest * 100)
                    }
                    for item in leads_by_interest[:5]
                ]

        # Get conversations for recent activity
        conv_response = await client.get(
            f"{WHATSAPP_BOT_URL}/api/conversations", timeout=15.0,
            headers=headers,
        )
        if conv_response.status_code == 200:
            conversations = conv_response.json()

            # Count messages
            analytics["messagesSent"] = sum(
                conv.get("messageCount", 0) for conv in conversations
            )

            # Recent activity (last 10)
            analytics["recentActivity"] = [
                {
                    "phone": conv.get("phone", "")[:7] + "****" + conv.get("phone", "")[-4:] if conv.get("phone") else "-",
                    "name": conv.get("name", "Unknown"),
                    "action": "Lead" if conv.get("status") == "new" else conv.get("status", "Message"),
                    "time": conv.get("lastMessageTime", ""),
                    "details": conv.get("lastMessage", "")[:50] if conv.get("lastMessage") else ""
                }
                for conv in conversations[:10]
            ]

    except Exception as e:
        logger.error("Error fetching bot analytics: %s", e)

    return JSONResponse(analytics)


# ============================================
# AI SUGGESTION ENDPOINT
# ============================================

@router.post("/api/suggest-response")
async def api_suggest_response(request: Request, db: Session = Depends(get_db)):
    """Get AI-powered response suggestion"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        body = await request.json()
        phone = body.get("phone", "")

        if not phone:
            return JSONResponse({"suggestion": None, "error": "Phone required"})

        client = get_bot_client()
        response = await client.post(
            f"{WHATSAPP_BOT_URL}/api/suggest-response",
            json={"phone": phone},
            timeout=30.0,
            headers=_bot_headers(request),
        )
        if response.status_code == 200:
            return JSONResponse(response.json())
        else:
            return JSONResponse({"suggestion": None, "error": f"Bot error: {response.status_code}"})

    except httpx.TimeoutException:
        return JSONResponse({"suggestion": None, "error": "AI service timeout"})
    except Exception as e:
        logger.error("Error getting AI suggestion: %s", e)
        return JSONResponse({"suggestion": None, "error": str(e)})


# ============================================
# MEDIA UPLOAD ENDPOINT
# ============================================

@router.post("/api/send-media")
async def api_send_media(request: Request, db: Session = Depends(get_db)):
    """Send media (image/video/audio/document) via WhatsApp.

    Proxeia o upload ao bot e persiste o balao de saida em wa_messages com a
    media_url, para o clone renderizar o preview da midia enviada.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        form = await request.form()
        phone = (form.get("phone") or "").strip()
        caption = form.get("caption") or ""
        file = form.get("file")

        if not phone or not file:
            return JSONResponse({"error": "Phone and file required"}, status_code=400)

        file_bytes = await file.read()
        content_type = getattr(file, "content_type", "") or "application/octet-stream"

        client = get_bot_client()
        files = {"file": (file.filename, file_bytes, content_type)}
        data = {"phone": phone, "caption": caption}
        response = await client.post(
            f"{WHATSAPP_BOT_URL}/api/send-media", files=files, data=data, timeout=60.0,
            headers=_bot_headers(request),
        )

        result = {}
        try:
            result = response.json()
        except ValueError:
            result = {}
        ok = bool(result.get("ok") or result.get("success")) and response.status_code < 400
        if ok:
            _persist_outgoing_media(
                db, request, phone, caption, result, content_type, file.filename,
                actor_user=user,
            )
        return JSONResponse(result, status_code=200 if ok else _failure_status_for_send(result))

    except httpx.TimeoutException:
        return JSONResponse({"error": "Upload timeout"}, status_code=504)
    except Exception as e:
        logger.error("Error sending media: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/media/{filename}")
async def api_media(request: Request, filename: str, db: Session = Depends(get_db)):
    """Auth-gated proxy for WhatsApp media binaries.

    O bot guarda a midia num volume interno; documento/foto de cliente nunca
    pode ficar em URL publica. Esta rota exige sessao CaseHub e faz stream do
    binario a partir do bot interno, com guarda de path-traversal.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    if (not filename or filename in (".", "..")
            or not _MEDIA_FILENAME_RE.match(filename)):
        return JSONResponse({"error": "invalid filename"}, status_code=400)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"error": "No org context"}, status_code=400)
    from models.whatsapp_clone import WaMessage
    owned = (
        db.query(WaMessage.id)
        .filter(
            WaMessage.org_id == org_id,
            (
                (WaMessage.media_filename == filename)
                | (WaMessage.media_url.like(f"%/{filename}"))
            ),
        )
        .first()
    )
    if not owned:
        return JSONResponse({"error": "media not found"}, status_code=404)
    # Range pass-through: <video>/<audio> do clone fazem seek via Range
    # requests. Sem isto o browser baixa o arquivo inteiro para cada scrub.
    fwd_headers = dict(_bot_headers(request))
    rng = request.headers.get("range")
    if rng:
        fwd_headers["Range"] = rng
    client = None
    try:
        client = httpx.AsyncClient(timeout=30.0)
        req = client.build_request(
            "GET", f"{WHATSAPP_BOT_URL}/media/{filename}", headers=fwd_headers
        )
        resp = await client.send(req, stream=True)
        if resp.status_code not in (200, 206):
            await resp.aclose()
            await client.aclose()
            return JSONResponse({"error": "media not found"}, status_code=404)
        out_headers = {
            "Cache-Control": "private, max-age=86400",
            "Content-Disposition": "inline",
            "Accept-Ranges": "bytes",
        }
        if "content-range" in resp.headers:
            out_headers["Content-Range"] = resp.headers["content-range"]

        async def stream_media():
            try:
                async for chunk in resp.aiter_bytes():
                    yield chunk
            finally:
                await resp.aclose()
                await client.aclose()

        return StreamingResponse(
            stream_media(),
            status_code=resp.status_code,
            media_type=resp.headers.get("content-type", "application/octet-stream"),
            headers=out_headers,
        )
    except Exception as e:
        if client is not None:
            await client.aclose()
        logger.error("media proxy error %s: %s", filename, e)
        return JSONResponse({"error": "media unavailable"}, status_code=502)


# ============================================
# HUMAN TAKEOVER ENDPOINT
# ============================================

@router.post("/api/human-takeover")
async def api_human_takeover(request: Request, db: Session = Depends(get_db)):
    """Toggle human takeover mode for a conversation"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        body = await request.json()
        phone = body.get("phone", "")
        takeover = body.get("takeover", False)

        if not phone:
            return JSONResponse({"error": "Phone required"}, status_code=400)

        client = get_bot_client()
        response = await client.post(
            f"{WHATSAPP_BOT_URL}/api/human-takeover",
            json={"phone": phone, "takeover": takeover},
            timeout=10.0,
            headers=_bot_headers(request),
        )
        return JSONResponse(response.json())

    except Exception as e:
        logger.error("Error setting human takeover: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


# ============================================
# CONVERSATION CONTEXT ENDPOINT
# ============================================

@router.post("/api/conversation-context")
async def api_get_conversation_context(
    request: Request,
    phone: str = Form(...),
    db: Session = Depends(get_db)
):
    """Get conversation context for AI processing"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        client = get_bot_client()
        headers = _bot_headers(request)
        # Get lead info
        lead_response = await client.get(
            f"{WHATSAPP_BOT_URL}/api/lead/{phone}", timeout=15.0, headers=headers,
        )
        lead = lead_response.json() if lead_response.status_code == 200 else {}

        # Get recent messages
        messages_response = await client.get(
            f"{WHATSAPP_BOT_URL}/api/messages/{phone}",
            params={"limit": 20},
            timeout=15.0,
            headers=headers,
        )
        messages = messages_response.json() if messages_response.status_code == 200 else []

        return JSONResponse({
            "phone": phone,
            "lead": lead,
            "messages": messages,
            "messageCount": len(messages)
        })

    except Exception as e:
        logger.error("Error getting conversation context: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


# ============================================
# RESTART BOT ENDPOINT
# ============================================

@router.post("/api/restart")
async def api_restart_bot(request: Request, db: Session = Depends(get_db)):
    """Restart the WhatsApp bot"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        client = get_bot_client()
        headers = _bot_headers(request)
        # First try specific restart endpoint
        response = await client.post(f"{WHATSAPP_BOT_URL}/api/restart", timeout=30.0, headers=headers)
        if response.status_code == 200:
            return JSONResponse(response.json())

        # Fallback to soft reconnect, preserving the saved WhatsApp session.
        await client.post(f"{WHATSAPP_BOT_URL}/api/reconnect", timeout=35.0, headers=headers)
        return JSONResponse({"success": True, "message": "Bot is restarting"})

    except httpx.TimeoutException:
        return JSONResponse({"success": False, "error": "Request timed out"}, status_code=504)
    except Exception as e:
        logger.error("Error restarting bot: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


# ===== v12.1: AUTO FOLLOW-UP PROXY ENDPOINTS =====

@router.post("/api/followup/mark")
async def api_mark_followup(request: Request, db: Session = Depends(get_db)):
    """Mark lead for auto follow-up"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        data = await request.json()
        phone = data.get("phone")
    else:
        form = await request.form()
        phone = form.get("phone")

    if not phone:
        return JSONResponse({"error": "phone required"}, status_code=400)

    try:
        client = get_bot_client()
        response = await client.post(
            f"{WHATSAPP_BOT_URL}/api/followup/mark",
            json={"phone": phone},
            timeout=10.0,
            headers=_bot_headers(request),
        )
        return JSONResponse(response.json())
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.post("/api/followup/unmark")
async def api_unmark_followup(request: Request, db: Session = Depends(get_db)):
    """Unmark lead from auto follow-up"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        data = await request.json()
        phone = data.get("phone")
    else:
        form = await request.form()
        phone = form.get("phone")

    if not phone:
        return JSONResponse({"error": "phone required"}, status_code=400)

    try:
        client = get_bot_client()
        response = await client.post(
            f"{WHATSAPP_BOT_URL}/api/followup/unmark",
            json={"phone": phone},
            timeout=10.0,
            headers=_bot_headers(request),
        )
        return JSONResponse(response.json())
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@router.get("/api/followup/check/{phone}")
async def api_check_followup(phone: str, request: Request, db: Session = Depends(get_db)):
    """Check if lead is marked for follow-up"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # Follow-up e feature opcional: o bot-lite pode nao expor /api/followup/check.
    # Nesse caso degrada para "nao marcado" (200) em vez de 500 — abrir uma
    # conversa nao pode quebrar por causa de um proxy de feature secundaria.
    try:
        client = get_bot_client()
        response = await client.get(
            f"{WHATSAPP_BOT_URL}/api/followup/check/{phone}", timeout=10.0,
            headers=_bot_headers(request),
        )
        if response.status_code == 200:
            try:
                return JSONResponse(response.json())
            except ValueError:
                pass
        return JSONResponse({"success": True, "marked": False})
    except Exception as e:
        logger.warning("followup/check proxy falhou para %s: %s", phone, e)
        return JSONResponse({"success": True, "marked": False})


@router.get("/api/followup/stats")
async def api_followup_stats(request: Request, db: Session = Depends(get_db)):
    """Get follow-up statistics"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        client = get_bot_client()
        response = await client.get(
            f"{WHATSAPP_BOT_URL}/api/followup/stats", timeout=10.0,
            headers=_bot_headers(request),
        )
        return JSONResponse(response.json())
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ===== v13.0: SSE Proxy for real-time messages =====
@router.get("/api/events/messages/{phone}")
async def sse_messages_proxy(phone: str, request: Request, db: Session = Depends(get_db)):
    """SSE proxy for real-time message streaming from WhatsApp Bot"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    # v13.2: Release DB connection BEFORE streaming (SSE holds connection indefinitely)
    db.close()

    headers = _bot_headers(request)

    async def event_stream():
        try:
            # v13.2: 5min read timeout to prevent memory leaks - browser auto-reconnects
            timeout = httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "GET",
                    f"{WHATSAPP_BOT_URL}/api/events/messages/{phone}",
                    headers=headers,
                ) as resp:
                    async for line in resp.aiter_lines():
                        if await request.is_disconnected():
                            break
                        yield line + "\n"
        except httpx.ReadTimeout:
            yield f"data: {json.dumps({'type': 'reconnect'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# ===== v13.1: Profile Picture Proxy =====
@router.get("/api/profile-pic/{phone}")
async def profile_pic_proxy(phone: str, request: Request, db: Session = Depends(get_db)):
    """Proxy profile picture URL from WhatsApp Bot"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _current_org_id(request, user)
    headers = _bot_headers(request)
    # Incident 2026-07-01 (prod outage, `users` table locked ~22min): this
    # handler ran get_current_user()'s SELECT on users through `db`, then
    # awaited the WhatsApp-bot HTTP round-trip with that transaction still
    # open — an idle-in-transaction session holding a lock on `users` for
    # however long the bot call took. Under deploy (bot container restarting
    # too) or a slow/unresponsive bot, that's long enough for a concurrent
    # `ALTER TABLE users ADD COLUMN ...` (schema ensure on startup) to queue
    # behind it, and then EVERY other query on `users` queues FIFO behind
    # THAT ALTER — a full-site outage. Release the DB session before the
    # slow external call; get_db() happily commits/closes an already-closed
    # session again at teardown, and the session transparently reopens a
    # connection for the writes below.
    db.close()
    try:
        client = get_bot_client()
        response = await client.get(
            f"{WHATSAPP_BOT_URL}/api/profile-pic/{phone}", timeout=10.0,
            headers=headers,
        )
        payload = response.json()
        raw_url = (
            payload.get("url")
            or payload.get("profilePic")
            or payload.get("profile_pic_url")
            or payload.get("profile_pic")
        )
        proxied = _profile_pic_payload_url(phone, raw_url)
        if proxied and org_id:
            try:
                whatsapp_clone_service.upsert_contact(
                    db,
                    org_id=org_id,
                    phone=phone,
                    profile_pic_url=str(raw_url),
                    commit=True,
                )
            except Exception:
                db.rollback()
        return JSONResponse({"phone": phone, "url": proxied, "profilePic": proxied})
    except Exception as e:
        return JSONResponse({"phone": phone, "url": None})

@router.post("/api/profile-pics")
async def profile_pics_batch_proxy(request: Request, db: Session = Depends(get_db)):
    """Batch proxy for profile picture URLs and cache them in wa_contacts."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _current_org_id(request, user)
    headers = _bot_headers(request)
    # Incident 2026-07-01 — same fix as profile_pic_proxy above: release the
    # DB session before the (up to 15s) WhatsApp-bot HTTP round-trip so this
    # request doesn't sit idle-in-transaction holding a lock on `users`.
    db.close()
    try:
        body = await request.json()
        client = get_bot_client()
        response = await client.post(
            f"{WHATSAPP_BOT_URL}/api/profile-pics", json=body, timeout=15.0,
            headers=headers,
        )
        payload = response.json()

        updated = 0
        profiles = []
        proxied_profiles = []
        proxied_by_phone = {}
        if isinstance(payload, dict) and isinstance(payload.get("profiles"), list):
            profiles = payload.get("profiles") or []
        elif isinstance(payload, dict):
            profiles = [
                {"phone": phone, "url": url}
                for phone, url in (payload.get("byPhone") or payload).items()
                if phone not in ("ok", "profiles", "byPhone", "updated", "error", "status")
            ]

        for item in profiles:
            if not isinstance(item, dict):
                continue
            phone = item.get("phone")
            url = (
                item.get("url")
                or item.get("profilePic")
                or item.get("profile_pic_url")
                or item.get("profile_pic")
            )
            if not phone:
                continue
            proxy_url = _profile_pic_payload_url(str(phone), url)
            proxied_profiles.append({"phone": str(phone), "url": proxy_url, "profilePic": proxy_url})
            proxied_by_phone[str(phone)] = proxy_url
            normalized_phone = whatsapp_clone_service.normalize_phone(str(phone))
            if normalized_phone:
                proxied_by_phone[normalized_phone] = proxy_url
            if not url or not _is_allowed_profile_photo_url(str(url)):
                continue
            try:
                whatsapp_clone_service.upsert_contact(
                    db,
                    org_id=org_id,
                    phone=str(phone),
                    profile_pic_url=str(url),
                    commit=False,
                )
                updated += 1
            except Exception:
                logger.warning("profile-pics cache skip phone=%s", phone, exc_info=True)
        if updated:
            db.commit()
            if isinstance(payload, dict):
                payload["updated"] = updated
        if isinstance(payload, dict):
            payload["profiles"] = proxied_profiles
            payload["byPhone"] = proxied_by_phone
        return JSONResponse(payload)
    except Exception:
        db.rollback()
        return JSONResponse({})


@router.get("/api/events/conversations")
async def sse_conversations_proxy(request: Request, db: Session = Depends(get_db)):
    """SSE proxy for real-time conversation updates"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    # v13.2: Release DB connection BEFORE streaming (SSE holds connection indefinitely)
    db.close()

    headers = _bot_headers(request)

    async def event_stream():
        try:
            # v13.2: 5min read timeout to prevent memory leaks - browser auto-reconnects
            timeout = httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "GET",
                    f"{WHATSAPP_BOT_URL}/api/events/conversations",
                    headers=headers,
                ) as resp:
                    async for line in resp.aiter_lines():
                        if await request.is_disconnected():
                            break
                        yield line + "\n"
        except httpx.ReadTimeout:
            yield f"data: {json.dumps({'type': 'reconnect'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# ============================================================
# Legacy /whatsapp-chat 301-redirect (only when the clone flag is ON)
# ============================================================
# When CASEHUB_WHATSAPP_CLONE_ENABLED is ON the clone owns /whatsapp, so any
# bookmark / link pointing at the old /whatsapp-chat alias should 301 to the new
# root. app_factory._import_router also picks up a module-level `pages_router`,
# so exposing the redirect router under that name is enough to register it.
#
# When the flag is OFF the clone IS /whatsapp-chat — a redirect router on the
# same prefix would collide, so `pages_router` is left undefined in that case.
if _CLONE_ENABLED:
    pages_router = APIRouter(prefix="/whatsapp-chat", tags=["whatsapp-chat-redirect"])

    @pages_router.get("")
    async def _redirect_legacy_chat_root():
        """301 the legacy /whatsapp-chat root to the new /whatsapp clone root."""
        return RedirectResponse(url=f"{PREFIX}/whatsapp", status_code=301)

    @pages_router.get("/{rest:path}")
    async def _redirect_legacy_chat_alias(rest: str = ""):
        """301 any legacy /whatsapp-chat/* path to the equivalent /whatsapp/* path."""
        target = f"{PREFIX}/whatsapp"
        if rest:
            target = f"{target}/{rest}"
        return RedirectResponse(url=target, status_code=301)
