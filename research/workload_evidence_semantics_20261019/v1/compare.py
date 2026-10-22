from pathlib import Path
from copy import deepcopy
from datetime import datetime
import json,hashlib,collections
from backend.app.product_services.workload_evidence import build_workload_evidence,select_measurement
from backend.app.product_services.scenario_allocation import measurement,role_measurement
P=Path(__file__).parent;source=Path('/private/tmp/sunday_actual_review_20261018/stored_run_configs.json');config=next(r for r in json.load(open(source))if r['optimizer_run_id'].startswith('398efe88'))['constraint_config_json'];audit=config['strategy_runtime']['player_pool']['rows'];original=deepcopy(config);features=json.load(open(P/'recovered_original_feature_fields.json'));byid={r['player_id']:r for r in features['rows']};assert len(byid)==len(features['rows']);decision=datetime.fromisoformat(features['decision_at']);eligible={r['player_id']for r in config['strategy_runtime']['classic_run_input_snapshot']['payload']['final_solver_rows']};assert eligible<=set(byid)
rows=[];packets={};counts=collections.Counter();conflicts=[]
for r in audit:
 pid=r['player_id'];old=r.get('workload_evidence')or{};f=byid.get(pid)
 if f:
  assert datetime.fromisoformat(f['feature_created'])<decision
 facts={**(f or{}),'workload_feature_run_id':(f or{}).get('feature_run_id')or old.get('lineage',{}).get('workload_feature_run_id'),'workload_feature_cutoff_at':old.get('lineage',{}).get('workload_feature_cutoff_at')}
 new=build_workload_evidence({**r,'workload_feature_evidence':facts},projection_run_id=features['projection_run_id'],cutoff=old.get('lineage',{}).get('evidence_cutoff_at'))
 packets[pid]=new
 for channel in ['targets','carries']:
  before,before_basis=measurement({'workload_evidence':old},channel);after,basis=measurement({'workload_evidence':new},channel);role,brole=role_measurement({'workload_evidence':new},channel)
  old_hist=old.get('historical',{}).get(channel+'_mean_3',{}).get('value');new_hist=new['historical'][channel+'_mean_3']['value']
  if f and old_hist is not None and f.get(channel+'_mean_3')is not None and abs(old_hist-f[channel+'_mean_3'])>1e-6:conflicts.append(dict(player_id=pid,channel=channel,old=old_hist,recovered=f[channel+'_mean_3']))
  counts['channels']+=1;counts['new_history_known']+=new_hist is not None;counts['old_history_known']+=old_hist is not None;counts['changed_history']+=old_hist!=new_hist;counts['changed_selected_measurement']+=before!=after;counts['new_role_unknown']+=role is None
  rows.append(dict(player_id=pid,name=r['player_name'],position=r['position'],included=r['included'],channel=channel,recovered=f is not None,old_value=before,old_basis=before_basis,new_value=after,new_basis=basis,new_role_value=role,new_role_basis=brole,old_history=old_hist,new_history=new_hist,new_history_status=new['historical'][channel+'_mean_3']['status'],original_projection=r['projection'],p90=r['p90'],exclusion_reasons=r.get('exclusion_reasons',[])))
assert config==original
out=dict(contract='workload_semantics_comparison_v1',source_run_id=features['source_run_id'],source_packet_contract='workload_evidence_v1',new_contract='workload_evidence_v2',source_config_sha256=features['source_config_sha256'],feature_capture_sha256=hashlib.sha256((P/'recovered_original_feature_fields.json').read_bytes()).hexdigest(),protocol_sha256=hashlib.sha256((P/'PROTOCOL.md').read_bytes()).hexdigest(),actors=len(audit),eligible=len(eligible),excluded=sum(not r['included']for r in audit),recovered_feature_actors=len(byid),missing_feature_actors=sum(r['player_id']not in byid for r in audit),all_eligible_features_present=True,legacy_source_unchanged=True,model_moments_and_preferences_unchanged=True,counts=dict(counts),recovered_vs_legacy_conflicts=conflicts,rows=rows,outcomes_used=False,new_fit=False,new_solve=False,live_promoted=False,qualification='New research child rebuilt from existing feature rows capturednow; not a backfilled original packet or independently source-certified pregame replay.')
(P/'comparison.json').write_text(json.dumps(out,indent=2));(P/'new_v2_evidence.json').write_text(json.dumps(packets,indent=2));print({k:v for k,v in out.items()if k not in['rows']});changes=[r for r in rows if r['old_history']is not None and r['new_history']is not None and r['position']in['RB','WR','TE']];changes.sort(key=lambda r:abs(r['old_history']-r['new_history']),reverse=True)
print('largest descriptive mapping changes',[(r['name'],r['channel'],r['old_history'],r['new_history'],r['included'])for r in changes[:8]])
