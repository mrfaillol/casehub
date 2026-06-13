-- CaseHub Maestro tenant-scoped AI policy and hash-only inference audit.
-- Real provider secrets must stay in deploy secret storage or encrypted columns;
-- this migration stores no credential values by default.

CREATE TABLE IF NOT EXISTS org_ai_policies (
    id SERIAL PRIMARY KEY,
    org_id INTEGER NOT NULL,
    feature VARCHAR(50) NOT NULL DEFAULT 'maestro',
    provider VARCHAR(50) NOT NULL DEFAULT 'ollama',
    model VARCHAR(120),
    endpoint_url TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (org_id, feature)
);

CREATE TABLE IF NOT EXISTS org_ai_provider_credentials (
    id SERIAL PRIMARY KEY,
    org_id INTEGER NOT NULL,
    provider VARCHAR(50) NOT NULL,
    secret_ref VARCHAR(200),
    encrypted_secret TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (org_id, provider)
);

CREATE TABLE IF NOT EXISTS maestro_inferences (
    id SERIAL PRIMARY KEY,
    org_id INTEGER NOT NULL,
    user_id INTEGER,
    message_sha256 VARCHAR(64) NOT NULL,
    response_sha256 VARCHAR(64),
    model VARCHAR(120),
    provider VARCHAR(50) NOT NULL DEFAULT 'ollama',
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_org_ai_policies_org_feature
    ON org_ai_policies(org_id, feature);

CREATE INDEX IF NOT EXISTS idx_maestro_inferences_org_created
    ON maestro_inferences(org_id, created_at DESC);
