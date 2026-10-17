"""Stage fixed existing models; zero fits and no DB/runtime selection changes."""
from pathlib import Path
import hashlib
import json
import joblib
import numpy as np
import pandas as pd
from backend.app.product_services.dst_deployment import CONTRACT, MANIFEST_CONTRACT, score_component
from backend.app.product_services.dst_feature_pipeline import POLICY
from backend.app.product_services.dst_training_labels import SCORING_CONTRACT

P=Path(__file__).resolve().parent
R=Path('research/dst_rank_stability_20261016/v1')
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
save=lambda path,data:path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
bundle=joblib.load(R/'ranking_candidate.joblib')
cal=pd.DataFrame(json.loads((R/'inner_row_predictions.json').read_text()))
original_target=joblib.load('research/dst_retrain_20261016/v1/prepared_incumbent.joblib')['target']
parity=[]
for policy,name in [('existing_mae_policy','corrected_dedicated_mae_v1'),('ensemble','corrected_temporal_ensemble_v1')]:
    # All 88 calibration forecasts were made by the prefix fit, before their
    # W3-W5 outcomes. They are disclosed retrospective, not fresh validation.
    calibration_model='median' if policy=='existing_mae_policy' else policy
    rows=cal[cal.model.eq(calibration_model)]
    assert len(rows)==88
    residual=rows.actual-rows.prediction
    component=dict(contract=CONTRACT,policy=policy,feature_policy=POLICY,
        scoring_contract=SCORING_CONTRACT,policies=bundle['policies'],context=bundle['context'],
        training_end=202605,target_period=202606,source_hashes=bundle['metadata']['source_hashes'],
        training_features_sha256=bundle['metadata']['training_features_sha256'],
        calibration=dict(sample_size=len(rows),source='DST prefix-only W3-W5 residuals; retrospective verified labels',
            residual_quantiles={f'p{int(q*100)}':float(residual.quantile(q)) for q in [.1,.25,.5,.75,.9]}),
        calibration_evidence_sha256=sha(R/'inner_row_predictions.json'),
        original_source_clock_attestation=False)
    artifact=P/f'{name}.joblib';joblib.dump(component,artifact,compress=3)
    reloaded=joblib.load(artifact)
    scored,audit=score_component(reloaded,original_target)
    frozen=pd.read_csv(R/'sunday_defense_rankings.csv')
    # CSV is a readable artifact; strict parity against the original policies.
    expected=bundle['policies'].predict(scored,policy=policy)
    np.testing.assert_array_equal(scored['mean'].to_numpy(),expected)
    manifest=dict(contract=MANIFEST_CONTRACT,policy=policy,feature_policy=POLICY,
        scoring_contract=SCORING_CONTRACT,artifact=dict(path=str(artifact),sha256=sha(artifact)),
        acceptance=dict(status='pending',decision_id=None,standard=None,
            limitations_acknowledged=False,evidence_sha256={
                'point_noninferiority':sha('research/dst_pipeline_repair_20261016/v1/validation.json'),
                'ranking_study':sha(R/'validation.json')}),
        limitations=['Previously inspected outcomes; historical capture clocks incomplete',
            'Rank-superiority gate failed; never relabelled as passed',
            'Component expires after 2026 week 6; no stale historical rollout'],
        evidence=dict(point_pass_policy='corrected dedicated MAE policy',
                      ranking_superiority_pass=False))
    selection=P/f'{name}.selection.pending.json';save(selection,manifest)
    parity.append(dict(policy=policy,artifact_sha256=sha(artifact),selection_path=str(selection),
        rows=len(scored),distinct_means=scored['mean'].nunique(),calibration_rows=len(rows),audit=audit))
save(P/'staging_verification.json',dict(fits=0,active_selection_changed=False,parity=parity))
print('Staged two fixed components; 20 DST rows each reproduce; no active selection changed')
