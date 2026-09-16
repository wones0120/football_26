CREATE TABLE IF NOT EXISTS target.agent_question (
    question_id TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL,
    variant_set_id TEXT NOT NULL REFERENCES target.digital_twin_variant_set(variant_set_id),
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    slate TEXT NOT NULL,
    trigger_type TEXT NOT NULL CHECK (
        trigger_type IN ('model_human_disagreement', 'high_value_uncertainty')
    ),
    priority INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 5),
    value_of_information_score DOUBLE PRECISION NOT NULL,
    subject_player_id TEXT NOT NULL,
    subject_label TEXT NOT NULL,
    question_text TEXT NOT NULL,
    context_json JSONB NOT NULL DEFAULT '{}',
    evidence_hash TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_question_scope
    ON target.agent_question (season, week, slate, created_at DESC);

CREATE TABLE IF NOT EXISTS target.agent_question_answer (
    answer_id TEXT PRIMARY KEY,
    question_id TEXT NOT NULL UNIQUE REFERENCES target.agent_question(question_id),
    answer TEXT NOT NULL CHECK (
        answer IN ('support_model', 'support_human', 'lean_upside', 'lean_downside', 'no_change')
    ),
    answer_text TEXT,
    resulting_modifier_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

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
