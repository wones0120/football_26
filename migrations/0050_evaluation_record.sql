-- Immutable evidence only; no optimizer, projection or selection-policy changes.
CREATE TABLE target.evaluation_record (
    record_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    optimizer_run_id TEXT REFERENCES target.optimizer_run(optimizer_run_id),
    evidence_sha256 TEXT NOT NULL,
    record_json JSONB NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX evaluation_record_run ON target.evaluation_record (optimizer_run_id, kind);
CREATE TRIGGER evaluation_record_immutable BEFORE UPDATE OR DELETE ON target.evaluation_record
FOR EACH ROW EXECUTE FUNCTION target.reject_learning_detail_rewrite();

INSERT INTO public.target_schema_contract (object_type, table_name, object_name, definition)
SELECT 'table', table_class.relname, table_class.relname, 'table'
FROM pg_class table_class JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target' AND table_class.relname = 'evaluation_record' AND table_class.relkind IN ('r', 'p')
UNION ALL
SELECT 'column', table_class.relname, attribute.attname,
       format('%%s|not_null=%%s|identity=%%s|generated=%%s',
              format_type(attribute.atttypid, attribute.atttypmod),
              attribute.attnotnull, attribute.attidentity, attribute.attgenerated)
FROM pg_attribute attribute JOIN pg_class table_class ON table_class.oid = attribute.attrelid
JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target' AND table_class.relname = 'evaluation_record' AND table_class.relkind IN ('r', 'p')
  AND attribute.attnum > 0 AND NOT attribute.attisdropped
UNION ALL
SELECT 'constraint', table_class.relname, constraint_row.conname,
       format('%%s|%%s', constraint_row.contype, pg_get_constraintdef(constraint_row.oid, true))
FROM pg_constraint constraint_row JOIN pg_class table_class ON table_class.oid = constraint_row.conrelid
JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target' AND table_class.relname = 'evaluation_record' AND table_class.relkind IN ('r', 'p');
