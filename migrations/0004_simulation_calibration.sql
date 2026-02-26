CREATE TABLE IF NOT EXISTS simulation_calibration_factor (
    simulation_calibration_factor_id BIGSERIAL PRIMARY KEY,
    source_system VARCHAR(32) NOT NULL,
    slate VARCHAR(64) NOT NULL,
    scope VARCHAR(24) NOT NULL,
    scope_key VARCHAR(64) NOT NULL,
    calibrated_season INT NOT NULL,
    calibrated_week INT NOT NULL,
    sample_size INT NOT NULL DEFAULT 0,
    multiplier DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    created_at TIMESTAMP NOT NULL
);
ALTER TABLE IF EXISTS simulation_calibration_factor ADD COLUMN IF NOT EXISTS simulation_calibration_factor_id BIGINT;
ALTER TABLE IF EXISTS simulation_calibration_factor ADD COLUMN IF NOT EXISTS source_system VARCHAR(32);
ALTER TABLE IF EXISTS simulation_calibration_factor ADD COLUMN IF NOT EXISTS slate VARCHAR(64);
ALTER TABLE IF EXISTS simulation_calibration_factor ADD COLUMN IF NOT EXISTS scope VARCHAR(24);
ALTER TABLE IF EXISTS simulation_calibration_factor ADD COLUMN IF NOT EXISTS scope_key VARCHAR(64);
ALTER TABLE IF EXISTS simulation_calibration_factor ADD COLUMN IF NOT EXISTS calibrated_season INT;
ALTER TABLE IF EXISTS simulation_calibration_factor ADD COLUMN IF NOT EXISTS calibrated_week INT;
ALTER TABLE IF EXISTS simulation_calibration_factor ADD COLUMN IF NOT EXISTS sample_size INT;
ALTER TABLE IF EXISTS simulation_calibration_factor ADD COLUMN IF NOT EXISTS multiplier DOUBLE PRECISION;
ALTER TABLE IF EXISTS simulation_calibration_factor ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_sim_calibration_lookup
ON simulation_calibration_factor(source_system, slate, scope, scope_key, calibrated_season, calibrated_week);

CREATE INDEX IF NOT EXISTS idx_sim_calibration_week
ON simulation_calibration_factor(source_system, calibrated_season, calibrated_week);
