"""One serial cached adapter+train-only preparation pass, never fits."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time,gc
from backend.app.product_services.scheduled_pressure_model_inputs import build_contexts,append_pressure_context
from backend.app.product_services.team_opportunity_models import prepare_model_inputs
from backend.app.product_services.feature_block_model_inputs import prepare_player_inputs
from backend.app.product_services.model_input_admission import cohort_manifest
from backend.app.product_services.evaluation_record import digest
ROOT=Path('research/scheduled_pressure_model_inputs_20261020/v1')
if(ROOT/'MANIFEST.json').exists():raise ValueError('Frozen output exists; no overwrite')
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p.resolve()),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
def load(r,cap):
 if r['bytes']>cap:raise ValueError('Bounded cache size exceeded')
 b=Path(r['path']).read_bytes()
 if len(b)!=r['bytes']or hashlib.sha256(b).hexdigest()!=r['sha256']:raise ValueError('Immutable parent bytes differ')
 return json.loads(b)
def save(value,kind):
 b=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(b).hexdigest();p=Path('artifacts',kind,sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==b
 else:
  with p.open('xb')as f:f.write(b)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(b))
started=datetime.now(UTC);timer=time.monotonic()
base_path=Path('research/reconstructed_model_input_manifest_20261020/v1/MANIFEST.json');base=json.loads(base_path.read_text())
pr=json.loads(Path('research/pfr_pressure_cohort_20261020/v1/actual_receipt.json').read_text())['full_ref']
sr=json.loads(Path('research/schedule_context_features_20261020/v1/actual_receipt.json').read_text())['artifact_ref']
pressure=load(pr,3*1024*1024);schedule=load(sr,9*1024*1024)
assert digest({k:v for k,v in pressure.items()if k not in{'semantic_sha256','provenance'}})==pressure['semantic_sha256']
assert digest(dict(version=schedule['version'],game_rows=[{k:v for k,v in r.items()if k!='source_row'}for r in schedule['game_rows']]))==schedule['semantic_sha256']
contexts=build_contexts(pressure,[r for r in schedule['game_rows']if 2023<=r['season']<=2026]);context_ref=save(contexts,'scheduled_pressure_model_contexts');del pressure,schedule;gc.collect()
parents=dict(pressure_catalog=pr,native_schedule=sr,context=context_ref)
outputs={}
for grain in('team','player'):
 b=base['grains'][grain];matrix=load(b['matrix_ref'],220*1024*1024);extended=append_pressure_context(matrix,contexts,grain=grain,parent_refs=parents)
 prepared=(prepare_model_inputs if grain=='team'else prepare_player_inputs)(extended,train_before=202401,validation_before=202501)
 cohorts=cohort_manifest(prepared,grain=grain)
 assert cohorts==b['cohorts'],'Known label cohorts must match baseline exactly'
 cols=extended['feature_columns'][-10:];coverage={}
 for split,part in prepared['splits'].items():
  keys={(k['game_id'],k['team'])for k in part['keys']};selected=[r for r in extended['rows']if(r['game_id'],r['team'])in keys]
  coverage[split]={k:sum(x[len(prepared['preprocessing']['columns'])+prepared['preprocessing']['columns'].index(k)]==0 for x in part['x'])for k in cols}
  if split=='train':assert all(coverage[split][k]>0 for k in cols),'New train columns need actual supported values'
 outputs[grain]=dict(matrix_ref=save(extended,'scheduled_pressure_model_matrices'),matrix_sha256=extended['matrix_sha256'],prepared_ref=save(prepared,'scheduled_pressure_model_prepared'),prepared_sha256=prepared['prepared_sha256'],consumer_version=prepared['version'],ordered_columns=extended['feature_columns'],added_columns=cols,added_coverage=coverage,cohorts=cohorts,preprocessing=prepared['preprocessing'],baseline_matrix_ref=b['matrix_ref'],baseline_prepared_ref=b['prepared_ref'],source_refs=parents)
 print(json.dumps(dict(grain=grain,columns=len(extended['feature_columns']),coverage=coverage,stage='END')),flush=True)
 del matrix,extended,prepared;gc.collect()
files=['backend/app/product_services/scheduled_pressure_model_inputs.py','backend/app/product_services/team_opportunity_models.py','backend/app/product_services/feature_block_model_inputs.py']
manifest=dict(version='scheduled_pressure_model_manifest_v1',actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,baseline_manifest_ref=ref(base_path),source_refs=parents,producer_refs=[ref(p)for p in files],grains=outputs,original_pregame_backtest_eligible=False,outcomes_previously_inspected=True,new_catalog_consumption=['G13-M03 compatible per-game HHS/nonspike DB own-offense exact3 prior scheduled context','G14-M01 compatible per-game HHS/nonspike DB opposing-defense exact3 prior scheduled context'],feature_counts_unchanged=244,all244_consumed=False,source_adapters_replayed=0,source_fetches=0,database_reads=0,fits=0,activation=False)
(ROOT/'MANIFEST.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
print(json.dumps(dict(stage='MANIFEST_END',elapsed=manifest['elapsed_seconds'],fits=0)),flush=True)
