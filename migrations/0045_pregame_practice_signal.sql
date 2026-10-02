-- Preserve sourced practice-only observations without inventing role or clearance.
-- Existing rows and append-only triggers are unchanged.
ALTER TABLE public.pregame_player_context
    DROP CONSTRAINT pregame_player_context_signal_check;

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
        OR NULLIF(BTRIM(evidence_json ->> 'practice_participation'), '') IS NOT NULL
        OR NULLIF(BTRIM(evidence_json -> 'practice_report' ->> 'practice_status'), '') IS NOT NULL
    );
