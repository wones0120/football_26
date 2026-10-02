CREATE TABLE IF NOT EXISTS target.saved_dk_contest (
    contest_id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    slate TEXT NOT NULL,
    contest_format TEXT NOT NULL CHECK (contest_format IN ('classic', 'showdown')),
    contest_type TEXT NOT NULL CHECK (contest_type IN ('gpp', 'cash', 'h2h', 'double_up', 'fifty_fifty', 'other')),
    name TEXT,
    draft_group_id TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_saved_dk_contest_scope
    ON target.saved_dk_contest (season, week, slate, contest_format, contest_type, active);

CREATE TABLE IF NOT EXISTS target.saved_dk_contest_observation (
    observation_id TEXT PRIMARY KEY,
    contest_id TEXT NOT NULL REFERENCES target.saved_dk_contest(contest_id),
    observed_at TIMESTAMPTZ NOT NULL,
    observation_reason TEXT NOT NULL CHECK (observation_reason IN ('save', 'preview', 'optimizer')),
    source TEXT NOT NULL,
    source_sha256 TEXT,
    source_payload_json JSONB,
    contest_json JSONB NOT NULL,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_saved_dk_contest_observation_history
    ON target.saved_dk_contest_observation (contest_id, observed_at DESC, created_at DESC);

TRUNCATE TABLE public.target_schema_contract;

INSERT INTO public.target_schema_contract
    (object_type, table_name, object_name, definition)
SELECT 'table', table_class.relname, table_class.relname, 'table'
FROM pg_class table_class
JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target' AND table_class.relkind IN ('r', 'p')

UNION ALL

SELECT 'column', table_class.relname, attribute.attname,
       format(
           '%%s|not_null=%%s|identity=%%s|generated=%%s',
           format_type(attribute.atttypid, attribute.atttypmod),
           attribute.attnotnull, attribute.attidentity, attribute.attgenerated
       )
FROM pg_attribute attribute
JOIN pg_class table_class ON table_class.oid = attribute.attrelid
JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target'
  AND table_class.relkind IN ('r', 'p')
  AND attribute.attnum > 0
  AND NOT attribute.attisdropped

UNION ALL

SELECT 'constraint', table_class.relname, constraint_row.conname,
       format('%%s|%%s', constraint_row.contype, pg_get_constraintdef(constraint_row.oid, true))
FROM pg_constraint constraint_row
JOIN pg_class table_class ON table_class.oid = constraint_row.conrelid
JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target' AND table_class.relkind IN ('r', 'p');
