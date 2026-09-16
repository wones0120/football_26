-- Append-only ownership identity decisions, including explicit unresolved review rows.
CREATE TABLE IF NOT EXISTS target.contest_ownership_observation (
    observation_id TEXT PRIMARY KEY,
    contest_id TEXT NOT NULL REFERENCES target.dfs_contest(contest_id),
    source_file_id TEXT NOT NULL REFERENCES target.source_file_import(source_file_id),
    season INTEGER NOT NULL,
    week INTEGER NOT NULL,
    slate TEXT NOT NULL,
    player_display_name TEXT NOT NULL,
    roster_position TEXT NOT NULL,
    player_id TEXT,
    resolution_status TEXT NOT NULL CHECK (resolution_status IN ('resolved','unresolved','ambiguous')),
    actual_ownership DOUBLE PRECISION NOT NULL CHECK (actual_ownership BETWEEN 0 AND 100),
    actual_points DOUBLE PRECISION,
    evidence_json JSONB NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((resolution_status = 'resolved') = (player_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_contest_ownership_review
    ON target.contest_ownership_observation (contest_id, resolution_status);
