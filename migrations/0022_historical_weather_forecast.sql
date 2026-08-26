CREATE TABLE IF NOT EXISTS public.weather_forecast_snapshot (
    forecast_snapshot_id VARCHAR(36) PRIMARY KEY,
    contract_id VARCHAR(64) NOT NULL,
    data_kind VARCHAR(48) NOT NULL,
    game_id VARCHAR(64) NOT NULL,
    season INT NOT NULL,
    week INT NOT NULL,
    registry_record_id VARCHAR(96) NOT NULL
        REFERENCES public.venue_registry_record(registry_record_id),
    provider VARCHAR(48) NOT NULL,
    provider_model VARCHAR(64) NOT NULL,
    variables_json JSONB NOT NULL DEFAULT '[]',
    valid_at TIMESTAMPTZ NOT NULL,
    fixed_lead_hours INT NOT NULL,
    forecast_basis_at TIMESTAMPTZ NOT NULL,
    forecast_basis_kind VARCHAR(48) NOT NULL,
    provider_issued_at TIMESTAMPTZ,
    provider_available_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ NOT NULL,
    requested_latitude DOUBLE PRECISION NOT NULL,
    requested_longitude DOUBLE PRECISION NOT NULL,
    returned_latitude DOUBLE PRECISION,
    returned_longitude DOUBLE PRECISION,
    returned_elevation_m DOUBLE PRECISION,
    returned_timezone VARCHAR(64),
    temperature_c DOUBLE PRECISION,
    relative_humidity_pct DOUBLE PRECISION,
    precipitation_mm DOUBLE PRECISION,
    wind_speed_mps DOUBLE PRECISION,
    wind_direction_degrees DOUBLE PRECISION,
    wind_gusts_mps DOUBLE PRECISION,
    status VARCHAR(16) NOT NULL,
    units_json JSONB NOT NULL DEFAULT '{}',
    quality_flags_json JSONB NOT NULL DEFAULT '[]',
    raw_artifact_path TEXT NOT NULL,
    manifest_path TEXT NOT NULL,
    source_uri_redacted TEXT NOT NULL,
    raw_sha256 VARCHAR(64) NOT NULL,
    byte_count BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_weather_forecast_snapshot_natural_key
        UNIQUE (
            contract_id,
            game_id,
            registry_record_id,
            provider_model,
            fixed_lead_hours,
            valid_at
        ),
    CONSTRAINT ck_weather_forecast_snapshot_data_kind
        CHECK (data_kind = 'historical_fixed_lead_forecast'),
    CONSTRAINT ck_weather_forecast_snapshot_fixed_lead
        CHECK (fixed_lead_hours = 24),
    CONSTRAINT ck_weather_forecast_snapshot_basis_kind
        CHECK (forecast_basis_kind = 'provider_fixed_lead'),
    CONSTRAINT ck_weather_forecast_snapshot_provider_timing_null
        CHECK (provider_issued_at IS NULL AND provider_available_at IS NULL),
    CONSTRAINT ck_weather_forecast_snapshot_status
        CHECK (status IN ('available', 'partial', 'missing')),
    CONSTRAINT ck_weather_forecast_snapshot_requested_coordinates
        CHECK (
            requested_latitude BETWEEN -90 AND 90
            AND requested_longitude BETWEEN -180 AND 180
        ),
    CONSTRAINT ck_weather_forecast_snapshot_returned_latitude
        CHECK (
            returned_latitude IS NULL
            OR returned_latitude BETWEEN -90 AND 90
        ),
    CONSTRAINT ck_weather_forecast_snapshot_returned_longitude
        CHECK (
            returned_longitude IS NULL
            OR returned_longitude BETWEEN -180 AND 180
        )
);

CREATE INDEX IF NOT EXISTS idx_weather_forecast_snapshot_game_valid
    ON public.weather_forecast_snapshot (game_id, valid_at);
CREATE INDEX IF NOT EXISTS idx_weather_forecast_snapshot_slice
    ON public.weather_forecast_snapshot (season, week);

CREATE TABLE IF NOT EXISTS public.weather_forecast_capture_result (
    capture_result_id VARCHAR(36) PRIMARY KEY,
    ingest_run_id VARCHAR(36) NOT NULL
        REFERENCES public.ingest_run(ingest_run_id) ON DELETE CASCADE,
    game_id VARCHAR(64) NOT NULL,
    season INT NOT NULL,
    week INT,
    registry_record_id VARCHAR(96)
        REFERENCES public.venue_registry_record(registry_record_id),
    forecast_snapshot_id VARCHAR(36)
        REFERENCES public.weather_forecast_snapshot(forecast_snapshot_id),
    valid_at TIMESTAMPTZ,
    status VARCHAR(16) NOT NULL,
    reason TEXT,
    request_uri_redacted TEXT,
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_weather_forecast_capture_result_run_game
        UNIQUE (ingest_run_id, game_id),
    CONSTRAINT ck_weather_forecast_capture_result_status
        CHECK (
            status IN (
                'captured', 'reused', 'partial', 'missing', 'error', 'quarantined'
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_weather_forecast_capture_result_run_status
    ON public.weather_forecast_capture_result (ingest_run_id, status);
CREATE INDEX IF NOT EXISTS idx_weather_forecast_capture_result_game
    ON public.weather_forecast_capture_result (game_id);

CREATE OR REPLACE FUNCTION public.reject_weather_forecast_snapshot_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'weather_forecast_snapshot rows are immutable; append a new contract version instead';
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'trg_weather_forecast_snapshot_immutable'
          AND tgrelid = 'public.weather_forecast_snapshot'::regclass
    ) THEN
        CREATE TRIGGER trg_weather_forecast_snapshot_immutable
        BEFORE UPDATE OR DELETE ON public.weather_forecast_snapshot
        FOR EACH ROW EXECUTE FUNCTION public.reject_weather_forecast_snapshot_mutation();
    END IF;
END;
$$;
