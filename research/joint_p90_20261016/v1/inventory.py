from pathlib import Path
import json
from sqlalchemy import text
from backend.app.product_services.optimizer import OptimizerService,_json_safe
P=Path(__file__).resolve().parent
queries={
'forecast_scope':'''SELECT p.season,p.week,count(*) rows,count(distinct p.projection_run_id) runs,min(p.created_at) first_stored,max(p.created_at) last_stored,count(*) filter(where g.kickoff_at is null) kickoff_missing,count(*) filter(where p.created_at<g.kickoff_at AND r.created_at<g.kickoff_at AND p.data_cutoff_at<=p.created_at) prekick_rows,count(*) filter(where a.player_id is not null) actual_rows,count(*) filter(where a.player_id is not null AND p.created_at<g.kickoff_at AND r.created_at<g.kickoff_at AND p.data_cutoff_at<=p.created_at) prekick_actual_rows FROM target.player_projection p JOIN target.projection_run r USING(projection_run_id) LEFT JOIN target.dim_game g ON g.game_id=p.game_id LEFT JOIN target.fact_player_game_actual a ON (a.season,a.week,a.game_id,a.player_id)=(p.season,p.week,p.game_id,p.player_id) GROUP BY 1,2 ORDER BY 1,2''',
'actual_scope':'''SELECT season,week,count(*) rows,count(distinct game_id) games,count(distinct position) positions FROM target.fact_player_game_actual GROUP BY 1,2 ORDER BY 1,2''',
'forecast_examples':'''SELECT p.*,r.created_at run_created FROM target.player_projection p JOIN target.projection_run r USING(projection_run_id) ORDER BY p.created_at ASC LIMIT 2''',
'model_schema':'''SELECT table_schema,table_name,column_name FROM information_schema.columns WHERE table_name IN ('model_run','evaluation_record','lineup_learning_record') ORDER BY table_schema,table_name,ordinal_position'''
}
with OptimizerService().engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 out={key:[dict(r) for r in c.execute(text(q)).mappings()] for key,q in queries.items()}
(P/'inventory.json').write_text(json.dumps(_json_safe(out),indent=2)+'\n');print(json.dumps(_json_safe(out['forecast_scope']),indent=2))
