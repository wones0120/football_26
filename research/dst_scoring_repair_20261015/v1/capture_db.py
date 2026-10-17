from pathlib import Path
from datetime import datetime,UTC
import json,hashlib
from sqlalchemy import text
from backend.app.product_services.optimizer import OptimizerService,_json_safe
P=Path(__file__).resolve().parent;s=OptimizerService()
queries={
'schedules_2026':"SELECT * FROM public.raw_nfl_schedule WHERE season=2026 AND week BETWEEN 1 AND 5 ORDER BY week,game_id,created_at,raw_nfl_schedule_id",
'stats_counts':"SELECT season,week,count(*) AS rows,count(DISTINCT player_id) AS players FROM public.raw_nfl_weekly_stat WHERE season=2026 AND week BETWEEN 1 AND 5 GROUP BY season,week ORDER BY week",
'live_main_run':"SELECT * FROM target.active_projection_run WHERE season=2026 AND week=6 AND slate_id='SUNDAY_MAIN'",
'live_main_values':"SELECT * FROM target.player_projection WHERE projection_run_id='b2ae485d-f436-470b-a52c-fa53095bbd4d' ORDER BY player_id"}
with s.engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 for name,q in queries.items():
  rows=[dict(r) for r in c.execute(text(q)).mappings()];v=_json_safe(dict(captured_at=datetime.now(UTC).isoformat(),query=q,rows=rows));(P/(name+'.json')).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n');print(name,len(rows),flush=True)
