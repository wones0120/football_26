"""Authorized saved preliminary highest-mean run plus isolated matched controls."""
from copy import deepcopy
from pathlib import Path
from contextlib import redirect_stdout
import json,uuid
from datetime import datetime,UTC
import pandas as pd
from backend.app.product_services.preliminary_optimizer import PreliminaryOptimizerRequest,run_preliminary
from backend.app.product_services.optimizer import OptimizerService,_json_safe
from backend.app.product_services.classic_highest_projection import solve
P=Path(__file__).resolve().parent
source=Path('research/sunday_refresh_20261015/normal_submitted_request.json');request=json.loads(source.read_text());run_id=str(uuid.uuid4());request['optimizer']['optimizer_run_id']=run_id;request['optimizer']['params'].update(classic_selection_objective='baseline_mean',locked_player_ids=[],locked_players=[],num_lineups=1)
(P/'submitted_request.json').write_text(json.dumps(request,indent=2)+'\n')
with (P/'generation.log').open('w') as handle,redirect_stdout(handle):
    job=run_preliminary(PreliminaryOptimizerRequest.model_validate(request),run_id=run_id)
result=_json_safe(dict(job_id=job.job_id,status=job.status,message=job.message,projection_run_id=job.projection_run_id,params=job.params,results=job.results,lineage_persisted=job.lineage_persisted,observed_at=datetime.now(UTC).isoformat()))
(P/'saved_run.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print('saved',job.job_id,job.status,job.message,flush=True)
assert job.status=='completed' and job.lineage_persisted and len(job.results)==1
report=job.params['strategy_runtime']['highest_projection'];pool=pd.DataFrame(report['input_snapshot']['players']);svc=OptimizerService.__new__(OptimizerService);params=job.params;arms={}
core={'a7d14336-632e-48c8-b0c1-45916b8476e4','319a7e5c-7967-4405-90f9-36ddfea66dfd'};stafford='30cb73fd-8a62-419b-bcdd-1f505531caeb'
with (P/'comparisons.log').open('w') as handle,redirect_stdout(handle):
 for label,locks,blocked in [('unlocked_replay',set(),set()),('puka_kyren_locked',core,set()),('stafford_puka_kyren_locked',core|{stafford},set()),('stafford_required',{stafford},set()),('best_non_stafford',set(),{stafford})]:
  lineups,audit=solve(svc,pool,params=params,cutoff=job.data_cutoff_at,locked_ids=locks,excluded_qb_ids=blocked)
  arms[label]=_json_safe(dict(lineups=lineups,audit=audit))
assert arms['unlocked_replay']['audit']['input_snapshot_sha256']==report['input_snapshot_sha256']
(P/'matched_comparisons.json').write_text(json.dumps(arms,indent=2,allow_nan=False)+'\n')
for label,arm in arms.items():print(label,arm['audit']['solver_status'],round(arm['audit'].get('base_mean',0),3),[(p['name'],p['salary']) for p in arm['lineups'][0]],flush=True)
# Reopen through a fresh service so persisted rows, not the in-process cache, establish success.
reopened=OptimizerService().get_job(run_id);assert reopened is not None and reopened.status=='completed';assert {p['player_id'] for p in reopened.results[0]}=={p['player_id'] for p in job.results[0]};assert reopened.params['strategy_runtime']['highest_projection']['locked_player_ids']==[]
(P/'reopened_run.json').write_text(json.dumps(_json_safe(dict(job_id=reopened.job_id,status=reopened.status,message=reopened.message,params=reopened.params,results=reopened.results)),indent=2,allow_nan=False)+'\n');print('reopened persisted',run_id,flush=True)
