-- Maestro official Brazilian legal corpus.
-- Global source-backed knowledge: no tenant data, no secrets, no user memory.

CREATE TABLE IF NOT EXISTS maestro_legal_sources (
    id SERIAL PRIMARY KEY,
    source_key VARCHAR(120) NOT NULL UNIQUE,
    authority VARCHAR(120) NOT NULL,
    title VARCHAR(255) NOT NULL,
    url TEXT NOT NULL,
    jurisdiction VARCHAR(80) NOT NULL DEFAULT 'BR',
    document_type VARCHAR(80) NOT NULL DEFAULT 'norma',
    official BOOLEAN NOT NULL DEFAULT TRUE,
    public BOOLEAN NOT NULL DEFAULT TRUE,
    trust_status VARCHAR(40) NOT NULL DEFAULT 'verified',
    parser_version VARCHAR(60) NOT NULL DEFAULT 'maestro-legal-v1',
    content_sha256 VARCHAR(64),
    fetched_at TIMESTAMP,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS maestro_legal_documents (
    id SERIAL PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES maestro_legal_sources(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    url TEXT NOT NULL,
    document_type VARCHAR(80) NOT NULL DEFAULT 'norma',
    jurisdiction VARCHAR(80) NOT NULL DEFAULT 'BR',
    effective_from TIMESTAMP,
    effective_to TIMESTAMP,
    content_sha256 VARCHAR(64) NOT NULL,
    raw_text TEXT NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'active',
    parser_version VARCHAR(60) NOT NULL DEFAULT 'maestro-legal-v1',
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS maestro_legal_chunks (
    id SERIAL PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES maestro_legal_sources(id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL REFERENCES maestro_legal_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    heading VARCHAR(255),
    content TEXT NOT NULL,
    content_sha256 VARCHAR(64) NOT NULL,
    citation_label VARCHAR(255) NOT NULL,
    url TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS maestro_legal_embeddings (
    id SERIAL PRIMARY KEY,
    chunk_id INTEGER NOT NULL UNIQUE REFERENCES maestro_legal_chunks(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL DEFAULT 'ollama',
    model VARCHAR(120) NOT NULL DEFAULT 'nomic-embed-text',
    vector JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_maestro_legal_sources_key
    ON maestro_legal_sources(source_key);
CREATE INDEX IF NOT EXISTS idx_maestro_legal_sources_trust
    ON maestro_legal_sources(trust_status, official, public);
CREATE INDEX IF NOT EXISTS idx_maestro_legal_documents_source
    ON maestro_legal_documents(source_id, status);
CREATE INDEX IF NOT EXISTS idx_maestro_legal_documents_hash
    ON maestro_legal_documents(content_sha256);
CREATE INDEX IF NOT EXISTS idx_maestro_legal_chunks_source
    ON maestro_legal_chunks(source_id, active);
CREATE INDEX IF NOT EXISTS idx_maestro_legal_chunks_document
    ON maestro_legal_chunks(document_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_maestro_legal_chunks_hash
    ON maestro_legal_chunks(content_sha256);
