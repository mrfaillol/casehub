CREATE TABLE IF NOT EXISTS appointment_assignees (
    appointment_id INTEGER NOT NULL REFERENCES appointments(id) ON DELETE CASCADE,
    user_id        INTEGER NOT NULL REFERENCES users(id)        ON DELETE CASCADE,
    PRIMARY KEY (appointment_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_appt_assignees_user
    ON appointment_assignees (user_id);
CREATE INDEX IF NOT EXISTS idx_appt_assignees_appt
    ON appointment_assignees (appointment_id);

-- Migrar responsáveis existentes (assignment singular → junction)
INSERT INTO appointment_assignees (appointment_id, user_id)
SELECT id, assigned_to
FROM appointments
WHERE assigned_to IS NOT NULL
ON CONFLICT DO NOTHING;
