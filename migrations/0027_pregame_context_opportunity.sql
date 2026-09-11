-- Extend append-only pregame context with explicit current-week opportunity signals.

ALTER TABLE public.pregame_player_context
    ADD COLUMN IF NOT EXISTS expected_snaps DOUBLE PRECISION
        CHECK (expected_snaps IS NULL OR expected_snaps >= 0.0),
    ADD COLUMN IF NOT EXISTS expected_routes DOUBLE PRECISION
        CHECK (expected_routes IS NULL OR expected_routes >= 0.0),
    ADD COLUMN IF NOT EXISTS expected_carries DOUBLE PRECISION
        CHECK (expected_carries IS NULL OR expected_carries >= 0.0),
    ADD COLUMN IF NOT EXISTS expected_targets DOUBLE PRECISION
        CHECK (expected_targets IS NULL OR expected_targets >= 0.0),
    ADD COLUMN IF NOT EXISTS red_zone_share DOUBLE PRECISION
        CHECK (red_zone_share IS NULL OR red_zone_share BETWEEN 0.0 AND 1.0),
    ADD COLUMN IF NOT EXISTS goal_line_share DOUBLE PRECISION
        CHECK (goal_line_share IS NULL OR goal_line_share BETWEEN 0.0 AND 1.0);

ALTER TABLE public.pregame_player_context
    DROP CONSTRAINT IF EXISTS pregame_player_context_check,
    DROP CONSTRAINT IF EXISTS pregame_player_context_signal_check;

ALTER TABLE public.pregame_player_context
    ADD CONSTRAINT pregame_player_context_signal_check CHECK (
        availability_probability IS NOT NULL
        OR start_probability IS NOT NULL
        OR carry_share IS NOT NULL
        OR target_share IS NOT NULL
        OR expected_snaps IS NOT NULL
        OR expected_routes IS NOT NULL
        OR expected_carries IS NOT NULL
        OR expected_targets IS NOT NULL
        OR red_zone_share IS NOT NULL
        OR goal_line_share IS NOT NULL
        OR role_label IS NOT NULL
        OR injury_status IS NOT NULL
    );
