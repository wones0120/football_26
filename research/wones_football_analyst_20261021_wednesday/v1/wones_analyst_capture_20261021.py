import json,csv,hashlib
from pathlib import Path
from datetime import datetime,timezone
from sqlalchemy import text
from backend.app.db import engine
p=Path('/private/tmp/wones_analyst_20261021_v1');p.mkdir(exist_ok=True)
queries={
'salary':'select * from curated_salary where season=2026 and week=7 order by slate,game_info,team,player_master_id',
'schedule':'select * from raw_nfl_schedule where season=2026 and week=7',
'projection_runs':'select * from target.projection_run where season=2026 and week=7 order by created_at desc',
'injury_counts':'select slate,count(*) from curated_injury where season=2026 and week=7 group by slate',
'columns':"select table_schema,table_name,column_name from information_schema.columns where table_name in ('player_master','player_alias','features_player_week','prediction_player','raw_nfl_weekly_stats') order by table_name,ordinal_position"
}
with engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 for n,q in queries.items():
  rows=[dict(r) for r in c.execute(text(q)).mappings()]
  (p/(n+'_capture.json')).write_text(json.dumps({'observed_at':datetime.now(timezone.utc).isoformat(),'access':'SET TRANSACTION READ ONLY; rollback','query':q,'rows':rows},default=str,indent=2)+'\n')
  print(n,len(rows));print(json.dumps(rows[:2],default=str)[:1800])
 c.rollback()
for f in sorted(Path('/Users/wones/NFL').glob('*2026_7*.csv')):
 b=f.read_bytes(); rows=list(csv.DictReader(b.decode('utf-8-sig').splitlines()))
 rec={'path':str(f),'sha256':hashlib.sha256(b).hexdigest(),'observed_at':datetime.now(timezone.utc).isoformat(),'rows':rows}
 (p/(f.stem+'.json')).write_text(json.dumps(rec,indent=2)+'\n')
 print(f.name,len(rows),rows[:1]);print('games',sorted({r.get('Game Info','') for r in rows}))
