CREATE TABLE IF NOT EXISTS raw_nfl_schedule (
    raw_nfl_schedule_id BIGSERIAL PRIMARY KEY,
    ingest_run_id VARCHAR(36) NOT NULL REFERENCES ingest_run(ingest_run_id) ON DELETE CASCADE,
    source_system VARCHAR(32) NOT NULL,
    season INT NOT NULL,
    week INT,
    game_id VARCHAR(64),
    home_team VARCHAR(16),
    away_team VARCHAR(16),
    game_type VARCHAR(32),
    kickoff VARCHAR(128),
    status VARCHAR(64),
    stadium VARCHAR(128),
    raw_row_json JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL
);
ALTER TABLE IF EXISTS raw_nfl_schedule ADD COLUMN IF NOT EXISTS raw_nfl_schedule_id BIGINT;
ALTER TABLE IF EXISTS raw_nfl_schedule ADD COLUMN IF NOT EXISTS ingest_run_id VARCHAR(36);
ALTER TABLE IF EXISTS raw_nfl_schedule ADD COLUMN IF NOT EXISTS source_system VARCHAR(32);
ALTER TABLE IF EXISTS raw_nfl_schedule ADD COLUMN IF NOT EXISTS season INT;
ALTER TABLE IF EXISTS raw_nfl_schedule ADD COLUMN IF NOT EXISTS week INT;
ALTER TABLE IF EXISTS raw_nfl_schedule ADD COLUMN IF NOT EXISTS game_id VARCHAR(64);
ALTER TABLE IF EXISTS raw_nfl_schedule ADD COLUMN IF NOT EXISTS home_team VARCHAR(16);
ALTER TABLE IF EXISTS raw_nfl_schedule ADD COLUMN IF NOT EXISTS away_team VARCHAR(16);
ALTER TABLE IF EXISTS raw_nfl_schedule ADD COLUMN IF NOT EXISTS game_type VARCHAR(32);
ALTER TABLE IF EXISTS raw_nfl_schedule ADD COLUMN IF NOT EXISTS kickoff VARCHAR(128);
ALTER TABLE IF EXISTS raw_nfl_schedule ADD COLUMN IF NOT EXISTS status VARCHAR(64);
ALTER TABLE IF EXISTS raw_nfl_schedule ADD COLUMN IF NOT EXISTS stadium VARCHAR(128);
ALTER TABLE IF EXISTS raw_nfl_schedule ADD COLUMN IF NOT EXISTS raw_row_json JSONB;
ALTER TABLE IF EXISTS raw_nfl_schedule ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;
CREATE INDEX IF NOT EXISTS idx_raw_nfl_schedule_season_week
ON raw_nfl_schedule(season, week);
CREATE INDEX IF NOT EXISTS idx_raw_nfl_schedule_game_id
ON raw_nfl_schedule(game_id);

CREATE TABLE IF NOT EXISTS raw_nfl_weekly_stat (
    raw_nfl_weekly_stat_id BIGSERIAL PRIMARY KEY,
    ingest_run_id VARCHAR(36) NOT NULL REFERENCES ingest_run(ingest_run_id) ON DELETE CASCADE,
    source_system VARCHAR(32) NOT NULL,
    season INT NOT NULL,
    week INT NOT NULL,
    player_id VARCHAR(64),
    player_name VARCHAR(128),
    team VARCHAR(16),
    opponent VARCHAR(16),
    position VARCHAR(16),
    game_id VARCHAR(64),
    raw_row_json JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL
);
ALTER TABLE IF EXISTS raw_nfl_weekly_stat ADD COLUMN IF NOT EXISTS raw_nfl_weekly_stat_id BIGINT;
ALTER TABLE IF EXISTS raw_nfl_weekly_stat ADD COLUMN IF NOT EXISTS ingest_run_id VARCHAR(36);
ALTER TABLE IF EXISTS raw_nfl_weekly_stat ADD COLUMN IF NOT EXISTS source_system VARCHAR(32);
ALTER TABLE IF EXISTS raw_nfl_weekly_stat ADD COLUMN IF NOT EXISTS season INT;
ALTER TABLE IF EXISTS raw_nfl_weekly_stat ADD COLUMN IF NOT EXISTS week INT;
ALTER TABLE IF EXISTS raw_nfl_weekly_stat ADD COLUMN IF NOT EXISTS player_id VARCHAR(64);
ALTER TABLE IF EXISTS raw_nfl_weekly_stat ADD COLUMN IF NOT EXISTS player_name VARCHAR(128);
ALTER TABLE IF EXISTS raw_nfl_weekly_stat ADD COLUMN IF NOT EXISTS team VARCHAR(16);
ALTER TABLE IF EXISTS raw_nfl_weekly_stat ADD COLUMN IF NOT EXISTS opponent VARCHAR(16);
ALTER TABLE IF EXISTS raw_nfl_weekly_stat ADD COLUMN IF NOT EXISTS position VARCHAR(16);
ALTER TABLE IF EXISTS raw_nfl_weekly_stat ADD COLUMN IF NOT EXISTS game_id VARCHAR(64);
ALTER TABLE IF EXISTS raw_nfl_weekly_stat ADD COLUMN IF NOT EXISTS raw_row_json JSONB;
ALTER TABLE IF EXISTS raw_nfl_weekly_stat ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;
CREATE INDEX IF NOT EXISTS idx_raw_nfl_weekly_stat_season_week
ON raw_nfl_weekly_stat(season, week);
CREATE INDEX IF NOT EXISTS idx_raw_nfl_weekly_stat_player_id
ON raw_nfl_weekly_stat(player_id);
