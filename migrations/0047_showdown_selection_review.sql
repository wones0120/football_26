-- Research-only immutable records. No production optimizer/lineup table changes.
CREATE TABLE IF NOT EXISTS target.showdown_selection_review (
    review_hash TEXT PRIMARY KEY,
    optimizer_run_id TEXT NOT NULL REFERENCES target.optimizer_run(optimizer_run_id),
    review_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (review_hash, optimizer_run_id)
);
CREATE TABLE IF NOT EXISTS target.showdown_selection_decision (
    decision_id TEXT PRIMARY KEY,
    optimizer_run_id TEXT NOT NULL REFERENCES target.optimizer_run(optimizer_run_id),
    review_hash TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    previous_decision_id TEXT,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PROPOSED','SELECTED','USER_APPROVED','ENTERED_CONFIRMED')),
    decided_at TIMESTAMPTZ NOT NULL,
    kickoff_at TIMESTAMPTZ NOT NULL,
    record_json JSONB NOT NULL,
    UNIQUE (optimizer_run_id, revision),
    UNIQUE (optimizer_run_id, idempotency_key),
    UNIQUE (optimizer_run_id, decision_id),
    UNIQUE (previous_decision_id),
    FOREIGN KEY (review_hash, optimizer_run_id) REFERENCES target.showdown_selection_review(review_hash, optimizer_run_id),
    FOREIGN KEY (optimizer_run_id, previous_decision_id) REFERENCES target.showdown_selection_decision(optimizer_run_id, decision_id),
    CHECK ((revision=1 AND previous_decision_id IS NULL) OR (revision>1 AND previous_decision_id IS NOT NULL)),
    CHECK (status='ENTERED_CONFIRMED' OR decided_at < kickoff_at)
);
CREATE TABLE IF NOT EXISTS target.showdown_selection_outcome (
    outcome_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL REFERENCES target.showdown_selection_decision(decision_id),
    learning_report_id TEXT NOT NULL REFERENCES target.slate_learning_report(report_id),
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    outcome_json JSONB NOT NULL,
    UNIQUE (decision_id, learning_report_id)
);
CREATE FUNCTION target.reject_showdown_selection_rewrite() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Showdown selection research records are append-only';
END;
$$;
CREATE TRIGGER showdown_review_immutable BEFORE UPDATE OR DELETE ON target.showdown_selection_review
FOR EACH ROW EXECUTE FUNCTION target.reject_showdown_selection_rewrite();
CREATE TRIGGER showdown_decision_immutable BEFORE UPDATE OR DELETE ON target.showdown_selection_decision
FOR EACH ROW EXECUTE FUNCTION target.reject_showdown_selection_rewrite();
CREATE TRIGGER showdown_outcome_immutable BEFORE UPDATE OR DELETE ON target.showdown_selection_outcome
FOR EACH ROW EXECUTE FUNCTION target.reject_showdown_selection_rewrite();

INSERT INTO public.target_schema_contract (object_type, table_name, object_name, definition)
SELECT 'table', t.relname, t.relname, 'table'
FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace
WHERE n.nspname='target' AND t.relname IN ('showdown_selection_review','showdown_selection_decision','showdown_selection_outcome') AND t.relkind IN ('r','p')
UNION ALL
SELECT 'column', t.relname, a.attname,
       format('%%s|not_null=%%s|identity=%%s|generated=%%s',format_type(a.atttypid,a.atttypmod),a.attnotnull,a.attidentity,a.attgenerated)
FROM pg_attribute a JOIN pg_class t ON t.oid=a.attrelid JOIN pg_namespace n ON n.oid=t.relnamespace
WHERE n.nspname='target' AND t.relname IN ('showdown_selection_review','showdown_selection_decision','showdown_selection_outcome')
  AND t.relkind IN ('r','p') AND a.attnum>0 AND NOT a.attisdropped
UNION ALL
SELECT 'constraint', t.relname, c.conname, format('%%s|%%s',c.contype,pg_get_constraintdef(c.oid,true))
FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace
WHERE n.nspname='target' AND t.relname IN ('showdown_selection_review','showdown_selection_decision','showdown_selection_outcome') AND t.relkind IN ('r','p')
ON CONFLICT (object_type, table_name, object_name) DO NOTHING;
