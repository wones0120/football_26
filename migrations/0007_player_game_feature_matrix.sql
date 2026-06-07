CREATE TABLE IF NOT EXISTS player_game_feature_matrix (
    player_game_feature_matrix_id BIGSERIAL PRIMARY KEY,
    source_system VARCHAR(32) NOT NULL,
    season INT NOT NULL,
    week INT NOT NULL,
    game_id VARCHAR(64),
    player_id VARCHAR(64) NOT NULL,
    player_master_id VARCHAR(36),
    source_player_key VARCHAR(128),
    player_name VARCHAR(128),
    team VARCHAR(16),
    opponent VARCHAR(16),
    position VARCHAR(16) NOT NULL,
    dk_points DOUBLE PRECISION NOT NULL,
    salary INT,
    slate VARCHAR(64),
    is_home BOOLEAN,
    kickoff_bucket VARCHAR(16),
    game_total_line DOUBLE PRECISION,
    team_spread_line DOUBLE PRECISION,
    team_implied_total DOUBLE PRECISION,
    opponent_implied_total DOUBLE PRECISION,
    player_games_history INT NOT NULL DEFAULT 0,
    player_roll3_mean DOUBLE PRECISION,
    player_roll8_mean DOUBLE PRECISION,
    player_roll8_std DOUBLE PRECISION,
    player_vs_opp_roll4 DOUBLE PRECISION,
    defense_pos_allowed_roll3 DOUBLE PRECISION,
    defense_pos_allowed_roll8 DOUBLE PRECISION,
    defense_pos_allowed_p90_roll8 DOUBLE PRECISION,
    player_injury_status VARCHAR(24),
    team_skill_out_count INT NOT NULL DEFAULT 0,
    team_position_out_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS player_game_feature_matrix_id BIGINT;
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS source_system VARCHAR(32);
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS season INT;
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS week INT;
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS game_id VARCHAR(64);
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS player_id VARCHAR(64);
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS player_master_id VARCHAR(36);
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS source_player_key VARCHAR(128);
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS player_name VARCHAR(128);
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS team VARCHAR(16);
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS opponent VARCHAR(16);
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS position VARCHAR(16);
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS dk_points DOUBLE PRECISION;
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS salary INT;
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS slate VARCHAR(64);
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS is_home BOOLEAN;
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS kickoff_bucket VARCHAR(16);
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS game_total_line DOUBLE PRECISION;
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS team_spread_line DOUBLE PRECISION;
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS team_implied_total DOUBLE PRECISION;
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS opponent_implied_total DOUBLE PRECISION;
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS player_games_history INT;
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS player_roll3_mean DOUBLE PRECISION;
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS player_roll8_mean DOUBLE PRECISION;
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS player_roll8_std DOUBLE PRECISION;
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS player_vs_opp_roll4 DOUBLE PRECISION;
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS defense_pos_allowed_roll3 DOUBLE PRECISION;
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS defense_pos_allowed_roll8 DOUBLE PRECISION;
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS defense_pos_allowed_p90_roll8 DOUBLE PRECISION;
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS player_injury_status VARCHAR(24);
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS team_skill_out_count INT;
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS team_position_out_count INT;
ALTER TABLE IF EXISTS player_game_feature_matrix ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_player_game_feature_row'
    ) THEN
        ALTER TABLE player_game_feature_matrix
        ADD CONSTRAINT uq_player_game_feature_row
        UNIQUE (source_system, season, week, game_id, player_id, position);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_pgfm_slice
ON player_game_feature_matrix(source_system, season, week);

CREATE INDEX IF NOT EXISTS idx_pgfm_player
ON player_game_feature_matrix(source_system, player_master_id, season, week);

CREATE INDEX IF NOT EXISTS idx_pgfm_team_pos
ON player_game_feature_matrix(source_system, team, opponent, position, season, week);
