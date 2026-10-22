from datetime import UTC,datetime
import json,hashlib,time
from pathlib import Path
from backend.app.product_services.player_opportunity_serving import infer_player_counts
from backend.app.product_services.count_scenario_response import count_world
R=Path('research/player_opportunity_models_20261020/v1');start=time.monotonic()
r=json.loads((R/'actual_adam_fit_receipt.json').read_text());mref=json.loads((R/'corrected_preprocessing_receipt.json').read_text())['matrix_ref'];raw=Path(mref['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==mref['sha256'];m=json.loads(raw);del raw
source=json.loads(Path('research/opportunity_component_response_20261019/v1/fullshape_retry_prepare_job.json').read_text())['result'];old=source['workload_forecast'];now=datetime.now(UTC)
new=infer_player_counts(r['result_ref']['sha256'],m,old,cutoff=now,purpose='offline_retrospective_evaluation')
D=Path('artifacts/player_opportunity_evaluations');D.mkdir(exist_ok=True)
def freeze(v):
 raw=json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest();p=D/(sha+'.json')
 if p.exists():assert p.read_bytes()==raw
 else:p.write_bytes(raw)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
ref=freeze(new);before={r['player_master_id']:r for r in old['players']};changes=[]
for actor in new['counts']['players']:
 prior=before[actor['player_master_id']];changes.append(dict(player_master_id=actor['player_master_id'],native_salary_actor=actor.get('native_salary_actor'),team=actor['team'],position=actor['position'],old_counts=prior['counts'],new_counts=actor['counts'],world_activity=actor.get('world_activity')))
receipt=dict(status='actual_model_to_count_and_component_offline_not_pregame',actual_at=now.isoformat(),elapsed_seconds=time.monotonic()-start,evaluation_ref=ref,model_result_ref=r['result_ref'],source_preparation_job_id='f9639e11-8b21-48ca-82ac-f80a67bbdf78',actors=len(changes),predicted_actors=len(new['predictions']),changes=changes,component_deltas=new['counts']['component_response']['players'],team_budgets=new['counts']['teams'],entry_ready=False)
(R/'actual_count_component_receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps({k:v for k,v in receipt.items() if k not in {'changes','component_deltas','team_budgets'}}),flush=True)
