from pathlib import Path
from datetime import datetime,timezone
import json,time
from sqlalchemy import text
from backend.app.db import engine
out=Path('research/readiness_2026_20261020/v1');started=datetime.now(timezone.utc);timer=time.monotonic()
queries={
'schedule':"""SELECT DISTINCT ON(game_id) raw_nfl_schedule_id,ingest_run_id,source_system,week,game_id,home_team,away_team,game_type,kickoff,status,raw_row_json->>'home_score' home_score,raw_row_json->>'away_score' away_score,raw_row_json->>'result' result,created_at FROM public.raw_nfl_schedule WHERE season=2026 AND game_type='REG' AND game_id IS NOT NULL ORDER BY game_id,created_at DESC,raw_nfl_schedule_id DESC LIMIT 300""",
'weekly_inventory':"""SELECT week,source_system,COUNT(*) revision_rows,COUNT(DISTINCT player_id) native_ids,MIN(created_at) first_import,MAX(created_at) last_import FROM public.raw_nfl_weekly_stat WHERE season=2026 AND raw_row_json->>'season_type'='REG' GROUP BY week,source_system ORDER BY week,source_system""",
'latest_weekly':"""SELECT DISTINCT ON(player_id,week) raw_nfl_weekly_stat_id,ingest_run_id,player_id,week,team,position,created_at,raw_row_json->>'game_id' game_id,raw_row_json->>'gameid' gameid,raw_row_json->>'attempts' attempts,raw_row_json->>'passing_attempts' passing_attempts,raw_row_json->>'carries' carries,raw_row_json->>'rushing_attempts' rushing_attempts,raw_row_json->>'targets' targets FROM public.raw_nfl_weekly_stat WHERE season=2026 AND raw_row_json->>'season_type'='REG' AND week BETWEEN1 AND18 ORDER BY player_id,week,created_at DESC,raw_nfl_weekly_stat_id DESC LIMIT 16000""",
'roster_inventory':"""SELECT week,source_system,COUNT(*) rows,COUNT(DISTINCT gsis_id) native_ids,COUNT(DISTINCT team) teams,MIN(created_at) first_import,MAX(created_at) last_import FROM public.raw_nfl_weekly_roster WHERE season=2026 GROUP BY week,source_system ORDER BY week,source_system""",
'injury_inventory':"""SELECT week,source_system,COUNT(*) rows,COUNT(DISTINCT source_player_key) source_keys,MIN(created_at) first_import,MAX(created_at) last_import FROM public.raw_injury_row WHERE season=2026 GROUP BY week,source_system ORDER BY week,source_system""",
'snapshot_inventory':"""SELECT snapshot_id,source_system,dataset,week,observed_at,effective_at,captured_at,slate_lock_at,observation_basis,content_sha256,byte_count,row_count,artifact_path,source_uri FROM public.source_snapshot WHERE season=2026 ORDER BY captured_at,snapshot_id LIMIT500""",
'snapshot_count':"""SELECT COUNT(*) total FROM public.source_snapshot WHERE season=2026""",
'aliases':"""SELECT source_key,player_master_id::text player_master_id,created_at FROM public.player_alias WHERE source_system='nflreadpy' ORDER BY source_key,player_master_id LIMIT20000"""}
# Fixed syntax spacing below is literal SQL, not user-controlled interpolation.
queries={k:v.replace('BETWEEN1 AND18','BETWEEN 1 AND 18').replace('LIMIT500','LIMIT 500').replace('LIMIT20000','LIMIT 20000')for k,v in queries.items()}
data={}
with engine.connect() as connection:
 with connection.begin():
  connection.execute(text('SET TRANSACTION READ ONLY'))
  connection.execute(text("SET LOCAL statement_timeout='30000ms'"))
  for name,q in queries.items():
   data[name]=[dict(r)for r in connection.execute(text(q)).mappings().all()]
record=dict(status='READ_ONLY_DATABASE_METADATA_AND_NATIVE_PROJECTION',started_at=started.isoformat(),completed_at=datetime.now(timezone.utc).isoformat(),elapsed_seconds=time.monotonic()-timer,queries=queries,results=data,mutation_statements=0,original_pregame_availability='Import/capture clocks are not original game publication proof')
(out/'DB_READONLY_PROJECTION.json').write_text(json.dumps(record,indent=2,sort_keys=True,default=str)+'\n')
print({k:len(v)for k,v in data.items()})
