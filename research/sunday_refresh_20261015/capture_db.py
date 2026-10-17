from backend.app.db import engine
from sqlalchemy import text
from pathlib import Path
from datetime import datetime,UTC
import json
r=Path('research/sunday_refresh_20261015/v1')
queries={'salary':"select * from curated_salary where season=2026 and week=6 and slate='SUNDAY_MAIN' order by game_info,team,player_master_id",'tables':"select table_name from information_schema.tables where table_schema='public' and (table_name like '%schedule%' or table_name like '%projection%')"}
with engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 for k,q in queries.items():
  rows=[dict(x) for x in c.execute(text(q)).mappings()]
  (r/(k+'_capture.json')).write_text(json.dumps({'observed_at':datetime.now(UTC).isoformat(),'access':'read-only transaction','query':q,'rows':rows},default=str,indent=2)+'\n')
  print(k,len(rows))
queries={'aliases':"select * from player_alias where player_master_id in (select player_master_id from curated_salary where season=2026 and week=6 and slate='SUNDAY_MAIN')",'stats':"select distinct on (player_id,week) * from raw_nfl_weekly_stat where season=2026 and week between 1 and 5 order by player_id,week,created_at desc,raw_nfl_weekly_stat_id desc",'snaps':"select distinct on (pfr_player_id,week) * from raw_nfl_snap_count where season=2026 and week between 1 and 5 order by pfr_player_id,week,created_at desc,raw_nfl_snap_count_id desc",'schedule':"select * from raw_nfl_schedule where season=2026 and week=6",'projection_runs':"select * from target.projection_run where season=2026 and week=6 and slate_id='SUNDAY_MAIN' order by created_at desc"}
with engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 for k,q in queries.items():
  try:
   rows=[dict(x) for x in c.execute(text(q)).mappings()]
   (r/(k+'_capture.json')).write_text(json.dumps({'observed_at':datetime.now(UTC).isoformat(),'access':'read-only transaction','query':q,'rows':rows},default=str,indent=2)+'\n');print(k,len(rows))
  except Exception as e: print(k,type(e).__name__);c.rollback();c.execute(text('SET TRANSACTION READ ONLY'))
