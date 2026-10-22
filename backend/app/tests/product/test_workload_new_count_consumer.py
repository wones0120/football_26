"""New team budgets reach the existing frozen workload objective, independent of FP."""
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
from uuid import UUID

import pandas as pd
import pytest
from sqlalchemy import create_engine

from backend.app.product_services import workload_count_forecast as counts
from backend.app.product_services.optimizer import OptimizerService
from backend.app.product_services.workload_optimizer import solve

NOW=datetime(2026,10,19,21,tzinfo=UTC)


def fixture():
    weekly=[];pool=[]
    for team_index,team in enumerate(('SF','WAS')):
        for index,(position,passes,rush,targets) in enumerate((('QB',30,3,0),('RB',0,17,5),('WR',0,0,12),('TE',0,0,8))):
            pid=str(UUID(int=team_index*4+index+1))
            for week in range(1,6):
                weekly.append(dict(player_master_id=pid,source_player_id='native'+pid,team=team,position=position,
                    period=202600+week,source_id=week*10+team_index*4+index,imported_at='2026-10-19T19:00:00Z',
                    pass_attempts=passes,rush_attempts=rush,targets=targets,passing_yards=passes*8,
                    passing_interceptions=passes/30,completions=passes*.6,rushing_yards=rush*4,
                    receptions=targets*.6,receiving_yards=targets*8))
            pool.append(dict(player_id=pid,name=team+position,player_team=team,opponent_team='WAS' if team=='SF' else 'SF',
                position=position,salary=5000,projection=1 if team=='SF' else 100,p90=999,
                is_starting_qb=position=='QB',starting_qb_source='source' if position=='QB' else None,
                canonical_role='expected_starter',role_availability='active',role_optimizer_eligible=True,
                role_starter_evidence=dict(player_id=pid,team=team,position=position,role='expected_starter',
                    source_ids=[1],source_uri='https://example.test/depth',observed_at='2026-10-19T20:00:00Z',received_at='2026-10-19T20:00:01Z'),
                showdown_captain_shortlisted=True,showdown_captain_p90=999,showdown_flex_mean=100))
    return pd.DataFrame(weekly),pool


def prepared(monkeypatch):
    weekly,pool=fixture()
    monkeypatch.setattr(counts,'load_history',lambda *a,**k:weekly.copy())
    monkeypatch.setattr(counts,'fit_team_model',lambda *a,**k:dict(training_max_period=202501,center=[0]*4,scale=[1]*4,
        coefficients=[[0]*4,[0]*4],intercept=[30,20]))
    from backend.app.product_services import workload_gamebook_participation as gaps
    monkeypatch.setattr(gaps,'load_verified_gaps',lambda *a,**k:[])
    from backend.app.product_services import team_opportunity_serving as serving
    monkeypatch.setattr(serving,'predict_registered_teams',lambda *a,**k:dict(status='forecast_complete',
        version='SYNTHETIC_REGISTERED_PAIR',inference_matrix_sha256='a'*64,source_measurements_sha256='b'*64,
        predictions=[dict(team='SF',counts=dict(pass_attempts=50.,rush_attempts=20.)),
                     dict(team='WAS',counts=dict(pass_attempts=10.,rush_attempts=20.))]))
    receipt=counts.prepare_receipt(create_engine('sqlite://'),pool,season=2026,week=6,cutoff=NOW,
        projection_run_id='frozen-projection',opportunity_source_context=dict(status='available_descriptive'),
        games=[dict(game_id='2026_06_WAS_SF')],markets=[])
    return pool,receipt


def run(pool,receipt):
    return solve(OptimizerService.__new__(OptimizerService),pd.DataFrame(pool),params=dict(
        workload_comparison='normalized_counts',num_lineups=1,max_exposure=1,captain_max_exposure=1,
        prepared_input_evidence=dict(workload_forecast=receipt)),contest_type='captain',
        stack_params=dict(captain_positions=['RB','WR','TE'],max_players_per_team=4),
        locked_ids=set(),flex_only_ids=set(),avoid_dst_opponents=True,enforce_single_te=False,requested_captain_id=None)


def signature(lineups):return {(p['player_id'],p['roster_position']) for p in lineups[0]}


def test_prepare_new_counts_recompute_utility_then_actual_workload_solver_consumes_frozen_receipt(monkeypatch):
    pool,receipt=prepared(monkeypatch)
    new={p['player_master_id']:p for p in receipt['players']}
    old={p['player_master_id']:p for p in receipt['reference_count_forecast']['players']}
    for row in receipt['players']:
        assert row['utility']==pytest.approx(counts.utility(row,receipt['scales']))
        assert row['counts']['targets']!=old[row['player_master_id']]['counts']['targets'] or row['position']=='QB'
    assert receipt['teams']['SF']['pass_attempts']==50
    assert receipt['teams']['WAS']['pass_attempts']==10
    assert receipt['team_budget_model_contract']['inference_matrix_sha256']=='a'*64
    assert any(new[pid]['utility']!=counts.utility(old[pid],receipt['scales']) for pid in new)
    lineups,report=run(pool,receipt)
    assert report['status']=='completed' and report['forecast_sha256']==receipt['sha256']
    assert next(p for p in lineups[0] if p['roster_position']=='CPT')['player_team']=='SF'
    for actor in lineups[0]:
        assert actor['workload_forecast']==new[actor['player_id']]
        assert actor['workload_forecast_sha256']==receipt['sha256']
    changed=deepcopy(pool)
    for row in changed:
        row['projection']*=-1000;row['p90']=-999;row['showdown_captain_p90']=-999;row['showdown_flex_mean']=-999
    assert signature(run(changed,receipt)[0])==signature(lineups)
    # Return to the legacy utilities under an independently valid receipt: the
    # actual solver's Captain choice changes, proving new utility consumption.
    legacy=deepcopy(receipt)
    for actor in legacy['players']:actor['utility']=counts.utility(old[actor['player_master_id']],receipt['scales'])
    legacy['sha256']=hashlib.sha256(json.dumps({k:v for k,v in legacy.items() if k!='sha256'},sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    assert signature(run(pool,legacy)[0])!=signature(lineups)


def test_changed_new_count_payload_cannot_reuse_prepared_receipt_binding(monkeypatch):
    pool,receipt=prepared(monkeypatch)
    receipt['players'][0]['counts']['pass_attempts']+=1
    with pytest.raises(ValueError,match='checksum'):run(pool,receipt)


def test_learned_mode_has_no_point_qualification_objective_or_tie_break(monkeypatch):
    from backend.app.product_services.showdown_captain_shortlist import build_captain_shortlist
    from backend.app.product_services.evaluation_record import digest
    pool,receipt=prepared(monkeypatch)
    receipt.update(learned_opportunities=True,learned_model_consumption=dict(
        team=dict(model_publication_record_id='synthetic-team'),
        player=dict(model_publication_record_id='synthetic-player'),points_heads_consumed=False))
    receipt['sha256']=digest({k:v for k,v in receipt.items() if k!='sha256'})
    params=dict(workload_comparison='learned_counts',num_lineups=1,max_exposure=1,captain_max_exposure=1,
        captain_positions=['RB','WR','TE'],prepared_input_evidence=dict(workload_forecast=receipt))
    def issue(rows):
        frame=pd.DataFrame(rows).drop(columns=['showdown_captain_shortlisted','showdown_captain_p90','showdown_flex_mean'])
        frame,qualification=build_captain_shortlist(frame,params=params,flex_only_ids=set())
        assert qualification['ranking'].startswith('canonical_player_id_asc')
        assert len(qualification['shortlist'])==6
        return solve(OptimizerService.__new__(OptimizerService),frame,params=params,contest_type='captain',
            stack_params=dict(captain_positions=['RB','WR','TE'],max_players_per_team=4),locked_ids=set(),
            flex_only_ids=set(),avoid_dst_opponents=True,enforce_single_te=False,requested_captain_id=None)
    lineups,report=issue(pool)
    assert report['points_selection_gates_consumed'] is False
    assert report['solver_audits'][0]['solver_status']=='Optimal'
    snapshot=report['solver_audits'][0]['input_snapshot']
    from backend.app.product_services.optimizer import _json_safe
    persisted=json.loads(json.dumps(_json_safe(report)))
    assert persisted['solver_audits'][0]['input_sha256']==digest(persisted['solver_audits'][0]['input_snapshot'])
    assert all(str(c.get('pi')) != '-0.0' for c in snapshot['model']['constraints'])
    assert all('projection' not in row and 'p90' not in row for row in snapshot['players'])
    changed=deepcopy(pool)
    for row in changed:row.update(projection=-999999.,p90=float('nan'))
    alternative,again=issue(changed)
    assert signature(alternative)==signature(lineups)
    assert again['solver_audits'][0]['objective']==report['solver_audits'][0]['objective']
    from backend.app.product_services.workload_optimizer import learned_recommendation
    from backend.app.product_services.draftkings_export import DraftKingsExportService
    monkeypatch.setattr(DraftKingsExportService,'build_lineup_download',lambda **kwargs: None)
    for row in alternative[0]:row['projection']=None;row['p90']=None
    recommendation=learned_recommendation(alternative,run_id='test',season=2026,week=6,
        slate='TEST',contest_format='showdown',projection_run_id='frozen',data_cutoff_at=NOW)
    assert recommendation['status']=='provisional' and recommendation['recommended']['lineup_number']==1
    assert recommendation['recommended']['projected_points'] is None
    params['require_team_leader']=True
    with pytest.raises(ValueError,match='points-based team leader'):issue(pool)


def test_learned_mode_refuses_reference_forecast_fallback(monkeypatch):
    pool,receipt=prepared(monkeypatch)
    with pytest.raises(ValueError,match='latest learned'):
        solve(OptimizerService.__new__(OptimizerService),pd.DataFrame(pool),params=dict(
            workload_comparison='learned_counts',prepared_input_evidence=dict(workload_forecast=receipt)),
            contest_type='captain',stack_params={},locked_ids=set(),flex_only_ids=set(),
            avoid_dst_opponents=True,enforce_single_te=False,requested_captain_id=None)
