"""Build a separate Sunday preview through existing context/projection services.

No projection parameters or strategy defaults are changed. Official depth-chart
roles are expectations, never final game availability or numerical usage forecasts.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import re

import pandas as pd
from sqlalchemy import text

from backend.app.db import engine, SessionLocal
from backend.app.product_services.optimizer import _json_safe
from backend.app.product_services.predictions import PredictionsService
from backend.app.product_services.pregame_context import PregameContextService
from backend.app.product_services.starters import StartingQBService
from backend.app.services.lineup_learning import LineupLearningService


def normalize(name):
    return ' '.join(re.sub(r'\b(jr|sr|ii|iii|iv)\b','',re.sub(r'[^a-z0-9 ]',' ',str(name).lower())).split())


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    parser.add_argument('--resume-prepared-context',action='store_true')
    parser.add_argument('--resume-model',action='store_true');args=parser.parse_args()
    base=args.directory
    if (base/'refresh_lineage.json').exists():raise ValueError('Completed refresh exists; use a new snapshot')
    if (base/'context_request.json').exists() and not (args.resume_prepared_context or args.resume_model):raise ValueError('Context freeze exists; use a new snapshot')
    manifest=json.loads((base/'capture_manifest.json').read_text());lineage=manifest['pipeline_lineage']
    salaries=json.loads((base/'fresh_salary_identities.json').read_text())
    by_identity={(row['team'],row['position'],normalize(row['player_name'])):row for row in salaries if row['player_master_id']}
    depth_evidence={};starters=[];review=[]
    for team in sorted({r['team'] for r in salaries}):
        key=team.lower()+'_depth';path=base/'public_sources'/(key+'.parsed.json')
        if not path.exists():continue
        tables=json.loads(path.read_text())['tables']
        for table in tables:
            for row in table[1:]:
                if len(row)<2:continue
                position={'HB':'RB','FB':'RB'}.get(row[0],row[0])
                if position not in {'QB','RB','WR','TE'}:continue
                for ordinal,name in enumerate(row[1:],1):
                    if not name:continue
                    salary=by_identity.get((team,position,normalize(name)))
                    if not salary:
                        review.append({'team':team,'position':position,'cell':name,'ordinal':ordinal,
                                       'reason':'no_unambiguous_team_position_normalized_alias_match'})
                        continue
                    pid=salary['player_master_id']
                    evidence={'ordinal':ordinal,'name':name,'role':'STARTER' if ordinal==1 else 'BACKUP',
                              'source_uri':manifest['public_sources'][key]['url'],
                              'observed_at':manifest['public_sources'][key]['completed_at'],
                              'snapshot_id':lineage[key]['snapshot_id'],'evidence_type':'official_club_unofficial_depth_chart'}
                    depth_evidence[pid]=evidence
                    if position=='QB' and ordinal==1:
                        starters.append({'team':team,'player_master_id':pid,'source':'provisional_official_club_depth_chart',
                                         'source_uri':evidence['source_uri'],'observed_at':evidence['observed_at'],
                                         'evidence_tier':'inferred','note':'Expected starter on club unofficial depth chart; final game availability unverified'})
    injuries=pd.read_csv(lineage['nflreadpy_injuries']['path']).where(lambda f:f.notna(),None).to_dict('records')
    with engine.connect() as c:
        aliases={row['source_key']:dict(row) for row in c.execute(text("SELECT source_key,player_master_id,team,position FROM public.player_alias WHERE source_system='nflreadpy'")).mappings()}
    salary_by_id={r['player_master_id']:r for r in salaries if r['player_master_id']}
    injury_evidence={}
    for row in injuries:
        alias=aliases.get(row['gsis_id']);salary=salary_by_id.get(alias['player_master_id']) if alias else None
        if not salary:continue
        if salary['team']!=row['team'] or salary['position']!=row['position']:
            review.append({'source_native_id':row['gsis_id'],'team':row['team'],'position':row['position'],
                           'reason':'native_id_salary_team_position_conflict'});continue
        injury_evidence[salary['player_master_id']]={**row,'source':'nflreadpy_week4_injuries',
            'source_snapshot_id':lineage['nflreadpy_injuries']['snapshot_id'],
            'observed_at':lineage['nflreadpy_injuries']['observed_at']}
    players=[]
    for pid in sorted(set(depth_evidence)|set(injury_evidence)):
        salary=salary_by_id[pid];depth=depth_evidence.get(pid);injury=injury_evidence.get(pid,{})
        status=injury.get('report_status');status=None if pd.isna(status) else status
        if not depth and not status and not injury.get("practice_status"):continue
        players.append({'player_id':pid,'team':salary['team'],'position':salary['position'],
                        'role_label':depth['role'] if depth else None,'injury_status':status,
                        'evidence':{'depth':depth,'practice_report':injury,
                           'nfl_state':'EXPECTED_ROLE_PENDING_FINAL_GAME_STATUS',
                           'final_game_inactives_published':False,
                           'role_uncertain':bool(depth and depth['ordinal']>1),
                           'availability_basis':'No final-game availability probability inferred from roster/depth inclusion.'}})
    body={'season':2026,'week':4,'slate':'SUNDAY_MAIN','source':'official_club_sunday_preview_depth_roles',
          'source_uri':'https://www.nfl.com/injuries/','observed_at':datetime.now(UTC),
          'notes':'Explicit expectation labels from official club unofficial depth charts. No numerical role, availability, routes, targets or carries supplied. Final Sunday clearance pending.',
          'players':players}
    if args.resume_model:
        prior=base/('context_request_v2.json' if (base/'context_request_v2.json').exists() else 'context_request.json')
        body=json.loads(prior.read_text());body['observed_at']=datetime.fromisoformat(body['observed_at'])
    for filename,value in [('context_request_v2.json' if args.resume_prepared_context else 'context_request.json',body),('source_identity_review.json',review),
                           ('depth_evidence.json',depth_evidence),('injury_evidence.json',injury_evidence),('starter_request.json',starters)]:
        if (base/filename).exists():continue
        with (base/filename).open('x') as f:json.dump(_json_safe(value),f,sort_keys=True,indent=2)
    context=PregameContextService().create_run(body)
    starter_service=StartingQBService()
    eligible_qbs=starter_service._load_candidates(season=2026,week=4,slate='SUNDAY_MAIN')
    eligible_ids=set(eligible_qbs['player_id'].astype(str))
    excluded_starter_evidence=[row for row in starters if row['player_master_id'] not in eligible_ids]
    starter_result=starter_service.derive_starters(2026,4,'SUNDAY_MAIN',
        confirmed_starters=[row for row in starters if row['player_master_id'] in eligible_ids])
    print('context',context['context_run_id'],'players',len(players),'starters',starter_result.rows_written,flush=True)
    result={'context_run_id':str(context['context_run_id']),'context_players':len(players),
            'starter_rows':starter_result.rows_written,'starter_message':starter_result.message,
            'club_starters_ineligible_under_salary_policy':excluded_starter_evidence}
    with SessionLocal() as session:
        result['features']=LineupLearningService(session).rebuild_player_game_feature_matrix(
            source_system='draftkings',season_start=2026,season_end=2026,slate='SUNDAY_MAIN',weeks=[3,4],
            progress_hook=lambda value:print(value,flush=True))
    cutoff=datetime.now(UTC)
    prediction=PredictionsService().train_and_predict(2026,4,slate='SUNDAY_MAIN',data_cutoff_at=cutoff)
    result.update(projection_run_id=str(prediction.projection_run_id),projection_records=len(prediction.records),
                  data_cutoff_at=cutoff.isoformat(),finished_at=datetime.now(UTC).isoformat())
    with (base/'refresh_lineage.json').open('x') as f:json.dump(_json_safe(result),f,sort_keys=True,indent=2)
    print(result['projection_run_id'],result['projection_records'],flush=True)


if __name__=='__main__':main()
