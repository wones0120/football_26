CREATE TABLE IF NOT EXISTS actual_top_lineup (
    actual_top_lineup_id BIGSERIAL PRIMARY KEY,
    source_system VARCHAR(32) NOT NULL,
    season INT NOT NULL,
    week INT NOT NULL,
    slate VARCHAR(64) NOT NULL,
    lineup_rank INT NOT NULL,
    actual_points DOUBLE PRECISION NOT NULL,
    salary_used INT NOT NULL,
    lineup_key VARCHAR(512) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

ALTER TABLE IF EXISTS actual_top_lineup ADD COLUMN IF NOT EXISTS actual_top_lineup_id BIGINT;
ALTER TABLE IF EXISTS actual_top_lineup ADD COLUMN IF NOT EXISTS source_system VARCHAR(32);
ALTER TABLE IF EXISTS actual_top_lineup ADD COLUMN IF NOT EXISTS season INT;
ALTER TABLE IF EXISTS actual_top_lineup ADD COLUMN IF NOT EXISTS week INT;
ALTER TABLE IF EXISTS actual_top_lineup ADD COLUMN IF NOT EXISTS slate VARCHAR(64);
ALTER TABLE IF EXISTS actual_top_lineup ADD COLUMN IF NOT EXISTS lineup_rank INT;
ALTER TABLE IF EXISTS actual_top_lineup ADD COLUMN IF NOT EXISTS actual_points DOUBLE PRECISION;
ALTER TABLE IF EXISTS actual_top_lineup ADD COLUMN IF NOT EXISTS salary_used INT;
ALTER TABLE IF EXISTS actual_top_lineup ADD COLUMN IF NOT EXISTS lineup_key VARCHAR(512);
ALTER TABLE IF EXISTS actual_top_lineup ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_actual_top_lineup_slice_rank'
    ) THEN
        ALTER TABLE actual_top_lineup
        ADD CONSTRAINT uq_actual_top_lineup_slice_rank
        UNIQUE (source_system, season, week, slate, lineup_rank);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_actual_top_lineup_slice_key'
    ) THEN
        ALTER TABLE actual_top_lineup
        ADD CONSTRAINT uq_actual_top_lineup_slice_key
        UNIQUE (source_system, season, week, slate, lineup_key);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_actual_top_lineup_slice
ON actual_top_lineup(source_system, season, week, slate, lineup_rank);

CREATE TABLE IF NOT EXISTS actual_top_lineup_player (
    actual_top_lineup_player_id BIGSERIAL PRIMARY KEY,
    actual_top_lineup_id BIGINT NOT NULL REFERENCES actual_top_lineup(actual_top_lineup_id) ON DELETE CASCADE,
    slot_index INT NOT NULL,
    roster_slot VARCHAR(16),
    position VARCHAR(16) NOT NULL,
    player_master_id VARCHAR(36),
    source_player_key VARCHAR(128),
    player_name VARCHAR(128) NOT NULL,
    team VARCHAR(16),
    salary INT NOT NULL,
    actual_points DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

ALTER TABLE IF EXISTS actual_top_lineup_player ADD COLUMN IF NOT EXISTS actual_top_lineup_player_id BIGINT;
ALTER TABLE IF EXISTS actual_top_lineup_player ADD COLUMN IF NOT EXISTS actual_top_lineup_id BIGINT;
ALTER TABLE IF EXISTS actual_top_lineup_player ADD COLUMN IF NOT EXISTS slot_index INT;
ALTER TABLE IF EXISTS actual_top_lineup_player ADD COLUMN IF NOT EXISTS roster_slot VARCHAR(16);
ALTER TABLE IF EXISTS actual_top_lineup_player ADD COLUMN IF NOT EXISTS position VARCHAR(16);
ALTER TABLE IF EXISTS actual_top_lineup_player ADD COLUMN IF NOT EXISTS player_master_id VARCHAR(36);
ALTER TABLE IF EXISTS actual_top_lineup_player ADD COLUMN IF NOT EXISTS source_player_key VARCHAR(128);
ALTER TABLE IF EXISTS actual_top_lineup_player ADD COLUMN IF NOT EXISTS player_name VARCHAR(128);
ALTER TABLE IF EXISTS actual_top_lineup_player ADD COLUMN IF NOT EXISTS team VARCHAR(16);
ALTER TABLE IF EXISTS actual_top_lineup_player ADD COLUMN IF NOT EXISTS salary INT;
ALTER TABLE IF EXISTS actual_top_lineup_player ADD COLUMN IF NOT EXISTS actual_points DOUBLE PRECISION;
ALTER TABLE IF EXISTS actual_top_lineup_player ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_actual_top_lineup_player_slot'
    ) THEN
        ALTER TABLE actual_top_lineup_player
        ADD CONSTRAINT uq_actual_top_lineup_player_slot
        UNIQUE (actual_top_lineup_id, slot_index);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_actual_top_lineup_player_lineup
ON actual_top_lineup_player(actual_top_lineup_id, slot_index);
