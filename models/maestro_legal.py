"""Official Brazilian legal corpus models for Maestro.

This is a global, source-backed corpus. It is intentionally separate from
tenant/user knowledge:

- tenant data stays org-scoped in CaseHub tables;
- user imports stay authorial memory;
- legal truth must come from official, versioned sources with hashes.
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from .base import Base


class MaestroLegalSource(Base):
    """Canonical source registry entry, e.g. Planalto, CNJ, STF, STJ."""

    __tablename__ = "maestro_legal_sources"

    id = Column(Integer, primary_key=True, index=True)
    source_key = Column(String(120), nullable=False, unique=True, index=True)
    authority = Column(String(120), nullable=False)
    title = Column(String(255), nullable=False)
    url = Column(Text, nullable=False)
    jurisdiction = Column(String(80), nullable=False, default="BR")
    document_type = Column(String(80), nullable=False, default="norma")
    official = Column(Boolean, nullable=False, default=True)
    public = Column(Boolean, nullable=False, default=True)
    trust_status = Column(String(40), nullable=False, default="verified")
    parser_version = Column(String(60), nullable=False, default="maestro-legal-v1")
    content_sha256 = Column(String(64))
    fetched_at = Column(DateTime(timezone=True))
    extra_metadata = Column("metadata", JSON().with_variant(JSONB(), "postgresql"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class MaestroLegalDocument(Base):
    """A fetched/validated document under one official source."""

    __tablename__ = "maestro_legal_documents"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(
        Integer,
        ForeignKey("maestro_legal_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(255), nullable=False)
    url = Column(Text, nullable=False)
    document_type = Column(String(80), nullable=False, default="norma")
    jurisdiction = Column(String(80), nullable=False, default="BR")
    effective_from = Column(DateTime(timezone=True))
    effective_to = Column(DateTime(timezone=True))
    content_sha256 = Column(String(64), nullable=False, index=True)
    raw_text = Column(Text, nullable=False)
    status = Column(String(40), nullable=False, default="active", index=True)
    parser_version = Column(String(60), nullable=False, default="maestro-legal-v1")
    extra_metadata = Column("metadata", JSON().with_variant(JSONB(), "postgresql"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class MaestroLegalChunk(Base):
    """Searchable legal text fragment with citation metadata."""

    __tablename__ = "maestro_legal_chunks"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(
        Integer,
        ForeignKey("maestro_legal_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id = Column(
        Integer,
        ForeignKey("maestro_legal_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index = Column(Integer, nullable=False)
    heading = Column(String(255))
    content = Column(Text, nullable=False)
    content_sha256 = Column(String(64), nullable=False, index=True)
    citation_label = Column(String(255), nullable=False)
    url = Column(Text, nullable=False)
    active = Column(Boolean, nullable=False, default=True, index=True)
    extra_metadata = Column("metadata", JSON().with_variant(JSONB(), "postgresql"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MaestroLegalEmbedding(Base):
    """Optional local embedding vector for a legal chunk.

    The v1 retrieval path is lexical so production does not need a vector DB.
    This table prepares the zero-transfer Ollama embeddings path for later.
    """

    __tablename__ = "maestro_legal_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    chunk_id = Column(
        Integer,
        ForeignKey("maestro_legal_chunks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    provider = Column(String(50), nullable=False, default="ollama")
    model = Column(String(120), nullable=False, default="nomic-embed-text")
    vector = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
