CREATE TABLE IF NOT EXISTS public.curated_game_weather (
    game_id VARCHAR(64) PRIMARY KEY,
    season INT NOT NULL,
    week INT NOT NULL,
    game_type VARCHAR(16),
    kickoff_at TIMESTAMPTZ,
    home_team VARCHAR(16),
    away_team VARCHAR(16),
    stadium VARCHAR(128),
    roof VARCHAR(16),
    surface VARCHAR(64),
    temperature_f DOUBLE PRECISION,
    wind_mph DOUBLE PRECISION,
    weather_status VARCHAR(32) NOT NULL,
    data_kind VARCHAR(48) NOT NULL,
    observation_basis VARCHAR(64) NOT NULL,
    observed_at TIMESTAMPTZ,
    effective_at TIMESTAMPTZ,
    replay_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    quality_flags_json JSONB NOT NULL DEFAULT '[]',
    source_system VARCHAR(32) NOT NULL,
    source_ingest_run_id VARCHAR(36) NOT NULL
        REFERENCES public.ingest_run(ingest_run_id),
    raw_nfl_schedule_id BIGINT NOT NULL
        REFERENCES public.raw_nfl_schedule(raw_nfl_schedule_id),
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT ck_curated_game_weather_retrospective_only
        CHECK (replay_eligible = FALSE AND observed_at IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_curated_game_weather_slice
    ON public.curated_game_weather (season, week);
CREATE INDEX IF NOT EXISTS idx_curated_game_weather_status
    ON public.curated_game_weather (weather_status);
