CREATE TABLE IF NOT EXISTS ingest_run (
    ingest_run_id VARCHAR(36) PRIMARY KEY,
    source_system VARCHAR(32) NOT NULL,
    source_table VARCHAR(64) NOT NULL,
    source_path TEXT,
    source_checksum VARCHAR(128),
    season INT,
    week INT,
    slate VARCHAR(64),
    status VARCHAR(24) NOT NULL,
    rows_raw INT NOT NULL DEFAULT 0,
    rows_curated INT NOT NULL DEFAULT 0,
    rows_unresolved INT NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP
);
ALTER TABLE IF EXISTS ingest_run ADD COLUMN IF NOT EXISTS ingest_run_id VARCHAR(36);
ALTER TABLE IF EXISTS ingest_run ADD COLUMN IF NOT EXISTS source_system VARCHAR(32);
ALTER TABLE IF EXISTS ingest_run ADD COLUMN IF NOT EXISTS source_table VARCHAR(64);
ALTER TABLE IF EXISTS ingest_run ADD COLUMN IF NOT EXISTS source_path TEXT;
ALTER TABLE IF EXISTS ingest_run ADD COLUMN IF NOT EXISTS source_checksum VARCHAR(128);
ALTER TABLE IF EXISTS ingest_run ADD COLUMN IF NOT EXISTS season INT;
ALTER TABLE IF EXISTS ingest_run ADD COLUMN IF NOT EXISTS week INT;
ALTER TABLE IF EXISTS ingest_run ADD COLUMN IF NOT EXISTS slate VARCHAR(64);
ALTER TABLE IF EXISTS ingest_run ADD COLUMN IF NOT EXISTS status VARCHAR(24);
ALTER TABLE IF EXISTS ingest_run ADD COLUMN IF NOT EXISTS rows_raw INT;
ALTER TABLE IF EXISTS ingest_run ADD COLUMN IF NOT EXISTS rows_curated INT;
ALTER TABLE IF EXISTS ingest_run ADD COLUMN IF NOT EXISTS rows_unresolved INT;
ALTER TABLE IF EXISTS ingest_run ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE IF EXISTS ingest_run ADD COLUMN IF NOT EXISTS started_at TIMESTAMP;
ALTER TABLE IF EXISTS ingest_run ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP;

CREATE TABLE IF NOT EXISTS player_master (
    player_master_id VARCHAR(36) PRIMARY KEY,
    full_name VARCHAR(128) NOT NULL,
    normalized_name VARCHAR(128) NOT NULL,
    first_name VARCHAR(64),
    last_name VARCHAR(64),
    primary_team VARCHAR(16),
    position VARCHAR(16),
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
ALTER TABLE IF EXISTS player_master ADD COLUMN IF NOT EXISTS player_master_id VARCHAR(36);
ALTER TABLE IF EXISTS player_master ADD COLUMN IF NOT EXISTS full_name VARCHAR(128);
ALTER TABLE IF EXISTS player_master ADD COLUMN IF NOT EXISTS normalized_name VARCHAR(128);
ALTER TABLE IF EXISTS player_master ADD COLUMN IF NOT EXISTS first_name VARCHAR(64);
ALTER TABLE IF EXISTS player_master ADD COLUMN IF NOT EXISTS last_name VARCHAR(64);
ALTER TABLE IF EXISTS player_master ADD COLUMN IF NOT EXISTS primary_team VARCHAR(16);
ALTER TABLE IF EXISTS player_master ADD COLUMN IF NOT EXISTS position VARCHAR(16);
ALTER TABLE IF EXISTS player_master ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;
ALTER TABLE IF EXISTS player_master ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
CREATE INDEX IF NOT EXISTS idx_player_master_normalized_name ON player_master(normalized_name);

CREATE TABLE IF NOT EXISTS player_alias (
    alias_id BIGSERIAL PRIMARY KEY,
    player_master_id VARCHAR(36) NOT NULL REFERENCES player_master(player_master_id) ON DELETE CASCADE,
    source_system VARCHAR(32) NOT NULL,
    source_key VARCHAR(128) NOT NULL,
    alias_name VARCHAR(128) NOT NULL,
    normalized_alias VARCHAR(128) NOT NULL,
    team VARCHAR(16),
    position VARCHAR(16),
    first_seen_season INT,
    first_seen_week INT,
    last_seen_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_player_alias_source_key UNIQUE (source_system, source_key)
);
ALTER TABLE IF EXISTS player_alias ADD COLUMN IF NOT EXISTS alias_id BIGINT;
ALTER TABLE IF EXISTS player_alias ADD COLUMN IF NOT EXISTS player_master_id VARCHAR(36);
ALTER TABLE IF EXISTS player_alias ADD COLUMN IF NOT EXISTS source_system VARCHAR(32);
ALTER TABLE IF EXISTS player_alias ADD COLUMN IF NOT EXISTS source_key VARCHAR(128);
ALTER TABLE IF EXISTS player_alias ADD COLUMN IF NOT EXISTS alias_name VARCHAR(128);
ALTER TABLE IF EXISTS player_alias ADD COLUMN IF NOT EXISTS normalized_alias VARCHAR(128);
ALTER TABLE IF EXISTS player_alias ADD COLUMN IF NOT EXISTS team VARCHAR(16);
ALTER TABLE IF EXISTS player_alias ADD COLUMN IF NOT EXISTS position VARCHAR(16);
ALTER TABLE IF EXISTS player_alias ADD COLUMN IF NOT EXISTS first_seen_season INT;
ALTER TABLE IF EXISTS player_alias ADD COLUMN IF NOT EXISTS first_seen_week INT;
ALTER TABLE IF EXISTS player_alias ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP;
ALTER TABLE IF EXISTS player_alias ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;
CREATE INDEX IF NOT EXISTS idx_player_alias_name_team_pos
ON player_alias(source_system, normalized_alias, team, position);

CREATE TABLE IF NOT EXISTS player_mapping_rule (
    rule_id VARCHAR(36) PRIMARY KEY,
    source_system VARCHAR(32) NOT NULL,
    rule_name VARCHAR(128) NOT NULL,
    match_pattern_json JSONB NOT NULL,
    player_master_id VARCHAR(36) NOT NULL REFERENCES player_master(player_master_id) ON DELETE CASCADE,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by VARCHAR(64) NOT NULL DEFAULT 'system',
    created_at TIMESTAMP NOT NULL
);
ALTER TABLE IF EXISTS player_mapping_rule ADD COLUMN IF NOT EXISTS rule_id VARCHAR(36);
ALTER TABLE IF EXISTS player_mapping_rule ADD COLUMN IF NOT EXISTS source_system VARCHAR(32);
ALTER TABLE IF EXISTS player_mapping_rule ADD COLUMN IF NOT EXISTS rule_name VARCHAR(128);
ALTER TABLE IF EXISTS player_mapping_rule ADD COLUMN IF NOT EXISTS match_pattern_json JSONB;
ALTER TABLE IF EXISTS player_mapping_rule ADD COLUMN IF NOT EXISTS player_master_id VARCHAR(36);
ALTER TABLE IF EXISTS player_mapping_rule ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION;
ALTER TABLE IF EXISTS player_mapping_rule ADD COLUMN IF NOT EXISTS is_active BOOLEAN;
ALTER TABLE IF EXISTS player_mapping_rule ADD COLUMN IF NOT EXISTS created_by VARCHAR(64);
ALTER TABLE IF EXISTS player_mapping_rule ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;

CREATE TABLE IF NOT EXISTS unresolved_player_queue (
    unresolved_id VARCHAR(36) PRIMARY KEY,
    ingest_run_id VARCHAR(36) NOT NULL REFERENCES ingest_run(ingest_run_id) ON DELETE CASCADE,
    source_system VARCHAR(32) NOT NULL,
    source_table VARCHAR(64) NOT NULL,
    source_player_key VARCHAR(128),
    season INT,
    week INT,
    slate VARCHAR(64),
    raw_row_json JSONB NOT NULL,
    normalized_name VARCHAR(128) NOT NULL,
    team VARCHAR(16),
    position VARCHAR(16),
    candidate_player_master_id VARCHAR(36),
    resolution_status VARCHAR(24) NOT NULL DEFAULT 'open',
    resolved_player_master_id VARCHAR(36),
    resolved_by VARCHAR(64),
    resolved_at TIMESTAMP,
    notes TEXT,
    created_at TIMESTAMP NOT NULL
);
ALTER TABLE IF EXISTS unresolved_player_queue ADD COLUMN IF NOT EXISTS unresolved_id VARCHAR(36);
ALTER TABLE IF EXISTS unresolved_player_queue ADD COLUMN IF NOT EXISTS ingest_run_id VARCHAR(36);
ALTER TABLE IF EXISTS unresolved_player_queue ADD COLUMN IF NOT EXISTS source_system VARCHAR(32);
ALTER TABLE IF EXISTS unresolved_player_queue ADD COLUMN IF NOT EXISTS source_table VARCHAR(64);
ALTER TABLE IF EXISTS unresolved_player_queue ADD COLUMN IF NOT EXISTS source_player_key VARCHAR(128);
ALTER TABLE IF EXISTS unresolved_player_queue ADD COLUMN IF NOT EXISTS season INT;
ALTER TABLE IF EXISTS unresolved_player_queue ADD COLUMN IF NOT EXISTS week INT;
ALTER TABLE IF EXISTS unresolved_player_queue ADD COLUMN IF NOT EXISTS slate VARCHAR(64);
ALTER TABLE IF EXISTS unresolved_player_queue ADD COLUMN IF NOT EXISTS raw_row_json JSONB;
ALTER TABLE IF EXISTS unresolved_player_queue ADD COLUMN IF NOT EXISTS normalized_name VARCHAR(128);
ALTER TABLE IF EXISTS unresolved_player_queue ADD COLUMN IF NOT EXISTS team VARCHAR(16);
ALTER TABLE IF EXISTS unresolved_player_queue ADD COLUMN IF NOT EXISTS position VARCHAR(16);
ALTER TABLE IF EXISTS unresolved_player_queue ADD COLUMN IF NOT EXISTS candidate_player_master_id VARCHAR(36);
ALTER TABLE IF EXISTS unresolved_player_queue ADD COLUMN IF NOT EXISTS resolution_status VARCHAR(24);
ALTER TABLE IF EXISTS unresolved_player_queue ADD COLUMN IF NOT EXISTS resolved_player_master_id VARCHAR(36);
ALTER TABLE IF EXISTS unresolved_player_queue ADD COLUMN IF NOT EXISTS resolved_by VARCHAR(64);
ALTER TABLE IF EXISTS unresolved_player_queue ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP;
ALTER TABLE IF EXISTS unresolved_player_queue ADD COLUMN IF NOT EXISTS notes TEXT;
ALTER TABLE IF EXISTS unresolved_player_queue ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;
CREATE INDEX IF NOT EXISTS idx_unresolved_status
ON unresolved_player_queue(resolution_status, source_system, season, week);

CREATE TABLE IF NOT EXISTS raw_salary_row (
    raw_salary_id BIGSERIAL PRIMARY KEY,
    ingest_run_id VARCHAR(36) NOT NULL REFERENCES ingest_run(ingest_run_id) ON DELETE CASCADE,
    source_system VARCHAR(32) NOT NULL,
    season INT NOT NULL,
    week INT NOT NULL,
    slate VARCHAR(64) NOT NULL,
    source_player_key VARCHAR(128),
    raw_row_json JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL
);
ALTER TABLE IF EXISTS raw_salary_row ADD COLUMN IF NOT EXISTS raw_salary_id BIGINT;
ALTER TABLE IF EXISTS raw_salary_row ADD COLUMN IF NOT EXISTS ingest_run_id VARCHAR(36);
ALTER TABLE IF EXISTS raw_salary_row ADD COLUMN IF NOT EXISTS source_system VARCHAR(32);
ALTER TABLE IF EXISTS raw_salary_row ADD COLUMN IF NOT EXISTS season INT;
ALTER TABLE IF EXISTS raw_salary_row ADD COLUMN IF NOT EXISTS week INT;
ALTER TABLE IF EXISTS raw_salary_row ADD COLUMN IF NOT EXISTS slate VARCHAR(64);
ALTER TABLE IF EXISTS raw_salary_row ADD COLUMN IF NOT EXISTS source_player_key VARCHAR(128);
ALTER TABLE IF EXISTS raw_salary_row ADD COLUMN IF NOT EXISTS raw_row_json JSONB;
ALTER TABLE IF EXISTS raw_salary_row ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;

CREATE TABLE IF NOT EXISTS raw_injury_row (
    raw_injury_id BIGSERIAL PRIMARY KEY,
    ingest_run_id VARCHAR(36) NOT NULL REFERENCES ingest_run(ingest_run_id) ON DELETE CASCADE,
    source_system VARCHAR(32) NOT NULL,
    season INT NOT NULL,
    week INT NOT NULL,
    slate VARCHAR(64) NOT NULL,
    source_player_key VARCHAR(128),
    raw_row_json JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL
);
ALTER TABLE IF EXISTS raw_injury_row ADD COLUMN IF NOT EXISTS raw_injury_id BIGINT;
ALTER TABLE IF EXISTS raw_injury_row ADD COLUMN IF NOT EXISTS ingest_run_id VARCHAR(36);
ALTER TABLE IF EXISTS raw_injury_row ADD COLUMN IF NOT EXISTS source_system VARCHAR(32);
ALTER TABLE IF EXISTS raw_injury_row ADD COLUMN IF NOT EXISTS season INT;
ALTER TABLE IF EXISTS raw_injury_row ADD COLUMN IF NOT EXISTS week INT;
ALTER TABLE IF EXISTS raw_injury_row ADD COLUMN IF NOT EXISTS slate VARCHAR(64);
ALTER TABLE IF EXISTS raw_injury_row ADD COLUMN IF NOT EXISTS source_player_key VARCHAR(128);
ALTER TABLE IF EXISTS raw_injury_row ADD COLUMN IF NOT EXISTS raw_row_json JSONB;
ALTER TABLE IF EXISTS raw_injury_row ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;

CREATE TABLE IF NOT EXISTS curated_salary (
    curated_salary_id BIGSERIAL PRIMARY KEY,
    ingest_run_id VARCHAR(36) NOT NULL REFERENCES ingest_run(ingest_run_id) ON DELETE CASCADE,
    source_system VARCHAR(32) NOT NULL,
    season INT NOT NULL,
    week INT NOT NULL,
    slate VARCHAR(64) NOT NULL,
    source_player_key VARCHAR(128) NOT NULL,
    player_master_id VARCHAR(36),
    player_name VARCHAR(128) NOT NULL,
    normalized_name VARCHAR(128) NOT NULL,
    team VARCHAR(16),
    opponent VARCHAR(16),
    position VARCHAR(16),
    roster_position VARCHAR(16),
    salary INT,
    game_info VARCHAR(128),
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_curated_salary_row UNIQUE (season, week, slate, source_system, source_player_key)
);
ALTER TABLE IF EXISTS curated_salary ADD COLUMN IF NOT EXISTS curated_salary_id BIGINT;
ALTER TABLE IF EXISTS curated_salary ADD COLUMN IF NOT EXISTS ingest_run_id VARCHAR(36);
ALTER TABLE IF EXISTS curated_salary ADD COLUMN IF NOT EXISTS source_system VARCHAR(32);
ALTER TABLE IF EXISTS curated_salary ADD COLUMN IF NOT EXISTS season INT;
ALTER TABLE IF EXISTS curated_salary ADD COLUMN IF NOT EXISTS week INT;
ALTER TABLE IF EXISTS curated_salary ADD COLUMN IF NOT EXISTS slate VARCHAR(64);
ALTER TABLE IF EXISTS curated_salary ADD COLUMN IF NOT EXISTS source_player_key VARCHAR(128);
ALTER TABLE IF EXISTS curated_salary ADD COLUMN IF NOT EXISTS player_master_id VARCHAR(36);
ALTER TABLE IF EXISTS curated_salary ADD COLUMN IF NOT EXISTS player_name VARCHAR(128);
ALTER TABLE IF EXISTS curated_salary ADD COLUMN IF NOT EXISTS normalized_name VARCHAR(128);
ALTER TABLE IF EXISTS curated_salary ADD COLUMN IF NOT EXISTS team VARCHAR(16);
ALTER TABLE IF EXISTS curated_salary ADD COLUMN IF NOT EXISTS opponent VARCHAR(16);
ALTER TABLE IF EXISTS curated_salary ADD COLUMN IF NOT EXISTS position VARCHAR(16);
ALTER TABLE IF EXISTS curated_salary ADD COLUMN IF NOT EXISTS roster_position VARCHAR(16);
ALTER TABLE IF EXISTS curated_salary ADD COLUMN IF NOT EXISTS salary INT;
ALTER TABLE IF EXISTS curated_salary ADD COLUMN IF NOT EXISTS game_info VARCHAR(128);
ALTER TABLE IF EXISTS curated_salary ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;
CREATE INDEX IF NOT EXISTS idx_curated_salary_player_master
ON curated_salary(player_master_id, season, week);

CREATE TABLE IF NOT EXISTS curated_injury (
    curated_injury_id BIGSERIAL PRIMARY KEY,
    ingest_run_id VARCHAR(36) NOT NULL REFERENCES ingest_run(ingest_run_id) ON DELETE CASCADE,
    source_system VARCHAR(32) NOT NULL,
    season INT NOT NULL,
    week INT NOT NULL,
    slate VARCHAR(64) NOT NULL,
    source_player_key VARCHAR(128) NOT NULL,
    player_master_id VARCHAR(36),
    player_name VARCHAR(128) NOT NULL,
    normalized_name VARCHAR(128) NOT NULL,
    team VARCHAR(16),
    position VARCHAR(16),
    injury_status VARCHAR(64),
    injury_details TEXT,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_curated_injury_row UNIQUE (season, week, slate, source_system, source_player_key)
);
ALTER TABLE IF EXISTS curated_injury ADD COLUMN IF NOT EXISTS curated_injury_id BIGINT;
ALTER TABLE IF EXISTS curated_injury ADD COLUMN IF NOT EXISTS ingest_run_id VARCHAR(36);
ALTER TABLE IF EXISTS curated_injury ADD COLUMN IF NOT EXISTS source_system VARCHAR(32);
ALTER TABLE IF EXISTS curated_injury ADD COLUMN IF NOT EXISTS season INT;
ALTER TABLE IF EXISTS curated_injury ADD COLUMN IF NOT EXISTS week INT;
ALTER TABLE IF EXISTS curated_injury ADD COLUMN IF NOT EXISTS slate VARCHAR(64);
ALTER TABLE IF EXISTS curated_injury ADD COLUMN IF NOT EXISTS source_player_key VARCHAR(128);
ALTER TABLE IF EXISTS curated_injury ADD COLUMN IF NOT EXISTS player_master_id VARCHAR(36);
ALTER TABLE IF EXISTS curated_injury ADD COLUMN IF NOT EXISTS player_name VARCHAR(128);
ALTER TABLE IF EXISTS curated_injury ADD COLUMN IF NOT EXISTS normalized_name VARCHAR(128);
ALTER TABLE IF EXISTS curated_injury ADD COLUMN IF NOT EXISTS team VARCHAR(16);
ALTER TABLE IF EXISTS curated_injury ADD COLUMN IF NOT EXISTS position VARCHAR(16);
ALTER TABLE IF EXISTS curated_injury ADD COLUMN IF NOT EXISTS injury_status VARCHAR(64);
ALTER TABLE IF EXISTS curated_injury ADD COLUMN IF NOT EXISTS injury_details TEXT;
ALTER TABLE IF EXISTS curated_injury ADD COLUMN IF NOT EXISTS created_at TIMESTAMP;
CREATE INDEX IF NOT EXISTS idx_curated_injury_player_master
ON curated_injury(player_master_id, season, week);
