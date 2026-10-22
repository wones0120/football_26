from datetime import UTC,datetime
import hashlib,json,os,time
from pathlib import Path
from collections import Counter
from backend.app.db import engine
from backend.app.product_services.workload_count_forecast import load_history
from backend.app.product_services.player_opportunity_sources import load_component_sources
from backend.app.product_services.offensive_volume_features import build_player_matrix,digest
from backend.app.product_services.feature_block_model_inputs import prepare_player_inputs
ROOT=Path('research/player_opportunity_models_20261020/v1');DEST=Path('artifacts/player_opportunity_matrices');DEST.mkdir(parents=True,exist_ok=True)
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest();p=DEST/(sha+'.json')
 if not p.exists():p.write_bytes(raw)
 elif p.read_bytes()!=raw:raise ValueError('Immutable matrix collision')
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
def progress(stage,**kw):
 x=dict(actual_at=datetime.now(UTC).isoformat(),stage=stage,**kw);(ROOT/'actual_progress.json').write_text(json.dumps(x,indent=2));print(json.dumps(x),flush=True)
start=time.monotonic();cutoff=datetime.now(UTC);before=202606
progress('source_reads')
hist=json.load(open('research/player_opportunity_history_20261020/v1/actual_history_derivation_receipt.json'))
current=json.load(open('research/player_opportunity_components_20261019/v1/actual_derivation_current_receipt.json'))
refs=[v['managed_ref'] for v in hist['outputs']]+[current['full_ref']]
components=load_component_sources(refs,cutoff=cutoff)
weekly=load_history(engine,season=2026,week=6,cutoff=cutoff)
sourcejob=json.load(open('research/opportunity_component_response_20261019/v1/fullshape_retry_prepare_job.json'))
frozen=sourcejob['result'];counts=frozen['workload_forecast'];actors=[r for r in counts['players'] if r.get('native_salary_actor')]
tmref=json.load(open('research/team_opportunity_forecast_20261019/v1/actual_matrix_receipt.json'))['matrix_ref'];raw=Path(tmref['path']).read_bytes()
if len(raw)!=tmref['bytes'] or hashlib.sha256(raw).hexdigest()!=tmref['sha256']:raise ValueError('Frozen team matrix byte proof failed')
teams=json.loads(raw);fresh={tuple((r['team'],r['period'])):r for r in counts['team_opportunity_model_inference']['inference_rows']}
teams['rows']=[fresh.get((r['team'],r['period']),r) for r in teams['rows']]
teams['matrix_sha256']=digest({k:v for k,v in teams.items() if k not in {'matrix_sha256','provenance'}})
progress('building_matrix',weekly_rows=len(weekly),source_actor_games=len(components['actor_game_rows']),forward_actors=len(actors))
matrix=build_player_matrix(weekly,components,before_period=before,cutoff=cutoff,actors=actors,team_matrix=teams)
progress('preprocessing',matrix_rows=len(matrix['rows']),columns=len(matrix['feature_columns']))
prepared=prepare_player_inputs(matrix,train_before=202401,validation_before=202501)
mr=save(matrix);pr=save(prepared)
cohorts={}
for split,part in prepared['splits'].items():
 c={}
 for key,labels in zip(part['keys'],part['labels']):
  for target,value in labels.items():
   group=f"{key['period']//100}:{key['position']}:{target}";row=c.setdefault(group,dict(rows=0,known_labels=0,zero_labels=0));row['rows']+=1;row['known_labels']+=value is not None;row['zero_labels']+=value==0 if value is not None else 0
 cohorts[split]=c
receipt=dict(status='actual_frozen_player_matrix_not_fit_or_served',actual_cutoff_at=cutoff.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),
 elapsed_seconds=time.monotonic()-start,matrix_ref=mr,prepared_ref=pr,matrix_sha256=matrix['matrix_sha256'],prepared_sha256=prepared['prepared_sha256'],
 feature_columns=matrix['feature_columns'],target_columns=matrix['target_columns'],source_refs=refs,frozen_team_matrix_ref=tmref,
 forward_team_rows='Exact immutable f963 issued features (52.5 total), replacing earlier51.5 frozen forward rows only; historical rows unchanged',
 forward_source_job_id=sourcejob['job_id'],forward_source_cutoff=frozen['data_cutoff_at'],forward_actors=len(actors),
 matrix_rows=len(matrix['rows']),split_rows={k:len(v['keys']) for k,v in prepared['splits'].items()},cohorts=cohorts,
 entirely_missing_train_columns=prepared['preprocessing']['entirely_missing_train_columns'],
 chronology='Offline postlock revised-history matrix; no current Monday preparation/entry-ready claim. Historical original pregame availability unproven.')
(ROOT/'actual_matrix_receipt.json').write_text(json.dumps(receipt,indent=2));progress('matrix_complete',elapsed_seconds=receipt['elapsed_seconds'],matrix_ref=mr,prepared_ref=pr,split_rows=receipt['split_rows'],entirely_missing_columns=len(receipt['entirely_missing_train_columns']))
