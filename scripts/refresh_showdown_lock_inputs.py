"""Append sourced context and run the normal projection pipeline for one freeze.

No optimizer, user preferences, model parameters, or entry outputs are modified.
Final game dressing remains explicitly unverified unless separately reconciled.
"""
import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import re

from sqlalchemy import text

from backend.app.db import engine, SessionLocal
from backend.app.product_services.pregame_context import PregameContextService
from backend.app.product_services.predictions import PredictionsService
from backend.app.services.lineup_learning import LineupLearningService
from backend.app.services.source_capture import SourceCaptureService
from scripts.audit_showdown_gameday import save, verify_salary_rows
from scripts.finalize_showdown_gameday_shadow import read_frozen


def normalize_name(name):
    return ' '.join(re.sub(r'\b(jr|sr|ii|iii|iv)\b', '', re.sub('[^a-z0-9 ]', ' ', name.lower())).split())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--morning', type=Path, required=True)
    args = parser.parse_args()
    base, sources = args.directory, args.directory/'public_sources'
    if (base/'prepared_context_request.json').exists():
        raise ValueError('Refresh records are immutable; use a new directory')
    manifest = json.loads((sources/'capture_manifest.json').read_text())
    old = read_frozen(args.morning/'refreshed_database_freeze.json')['payload']
    kickoff = datetime.fromisoformat('2026-10-01T20:15:00-04:00')
    # This run is the requested PIT/CLE Week 4 slate, not a generic schedule resolver.
    result = {'started_at':datetime.now(UTC).isoformat(), 'season':2026, 'week':4,
              'slate':'THURSDAY_NIGHT', 'production_parameters_changed':False}
    market_text = json.loads((sources/'market.parsed.json').read_text())['text']
    start = market_text.index('PIT Steelers @ CLE Browns')
    market_text = market_text[start:market_text.index('IND Colts @ WAS Commanders',start)]
    spread = float(re.search(r'Spread PIT Steelers ([−+-]?[0-9.]+)',market_text)[1].replace('−','-'))
    total = float(re.search(r'Total Over ([0-9.]+)',market_text)[1])
    # The checked unchanged market is already represented by immutable database lineage.
    old_pool = old['player_pool']
    old_pit = next(p for p in old_pool if p['player_team']=='PIT')
    if abs(total-float(old_pit['game_total_line']))>1e-9 or abs(spread-float(old_pit['team_spread_line']))>1e-9:
        raise ValueError('Market changed: ingest the captured observation through the normal market service before rebuilding')
    result['market'] = {'pit_spread':spread,'total':total,'observed_at':manifest['market']['retrieved_at'],'unchanged':True}
    snapshots = {}
    with SessionLocal() as session:
        capture_service = SourceCaptureService(session,snapshot_root=base/'immutable_source_snapshots')
        salary = capture_service.capture_and_ingest_draftkings_salary(
            sources/'dk_salary.csv',season=2026,week=4,slate='THURSDAY_NIGHT',slate_lock_at=kickoff,
            source_license='Official public DraftKings salary download; upstream terms apply',source_uri=manifest['dk_salary']['url'])
        if salary.ingest.rows_unresolved or salary.ingest.rows_raw!=102:
            raise ValueError('Fresh native DraftKings identity universe is unresolved or changed')
        result['salary_ingest'] = salary.ingest.model_dump(mode='json')
        result['salary_snapshot_id'] = str(salary.capture.snapshot.snapshot_id)
        for key,meta in manifest.items():
            if key=='dk_salary' or 'sha256' not in meta:continue
            observed = datetime.fromisoformat(meta['retrieved_at'])
            capture = SourceCaptureService(session,snapshot_root=base/'immutable_source_snapshots',clock=lambda at=observed:at).capture_file(
                Path(meta['path']),source_system='nws' if key=='weather' else 'draftkings_public' if key in {'market','dk_contest'} else 'official_nfl_club',
                dataset='showdown_'+key,season=2026,week=4,slate='THURSDAY_NIGHT',source_license='Public source; upstream terms apply',
                source_uri=meta['url'],slate_lock_at=kickoff,media_type=meta['content_type'],metadata={'capture_manifest_sha256':meta['sha256']})
            snapshots[key] = str(capture.snapshot.snapshot_id)
        observed = datetime.fromisoformat(manifest['weather']['completed_at'])
        hourly = SourceCaptureService(session,snapshot_root=base/'immutable_source_snapshots',clock=lambda:observed).capture_file(
            sources/'weather_hourly.json',source_system='nws',dataset='showdown_weather_hourly',season=2026,week=4,slate='THURSDAY_NIGHT',
            source_license='Official NWS public forecast',source_uri=manifest['weather']['hourly_url'],slate_lock_at=kickoff,media_type='application/json')
        snapshots['weather_hourly'] = str(hourly.snapshot.snapshot_id)
        session.commit()
    with engine.connect() as connection:
        salaries = [dict(r) for r in connection.execute(text("SELECT DISTINCT ON (player_master_id) player_master_id,player_name,team,position,player_status FROM public.curated_salary WHERE season=2026 AND week=4 AND upper(slate)='THURSDAY_NIGHT' AND player_master_id IS NOT NULL ORDER BY player_master_id,CASE WHEN roster_position='FLEX' THEN 0 ELSE 1 END,created_at DESC")).mappings()]
    import csv
    with (sources/'dk_salary.csv').open(encoding='utf-8-sig',newline='') as file:
        identity = verify_salary_rows(list(csv.DictReader(file)),old['salaries'])
    save(base/'salary_verification.json',identity)
    active, depth = {}, {}
    for team in ('PIT','CLE'):
        roster = json.loads((sources/(team.lower()+'_roster.parsed.json')).read_text())['tables'][0]
        active[team] = {normalize_name(r[0]):r[2] for r in roster[1:] if len(r)>2}
        tables = json.loads((sources/(team.lower()+'_depth.parsed.json')).read_text())['tables']
        depth[team] = [(r[0],r[1]) for t in tables for r in t[1:] if len(r)>1]
    # Official final club game-status reports, not an assumption from a Q flag.
    out_players = {('PIT','RB','Rico Dowdle'),('CLE','WR','Tylan Wallace')}
    players = []
    for row in salaries:
        team, position, name = row['team'],row['position'],row['player_name']
        key = normalize_name(name)
        roster_position = active[team].get(key)
        on_roster = roster_position is not None
        if on_roster and not (position=='DST' or roster_position==position or position=='RB' and roster_position in {'FB','RB/WR'}):
            raise ValueError('Official team/position identity mismatch: '+name)
        official_out = (team,position,name) in out_players
        out = official_out or row['player_status'] in {'IR','OUT','PUP','NFI'}
        available = position=='DST' or on_roster and not out
        first = any(position==p and key in normalize_name(n.lstrip('*')) for p,n in depth[team])
        is_qb, starter = position=='QB',first and position=='QB'
        players.append({'player_id':str(row['player_master_id']),'team':team,'position':position,
            'availability_probability':float(available),'start_probability':float(starter) if is_qb else None,
            'role_label':'STARTER' if starter or available and first else 'BACKUP' if is_qb else None,
            'injury_status':'OUT' if out else 'ACTIVE' if available else None,
            'evidence':{'nfl_state':'DEFENSE_UNIT' if position=='DST' else 'OUT' if official_out else 'ACTIVE_ROSTER_PENDING_GAME_INACTIVES' if available else 'NOT_ON_ACTIVE_ROSTER_NO_VERIFIED_CURRENT_ELEVATION',
                'final_game_inactives_published':False,'observed_position':roster_position,'depth_first':first,
                'role_uncertain':available and not first and position in {'RB','WR','TE'},'official_out':official_out,
                'availability_basis':'Current official roster, depth chart and club game status; dressing remains pending. No invented opportunity shares.',
                'source_urls':[manifest[team.lower()+suffix]['url'] for suffix in ['_roster','_depth','_injuries','_transactions']],
                'source_snapshot_ids':[snapshots[team.lower()+suffix] for suffix in ['_roster','_depth','_injuries','_transactions']]}})
    payload = {'season':2026,'week':4,'slate':'THURSDAY_NIGHT','source':'official_club_final_lock_afternoon_refresh',
        'source_uri':manifest['pit_injuries']['url'],'observed_at':max(datetime.fromisoformat(v['completed_at']) for v in manifest.values() if 'completed_at' in v),
        'notes':'Official afternoon source changes reconciled. Final inactives unavailable; roster assumptions explicitly pending. No weather/DST manual adjustments; existing projection pipeline unchanged.',
        'players':players}
    save(base/'prepared_context_request.json',json.loads(json.dumps(payload,default=str)))
    context = PregameContextService().create_run(payload)
    result.update(context_run_id=str(context['context_run_id']),context_players=len(players),source_snapshot_ids=snapshots)
    print({'context_run_id':result['context_run_id'],'players':len(players),'salary_unresolved':0},flush=True)
    with SessionLocal() as session:
        result['features'] = LineupLearningService(session).rebuild_player_game_feature_matrix(
            source_system='draftkings',season_start=2026,season_end=2026,slate='THURSDAY_NIGHT',weeks=[4],progress_hook=lambda value:print(value,flush=True))
    projection = PredictionsService().train_and_predict(2026,4,slate='THURSDAY_NIGHT',data_cutoff_at=datetime.now(UTC))
    result.update(projection_run_id=str(projection.projection_run_id),projection_records=len(projection.records),finished_at=datetime.now(UTC).isoformat())
    save(base/'input_refresh_lineage.json',json.loads(json.dumps(result,default=str)))
    print({'projection_run_id':result['projection_run_id'],'projection_records':len(projection.records)},flush=True)


if __name__=='__main__':main()
