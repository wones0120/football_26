from copy import deepcopy
from io import BytesIO
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
import pytest

from backend.app.product_services.dst_feature_support import build_support, operational_support, SUPPORT_MANIFEST, LEGACY_DST_CONTRACT
from backend.app.product_services.dst_feature_pipeline import POLICY
from backend.app.product_services.dst_training_labels import SCORING_CONTRACT
from backend.app.product_services.model_artifacts import serialize_artifact,deserialize_artifact
from backend.app.tests.product.test_dedicated_dst_model import event,target
from backend.app.tests.product.test_model_artifacts import _fitted_payload


def files(tmp_path,activation=False):
    events=tmp_path/'events.json';events.write_text(json.dumps([event(1,0),event(2,10),dict(event(3,50),game_id='2025_03_BUF_ARI')]))
    ids=tmp_path/'identities.json';ids.write_text(json.dumps([dict(primary_team='ARI',player_master_id='canonical-ari')]))
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps(dict(contract=SUPPORT_MANIFEST,feature_policy=POLICY,scoring_contract=SCORING_CONTRACT,model_activation=activation,events=dict(path=str(events),sha256=sha(events)),identities=dict(path=str(ids),sha256=sha(ids)))))
    return dict(manifest_path=str(manifest),manifest_sha256=sha(manifest),output_root=str(tmp_path/'support'),cutoff='2025-10-01T12:00:00Z')


def frames():
    train=target().assign(game_id=None,is_home=0,player_games_history=0,dk_points=0.,label_dk_total_points=0.)
    prediction=target(4).assign(is_home=0,player_games_history=0)
    return train,prediction


def test_support_reconstructs_versioned_inputs_without_changing_incumbent_frames(tmp_path):
    kwargs=files(tmp_path);train,prediction=frames();before_train=train.copy(deep=True);before_target=prediction.copy(deep=True)
    result=build_support(train,prediction,**kwargs)
    assert result['status']=='ready_inactive' and not result['model_activation']
    assert result['active_model_input_contract']==LEGACY_DST_CONTRACT
    payload=json.loads(open(result['artifact_path']).read())
    assert payload['training'][0]['label_dk_total_points']==50
    assert payload['training'][0]['is_home']==1 and payload['training'][0]['player_roll3_mean']==5
    assert payload['original_training_labels'][0]['label_dk_total_points']==0
    assert payload['classification'].startswith('VERSIONED_RECONSTRUCTED')
    assert 'dk_points' not in payload['prediction'][0]
    pd.testing.assert_frame_equal(train,before_train);pd.testing.assert_frame_equal(prediction,before_target)
    assert train.attrs==before_train.attrs and prediction.attrs==before_target.attrs
    assert build_support(train,prediction,**kwargs)['support_id']==result['support_id']


def test_bad_checksums_activation_and_missing_training_evidence_reject(tmp_path):
    kwargs=files(tmp_path);train,prediction=frames()
    with pytest.raises(ValueError,match='checksum'):
        build_support(train,prediction,**dict(kwargs,manifest_sha256='bad'))
    kwargs=files(tmp_path,activation=True)
    with pytest.raises(ValueError,match='activation'):
        build_support(train,prediction,**kwargs)
    kwargs=files(tmp_path);train=target(5).assign(is_home=0,dk_points=0.,label_dk_total_points=0.)
    with pytest.raises(ValueError,match='cover every'):
        build_support(train,prediction,**kwargs)


def test_support_failure_is_explicit_and_cannot_activate_or_mutate(tmp_path):
    train,prediction=frames();settings=SimpleNamespace(dst_feature_support_manifest_path='missing',dst_feature_support_manifest_sha256='bad',dst_feature_support_output_root=str(tmp_path))
    with patch('backend.app.config.get_settings',return_value=settings):
        result=operational_support(train,prediction,cutoff='2025-10-01')
    assert result['status']=='unavailable' and not result['model_activation'] and result['error']
    assert result['active_model_input_contract']==LEGACY_DST_CONTRACT


def test_incumbent_artifact_marks_contract_rejects_candidate_and_loads_old_payload():
    model,train,prediction,columns=_fitted_payload()
    kwargs=dict(model=model,train=train,target=prediction,feature_columns=columns,calibration={},profiles={})
    raw,sha=serialize_artifact(**kwargs);loaded=deserialize_artifact(raw,sha)
    assert loaded['feature_contracts']['dst']==LEGACY_DST_CONTRACT
    np.testing.assert_array_equal(loaded['raw_predictions'],model.predict(prediction[columns]))
    old=deepcopy(loaded);old.pop('feature_contracts');buffer=BytesIO();joblib.dump(old,buffer);oldraw=buffer.getvalue()
    assert deserialize_artifact(oldraw,hashlib.sha256(oldraw).hexdigest())['feature_contracts']['dst']==LEGACY_DST_CONTRACT
    train.attrs['dst_feature_policy']=POLICY
    with pytest.raises(ValueError,match='Candidate DST'):
        serialize_artifact(**kwargs)
    loaded['feature_contracts']['dst']=POLICY;buffer=BytesIO();joblib.dump(loaded,buffer);bad=buffer.getvalue()
    with pytest.raises(ValueError,match='feature contract'):
        deserialize_artifact(bad,hashlib.sha256(bad).hexdigest())


def test_normal_prediction_workflow_persists_support_audit_without_changing_scores(tmp_path):
    from sqlalchemy import create_engine
    from backend.app.models import CuratedSalary,PlayerGameFeatureMatrix
    from backend.app.product_services.predictions import PredictionsService
    from backend.app.tests.product.test_canonical_projection_inputs import inputs,CUTOFF
    engine=create_engine(f"sqlite:///{tmp_path/'normal.sqlite'}")
    matrix,salaries=inputs()
    for frame,model in [(matrix,PlayerGameFeatureMatrix),(salaries,CuratedSalary)]:
        frame['created_at']=pd.to_datetime(frame.created_at,utc=True).dt.tz_localize(None)
        for column in model.__table__.columns:
            if column.name not in frame:frame[column.name]=None
        frame.to_sql(model.__tablename__,engine,index=False)
    service=PredictionsService(str(engine.url));audit=dict(status='ready_inactive',model_activation=False,active_model_input_contract=LEGACY_DST_CONTRACT,support_id='verified-test-support')
    with patch('backend.app.product_services.dst_feature_support.operational_support',return_value={'status':'not_configured'}), patch.object(service,'_persist_target_prediction_run',return_value=True):
        before=service.train_and_predict(season=2026,week=1,slate='night',data_cutoff_at=CUTOFF)
    with patch('backend.app.product_services.dst_feature_support.operational_support',return_value=audit), patch.object(service,'_persist_target_prediction_run',return_value=True) as persist:
        after=service.train_and_predict(season=2026,week=1,slate='night',data_cutoff_at=CUTOFF)
    forecasts=lambda records:[{key:value for key,value in row.__dict__.items() if key.startswith('predicted_') or key in {'adj_mean','adj_p90'}} for row in records]
    assert forecasts(before.records)==forecasts(after.records)
    assert persist.call_args.kwargs['source_versions']['dst_feature_support']==audit
    assert persist.call_args.kwargs['calibration_metrics']['dst_feature_support']==audit
