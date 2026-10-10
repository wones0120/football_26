-- Append-only research registrations and outcome reports. No live selection writes.
CREATE TABLE target.gpp_shadow_experiment (
    experiment_id TEXT PRIMARY KEY,
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    slate TEXT NOT NULL,
    contest_format TEXT NOT NULL CHECK (contest_format IN ('classic','showdown')),
    snapshot_json JSONB NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE target.gpp_shadow_report (
    report_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES target.gpp_shadow_experiment(experiment_id),
    status TEXT NOT NULL,
    report_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX gpp_shadow_report_experiment ON target.gpp_shadow_report(experiment_id,created_at DESC);
CREATE TRIGGER gpp_shadow_experiment_immutable BEFORE UPDATE OR DELETE ON target.gpp_shadow_experiment
FOR EACH ROW EXECUTE FUNCTION target.reject_showdown_selection_rewrite();
CREATE TRIGGER gpp_shadow_report_immutable BEFORE UPDATE OR DELETE ON target.gpp_shadow_report
FOR EACH ROW EXECUTE FUNCTION target.reject_showdown_selection_rewrite();

INSERT INTO public.target_schema_contract (object_type, table_name, object_name, definition)
SELECT 'table', t.relname, t.relname, 'table'
FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace
WHERE n.nspname='target' AND t.relname IN ('gpp_shadow_experiment','gpp_shadow_report') AND t.relkind IN ('r','p')
UNION ALL
SELECT 'column', t.relname, a.attname,
       format('%%s|not_null=%%s|identity=%%s|generated=%%s',format_type(a.atttypid,a.atttypmod),a.attnotnull,a.attidentity,a.attgenerated)
FROM pg_attribute a JOIN pg_class t ON t.oid=a.attrelid JOIN pg_namespace n ON n.oid=t.relnamespace
WHERE n.nspname='target' AND t.relname IN ('gpp_shadow_experiment','gpp_shadow_report')
  AND t.relkind IN ('r','p') AND a.attnum>0 AND NOT a.attisdropped
UNION ALL
SELECT 'constraint', t.relname, c.conname, format('%%s|%%s',c.contype,pg_get_constraintdef(c.oid,true))
FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace
WHERE n.nspname='target' AND t.relname IN ('gpp_shadow_experiment','gpp_shadow_report') AND t.relkind IN ('r','p')
ON CONFLICT (object_type, table_name, object_name) DO NOTHING;
