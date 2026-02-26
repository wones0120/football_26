ALTER TABLE IF EXISTS simulation_calibration_factor
ADD COLUMN IF NOT EXISTS low_salary_threshold INT;

ALTER TABLE IF EXISTS simulation_calibration_factor
ADD COLUMN IF NOT EXISTS low_salary_hit_points DOUBLE PRECISION;

CREATE INDEX IF NOT EXISTS idx_sim_calibration_low_salary
ON simulation_calibration_factor(source_system, slate, low_salary_threshold, low_salary_hit_points);
