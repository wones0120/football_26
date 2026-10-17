"""Read persisted UI run and compare exact baseline-mean controls without live writes."""
from pathlib import Path
from contextlib import redirect_stdout
from datetime import datetime,UTC
import json,urllib.request,hashlib
import pandas as pd
from backend.app.product_services.optimizer import OptimizerService,_json_safe
from backend.app.product_services.classic_highest_projection import solve
P=Path(__file__).resolve().parent;run_id='fa65082d-ca23-45e0-9edf-b45b79de86e5';job=OptimizerService().get_job(run_id)
assert job is not None and job.status=='completed' and len(job.results)==1
assert job.params['entry_readiness']['entry_ready'] is False
assert job.params.get('gpp_recommendation') is None
report=job.params['strategy_runtime']['highest_projection'];assert report['locked_player_ids']==[] and report['solver_status']=='Optimal'
(P/'ui_saved_run.json').write_text(json.dumps(_json_safe(dict(job_id=run_id,status=job.status,message=job.message,params=job.params,results=job.results,observed_at=datetime.now(UTC).isoformat())),indent=2,allow_nan=False)+'\n')
with urllib.request.urlopen('http://127.0.0.1:8000/api/optimizer/results/'+run_id) as handle:response=json.load(handle)
assert response['highest_projection']['solver_status']=='Optimal' and response['entry_readiness']['entry_ready'] is False
(P/'ui_api_response.json').write_text(json.dumps(response,indent=2)+'\n')
svc=OptimizerService.__new__(OptimizerService);pool=pd.DataFrame(report['input_snapshot']['players']);core={'a7d14336-632e-48c8-b0c1-45916b8476e4','319a7e5c-7967-4405-90f9-36ddfea66dfd'};stafford='30cb73fd-8a62-419b-bcdd-1f505531caeb';arms={}
with (P/'ui_comparisons.log').open('w') as log,redirect_stdout(log):
 for label,locks,excluded in [('unlocked_replay',set(),set()),('puka_kyren_locked',core,set()),('stafford_puka_kyren_locked',core|{stafford},set()),('stafford_required',{stafford},set()),('best_non_stafford',set(),{stafford})]:
  lineups,audit=solve(svc,pool,params=job.params,cutoff=job.data_cutoff_at,locked_ids=locks,excluded_qb_ids=excluded)
  assert audit['solver_status']=='Optimal';arms[label]=_json_safe(dict(lineups=lineups,audit=audit))
assert arms['unlocked_replay']['audit']['input_snapshot_sha256']==report['input_snapshot_sha256']
(P/'ui_matched_comparisons.json').write_text(json.dumps(arms,indent=2,allow_nan=False)+'\n')
def numeric_signature(rows):return sorted((r['player_id'],r['salary'],r['projection'],r['position'],r['player_team'],r.get('opponent_team')) for r in rows)
initial=json.loads((P/'saved_run.json').read_text());assert numeric_signature(initial['params']['strategy_runtime']['highest_projection']['input_snapshot']['players'])==numeric_signature(report['input_snapshot']['players'])
verification=dict(ui_run_id=run_id,preliminary_snapshot=job.params['preliminary_report']['snapshot_sha256'],projection_run_id=job.projection_run_id,ownership_run_id=job.params['ownership_run_id'],eligible_player_count=report['eligible_player_count'],numerical_pool_matches_initial_build=True,initial_local_saved_run_id=initial['job_id'],ui_saved_and_api_reopened=True,entry_ready=False,objective='sum unchanged baseline means',solver_status='Optimal',locks=[],hard_qb_stack=False,mandatory_bringback=False,generated_scenario_constraints=False,api_runtime_report=bool(response.get('highest_projection')),gpp_recommendation=None,stafford_gap=report['base_mean']-arms['best_non_stafford']['audit']['base_mean'])
(P/'verification.json').write_text(json.dumps(verification,indent=2)+'\n');print(json.dumps(verification,indent=2),flush=True)
