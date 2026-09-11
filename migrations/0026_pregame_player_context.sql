-- Add append-only, point-in-time player context for projection scoring.

CREATE TABLE IF NOT EXISTS public.pregame_context_run (
    context_run_id VARCHAR(36) PRIMARY KEY,
    season INT NOT NULL,
    week INT NOT NULL,
    slate VARCHAR(64) NOT NULL,
    source VARCHAR(128) NOT NULL,
    source_uri TEXT,
    observed_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes TEXT,
    content_hash VARCHAR(64) NOT NULL UNIQUE,
    status VARCHAR(24) NOT NULL DEFAULT 'completed'
        CHECK (status IN ('completed', 'failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pregame_context_run_slice
    ON public.pregame_context_run
        (season, week, slate, observed_at DESC, received_at DESC);

CREATE TABLE IF NOT EXISTS public.pregame_player_context (
    pregame_player_context_id BIGSERIAL PRIMARY KEY,
    context_run_id VARCHAR(36) NOT NULL
        REFERENCES public.pregame_context_run(context_run_id),
    player_master_id VARCHAR(36) NOT NULL
        REFERENCES public.player_master(player_master_id),
    player_name VARCHAR(128) NOT NULL,
    team VARCHAR(16) NOT NULL,
    position VARCHAR(16) NOT NULL,
    availability_probability DOUBLE PRECISION
        CHECK (
            availability_probability IS NULL
            OR availability_probability BETWEEN 0.0 AND 1.0
        ),
    start_probability DOUBLE PRECISION
        CHECK (
            start_probability IS NULL
            OR start_probability BETWEEN 0.0 AND 1.0
        ),
    carry_share DOUBLE PRECISION
        CHECK (carry_share IS NULL OR carry_share BETWEEN 0.0 AND 1.0),
    target_share DOUBLE PRECISION
        CHECK (target_share IS NULL OR target_share BETWEEN 0.0 AND 1.0),
    role_label VARCHAR(32),
    injury_status VARCHAR(64),
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (context_run_id, player_master_id),
    CHECK (
        availability_probability IS NOT NULL
        OR start_probability IS NOT NULL
        OR carry_share IS NOT NULL
        OR target_share IS NOT NULL
        OR role_label IS NOT NULL
        OR injury_status IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_pregame_player_context_player
    ON public.pregame_player_context (player_master_id, context_run_id);

-- Pregame evidence is event-style input. Corrections are new runs, never edits.
CREATE OR REPLACE FUNCTION public.reject_pregame_context_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'pregame context is immutable; insert a newer context run';
END;
$$;

DROP TRIGGER IF EXISTS trg_pregame_context_run_immutable
    ON public.pregame_context_run;
CREATE TRIGGER trg_pregame_context_run_immutable
BEFORE UPDATE OR DELETE ON public.pregame_context_run
FOR EACH ROW EXECUTE FUNCTION public.reject_pregame_context_mutation();

DROP TRIGGER IF EXISTS trg_pregame_player_context_immutable
    ON public.pregame_player_context;
CREATE TRIGGER trg_pregame_player_context_immutable
BEFORE UPDATE OR DELETE ON public.pregame_player_context
FOR EACH ROW EXECUTE FUNCTION public.reject_pregame_context_mutation();

-- Refresh the migration-owned target contract after migration 0025 altered a
-- target table. Percent placeholders are doubled for psycopg driver execution.
TRUNCATE TABLE public.target_schema_contract;

INSERT INTO public.target_schema_contract
    (object_type, table_name, object_name, definition)
SELECT 'table', table_class.relname, table_class.relname, 'table'
FROM pg_class table_class
JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target'
  AND table_class.relkind IN ('r', 'p')

UNION ALL

SELECT 'column', table_class.relname, attribute.attname,
       format(
           '%%s|not_null=%%s|identity=%%s|generated=%%s',
           format_type(attribute.atttypid, attribute.atttypmod),
           attribute.attnotnull,
           attribute.attidentity,
           attribute.attgenerated
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
       format(
           '%%s|%%s',
           constraint_row.contype,
           pg_get_constraintdef(constraint_row.oid, true)
       )
FROM pg_constraint constraint_row
JOIN pg_class table_class ON table_class.oid = constraint_row.conrelid
JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target'
  AND table_class.relkind IN ('r', 'p');
