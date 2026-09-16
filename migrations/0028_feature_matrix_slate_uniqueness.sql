ALTER TABLE IF EXISTS player_game_feature_matrix
DROP CONSTRAINT IF EXISTS uq_player_game_feature_row;

ALTER TABLE IF EXISTS player_game_feature_matrix
ADD CONSTRAINT uq_player_game_feature_row
UNIQUE (source_system, season, week, slate, game_id, player_id, position);
