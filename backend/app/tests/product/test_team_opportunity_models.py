from copy import deepcopy
import numpy as np
import pytest

from backend.app.product_services.team_opportunity_models import prepare_model_inputs,transform_rows,fit_team_family,predict_team_family,predict_team_families
from backend.app.product_services.defense_context_evidence import _hash
from backend.app.product_services.team_opportunity_matrix import VERSION,FEATURES


def matrix():
    rows=[]
    for i,(period,value,y) in enumerate([(202301,1,10),(202302,None,20),(202401,1000,30),(202501,2000,40),(202606,3,None)]):
        rows.append(dict(game_id=f'game{i}',team='BUF',period=period,legacy_feature_ready=True,
            features=dict.fromkeys(FEATURES)|dict(pass_mean3=value,pass_mean8=None),labels=dict(pass_attempts=y,rush_attempts=y)))
    result=dict(version=VERSION,before_period=202606,feature_columns=list(FEATURES),target_columns=['pass_attempts','rush_attempts'],rows=rows)
    result['matrix_sha256']=_hash(result)
    return result


def prepared():return prepare_model_inputs(matrix(),train_before=202401,validation_before=202501)


def test_train_only_imputation_scaling_same_frozen_inputs_and_all_missing_mask():
    result=prepared();p=result['preprocessing']
    assert p['medians'][:2]==[1,0]
    assert p['center'][:2]==[1,0]
    assert p['entirely_missing_train_columns']==list(FEATURES[1:])
    assert result['training_max_period']==202302
    assert result['splits']['train']['x'][1][len(FEATURES):len(FEATURES)+2]==[1,1]
    assert result['splits']['validation']['x'][0][0]==999
    assert result['splits']['retrospective_test']['keys'][0]['period']==202501
    assert len(result['splits']['train']['x'][0])==len(FEATURES)*2
    assert prepared()==result


def test_changed_validation_values_do_not_learn_preprocessing_and_tamper_rejects():
    a=matrix();b=deepcopy(a);b['rows'][2]['features']['pass_mean3']=999999;b.pop('matrix_sha256');b['matrix_sha256']=_hash(b)
    assert prepare_model_inputs(a,train_before=202401,validation_before=202501)['preprocessing']==prepare_model_inputs(b,train_before=202401,validation_before=202501)['preprocessing']
    a['rows'][0]['features']['pass_mean3']=10
    with pytest.raises(ValueError,match='checksum'):prepare_model_inputs(a,train_before=202401,validation_before=202501)


def test_forward_rows_are_not_training_labels_and_empty_training_rejects():
    result=prepared()
    assert not any(k['period']==202606 for split in result['splits'].values() for k in split['keys'])
    with pytest.raises(ValueError,match='training rows'):prepare_model_inputs(matrix(),train_before=202201,validation_before=202301)
    with pytest.raises(ValueError,match='100'):fit_team_family(result,family='tree')


class Constant:
    def __init__(self,value):self.value=value
    def predict(self,x):return np.full(len(x),self.value)


class ConstantPair:
    def predict(self,x):return np.tile([1,-1],(len(x),1))


def bundle(family):
    p=prepared();return dict(receipt=dict(version='team_opportunity_models_v1',code_sha256='a'*64,status='fit_complete',family=family,training_max_period=202302,
        preprocessing=p['preprocessing'],target_columns=p['target_columns'],matrix_sha256=p['matrix_sha256'],prepared_sha256=p['prepared_sha256']),
        estimators=[Constant(0),Constant(0)] if family=='tree' else ConstantPair())


def test_same_target_simple_average_components_disagreement_not_added_twice():
    rows=[matrix()['rows'][-1]]
    result=predict_team_families(bundle('tree'),bundle('neural'),rows,before_period=202606)[0]
    assert result['components']['tree']==dict(pass_attempts=15,rush_attempts=15)
    assert result['components']['neural']==dict(pass_attempts=20,rush_attempts=10)
    assert result['counts']==dict(pass_attempts=17.5,rush_attempts=12.5)
    assert result['disagreement']==dict(pass_attempts=5,rush_attempts=5)
    assert 'not a calibrated interval' in result['uncertainty']


def test_mismatched_families_future_training_nonconvergence_and_incomplete_rows_reject():
    rows=[matrix()['rows'][-1]];neural=bundle('neural');neural['receipt']['matrix_sha256']='other'
    with pytest.raises(ValueError,match='same frozen'):predict_team_families(bundle('tree'),neural,rows,before_period=202606)
    for field,value in [('training_max_period',202606),('status','fit_not_converged')]:
        model=bundle('tree');model['receipt'][field]=value
        with pytest.raises(ValueError,match='Unusable'):predict_team_family(model,rows,before_period=202606)
    rows[0]['legacy_feature_ready']=False
    with pytest.raises(ValueError,match='incomplete'):predict_team_family(bundle('tree'),rows,before_period=202606)


def test_no_implicit_estimator_fit_in_preprocessing_or_prediction(monkeypatch):
    def forbidden(*a,**k):raise AssertionError('No model fit during matrix/inference tests')
    monkeypatch.setattr('backend.app.product_services.team_opportunity_models.HistGradientBoostingRegressor.fit',forbidden)
    monkeypatch.setattr('backend.app.product_services.team_opportunity_models.MLPRegressor.fit',forbidden)
    prepared();predict_team_family(bundle('tree'),[matrix()['rows'][-1]],before_period=202606)


def test_forged_fp_feature_and_target_period_source_guard():
    value=matrix();value['feature_columns'][0]='fantasy_points';value.pop('matrix_sha256');value['matrix_sha256']=_hash(value)
    with pytest.raises(ValueError,match='ordered count matrix'):
        prepare_model_inputs(value,train_before=202401,validation_before=202501)
    value=matrix();value['rows'][0]['context_periods']=[202301];value.pop('matrix_sha256');value['matrix_sha256']=_hash(value)
    with pytest.raises(ValueError,match='leaks'):
        prepare_model_inputs(value,train_before=202401,validation_before=202501)


@pytest.mark.parametrize('labels',[dict(pass_attempts=1),dict(pass_attempts=1,rush_attempts=float('nan')),dict(pass_attempts=1,rush_attempts=-1),dict(pass_attempts=1,rush_attempts=float('inf'))])
def test_incomplete_nonfinite_or_negative_labels_in_any_split_rejected(labels):
    value=matrix();value['rows'][2]['labels']=labels;value.pop('matrix_sha256')
    # NaN/Inf cannot enter a valid canonical JSON receipt in the first place.
    try:value['matrix_sha256']=_hash(value)
    except ValueError:return
    with pytest.raises(ValueError,match='label'):
        prepare_model_inputs(value,train_before=202401,validation_before=202501)


def test_inference_future_contributing_period_rejected_and_final_refit_explicit():
    rows=[matrix()['rows'][-1]];rows[0]['legacy_periods']=[202606]
    with pytest.raises(ValueError,match='contributing period'):
        predict_team_family(bundle('tree'),rows,before_period=202606)
    final=prepare_model_inputs(matrix(),train_before=202606)
    assert final['final_refit'] is True
    assert final['training_max_period']==202501
    assert final['splits']['validation']['x']==[] and final['splits']['retrospective_test']['x']==[]


def test_managed_model_persistence_roundtrip_metadata_clock_root_and_tamper(tmp_path):
    from backend.app.product_services.team_opportunity_models import freeze_team_family,load_team_family
    model=bundle('tree');ref=freeze_team_family(model,directory=tmp_path,producer_clock=lambda:'2026-10-19T19:00:00Z')
    loaded=load_team_family(ref,before_period=202606,cutoff='2026-10-19T20:00:00Z',directory=tmp_path)
    assert loaded['receipt']==model['receipt']
    with pytest.raises(ValueError,match='metadata'):
        load_team_family(ref|dict(matrix_sha256='other'),before_period=202606,cutoff='2026-10-19T20:00:00Z',directory=tmp_path)
    with pytest.raises(ValueError,match='managed root'):
        load_team_family(ref|dict(path='/private/tmp/research.joblib'),before_period=202606,cutoff='2026-10-19T20:00:00Z',directory=tmp_path)
    with pytest.raises(ValueError,match='unavailable'):
        load_team_family(ref,before_period=202606,cutoff='2026-10-19T18:00:00Z',directory=tmp_path)
    with pytest.raises(ValueError,match='byte bound'):
        load_team_family(ref,before_period=202606,cutoff='2026-10-19T20:00:00Z',directory=tmp_path,max_bytes=1)
    from pathlib import Path
    path=Path(ref['path']);original=path.read_bytes();path.chmod(0o600);path.write_bytes(original[:-1]+bytes([original[-1]^1]))
    with pytest.raises(ValueError,match='byte hash'):
        load_team_family(ref,before_period=202606,cutoff='2026-10-19T20:00:00Z',directory=tmp_path)


def test_never_observed_training_column_stays_unknown_without_mutating_source():
    result=prepared();p=result['preprocessing'];rows=[deepcopy(matrix()['rows'][-1])]
    rows[0]['features']['pass_mean8']=42
    original=deepcopy(rows)
    actual=transform_rows(rows,p)
    absent=deepcopy(rows);absent[0]['features']['pass_mean8']=None
    assert np.array_equal(actual,transform_rows(absent,p))
    assert actual[0][1]==0 and actual[0][len(FEATURES)+1]==1
    assert rows==original and rows[0]['features']['pass_mean8']==42
    # The column learned during training still consumes a newly observed value.
    assert actual[0][0]==2 and actual[0][len(FEATURES)]==0
    # Old explicitly supplied preprocessing without this metadata keeps its contract.
    legacy=deepcopy(p);legacy.pop('entirely_missing_train_columns')
    assert transform_rows(rows,legacy)[0][1]==42


def test_holdout_values_cannot_activate_an_entirely_missing_training_channel():
    value=matrix();value['rows'][2]['features']['pass_mean8']=42;value['rows'][3]['features']['pass_mean8']=99
    value.pop('matrix_sha256');value['matrix_sha256']=_hash(value)
    p=prepare_model_inputs(value,train_before=202401,validation_before=202501)
    for name in ('validation','retrospective_test'):
        assert p['splits'][name]['x'][0][1]==0
        assert p['splits'][name]['x'][0][len(FEATURES)+1]==1
