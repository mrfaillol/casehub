"""Functional tests for WhatsApp CRM Phase-1: owner-tag + name priority + intake funnel.

Exercises the real services/whatsapp_clone_service code paths against an in-memory
sqlite DB. Guards the runtime behavior (tenant isolation, name resolution, owner
badge, funnel normalization, from_bot direction, disabled-owner hiding).
"""
import os
os.environ.setdefault("SECRET_KEY", "test-secret-1234567890")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("CASEHUB_PRODUCT", "lite")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.base import Base
import models  # noqa: F401 — populate metadata with every table
from models.user import User
from models.client import Client
from models.tenant import Organization
from models.whatsapp_clone import WaContact, WaConversation, WaMessage
import services.whatsapp_clone_service as wcs


@pytest.fixture(scope="module")
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add_all([Organization(id=1, uuid="u-a", name="Org A", slug="a"),
               Organization(id=2, uuid="u-b", name="Org B", slug="b")])
    s.flush()

    def mkuser(uid, org, name, color, enabled=True):
        s.add(User(id=uid, org_id=org, email=f"u{uid}@x.com", name=name,
                   password_hash="x", enabled=enabled, color=color))
    mkuser(10, 1, "[parceiro] o cliente", "#7c3aed")   # explicit purple
    mkuser(11, 1, "Ana Costa", "#1C2447")             # DB default -> palette
    mkuser(12, 1, "Disabled Dan", "#059669", enabled=False)
    mkuser(20, 2, "Bruno OutraOrg", "#7c3aed")        # other org
    s.add(Client(id=5, org_id=1, first_name="João", last_name="Silva"))
    s.flush()

    def contact(cid, org, phone, dn, client_id, owner, stage):
        c = WaContact(id=cid, org_id=org, phone=phone, display_name=dn,
                      client_id=client_id, owner_user_id=owner, lead_stage=stage)
        s.add(c); s.flush()
        conv = WaConversation(org_id=org, contact_id=c.id); s.add(conv); s.flush()
        return conv
    v1 = contact(1, 1, "+551", "Ze", 5, 10, "cold")       # client-linked, owned, legacy stage
    v2 = contact(2, 1, "+552", "Maria", None, None, "reuniao")
    contact(3, 1, "+553", None, None, None, None)         # no name/owner/stage
    contact(4, 1, "+554", "Disabled Owner", None, 12, "novo")  # owner disabled
    contact(9, 2, "+559", "OrgB", None, 20, "novo")       # other org
    # Last message: c1 outgoing (we replied) -> from_bot=1; c2 incoming -> needs response.
    m_out = WaMessage(org_id=1, conversation_id=v1.id, body="reply",
                      from_me=True, direction="outgoing", ai_generated=False)
    s.add(m_out); s.flush(); v1.last_message_id = m_out.id
    m_in = WaMessage(org_id=1, conversation_id=v2.id, body="oi",
                     from_me=False, direction="incoming")
    s.add(m_in); s.flush(); v2.last_message_id = m_in.id
    s.commit()
    return s


def _rows(db):
    return {r["phone"]: r for r in wcs.list_conversations(db, org_id=1)}


def test_tenant_isolation(db):
    r = _rows(db)
    assert "+559" not in r          # org2 contact not visible to org1
    assert len(r) == 4


def test_name_priority(db):
    r = _rows(db)
    assert r["+551"]["name"] == "João Silva"   # linked client full_name wins
    assert r["+552"]["name"] == "Maria"        # display_name fallback
    assert r["+553"]["name"] == "+553"         # phone fallback


def test_owner_badge_shape(db):
    r = _rows(db)
    assert r["+551"]["owner"] == {"user_id": 10, "name": "[parceiro] o cliente", "color": "#7c3aed"}
    assert r["+552"]["owner"] is None


def test_disabled_owner_hidden(db):
    r = _rows(db)
    assert r["+554"]["owner"] is None          # disabled owner -> badge hidden
    assert wcs.resolve_owner(db, 1, 12) is None


def test_funnel_normalization(db):
    r = _rows(db)
    assert r["+551"]["lead_stage"] == "novo"   # legacy cold -> novo
    assert r["+552"]["lead_stage"] == "reuniao"
    assert r["+553"]["lead_stage"] == "novo"   # null -> novo


def test_from_bot_reflects_direction(db):
    r = _rows(db)
    assert r["+551"]["from_bot"] == 1          # outgoing/from_me -> NOT needs-response
    assert r["+552"]["from_bot"] == 0          # incoming -> needs response


def test_resolve_owner_tenant_isolation(db):
    assert wcs.resolve_owner(db, 1, 10)["name"] == "[parceiro] o cliente"
    assert wcs.resolve_owner(db, 2, 10) is None   # cross-org -> None (no leak)
    assert wcs.resolve_owner(db, 1, None) is None


def test_normalize_stage():
    assert wcs.normalize_stage("cold") == "novo"
    assert wcs.normalize_stage("") == "novo"
    assert wcs.normalize_stage(None) == "novo"
    assert wcs.normalize_stage("REUNIAO") == "reuniao"
    assert wcs.normalize_stage("xyz") == "novo"
    assert wcs.normalize_stage("qualified") == "reuniao"


def test_owner_color_default_handling():
    class _U:
        pass
    explicit = _U(); explicit.id = 10; explicit.color = "#7c3aed"
    default = _U(); default.id = 11; default.color = "#1C2447"
    assert wcs.owner_color(explicit) == "#7c3aed"
    c = wcs.owner_color(default)
    assert c in wcs.OWNER_PALETTE and c != "#1C2447"


def test_contact_notes_crud_and_tenant(db):
    # contact id 1 belongs to org 1; user 10 ([parceiro]) is the author.
    n = wcs.add_note(db, 1, 1, 10, "  primeira nota  ")
    assert n["body"] == "primeira nota"                 # trimmed
    assert n["author_name"] == "[parceiro] o cliente"    # author resolved
    assert wcs.add_note(db, 1, 1, 10, "   ") is None     # empty body -> None
    notes = wcs.list_notes(db, 1, 1)
    assert len(notes) == 1 and notes[0]["body"] == "primeira nota"
    # tenant isolation: org 2 cannot read a note stored under org 1
    assert wcs.list_notes(db, 2, 1) == []
    # tenant-scoped delete: org 2 cannot delete org 1's note; org 1 can
    assert wcs.delete_note(db, 2, n["id"]) is False
    assert wcs.delete_note(db, 1, n["id"]) is True
    assert wcs.list_notes(db, 1, 1) == []


def test_follow_up_schedule_and_overdue(db):
    import datetime as _dt
    res = wcs.schedule_follow_up(db, 1, 1, _dt.date(2020, 1, 1), "ligar de volta")
    assert res["follow_up_date"] == "2020-01-01" and res["follow_up_note"] == "ligar de volta"
    overdue = wcs.get_overdue_follow_ups(db, 1, _dt.date(2020, 1, 10))
    o = next((x for x in overdue if x["contact_id"] == 1), None)
    assert o is not None and o["days_overdue"] == 9
    # tenant: org 2 never sees org 1's follow-up
    assert 1 not in [x["contact_id"] for x in wcs.get_overdue_follow_ups(db, 2, _dt.date(2020, 1, 10))]
    # clearing (date=None) removes it from overdue
    wcs.schedule_follow_up(db, 1, 1, None)
    assert 1 not in [x["contact_id"] for x in wcs.get_overdue_follow_ups(db, 1, _dt.date(2020, 1, 10))]


def test_check_duplicates_org_scoped(db):
    from models.whatsapp_clone import WaContact
    a = WaContact(org_id=1, phone="+5511999990000", normalized_phone="5511999990000")
    b = WaContact(org_id=1, phone="11999990000", normalized_phone="11999990000")  # same last-10
    z = WaContact(org_id=2, phone="+5511999990000", normalized_phone="5511999990000")  # other org
    db.add_all([a, b, z]); db.commit()
    dups = wcs.check_duplicates(db, 1, "+5511999990000", exclude_contact_id=a.id)
    ids = {d["contact_id"] for d in dups}
    assert b.id in ids       # org-1 sibling matched by last-10 digits
    assert z.id not in ids   # org-2 NOT visible (tenant isolation — Council red line)
    assert a.id not in ids   # self excluded
    assert wcs.check_duplicates(db, 1, "123") == []  # too short to dedup


def test_org_templates_crud_tenant(db):
    t = wcs.create_template(db, 1, "Saudação VS", "Olá, aqui é o escritório.", category="greeting")
    assert t.id and t.name == "Saudação VS"
    assert t.to_dict()["id"] == "c%d" % t.id and t.to_dict()["is_custom"] is True
    assert t.body_for("es") == t.body_pt          # no body_es -> falls back to pt
    # list is org-scoped: org 1 sees it, org 2 does not
    assert t.id in [x.id for x in wcs.list_org_templates(db, 1)]
    assert t.id not in [x.id for x in wcs.list_org_templates(db, 2)]
    # update own-org
    u = wcs.update_template(db, 1, t.id, name="Saudação 2", body_en="Hello")
    assert u.name == "Saudação 2" and u.body_en == "Hello"
    # org 2 cannot edit/delete org 1's template (tenant isolation)
    assert wcs.update_template(db, 2, t.id, name="hack") is None
    assert wcs.delete_template(db, 2, t.id) is False
    # delete own
    assert wcs.delete_template(db, 1, t.id) is True
    assert wcs.list_org_templates(db, 1) == []


def test_lead_score_deterministic_and_normalized(db):
    from models.whatsapp_clone import WaContact, WaConversation, WaMessage
    c = WaContact(org_id=1, phone="+5511777770000", lead_stage="reuniao", client_id=5)
    db.add(c); db.flush()
    cv = WaConversation(org_id=1, contact_id=c.id); db.add(cv); db.flush()
    for txt in ["Preciso de uma consulta",
                "Quero agendar uma audiência sobre meu processo",
                "Sobre os honorários"]:
        db.add(WaMessage(org_id=1, conversation_id=cv.id, body=txt,
                         from_me=False, direction="incoming"))
    db.commit()
    s1 = wcs.compute_lead_score(db, 1, c)
    assert s1 == wcs.compute_lead_score(db, 1, c)          # deterministic
    assert isinstance(s1, int)
    # eng 12 (3 msgs) + intent 30 (consulta/agendar/audiência/processo/honorários) + reuniao 14 + vínculo 10
    assert s1 == 66
    # accent normalization (NFKD+casefold): accented PT-BR legal terms still match
    assert wcs._intent_keyword_matches(["audiência", "petição", "ação"]) == 3
    # terminal stage scores its bucket (descartado = 0 stage points)
    c.lead_stage = "descartado"
    assert wcs.compute_lead_score(db, 1, c) == 12 + 30 + 0 + 10
    # clamped 0..100 and no keyword false-positives on empty
    assert wcs._intent_keyword_matches([]) == 0


def test_case_number_in_sidebar(db):
    from models.case import Case
    db.add(Case(org_id=1, client_id=5, case_number="0001234-56.2026"))
    db.commit()
    rows = {r["phone"]: r for r in wcs.list_conversations(db, org_id=1)}
    assert rows["+551"]["case_number"] == "0001234-56.2026"  # contact 1 linked to client 5
    assert rows["+552"]["case_number"] is None               # unlinked contact -> no Processo badge


def test_stage_history_capture_and_tenant(db):
    h = wcs.record_stage_change(db, 1, 1, "novo", "reuniao", actor_user_id=10, reason="manual")
    assert h is not None and h.to_stage == "reuniao"
    assert wcs.record_stage_change(db, 1, 1, "reuniao", "reuniao") is None   # no-op: unchanged
    hist = wcs.list_stage_history(db, 1, 1)
    assert any(x["from_stage"] == "novo" and x["to_stage"] == "reuniao" for x in hist)
    # tenant isolation: org 2 never sees org 1's history
    assert wcs.list_stage_history(db, 2, 1) == []


def test_funnel_analytics_org_scoped(db):
    import datetime as _dt
    m = wcs.compute_funnel_analytics(db, 1, _dt.date(2030, 1, 1))
    assert m["total"] >= 1
    assert set(m["by_stage"].keys()) == set(wcs.LEAD_STAGES)
    assert 0 <= m["conversion_pct"] <= 100
    assert "avg_score" in m and "overdue" in m and "avg_days_to_win" in m
    # org 2 analytics computed independently (no cross-org mixing)
    m2 = wcs.compute_funnel_analytics(db, 2, _dt.date(2030, 1, 1))
    assert m2["total"] >= 1
    assert m["total"] + m2["total"] >= 2


def test_suggest_next_stage_promote_only(db):
    from models.whatsapp_clone import WaContact
    c = WaContact(org_id=1, phone="+5599", lead_stage="novo", lead_score=75)
    assert wcs.suggest_next_stage(c) == "proposta"   # high score -> suggest advance
    c.lead_score = 35
    assert wcs.suggest_next_stage(c) == "triagem"
    c.lead_score = 10
    assert wcs.suggest_next_stage(c) is None          # low score -> no move (no demote)
    c.lead_stage = "proposta"; c.lead_score = 90
    assert wcs.suggest_next_stage(c) is None          # already top of order
    c.lead_stage = "cliente"; c.lead_score = 90
    assert wcs.suggest_next_stage(c) is None          # terminal untouched (never demote)
