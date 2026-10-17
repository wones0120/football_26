from pathlib import Path
from copy import deepcopy
from datetime import datetime
import json,importlib.util,hashlib,uuid
import pandas as pd
from sqlalchemy import create_engine
from backend.app.product_services.optimizer import OptimizerService,_json_safe
from backend.app.product_services.model_artifacts import load_run_artifact
P=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('dst_counterfactual',Path('research/dst_production_rollout_20261016/v1/counterfactual.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
snapshot_response=json.loads((P/'snapshot_response.json').read_text());snapshot=json.loads((Path('artifacts/preliminary_optimizer_snapshots')/(snapshot_response['snapshot_sha256']+'.json')).read_text());request=json.loads((P/'submitted_request.json').read_text())['optimizer'];params=deepcopy(request['params']);params['ownership_run_id']=snapshot['ownership_run_id'];params['exclude_player_ids']=sorted(set(params.get('exclude_player_ids',[]))|set(snapshot['assumption_manifest']['exclude_player_ids']))
actual_params=json.loads((P/'saved_run.json').read_text())['params']
for key in ('analyst_discovery_enabled','analyst_teammate_enabled','analyst_challenger_enabled'):
 if key in actual_params:params[key]=actual_params[key]
base=OptimizerService();readonly=create_engine(base.connection_string,connect_args={'options':'-c default_transaction_read_only=on'})
with readonly.connect() as c:
 payload,metadata=load_run_artifact(c,snapshot['projection_run_id'])
 legacy=module.incumbent_dst_counterfactual(payload)
(P/'incumbent_dst_same_inputs.json').write_text(json.dumps(_json_safe(legacy.to_dict('records')),indent=2)+'\n')
byid={r['player_id']:r for r in legacy.to_dict('records')};original=deepcopy(snapshot['pool']);new=deepcopy(original);changed=[]
fields=['projection','mean','predicted_mean','adj_mean','p90','predicted_p10','predicted_p25','predicted_p50','predicted_p75','predicted_p90','calibration_method','calibration_sample_size']
for row in new:
 if row['position']!='DST':continue
 other=byid[row['player_id']];changed.append(dict(player_id=row['player_id'],team=row['player_team'],salary=row['salary'],ensemble_mean=row['projection'],incumbent_mean=other['projection']))
 for key in fields:
  if key in row and key in other:row[key]=other[key]
# All original non-DST cells and every roster-eligibility/source/preference cell remain fixed.
assert [r for r in original if r['position']!='DST']==[r for r in new if r['position']!='DST']
(P/'dst_mean_comparison.json').write_text(json.dumps(changed,indent=2)+'\n')
class LocalResearchService(OptimizerService):
 def __init__(self,rows):
  super().__init__(base.connection_string);self.engine=readonly;self.rows=rows
 def _load_player_pool(self,*args,**kwargs):
  frame=pd.DataFrame(deepcopy(self.rows));frame.attrs=deepcopy(snapshot['pool_attrs']);return frame
 def _persist_optimizer_run(self,job):
  # This is a local research artifact receipt, never a target.optimizer_run row.
  output=_json_safe(vars(job));output['database_persisted']=False;output['local_comparison_only']=True
  (P/(self.arm+'_local_run.json')).write_text(json.dumps(output,indent=2)+'\n');return True
for arm,rows in [('ensemble_replay',original),('incumbent_counterfactual',new),('fresh_highest_baseline_reference',original)]:
 svc=LocalResearchService(rows);svc.arm=arm
 arm_params=deepcopy(params)
 if arm=='fresh_highest_baseline_reference':
  arm_params.update(num_lineups=1,max_exposure=1,classic_selection_objective='baseline_mean',analyst_handoff_mode='BASELINE')
  for key in ['analyst_packet_sha256','analyst_strategy','analyst_candidates_per_thesis','analyst_portfolio_mode','analyst_handoff_compatibility_sha256']:arm_params.pop(key,None)
 job=svc.run_job(2026,6,'SUNDAY_MAIN','classic_large_gpp_v1',arm_params,contest_format='classic',objective='gpp',projection_run_id=snapshot['projection_run_id'],data_cutoff_at=datetime.fromisoformat(snapshot['data_cutoff_at']),allow_incomplete_evidence=True)
 out=_json_safe(vars(job));out.update(database_persisted=False,local_comparison_only=True,comparison_arm=arm,component_intervention='unchanged accepted ensemble' if arm!='incumbent_counterfactual' else 'only DST mean/quantile cells swapped to same-input legacy counterfactual',snapshot_sha256=snapshot['sha256']);(P/(arm+'_local_run.json')).write_text(json.dumps(out,indent=2)+'\n');print(arm,job.status,len(job.results or []),job.message,flush=True)
(P/'counterfactual_manifest.json').write_text(json.dumps(dict(kind='matched_generation_experiment_not_same_candidate_pool_selector_test',projection_run_id=snapshot['projection_run_id'],model_run_id=metadata['model_run_id'],artifact_sha256=metadata['artifact_sha256'],all_non_dst_cells_exact=True,eligibility_settings_packet_seed_held_fixed=True,database_writes=False,source_snapshot_sha256=snapshot['sha256']),indent=2)+'\n')
