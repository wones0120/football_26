from pathlib import Path
from datetime import datetime,timezone
import json
from sqlalchemy import text
from backend.app.db import engine
p=Path('/private/tmp/wones_analyst_20261021_v1')
queries={
'aliases':"select * from player_alias where player_master_id in (select player_master_id from curated_salary where season=2026 and week=7)",
'stats':"select distinct on (player_id,week) * from raw_nfl_weekly_stat where season=2026 and week between 1 and 6 order by player_id,week,created_at desc,raw_nfl_weekly_stat_id desc",
'snaps':"select distinct on (pfr_player_id,week) * from raw_nfl_snap_count where season=2026 and week between 1 and 6 order by pfr_player_id,week,created_at desc,raw_nfl_snap_count_id desc",
'participation':"select * from curated_player_game_participation where season=2026 and week between 1 and 6",
'ingest':"select * from ingest_run where season=2026 and week=7 order by started_at",
'feature_columns':"select table_schema,table_name,column_name from information_schema.columns where table_schema='target' and table_name in ('feature_snapshot','player_projection') order by table_name,ordinal_position"
}
with engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 for n,q in queries.items():
  rows=[dict(x) for x in c.execute(text(q)).mappings()]
  f=p/(n+'_capture.json');assert not f.exists()
  f.write_text(json.dumps({'observed_at':datetime.now(timezone.utc).isoformat(),'access':'SET TRANSACTION READ ONLY; rollback','query':q,'rows':rows},default=str,indent=2)+'\n');print(n,len(rows));print(json.dumps(rows[:1],default=str)[:1600])
 c.rollback()
