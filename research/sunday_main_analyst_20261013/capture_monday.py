from backend.app.db import engine
from sqlalchemy import text
from pathlib import Path
import json
from datetime import datetime,timezone
p=Path(__file__).resolve().parent
if (p/'monday_contests_capture.json').exists():raise SystemExit('Immutable capture exists; create new research version for refresh.')
with engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 queries={'monday_contests':"select * from target.dfs_contest where season=2026 and week=5 and upper(slate_id)='MONDAY_NIGHT'",'monday_columns':"select table_name,column_name from information_schema.columns where table_schema='target' and table_name in ('dfs_contest_entry_result','dfs_contest') order by table_name,ordinal_position"}
 for k,q in queries.items():
  rows=[dict(x) for x in c.execute(text(q)).mappings()];(p/(k+'_capture.json')).write_text(json.dumps({'query':q,'observed_at':datetime.now(timezone.utc).isoformat(),'rows':rows},default=str,indent=2)+'\n');print(k,len(rows))
 c.rollback()
