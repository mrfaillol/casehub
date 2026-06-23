"""
Regression tests for the kanban seed guard (T7-kanban-concluida-bug).

Bug: deleting the shared "Concluida" list (a soft-delete that sets
is_archived = TRUE) made the board re-seed ALL 4 default columns on the next
load, because the old guard counted only *active shared* columns. When the
last active shared column was archived, count == 0 and the seed ran again.

Fix: `_ensure_kanban_columns` now counts ANY column ever created for the org
(shared OR private, archived OR not). The seed therefore runs exactly once,
on an org's genuine first access, and never resurrects defaults after the
user has configured/cleaned their lists.

These tests drive the guard against an in-memory SQLite kanban_columns table
(the table is raw SQL, not a SQLAlchemy model, so we create it explicitly).
"""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from routes.tasks import _ensure_kanban_columns


# Mirrors the shape created by core/app_factory.py (visibility / is_archived
# included) so the guard and the seed INSERT both work on SQLite.
_CREATE_KANBAN_COLUMNS = """
    CREATE TABLE kanban_columns (
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
"""


@pytest.fixture
def kanban_db():
    """Isolated in-memory SQLite session with just the kanban_columns table."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    session.execute(text(_CREATE_KANBAN_COLUMNS))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _column_rows(db, org_id):
    return db.execute(
        text(
            "SELECT name, slug, visibility, COALESCE(is_archived, 0) AS is_archived "
            "FROM kanban_columns WHERE org_id = :o ORDER BY position"
        ),
        {"o": org_id},
    ).fetchall()


def _count_all(db, org_id):
    return db.execute(
        text("SELECT COUNT(*) FROM kanban_columns WHERE org_id = :o"),
        {"o": org_id},
    ).scalar() or 0


def _count_active_shared(db, org_id):
    return db.execute(
        text(
            "SELECT COUNT(*) FROM kanban_columns WHERE org_id = :o "
            "AND COALESCE(visibility, 'shared') = 'shared' "
            "AND COALESCE(is_archived, 0) = 0"
        ),
        {"o": org_id},
    ).scalar() or 0


class TestKanbanSeedGuard:
    ORG_ID = 4  # Escritorio Demo org id used in alpha; arbitrary for the test.

    def test_new_org_gets_four_defaults_once(self, kanban_db):
        """A genuinely new org (zero rows) receives the 4 default columns."""
        assert _count_all(kanban_db, self.ORG_ID) == 0

        _ensure_kanban_columns(kanban_db, self.ORG_ID)

        rows = _column_rows(kanban_db, self.ORG_ID)
        assert len(rows) == 4
        slugs = [r.slug for r in rows]
        assert slugs == ["pendente", "em_andamento", "blocked", "completed"]
        assert all(r.visibility == "shared" for r in rows)

    def test_idempotent_no_duplicate_defaults_on_second_load(self, kanban_db):
        """Calling the guard again on a seeded org must not duplicate columns."""
        _ensure_kanban_columns(kanban_db, self.ORG_ID)
        _ensure_kanban_columns(kanban_db, self.ORG_ID)

        assert _count_all(kanban_db, self.ORG_ID) == 4

    def test_deleting_last_shared_column_does_not_reseed(self, kanban_db):
        """Soft-deleting (archiving) every shared column must NOT re-create defaults.

        Reproduces the UsuarioDemo bug: after the seed runs, archive all 4 shared
        columns (as delete_column does, incl. the 'Concluida' list). On the
        next board load the guard runs again and must stay a no-op, leaving the
        board empty of *active* columns and NOT resurrecting the defaults.
        """
        _ensure_kanban_columns(kanban_db, self.ORG_ID)
        assert _count_active_shared(kanban_db, self.ORG_ID) == 4

        # Simulate delete_column's intentional soft-delete on every column.
        kanban_db.execute(
            text("UPDATE kanban_columns SET is_archived = 1 WHERE org_id = :o"),
            {"o": self.ORG_ID},
        )
        kanban_db.commit()
        assert _count_active_shared(kanban_db, self.ORG_ID) == 0

        # Next board load -> guard must NOT re-seed.
        _ensure_kanban_columns(kanban_db, self.ORG_ID)

        assert _count_all(kanban_db, self.ORG_ID) == 4  # still only the originals
        assert _count_active_shared(kanban_db, self.ORG_ID) == 0  # stays empty

    def test_deleting_only_concluida_does_not_revive_others(self, kanban_db):
        """Archiving just the shared 'Concluida' must not resurrect any list."""
        _ensure_kanban_columns(kanban_db, self.ORG_ID)

        kanban_db.execute(
            text(
                "UPDATE kanban_columns SET is_archived = 1 "
                "WHERE org_id = :o AND slug = 'completed'"
            ),
            {"o": self.ORG_ID},
        )
        kanban_db.commit()

        _ensure_kanban_columns(kanban_db, self.ORG_ID)

        # No re-seed: still exactly the 4 originals, 'completed' stays archived,
        # exactly one archived row, nothing revived.
        assert _count_all(kanban_db, self.ORG_ID) == 4
        archived = kanban_db.execute(
            text(
                "SELECT slug FROM kanban_columns "
                "WHERE org_id = :o AND COALESCE(is_archived, 0) = 1"
            ),
            {"o": self.ORG_ID},
        ).fetchall()
        assert [r.slug for r in archived] == ["completed"]

    def test_private_columns_not_resurrected_when_shared_deleted(self, kanban_db):
        """User-created private (MEU QUADRO) lists are untouched by re-seed guard.

        After seeding defaults, the user adds a private column and deletes the
        shared 'Concluida'. The guard must not re-seed nor disturb the private
        column.
        """
        _ensure_kanban_columns(kanban_db, self.ORG_ID)

        # User creates a private column on their personal board.
        kanban_db.execute(
            text(
                "INSERT INTO kanban_columns "
                "(org_id, name, slug, position, color, is_done, visibility, owner_user_id, is_archived) "
                "VALUES (:o, 'Minha Lista', 'minha_lista', 4, '#a855f7', 0, 'private', 7, 0)"
            ),
            {"o": self.ORG_ID},
        )
        kanban_db.commit()

        # Delete (archive) the shared 'Concluida'.
        kanban_db.execute(
            text(
                "UPDATE kanban_columns SET is_archived = 1 "
                "WHERE org_id = :o AND slug = 'completed'"
            ),
            {"o": self.ORG_ID},
        )
        kanban_db.commit()

        _ensure_kanban_columns(kanban_db, self.ORG_ID)

        # 4 defaults + 1 private == 5 rows; no re-seed.
        assert _count_all(kanban_db, self.ORG_ID) == 5
        private = kanban_db.execute(
            text(
                "SELECT name, COALESCE(is_archived, 0) AS is_archived "
                "FROM kanban_columns WHERE org_id = :o AND visibility = 'private'"
            ),
            {"o": self.ORG_ID},
        ).fetchall()
        assert len(private) == 1
        assert private[0].name == "Minha Lista"
        assert private[0].is_archived == 0  # untouched / not resurrected
