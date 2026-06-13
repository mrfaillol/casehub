ALTER TABLE appointments ADD COLUMN IF NOT EXISTS outcome VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_appointments_outcome
    ON appointments (org_id, outcome) WHERE outcome IS NOT NULL;
