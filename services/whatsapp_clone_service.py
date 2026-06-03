"""
CaseHub - WhatsApp Web Clone Service

Upsert / query logic for the wa_contacts / wa_conversations / wa_messages model.
Backs the persistence-backed endpoints in routes/whatsapp_chat.py and the inbound
mirror in services/whatsapp_inbound_service.py.

Design rules:
  * EVERYTHING is multi-tenant scoped by org_id (models/tenant.tenant_query pattern).
    No query crosses tenant boundaries.
  * record_message dedups by (org_id, wa_message_id) so SSE + bridge + history-sync
    can all feed the same message without creating duplicates.
  * The bot stays stateless — this service is the source of truth for history.

The bot itself is reached by routes/whatsapp_proxy.py; this module never does HTTP.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from models.whatsapp_clone import WaContact, WaConversation, WaMessage, WaContactNote, WaTemplate, WaContactStageHistory
from models.user import User
from models.client import Client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CRM lead funnel + ownership (shared vocab). routes/whatsapp_crm.py imports
# LEAD_STAGES/LABELS/normalize_stage/resolve_owner from here, and the sidebar
# (list_conversations) emits the resolved name + owner badge for every row.
# ---------------------------------------------------------------------------
# Intake-jurídico funnel (ordered). Supersedes the old cold/warm/qualified/hot.
LEAD_STAGES = ["novo", "triagem", "reuniao", "proposta", "cliente", "descartado"]
LEAD_STAGE_LABELS = {
    "novo": "Novo",
    "triagem": "Triagem",
    "reuniao": "Reunião",
    "proposta": "Proposta",
    "cliente": "Cliente",
    "descartado": "Descartado",
}
# Map the previous generic vocab (and a few aliases) onto the new funnel so any
# existing wa_contacts.lead_stage value still lands in a sensible column.
_STAGE_ALIASES = {
    "cold": "novo", "warm": "triagem", "qualified": "reuniao", "hot": "proposta",
    "new": "novo", "contacted": "triagem", "won": "cliente", "lost": "descartado",
}


def normalize_stage(raw) -> str:
    """Coerce any stored/legacy lead_stage to a valid current stage (default novo)."""
    s = (raw or "").strip().lower()
    s = _STAGE_ALIASES.get(s, s)
    return s if s in LEAD_STAGES else "novo"


# ---------------------------------------------------------------------------
# Lead scoring (PR6, ruling 2026-05-31): deterministic 0-100, MATERIALIZED in
# wa_contacts.lead_score and recomputed ON-WRITE — never scanned on the sidebar
# read path (would regress the anti-N+1 list_conversations fix).
# ---------------------------------------------------------------------------
_STAGE_SCORE = {
    "novo": 4, "triagem": 8, "reuniao": 14,
    "proposta": 18, "cliente": 20, "descartado": 0,
}

# PT-BR legal-intent keywords, pre-normalized (NFKD + strip accents + casefold).
_LEGAL_KEYWORDS = frozenset([
    "agendar", "consulta", "processo", "contratar", "orcamento", "honorarios",
    "audiencia", "peticao", "acao", "reuniao", "advogado", "advogada", "juridico",
    "contrato", "divorcio", "inventario", "trabalhista", "indenizacao", "proposta",
    "causa", "direito", "recurso", "acordo", "citacao", "prazo",
])


def _norm_text(s) -> str:
    """Accent-fold + casefold (PT-BR legal terms are accent-heavy)."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.casefold()


def _intent_keyword_matches(bodies) -> int:
    """Distinct legal-intent keywords across a contact's messages (word-boundary)."""
    found = set()
    for body in bodies:
        for tok in re.findall(r"[a-z0-9]+", _norm_text(body)):
            if tok in _LEGAL_KEYWORDS:
                found.add(tok)
    return len(found)


def compute_lead_score(db: Session, org_id: int, contact) -> int:
    """Deterministic 0-100 lead score: Engagement 40 + Intent 30 + Stage 20 +
    Vínculo 10. Integer arithmetic, org-scoped. Recompute ON-WRITE only."""
    conv = (
        db.query(WaConversation)
        .filter(WaConversation.org_id == org_id, WaConversation.contact_id == contact.id)
        .first()
    )
    bodies = []
    msg_count = 0
    if conv is not None:
        msgs = (
            db.query(WaMessage)
            .filter(WaMessage.org_id == org_id, WaMessage.conversation_id == conv.id)
            .all()
        )
        msg_count = len(msgs)
        bodies = [m.body for m in msgs if m.body]
    engagement = min(40, msg_count * 4)
    intent = min(30, _intent_keyword_matches(bodies) * 10)
    stage = _STAGE_SCORE.get(normalize_stage(contact.lead_stage), 4)
    vinculo = 10 if contact.client_id else 0
    return max(0, min(100, engagement + intent + stage + vinculo))


def recalc_lead_score(db: Session, org_id: int, contact, commit: bool = True) -> int:
    """Recompute + store the materialized lead score for a contact. Non-fatal."""
    try:
        score = compute_lead_score(db, org_id, contact)
    except Exception:  # noqa: BLE001
        return contact.lead_score or 0
    contact.lead_score = score
    if commit:
        db.commit()
    return score


# Deterministic per-member badge palette (used when a User has no explicit color).
# Purple first so it reads as the canonical "owner" accent.
OWNER_PALETTE = [
    "#7c3aed", "#2563eb", "#059669", "#d97706", "#dc2626",
    "#db2777", "#0891b2", "#65a30d", "#9333ea", "#ea580c",
]
_DEFAULT_USER_COLOR = "#1c2447"


def owner_color(user) -> str:
    """Badge color for an owner User: explicit User.color if set, else palette by id."""
    c = (getattr(user, "color", None) or "").strip()
    if c and c.lower() != _DEFAULT_USER_COLOR:
        return c
    return OWNER_PALETTE[(getattr(user, "id", 0) or 0) % len(OWNER_PALETTE)]


def _owner_dict(user) -> Optional[dict]:
    if user is None:
        return None
    return {"user_id": user.id, "name": user.name, "color": owner_color(user)}


def resolve_owner(db: Session, org_id: int, owner_user_id) -> Optional[dict]:
    """Owner badge payload {user_id,name,color} for one contact, tenant-scoped."""
    if not owner_user_id:
        return None
    u = (
        db.query(User)
        .filter(User.id == owner_user_id, User.org_id == org_id, User.enabled.is_(True))
        .first()
    )
    return _owner_dict(u)


# ---------------------------------------------------------------------------
# Per-contact CRM notes (append log, tenant-scoped). Backs /api/crm/notes/*.
# ---------------------------------------------------------------------------
def list_notes(db: Session, org_id: int, contact_id: int) -> List[dict]:
    """Notes for one contact, newest-first, with author names resolved (batched)."""
    notes = (
        db.query(WaContactNote)
        .filter(WaContactNote.org_id == org_id, WaContactNote.contact_id == contact_id)
        .order_by(WaContactNote.created_at.desc())
        .limit(200)
        .all()
    )
    author_ids = {n.author_user_id for n in notes if n.author_user_id}
    names: dict = {}
    if author_ids:
        for u in db.query(User).filter(User.id.in_(author_ids)).all():
            names[u.id] = u.name
    return [n.to_dict(author_name=names.get(n.author_user_id)) for n in notes]


def add_note(db: Session, org_id: int, contact_id: int, author_user_id,
             body: str, note_type: str = "note") -> Optional[dict]:
    """Append a note to a contact. Returns the created note dict (None if empty body)."""
    body = (body or "").strip()
    if not body:
        return None
    note = WaContactNote(
        org_id=org_id, contact_id=contact_id, author_user_id=author_user_id,
        body=body[:5000], note_type=note_type or "note",
    )
    db.add(note)
    db.commit()
    name = None
    if author_user_id:
        u = db.query(User).filter(User.id == author_user_id).first()
        name = u.name if u else None
    return note.to_dict(author_name=name)


def delete_note(db: Session, org_id: int, note_id: int) -> bool:
    """Delete a note within an org (tenant-scoped). True if a row was removed."""
    note = (
        db.query(WaContactNote)
        .filter(WaContactNote.id == note_id, WaContactNote.org_id == org_id)
        .first()
    )
    if note is None:
        return False
    db.delete(note)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Follow-up scheduling + duplicate detection (PR7 + PR8, tenant-scoped).
# ---------------------------------------------------------------------------
def _digits(value) -> str:
    """Digits-only form of a phone (for dedup suffix matching)."""
    return "".join(ch for ch in (value or "") if ch.isdigit())


def schedule_follow_up(db: Session, org_id: int, contact_id: int,
                       follow_up_date, note=None) -> Optional[dict]:
    """Set (follow_up_date) or clear (None) the follow-up on a contact, org-scoped."""
    contact = (
        db.query(WaContact)
        .filter(WaContact.org_id == org_id, WaContact.id == contact_id)
        .first()
    )
    if contact is None:
        return None
    contact.follow_up_date = follow_up_date
    contact.follow_up_note = (note or None) if follow_up_date else None
    contact.updated_at = _now()
    db.commit()
    return {
        "contact_id": contact.id,
        "follow_up_date": contact.follow_up_date.isoformat() if contact.follow_up_date else None,
        "follow_up_note": contact.follow_up_note,
    }


def get_overdue_follow_ups(db: Session, org_id: int, today) -> List[dict]:
    """Contacts whose follow-up is due on/before `today`, most-overdue first."""
    rows = (
        db.query(WaContact)
        .filter(
            WaContact.org_id == org_id,
            WaContact.follow_up_date.isnot(None),
            WaContact.follow_up_date <= today,
        )
        .order_by(WaContact.follow_up_date.asc())
        .all()
    )
    return [{
        "contact_id": c.id, "phone": c.phone, "display_name": c.display_name,
        "follow_up_date": c.follow_up_date.isoformat() if c.follow_up_date else None,
        "follow_up_note": c.follow_up_note,
        "days_overdue": (today - c.follow_up_date).days,
    } for c in rows]


def check_duplicates(db: Session, org_id: int, phone: str,
                     exclude_contact_id: Optional[int] = None) -> List[dict]:
    """Other contacts in the SAME org matching by last-10 phone digits.

    Tenant-scoped by org_id — a global suffix match would surface another firm's
    clients (the cross-org leak the Council flagged in the dedup port note).
    """
    last10 = _digits(phone)[-10:]
    if len(last10) < 8:
        return []
    rows = db.query(WaContact).filter(WaContact.org_id == org_id).all()
    out = []
    for c in rows:
        if exclude_contact_id and c.id == exclude_contact_id:
            continue
        cd = _digits(c.normalized_phone or c.phone)
        if cd and cd[-10:] == last10:
            out.append({
                "contact_id": c.id, "phone": c.phone,
                "display_name": c.display_name, "client_id": c.client_id,
            })
    return out


# ---------------------------------------------------------------------------
# Org-owned quick-reply templates (PR4, tenant-scoped CRUD).
# ---------------------------------------------------------------------------
def list_org_templates(db: Session, org_id: int):
    return (
        db.query(WaTemplate)
        .filter(WaTemplate.org_id == org_id)
        .order_by(WaTemplate.name)
        .all()
    )


def get_org_template(db: Session, org_id: int, template_id: int):
    return (
        db.query(WaTemplate)
        .filter(WaTemplate.id == template_id, WaTemplate.org_id == org_id)
        .first()
    )


def create_template(db: Session, org_id: int, name: str, body_pt: str,
                    category: str = "custom", body_en=None, body_es=None):
    t = WaTemplate(
        org_id=org_id, name=(name or "")[:128], body_pt=body_pt or "",
        category=(category or "custom")[:64], body_en=body_en, body_es=body_es,
    )
    db.add(t)
    db.commit()
    return t


def update_template(db: Session, org_id: int, template_id: int, **fields):
    t = get_org_template(db, org_id, template_id)
    if t is None:
        return None
    if fields.get("name"):
        t.name = fields["name"][:128]
    if fields.get("body_pt"):
        t.body_pt = fields["body_pt"]
    if "body_en" in fields:
        t.body_en = fields["body_en"]
    if "body_es" in fields:
        t.body_es = fields["body_es"]
    if fields.get("category"):
        t.category = fields["category"][:64]
    db.commit()
    return t


def delete_template(db: Session, org_id: int, template_id: int) -> bool:
    t = get_org_template(db, org_id, template_id)
    if t is None:
        return False
    db.delete(t)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Lead-stage transition history (PR5, append-only, tenant-scoped).
# ---------------------------------------------------------------------------
def record_stage_change(db: Session, org_id: int, contact_id: int,
                        from_stage, to_stage, actor_user_id=None, reason=None):
    """Append a stage transition (no-op when unchanged). Commits."""
    if not to_stage or from_stage == to_stage:
        return None
    h = WaContactStageHistory(
        org_id=org_id, contact_id=contact_id, from_stage=from_stage,
        to_stage=to_stage, actor_user_id=actor_user_id, reason=reason,
    )
    db.add(h)
    db.commit()
    return h


def list_stage_history(db: Session, org_id: int, contact_id: int) -> List[dict]:
    rows = (
        db.query(WaContactStageHistory)
        .filter(WaContactStageHistory.org_id == org_id,
                WaContactStageHistory.contact_id == contact_id)
        .order_by(WaContactStageHistory.created_at.desc())
        .all()
    )
    return [h.to_dict() for h in rows]


# ---------------------------------------------------------------------------
# Deterministic stage suggestion (PR10). PROMOTE-ONLY, never touches terminals
# (cliente/descartado), never auto-applies — just a hint from the materialized
# lead_score. The operator decides. No LLM, no message scan (reads the score).
# ---------------------------------------------------------------------------
_FUNNEL_ORDER = ["novo", "triagem", "reuniao", "proposta"]


def suggest_next_stage(contact) -> Optional[str]:
    """Suggest advancing the lead (promote-only) based on its score. None = no move."""
    if contact is None:
        return None
    cur = normalize_stage(contact.lead_stage)
    if cur not in _FUNNEL_ORDER:          # cliente / descartado -> terminal, untouched
        return None
    score = contact.lead_score or 0
    idx = _FUNNEL_ORDER.index(cur)
    target = idx
    if score >= 70:
        target = _FUNNEL_ORDER.index("proposta")
    elif score >= 50:
        target = _FUNNEL_ORDER.index("reuniao")
    elif score >= 30:
        target = _FUNNEL_ORDER.index("triagem")
    return _FUNNEL_ORDER[target] if target > idx else None  # promote-only


# ---------------------------------------------------------------------------
# Funnel analytics (PR11, org-scoped). Conversion / avg-score / overdue /
# velocity from wa_contacts + wa_contact_stage_history (PR5).
# ---------------------------------------------------------------------------
def compute_funnel_analytics(db: Session, org_id: int, today) -> dict:
    contacts = db.query(WaContact).filter(WaContact.org_id == org_id).all()
    total = len(contacts)
    by_stage = {s: 0 for s in LEAD_STAGES}
    score_sum = 0
    for c in contacts:
        st = normalize_stage(c.lead_stage)
        by_stage[st] = by_stage.get(st, 0) + 1
        score_sum += (c.lead_score or 0)
    won = by_stage.get("cliente", 0)
    lost = by_stage.get("descartado", 0)
    closed = won + lost
    conversion_pct = round(won / closed * 100) if closed else 0
    avg_score = round(score_sum / total) if total else 0
    overdue = (
        db.query(WaContact)
        .filter(WaContact.org_id == org_id, WaContact.follow_up_date.isnot(None),
                WaContact.follow_up_date <= today)
        .count()
    )
    # Velocity: avg days from a contact's first stage transition to "cliente".
    avg_days_to_win = None
    won_hist = (
        db.query(WaContactStageHistory)
        .filter(WaContactStageHistory.org_id == org_id,
                WaContactStageHistory.to_stage == "cliente")
        .all()
    )
    if won_hist:
        days = []
        for h in won_hist:
            first = (
                db.query(WaContactStageHistory)
                .filter(WaContactStageHistory.org_id == org_id,
                        WaContactStageHistory.contact_id == h.contact_id)
                .order_by(WaContactStageHistory.created_at.asc())
                .first()
            )
            if first and first.created_at and h.created_at:
                d = (_as_aware(h.created_at) - _as_aware(first.created_at)).days
                if d >= 0:
                    days.append(d)
        if days:
            avg_days_to_win = round(sum(days) / len(days))
    return {
        "total": total, "by_stage": by_stage, "won": won, "lost": lost,
        "conversion_pct": conversion_pct, "avg_score": avg_score,
        "overdue": overdue, "avg_days_to_win": avg_days_to_win,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _as_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Coerce a datetime to tz-aware (UTC).

    DateTime(timezone=True) round-trips as tz-aware on Postgres but as a NAIVE
    datetime on SQLite (the test DB). Comparing the two raises TypeError, so any
    datetime crossing a comparison goes through here first.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def normalize_phone(raw: Optional[str]) -> str:
    """Normalize a phone/JID to a stable E.164-ish key: '+' + digits.

    Accepts '5511999999999@c.us', '+55 11 99999-9999', '5511999999999' — all
    collapse to '+5511999999999'. Group JIDs keep their digits too.
    """
    if not raw:
        return ""
    # Drop a JID suffix (@c.us / @g.us / @s.whatsapp.net) before digit-stripping.
    head = str(raw).split("@", 1)[0]
    digits = "".join(ch for ch in head if ch.isdigit())
    if not digits:
        return ""
    return "+" + digits


# ---------------------------------------------------------------------------
# Contact
# ---------------------------------------------------------------------------
def upsert_contact(
    db: Session,
    *,
    org_id: int,
    phone: str,
    wa_jid: Optional[str] = None,
    display_name: Optional[str] = None,
    profile_pic_url: Optional[str] = None,
    is_business: Optional[bool] = None,
    is_group: Optional[bool] = None,
    client_id: Optional[int] = None,
    commit: bool = True,
) -> WaContact:
    """Create or update a wa_contacts row, keyed by UNIQUE(org_id, phone)."""
    if not org_id:
        raise ValueError("org_id is required for upsert_contact")
    e164 = normalize_phone(phone)
    if not e164:
        raise ValueError("a non-empty phone is required for upsert_contact")

    contact = (
        db.query(WaContact)
        .filter(WaContact.org_id == org_id, WaContact.phone == e164)
        .first()
    )
    if contact is None:
        contact = WaContact(org_id=org_id, phone=e164, tags=[])
        db.add(contact)

    # Only overwrite fields when a value was supplied (None = leave as-is).
    if wa_jid is not None:
        contact.wa_jid = wa_jid
    if display_name is not None:
        contact.display_name = display_name
    if profile_pic_url is not None:
        contact.profile_pic_url = profile_pic_url
    if is_business is not None:
        contact.is_business = bool(is_business)
    if is_group is not None:
        contact.is_group = bool(is_group)
    if client_id is not None:
        contact.client_id = client_id
    if not contact.normalized_phone:
        contact.normalized_phone = _digits(e164)
    contact.updated_at = _now()

    db.flush()
    if commit:
        db.commit()
    return contact


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------
def upsert_conversation(
    db: Session,
    *,
    org_id: int,
    contact_id: int,
    commit: bool = True,
) -> WaConversation:
    """Create or fetch the wa_conversations row, keyed by UNIQUE(org_id, contact_id)."""
    if not org_id:
        raise ValueError("org_id is required for upsert_conversation")

    conv = (
        db.query(WaConversation)
        .filter(
            WaConversation.org_id == org_id,
            WaConversation.contact_id == contact_id,
        )
        .first()
    )
    if conv is None:
        conv = WaConversation(
            org_id=org_id,
            contact_id=contact_id,
            unread_count=0,
            bot_enabled=True,
            human_takeover=False,
        )
        db.add(conv)
        db.flush()

    if commit:
        db.commit()
    return conv


def get_or_create_thread(
    db: Session,
    *,
    org_id: int,
    phone: str,
    display_name: Optional[str] = None,
    wa_jid: Optional[str] = None,
    profile_pic_url: Optional[str] = None,
    commit: bool = True,
) -> tuple[WaContact, WaConversation]:
    """Convenience: upsert contact + its conversation in one call."""
    contact = upsert_contact(
        db,
        org_id=org_id,
        phone=phone,
        wa_jid=wa_jid,
        display_name=display_name,
        profile_pic_url=profile_pic_url,
        commit=False,
    )
    conv = upsert_conversation(db, org_id=org_id, contact_id=contact.id, commit=False)
    if commit:
        db.commit()
    return contact, conv


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------
def record_message(
    db: Session,
    *,
    org_id: int,
    phone: str,
    body: str = "",
    direction: str = "incoming",
    wa_message_id: Optional[str] = None,
    media_type: str = "text",
    media_url: Optional[str] = None,
    media_mime: Optional[str] = None,
    media_filename: Optional[str] = None,
    media_ocr_text: Optional[str] = None,
    status: Optional[str] = None,
    from_me: Optional[bool] = None,
    author_phone: Optional[str] = None,
    sent_at: Optional[datetime] = None,
    ai_generated: bool = False,
    reply_to_message_id: Optional[int] = None,
    display_name: Optional[str] = None,
    profile_pic_url: Optional[str] = None,
    auto_link_client_id: Optional[int] = None,
    commit: bool = True,
) -> WaMessage:
    """Insert a message into wa_messages, dedup by (org_id, wa_message_id).

    Side effects on the conversation:
      * bumps last_message_id / last_message_at when this message is newer;
      * increments unread_count for incoming messages (decremented by
        mark_conversation_read when the operator opens the thread).

    Returns the WaMessage (existing row if it was a duplicate).
    """
    if not org_id:
        raise ValueError("org_id is required for record_message")

    if from_me is None:
        from_me = direction == "outgoing"
    direction = "outgoing" if from_me else "incoming"
    if status is None:
        status = "sent" if from_me else "delivered"
    when = sent_at or _now()

    contact, conv = get_or_create_thread(
        db,
        org_id=org_id,
        phone=phone,
        display_name=display_name,
        profile_pic_url=profile_pic_url,
        commit=False,
    )

    # Auto-vínculo CRM: o telefone casou com um Cliente já cadastrado e o
    # contato ainda não tem vínculo -> liga automaticamente. NUNCA sobrescreve
    # um vínculo manual feito pelo operador (só preenche quando está vazio).
    if auto_link_client_id and not contact.client_id:
        contact.client_id = auto_link_client_id

    # Dedup: a message id we have already stored for this org is a no-op.
    if wa_message_id:
        existing = (
            db.query(WaMessage)
            .filter(
                WaMessage.org_id == org_id,
                WaMessage.wa_message_id == wa_message_id,
            )
            .first()
        )
        if existing is not None:
            logger.debug("record_message: dedup hit wamid=%s", wa_message_id)
            if commit:
                db.commit()
            return existing

    msg = WaMessage(
        org_id=org_id,
        conversation_id=conv.id,
        wa_message_id=wa_message_id,
        direction=direction,
        body=body or "",
        media_type=media_type or "text",
        media_url=media_url,
        media_mime=media_mime,
        media_filename=media_filename,
        media_ocr_text=media_ocr_text,
        status=status,
        from_me=bool(from_me),
        author_phone=normalize_phone(author_phone) or contact.phone,
        sent_at=when,
        ai_generated=bool(ai_generated),
        reply_to_message_id=reply_to_message_id,
        reactions=[],
    )
    db.add(msg)
    db.flush()  # assign msg.id

    # Bump conversation recency when this message is the newest one.
    # _as_aware guards the naive-vs-aware mismatch between SQLite and Postgres.
    prev_at = _as_aware(conv.last_message_at)
    if prev_at is None or _as_aware(when) >= prev_at:
        conv.last_message_id = msg.id
        conv.last_message_at = when
    if not from_me:
        conv.unread_count = (conv.unread_count or 0) + 1
    conv.updated_at = _now()

    # Recompute the materialized lead score on every message write (Council ruling
    # 2026-05-31: ON-WRITE, never on the sidebar read path). Non-fatal.
    try:
        contact.lead_score = compute_lead_score(db, org_id, contact)
    except Exception:  # noqa: BLE001
        pass

    if commit:
        db.commit()
    return msg


def update_message_status(
    db: Session,
    *,
    org_id: int,
    wa_message_id: str,
    status: Optional[str] = None,
    ack: Optional[int] = None,
    commit: bool = True,
) -> Optional[WaMessage]:
    """Advance delivery ticks for an outgoing message (bot `message_ack` event).

    Accepts either a status string or a numeric `ack` (0..4 from whatsapp-web.js).
    Status only ever moves FORWARD (sent -> delivered -> read -> played); a stale
    out-of-order ack is ignored. Returns the message, or None if not found.
    """
    if not org_id or not wa_message_id:
        return None

    if status is None and ack is not None:
        status = WaMessage.status_from_ack(ack)
    if not status:
        return None

    msg = (
        db.query(WaMessage)
        .filter(
            WaMessage.org_id == org_id,
            WaMessage.wa_message_id == wa_message_id,
        )
        .first()
    )
    if msg is None:
        logger.debug("update_message_status: unknown wamid=%s", wa_message_id)
        return None

    current = WaMessage._STATUS_TO_ACK.get(msg.status or "sent", 1)
    incoming = WaMessage._STATUS_TO_ACK.get(status, 1)
    # 'failed' is terminal-ish and always honored; otherwise only move forward.
    if status == "failed" or incoming >= current:
        msg.status = status

    if commit:
        db.commit()
    return msg


# ---------------------------------------------------------------------------
# Queries (tenant-scoped)
# ---------------------------------------------------------------------------
def list_conversations(
    db: Session,
    *,
    org_id: int,
    include_archived: bool = False,
    limit: int = 200,
) -> List[dict]:
    """Return conversations for one org, newest-first, in the shape chat.js expects.

    chat.js (renderConversations) reads: phone, name, profilePic, lastMessage,
    lastMessageTime, unread, from_bot, bot_enabled, human_takeover, contact_type,
    updated_at, client_name, client_id.
    """
    if not org_id:
        return []

    q = (
        db.query(WaConversation, WaContact)
        .join(WaContact, WaConversation.contact_id == WaContact.id)
        .filter(WaConversation.org_id == org_id, WaContact.org_id == org_id)
    )
    if not include_archived:
        q = q.filter(WaConversation.archived.is_(False))
    q = q.order_by(
        WaConversation.pinned.desc(),
        WaConversation.last_message_at.desc().nullslast(),
    ).limit(limit)

    rows = q.all()

    # Batch-fetch every conversation's last message in a single query. This
    # used to be one query per row -- a 1+N round-trip on the chat sidebar
    # load. See test_list_conversations_no_n_plus_one.
    last_message_ids = {
        conv.last_message_id for conv, _ in rows if conv.last_message_id
    }
    last_messages: dict = {}
    if last_message_ids:
        for msg in (
            db.query(WaMessage)
            .filter(
                WaMessage.org_id == org_id,
                WaMessage.id.in_(last_message_ids),
            )
            .all()
        ):
            last_messages[msg.id] = msg

    # Batch-fetch linked clients + owner users (avoid 1+N on the sidebar load).
    client_ids = {c.client_id for _, c in rows if c.client_id}
    client_map: dict = {}
    if client_ids:
        for cl in (
            db.query(Client)
            .filter(Client.org_id == org_id, Client.id.in_(client_ids))
            .all()
        ):
            client_map[cl.id] = cl
    owner_ids = {c.owner_user_id for _, c in rows if c.owner_user_id}
    owner_map: dict = {}
    if owner_ids:
        for u in (
            db.query(User)
            .filter(User.org_id == org_id, User.id.in_(owner_ids), User.enabled.is_(True))
            .all()
        ):
            owner_map[u.id] = u
    # Batched case lookup for the sidebar "Processo" badge: client_id -> case_number.
    case_map: dict = {}
    if client_ids:
        from models.case import Case
        for cs in (
            db.query(Case)
            .filter(Case.org_id == org_id, Case.client_id.in_(client_ids))
            .all()
        ):
            if cs.client_id not in case_map:
                case_map[cs.client_id] = cs.case_number or cs.numero_processo

    out: List[dict] = []
    for conv, contact in rows:
        last_msg = (
            last_messages.get(conv.last_message_id)
            if conv.last_message_id
            else None
        )
        last_at = conv.last_message_at.isoformat() if conv.last_message_at else None
        client = client_map.get(contact.client_id) if contact.client_id else None
        owner = _owner_dict(owner_map.get(contact.owner_user_id)) if contact.owner_user_id else None
        # Name priority: linked Client.full_name > WhatsApp display_name > phone.
        disp = (client.full_name if client else None) or contact.display_name or contact.phone
        out.append(
            {
                "phone": contact.phone,
                "name": disp,
                "whatsapp_name": contact.display_name,
                "profilePic": contact.profile_pic_url,
                "lastMessage": (last_msg.body if last_msg else "") or "",
                "lastMessageTime": last_at,
                "last_message_at": last_at,
                "updated_at": conv.updated_at.isoformat() if conv.updated_at else last_at,
                "unread": conv.unread_count or 0,
                "from_bot": 1 if (last_msg and last_msg.from_me) else 0,
                "bot_enabled": bool(conv.bot_enabled),
                "human_takeover": bool(conv.human_takeover),
                "never_contact": bool(conv.human_takeover) and not bool(conv.bot_enabled),
                "archived": bool(conv.archived),
                "pinned": bool(conv.pinned),
                "is_group": bool(contact.is_group),
                "is_business": bool(contact.is_business),
                "contact_type": "active_client" if contact.client_id else "lead",
                "client_id": contact.client_id,
                "client_name": client.full_name if client else None,
                "case_number": case_map.get(contact.client_id) if contact.client_id else None,
                "tags": contact.tags or [],
                "lead_stage": normalize_stage(contact.lead_stage),
                "owner": owner,
                "conversation_id": conv.id,
            }
        )
    return out


def list_messages(
    db: Session,
    *,
    org_id: int,
    phone: str,
    limit: int = 100,
) -> List[dict]:
    """Return the last `limit` messages for a phone, oldest-first, in chat.js shape.

    chat.js (renderWhatsAppMessages) reads: id, role, content, created_at, ack,
    media_type/media_url/mimetype/filename, hasMedia.
    """
    if not org_id:
        return []
    e164 = normalize_phone(phone)
    if not e164:
        return []

    contact = (
        db.query(WaContact)
        .filter(WaContact.org_id == org_id, WaContact.phone == e164)
        .first()
    )
    if contact is None:
        return []
    conv = (
        db.query(WaConversation)
        .filter(
            WaConversation.org_id == org_id,
            WaConversation.contact_id == contact.id,
        )
        .first()
    )
    if conv is None:
        return []

    rows = (
        db.query(WaMessage)
        .filter(
            WaMessage.org_id == org_id,
            WaMessage.conversation_id == conv.id,
        )
        .order_by(WaMessage.sent_at.desc(), WaMessage.id.desc())
        .limit(limit)
        .all()
    )
    # Reverse to oldest-first (chat.js renders top->bottom, scrolls to bottom).
    return [m.to_frontend_dict() for m in reversed(rows)]


def mark_conversation_read(
    db: Session,
    *,
    org_id: int,
    phone: str,
    commit: bool = True,
) -> bool:
    """Reset unread_count to 0 when the operator opens a thread."""
    if not org_id:
        return False
    e164 = normalize_phone(phone)
    if not e164:
        return False
    contact = (
        db.query(WaContact)
        .filter(WaContact.org_id == org_id, WaContact.phone == e164)
        .first()
    )
    if contact is None:
        return False
    conv = (
        db.query(WaConversation)
        .filter(
            WaConversation.org_id == org_id,
            WaConversation.contact_id == contact.id,
        )
        .first()
    )
    if conv is None:
        return False
    conv.unread_count = 0
    conv.updated_at = _now()
    if commit:
        db.commit()
    return True


def set_bot_enabled(
    db: Session,
    *,
    org_id: int,
    phone: str,
    enabled: bool,
    human_takeover: Optional[bool] = None,
    commit: bool = True,
) -> bool:
    """Toggle per-conversation bot / human-takeover state."""
    if not org_id:
        return False
    e164 = normalize_phone(phone)
    if not e164:
        return False
    contact = (
        db.query(WaContact)
        .filter(WaContact.org_id == org_id, WaContact.phone == e164)
        .first()
    )
    if contact is None:
        return False
    conv = (
        db.query(WaConversation)
        .filter(
            WaConversation.org_id == org_id,
            WaConversation.contact_id == contact.id,
        )
        .first()
    )
    if conv is None:
        return False
    conv.bot_enabled = bool(enabled)
    if human_takeover is not None:
        conv.human_takeover = bool(human_takeover)
    conv.updated_at = _now()
    if commit:
        db.commit()
    return True
