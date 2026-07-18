CREATE TABLE IF NOT EXISTS projection_residual_snapshot (
    projection_residual_snapshot_id VARCHAR(36) PRIMARY KEY,
    source_system VARCHAR(32) NOT NULL,
    season INT NOT NULL,
    week INT NOT NULL,
    slate VARCHAR(64) NOT NULL,
    parameters_hash VARCHAR(64) NOT NULL,
    parameters_json JSONB NOT NULL,
    feature_set_hash VARCHAR(64) NOT NULL,
    code_version VARCHAR(64) NOT NULL,
    observations_json JSONB NOT NULL,
    observations_count INT NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'completed',
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_projection_residual_snapshot_slice
        UNIQUE (source_system, season, week, slate)
);

CREATE INDEX IF NOT EXISTS idx_projection_residual_snapshot_lookup
ON projection_residual_snapshot(source_system, slate, season, week, status);
