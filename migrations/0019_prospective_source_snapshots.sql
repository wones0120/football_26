CREATE TABLE IF NOT EXISTS public.source_snapshot (
    snapshot_id VARCHAR(36) PRIMARY KEY,
    source_system VARCHAR(32) NOT NULL,
    dataset VARCHAR(64) NOT NULL,
    season INT NOT NULL,
    week INT,
    slate VARCHAR(64),
    observed_at TIMESTAMPTZ NOT NULL,
    effective_at TIMESTAMPTZ,
    captured_at TIMESTAMPTZ NOT NULL,
    slate_lock_at TIMESTAMPTZ,
    observation_basis VARCHAR(48) NOT NULL,
    content_sha256 VARCHAR(64) NOT NULL,
    byte_count BIGINT NOT NULL,
    row_count INT,
    media_type VARCHAR(128) NOT NULL,
    artifact_path TEXT NOT NULL,
    manifest_path TEXT NOT NULL,
    original_path TEXT,
    source_uri TEXT,
    source_license TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_source_snapshot_scope_observed
    ON public.source_snapshot (
        source_system, dataset, season, week, slate, observed_at
    );
CREATE INDEX IF NOT EXISTS idx_source_snapshot_content_sha256
    ON public.source_snapshot (content_sha256);

CREATE TABLE IF NOT EXISTS public.source_snapshot_ingest_run (
    snapshot_id VARCHAR(36) NOT NULL
        REFERENCES public.source_snapshot(snapshot_id),
    ingest_run_id VARCHAR(36) NOT NULL
        REFERENCES public.ingest_run(ingest_run_id) ON DELETE CASCADE,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_id, ingest_run_id)
);

CREATE OR REPLACE FUNCTION public.reject_source_snapshot_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'source_snapshot rows are immutable; append a new snapshot instead';
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'trg_source_snapshot_immutable'
          AND tgrelid = 'public.source_snapshot'::regclass
    ) THEN
        CREATE TRIGGER trg_source_snapshot_immutable
        BEFORE UPDATE OR DELETE ON public.source_snapshot
        FOR EACH ROW EXECUTE FUNCTION public.reject_source_snapshot_mutation();
    END IF;
END;
$$;
