CREATE TABLE IF NOT EXISTS operational_job (
    job_id VARCHAR(36) PRIMARY KEY,
    job_type VARCHAR(64) NOT NULL,
    idempotency_key VARCHAR(255) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    request_json JSONB NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'queued',
    stage VARCHAR(64) NOT NULL DEFAULT 'queued',
    progress_current INT NOT NULL DEFAULT 0,
    progress_total INT NOT NULL DEFAULT 1,
    progress_message TEXT,
    run_id VARCHAR(255),
    checkpoint_json JSONB,
    result_json JSONB,
    error_message TEXT,
    attempt_count INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 3,
    available_at TIMESTAMP NOT NULL DEFAULT now(),
    locked_by VARCHAR(255),
    lease_expires_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    CONSTRAINT uq_operational_job_type_idempotency_key
        UNIQUE (job_type, idempotency_key),
    CONSTRAINT ck_operational_job_max_attempts
        CHECK (max_attempts > 0),
    CONSTRAINT ck_operational_job_attempt_count
        CHECK (attempt_count >= 0)
);

CREATE INDEX IF NOT EXISTS idx_operational_job_dispatch
ON operational_job(status, available_at, created_at);

CREATE INDEX IF NOT EXISTS idx_operational_job_lease
ON operational_job(status, lease_expires_at);
