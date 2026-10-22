from copy import deepcopy
import importlib.util
from pathlib import Path
import numpy as np
import pytest
from backend.app.product_services import joint_rush_conditional_means as rush,joint_target_pass_conditional_means as target
from backend.app.product_services.scheduled_workload_efficiency_model_inputs import TEAM_ADDED,PLAYER_ADDED

spec=importlib.util.spec_from_file_location('eval2026inputs',Path(__file__).with_name('inputs.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def fixture(channel='rush'):
    columns=[*TEAM_ADDED,*PLAYER_ADDED,'is_known_outside_rest','prior_candidate_count']+(['is_source_pass_minus_target_remainder']if channel=='target'else[])
    prep=dict(columns=columns,medians=[0.]*len(columns),centers=[0.]*len(columns),scales=[1.]*len(columns),entirely_missing_train_columns=[columns[0]])
    gp=dict(columns=list(TEAM_ADDED),medians=[0.]*38,centers=[0.]*38,scales=[1.]*38,entirely_missing_train_columns=[TEAM_ADDED[0]])
    f=dict.fromkeys(columns,0.);f[columns[0]]=99.
    cells=[dict(kind='candidate',source_player_id='00-0000001',player_master_id='p',label=2,features=dict(f)),dict(kind='outside_rest'if channel=='rush'else'outside_target_rest',source_player_id=None,player_master_id=None,label=1,features=dict(f))]
    g=dict(game_id='2026_04_A_B',team='A',period=202604,cells=cells,budget_label=3)
    if channel=='target':
        g.update(target_budget_label=3,pass_budget_label=4);cells.append(dict(kind='source_pass_minus_target_remainder',source_player_id=None,player_master_id=None,label=1,features=dict(f)))
    return g,prep,gp

@pytest.mark.parametrize('channel',['rush','target'])
def test_identical_numerical_transform_and_frozen_unknown(channel):
    g,p,gp=fixture(channel);before=deepcopy(g);actual=m.transform_evaluation([g],p,gp,channel=channel)
    # Synthetic algebra comparison only: historical transform rejects actual2026.
    historical=deepcopy(g);historical['period']=202504
    reference=(rush if channel=='rush'else target).transform_groups([historical],p)
    assert np.array_equal(actual['X'],reference['X'])and actual['X'][0,0]==0 and actual['X'][0,len(p['columns'])]==1
    assert g==before and actual['G'].shape==(1,76)

@pytest.mark.parametrize('field,value',[('period',202603),('period',202606),('period',202504)])
def test_unsupported_period_fails(field,value):
    g,p,gp=fixture();g[field]=value
    with pytest.raises(ValueError):m.transform_evaluation([g],p,gp,channel='rush')

def test_unknown_label_and_broken_budget_fail():
    for label in(None,4):
        g,p,gp=fixture();g['cells'][0]['label']=label
        with pytest.raises(ValueError):m.transform_evaluation([g],p,gp,channel='rush')

def test_same_group_context_required():
    g,p,gp=fixture();g['cells'][1]['features'][TEAM_ADDED[1]]=1
    with pytest.raises(ValueError):m.transform_evaluation([g],p,gp,channel='rush')

def test_only_prior_rows_and_roles_feed_predictors():
    ids=[f'2026_0{i}_A_B'for i in(1,2,3)];proof=dict(team='A',week=4,prior_games=ids,channels={'rush_attempts':{'candidate_count':1}})
    context=dict(period=202604,features=dict.fromkeys(TEAM_ADDED,None),windows={k:dict(game_ids=ids,periods=[202601,202602,202603])for k in('own','opponent')})
    fields=['attempts','completions','passing_yards','interceptions','passing_tds','carries','rushing_yards','targets','receptions','receiving_yards']
    actor=dict(values=dict.fromkeys(fields,0),counts=dict.fromkeys(m.CHANNEL_FIELDS,0),source_position='RB',source_QB_proven=False)
    actors={(gid,'A','n'):deepcopy(actor)for gid in ids};teams={(gid,'A'):dict(values=dict.fromkeys(fields,1))for gid in ids}
    before=m.prior_features(proof,'n',context,actors,teams,channel='rush')
    actors['2026_04_A_B','A','n']=dict(actor,source_position='QB',counts=dict.fromkeys(m.CHANNEL_FIELDS,999))
    assert m.prior_features(proof,'n',context,actors,teams,channel='rush')==before
    del actors[ids[0],'A','n']
    after=m.prior_features(proof,'n',context,actors,teams,channel='rush')
    assert after['scheduled3_rush_attempts_mean']is None and after['scheduled3_unknown_actor_rows']==1
