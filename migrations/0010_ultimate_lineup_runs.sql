CREATE TABLE IF NOT EXISTS ultimate_lineup_run (
    ultimate_lineup_run_id VARCHAR(36) PRIMARY KEY,
    idempotency_key VARCHAR(255) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    source_system VARCHAR(32) NOT NULL,
    season INT NOT NULL,
    week INT NOT NULL,
    slate VARCHAR(64) NOT NULL,
    request_json JSONB NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'queued',
    stage VARCHAR(32) NOT NULL DEFAULT 'queued',
    progress_current INT NOT NULL DEFAULT 0,
    progress_total INT NOT NULL DEFAULT 1,
    progress_message TEXT,
    checkpoint_path TEXT,
    attempt_count INT NOT NULL DEFAULT 0,
    result_json JSONB,
    error_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    CONSTRAINT uq_ultimate_lineup_run_idempotency_key
        UNIQUE (idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_ultimate_lineup_run_slice
ON ultimate_lineup_run(source_system, season, week, slate, created_at);

CREATE INDEX IF NOT EXISTS idx_ultimate_lineup_run_status
ON ultimate_lineup_run(status, updated_at);
