-- Older ownership tables predate per-contest source lineage.
ALTER TABLE IF EXISTS public.dk_ownership ADD COLUMN IF NOT EXISTS contest_id TEXT;
ALTER TABLE IF EXISTS public.dk_ownership ADD COLUMN IF NOT EXISTS source_file_id TEXT;
