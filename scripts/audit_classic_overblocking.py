"""Read-only evidence export for the Classic readiness overblocking repair."""
from datetime import UTC, datetime
import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.db import engine
from backend.app.product_services.optimizer import OptimizerService, _json_safe
from backend.app.product_services.slate_preparation import SlatePreparationRequest, source_manifest

OUT = Path('artifacts/classic_gpp_overblocking_repair')
NAMES = ['Mitch Tinsley', 'Ihmir Smith-Marsette', 'Drew Ogletree', 'Scotty Miller', 'Lew Nichols', 'Jackson Meeks']


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with Session(engine) as session:
        session.execute(text('SET TRANSACTION READ ONLY'))
        manifest = source_manifest(session, SlatePreparationRequest(season=2026, week=5, slate='SUNDAY_MAIN', action='rebuild'))
        def read(sql, params=None):
            return [dict(r) for r in session.execute(text(sql), params or {}).mappings()]
        data = {'manifest': manifest}
        data['ingest'] = read('SELECT * FROM public.ingest_run WHERE ingest_run_id=:id', {'id': '5dd55a4b-b108-433b-bfaf-125c636a1705'})
        data['identity_queue'] = read('SELECT * FROM public.unresolved_player_queue WHERE ingest_run_id=:id', {'id': '5dd55a4b-b108-433b-bfaf-125c636a1705'})
        salaries = [r for r in manifest['salaries'] if r['player_name'] in NAMES or not r.get('player_master_id')]
        ids = [r['player_master_id'] for r in salaries if r.get('player_master_id')]
        data['players'] = read('SELECT * FROM public.player_master WHERE player_master_id=ANY(:ids)', {'ids': ids})
        data['aliases'] = read('SELECT * FROM public.player_alias WHERE player_master_id=ANY(:ids)', {'ids': ids})
        keys = [r['source_key'] for r in data['aliases'] if r['source_system'] in {'nflreadpy','nflverse'}]
        names = NAMES + [r['player_name'] for r in salaries]
        data['rosters'] = read("SELECT * FROM public.raw_nfl_weekly_roster WHERE season=2026 AND (gsis_id=ANY(:keys) OR player_name=ANY(:names) OR raw_row_json->>'full_name'=ANY(:names) OR raw_row_json->>'football_name'=ANY(:names)) ORDER BY week DESC", {'keys': keys, 'names': names})
        data['all_native_aliases'] = read("SELECT * FROM public.player_alias WHERE source_system IN ('nflreadpy','nflverse') AND source_key=ANY(:keys)", {'keys': [r['gsis_id'] for r in data['rosters'] if r.get('gsis_id')]})
        data['master_candidates'] = read("SELECT * FROM public.player_master WHERE full_name=ANY(:names)", {'names': names})
        data['quarantine'] = read("SELECT * FROM target.identity_quarantine WHERE season=2026 AND week=5 AND UPPER(slate)='SUNDAY_MAIN' AND source_table='curated_salary'")
        data['raw_salary'] = read('SELECT * FROM public.raw_salary_row WHERE ingest_run_id=:id', {'id': '5dd55a4b-b108-433b-bfaf-125c636a1705'})
        data['snapshots'] = read("SELECT * FROM public.source_snapshot WHERE (season=2026 AND week=5 AND dataset ILIKE '%salar%') OR content_sha256=:hash", {'hash': data['ingest'][0]['source_checksum']})
        data['schemas'] = read("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema IN ('public','target') AND table_name IN ('raw_nfl_weekly_roster','raw_salary_row','projection','projection_run')")
    path = OUT/'evidence_before.json'
    path.write_text(json.dumps(_json_safe(data), indent=2, default=str))
    print('Export:', path)
    print('Import:', data['ingest'])
    print('Target salaries:', [{k:r.get(k) for k in ('player_name','player_master_id','team','position','salary','game_info','source_player_key','player_status')} for r in salaries])
    print('Snapshots:', [{k:r.get(k) for k in ('snapshot_id','source_uri','artifact_path','observed_at','captured_at','metadata_json')} for r in data['snapshots']])
    print('Queue:', data['identity_queue'])


if __name__ == '__main__':
    main()
