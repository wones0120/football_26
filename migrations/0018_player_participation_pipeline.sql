-- Add immutable weekly roster/snap snapshots and leakage-safe availability features.

CREATE TABLE IF NOT EXISTS public.raw_nfl_weekly_roster (
    raw_nfl_weekly_roster_id BIGSERIAL PRIMARY KEY,
    ingest_run_id VARCHAR(36) NOT NULL
        REFERENCES public.ingest_run(ingest_run_id) ON DELETE CASCADE,
    source_system VARCHAR(32) NOT NULL,
    season INT NOT NULL,
    week INT NOT NULL,
    game_type VARCHAR(16),
    team VARCHAR(16),
    position VARCHAR(16),
    depth_chart_position VARCHAR(16),
    roster_status VARCHAR(32),
    player_name VARCHAR(128),
    gsis_id VARCHAR(64),
    pfr_id VARCHAR(64),
    raw_row_json JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_raw_nfl_weekly_roster_slice
    ON public.raw_nfl_weekly_roster (season, week, team);
CREATE INDEX IF NOT EXISTS idx_raw_nfl_weekly_roster_gsis
    ON public.raw_nfl_weekly_roster (gsis_id);
CREATE INDEX IF NOT EXISTS idx_raw_nfl_weekly_roster_pfr
    ON public.raw_nfl_weekly_roster (pfr_id);

CREATE TABLE IF NOT EXISTS public.raw_nfl_snap_count (
    raw_nfl_snap_count_id BIGSERIAL PRIMARY KEY,
    ingest_run_id VARCHAR(36) NOT NULL
        REFERENCES public.ingest_run(ingest_run_id) ON DELETE CASCADE,
    source_system VARCHAR(32) NOT NULL,
    season INT NOT NULL,
    week INT NOT NULL,
    game_type VARCHAR(16),
    game_id VARCHAR(64),
    pfr_game_id VARCHAR(64),
    pfr_player_id VARCHAR(64),
    player_name VARCHAR(128),
    team VARCHAR(16),
    opponent VARCHAR(16),
    position VARCHAR(16),
    offense_snaps INT,
    offense_pct DOUBLE PRECISION,
    defense_snaps INT,
    defense_pct DOUBLE PRECISION,
    st_snaps INT,
    st_pct DOUBLE PRECISION,
    raw_row_json JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_raw_nfl_snap_count_slice
    ON public.raw_nfl_snap_count (season, week, team);
CREATE INDEX IF NOT EXISTS idx_raw_nfl_snap_count_player
    ON public.raw_nfl_snap_count (pfr_player_id, season, week);

CREATE TABLE IF NOT EXISTS public.curated_player_game_participation (
    curated_player_game_participation_id BIGSERIAL PRIMARY KEY,
    season INT NOT NULL,
    week INT NOT NULL,
    game_id VARCHAR(64) NOT NULL,
    game_type VARCHAR(16),
    player_master_id VARCHAR(36) NOT NULL
        REFERENCES public.player_master(player_master_id),
    player_name VARCHAR(128),
    team VARCHAR(16) NOT NULL,
    opponent VARCHAR(16),
    position VARCHAR(16),
    roster_status VARCHAR(32),
    participation_status VARCHAR(24) NOT NULL
        CHECK (participation_status IN ('played_confirmed', 'played_inferred', 'did_not_play', 'unknown')),
    participation_reason VARCHAR(48) NOT NULL,
    offense_snaps INT,
    offense_snap_share DOUBLE PRECISION,
    defense_snaps INT,
    defense_snap_share DOUBLE PRECISION,
    st_snaps INT,
    st_snap_share DOUBLE PRECISION,
    box_score_activity BOOLEAN NOT NULL DEFAULT FALSE,
    roster_ingest_run_id VARCHAR(36),
    snap_ingest_run_id VARCHAR(36),
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_curated_player_game_participation
        UNIQUE (season, week, game_id, player_master_id, team)
);

CREATE INDEX IF NOT EXISTS idx_curated_participation_slice
    ON public.curated_player_game_participation (season, week, team);
CREATE INDEX IF NOT EXISTS idx_curated_participation_player
    ON public.curated_player_game_participation (player_master_id, season, week);

CREATE TABLE IF NOT EXISTS public.features_team_game_availability (
    features_team_game_availability_id BIGSERIAL PRIMARY KEY,
    season INT NOT NULL,
    week INT NOT NULL,
    game_id VARCHAR(64) NOT NULL,
    team VARCHAR(16) NOT NULL,
    opponent VARCHAR(16) NOT NULL,
    team_offense_missing_share_lag1 DOUBLE PRECISION NOT NULL DEFAULT 0,
    team_defense_missing_share_lag1 DOUBLE PRECISION NOT NULL DEFAULT 0,
    team_offense_missing_count_lag1 INT NOT NULL DEFAULT 0,
    team_defense_missing_count_lag1 INT NOT NULL DEFAULT 0,
    opponent_offense_missing_share_lag1 DOUBLE PRECISION NOT NULL DEFAULT 0,
    opponent_defense_missing_share_lag1 DOUBLE PRECISION NOT NULL DEFAULT 0,
    opponent_offense_missing_count_lag1 INT NOT NULL DEFAULT 0,
    opponent_defense_missing_count_lag1 INT NOT NULL DEFAULT 0,
    team_source_game_id VARCHAR(64),
    team_source_week INT,
    opponent_source_game_id VARCHAR(64),
    opponent_source_week INT,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_features_team_game_availability
        UNIQUE (season, week, game_id, team)
);

CREATE INDEX IF NOT EXISTS idx_features_team_game_availability_slice
    ON public.features_team_game_availability (season, week, team);

ALTER TABLE public.player_game_feature_matrix
    ADD COLUMN IF NOT EXISTS team_offense_missing_share_lag1 DOUBLE PRECISION NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS team_defense_missing_share_lag1 DOUBLE PRECISION NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS opponent_offense_missing_share_lag1 DOUBLE PRECISION NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS opponent_defense_missing_share_lag1 DOUBLE PRECISION NOT NULL DEFAULT 0;
