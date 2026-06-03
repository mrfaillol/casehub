from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def _sqlite_columns(conn, table_name):
    return {row[1] for row in conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()}


def test_pending_migrations_backfill_clients_and_process_tables(monkeypatch):
    from core import app_factory
    import models.base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Session = sessionmaker(bind=engine)

    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE clients (id INTEGER PRIMARY KEY AUTOINCREMENT)"))
        conn.execute(text("CREATE TABLE cases (id INTEGER PRIMARY KEY AUTOINCREMENT)"))
        conn.execute(text("CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT)"))
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT)"))
        conn.execute(text("CREATE TABLE prazos_processuais (id INTEGER PRIMARY KEY AUTOINCREMENT)"))

    monkeypatch.setattr(models.base, "SessionLocal", Session)

    app_factory._run_pending_migrations()

    with engine.connect() as conn:
        client_columns = _sqlite_columns(conn, "clients")
        assert {"first_name", "last_name", "client_number", "cpf", "org_id", "status"} <= client_columns

        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'table'")
            ).fetchall()
        }
        assert {
            "audit_log",
            "case_processes",
            "process_steps",
            "case_process_tracking",
            "case_step_progress",
        } <= tables

        audit_columns = _sqlite_columns(conn, "audit_log")
        assert {"action", "entity_type", "entity_id", "user_email", "details", "created_at"} <= audit_columns

        process_columns = _sqlite_columns(conn, "case_processes")
        assert {"org_id", "name", "area_of_practice", "enabled"} <= process_columns
