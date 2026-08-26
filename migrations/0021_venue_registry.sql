CREATE TABLE IF NOT EXISTS public.venue_registry_record (
    registry_record_id VARCHAR(96) PRIMARY KEY,
    venue_id VARCHAR(64) NOT NULL,
    registry_version INT NOT NULL,
    canonical_name VARCHAR(128) NOT NULL,
    effective_from_season INT NOT NULL,
    effective_to_season INT,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    timezone VARCHAR(64) NOT NULL,
    default_roof VARCHAR(24) NOT NULL,
    country_code VARCHAR(2) NOT NULL,
    source_system VARCHAR(32),
    source_venue_id VARCHAR(64),
    source_evidence_uri TEXT,
    coordinate_source_uri TEXT NOT NULL,
    review_notes TEXT NOT NULL,
    review_classifications_json JSONB NOT NULL DEFAULT '[]',
    definition_sha256 VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_venue_registry_record_version
        UNIQUE (venue_id, registry_version),
    CONSTRAINT ck_venue_registry_record_positive_version
        CHECK (registry_version >= 1),
    CONSTRAINT ck_venue_registry_record_effective_range
        CHECK (
            effective_to_season IS NULL
            OR effective_to_season >= effective_from_season
        ),
    CONSTRAINT ck_venue_registry_record_coordinates
        CHECK (
            latitude BETWEEN -90 AND 90
            AND longitude BETWEEN -180 AND 180
        ),
    CONSTRAINT ck_venue_registry_record_default_roof
        CHECK (default_roof IN ('outdoor', 'fixed_indoor', 'retractable'))
);

CREATE INDEX IF NOT EXISTS idx_venue_registry_source_effective
    ON public.venue_registry_record (
        source_system,
        source_venue_id,
        effective_from_season,
        effective_to_season
    );

CREATE TABLE IF NOT EXISTS public.venue_game_override (
    override_id VARCHAR(96) PRIMARY KEY,
    game_id VARCHAR(64) NOT NULL,
    decision_version INT NOT NULL,
    registry_record_id VARCHAR(96) NOT NULL
        REFERENCES public.venue_registry_record(registry_record_id),
    reason TEXT NOT NULL,
    evidence_uri TEXT NOT NULL,
    definition_sha256 VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_venue_game_override_version
        UNIQUE (game_id, decision_version),
    CONSTRAINT ck_venue_game_override_positive_version
        CHECK (decision_version >= 1)
);

CREATE INDEX IF NOT EXISTS idx_venue_game_override_game
    ON public.venue_game_override (game_id, decision_version);

CREATE TABLE IF NOT EXISTS public.curated_game_venue (
    game_id VARCHAR(64) PRIMARY KEY,
    season INT NOT NULL,
    week INT NOT NULL,
    mapping_status VARCHAR(16) NOT NULL,
    mapping_method VARCHAR(32) NOT NULL,
    source_venue_id VARCHAR(64),
    registry_record_id VARCHAR(96)
        REFERENCES public.venue_registry_record(registry_record_id),
    evidence_json JSONB NOT NULL DEFAULT '{}',
    candidate_registry_record_ids_json JSONB NOT NULL DEFAULT '[]',
    source_ingest_run_id VARCHAR(36) NOT NULL
        REFERENCES public.ingest_run(ingest_run_id),
    raw_nfl_schedule_id BIGINT NOT NULL
        REFERENCES public.raw_nfl_schedule(raw_nfl_schedule_id),
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT ck_curated_game_venue_status
        CHECK (mapping_status IN ('resolved', 'unresolved', 'ambiguous')),
    CONSTRAINT ck_curated_game_venue_resolution
        CHECK (
            (mapping_status = 'resolved' AND registry_record_id IS NOT NULL)
            OR (mapping_status <> 'resolved' AND registry_record_id IS NULL)
        )
);

CREATE INDEX IF NOT EXISTS idx_curated_game_venue_slice
    ON public.curated_game_venue (season, week);
CREATE INDEX IF NOT EXISTS idx_curated_game_venue_status
    ON public.curated_game_venue (mapping_status);
