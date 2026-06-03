-- improvement_tasks: queue of tasks pushed by external Command Center
-- Authority: trabalho-workspace ruling 2026-05-06-cmd-control-center-activation
-- Receiver route: routes/improvement_tasks.py (POST /casehub/api/v1/improvement-tasks)

CREATE TABLE IF NOT EXISTS improvement_tasks (
    id SERIAL PRIMARY KEY,
    org_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL,

    -- Provenance
    envelope_ref VARCHAR(120) NOT NULL UNIQUE,
    source VARCHAR(80) NOT NULL DEFAULT 'ingest:command-center',
    requested_runtime VARCHAR(40),
    skill VARCHAR(80),

    -- Task content
    kind VARCHAR(80) NOT NULL,
    title VARCHAR(255) NOT NULL,
    summary TEXT,
    payload JSONB,
    payload_hash_sha256 VARCHAR(64),
    priority VARCHAR(8) DEFAULT 'P2',

    -- State machine
    status VARCHAR(24) DEFAULT 'received',
    dispatch_url VARCHAR(500),
    failure_reason TEXT,
    halt_blocked BOOLEAN DEFAULT FALSE,

    -- Timestamps
    received_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    dispatched_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_improvement_tasks_envelope_ref ON improvement_tasks (envelope_ref);
CREATE INDEX IF NOT EXISTS ix_improvement_tasks_org_status ON improvement_tasks (org_id, status);
CREATE INDEX IF NOT EXISTS ix_improvement_tasks_kind_received ON improvement_tasks (kind, received_at DESC);
CREATE INDEX IF NOT EXISTS ix_improvement_tasks_payload_hash ON improvement_tasks (payload_hash_sha256);
CREATE INDEX IF NOT EXISTS ix_improvement_tasks_halt_blocked ON improvement_tasks (halt_blocked) WHERE halt_blocked = TRUE;
