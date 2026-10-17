from copy import deepcopy
from dataclasses import dataclass
from io import BytesIO
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
import pytest

from backend.app.product_services.dst_deployment import (
    CONTRACT, MANIFEST_CONTRACT, apply_component, configured_component,
    load_selection, score_component,
)
from backend.app.product_services.dst_feature_pipeline import DstFeatureContext, POLICY
from backend.app.product_services.dst_training_labels import SCORING_CONTRACT
from backend.app.product_services.model_artifacts import deserialize_artifact, explain_player, serialize_artifact
from backend.app.tests.product.test_dst_feature_support import files
from backend.app.tests.product.test_dedicated_dst_model import target
from backend.app.tests.product.test_model_artifacts import _fitted_payload


@dataclass
class FixturePolicy:
    columns: tuple = ('player_roll3_mean', 'is_home')

    def predict(self, frame, *, policy):
        return frame.player_roll3_mean.to_numpy() + .1*frame.is_home.to_numpy()


def component(tmp_path):
    kwargs=files(tmp_path)
    manifest=json.loads(open(kwargs['manifest_path']).read())
    context=DstFeatureContext.read(manifest['events']['path'],manifest['identities']['path'],
        expected_events_sha256=manifest['events']['sha256'],expected_identities_sha256=manifest['identities']['sha256'])
    return dict(contract=CONTRACT,policy='ensemble',feature_policy=POLICY,scoring_contract=SCORING_CONTRACT,
        context=context,policies=FixturePolicy(),target_period=202504,training_end=202503,source_hashes=dict(events=context.source_sha256,identities=context.identities_sha256),
        training_features_sha256='fixture-training',calibration_evidence_sha256='fixture-calibration',
        calibration=dict(sample_size=88,source='isolated fixture',residual_quantiles={name:value for name,value in zip(['p10','p25','p50','p75','p90'],[-3,-2,0,2,8])}))


def selection(tmp_path, comp, approved=True):
    artifact=tmp_path/'model.joblib';joblib.dump(comp,artifact)
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    manifest=dict(contract=MANIFEST_CONTRACT,feature_policy=POLICY,scoring_contract=SCORING_CONTRACT,
        policy=comp['policy'],artifact=dict(path=str(artifact),sha256=sha(artifact)),
        acceptance=dict(status='approved' if approved else 'pending',decision_id='isolated-test-only',
            standard='fixture contract, not production approval',limitations_acknowledged=True,evidence_sha256={'fixture':'pinned'}))
    path=tmp_path/'selection.json';path.write_text(json.dumps(manifest))
    return path,sha(path)


def test_selection_requires_explicit_decision_and_exact_bytes(tmp_path):
    comp=component(tmp_path);path,sha=selection(tmp_path,comp,False)
    with pytest.raises(ValueError,match='acceptance'):
        load_selection(path,sha)
    path,sha=selection(tmp_path,comp)
    assert load_selection(path,sha)[1]['acceptance']['decision_id']=='isolated-test-only'
    with pytest.raises(ValueError,match='checksum'):
        load_selection(path,'bad')
    (tmp_path/'model.joblib').write_bytes(b'changed')
    with pytest.raises(ValueError,match='component checksum'):
        load_selection(path,sha)


def test_corrected_home_history_canonical_overlay_preserves_offense_and_source(tmp_path):
    comp=component(tmp_path);dst=target(4).assign(game_id='2025_04_BUF_ARI',player_id='canonical-ari',is_home=0,player_roll3_mean=0)
    offense=dst.copy().assign(position='WR',player_master_id='offense',player_id='offense')
    frame=pd.concat([offense,dst],ignore_index=True);before=frame.copy(deep=True)
    means,audit=apply_component([27.,-100.],frame,comp)
    assert means[0]==27.
    expected=(0+10+50)/3+.1  # home supplied by canonical game, all three prior outcomes
    assert means[1]==pytest.approx(expected)
    assert audit['rows']==1
    pd.testing.assert_frame_equal(frame,before)
    with pytest.raises(ValueError,match='expired'):
        score_component(comp,dst.assign(week=5))
    with pytest.raises(ValueError,match='overlaps'):
        score_component(dict(comp,training_end=202504),dst)
    with pytest.raises(ValueError,match='Ambiguous'):
        score_component(comp,pd.concat([dst,dst]))
    with pytest.raises(ValueError):
        score_component(comp,dst.assign(player_master_id='wrong-canonical-id'))


def test_empty_selection_default_and_configured_failure_explicit(tmp_path):
    dst=target(4)
    with patch('backend.app.config.get_settings',return_value=SimpleNamespace(dst_deployment_manifest_path='')):
        assert configured_component(dst)[0] is None
    with patch('backend.app.config.get_settings',return_value=SimpleNamespace(dst_deployment_manifest_path=str(tmp_path/'absent'),dst_deployment_manifest_sha256='bad')):
        with pytest.raises(FileNotFoundError):
            configured_component(dst)


def test_saved_artifact_reproduces_dst_component_and_explanation(tmp_path):
    comp=component(tmp_path);model,train,oldtarget,columns=_fitted_payload()
    dst=target(4).assign(game_id='2025_04_BUF_ARI',player_id='canonical-ari',recent_team='ARI',opponent_team='BUF',pregame_availability_probability=1.)
    for column in columns:
        if column not in dst:dst[column]=0.
    mixed=pd.concat([oldtarget.iloc[[0]],dst],ignore_index=True)
    raw,sha=serialize_artifact(model=model,train=train,target=mixed,feature_columns=columns,
        calibration={},profiles={},dst_component=comp)
    loaded=deserialize_artifact(raw,sha)
    expected=score_component(comp,dst)[0]['mean'].iloc[0]
    explained=explain_player(loaded,'canonical-ari')
    assert explained['reloaded_model_mean']==pytest.approx(expected)
    assert explained['actual_inputs']['is_home']==1.
    assert 'shared offense tree' in explained['attribution_method']
    # An internally inconsistent saved component cannot pass reload verification.
    bad=deepcopy(loaded);bad['dst_component_predictions']['mean']+=1
    buf=BytesIO();joblib.dump(bad,buf);data=buf.getvalue()
    with pytest.raises(AssertionError):
        deserialize_artifact(data,hashlib.sha256(data).hexdigest())


def test_invalid_selected_manifest_stops_prepare_before_fit_or_persistence(tmp_path):
    from backend.app.product_services.predictions import PredictionsService
    comp=component(tmp_path);path,sha=selection(tmp_path,comp,approved=False)
    service=PredictionsService('sqlite://')
    settings=SimpleNamespace(dst_deployment_manifest_path=str(path),dst_deployment_manifest_sha256=sha)
    with patch('backend.app.config.get_settings',return_value=settings), patch('backend.app.product_services.canonical_projection_inputs.load_inputs',return_value=(pd.DataFrame(),target(4),{})), patch.object(service,'_train_model') as fit, patch.object(service,'_persist_target_prediction_run') as persist:
        with pytest.raises(ValueError,match='acceptance'):
            service._train_canonical(season=2025,week=4,positions=None,slate='test',data_cutoff_at=None,
                feature_run_id=None,model_run_id=None,projection_run_id=None)
    fit.assert_not_called();persist.assert_not_called()


def test_runtime_status_attests_selection_or_reports_failure(tmp_path):
    from backend.app.product_services.dst_deployment import runtime_status
    comp=component(tmp_path);path,sha=selection(tmp_path,comp)
    settings=SimpleNamespace(dst_deployment_manifest_path=str(path),dst_deployment_manifest_sha256=sha)
    with patch('backend.app.config.get_settings',return_value=settings):
        assert runtime_status()['policy']=='ensemble'
    settings.dst_deployment_manifest_sha256='invalid'
    with patch('backend.app.config.get_settings',return_value=settings):
        assert runtime_status()['status']=='invalid_selection'
        assert 'no_silent_fallback' in runtime_status()['prepare_policy']
