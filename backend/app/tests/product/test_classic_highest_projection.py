from copy import deepcopy
from unittest.mock import patch

import pandas as pd
import pytest
from sqlalchemy import create_engine

from backend.app.product_services.classic_highest_projection import normalize_request, solve, stack_policy
from backend.app.product_services.optimizer import OptimizerService


def pool_fixture():
    specs = [
        ('q1','QB','A','B',6000,24,25), ('q2','QB','C','D',6000,20,90),
        ('r1','RB','E','F',6000,20,21), ('r2','RB','G','H',6000,19,20),
        ('r3','RB','J','K',6000,14,70), ('w1','WR','L','M',5000,18,19),
        ('w2','WR','N','O',5000,17,18), ('w3','WR','P','Q',5000,16,17),
        ('w4','WR','R','S',5000,15,16), ('w5','WR','A','B',5000,1,95),
        ('t1','TE','T','U',3000,10,11), ('t2','TE','V','W',3000,9,80),
        ('d1','DST','X','Y',3000,5,6), ('d2','DST','Z','AA',3000,4,80),
    ]
    return pd.DataFrame([dict(player_id=pid,name=pid,position=pos,player_team=team,opponent_team=opp,
        salary=salary,projection=mean,p90=ceiling,ownership=90,optimizer_context_adjustment=100,
        game_id=f'{team}@{opp}') for pid,pos,team,opp,salary,mean,ceiling in specs])


def service():
    return OptimizerService.__new__(OptimizerService)


def test_exact_mean_ignores_ceiling_ownership_context_and_all_stack_layers():
    pool=pool_fixture();original=deepcopy(pool.to_dict('records'))
    lineups,report=solve(service(),pool,params=dict(enforce_single_te=True,max_players_per_team=4,max_players_per_game=5))
    assert report['solver_status']=='Optimal'
    assert report['locked_player_ids']==[] and report['generated_scenario_constraints'] is False
    ids={p['player_id'] for p in lineups[0]}
    assert ids=={'q1','r1','r2','w1','w2','w3','w4','t1','d1'}
    assert 'w5' not in ids  # It is q1's only teammate, with enormous ceiling.
    assert report['base_mean']==144
    assert report['hard_qb_stack'] is False and report['mandatory_opponent_bringback'] is False
    assert report['correlation_bonus']==report['ownership_weight']==report['ceiling_weight']==0
    assert pool.to_dict('records')==original
    coefficients=report['input_snapshot']['model']['objective']['coefficients']
    assert {c['name'] for c in coefficients}<=set(report['input_snapshot']['variable_players'])


def test_retains_game_team_dst_single_te_and_explicit_research_locks():
    pool=pool_fixture();pool.loc[pool.player_id=='w1',['player_team','opponent_team']]=['A','B'];pool.loc[pool.player_id=='w2',['player_team','opponent_team']]=['A','B']
    lineups,report=solve(service(),pool,params=dict(enforce_single_te=True,max_players_per_team=2,max_players_per_game=2),locked_ids={'q1'})
    lineup=lineups[0]
    assert sum(p['player_team']=='A' for p in lineup)<=2
    assert sum(p['position']=='TE' for p in lineup)==1
    assert report['locked_player_ids']==['q1']
    blocked=pool_fixture();blocked.loc[blocked.player_id=='d1',['player_team','opponent_team']]=['B','A']
    result,_=solve(service(),blocked,params=dict(avoid_dst_opponents=True,enforce_single_te=True))
    assert not {'q1','d1'}<={p['player_id'] for p in result[0]}


@pytest.mark.parametrize('changed',[{'locked_player_ids':['p']},{'locked_players':['p']},{'lock_player_ids':['p']},{'minimum_exposure_by_player':{'p':1}},{'long_shot_mode':True}])
def test_public_request_rejects_hidden_player_locks_or_alternate_scoring(changed):
    with pytest.raises(ValueError):normalize_request(dict(classic_selection_objective='baseline_mean',**changed),contest_format='classic',strategy='classic_large_gpp_v1')


def test_request_scope_and_annotations_are_isolated_and_other_settings_preserved():
    original=dict(classic_selection_objective='baseline_mean',analyst_strategy='MERGED_SCENARIOS',analyst_optimization_intent='EXPECTED_GAME',analyst_packet_sha256='a'*64,minimum_rb_salary=4500,exclude_opponent_teams=['DEN'],enforce_single_te=True,num_lineups=5)
    params=deepcopy(original)
    assert normalize_request(params,contest_format='classic',strategy='classic_large_gpp_v1')
    assert params['analyst_handoff_mode']=='BASELINE' and params['analyst_optimization_intent']=='MIXED'
    assert 'analyst_strategy' not in params and 'analyst_packet_sha256' not in params
    assert params['num_lineups']==1 and params['minimum_rb_salary']==4500 and params['exclude_opponent_teams']==['DEN']
    assert original['num_lineups']==5
    with pytest.raises(ValueError,match='Classic Large GPP'):normalize_request(deepcopy(original),contest_format='showdown',strategy='showdown_gpp_portfolio_v3')
    ordinary={'num_lineups':5,'analyst_strategy':'MERGED_SCENARIOS'}
    assert not normalize_request(ordinary,contest_format='classic',strategy='classic_large_gpp_v1')
    assert ordinary=={'num_lineups':5,'analyst_strategy':'MERGED_SCENARIOS'}
    assert stack_policy()['enabled'] is False


def test_preliminary_mode_saves_exact_objective_and_keeps_not_entry_cleared(tmp_path):
    from backend.app.tests.product.test_preliminary_optimizer import snapshot_fixture,request_fixture
    from backend.app.product_services.preliminary_optimizer import save_snapshot,run_preliminary
    source,_=snapshot_fixture();snapshot=save_snapshot(source,directory=tmp_path)
    request=request_fixture(snapshot);request.optimizer.params.update(classic_selection_objective='baseline_mean')
    svc=OptimizerService();svc.engine=create_engine('sqlite://');saved=[]
    with patch.object(OptimizerService,'_persist_optimizer_run',side_effect=lambda job:saved.append(deepcopy(job)) or True):
        job=run_preliminary(request,run_id='highest-projection-test',service=svc,directory=tmp_path)
    assert job.status=='completed',job.message
    assert len(job.results)==1 and job.params['stack_policy']['enabled'] is False
    assert job.params['objective_config']['objective_id']=='baseline_mean'
    assert job.params['strategy_runtime']['highest_projection']['solver_status']=='Optimal'
    assert job.params['strategy_runtime']['highest_projection']['locked_player_ids']==[]
    assert 'football_analyst' not in job.params['strategy_runtime']
    assert job.params.get('gpp_recommendation') is None
    assert job.params['entry_readiness']['entry_ready'] is False
    assert saved[-1].params['strategy_runtime']['highest_projection']['input_snapshot']['model']
    assert all(p['entry_ready'] is False for p in job.results[0])
