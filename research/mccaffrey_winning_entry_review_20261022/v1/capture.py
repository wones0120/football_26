"""Read-only review of an observed winning entry and original pregame records."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from sqlalchemy import text
from backend.app.db import engine

out=Path(__file__).parent
target=out/'database_evidence.json'
if target.exists():raise SystemExit('Preserve existing snapshot')
saved=json.loads(Path('research/opportunity_component_response_20261019/v1/new_count_saved_results.json').read_text())
pids=[p['player_id'] for p in saved['results'][0]]
source_ids=sorted({i for p in saved['results'][0] for i in p['workload_forecast']['source_ids']})
with engine.connect() as c:
    c.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
    c.execute(text("SET LOCAL statement_timeout='20000'"))
    def q(sql,params=None):return [dict(r) for r in c.execute(text(sql),params or {}).mappings()]
    data={
        'entries':q("SELECT e.*,c.contest_name,c.field_size,c.week,c.slate_id FROM target.dfs_contest_entry_result e JOIN target.dfs_contest c USING(contest_id) WHERE c.season=2026 AND c.week=6 AND c.slate_id='MONDAY_NIGHT' AND c.contest_format='showdown' AND e.entry_name ILIKE 'wones0120%' ORDER BY e.contest_id,e.rank"),
        'runs':q("SELECT * FROM target.optimizer_run WHERE season=2026 AND week=6 AND slate_id='MONDAY_NIGHT' AND contest_format='showdown' ORDER BY created_at"),
        'lineups':q("SELECT l.*,jsonb_agg(jsonb_build_object('player_id',p.player_id,'slot_index',p.slot_index,'slot',p.roster_position,'salary',p.salary,'player_json',p.player_json) ORDER BY p.slot_index) AS players FROM target.lineup l JOIN target.optimizer_run r USING(optimizer_run_id) JOIN target.lineup_player p USING(lineup_id) WHERE r.season=2026 AND r.week=6 AND r.slate_id='MONDAY_NIGHT' AND r.contest_format='showdown' GROUP BY l.lineup_id ORDER BY l.created_at,l.lineup_number"),
        'prior_stats':q("SELECT s.*,i.started_at AS ingest_started_at,i.completed_at AS ingest_completed_at,i.source_checksum FROM raw_nfl_weekly_stat s JOIN ingest_run i USING(ingest_run_id) WHERE s.raw_nfl_weekly_stat_id=ANY(:ids)",{'ids':source_ids}),
        'actual_stats':q("SELECT DISTINCT ON (s.raw_nfl_weekly_stat_id) s.* FROM raw_nfl_weekly_stat s JOIN player_alias a ON a.source_system='nflreadpy' AND a.source_key=s.player_id WHERE s.season=2026 AND s.week=6 AND a.player_master_id::text=ANY(:ids) ORDER BY s.raw_nfl_weekly_stat_id DESC",{'ids':pids}),
    }
    for table in ['contest_entry_assignment','dk_upload_export','dk_export_validation']:
        columns=q("SELECT column_name FROM information_schema.columns WHERE table_schema='target' AND table_name=:t",{'t':table})
        names={r['column_name'] for r in columns}
        if 'season' in names and 'week' in names:
            data[table]=q('SELECT * FROM target.'+table+' WHERE season=2026 AND week=6')
        elif 'optimizer_run_id' in names:
            data[table]=q('SELECT * FROM target.'+table+" WHERE optimizer_run_id IN (SELECT optimizer_run_id FROM target.optimizer_run WHERE season=2026 AND week=6 AND slate_id='MONDAY_NIGHT' AND contest_format='showdown')")
        else:data[table+'_columns']=sorted(names)
target.write_text(json.dumps(data,default=str,indent=2)+'\n')
(out/'manifest.json').write_text(json.dumps({'captured_at':datetime.now(timezone.utc).isoformat(),'source':'local database read-only transaction; no DraftKings access','sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'counts':{k:len(v) for k,v in data.items()}},indent=2)+'\n')
print({k:len(v) for k,v in data.items()})
