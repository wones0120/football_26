"""Prepare a verified fresh Sunday capture using existing canonical services."""
from datetime import UTC, datetime
from pathlib import Path
import argparse, json, uuid
import pandas as pd
from sqlalchemy import text
from backend.app.db import engine, SessionLocal
from Database.dst import normalize_team
from backend.app.schemas import NflReadPySeasonRequest
from backend.app.services.source_capture import SourceCaptureService, fetch_nflreadpy_dataset
from backend.app.services.ingest import IngestService
from backend.app.services.slate_weather import SlateWeatherService
from backend.app.product_services.optimizer import _json_safe


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path);a=parser.parse_args();p=a.directory
    if (p/'preparation.json').exists():raise ValueError('Preparation already saved; choose a new capture')
    manifest=json.loads((p/'capture_manifest.json').read_text())
    native=pd.read_csv(manifest['public_sources']['dk_salary']['path'])
    games=set(native['Game Info']);pairs={tuple(sorted(g.split(' ')[0].split('@'))) for g in games}
    if not all('10/04/2026' in g for g in games):raise ValueError('Wrong Sunday date')
    draftables=json.loads((p/'native_draftables.json').read_text())
    native_ids=set(native.ID.astype(str));draftable_ids={str(r['draftableId']) for r in draftables['draftables']}
    if not native_ids<=draftable_ids:raise ValueError('Salary IDs do not match native draft group')
    with engine.connect() as c:
        rows=[dict(r) for r in c.execute(text("SELECT * FROM public.curated_salary WHERE source_system='draftkings' AND season=2026 AND week=4 AND UPPER(slate)='SUNDAY_MAIN'")).mappings()]
        aliases=[dict(r) for r in c.execute(text("SELECT * FROM public.player_alias WHERE source_system='nflreadpy'")).mappings()]
        missing=['033ec938-ecea-4589-9dba-8962be84c496','285150bc-8c9e-44f3-8900-3e00a3cc3522','2aca41af-945f-4a4d-a94d-9520dd2e11cb','3a63877d-881f-4d87-8218-04c4f7fe8518']
        historic=[dict(r) for r in c.execute(text('SELECT p.player_master_id,p.full_name,p.position,a.source_key,a.team FROM public.player_master p LEFT JOIN public.player_alias a ON a.player_master_id=p.player_master_id AND a.source_system=\'nflreadpy\' WHERE p.player_master_id=ANY(:ids)'),{'ids':missing}).mappings()]
    current=[r for r in rows if r['game_info'] in games and str(r['source_player_key']) in native_ids]
    if not (p/'fresh_salary_identities.json').exists():
        with (p/'fresh_salary_identities.json').open('x') as f:json.dump(_json_safe(current),f,indent=2)
    if not (p/'usage_identity_aliases.json').exists():
        with (p/'usage_identity_aliases.json').open('x') as f:json.dump(_json_safe(aliases),f,indent=2)
    stats=pd.read_csv(manifest['pipeline_lineage']['nflreadpy_weekly_stats']['path'])
    historical=[]
    for r in historic:
        matches=stats.loc[(stats['player_id'].astype(str)==str(r['source_key'])) & (stats.week==3)]
        historical.append({**r,'week3_native_stat_rows':matches.where(matches.notna(),None).to_dict('records'),
                           'disposition':'native_identity_resolved_actual_missing' if matches.empty else 'native_identity_and_stat_found',
                           'zero_substituted':False})
    if not (p/'historical_identity_review.json').exists():
        with (p/'historical_identity_review.json').open('x') as f:json.dump(_json_safe(historical),f,indent=2)
    schedule,version=fetch_nflreadpy_dataset('schedules',season=2026,week=4)
    schedule=schedule.loc[pd.to_numeric(schedule.week,errors='coerce').eq(4)].copy()
    schedule=schedule.loc[schedule.apply(lambda r:tuple(sorted([normalize_team(r.away_team),normalize_team(r.home_team)])) in pairs,axis=1)].copy()
    if len(schedule)!=len(pairs):raise ValueError('Schedule membership mismatch')
    # Sunday-only rows; no Thursday results enter this frame.
    cutoff=datetime.now(UTC);kickoff=datetime(2026,10,4,17,tzinfo=UTC)
    with SessionLocal() as session:
        service=SourceCaptureService(session,snapshot_root=p/'immutable_source_snapshots')
        capture=service.capture_dataframe(schedule,artifact_name='sunday_schedule_markets.csv',source_system='nflreadpy',dataset='schedules',season=2026,week=4,slate='SUNDAY_MAIN',slate_lock_at=kickoff,source_license='nflverse schedules',source_uri='nflreadpy://schedules/2026',metadata={'sunday_only':True,'provider_version':version})
        run=IngestService(session).ingest_nflreadpy_schedules(NflReadPySeasonRequest(season=2026,weeks=[4]),source_frame=pd.read_csv(capture.snapshot.artifact_path),source_path=capture.snapshot.artifact_path,ingest_run_id=str(uuid.uuid5(uuid.NAMESPACE_URL,'sunday_market/'+str(capture.snapshot.snapshot_id))))
        service.link_ingest_run(capture.snapshot.snapshot_id,run.ingest_run_id)
        snapshot_id=str(capture.snapshot.snapshot_id)
        weather=SlateWeatherService(session).report(source_system='draftkings',season=2026,week=4,slate='SUNDAY_MAIN')
    if not (p/'weather.json').exists():
        with (p/'weather.json').open('x') as f:json.dump(_json_safe(weather),f,indent=2)
    body={'native_draft_group_id':154078,'games':sorted(games),'native_salary_count':len(native),
          'resolved_salary_count':sum(bool(r['player_master_id']) for r in current),'unresolved_salaries':[r for r in current if not r['player_master_id']],
          'market_snapshot_id':snapshot_id,'market_ingest':run.model_dump(mode='json'),'prepared_at':cutoff.isoformat(),
          'contest_intent':{'assignment_status':'UNASSIGNED','intended_profile':'public_tournament_planning_unvalidated','intended_entry_count':None,'planning_lineup_count':5,'field_size':None,'entry_limit':None,'payout_structure':None,'technical_strategy':'classic_small_field_gpp','borrowed_components':'classic_large_gpp_v1; unvalidated','warning':'No upcoming Sunday plans or assignments found. No scoring weights changed.'}}
    with (p/'preparation.json').open('x') as f:json.dump(_json_safe(body),f,indent=2)
    print('prepared',len(current),'salaries,',len(games),'games; market run',run.ingest_run_id,flush=True)

if __name__=='__main__':main()
