-- Reward diversity only among quality-qualified frontier theses.
-- Preserve the immutable v1/v2 diagnostic rows rather than rewriting history.
CREATE TABLE IF NOT EXISTS target.classic_dynamic_thesis_shadow_v3 (
    optimizer_run_id TEXT PRIMARY KEY REFERENCES target.optimizer_run(optimizer_run_id),
    supersedes_shadow_sha256 TEXT,
    source_solver_sha256 TEXT NOT NULL,
    candidate_universe_sha256 TEXT NOT NULL,
    shadow_sha256 TEXT NOT NULL,
    shadow_json JSONB NOT NULL,
    decision_cutoff_at TIMESTAMPTZ NOT NULL,
    first_kickoff_at TIMESTAMPTZ NOT NULL,
    frozen_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT dynamic_thesis_shadow_v3_prelock CHECK (
        decision_cutoff_at < first_kickoff_at AND frozen_at < first_kickoff_at
    )
);

DROP TRIGGER IF EXISTS dynamic_thesis_shadow_v3_immutable ON target.classic_dynamic_thesis_shadow_v3;
CREATE TRIGGER dynamic_thesis_shadow_v3_immutable
BEFORE UPDATE OR DELETE ON target.classic_dynamic_thesis_shadow_v3
FOR EACH ROW EXECUTE FUNCTION target.reject_dynamic_thesis_shadow_rewrite();

INSERT INTO public.target_schema_contract (object_type, table_name, object_name, definition)
SELECT 'table', table_class.relname, table_class.relname, 'table'
FROM pg_class table_class JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target' AND table_class.relname = 'classic_dynamic_thesis_shadow_v3'
  AND table_class.relkind IN ('r', 'p')
UNION ALL
SELECT 'column', table_class.relname, attribute.attname,
       format('%%s|not_null=%%s|identity=%%s|generated=%%s',
              format_type(attribute.atttypid, attribute.atttypmod),
              attribute.attnotnull, attribute.attidentity, attribute.attgenerated)
FROM pg_attribute attribute JOIN pg_class table_class ON table_class.oid = attribute.attrelid
JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target' AND table_class.relname = 'classic_dynamic_thesis_shadow_v3'
  AND table_class.relkind IN ('r', 'p') AND attribute.attnum > 0 AND NOT attribute.attisdropped
UNION ALL
SELECT 'constraint', table_class.relname, constraint_row.conname,
       format('%%s|%%s', constraint_row.contype, pg_get_constraintdef(constraint_row.oid, true))
FROM pg_constraint constraint_row JOIN pg_class table_class ON table_class.oid = constraint_row.conrelid
JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target' AND table_class.relname = 'classic_dynamic_thesis_shadow_v3'
ON CONFLICT (object_type, table_name, object_name) DO NOTHING;
