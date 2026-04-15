-- Audit database initialization
-- This database is designed to be WRITE-ONLY for the application
-- Only compliance officers with elevated privileges can read

CREATE SCHEMA IF NOT EXISTS audit;

-- Append-only audit table with row-level security
CREATE TABLE audit.audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type VARCHAR(50) NOT NULL,
    actor_id VARCHAR(255),
    actor_role VARCHAR(50),
    patient_id UUID,
    phi_fields_accessed TEXT[],
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100),
    resource_id VARCHAR(255),
    details JSONB,
    ip_address INET,
    user_agent TEXT,
    session_id VARCHAR(255),
    -- Prevent any updates or deletes
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Append-only constraint: no updates or deletes allowed
CREATE OR REPLACE FUNCTION audit.prevent_update()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' OR TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Audit log is append-only. % operations are not allowed.', TG_OP;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_append_only
    BEFORE UPDATE OR DELETE ON audit.audit_log
    FOR EACH ROW
    EXECUTE FUNCTION audit.prevent_update();

-- Row-level security
ALTER TABLE audit.audit_log ENABLE ROW LEVEL SECURITY;

-- Only INSERT allowed for application role
CREATE POLICY audit_insert_only ON audit.audit_log
    FOR INSERT TO hcrm_app_user
    WITH CHECK (true);

-- Read allowed only for compliance officer role
CREATE POLICY audit_read_compliance ON audit.audit_log
    FOR SELECT TO hcrm_compliance_user
    USING (true);

-- Index for common queries
CREATE INDEX idx_audit_log_timestamp ON audit.audit_log(timestamp);
CREATE INDEX idx_audit_log_actor ON audit.audit_log(actor_id);
CREATE INDEX idx_audit_log_patient ON audit.audit_log(patient_id);
CREATE INDEX idx_audit_log_event_type ON audit.audit_log(event_type);
