"""One bounded authenticated baseline-matrix decode per grain; no estimator fit."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time,gc
from backend.app.product_services.model_input_admission import admit_matrix,cohort_manifest,VERSION as POLICY
from backend.app.product_services.team_opportunity_models import prepare_model_inputs
from backend.app.product_services.feature_block_model_inputs import prepare_player_inputs
from backend.app.product_services.offensive_volume_features import digest
ROOT=Path('research/reconstructed_model_input_manifest_20261020/v1')
if (ROOT/'MANIFEST.json').exists():raise ValueError('Frozen existing manifest: use a separately identified output revision; no overwrite')
started=datetime.now(UTC);timer=time.monotonic()
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p.resolve()),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
def load(r,cap):
 assert r['bytes']<=cap;raw=Path(r['path']).read_bytes();assert len(raw)==r['bytes']and hashlib.sha256(raw).hexdigest()==r['sha256'];return json.loads(raw)
def save(x,kind):
 raw=json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode();p=Path('artifacts',kind)/(hashlib.sha256(raw).hexdigest()+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb')as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
audit_path=Path('research/model_input_eligibility_audit_20261020/v1/AUDIT.json');audit=json.loads(audit_path.read_text());outputs={}
for grain in ('team','player'):
 contract=audit['existing_'+grain+'_contract'];parent_ref=contract['matrix_ref'];m=load(parent_ref,210*1024*1024);view,stats=admit_matrix(m,grain=grain,parent_ref=parent_ref)
 p=(prepare_model_inputs if grain=='team'else prepare_player_inputs)(view,train_before=202401,validation_before=202501)
 cohorts=cohort_manifest(p,grain=grain);assert cohorts['train']['rows']>=100 and all(c['known_rows']>=100 for c in cohorts['train']['head_cohorts'].values())
 masks=view['admission_policy']['masked_columns'];assert all(k in p['preprocessing']['entirely_missing_train_columns']for k in masks)
 assert p['training_max_period']<202401
 columns=[]
 for name in view['feature_columns']:
  masked=name in masks
  if grain=='team'or name.startswith('team_'):recipe='Reviewed fixed team source recipe: prior same-team/opponent observed event context or latest3/8 source count history; exact recipe in team_opportunity_matrix.py. Known-sample rates retain unknown counters, not automatic latest full catalog estimands.'
  elif name.startswith('position_'):recipe='Latest prior source-listed weekly position for measured historical actor; no inferred health/current expected role.'
  elif name.startswith('event_'):recipe='Exact within-observed-log components across last3/8 observed team-source periods before target. Missing actor/log is unknown, known/unknown counts explicit; not a complete scheduled-NFL census.'
  else:recipe='Latest prior weekly count or3/8 available-row historical mean; share3 is mean of3 per-row channel shares. Missing weekly rows are not DNP/zero.'
  columns.append(dict(name=name,grain=grain,model_admission='MASKED_UNKNOWN'if masked else 'RECONSTRUCTED_PRIOR_INPUT',reason='Original quote clock or provider EP-model/training vintage unproven'if masked else'Prior contributing periods validated; actual source availability still retrospective',recipe=recipe,parent_matrix_ref=parent_ref,source_availability='Revised2026receipt; original historical publication/capture unknown. Not original-pregame backtest proof.',provider_model_vintage='UNPROVEN_EXCLUDED'if masked else'No additional provider expectation model admitted by this policy',all_missing_in_train=name in p['preprocessing']['entirely_missing_train_columns']))
 out=dict(grain=grain,raw_parent_ref=parent_ref,raw_parent_provenance_sha256=digest(m.get('provenance',{})),admission_policy=view['admission_policy'],matrix_semantic_sha256=view['matrix_sha256'],matrix_ref=save(view,'admitted_count_matrices'),prepared_ref=save(p,'admitted_count_prepared'),prepared_sha256=p['prepared_sha256'],columns=columns,target_columns=p['target_columns'],training_max_period=p['training_max_period'],cohorts=cohorts,preprocessing=p['preprocessing'],raw_rows=stats,baseline_prepared_ref=contract.get('prepared_baseline_ref')or contract.get('corrected_prepared_ref'),consumer_code_ref=ref(Path('backend/app/product_services/team_opportunity_models.py'if grain=='team'else'backend/app/product_services/feature_block_model_inputs.py')))
 outputs[grain]=out;print(json.dumps(dict(stage=grain+'_matrix_END',rows=len(view['rows']),columns=len(columns),prepared_ref=out['prepared_ref'],splits={k:v['rows']for k,v in cohorts.items()},all_missing_train=p['preprocessing']['entirely_missing_train_columns'])),flush=True);del m,view,p;gc.collect()
manifest=dict(version='reconstructed_count_matrix_manifest_v1',policy_version=POLICY,actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,admission_code_ref=ref(Path('backend/app/product_services/model_input_admission.py')),audit_ref=ref(audit_path),grains=outputs,catalog_mapping_ref=ref(audit_path),feature_consumption_claim='57/251 ordered historical-recipe columns only;18source-vintage fields masked pergrain;244catalog approvals are NOT244consumed numerical fields or automatic exact catalog consumers.',original_pregame_backtest_eligible=False,outcomes_previously_inspected=True,comparison='Matched tree/neural on identical newly prepared inputs and per-head known labels; frozen prior recipes retained as baselines, data-admission treatment explicit.',target_semantics='Official count labels; player log1p/expm1 point heads are not unbiased arithmetic expected counts. No calibrated probability or joint budget/roster guarantee.',football_gates=['No missing label/actor becomes0 or DNP','Passing and receiving views share one physical event; never sum passes+targets as independent opportunities','Nonnegative point predictions do not certify complete team/player budget conservation; integration/activation remains separate'],fits=0,source_fetches=0,database_reads=0,live_activation=False)
(ROOT/'MANIFEST.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n');print(json.dumps(dict(stage='MANIFEST_END',elapsed_seconds=manifest['elapsed_seconds'],fits=0)),flush=True)
