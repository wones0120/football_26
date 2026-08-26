ALTER TABLE public.weather_forecast_snapshot
    DROP CONSTRAINT IF EXISTS uq_weather_forecast_snapshot_natural_key;

ALTER TABLE public.weather_forecast_snapshot
    DROP CONSTRAINT IF EXISTS ck_weather_forecast_snapshot_data_kind,
    DROP CONSTRAINT IF EXISTS ck_weather_forecast_snapshot_fixed_lead,
    DROP CONSTRAINT IF EXISTS ck_weather_forecast_snapshot_basis_kind;

ALTER TABLE public.weather_forecast_snapshot
    ALTER COLUMN fixed_lead_hours DROP NOT NULL;

ALTER TABLE public.weather_forecast_snapshot
    ADD CONSTRAINT ck_weather_forecast_snapshot_data_kind
        CHECK (
            data_kind IN (
                'historical_fixed_lead_forecast',
                'current_forecast_capture'
            )
        ),
    ADD CONSTRAINT ck_weather_forecast_snapshot_fixed_lead
        CHECK (
            (
                data_kind = 'historical_fixed_lead_forecast'
                AND fixed_lead_hours = 24
            )
            OR (
                data_kind = 'current_forecast_capture'
                AND fixed_lead_hours IS NULL
            )
        ),
    ADD CONSTRAINT ck_weather_forecast_snapshot_basis_kind
        CHECK (
            (
                data_kind = 'historical_fixed_lead_forecast'
                AND forecast_basis_kind = 'provider_fixed_lead'
            )
            OR (
                data_kind = 'current_forecast_capture'
                AND forecast_basis_kind = 'server_received_at'
                AND forecast_basis_at = received_at
            )
        );

CREATE UNIQUE INDEX IF NOT EXISTS uq_weather_forecast_snapshot_historical
    ON public.weather_forecast_snapshot (
        contract_id,
        game_id,
        registry_record_id,
        provider_model,
        fixed_lead_hours,
        valid_at
    )
    WHERE data_kind = 'historical_fixed_lead_forecast';

CREATE UNIQUE INDEX IF NOT EXISTS uq_weather_forecast_snapshot_current_receipt
    ON public.weather_forecast_snapshot (
        contract_id,
        game_id,
        registry_record_id,
        provider_model,
        valid_at,
        received_at
    )
    WHERE data_kind = 'current_forecast_capture';

CREATE INDEX IF NOT EXISTS idx_weather_forecast_snapshot_current_game_received
    ON public.weather_forecast_snapshot (game_id, received_at)
    WHERE data_kind = 'current_forecast_capture';

ALTER TABLE public.weather_forecast_capture_result
    ADD COLUMN IF NOT EXISTS capture_kind VARCHAR(24) NOT NULL
        DEFAULT 'historical_backfill',
    ADD COLUMN IF NOT EXISTS slate VARCHAR(64),
    ADD COLUMN IF NOT EXISTS slate_lock_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_weather_forecast_capture_result_kind'
          AND conrelid = 'public.weather_forecast_capture_result'::regclass
    ) THEN
        ALTER TABLE public.weather_forecast_capture_result
            ADD CONSTRAINT ck_weather_forecast_capture_result_kind
                CHECK (
                    capture_kind IN ('historical_backfill', 'current_refresh')
                );
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_weather_forecast_capture_result_kind_game_attempted
    ON public.weather_forecast_capture_result (
        capture_kind,
        game_id,
        attempted_at
    );
