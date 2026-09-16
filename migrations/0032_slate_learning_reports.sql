CREATE TABLE IF NOT EXISTS target.slate_learning_report (
    report_id TEXT PRIMARY KEY,
    contract_id TEXT NOT NULL,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    slate TEXT NOT NULL,
    entry_user TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('completed', 'partial')),
    source_file_ids_json JSONB NOT NULL DEFAULT '[]',
    run_ids_json JSONB NOT NULL DEFAULT '{}',
    report_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (season, week, slate, entry_user, evidence_hash)
);

CREATE INDEX IF NOT EXISTS idx_slate_learning_report_scope
    ON target.slate_learning_report (season, week, slate, entry_user, created_at DESC);

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
