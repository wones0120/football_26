-- A pre-lock choice is append-only and tied to the exact frozen optimizer run.
CREATE TABLE IF NOT EXISTS target.skill_exposure_decision (
    decision_id TEXT PRIMARY KEY,
    optimizer_run_id TEXT NOT NULL REFERENCES target.optimizer_run(optimizer_run_id),
    player_id TEXT NOT NULL,
    selected_exposure DOUBLE PRECISION NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('approve', 'cap')),
    requested_cap DOUBLE PRECISION,
    resulting_optimizer_run_id TEXT REFERENCES target.optimizer_run(optimizer_run_id),
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    decided_at TIMESTAMPTZ NOT NULL,
    first_kickoff_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT skill_decision_prelock CHECK (decided_at < first_kickoff_at),
    CONSTRAINT skill_decision_cap CHECK (
        (decision = 'approve' AND requested_cap IS NULL AND resulting_optimizer_run_id IS NULL)
        OR (decision = 'cap' AND requested_cap >= 0 AND requested_cap <= 0.8
            AND resulting_optimizer_run_id IS NOT NULL)
    ),
    UNIQUE (optimizer_run_id, player_id)
);

CREATE OR REPLACE FUNCTION target.reject_skill_decision_rewrite()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Pre-lock skill exposure decisions are immutable';
END;
$$;
DROP TRIGGER IF EXISTS skill_decision_immutable ON target.skill_exposure_decision;
CREATE TRIGGER skill_decision_immutable BEFORE UPDATE OR DELETE ON target.skill_exposure_decision
FOR EACH ROW EXECUTE FUNCTION target.reject_skill_decision_rewrite();

INSERT INTO public.target_schema_contract (object_type, table_name, object_name, definition)
SELECT 'table', table_class.relname, table_class.relname, 'table'
FROM pg_class table_class JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target' AND table_class.relname = 'skill_exposure_decision'
  AND table_class.relkind IN ('r', 'p')
UNION ALL
SELECT 'column', table_class.relname, attribute.attname,
       format('%%s|not_null=%%s|identity=%%s|generated=%%s',
              format_type(attribute.atttypid, attribute.atttypmod),
              attribute.attnotnull, attribute.attidentity, attribute.attgenerated)
FROM pg_attribute attribute JOIN pg_class table_class ON table_class.oid = attribute.attrelid
JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target' AND table_class.relname = 'skill_exposure_decision'
  AND table_class.relkind IN ('r', 'p') AND attribute.attnum > 0 AND NOT attribute.attisdropped
UNION ALL
SELECT 'constraint', table_class.relname, constraint_row.conname,
       format('%%s|%%s', constraint_row.contype, pg_get_constraintdef(constraint_row.oid, true))
FROM pg_constraint constraint_row JOIN pg_class table_class ON table_class.oid = constraint_row.conrelid
JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target' AND table_class.relname = 'skill_exposure_decision'
  AND table_class.relkind IN ('r', 'p')
ON CONFLICT (object_type, table_name, object_name) DO NOTHING;
