"""One root-authorized fixed-recipe offline fit; no activation or automatic retry."""
from pathlib import Path
from datetime import datetime,UTC
import argparse,json,hashlib,time,signal
from io import BytesIO
import numpy as np
import joblib
from backend.app.product_services.team_opportunity_models import fit_team_family,_predict as team_predict
from backend.app.product_services.raw_count_player_models import fit_raw_player_family,predict_arrays,count_metrics
from backend.app.product_services.evaluation_record import digest
p=argparse.ArgumentParser();p.add_argument('--grain',choices=['team','player'],required=True);p.add_argument('--family',choices=['tree','neural'],required=True);a=p.parse_args()
ROOT=Path('research/workload_direct_count_fits_20261020/v1');name=a.grain+'_'+a.family;out=ROOT/(name+'.json')
if out.exists():raise ValueError('Immutable existing fit receipt; no automatic retry')
GATE=Path('research/workload_efficiency_model_batch_20261020/v1/HIGH_REVIEW.json');gate=json.loads(GATE.read_text());assert gate['status']=='FINAL_PASS_MATRIX_AND_SOURCE_ACCOUNTING_GATE'
recipe_gate_path=Path('research/raw_count_player_recipe_20261020/v1/HIGH_REVIEW.json');recipe_gate=json.loads(recipe_gate_path.read_text());assert recipe_gate['status'].startswith('FINAL_PASS')
manifest_path=GATE.with_name('MANIFEST.json');manifest=json.loads(manifest_path.read_text());ref=gate['prepared_refs'][a.grain]
raw=Path(ref['path']).read_bytes();assert len(raw)==ref['bytes']and hashlib.sha256(raw).hexdigest()==ref['sha256'];prepared=json.loads(raw)
assert prepared['prepared_sha256']==manifest['grains'][a.grain]['prepared_sha256']
recipe='adam_optimizer_repair_v1'if a.grain=='player'and a.family=='neural'else'lbfgs_v1'if a.family=='neural'else'fixed_hist_gradient_boosting_v1'
def save(value,kind,suffix='.json'):
 b=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()if suffix=='.json'else value
 sha=hashlib.sha256(b).hexdigest();path=Path('artifacts',kind,sha+suffix);path.parent.mkdir(exist_ok=True)
 if path.exists():assert path.read_bytes()==b
 else:
  with path.open('xb')as f:f.write(b)
  path.chmod(0o444)
 return dict(path=str(path.resolve()),sha256=sha,bytes=len(b))
def fail_timeout(*_):raise TimeoutError('Fixed300second cap exceeded; no automatic restart/grid')
started=datetime.now(UTC);timer=time.monotonic();signal.signal(signal.SIGALRM,fail_timeout);signal.alarm(300)
try:
 bundle=fit_team_family(prepared,family=a.family)if a.grain=='team'else fit_raw_player_family(prepared,family=a.family)
 signal.alarm(0)
except Exception as e:
 signal.alarm(0);out.write_text(json.dumps(dict(status='fit_failed',started_at=started.isoformat(),completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,error_type=type(e).__name__,error=str(e),recipe=recipe,prepared_ref=ref,retry=False),indent=2)+'\n');raise
receipt=bundle['receipt']
if receipt['status']!='fit_complete':
 stream=BytesIO();joblib.dump(dict(contract='offline_workload_direct_count_research_model_v1',bundle=bundle),stream,compress=3)
 result=dict(status=receipt['status'],grain=a.grain,family=a.family,receipt=receipt,prepared_ref=ref,model_ref=save(stream.getvalue(),'workload_direct_count_failed_models','.joblib'),started_at=started.isoformat(),completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,retry=False)
 out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps(result));raise SystemExit(2)
prediction_rows=[];evaluation={}
train=prepared['splits']['train'];targets=prepared['target_columns'];cols=prepared['preprocessing']['columns'];prep=prepared['preprocessing']
def labels(part):return part['labels']if a.grain=='player'else[dict(zip(targets,y))for y in part['y']]
train_labels=labels(train);train_means={t:float(np.mean([r[t]for r in train_labels if r[t]is not None]))for t in targets}
for split,part in prepared['splits'].items():
 if not part['x']:continue
 x=np.asarray(part['x'])
 if a.grain=='team':
  models=bundle['estimators'];z=np.column_stack([m.predict(x)for m in models])if a.family=='tree'else models.predict(x);raw_pred=np.asarray(z)*prep['target_scale']+prep['target_center'];assert np.isfinite(raw_pred).all();raw_pred={t:raw_pred[:,i]for i,t in enumerate(targets)};pred={t:np.maximum(0,v)for t,v in raw_pred.items()}
 else:
  arrays=predict_arrays(bundle,x);raw_pred={t:arrays[t]['raw']for t in targets if t in arrays};pred={t:arrays[t]['supported']for t in raw_pred}
 if set(pred)!=set(targets):continue
 ys=labels(part);evaluation[split]={}
 for t in targets:
  ids=[i for i,y in enumerate(ys)if y[t]is not None];actual=np.asarray([ys[i][t]for i in ids]);prediction=pred[t][ids];base=np.full(len(ids),train_means[t]);key=('pass_mean3'if t=='pass_attempts'else'rush_mean3')if a.grain=='team'else t+'_mean3';j=cols.index(key);hist=np.asarray(part['x'])[:,j]*prep['scale'][j]+prep['center'][j];known=np.asarray(part['x'])[:,len(cols)+j]==0;matched=[i for i in ids if known[i]]
  order=np.argsort(prediction,kind='stable');groups=np.array_split(order,min(10,len(order)))
  calibration=[dict(rows=len(g),predicted_mean=float(prediction[g].mean()),observed_mean=float(actual[g].mean()))for g in groups if len(g)]
  evaluation[split][t]=dict(rows=len(ids),model_mae=float(np.mean(abs(prediction-actual))),model_bias=float(np.mean(prediction-actual)),model_rmse=float(np.sqrt(np.mean((prediction-actual)**2))),train_only_constant=train_means[t],train_constant_mae=float(np.mean(abs(base-actual))),historical3_known_rows=len(matched),historical3_mae=float(np.mean([abs(hist[i]-ys[i][t])for i in matched]))if matched else None,descriptive_prediction_deciles=calibration,raw_metrics=count_metrics(actual,raw_pred[t][ids]),supported_metrics=count_metrics(actual,prediction),clipping_all_rows=dict(rows=int((raw_pred[t]<0).sum()),total_magnitude=float(np.maximum(0,-raw_pred[t]).sum()),maximum_magnitude=float(np.maximum(0,-raw_pred[t]).max())),calibration_scope='Observed point-mean diagnostic only; no probability/interval calibration or fresh outcome-blind test')
 for i,key in enumerate(part['keys']):prediction_rows.append(dict(split=split,**key,actual=ys[i],raw_predicted={t:float(raw_pred[t][i])for t in targets},predicted={t:float(pred[t][i])for t in targets}))
# Recorded-cohort accounting diagnostics retain incomplete player universe limits.
accounting={}
for split in evaluation:
 rows=[r for r in prediction_rows if r['split']==split];groups={}
 for r in rows:
  g=groups.setdefault((r['game_id'],r['team']),dict(actual=dict.fromkeys(targets,0),predicted=dict.fromkeys(targets,0.)))
  for t in targets:
   if r['actual'][t]is not None:g['actual'][t]+=r['actual'][t]
   g['predicted'][t]+=r['predicted'][t]
 accounting[split]=dict(game_sides=len(groups),mean_recorded_cohort_actual={t:float(np.mean([g['actual'][t]for g in groups.values()]))for t in targets},mean_recorded_cohort_predicted={t:float(np.mean([g['predicted'][t]for g in groups.values()]))for t in targets},negative_or_nonfinite=sum(not np.isfinite(v)or v<0 for r in rows for v in r['predicted'].values()),scope='Recorded canonical label cohort, not complete team/player opportunity reconciliation; no forced budget normalization or pass+target summation')
models=bundle['estimators'];actual_params={t:m.get_params()for t,m in models.items()}if isinstance(models,dict)else[m.get_params()for m in models]if isinstance(models,list)else models.get_params()
stream=BytesIO();joblib.dump(dict(contract='offline_workload_direct_count_research_model_v1',bundle=bundle),stream,compress=3)
result=dict(grain=a.grain,family=a.family,status=receipt['status'],recipe=recipe,recipe_parameters=actual_params,started_at=started.isoformat(),completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,hard_cap_seconds=300,gate_ref=dict(path=str(GATE.resolve()),sha256=hashlib.sha256(GATE.read_bytes()).hexdigest()),prepared_ref=ref,model_ref=save(stream.getvalue(),'workload_direct_count_models','.joblib'),prediction_ref=save(prediction_rows,'workload_direct_count_predictions'),receipt=receipt,evaluation=evaluation,accounting=accounting,feature_columns=cols,new_feature_columns=manifest['grains'][a.grain]['added_columns'],added_input_coverage=manifest['grains'][a.grain].get('added_coverage',manifest['grains'][a.grain].get('coverage')),outcomes_previously_inspected=True,original_pregame_backtest_eligible=False,incremental_feature_benefit='NOT_ISOLATED: inputs, direct-count target transform and some label scope changed together; saved-prior comparisons use identical known keys/new labels, no baseline retraining' ,recipe_gate_ref=dict(path=str(recipe_gate_path.resolve()),sha256=hashlib.sha256(recipe_gate_path.read_bytes()).hexdigest()),live_activation=False,settings_changes=0,lineup_changes=0)
out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps(dict(job=name,status=result['status'],elapsed_seconds=result['elapsed_seconds'],model_ref=result['model_ref'],evaluation={s:{t:{k:v for k,v in d.items()if k in('model_mae','model_bias','train_constant_mae','historical3_mae')}for t,d in heads.items()}for s,heads in evaluation.items()})),flush=True)
