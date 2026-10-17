from copy import deepcopy
import importlib.util
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pytest
from backend.app.product_services.team_game_outlook import (TeamGameModel,FEATURES,TARGETS,digest,feasible,validate_outlook,bind_outlook,allocate_budget,conditional_factors)
from backend.app.product_services.analyst_scenarios import build_scenarios
from backend.app.product_services.analyst_packets import validate
from scripts.run_merged_analyst_fixture import scenario_fixture
ROOT=Path(__file__).resolve().parents[4]
HERE=ROOT/'research/team_game_outlook_20261013'


def synthetic_outlook(packet):
    original=json.loads((HERE/'outlook_2026w6.json').read_text());block=deepcopy(original)
    block['games']=[];block['generated_at']='2099-09-01T11:00:00Z';block['source_available_at']='2099-09-01T10:00:00Z'
    for scope in packet['games']:
        game=deepcopy(original['games'][0]);game.update(game_id=scope['game_id'],season=2099,week=1,kickoff_at=scope['kickoff_at'])
        teams=scope['teams'];items=list(game['teams'].values());game['teams']={teams[i]:dict(items[i],opponent=teams[1-i]) for i in range(2)};block['games'].append(game)
    block['sha256']=digest({k:v for k,v in block.items() if k!='sha256'});return block


def test_feasible_budgets_and_observed_missing_labels():
    values=feasible([[20,60,100,.8,.7],[-3,-1,0,-.5,.9]])
    assert (values[:,3:5].sum(axis=1)<=1).all() and (values[:,2]<=values[:,1]).all()
    frame=pd.DataFrame([{**dict.fromkeys(FEATURES,1),**dict.fromkeys(TARGETS,1), 'game_id':'g','team':'DEN'}]);frame.loc[0,'points']=np.nan
    with pytest.raises(ValueError,match='missing target'):TeamGameModel().fit(frame)


def test_historical_matrix_uses_completed_earlier_weeks_only():
    frame=pd.read_csv(HERE/'feature_matrix.csv')
    with_history=frame.last_history_completed_at.notna()
    assert (pd.to_datetime(frame.loc[with_history,'last_history_completed_at'])<pd.to_datetime(frame.loc[with_history,'cutoff_at'])).all()
    assert not frame[['game_id','team']].duplicated().any()
    assert 'LAR' in set(frame.team) and 'LA' not in set(frame.team)
    # No current/same-week label appears in any feature name.
    assert set(FEATURES).isdisjoint(TARGETS) and all(c not in FEATURES for c in ['game_id','team','opponent'])
    spec=importlib.util.spec_from_file_location('team_game_run',HERE/'run.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    rebuilt,_,_=mod.prepare()
    assert np.allclose(frame[FEATURES].to_numpy(),rebuilt[FEATURES].to_numpy(),equal_nan=True)


@pytest.mark.parametrize('fmt',['CLASSIC','SHOWDOWN'])
def test_both_formats_receive_shared_context_without_mutating_truth(fmt):
    packet,snapshot=scenario_fixture(fmt);baseline=deepcopy(snapshot);packet['team_game_outlook']=synthetic_outlook(packet)
    assert not validate(packet)
    results=build_scenarios(packet,snapshot['players'],fmt=fmt,decision_at='2099-09-01T12:00:00Z')
    assert all(s['team_game_outlook']['sha256']==packet['team_game_outlook']['sha256'] for s in results)
    assert all(a['baseline_mutation'] is False for s in results for a in s['team_budget_allocation_audit'])
    assert snapshot==baseline
    legacy=deepcopy(packet);legacy.pop('team_game_outlook')
    old=build_scenarios(legacy,snapshot['players'],fmt=fmt,decision_at='2099-09-01T12:00:00Z')
    assert [s['moments'] for s in results]==[s['moments'] for s in old]


def test_hash_future_probability_and_game_scope_rejected():
    packet,_=scenario_fixture('CLASSIC');block=synthetic_outlook(packet)
    for mutation,match in [(lambda b:b.update(source_available_at='2100-01-01T00:00:00Z'),'future'),(lambda b:b['games'][0]['teams']['AAA'].update(win_probability=2),'probabilities'),(lambda b:b['games'][0].update(game_id='wrong'),'out-of-scope'),(lambda b:b['games'][0]['teams']['AAA']['central'].update(targets=1000),'budget')]:
        bad=deepcopy(block);mutation(bad);bad['sha256']=digest({k:v for k,v in bad.items() if k!='sha256'})
        assert any(match in e for e in validate_outlook(bad,games=packet['games'],decision_at='2099-09-01T12:00:00Z'))
    block['seed']=0;assert any('hash' in e for e in validate_outlook(block,games=packet['games'],decision_at='2099-09-01T12:00:00Z'))


def test_native_game_binding_and_conserved_partial_player_pool():
    block=json.loads((HERE/'outlook_2026w6.json').read_text());game=block['games'][0]
    scope=dict(game_id='scoped-id',season=game['season'],week=game['week'],teams=list(game['teams']),kickoff_at=game['kickoff_at'])
    bound=bind_outlook(block,[scope]);assert bound['games'][0]['source_native_game_id']==game['game_id']
    bad=dict(scope,week=7)
    with pytest.raises(ValueError,match='binding'):bind_outlook(block,[bad])
    packet,snapshot=scenario_fixture('SHOWDOWN');team=packet['games'][0]['teams'][0];members=[p for p in packet['players'] if p['team']==team and p['position'] in {'QB','RB','WR','TE'}]
    for p in members:
        for channel in ['targets','carries']:p['workload_evidence']['historical'][channel+'_mean_3']=dict(status='observed',available=True,value=0 if p==members[0] else 5)
    budget=dict(points=20,plays=60,drives=10,targets=30,carries=25)
    audit=allocate_budget(packet,snapshot['players'][1:],packet['games'][0]['game_id'],team,budget,decision_at='2099-09-01T12:00:00Z')
    for c in audit['channels'].values():assert sum(c['allocated'].values())+c['unallocated']==pytest.approx(c['budget'])
    members[-1]['workload_evidence']['historical']={}
    audit=allocate_budget(packet,snapshot['players'],packet['games'][0]['game_id'],team,budget,decision_at='2099-09-01T12:00:00Z')
    assert audit['channels']['targets']['status']=='unavailable_complete_role_shares' and audit['channels']['targets']['allocated']=={}


def test_same_joint_condition_used_for_own_and_opponent():
    packet,_=scenario_fixture('SHOWDOWN');packet['team_game_outlook']=synthetic_outlook(packet);game=packet['team_game_outlook']['games'][0]
    team,opp=game['teams'];budget=game['teams'][opp]['central'];branch=game['teams'][opp]['capability_branches']['competitive_scoring']
    branch['budget']=dict(budget,targets=budget['targets']*1.1,carries=budget['carries']*.9)
    own=game['teams'][team]['central'];branch['opponent_budget']=dict(own,targets=own['targets']*1.05,carries=own['carries']*.95)
    assert conditional_factors(packet,game['game_id'],team,'competitive_scoring',conditioned_on_team=opp)==pytest.approx((1.05,.95))
    assert conditional_factors(packet,game['game_id'],opp,'competitive_scoring',conditioned_on_team=opp)==pytest.approx((1.1,.9))


def test_exact_lag_window_and_repeatable_saved_model():
    import joblib
    frame=pd.read_csv(HERE/'feature_matrix.csv')
    for row in frame[frame.history_count>0].to_dict('records'):
        prior=frame[(frame.team==row['team'])&frame.points.notna()&((frame.season<row['season'])|((frame.season==row['season'])&(frame.week<row['week'])))].copy()
        prior=prior[pd.to_datetime(prior.kickoff_at)+pd.Timedelta(hours=8)<pd.Timestamp(row['cutoff_at'])].sort_values('kickoff_at').tail(5)
        assert row['own_points_mean5']==pytest.approx(prior.points.mean())
    model=joblib.load(HERE/'fitted_model.joblib');game=frame[(frame.season==2026)&(frame.week==6)].groupby('game_id').get_group('2026_06_SEA_DEN')
    first=model.game(game);assert first==model.game(game)
    for team in first['teams'].values():
        assert sum(team[k] for k in ['win_probability','loss_probability','tie_probability'])==pytest.approx(1)
        assert sum(b['probability'] for b in team['capability_branches'].values())==pytest.approx(1)
        assert team['central']['targets']+team['central']['carries']<=team['central']['plays']+1e-8


def test_final_real_consumers_have_matching_joint_budgets():
    audit=json.loads((HERE/'final_consumption_audit.json').read_text())
    assert not audit['classic']['packet_errors'] and not audit['showdown']['packet_errors']
    fitted=[s for s in audit['showdown']['scenarios'] if s.get('volume_response_source')=='fitted_conditional_budget_ratios']
    assert fitted and all(s['fitted_game_condition']['portfolio_weight_status'].startswith('uncalibrated') for s in fitted)
    for fmt in audit.values():
        for scenario in fmt['scenarios']:
            for team in scenario['team_budget_allocation_audit']:
                assert team['unassigned_play_budget']>=-1e-8
                for channel in team['channels'].values():assert sum(channel['allocated'].values())+channel['unallocated']==pytest.approx(channel['budget'])
