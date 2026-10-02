-- Append-only normalized market observations. Source bytes are in public.source_snapshot.
CREATE TABLE IF NOT EXISTS target.market_snapshot (
    market_snapshot_id TEXT PRIMARY KEY,
    source_snapshot_id VARCHAR(36) NOT NULL REFERENCES public.source_snapshot(snapshot_id),
    ingest_run_id VARCHAR(36) NOT NULL REFERENCES public.ingest_run(ingest_run_id),
    season INT NOT NULL,
    week INT NOT NULL,
    game_id TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    kickoff_at TIMESTAMPTZ NOT NULL,
    game_total DOUBLE PRECISION NOT NULL,
    home_spread DOUBLE PRECISION NOT NULL,
    source TEXT NOT NULL,
    source_game_id TEXT,
    observed_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT market_snapshot_teams_differ CHECK (home_team <> away_team),
    CONSTRAINT market_snapshot_observed_before_kickoff CHECK (observed_at < kickoff_at),
    CONSTRAINT market_snapshot_ingested_after_observed CHECK (ingested_at >= observed_at),
    UNIQUE (source_snapshot_id, game_id, source)
);
CREATE INDEX IF NOT EXISTS market_snapshot_game_time
    ON target.market_snapshot (season, week, game_id, observed_at DESC);

CREATE OR REPLACE FUNCTION target.reject_market_snapshot_rewrite()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Market snapshots are append-only; reverse an ingest by changing its run status';
END;
$$;
DROP TRIGGER IF EXISTS market_snapshot_immutable ON target.market_snapshot;
CREATE TRIGGER market_snapshot_immutable BEFORE UPDATE OR DELETE ON target.market_snapshot
FOR EACH ROW EXECUTE FUNCTION target.reject_market_snapshot_rewrite();

INSERT INTO public.target_schema_contract (object_type, table_name, object_name, definition)
SELECT 'table', table_class.relname, table_class.relname, 'table'
FROM pg_class table_class JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target' AND table_class.relkind IN ('r', 'p')
  AND table_class.relname = 'market_snapshot'
UNION ALL
SELECT 'column', table_class.relname, attribute.attname,
       format('%%s|not_null=%%s|identity=%%s|generated=%%s',
              format_type(attribute.atttypid, attribute.atttypmod),
              attribute.attnotnull, attribute.attidentity, attribute.attgenerated)
FROM pg_attribute attribute JOIN pg_class table_class ON table_class.oid = attribute.attrelid
JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target' AND table_class.relkind IN ('r', 'p')
  AND table_class.relname = 'market_snapshot'
  AND attribute.attnum > 0 AND NOT attribute.attisdropped
UNION ALL
SELECT 'constraint', table_class.relname, constraint_row.conname,
       format('%%s|%%s', constraint_row.contype, pg_get_constraintdef(constraint_row.oid, true))
FROM pg_constraint constraint_row JOIN pg_class table_class ON table_class.oid = constraint_row.conrelid
JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
WHERE namespace.nspname = 'target' AND table_class.relkind IN ('r', 'p')
  AND table_class.relname = 'market_snapshot'
ON CONFLICT (object_type, table_name, object_name) DO NOTHING;
