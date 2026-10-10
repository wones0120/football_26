-- Immutable account entry-history snapshots; no projections or pregame records changed.
CREATE TABLE target.dk_entry_history_snapshot (
    content_sha256 TEXT PRIMARY KEY,
    original_path TEXT NOT NULL,
    raw_content BYTEA NOT NULL,
    entries_json JSONB NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER dk_entry_history_immutable BEFORE UPDATE OR DELETE ON target.dk_entry_history_snapshot
FOR EACH ROW EXECUTE FUNCTION target.reject_showdown_selection_rewrite();

INSERT INTO public.target_schema_contract (object_type, table_name, object_name, definition)
SELECT 'table', t.relname, t.relname, 'table'
FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace
WHERE n.nspname='target' AND t.relname IN ('dk_entry_history_snapshot') AND t.relkind IN ('r','p')
UNION ALL
SELECT 'column', t.relname, a.attname,
       format('%%s|not_null=%%s|identity=%%s|generated=%%s',format_type(a.atttypid,a.atttypmod),a.attnotnull,a.attidentity,a.attgenerated)
FROM pg_attribute a JOIN pg_class t ON t.oid=a.attrelid JOIN pg_namespace n ON n.oid=t.relnamespace
WHERE n.nspname='target' AND t.relname IN ('dk_entry_history_snapshot')
  AND t.relkind IN ('r','p') AND a.attnum>0 AND NOT a.attisdropped
UNION ALL
SELECT 'constraint', t.relname, c.conname, format('%%s|%%s',c.contype,pg_get_constraintdef(c.oid,true))
FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace
WHERE n.nspname='target' AND t.relname IN ('dk_entry_history_snapshot') AND t.relkind IN ('r','p')
ON CONFLICT (object_type, table_name, object_name) DO NOTHING;
