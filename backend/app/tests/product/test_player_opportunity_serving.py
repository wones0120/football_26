from copy import deepcopy
from datetime import UTC,datetime,timedelta
from io import BytesIO
import hashlib,json
import joblib
import pytest
from backend.app.product_services.player_opportunity_serving import load_player_result,infer_player_counts
from backend.app.tests.product.test_feature_block_model_inputs import pair,matrix,count_receipt
from backend.app.product_services.offensive_volume_features import digest


def fixture(tmp_path):
    p,t,n=pair();now=datetime.now(UTC)+timedelta(seconds=5);refs={}
    for family,b in [('tree',t),('neural',n)]:
        envelope=dict(contract='player_opportunity_model_artifact_v1',published_at=now.isoformat(),bundle=b)
        stream=BytesIO();joblib.dump(envelope,stream);raw=stream.getvalue();sha=hashlib.sha256(raw).hexdigest();path=tmp_path/(sha+'.joblib');path.write_bytes(raw)
        refs[family]=dict(path=str(path),sha256=sha,bytes=len(raw),contract=envelope['contract'],published_at=now.isoformat(),family=family,receipt_sha256=digest(b['receipt']))
    result=dict(status='actual_two_player_families_fitted_not_registered_or_app_consumed',actual_family_fits=2,completed_at=now.isoformat(),model_refs=refs)
    def save(value):
        raw=json.dumps(value,sort_keys=True).encode();sha=hashlib.sha256(raw).hexdigest();(tmp_path/(sha+'.json')).write_bytes(raw);return sha
    return now+timedelta(seconds=1),result,save


def test_frozen_pair_real_loader_and_actual_count_consumer_unknowns(tmp_path):
    cutoff,result,save=fixture(tmp_path);sha=save(result);m=matrix();r=deepcopy(m['rows'][-1]);r.update(period=202506,current_inference=True);m['rows']=[r];m['matrix_sha256']=digest({k:v for k,v in m.items() if k not in {'matrix_sha256','provenance'}})
    out=infer_player_counts(sha,m,count_receipt(),cutoff=cutoff,purpose='offline_retrospective_evaluation',directory=tmp_path)
    assert out['status']=='forecast_complete' and not out['pregame_serving_eligible']
    assert len(out['predictions'])==1 and out['counts']['players'][0]['counts']['rush_attempts']!=5.
    assert out['counts']['players'][1]['counts']['targets'] is None
    assert 'sha256' in out['counts']
    with pytest.raises(ValueError,match='retrospective'):infer_player_counts(sha,m,count_receipt(),cutoff=cutoff,directory=tmp_path)


def test_changed_event_window_requires_matching_refitted_model(tmp_path):
    from backend.app.product_services.offensive_volume_features import ACTIVE_VERSION
    cutoff,result,save=fixture(tmp_path);m=matrix();m['version']=ACTIVE_VERSION
    m['matrix_sha256']=digest({k:v for k,v in m.items() if k not in {'matrix_sha256','provenance'}})
    with pytest.raises(ValueError,match='event-window'):
        infer_player_counts(save(result),m,count_receipt(),cutoff=cutoff,purpose='offline_retrospective_evaluation',directory=tmp_path)


@pytest.mark.parametrize('kind',['hash','path','future','receipt','nonconverged','period'])
def test_invalid_model_artifacts_never_enter_count_consumer(tmp_path,kind):
    cutoff,result,save=fixture(tmp_path)
    if kind=='path':result['model_refs']['tree']['path']='/tmp/client-model.joblib'
    if kind=='receipt':result['model_refs']['tree']['receipt_sha256']='0'*64
    if kind=='future':cutoff=datetime(2000,1,1,tzinfo=UTC)
    if kind=='nonconverged':result['status']='incomplete'
    sha=save(result)
    if kind=='hash':(tmp_path/(sha+'.json')).write_text('{}')
    with pytest.raises(ValueError):load_player_result(sha,before_period=202519 if kind=='period' else 202506,cutoff=cutoff,directory=tmp_path)


@pytest.mark.parametrize('active',[False,True])
@pytest.mark.parametrize('model_version',['player_opportunity_models_active_games_v2','player_opportunity_models_rb_rush_mean_v3','player_opportunity_models_sparse_wr_return_v4'])
def test_registry_preserves_latest_compatible_model_for_legacy_consumers(monkeypatch,active,model_version):
    from types import SimpleNamespace
    from backend.app.product_services import player_opportunity_serving as service
    rows=[]
    for sha in ['active','legacy']:
        envelope=dict(payload=dict(result_sha256=sha,published_at='2026-01-01T00:00:00+00:00',model_refs={}))
        from backend.app.product_services.evaluation_record import digest as ledger_digest
        rows.append(dict(record_id='evaluation-'+ledger_digest(envelope),record_json=envelope))
    session=SimpleNamespace(execute=lambda *a,**k:SimpleNamespace(mappings=lambda:SimpleNamespace(all=lambda:rows)))
    def load(sha,**kwargs):
        version=model_version if sha=='active' else service.VERSION
        return dict(model_refs={}),dict(tree=dict(receipt=dict(version=version)))
    monkeypatch.setattr(service,'load_player_result',load)
    monkeypatch.setattr(service,'infer_player_counts',lambda sha,*a,**k:dict(selected=sha))
    out=service.predict_registered_players(session,dict(version=service.ACTIVE_MATRIX_VERSION if active else 'player_opportunity_matrix_v1'),dict(before_period=202607),cutoff='2026-10-21T00:00:00+00:00')
    assert out['selected']==('active' if active else 'legacy')


def scoped_fixture(tmp_path,bundles=None):
    from backend.app.tests.product.test_feature_block_model_inputs import scoped_pair
    _,t,n=bundles or scoped_pair();now=datetime.now(UTC)+timedelta(seconds=5);refs={}
    for family,b in [('tree',t),('neural',n)]:
        envelope=dict(contract='player_opportunity_model_artifact_v1',published_at=now.isoformat(),bundle=b)
        stream=BytesIO();joblib.dump(envelope,stream);raw=stream.getvalue();sha=hashlib.sha256(raw).hexdigest();path=tmp_path/(sha+'.joblib');path.write_bytes(raw)
        refs[family]=dict(path=str(path),sha256=sha,bytes=len(raw),contract=envelope['contract'],published_at=now.isoformat(),family=family,receipt_sha256=digest(b['receipt']))
    result=dict(status='actual_two_player_families_fitted_not_registered_or_app_consumed',actual_family_fits=2,completed_at=now.isoformat(),model_refs=refs)
    raw=json.dumps(result).encode();sha=hashlib.sha256(raw).hexdigest();(tmp_path/(sha+'.json')).write_bytes(raw)
    return now+timedelta(seconds=1),sha


def test_real_scoped_model_loader_preserves_unknowns_and_full_team_residuals(tmp_path):
    from backend.app.product_services.offensive_volume_features import ACTIVE_VERSION
    cutoff,sha=scoped_fixture(tmp_path);m=matrix();r=deepcopy(m['rows'][-1]);r.update(period=202506,current_inference=True);m.update(version=ACTIVE_VERSION,rows=[r]);m['matrix_sha256']=digest({k:v for k,v in m.items() if k not in {'matrix_sha256','provenance'}})
    out=infer_player_counts(sha,m,count_receipt(),cutoff=cutoff,purpose='offline_retrospective_evaluation',directory=tmp_path)
    assert out['predictions'][0]['counts']['rush_attempts']==10.
    assert out['counts']['players'][0]['counts']['rush_attempts']==5.  # Unknown WR keeps reference residual.
    assert out['counts']['players'][1]['counts']['rush_attempts'] is None
    assert out['counts']['teams']['SF']['reconciliation']['rush_attempts']['unallocated']==15.
    assert out['count_head_contract']['rb_rush_mean_head']['position']=='RB'


@pytest.mark.parametrize('invalid',[None,'scale','missing_estimator','future_training'])
def test_sparse_receiver_managed_loader_validates_actual_head_contract(tmp_path,invalid):
    from backend.app.tests.product.test_feature_block_model_inputs import sparse_pair
    bundles=sparse_pair()
    if invalid=='scale':bundles[1]['receipt']['sparse_wr_count_heads']['heads']['targets']['target_scaler']['scale']=0
    if invalid=='missing_estimator':bundles[1]['estimators'].pop('sparse_wr_targets')
    if invalid=='future_training':bundles[1]['receipt']['sparse_wr_count_heads']['heads']['targets']['training_max_period']=202506
    cutoff,sha=scoped_fixture(tmp_path,bundles)
    if invalid:
        with pytest.raises(ValueError,match='sparse WR'):load_player_result(sha,before_period=202506,cutoff=cutoff,directory=tmp_path)
    else:
        _,pair=load_player_result(sha,before_period=202506,cutoff=cutoff,directory=tmp_path)
        assert pair['tree']['receipt']['sparse_wr_count_heads']['prior_games']==2
