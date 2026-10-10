-- New compact learning reports reference content-addressed postgame evidence.
-- Existing v1 reports and original optimizer pools remain untouched.
CREATE TABLE target.slate_learning_run_detail (
    detail_id TEXT PRIMARY KEY,
    optimizer_run_id TEXT NOT NULL REFERENCES target.optimizer_run(optimizer_run_id),
    evidence_hash TEXT NOT NULL,
    candidate_count INTEGER NOT NULL CHECK (candidate_count >= 0),
    detail_json JSONB NOT NULL,
    correlation_samples_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_slate_learning_run_detail_run ON target.slate_learning_run_detail (optimizer_run_id);
CREATE FUNCTION target.reject_learning_detail_rewrite() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Learning candidate evidence is immutable';
END;
$$;
CREATE TRIGGER learning_detail_immutable BEFORE UPDATE OR DELETE ON target.slate_learning_run_detail
FOR EACH ROW EXECUTE FUNCTION target.reject_learning_detail_rewrite();

INSERT INTO public.target_schema_contract (object_type, table_name, object_name, definition)
SELECT 'table', table_class.relname, table_class.relname, 'table'
FROM pg_class table_class JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target' AND table_class.relname = 'slate_learning_run_detail' AND table_class.relkind IN ('r', 'p')
UNION ALL
SELECT 'column', table_class.relname, attribute.attname,
       format('%%s|not_null=%%s|identity=%%s|generated=%%s',
              format_type(attribute.atttypid, attribute.atttypmod),
              attribute.attnotnull, attribute.attidentity, attribute.attgenerated)
FROM pg_attribute attribute JOIN pg_class table_class ON table_class.oid = attribute.attrelid
JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target' AND table_class.relname = 'slate_learning_run_detail' AND table_class.relkind IN ('r', 'p')
  AND attribute.attnum > 0 AND NOT attribute.attisdropped
UNION ALL
SELECT 'constraint', table_class.relname, constraint_row.conname,
       format('%%s|%%s', constraint_row.contype, pg_get_constraintdef(constraint_row.oid, true))
FROM pg_constraint constraint_row JOIN pg_class table_class ON table_class.oid = constraint_row.conrelid
JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target' AND table_class.relname = 'slate_learning_run_detail' AND table_class.relkind IN ('r', 'p');
