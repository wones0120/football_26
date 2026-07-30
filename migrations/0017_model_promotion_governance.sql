-- Persist model challenger evaluations plus atomic promotion/rollback approvals.

CREATE TABLE IF NOT EXISTS target.model_challenger_evaluation (
    evaluation_id TEXT PRIMARY KEY,
    season INT NOT NULL,
    week INT NOT NULL,
    slate_id TEXT NOT NULL,
    champion_projection_run_id TEXT NOT NULL
        REFERENCES target.projection_run(projection_run_id),
    challenger_projection_run_id TEXT NOT NULL
        REFERENCES target.projection_run(projection_run_id),
    data_window_json JSONB NOT NULL,
    champion_feature_set_hash TEXT NOT NULL,
    challenger_feature_set_hash TEXT NOT NULL,
    champion_code_hash TEXT NOT NULL,
    challenger_code_hash TEXT NOT NULL,
    gate_policy_json JSONB NOT NULL,
    gate_results_json JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('passed', 'blocked')),
    evaluation_hash TEXT NOT NULL UNIQUE,
    evaluated_by TEXT NOT NULL,
    evidence_uri TEXT NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (champion_projection_run_id <> challenger_projection_run_id)
);

CREATE INDEX IF NOT EXISTS idx_model_challenger_evaluation_scope
    ON target.model_challenger_evaluation
        (season, week, slate_id, created_at DESC);

CREATE TABLE IF NOT EXISTS target.model_promotion_decision (
    decision_id TEXT PRIMARY KEY,
    evaluation_id TEXT NOT NULL
        REFERENCES target.model_challenger_evaluation(evaluation_id),
    action TEXT NOT NULL CHECK (action IN ('promotion', 'rollback')),
    approved_by TEXT NOT NULL,
    approval_reason TEXT NOT NULL,
    previous_projection_run_id TEXT NOT NULL
        REFERENCES target.projection_run(projection_run_id),
    selected_projection_run_id TEXT NOT NULL
        REFERENCES target.projection_run(projection_run_id),
    rollback_of_decision_id TEXT UNIQUE
        REFERENCES target.model_promotion_decision(decision_id),
    decision_hash TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (evaluation_id, action),
    CHECK (previous_projection_run_id <> selected_projection_run_id),
    CHECK (
        (action = 'promotion' AND rollback_of_decision_id IS NULL)
        OR (action = 'rollback' AND rollback_of_decision_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_model_promotion_decision_evaluation
    ON target.model_promotion_decision (evaluation_id, created_at);

-- Refresh the migration-owned target schema contract after adding both tables.
-- Psycopg treats percent placeholders in driver-executed migration text as
-- parameters, so PostgreSQL format() placeholders remain escaped here.

TRUNCATE TABLE public.target_schema_contract;

INSERT INTO public.target_schema_contract
    (object_type, table_name, object_name, definition)
SELECT 'table',
       table_class.relname,
       table_class.relname,
       'table'
FROM pg_class table_class
JOIN pg_namespace namespace
  ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target'
  AND table_class.relkind IN ('r', 'p')

UNION ALL

SELECT 'column',
       table_class.relname,
       attribute.attname,
       format(
           '%%s|not_null=%%s|identity=%%s|generated=%%s',
           format_type(attribute.atttypid, attribute.atttypmod),
           attribute.attnotnull,
           attribute.attidentity,
           attribute.attgenerated
       )
FROM pg_attribute attribute
JOIN pg_class table_class
  ON table_class.oid = attribute.attrelid
JOIN pg_namespace namespace
  ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target'
  AND table_class.relkind IN ('r', 'p')
  AND attribute.attnum > 0
  AND NOT attribute.attisdropped

UNION ALL

SELECT 'constraint',
       table_class.relname,
       constraint_row.conname,
       format(
           '%%s|%%s',
           constraint_row.contype,
           pg_get_constraintdef(constraint_row.oid, true)
       )
FROM pg_constraint constraint_row
JOIN pg_class table_class
  ON table_class.oid = constraint_row.conrelid
JOIN pg_namespace namespace
  ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target'
  AND table_class.relkind IN ('r', 'p');
