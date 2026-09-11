ALTER TABLE IF EXISTS public.curated_salary
    ADD COLUMN IF NOT EXISTS player_status VARCHAR(32);

ALTER TABLE IF EXISTS target.snapshot_salary
    ADD COLUMN IF NOT EXISTS player_status TEXT;
