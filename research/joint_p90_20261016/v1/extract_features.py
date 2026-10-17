from pathlib import Path
import json
from sqlalchemy import text
from backend.app.product_services.optimizer import OptimizerService,_json_safe
keys=['team_implied_total','team_spread_line','game_total_line','targets_mean_3','carries_mean_3','pregame_target_share','pregame_carry_share','target_share_mean_3','carry_share_mean_3','pregame_injury_status','pregame_role_label','pregame_availability_probability','pregame_context_observed_at','salary','snap_share_mean_3']
fields=','.join("f.feature_json->'"+k+"' AS "+k for k in keys)
q="SELECT p.projection_run_id,p.player_id,p.game_id,m.created_at model_created,f.created_at feature_created,g.created_at feature_run_created,g.training_cutoff,m.params_json->>'code_hash' code_hash,"+fields+" FROM target.player_projection p JOIN target.model_run m USING(model_run_id) JOIN target.feature_player_game f ON f.feature_run_id=m.feature_run_id AND f.player_id=p.player_id AND f.game_id=p.game_id JOIN target.feature_generation_run g ON g.feature_run_id=m.feature_run_id WHERE p.season=2026 AND p.week<=5"
with OptimizerService().engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'));v=_json_safe([dict(r) for r in c.execute(text(q)).mappings()])
Path('research/joint_p90_20261016/v1/features.json').write_text(json.dumps(v,sort_keys=True)+'\n');print(len(v))
