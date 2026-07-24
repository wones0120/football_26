-- Make numbered migrations authoritative for target persistence and record the
-- exact table/column/constraint contract for read-only runtime validation.

ALTER TABLE target.player_projection
    ADD COLUMN IF NOT EXISTS calibration_method TEXT,
    ADD COLUMN IF NOT EXISTS calibration_position TEXT,
    ADD COLUMN IF NOT EXISTS calibration_role TEXT,
    ADD COLUMN IF NOT EXISTS calibration_sample_size INT;

ALTER TABLE target.lineup
    ADD COLUMN IF NOT EXISTS projected_median DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS projected_floor DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS objective_score DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS average_role_certainty DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS fragility_penalty DOUBLE PRECISION;

CREATE TABLE IF NOT EXISTS public.target_schema_contract (
    object_type TEXT NOT NULL
        CHECK (object_type IN ('table', 'column', 'constraint')),
    table_name TEXT NOT NULL,
    object_name TEXT NOT NULL,
    definition TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (object_type, table_name, object_name)
);

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
