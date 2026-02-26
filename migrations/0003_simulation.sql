CREATE TABLE IF NOT EXISTS simulation_run (
    simulation_run_id VARCHAR(36) PRIMARY KEY,
    source_system VARCHAR(32) NOT NULL,
    season INT NOT NULL,
    week INT NOT NULL,
    slate VARCHAR(64) NOT NULL,
    iterations INT NOT NULL,
    players_considered INT NOT NULL DEFAULT 0,
    players_simulated INT NOT NULL DEFAULT 0,
    status VARCHAR(24) NOT NULL,
    error_message TEXT,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP
);
ALTER TABLE IF EXISTS simulation_run ADD COLUMN IF NOT EXISTS simulation_run_id VARCHAR(36);
ALTER TABLE IF EXISTS simulation_run ADD COLUMN IF NOT EXISTS source_system VARCHAR(32);
ALTER TABLE IF EXISTS simulation_run ADD COLUMN IF NOT EXISTS season INT;
ALTER TABLE IF EXISTS simulation_run ADD COLUMN IF NOT EXISTS week INT;
ALTER TABLE IF EXISTS simulation_run ADD COLUMN IF NOT EXISTS slate VARCHAR(64);
ALTER TABLE IF EXISTS simulation_run ADD COLUMN IF NOT EXISTS iterations INT;
ALTER TABLE IF EXISTS simulation_run ADD COLUMN IF NOT EXISTS players_considered INT;
ALTER TABLE IF EXISTS simulation_run ADD COLUMN IF NOT EXISTS players_simulated INT;
ALTER TABLE IF EXISTS simulation_run ADD COLUMN IF NOT EXISTS status VARCHAR(24);
ALTER TABLE IF EXISTS simulation_run ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE IF EXISTS simulation_run ADD COLUMN IF NOT EXISTS started_at TIMESTAMP;
ALTER TABLE IF EXISTS simulation_run ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP;

CREATE TABLE IF NOT EXISTS simulated_player_outcome (
    simulated_player_outcome_id BIGSERIAL PRIMARY KEY,
    simulation_run_id VARCHAR(36) NOT NULL REFERENCES simulation_run(simulation_run_id) ON DELETE CASCADE,
    player_master_id VARCHAR(36),
    source_player_key VARCHAR(128),
    player_name VARCHAR(128) NOT NULL,
    team VARCHAR(16),
    position VARCHAR(16),
    salary INT,
    history_games INT NOT NULL DEFAULT 0,
    mean_points DOUBLE PRECISION NOT NULL,
    median_points DOUBLE PRECISION NOT NULL,
    p75_points DOUBLE PRECISION NOT NULL,
    p90_points DOUBLE PRECISION NOT NULL,
    p95_points DOUBLE PRECISION NOT NULL,
    ceiling_prob_20 DOUBLE PRECISION NOT NULL,
    ceiling_prob_25 DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_sim_outcome_run_source_key UNIQUE (simulation_run_id, source_player_key)
);
ALTER TABLE IF EXISTS simulated_player_outcome ADD COLUMN IF NOT EXISTS simulated_player_outcome_id BIGINT;
ALTER TABLE IF EXISTS simulated_player_outcome ADD COLUMN IF NOT EXISTS simulation_run_id VARCHAR(36);
ALTER TABLE IF EXISTS simulated_player_outcome ADD COLUMN IF NOT EXISTS player_master_id VARCHAR(36);
ALTER TABLE IF EXISTS simulated_player_outcome ADD COLUMN IF NOT EXISTS source_player_key VARCHAR(128);
ALTER TABLE IF EXISTS simulated_player_outcome ADD COLUMN IF NOT EXISTS player_name VARCHAR(128);
ALTER TABLE IF EXISTS simulated_player_outcome ADD COLUMN IF NOT EXISTS team VARCHAR(16);
ALTER TABLE IF EXISTS simulated_player_outcome ADD COLUMN IF NOT EXISTS position VARCHAR(16);
ALTER TABLE IF EXISTS simulated_player_outcome ADD COLUMN IF NOT EXISTS salary INT;
ALTER TABLE IF EXISTS simulated_player_outcome ADD COLUMN IF NOT EXISTS history_games INT;
ALTER TABLE IF EXISTS simulated_player_outcome ADD COLUMN IF NOT EXISTS mean_points DOUBLE PRECISION;
ALTER TABLE IF EXISTS simulated_player_outcome ADD COLUMN IF NOT EXISTS median_points DOUBLE PRECISION;
ALTER TABLE IF EXISTS simulated_player_outcome ADD COLUMN IF NOT EXISTS p75_points DOUBLE PRECISION;
ALTER TABLE IF EXISTS simulated_player_outcome ADD COLUMN IF NOT EXISTS p90_points DOUBLE PRECISION;
ALTER TABLE IF EXISTS simulated_player_outcome ADD COLUMN IF NOT EXISTS p95_points DOUBLE PRECISION;
ALTER TABLE IF EXISTS simulated_player_outcome ADD COLUMN IF NOT EXISTS ceiling_prob_20 DOUBLE PRECISION;
ALTER TABLE IF EXISTS simulated_player_outcome ADD COLUMN IF NOT EXISTS ceiling_prob_25 DOUBLE PRECISION;
ALTER TABLE IF EXISTS simulated_player_outcome ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_sim_outcome_run_p90
ON simulated_player_outcome(simulation_run_id, p90_points);
