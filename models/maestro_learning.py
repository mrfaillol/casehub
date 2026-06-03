"""CaseHub — Maestro Learning Entry model.

User-scoped corpus that the Maestro Lite chat assistant
(``services/maestro_lite.py``) can pull into its context window so the
lawyer's assistant "remembers" things the firm taught it (style notes,
client-specific glossary, jurisprudential snippets, internal SOPs).

Each entry is **user-specific** (not org-shared) on purpose: lawyers in
the same office may want different corpora — a senior associate's notes
on a specific judge, a junior's translation cheatsheet, etc. The chat
flow filters by ``user_id`` before assembling context.

Privacy contract:
- ``content`` is plain text, not encrypted at rest (it is the *user's*
  notes, not PII). Add column-level encryption later if the lawyer
  community asks.
- A user can only see/edit/delete **their own** entries. The route layer
  enforces this with ``tenant_query`` + a ``user_id == current_user.id``
  filter — never trust the client-side ``id`` alone.

Authority: goal frente D (alpha-pretty-critical) — Maestro learning
space backend. Feature flag ``CASEHUB_MAESTRO_LEARNING_ENABLED`` gates
the routes so the infra ships in alpha without enabling the feature
until Council greenlights the pipeline (per
``docs/casehub-alpha/primeiros-passos.md``).
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from .base import Base


class MaestroLearningEntry(Base):
    """A user-authored knowledge fragment for the Maestro Lite assistant.

    The chat flow at ``services/maestro_lite.MaestroLite.chat`` reads
    ``content`` (and optionally ``tags`` for filtering) and folds it into
    the system context per request.
    """

    __tablename__ = "maestro_learning_entries"

    id = Column(Integer, primary_key=True, index=True)

    # Tenant + ownership scoping. Both columns are required: ``org_id`` for
    # tenant_query routing, ``user_id`` for per-user filtering at the route
    # layer. A user-less entry is meaningless for the chat flow.
    org_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Content. ``title`` is optional but useful for UI listing; ``content``
    # is the body the chat pulls into context.
    title = Column(String(255))
    content = Column(Text, nullable=False)

    # Provenance — set by the route handler based on how the entry arrived.
    # "manual" for typed entries, "upload" for file imports (future),
    # "web_clip" for browser-extension clips (future). Keep it open-string;
    # we don't want a strict enum that fights migrations.
    source = Column(String(40), nullable=False, default="manual")

    # Tags as a JSON list of strings. JSONB on Postgres for indexability;
    # plain JSON on SQLite so tests work without backend tricks.
    tags = Column(JSON().with_variant(JSONB(), "postgresql"))

    # Soft-toggle so a user can keep a draft entry but exclude it from chat
    # context without deleting it. The chat assembler filters on this flag.
    enabled = Column(Boolean, nullable=False, default=True, index=True)

    # Timestamps — server-default so callers don't need to set them.
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def to_dict(self) -> dict:
        """Stable JSON shape for the REST surface.

        Pinned here (not in the route handler) so every endpoint that
        returns an entry produces the same projection — including any
        future "search" endpoint.
        """
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "tags": list(self.tags or []),
            "enabled": bool(self.enabled),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
