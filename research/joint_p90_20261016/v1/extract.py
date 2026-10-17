from pathlib import Path
import json,hashlib
from sqlalchemy import text
from backend.app.product_services.optimizer import OptimizerService,_json_safe
P=Path(__file__).resolve().parent
Q={
'forecasts':'''SELECT p.*,r.created_at run_created,r.status run_status FROM target.player_projection p JOIN target.projection_run r USING(projection_run_id) WHERE p.season=2026 AND p.week<=5''',
'schedule':'''SELECT DISTINCT ON(game_id) game_id,season,week,raw_row_json,created_at,ingest_run_id FROM public.raw_nfl_schedule WHERE season=2026 AND week<=5 ORDER BY game_id,created_at DESC,raw_nfl_schedule_id DESC''',
'stats':'''SELECT DISTINCT ON(player_id,game_id) player_id,player_name,team,position,game_id,raw_row_json,created_at,ingest_run_id FROM public.raw_nfl_weekly_stat WHERE season=2026 AND week<=5 AND source_system='nflreadpy' ORDER BY player_id,game_id,created_at DESC,raw_nfl_weekly_stat_id DESC''',
'aliases':'''SELECT DISTINCT player_master_id,source_key FROM public.player_alias WHERE source_system='nflreadpy' ''',
'salaries':'''SELECT season,week,player_master_id,team,position,salary,created_at,source_player_key FROM public.curated_salary WHERE season=2026 AND week<=5 AND source_system='draftkings' ''',
'participation':'''SELECT DISTINCT ON(player_master_id,game_id) player_master_id,game_id,team,position,participation_status,offense_snaps,box_score_activity,created_at FROM public.curated_player_game_participation WHERE season=2026 AND week<=5 ORDER BY player_master_id,game_id,created_at DESC'''
}
with OptimizerService().engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 for name,q in Q.items():
  v=_json_safe([dict(r) for r in c.execute(text(q)).mappings()]);data=(json.dumps(v,sort_keys=True,default=str)+'\n').encode();(P/(name+'.json')).write_bytes(data);print(name,len(v),hashlib.sha256(data).hexdigest())
