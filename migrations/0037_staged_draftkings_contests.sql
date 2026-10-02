CREATE TABLE IF NOT EXISTS target.dk_contest_staged_file (
    source_file_id TEXT PRIMARY KEY REFERENCES target.source_file_import(source_file_id),
    contest_id TEXT,
    file_name TEXT NOT NULL,
    raw_file BYTEA NOT NULL,
    first_staged_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    resolved_season INT,
    resolved_week INT,
    resolved_slate TEXT
);

CREATE INDEX IF NOT EXISTS idx_dk_contest_staged_file_unresolved
    ON target.dk_contest_staged_file (contest_id)
    WHERE resolved_at IS NULL;

ALTER TABLE target.import_batch ADD COLUMN IF NOT EXISTS staged INT NOT NULL DEFAULT 0;

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
