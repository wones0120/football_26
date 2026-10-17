from backend.app.db import engine
from sqlalchemy import text
from pathlib import Path
import json
from datetime import datetime,timezone
p=Path(__file__).resolve().parent
with engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 queries={'aliases':"select * from player_alias where player_master_id in (select player_master_id from curated_salary where season=2026 and week=6 and slate='SUNDAY_MAIN')",'stats':"select distinct on (player_id,week) * from raw_nfl_weekly_stat where season=2026 and week between 1 and 5 order by player_id,week,created_at desc,raw_nfl_weekly_stat_id desc",'snaps':"select distinct on (pfr_player_id,week) * from raw_nfl_snap_count where season=2026 and week between 1 and 5 order by pfr_player_id,week,created_at desc,raw_nfl_snap_count_id desc",'participation':"select * from curated_player_game_participation where season=2026 and week between 1 and 5",'schedule':"select * from raw_nfl_schedule where season=2026 and week=6",'feature_columns':"select table_schema,table_name,column_name from information_schema.columns where table_schema='target' and table_name like '%feature%' order by table_name,ordinal_position"}
 for k,q in queries.items():
  dest=p/(k+'_capture.json')
  if dest.exists():continue
  rows=[dict(r) for r in c.execute(text(q)).mappings()];dest.write_text(json.dumps({'observed_at':datetime.now(timezone.utc).isoformat(),'access':'read-only transaction','query':q,'rows':rows},default=str,indent=2)+'\n');print(k,len(rows))
 c.rollback()
