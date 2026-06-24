"""FB2 (alpha UsuarioDemo) — arquivar cartões do Kanban (soft-archive).

Antes só existia "Excluir" (hard delete via db.delete) e somente kanban_columns
tinha is_archived. Estes testes cobrem o soft-archive de TAREFAS:
  - migração idempotente adiciona tasks.is_archived + tasks.archived_at
  - POST /tasks/api/{id}/archive seta is_archived=TRUE (não deleta)
  - POST /tasks/api/{id}/unarchive volta is_archived=FALSE
  - o board do Kanban exclui tarefas arquivadas
  - bulk POST /tasks/api/columns/{col_id}/archive-cards arquiva os cartões da lista
  - tudo org-scoped: cross-tenant nunca arquiva nem vaza (Sentinela).
"""
from __future__ import annotations

import inspect
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import routes.tasks as task_routes
from models import Organization, Task, User
from routes.tasks import (
    _ensure_kanban_schema,
    _not_archived_task_filter,
    archive_task_api,
    unarchive_task_api,
    archive_column_cards_api,
    kanban_view,
)


def _create_org_user(db, *, org_id=1, user_id=1, user_type="admin", name="User"):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        org = Organization(id=org_id, uuid=f"org-{org_id}", name=f"Org {org_id}", slug=f"org-{org_id}")
        db.add(org)
    user = User(
        id=user_id,
        org_id=org_id,
        email=f"user{user_id}@org{org_id}.test",
        name=name,
        password_hash="hash",
        user_type=user_type,
        enabled=True,
    )
    db.add(user)
    db.flush()
    return org, user


def _create_kanban_tables(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS kanban_columns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER NOT NULL,
            name VARCHAR(120) NOT NULL,
            slug VARCHAR(80) NOT NULL,
            position INTEGER DEFAULT 0,
            color VARCHAR(20) DEFAULT '#94a3b8',
            is_done BOOLEAN DEFAULT 0,
            visibility VARCHAR(20) DEFAULT 'shared',
            owner_user_id INTEGER,
            is_archived BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS task_kanban_placements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER NOT NULL,
            task_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            column_id INTEGER NOT NULL,
            position INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, task_id)
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS task_assignees (
            task_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (task_id, user_id)
        )
    """))
    # Estas tabelas usam CREATE TABLE IF NOT EXISTS e NÃO são geridas pelo
    # Base.metadata do conftest — logo sobrevivem ao drop_all entre testes. Limpamos
    # explicitamente p/ isolar o board de colunas/placements vazados de outros testes.
    db.execute(text("DELETE FROM kanban_columns"))
    db.execute(text("DELETE FROM task_kanban_placements"))
    db.execute(text("DELETE FROM task_assignees"))
    db.commit()


class JsonRequest(SimpleNamespace):
    async def json(self):
        return getattr(self, "payload", {})


def _json_body(response):
    return json.loads(response.body.decode("utf-8"))


def _is_archived(db, task_id):
    return db.execute(
        text("SELECT COALESCE(is_archived, FALSE) FROM tasks WHERE id = :id"),
        {"id": task_id},
    ).scalar()


# ── Migração idempotente ────────────────────────────────────────────────────

def test_ensure_kanban_schema_adds_task_archive_columns(db):
    _create_kanban_tables(db)
    _ensure_kanban_schema(db)
    cols = {row[1] for row in db.execute(text("PRAGMA table_info(tasks)")).fetchall()}
    assert "is_archived" in cols
    assert "archived_at" in cols
    # Idempotente: rodar de novo não explode.
    _ensure_kanban_schema(db)


def test_ensure_kanban_schema_registers_task_archive_additions():
    source = inspect.getsource(task_routes._ensure_kanban_schema)
    assert '("tasks", "is_archived"' in source
    assert '("tasks", "archived_at"' in source


def test_archive_migration_sql_is_idempotent():
    with open("migrations/2026-06-17_task_archive.sql", encoding="utf-8") as fh:
        sql = fh.read()
    assert "ADD COLUMN IF NOT EXISTS is_archived" in sql
    assert "ADD COLUMN IF NOT EXISTS archived_at" in sql


# ── archive / unarchive endpoint ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_archive_endpoint_sets_is_archived_without_delete(db, monkeypatch):
    _create_kanban_tables(db)
    _ensure_kanban_schema(db)
    _, user = _create_org_user(db, org_id=1, user_id=1)
    task = Task(org_id=1, title="Arquivar", status="pending", created_by=user.id)
    db.add(task)
    db.commit()
    monkeypatch.setattr(task_routes, "get_current_user", lambda request, db: user)
    request = JsonRequest(state=SimpleNamespace(org_id=1), payload={})

    response = await archive_task_api(request, task.id, db=db)
    body = _json_body(response)

    assert response.status_code == 200
    assert body["success"] is True
    assert body["task_id"] == task.id
    # Não deletou — a linha ainda existe, só marcada como arquivada.
    assert db.query(Task).filter(Task.id == task.id).count() == 1
    assert bool(_is_archived(db, task.id)) is True
    archived_at = db.execute(
        text("SELECT archived_at FROM tasks WHERE id = :id"), {"id": task.id}
    ).scalar()
    assert archived_at is not None


@pytest.mark.asyncio
async def test_unarchive_endpoint_clears_is_archived(db, monkeypatch):
    _create_kanban_tables(db)
    _ensure_kanban_schema(db)
    _, user = _create_org_user(db, org_id=1, user_id=1)
    task = Task(org_id=1, title="Restaurar", status="pending", created_by=user.id)
    db.add(task)
    db.commit()
    db.execute(text("UPDATE tasks SET is_archived = TRUE WHERE id = :id"), {"id": task.id})
    db.commit()
    monkeypatch.setattr(task_routes, "get_current_user", lambda request, db: user)
    request = JsonRequest(state=SimpleNamespace(org_id=1), payload={})

    response = await unarchive_task_api(request, task.id, db=db)
    body = _json_body(response)

    assert response.status_code == 200
    assert body["success"] is True
    assert bool(_is_archived(db, task.id)) is False


@pytest.mark.asyncio
async def test_archive_endpoint_cross_tenant_returns_404(db, monkeypatch):
    """Sentinela: arquivar tarefa de OUTRA org retorna 404 e não muda nada."""
    _create_kanban_tables(db)
    _ensure_kanban_schema(db)
    _, attacker = _create_org_user(db, org_id=1, user_id=1, name="Attacker")
    _create_org_user(db, org_id=2, user_id=2, name="Victim")
    victim_task = Task(org_id=2, title="Tarefa da vítima", status="pending", created_by=2)
    db.add(victim_task)
    db.commit()
    monkeypatch.setattr(task_routes, "get_current_user", lambda request, db: attacker)
    request = JsonRequest(state=SimpleNamespace(org_id=1), payload={})

    response = await archive_task_api(request, victim_task.id, db=db)

    assert response.status_code == 404
    assert bool(_is_archived(db, victim_task.id)) is False


# ── Board exclui arquivados ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_kanban_board_excludes_archived_tasks(db, monkeypatch):
    _create_kanban_tables(db)
    _ensure_kanban_schema(db)
    _, user = _create_org_user(db, org_id=1, user_id=1)
    db.execute(text("""
        INSERT INTO kanban_columns (org_id, name, slug, position, color, is_done, visibility)
        VALUES (1, 'A Fazer', 'todo', 0, '#888', 0, 'shared')
    """))
    db.commit()
    visible = Task(org_id=1, title="Visível", status="pending", created_by=user.id)
    archived = Task(org_id=1, title="Arquivada", status="pending", created_by=user.id)
    db.add_all([visible, archived])
    db.commit()
    db.execute(text("UPDATE tasks SET is_archived = TRUE WHERE id = :id"), {"id": archived.id})
    db.commit()

    monkeypatch.setattr(task_routes, "get_current_user", lambda request, db: user)
    monkeypatch.setattr(task_routes, "get_context", lambda request, db: {"request": request, "PREFIX": "/casehub"})
    captured = {}

    def fake_template_response(template_name, context):
        captured["context"] = context
        return SimpleNamespace(template=template_name, context=context)

    monkeypatch.setattr(task_routes.templates, "TemplateResponse", fake_template_response)
    request = SimpleNamespace(
        state=SimpleNamespace(org_id=1),
        query_params={"board": "org"},
    )

    await kanban_view(request, db=db)

    all_titles = [
        t.title
        for col in captured["context"]["kanban_columns"]
        for t in col["tasks"]
    ]
    assert "Visível" in all_titles
    assert "Arquivada" not in all_titles


# ── Bulk archive de uma lista ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bulk_archive_column_cards_archives_only_that_column_in_org(db, monkeypatch):
    _create_kanban_tables(db)
    _ensure_kanban_schema(db)
    _, user = _create_org_user(db, org_id=1, user_id=1, user_type="admin")
    col_id = db.execute(text("""
        INSERT INTO kanban_columns (org_id, name, slug, position, color, is_done, visibility)
        VALUES (1, 'A Fazer', 'todo', 0, '#888', 0, 'shared') RETURNING id
    """)).scalar()
    other_col = db.execute(text("""
        INSERT INTO kanban_columns (org_id, name, slug, position, color, is_done, visibility)
        VALUES (1, 'Feito', 'done', 1, '#888', 1, 'shared') RETURNING id
    """)).scalar()
    t_in = Task(org_id=1, title="Na lista", status="pending", column_id=col_id, created_by=user.id)
    t_out = Task(org_id=1, title="Outra lista", status="completed", column_id=other_col, created_by=user.id)
    db.add_all([t_in, t_out])
    db.commit()

    monkeypatch.setattr(task_routes, "get_current_user", lambda request, db: user)
    request = JsonRequest(state=SimpleNamespace(org_id=1), payload={})

    response = await archive_column_cards_api(request, col_id, db=db)
    body = _json_body(response)

    assert response.status_code == 200
    assert body["success"] is True
    assert body["archived"] == 1
    assert bool(_is_archived(db, t_in.id)) is True
    assert bool(_is_archived(db, t_out.id)) is False


@pytest.mark.asyncio
async def test_bulk_archive_column_cards_cross_tenant_noop(db, monkeypatch):
    """Bulk archive nunca toca cartões de outra org (mesmo col_id colidindo)."""
    _create_kanban_tables(db)
    _ensure_kanban_schema(db)
    _, attacker = _create_org_user(db, org_id=1, user_id=1, name="Attacker", user_type="admin")
    _create_org_user(db, org_id=2, user_id=2, name="Victim")
    victim_col = db.execute(text("""
        INSERT INTO kanban_columns (org_id, name, slug, position, color, is_done, visibility)
        VALUES (2, 'Vítima', 'todo', 0, '#888', 0, 'shared') RETURNING id
    """)).scalar()
    victim_task = Task(org_id=2, title="Cartão da vítima", status="pending", column_id=victim_col, created_by=2)
    db.add(victim_task)
    db.commit()

    monkeypatch.setattr(task_routes, "get_current_user", lambda request, db: attacker)
    request = JsonRequest(state=SimpleNamespace(org_id=1), payload={})

    response = await archive_column_cards_api(request, victim_col, db=db)

    # Coluna não pertence à org do atacante → 404 (sem arquivar nada da vítima).
    assert response.status_code == 404
    assert bool(_is_archived(db, victim_task.id)) is False


def test_not_archived_filter_uses_coalesce_false():
    """O filtro do board precisa tratar legado (NULL) como não-arquivado."""
    source = inspect.getsource(task_routes._not_archived_task_filter)
    assert "is_archived" in source


# ── Template (botões Arquivar) ──────────────────────────────────────────────

def test_kanban_template_has_archive_buttons():
    with open("templates/app/tasks/kanban.html", encoding="utf-8") as fh:
        template = fh.read()
    # Botão por-cartão no modal (ao lado de Excluir).
    assert "ch-task-modal-archive" in template
    assert "/archive" in template
    # Botão bulk na lista (arquivar todos os cartões da coluna).
    assert "data-column-archive-cards" in template
    assert "/archive-cards" in template
