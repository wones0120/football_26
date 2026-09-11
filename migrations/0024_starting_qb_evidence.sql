-- Persist one auditable starting-QB selection per team and slate.

CREATE TABLE IF NOT EXISTS public.starting_qb_evidence (
    starting_qb_id BIGSERIAL PRIMARY KEY,
    season INT NOT NULL,
    week INT NOT NULL,
    slate VARCHAR(64) NOT NULL,
    team VARCHAR(16) NOT NULL,
    player_id VARCHAR(64) NOT NULL,
    player_master_id VARCHAR(36) NOT NULL
        REFERENCES public.player_master(player_master_id),
    player_name VARCHAR(128) NOT NULL,
    status VARCHAR(24) NOT NULL,
    source VARCHAR(64) NOT NULL,
    evidence_tier VARCHAR(24) NOT NULL
        CHECK (evidence_tier IN ('confirmed', 'inferred')),
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_starting_qb_evidence_slate_team
        UNIQUE (season, week, slate, team)
);

CREATE INDEX IF NOT EXISTS idx_starting_qb_evidence_player
    ON public.starting_qb_evidence (player_master_id, season, week);
