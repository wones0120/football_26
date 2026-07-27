CREATE TABLE IF NOT EXISTS weekly_run (
    weekly_run_id VARCHAR(36) PRIMARY KEY,
    operational_job_id VARCHAR(36) NOT NULL UNIQUE
        REFERENCES operational_job(job_id) ON DELETE CASCADE,
    season INT NOT NULL,
    week INT NOT NULL,
    slate VARCHAR(64) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'queued',
    current_stage VARCHAR(64) NOT NULL DEFAULT 'queued',
    data_cutoff_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    CONSTRAINT ck_weekly_run_week CHECK (week >= 1 AND week <= 25)
);

CREATE INDEX IF NOT EXISTS idx_weekly_run_scope
ON weekly_run(season, week, slate, created_at);

CREATE INDEX IF NOT EXISTS idx_weekly_run_status
ON weekly_run(status, updated_at);

CREATE TABLE IF NOT EXISTS weekly_run_stage (
    weekly_run_id VARCHAR(36) NOT NULL
        REFERENCES weekly_run(weekly_run_id) ON DELETE CASCADE,
    stage VARCHAR(64) NOT NULL,
    stage_order INT NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'pending',
    attempt_count INT NOT NULL DEFAULT 0,
    message TEXT,
    counts_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    logs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    errors_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    artifact_ids_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_json JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    PRIMARY KEY (weekly_run_id, stage),
    CONSTRAINT uq_weekly_run_stage_order UNIQUE (weekly_run_id, stage_order),
    CONSTRAINT ck_weekly_run_stage_order CHECK (stage_order >= 1),
    CONSTRAINT ck_weekly_run_stage_attempt_count CHECK (attempt_count >= 0)
);

CREATE INDEX IF NOT EXISTS idx_weekly_run_stage_status
ON weekly_run_stage(status, updated_at);
