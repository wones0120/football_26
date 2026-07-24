CREATE TABLE IF NOT EXISTS target.ownership_model_run (
    ownership_run_id TEXT PRIMARY KEY,
    model_id TEXT NOT NULL,
    season INT NOT NULL,
    week INT NOT NULL,
    slate_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    data_cutoff_at TIMESTAMPTZ NOT NULL,
    training_rows INT NOT NULL,
    params_json JSONB NOT NULL DEFAULT '{}',
    metrics_json JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS target.ownership_projection (
    ownership_run_id TEXT NOT NULL
        REFERENCES target.ownership_model_run(ownership_run_id),
    season INT NOT NULL,
    week INT NOT NULL,
    slate_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    roster_position TEXT NOT NULL,
    projected_ownership DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    data_cutoff_at TIMESTAMPTZ NOT NULL,
    feature_json JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (ownership_run_id, player_id, roster_position)
);

CREATE INDEX IF NOT EXISTS idx_ownership_projection_scope
ON target.ownership_projection (season, week, slate_id, created_at DESC);

CREATE TABLE IF NOT EXISTS target.digital_twin_variant_set (
    variant_set_id TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL,
    season INT NOT NULL,
    week INT NOT NULL,
    slate TEXT NOT NULL,
    contest_format TEXT,
    objective TEXT,
    projection_run_id TEXT NOT NULL,
    projection_data_cutoff_at TIMESTAMPTZ,
    decision_cutoff_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('completed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_digital_twin_variant_set_scope
ON target.digital_twin_variant_set
    (season, week, slate, contest_format, objective, created_at DESC);

CREATE TABLE IF NOT EXISTS target.digital_twin_variant (
    variant_id TEXT PRIMARY KEY,
    variant_set_id TEXT NOT NULL
        REFERENCES target.digital_twin_variant_set(variant_set_id),
    variant_type TEXT NOT NULL
        CHECK (variant_type IN ('model_only', 'human_only', 'combined')),
    artifact_json JSONB NOT NULL,
    artifact_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (variant_set_id, variant_type)
);
