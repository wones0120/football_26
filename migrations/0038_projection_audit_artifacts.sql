-- Immutable fitted-model and external projection evidence. Existing runs remain untouched.
CREATE TABLE IF NOT EXISTS target.model_artifact (
    model_run_id TEXT PRIMARY KEY REFERENCES target.model_run(model_run_id),
    artifact_uri TEXT NOT NULL UNIQUE,
    artifact_sha256 TEXT NOT NULL,
    artifact_bytes BYTEA NOT NULL,
    model_version TEXT NOT NULL,
    feature_schema_json JSONB NOT NULL,
    training_cutoff TIMESTAMPTZ NOT NULL,
    training_dataset_sha256 TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    git_revision TEXT,
    calibration_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS target.external_projection_benchmark (
    benchmark_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_url TEXT,
    season INT NOT NULL,
    week INT NOT NULL,
    slate_id TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    raw_snapshot_uri TEXT,
    raw_snapshot_sha256 TEXT,
    status TEXT NOT NULL DEFAULT 'available',
    unavailable_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS target.external_projection_value (
    benchmark_id TEXT NOT NULL REFERENCES target.external_projection_benchmark(benchmark_id),
    player_id TEXT NOT NULL REFERENCES target.dim_player(player_id),
    source_player_id TEXT,
    projection DOUBLE PRECISION,
    value DOUBLE PRECISION,
    classification TEXT,
    PRIMARY KEY (benchmark_id, player_id)
);

TRUNCATE TABLE public.target_schema_contract;
INSERT INTO public.target_schema_contract (object_type, table_name, object_name, definition)
SELECT 'table', table_class.relname, table_class.relname, 'table'
FROM pg_class table_class JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target' AND table_class.relkind IN ('r', 'p')
UNION ALL
SELECT 'column', table_class.relname, attribute.attname,
       format('%%s|not_null=%%s|identity=%%s|generated=%%s',
              format_type(attribute.atttypid, attribute.atttypmod),
              attribute.attnotnull, attribute.attidentity, attribute.attgenerated)
FROM pg_attribute attribute JOIN pg_class table_class ON table_class.oid = attribute.attrelid
JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target' AND table_class.relkind IN ('r', 'p')
  AND attribute.attnum > 0 AND NOT attribute.attisdropped
UNION ALL
SELECT 'constraint', table_class.relname, constraint_row.conname,
       format('%%s|%%s', constraint_row.contype, pg_get_constraintdef(constraint_row.oid, true))
FROM pg_constraint constraint_row JOIN pg_class table_class ON table_class.oid = constraint_row.conrelid
JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target' AND table_class.relkind IN ('r', 'p');
