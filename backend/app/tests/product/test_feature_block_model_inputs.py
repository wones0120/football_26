from copy import deepcopy
from unittest.mock import patch
import numpy as np
import pytest
from backend.app.product_services.offensive_volume_features import FEATURES, VERSION as MATRIX_VERSION,digest
from backend.app.product_services.feature_block_model_inputs import (prepare_player_inputs,fit_player_family,
    predict_player_families,apply_player_count_predictions,transform)
from backend.app.product_services.opportunity_history_evidence import CHANNELS

PID='11111111-1111-4111-8111-111111111111'
OTHER='22222222-2222-4222-8222-222222222222'


def matrix():
    rows=[]
    for season in [2023,2024,2025]:
        for week in range(1,5):
            values=dict.fromkeys(FEATURES,0.)
            values.update(rush_attempts_mean3=float(week),pass_attempts_known3=3.,rush_attempts_known3=3.,targets_known3=3.)
            rows.append(dict(player_master_id=PID,game_id=f'{season}_{week:02d}_WAS_SF',team='SF',position='RB',period=season*100+week,
                features=values,labels=dict(pass_attempts=0.,rush_attempts=float(week),targets=0. if week%2 else None),
                history_periods=[(season-1)*100+18],context_periods=[],current_inference=False))
    value=dict(version=MATRIX_VERSION,before_period=202506,feature_columns=list(FEATURES),target_columns=list(CHANNELS),rows=rows,
        usage='offline_retrospective_model_inputs')
    value['matrix_sha256']=digest(value);value['provenance']={'source':'fixture-revised'}
    return value


def prepared():return prepare_player_inputs(matrix(),train_before=202401,validation_before=202501)


class Estimator:
    def __init__(self,**kwargs):pass
    def fit(self,x,y):self.mean=float(np.mean(y));return self
    def predict(self,x):return self.mean+np.asarray(x)[:,list(FEATURES).index('rush_attempts_mean3')]*.05


def pair():
    p=prepared()
    with patch('backend.app.product_services.feature_block_model_inputs.HistGradientBoostingRegressor',Estimator), \
         patch('backend.app.product_services.feature_block_model_inputs.MLPRegressor',Estimator):
        return p,fit_player_family(p,family='tree',minimum_target_rows=2),fit_player_family(p,family='neural',minimum_target_rows=2)


def test_shared_chronological_cohort_retains_zero_omits_only_missing_head_label():
    p,t,n=pair()
    assert len(p['splits']['train']['keys'])==4
    assert t['receipt']['training_rows_by_target']==dict(pass_attempts=4,rush_attempts=4,targets=2)
    assert t['receipt']['prepared_sha256']==n['receipt']['prepared_sha256']
    assert max(k['period'] for k in t['receipt']['training_keys_by_target']['targets'])<202401
    assert t['receipt']['metrics']['validation']['pass_attempts']['rows']==4


def test_preprocessing_train_only_and_unknown_mask_not_source_zero():
    m=matrix();p=prepare_player_inputs(m,train_before=202401,validation_before=202501)
    m['rows'][-1]['features']['rush_attempts_mean3']=999999.
    m['matrix_sha256']=digest({k:v for k,v in m.items() if k not in {'matrix_sha256','provenance'}})
    changed=prepare_player_inputs(m,train_before=202401,validation_before=202501)
    assert p['preprocessing']==changed['preprocessing']
    r=deepcopy(m['rows'][0]);r['features']['rush_attempts_mean3']=None
    x=transform([r],p['preprocessing']);idx=list(FEATURES).index('rush_attempts_mean3')
    assert x[0,len(FEATURES)+idx]==1


def test_both_family_contracts_consume_same_new_feature_and_change_prediction():
    p,t,n=pair();r=deepcopy(matrix()['rows'][-1]);r.update(period=202506,current_inference=True)
    old=predict_player_families(t,n,[r],before_period=202506)
    r['features']['rush_attempts_mean3']+=1
    new=predict_player_families(t,n,[r],before_period=202506)
    for family in ['tree','neural']:
        assert old[0]['components'][family]['rush_attempts']!=new[0]['components'][family]['rush_attempts']
    assert old[0]['inference_features_sha256']!=new[0]['inference_features_sha256']
    assert all(v>=0 for v in new[0]['counts'].values())


@pytest.mark.parametrize('kind',['leak','hash','label','feature_order','fp_column'])
def test_invalid_matrix_rejected(kind):
    m=matrix()
    if kind=='leak':m['rows'][0]['history_periods']=[m['rows'][0]['period']]
    if kind=='label':m['rows'][0]['labels']['targets']=-1.
    if kind=='feature_order':m['rows'][0]['features'].pop('rush_attempts_mean3')
    if kind=='fp_column':m['feature_columns'].append('FP');[r['features'].update(FP=20.) for r in m['rows']]
    if kind!='hash':m['matrix_sha256']=digest({k:v for k,v in m.items() if k not in {'matrix_sha256','provenance'}})
    else:m['rows'][0]['labels']['targets']=25.
    with pytest.raises(ValueError):prepare_player_inputs(m,train_before=202401,validation_before=202501)


def count_receipt():
    return dict(before_period=202506,teams={'SF':dict(pass_attempts=30.,rush_attempts=20.,targets=25.)},players=[
        dict(player_master_id=PID,team='SF',position='RB',counts=dict(pass_attempts=None,rush_attempts=5.,targets=4.)),
        dict(player_master_id=OTHER,team='SF',position='WR',counts=dict(pass_attempts=None,rush_attempts=None,targets=None))])


def test_real_count_consumer_preserves_unknown_residual_and_signed_no_preference_inputs():
    original=count_receipt();prediction=dict(player_master_id=PID,team='SF',period=202506,counts=dict(pass_attempts=15.,rush_attempts=50.,targets=40.))
    r=apply_player_count_predictions(original,[prediction]);actor=r['players'][0]
    assert actor['counts']['pass_attempts'] is None
    assert actor['counts']['rush_attempts']==5. and actor['counts']['targets']==4.
    assert r['players'][1]['counts']['targets'] is None
    assert r['teams']['SF']['reconciliation']['rush_attempts']['unallocated']==15.
    assert original['players'][0]['counts']['rush_attempts']==5.
    assert r['player_model_consumption']['actors']==1


def test_inactive_no_positive_count_and_no_unknown_actor_insertion():
    r=count_receipt();r['players'][0]['world_activity']=False
    p=dict(player_master_id=PID,team='SF',period=202506,counts=dict.fromkeys(CHANNELS,4.))
    out=apply_player_count_predictions(r,[p]);assert all(v==0 for v in out['players'][0]['counts'].values())
    p['player_master_id']='33333333-3333-4333-8333-333333333333'
    with pytest.raises(ValueError,match='outside'):apply_player_count_predictions(r,[p])


@pytest.mark.parametrize('kind',['negative','team','period','target_budget'])
def test_physical_count_consumer_guards(kind):
    r=count_receipt();p=dict(player_master_id=PID,team='SF',period=202506,counts=dict.fromkeys(CHANNELS,4.))
    if kind=='negative':p['counts']['targets']=-1.
    if kind=='team':p['team']='WAS'
    if kind=='period':p['period']=202507
    if kind=='target_budget':r['teams']['SF']['targets']=31.
    with pytest.raises(ValueError):apply_player_count_predictions(r,[p])


def test_canonical_json_object_order_is_not_feature_column_order():
    import json
    m=matrix();p=prepare_player_inputs(m,train_before=202401,validation_before=202501)
    restored=json.loads(json.dumps(m,sort_keys=True))
    q=prepare_player_inputs(restored,train_before=202401,validation_before=202501)
    assert p['preprocessing']==q['preprocessing']
    assert p['splits']==q['splits']
    assert p['prepared_sha256']==q['prepared_sha256']


def test_entirely_missing_training_field_cannot_gain_unlearned_inference_response():
    m=matrix();field='event_air_yards_mean8'
    for r in m['rows']:
        r['features'][field]=None if r['period']<202401 else 55.
    m['matrix_sha256']=digest({k:v for k,v in m.items() if k not in {'matrix_sha256','provenance'}})
    p=prepare_player_inputs(m,train_before=202401,validation_before=202501)
    assert field in p['preprocessing']['entirely_missing_train_columns']
    r=deepcopy(m['rows'][-1]);x=transform([r],p['preprocessing'])
    r['features'][field]=-10000.;assert np.array_equal(x,transform([r],p['preprocessing']))
    idx=list(FEATURES).index(field)
    assert x[0,idx]==0 and x[0,len(FEATURES)+idx]==1


def test_2025_retrospective_test_separated_from_inspected_2026_diagnostic():
    m=matrix();r=deepcopy(m['rows'][-1]);r.update(period=202601,game_id='2026_01_WAS_SF',history_periods=[202518])
    m['rows'].append(r);m['before_period']=202606
    m['matrix_sha256']=digest({k:v for k,v in m.items() if k not in {'matrix_sha256','provenance'}})
    p=prepare_player_inputs(m,train_before=202401,validation_before=202501)
    assert all(k['period']//100==2025 for k in p['splits']['retrospective_test']['keys'])
    assert [k['period'] for k in p['splits']['inspected_later_diagnostic']['keys']]==[202601]


class RestartEstimator:
    def __init__(self):
        self.coefs_=[np.array([[7.]])];self.loss_=1.;self.n_iter_=500;self.max_iter=500;self.solver='lbfgs'
    def set_params(self,**params):
        self.__dict__.update(params);return self
    def get_params(self):return dict(max_iter=self.max_iter,solver=self.solver,warm_start=self.warm_start)
    def fit(self,x,y):
        assert self.coefs_[0][0,0]==7. and self.warm_start is True
        self.coefs_[0][0,0]=9.;self.loss_=.5;self.n_iter_=20;return self
    def predict(self,x):return np.zeros(len(x))


def test_explicit_neural_repair_preserves_supplied_weights_and_original():
    from backend.app.product_services.feature_block_model_inputs import repair_neural_convergence
    p,t,n=pair();n['receipt']['status']='fit_not_converged';n['estimators']={k:RestartEstimator() for k in CHANNELS}
    repaired=repair_neural_convergence(n,p)
    assert repaired['receipt']['status']=='fit_complete'
    assert all(m.coefs_[0][0,0]==7. and m.max_iter==500 for m in n['estimators'].values())
    assert all(m.coefs_[0][0,0]==9. and m.max_iter==1500 for m in repaired['estimators'].values())
    with pytest.raises(ValueError,match='repeated'):repair_neural_convergence(repaired,p)
    changed=deepcopy(p);changed['training_max_period']+=1
    changed['prepared_sha256']=digest({k:v for k,v in changed.items() if k not in {'prepared_sha256','provenance'}})
    with pytest.raises(ValueError,match='differs'):repair_neural_convergence(n,changed)
    n['receipt']['training_keys_by_target']['targets']=[]
    with pytest.raises(ValueError,match='cohort'):repair_neural_convergence(n,p)


def test_explicit_adam_repair_recipe_uses_same_frozen_inputs_and_strict_warning_gate():
    from sklearn.exceptions import ConvergenceWarning
    import warnings
    observed=[]
    class Adam(Estimator):
        def __init__(self,**kwargs):observed.append(kwargs)
        def fit(self,x,y):warnings.warn('limit',ConvergenceWarning);return super().fit(x,y)
    p=prepared();old=deepcopy(p)
    with patch('backend.app.product_services.feature_block_model_inputs.MLPRegressor',Adam):
        n=fit_player_family(p,family='neural',minimum_target_rows=2,neural_recipe='adam_optimizer_repair_v1')
    assert p==old and n['receipt']['status']=='fit_not_converged'
    assert n['receipt']['neural_recipe_id']=='adam_optimizer_repair_v1'
    assert len(observed)==3 and all(k['solver']=='adam' and k['max_iter']==500 and k['n_iter_no_change']==20 and not k['early_stopping'] for k in observed)
    assert n['receipt']['training_keys_by_target']['targets']==[p['splits']['train']['keys'][i] for i,r in enumerate(p['splits']['train']['labels']) if r['targets'] is not None]
    with pytest.raises(ValueError):fit_player_family(p,family='tree',neural_recipe='adam_optimizer_repair_v1')


class RawRushEstimator:
    def predict(self,x):return np.full(len(x),2.)


def scoped_pair():
    from backend.app.product_services.feature_block_model_inputs import RB_RUSH_MEAN_VERSION
    p,t,n=pair()
    head=dict(position='RB',channel='rush_attempts',transform='standardized_raw_count_mse_v1',target_scaler=dict(center=4.,scale=3.))
    for b in (t,n):
        b['receipt']['version']=RB_RUSH_MEAN_VERSION;b['receipt']['rb_rush_mean_head']=deepcopy(head)
        b['estimators']['rb_rush_attempts']=RawRushEstimator()
    return p,t,n


def test_scoped_raw_rush_head_changes_only_rb_rush_and_preserves_other_families():
    _,old_t,old_n=pair();_,t,n=scoped_pair();rows=[]
    for i,pos in enumerate(['RB','QB','WR','TE']):
        r=deepcopy(matrix()['rows'][-1]);r.update(player_master_id=str(i),position=pos,period=202506,current_inference=True);rows.append(r)
    old=predict_player_families(old_t,old_n,rows,before_period=202506);new=predict_player_families(t,n,rows,before_period=202506)
    assert new[0]['counts']['rush_attempts']==10.
    assert 'raw-count' in new[0]['estimand']
    for i in range(4):
        for channel in ['pass_attempts','targets']:assert new[i]['counts'][channel]==old[i]['counts'][channel]
        if i:assert new[i]['counts']['rush_attempts']==old[i]['counts']['rush_attempts']
    assert new[0]['counts']['rush_attempts']!=old[0]['counts']['rush_attempts']


def test_scoped_head_requires_positions_valid_scaler_and_matching_contract():
    from backend.app.product_services.feature_block_model_inputs import _predict
    p,t,n=scoped_pair();x=np.asarray(p['splits']['train']['x'])
    with pytest.raises(ValueError,match='positions'):_predict(t,x)
    t['receipt']['rb_rush_mean_head']['target_scaler']['scale']=0
    with pytest.raises(ValueError,match='scaler'):_predict(t,x,positions=['RB']*len(x))
    with pytest.raises(ValueError,match='RB rush contracts'):predict_player_families(t,n,[],before_period=202506)


def sparse_pair():
    from backend.app.product_services.feature_block_model_inputs import SPARSE_WR_VERSION
    p,t,n=scoped_pair()
    head=dict(position='WR',prior_games=2,transform='standardized_raw_count_mse_v1',heads={
        c:dict(target_scaler=dict(center=4.,scale=3.),training_rows=100,training_max_period=202318)
        for c in ('targets','rush_attempts')})
    for b in (t,n):
        b['receipt'].update(version=SPARSE_WR_VERSION,sparse_wr_count_heads=deepcopy(head))
        b['estimators'].update({'sparse_wr_'+c:RawRushEstimator() for c in head['heads']})
    return p,t,n


def test_sparse_wr_consumer_is_exact_cohort_only_and_leaves_other_predictions_identical():
    _,old_t,old_n=scoped_pair();_,t,n=sparse_pair();rows=[]
    for i,(pos,games) in enumerate([('WR',2),('WR',3),('RB',2),('QB',2),('WR',1)]):
        r=deepcopy(matrix()['rows'][-1]);r.update(player_master_id=str(i),position=pos,period=202506,current_inference=True)
        for c in CHANNELS:r['features'][c+'_known3']=float(games)
        rows.append(r)
    old=predict_player_families(old_t,old_n,rows,before_period=202506)
    new=predict_player_families(t,n,rows,before_period=202506)
    assert new[0]['counts']['targets']==new[0]['counts']['rush_attempts']==10.
    assert new[0]['history_supported'] and not old[0]['history_supported']
    assert 'Sparse WR' in new[0]['estimand']
    assert new[0]['counts']['pass_attempts']==old[0]['counts']['pass_attempts']
    assert all(new[i]['counts']==old[i]['counts'] for i in range(1,len(rows)))
    n['receipt']['sparse_wr_count_heads']['prior_games']=1
    with pytest.raises(ValueError,match='sparse WR contracts'):predict_player_families(t,n,[],before_period=202506)


def test_unsupported_sparse_history_cannot_turn_reference_counts_into_served_model_counts():
    receipt=count_receipt();p=dict(player_master_id=PID,team='SF',period=202506,counts=dict.fromkeys(CHANNELS,4.),history_supported=False)
    out=apply_player_count_predictions(receipt,[p])
    assert all(v is None for v in out['players'][0]['counts'].values())
    assert out['players'][0]['player_model_components']['counts']['targets']==4.
    assert 'sparse' in out['players'][0]['reasons'][-1]
    assert out['teams']['SF']['reconciliation']['targets']['unallocated']==25.


@pytest.mark.parametrize('history_supported',[False,True])
def test_sparse_history_cannot_erase_factual_nonparticipation(history_supported):
    original=count_receipt()
    actor=original['players'][0]
    actor.update(world_activity=False,world_activity_reason='Scoped reserve or no-elevation condition',
        counts=dict.fromkeys(CHANNELS,0.),hypothetical_active_role_reference_counts=dict.fromkeys(CHANNELS,None))
    p=dict(player_master_id=PID,team='SF',period=202506,history_supported=history_supported,
        counts=dict.fromkeys(CHANNELS,7.))
    out=apply_player_count_predictions(original,[p]);changed=out['players'][0]
    assert changed['counts']==dict.fromkeys(CHANNELS,0.)
    assert changed['player_model_application']=='not_applied_factual_nonparticipation'
    assert changed['player_model_components']['history_supported']==history_supported
    assert changed['hypothetical_active_role_reference_counts']==dict.fromkeys(CHANNELS,None)
    assert out['players'][1]['counts']==dict.fromkeys(CHANNELS,None)
    assert original['players'][0].get('player_model_application') is None
    assert out['teams']['SF']['reconciliation']['targets']['unallocated']==25.


def test_sparse_active_and_questionable_players_stay_unknown_without_factual_condition():
    original=count_receipt();original['players'][0].update(native_status='Q',world_activity=None)
    p=dict(player_master_id=PID,team='SF',period=202506,history_supported=False,counts=dict.fromkeys(CHANNELS,7.))
    out=apply_player_count_predictions(original,[p])
    assert out['players'][0]['counts']==dict.fromkeys(CHANNELS,None)
    assert out['players'][0]['native_status']=='Q'
    assert out['players'][0].get('player_model_application') is None
    assert 'sparse same-team' in out['players'][0]['reasons'][-1]


def test_inactive_precedence_does_not_bypass_prediction_integrity():
    r=count_receipt();r['players'][0]['world_activity']=False
    p=dict(player_master_id=PID,team='SF',period=202506,history_supported=False,counts=dict.fromkeys(CHANNELS,-1.))
    with pytest.raises(ValueError,match='Invalid physical'):
        apply_player_count_predictions(r,[p])
