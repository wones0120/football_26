from backend.app.db import engine
from sqlalchemy import text
from pathlib import Path
import json,re,collections
from datetime import datetime,timezone
p=Path(__file__).resolve().parent
if (p/'monday_winners_capture.json').exists():raise SystemExit('Immutable capture exists; create new research version for refresh.')
with engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 q="select e.* from target.dfs_contest_entry_result e join target.dfs_contest c using(contest_id) where c.season=2026 and c.week=5 and upper(c.slate_id)='MONDAY_NIGHT' and e.rank=1 order by e.contest_id,e.entry_id"
 winners=[dict(r) for r in c.execute(text(q)).mappings()];print([(r['contest_id'],r['entry_name'],r['entry_points'],r['lineup_text']) for r in winners])
 counts=[dict(r) for r in c.execute(text("select e.contest_id,count(*) as loaded_rows,count(distinct entry_id) as unique_entries from target.dfs_contest_entry_result e join target.dfs_contest c using(contest_id) where c.season=2026 and c.week=5 and upper(c.slate_id)='MONDAY_NIGHT' group by e.contest_id")).mappings()]
 names={re.sub(r'\s*\(\d+(/\d+)?\)\s*$','',r['entry_name']) for r in winners};cohort=[]
 for name in names:
  cohort.extend(dict(r) for r in c.execute(text("select e.* from target.dfs_contest_entry_result e join target.dfs_contest c using(contest_id) where c.season=2026 and c.week=5 and upper(c.slate_id)='MONDAY_NIGHT' and (entry_name=:name or entry_name like :prefix) order by contest_id,rank,entry_id"),{'name':name,'prefix':name+' (%'}).mappings())
 dest=p/'monday_winners_capture.json';dest.write_text(json.dumps({'observed_at':datetime.now(timezone.utc).isoformat(),'access':'read-only DB','winner_query':q,'winner_rows':winners,'loaded_counts':counts,'display_prefix_policy':'Trailing numeric entry suffix removed only; this is displayed entrant-label grouping, not proven human ownership or intent.','display_names':sorted(names),'cohort_rows':cohort},default=str,indent=2)+'\n');print('cohort',len(cohort));c.rollback()
