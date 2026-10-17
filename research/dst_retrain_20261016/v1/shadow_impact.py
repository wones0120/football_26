from pathlib import Path
from datetime import datetime,UTC
from contextlib import redirect_stdout
import json,hashlib,joblib
import numpy as np,pandas as pd
from sklearn.base import clone
from backend.app.product_services.dst_training_labels import read_verified_correction,select_corrected_dst_labels
from backend.app.product_services.predictions import TARGET_COL,blend_point_predictions
from backend.app.product_services.model_artifacts import training_fingerprint,git_revision
from backend.app.product_services.classic_highest_projection import solve
from backend.app.product_services.optimizer import OptimizerService,_json_safe
P=Path(__file__).resolve().parent;C=Path('research/dst_scoring_repair_20261015/v1');receipt=json.load(open(C/'full_matrix_version_receipt.json'))
dataset=read_verified_correction(receipt['artifact_path'],expected_sha256=receipt['content_sha256']);a=joblib.load(P/'prepared_incumbent.joblib');train,audit=select_corrected_dst_labels(a['train'],dataset,target_season=2026,target_week=6);features=a['feature_columns'];target=a['target'];dst=target.position.eq('DST');model=clone(a['model']);model.fit(train[features].apply(pd.to_numeric,errors='coerce').fillna(0),train[TARGET_COL])
raw=model.predict(target[features].apply(pd.to_numeric,errors='coerce').fillna(0));means=np.maximum(0,blend_point_predictions(raw,train,target));baseline=target.projection_after_scenario.to_numpy()
# Verify exact incumbent arithmetic for DST before using the frozen target snapshot.
old=np.maximum(0,blend_point_predictions(a['model'].predict(target[features].apply(pd.to_numeric,errors='coerce').fillna(0)),a['train'],target));assert np.max(np.abs(old[dst]-baseline[dst]))<1e-9
ranking=pd.DataFrame(dict(player_id=target.loc[dst,'player_id'].to_numpy(),team=target.loc[dst,'recent_team'].to_numpy(),old=baseline[dst],candidate=means[dst],salary=target.loc[dst,'salary'].to_numpy()));ranking['old_rank']=ranking.old.rank(ascending=False,method='min').astype(int);ranking['candidate_rank']=ranking.candidate.rank(ascending=False,method='min').astype(int);ranking['delta']=ranking.candidate-ranking.old;ranking=ranking.sort_values('candidate_rank');ranking.to_csv(P/'sunday_defense_rankings.csv',index=False)
saved=json.load(open('research/sunday_hurts_refresh_20261015/v1/saved_run.json'));report=saved['params']['strategy_runtime']['highest_projection'];pool=pd.DataFrame(report['input_snapshot']['players']);pool_before=pool.copy(deep=True);candidate_by_id=dict(zip(ranking.player_id,ranking.candidate));mask=pool.position.eq('DST');pool.loc[mask,'projection']=pool.loc[mask,'player_id'].map(candidate_by_id);assert pool.loc[~mask].equals(pool_before.loc[~mask]);assert pool.drop(columns='projection').equals(pool_before.drop(columns='projection'))
service=OptimizerService.__new__(OptimizerService);arms={}
with open(P/'shadow_solver.log','w') as h,redirect_stdout(h):
 for name,frame in [('before',pool_before),('corrected_dst_only_shadow',pool)]:
  lineups,solver_audit=solve(service,frame,params=saved['params'],cutoff=datetime.fromisoformat('2026-10-15T19:17:26.763111+00:00'))
  arms[name]=_json_safe(dict(lineups=lineups,audit=solver_audit));assert solver_audit['solver_status']=='Optimal'
assert abs(arms['before']['audit']['base_mean']-133.143015329788)<.001
(P/'matched_lineups.json').write_text(json.dumps(arms,indent=2,allow_nan=False)+'\n')
# Shadow only: heldout gate failed; this full-history fit is for future Week6 impact, never scored as validation.
metadata=dict(version='v4.2-dst-exact-label-shadow-20261016',created_at=datetime.now(UTC).isoformat(),status='REJECTED_FOR_LIVE_PROMOTION',live_activation=False,validation_file='validation.json',source_snapshot_id=receipt['snapshot_id'],source_content_sha256=receipt['content_sha256'],scoring_contract=dataset['contract_id'],selection=audit,training_rows=len(train),training_through='2026-W05',target='2026-W06',dataset_sha256=training_fingerprint(train),feature_columns=features,feature_set_sha256=hashlib.sha256(json.dumps(features).encode()).hexdigest(),model_parameters=model.get_params(),git_revision=git_revision(),baseline_projection_run_id=saved['projection_run_id'],baseline_saved_run=saved['job_id'],frozen_source_cutoff='2026-10-15T19:17:26.763111+00:00',non_dst_changes_applied=0,all_defense_rows=len(ranking),rank_changes=int((ranking.old_rank!=ranking.candidate_rank).sum()),model_design='shared multi-position fit; only DST results substituted in matched comparison',intervals='Full shadow fit is uncalibrated for live use. Historical validation intervals use prior calibration windows.',code_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('backend/app/product_services/dst_training_labels.py'),Path('backend/app/product_services/predictions.py'),Path('backend/app/product_services/canonical_projection_inputs.py'),Path(__file__)]})
joblib.dump(dict(model=model,train=train,target=target,feature_columns=features,metadata=metadata),P/'candidate_shadow.joblib',compress=3);metadata['artifact_sha256']=hashlib.sha256((P/'candidate_shadow.joblib').read_bytes()).hexdigest();(P/'candidate_manifest.json').write_text(json.dumps(metadata,indent=2,default=str)+'\n')
for arm,result in arms.items():print(arm,result['audit']['base_mean'],result['audit']['salary'],[(r['name'],round(r['projection'],4)) for r in result['lineups'][0]])
print(ranking.to_string(index=False));print('rank changes',metadata['rank_changes'],flush=True)
