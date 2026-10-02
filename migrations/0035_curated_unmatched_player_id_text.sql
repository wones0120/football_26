-- nflverse player identifiers are GSIS strings such as 00-0036919.
-- Older development databases inferred this legacy review column as BIGINT.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'curated_unmatched'
          AND column_name = 'player_id'
          AND data_type <> 'text'
    ) THEN
        ALTER TABLE public.curated_unmatched
            ALTER COLUMN player_id TYPE TEXT
            USING player_id::TEXT;
    END IF;
END$$;
