from backend.app.db import engine
from sqlalchemy import text
from pathlib import Path
import json
from datetime import datetime, timezone
p=Path(__file__).resolve().parent
with engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 queries={'salary':"select * from curated_salary where season=2026 and week=6 and slate='SUNDAY_MAIN' order by game_info,team,player_master_id",'projection_runs':"select * from target.projection_run where season=2026 and week=6 order by created_at desc",'columns':"select table_schema,table_name,column_name from information_schema.columns where table_schema='target' and (table_name like '%context%' or table_name in ('player_projection','feature_snapshot')) order by table_name,ordinal_position",'injuries':"select * from curated_injury where season=2026 and week=6 and slate='SUNDAY_MAIN'",'history_coverage':"select season,max(week) as maxweek,count(*) from raw_nfl_weekly_stat where season in (2025,2026) group by season"}
 for k,q in queries.items():
  dest=p/(k+'_capture.json')
  if dest.exists(): continue
  rows=[dict(r) for r in c.execute(text(q)).mappings()]; dest.write_text(json.dumps({'observed_at':datetime.now(timezone.utc).isoformat(),'access':'read-only transaction','query':q,'rows':rows},default=str,indent=2)+'\n'); print(k,len(rows))
 c.rollback()
