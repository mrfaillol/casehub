from types import SimpleNamespace

import pytest
from sqlalchemy import text

from services import work_intelligence as wi


def _create_support_tables(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS org_settings (
            org_id INTEGER NOT NULL,
            key VARCHAR(120) NOT NULL,
            value TEXT,
            PRIMARY KEY (org_id, key)
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS work_intelligence_events (
            id INTEGER PRIMARY KEY,
            org_id INTEGER NOT NULL,
            user_id INTEGER,
            event_type VARCHAR(80) NOT NULL,
            route VARCHAR(255),
            surface VARCHAR(120),
            duration_ms INTEGER,
            metadata TEXT,
            source VARCHAR(40),
            session_hash VARCHAR(64),
            occurred_at TIMESTAMP,
            created_at TIMESTAMP
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY,
            org_id INTEGER,
            action VARCHAR(100),
            entity_type VARCHAR(100),
            entity_id INTEGER,
            user_id INTEGER,
            user_email VARCHAR(255),
            description TEXT,
            details TEXT,
            ip_address VARCHAR(100),
            user_agent VARCHAR(500),
            created_at TIMESTAMP
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS work_intelligence_feedback (
            id INTEGER PRIMARY KEY,
            org_id INTEGER NOT NULL,
            user_id INTEGER,
            insight_id INTEGER,
            feedback_type VARCHAR(40) NOT NULL,
            usefulness INTEGER,
            comment_redacted TEXT,
            created_at TIMESTAMP
        )
    """))
    for table_name in (
        "work_intelligence_feedback",
        "work_intelligence_events",
        "audit_log",
        "org_settings",
    ):
        db.execute(text(f"DELETE FROM {table_name}"))
    db.execute(text("""
        INSERT INTO org_settings (org_id, key, value)
        VALUES
            (1, 'work_intelligence_enabled', 'true'),
            (1, 'work_intelligence_client_events_enabled', 'true')
    """))
    db.commit()


def _enable_flags(monkeypatch):
    monkeypatch.setattr(wi.settings, "CASEHUB_WORK_INTELLIGENCE_ENABLED", True, raising=False)
    monkeypatch.setattr(wi.settings, "CASEHUB_WORK_INTELLIGENCE_CLIENT_EVENTS_ENABLED", True, raising=False)


def _seed_users(db):
    rows = [
        (1, 1, "usuario_demo@example.com", "UsuarioDemo", "admin"),
        (2, 1, "pessoa_demo@example.com", "PessoaDemo", "case_worker"),
        (3, 1, "pessoa_demo@example.com", "PessoaDemo", "case_worker"),
        (4, 1, "casehub_team@example.com", "Equipe CaseHub", "superadmin"),
        (5, 2, "other@example.com", "Other", "case_worker"),
    ]
    for row in rows:
        db.execute(
            text("""
                INSERT INTO users (id, org_id, email, name, password_hash, user_type, enabled)
                VALUES (:id, :org_id, :email, :name, 'hash', :user_type, TRUE)
            """),
            {
                "id": row[0],
                "org_id": row[1],
                "email": row[2],
                "name": row[3],
                "user_type": row[4],
            },
        )
    db.commit()


def test_sanitize_client_event_rejects_sensitive_keys():
    with pytest.raises(ValueError):
        wi.sanitize_client_event({
            "event_type": "action",
            "route": "/casehub/tasks",
            "metadata": {"value": "typed text"},
        })

    with pytest.raises(ValueError):
        wi.sanitize_client_event({
            "event_type": "action",
            "route": "/casehub/tasks",
            "metadata": {"cursor": {"x": 1, "y": 2}},
        })


def test_client_event_ingestion_is_default_off_and_excludes_dev_users(db, monkeypatch):
    _create_support_tables(db)
    _seed_users(db)
    casehub_team = SimpleNamespace(id=4, email="casehub_team@example.com", name="Equipe CaseHub", user_type="superadmin")
    event = {"event_type": "page_view", "route": "/casehub/tasks/kanban", "session_id": "s1"}

    monkeypatch.setattr(wi.settings, "CASEHUB_WORK_INTELLIGENCE_ENABLED", False, raising=False)
    assert wi.record_client_events(db, org_id=1, user=casehub_team, events=[event])["status"] == "disabled"

    _enable_flags(monkeypatch)
    assert wi.record_client_events(db, org_id=1, user=casehub_team, events=[event])["status"] == "excluded_user"
    assert db.execute(text("SELECT COUNT(*) FROM work_intelligence_events")).scalar() == 0


def test_summary_is_tenant_scoped_and_excludes_dev_qa_rows(db, monkeypatch):
    _create_support_tables(db)
    _seed_users(db)
    _enable_flags(monkeypatch)
    db.execute(text("""
        INSERT INTO tasks (org_id, title, status, assigned_to, due_date, created_at)
        VALUES
            (1, 'real task', 'pending', 1, DATE('now', '-1 day'), CURRENT_TIMESTAMP),
            (1, 'dev task', 'pending', 4, DATE('now', '-1 day'), CURRENT_TIMESTAMP),
            (2, 'other tenant', 'pending', 5, DATE('now', '-1 day'), CURRENT_TIMESTAMP)
    """))
    db.execute(text("""
        INSERT INTO work_intelligence_events
            (org_id, user_id, event_type, route, source, occurred_at, created_at)
        VALUES
            (1, 1, 'api_error', '/casehub/tasks', 'client', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (1, 4, 'api_error', '/casehub/dev', 'client', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
            (2, 5, 'api_error', '/casehub/other', 'client', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """))
    db.commit()

    summary = wi.build_summary(db, org_id=1, days=7)

    assert summary["suppressed"] is False
    assert summary["active_real_users"] == 3
    assert summary["excluded_user_count"] == 1
    assert summary["sources"]["tasks"]["total"] == 1
    assert summary["sources"]["client_events"]["errors"] == 1
    assert "/casehub/other" not in str(summary)
    assert "/casehub/dev" not in str(summary)


def test_maestro_context_contains_only_aggregate_redacted_insights(db, monkeypatch):
    _create_support_tables(db)
    _seed_users(db)
    _enable_flags(monkeypatch)
    db.execute(text("""
        INSERT INTO tasks (org_id, title, status, assigned_to, due_date, created_at)
        VALUES (1, 'Mensagem secreta do cliente', 'pending', 1, DATE('now', '-1 day'), CURRENT_TIMESTAMP)
    """))
    db.execute(text("""
        INSERT INTO work_intelligence_events
            (org_id, user_id, event_type, route, metadata, source, occurred_at, created_at)
        VALUES
            (1, 1, 'api_error', '/casehub/tasks', '{"action_id":"save"}', 'client', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """))
    db.commit()

    context = wi.build_maestro_context(db, org_id=1, user=SimpleNamespace(id=1))

    assert "Work Intelligence" in context
    assert "log cru" in context
    assert "Mensagem secreta do cliente" not in context
    assert "ranking individual" in context


def test_audit_log_action_persists_org_id_from_context(db):
    _create_support_tables(db)
    from services.audit import log_action, set_audit_context

    set_audit_context(user_id=1, user_email="usuario_demo@example.com", org_id=41)
    log_action(db, action="manual", entity_type="case", entity_id=9, user_id=1)

    row = db.execute(text("SELECT org_id FROM audit_log WHERE entity_id = 9")).fetchone()
    assert row[0] == 41
