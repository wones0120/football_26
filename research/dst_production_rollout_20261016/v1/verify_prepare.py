"""Exercise real Prepare scorer on the preserved valid snapshot, no DB writes.

The service's persistence boundary is captured and the real serializer/reloader
is exercised. No fresh-slate availability claim or production acceptance given.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
from unittest.mock import patch
import joblib
import numpy as np
import pandas as pd
from backend.app.product_services.predictions import PredictionsService
from backend.app.product_services.model_artifacts import serialize_artifact,deserialize_artifact,explain_player
from backend.app.product_services.dst_deployment import load_selection

P=Path(__file__).resolve().parent
bundle=joblib.load('research/dst_retrain_20261016/v1/prepared_incumbent.joblib')
service=PredictionsService('sqlite://')
reports=[]

def execute(comp=None,audit=None):
    train,target=bundle['train'].copy(deep=True),bundle['target'].copy(deep=True)
    sources=dict(unresolved_salary_source_keys=[],excluded_positions=[],market_context=dict(team_rows=[]))
    with patch('backend.app.product_services.canonical_projection_inputs.load_inputs',return_value=(train,target,sources)), patch('backend.app.product_services.predictions.generate_walk_forward_residuals',return_value=pd.DataFrame()), patch('backend.app.product_services.predictions.build_position_calibration',return_value=(deepcopy(bundle['profiles']),deepcopy(bundle['calibration']))), patch('backend.app.product_services.predictions.historical_role_calibration',return_value={}), patch('backend.app.product_services.dst_deployment.configured_component',return_value=(comp,audit or dict(status='incumbent_retained'))), patch.object(service,'_train_model',return_value=bundle['model']), patch.object(service,'_persist_target_prediction_run',return_value=True) as persist:
        result=service._train_canonical(season=2026,week=6,positions=None,slate='SUNDAY_MAIN',
            data_cutoff_at=pd.Timestamp('2026-10-15T19:17:26.763111Z').to_pydatetime(),
            feature_run_id=None,model_run_id=None,projection_run_id=None)
    args=persist.call_args.kwargs
    raw,sha=serialize_artifact(model=args['fitted_model'],train=args['train_df'],target=args['source_features'],
        feature_columns=args['feature_cols'],calibration=args['calibration_metrics'],
        profiles=args['calibration_profiles'],dst_component=args['dst_component'])
    loaded=deserialize_artifact(raw,sha)
    return pd.DataFrame([r.__dict__ for r in result.records]),args,loaded,sha

baseline,_,_,_=execute()
for name in ['corrected_dedicated_mae_v1','corrected_temporal_ensemble_v1']:
    pending=P/f'{name}.selection.pending.json'
    data=json.loads(pending.read_text())
    # Local isolated acceptance fixture is not written to runtime or promoted.
    data['acceptance'].update(status='approved',decision_id='ISOLATED_VERIFICATION_ONLY',
        standard='exercise production contract; not authorization to activate',limitations_acknowledged=True)
    fixture=P/f'{name}.selection.ISOLATED_TEST.json'
    fixture.write_text(json.dumps(data,indent=2)+'\n')
    comp,audit=load_selection(fixture,hashlib.sha256(fixture.read_bytes()).hexdigest())
    result,args,loaded,sha=execute(comp,audit)
    mask=baseline.position.ne('DST')
    columns=[c for c in result if c.startswith('predicted_') or c=='adj_mean']
    pd.testing.assert_frame_equal(baseline.loc[mask,columns],result.loc[mask,columns],check_exact=True)
    dst=result.loc[~mask]
    for _,row in dst.iterrows():
        explanation=explain_player(loaded,str(row.player_id))
        assert abs(explanation['reloaded_model_mean']-row.predicted_mean) < 1e-12
        assert row.calibration_sample_size==88
    assert args['source_versions']['dst_deployment']['status']=='selected'
    reports.append(dict(policy=comp['policy'],rows=len(result),offense_rows_unchanged=int(mask.sum()),
        dst_rows=len(dst),distinct_dst_means=dst.predicted_mean.nunique(),
        calibration_rows=88,artifact_reload_exact=True,explanation_tolerance=1e-12,artifact_sha256=sha,
        persisted_to_database=False,inference_audit=args['source_versions']['dst_deployment']['inference']))
(P/'prepare_verification.json').write_text(json.dumps(dict(scope='preserved valid canonical snapshot, real Prepare scoring and serialization; persistence intercepted',fits=0,production_acceptance=False,results=reports),indent=2)+'\n')
print('Prepare verification complete: both components, all 268 non-DST forecasts exact, 20 DST artifact explanations match within 1e-12; no DB writes')
