from copy import deepcopy
from pathlib import Path
import json,hashlib
from backend.app.product_services.analyst_packets import load_packet
from backend.app.product_services.analyst_shadow import digest
from backend.app.product_services.scenario_allocation import AllocationControls,build_ideas,plan_slots,conditional_world
from backend.app.product_services.full_game_breadth import role_universe
P=Path(__file__).parent
c=next(x['constraint_config_json']for x in json.load(open('/private/tmp/sunday_actual_review_20261018/stored_run_configs.json'))if x['optimizer_run_id'].startswith('398efe88'))
original=deepcopy(c);a=c['strategy_runtime']['football_analyst'];p=load_packet(a['packet_sha256']);assert digest(p)==a['packet_sha256']
v2=json.load(open(P.parent/'v1/new_v2_evidence.json'));assert len(v2)==513
rows=deepcopy(a['input_snapshot']['players'])
for r in rows:r['player_id']=r['player_master_id']
controls=AllocationControls.model_validate(a['scenario_allocation_plan']['controls']);pool=c['strategy_runtime']['player_pool']['rows']
source_evidence={r['player_id']:r['workload_evidence'] for r in pool}
assert set(source_evidence)==set(v2)=={x['player_master_id']for x in p['players']}
# Keep original checked packet exactly, vary only evidence.
p1=deepcopy(p);p2=deepcopy(p)
# Source-parity assertion deliberately not relaxed into a claim: actual packet
# uses an independent raw-box derivation; v2 is a source-changing sensitivity.
for x in p2['players']:x['workload_evidence']=deepcopy(v2[x['player_master_id']])
results={}
for version,packet in [('v1',p1),('v2',p2)]:
 ideas,rejected=build_ideas(packet,rows,controls);plan=plan_slots(ideas,c['num_lineups'],controls)
 worlds={i['idea_id']:conditional_world(i,rows,packet,controls)for i in ideas}
 full=deepcopy(pool)
 for x in full:x['workload_evidence']=deepcopy((source_evidence if version=='v1'else v2)[x['player_id']])
 try:
  universe,audit=role_universe(full,rows)
  roles={str(k):[{'player_id':r['player_id'],'value':value,'basis':basis,'included':r['included']}for r,value,basis in values]for k,values in universe.items()}
  role_result={'status':'accepted','roles':roles,'audit':audit}
 except ValueError as e:role_result={'status':'abstained','reason':str(e)}
 candidates=[]
 for candidate in a['candidates']:
  ids=[r['player_master_id']for r in candidate['roster']]
  scores={key:sum(world['moments'][pid]['mean']+.35*(world['moments'][pid]['p90']-world['moments'][pid]['mean'])for pid in ids)for key,world in worlds.items()}
  candidates.append({'source_candidate_identity':{k:candidate[k]for k in ['candidate_id','variant_id','generation_order','allocation_slot','allocated_idea_id']if k in candidate},'roster':candidate['roster'],'scores':scores})
 results[version]={'ideas':ideas,'rejected':rejected,'plan':plan,'worlds':worlds,'role_transport':role_result,'fixed_original_candidates':candidates}
assert c==original
left=results['v1'];right=results['v2'];common=set(left['worlds'])&set(right['worlds']);changes=[]
for wid in sorted(common):
 l=left['worlds'][wid];r=right['worlds'][wid]
 changed=[pid for pid in l['moments']if abs(l['moments'][pid]['mean']-r['moments'][pid]['mean'])>1e-9]
 changes.append({'idea_id':wid,'changed_player_moments':len(changed),'max_abs_mean_change':max((abs(l['moments'][pid]['mean']-r['moments'][pid]['mean'])for pid in changed),default=0),'before_budget':l['opportunity_budget'],'after_budget':r['opportunity_budget']})
summary={'comparison_qualification':'Actual packet vs recovered-feature child is source-changing sensitivity, not isolated semantic A/B. Pool role transport is the direct semantic A/B.', 'protocol_sha256':hashlib.sha256((P/'PROTOCOL.md').read_bytes()).hexdigest(),'source_packet_sha256':digest(p),'source_config_sha256':digest(c),'actors':len(pool),'eligible':len(rows),'excluded':sum(not r['included']for r in pool),'missing_feature_actors_retained':228,'ideas_before':len(left['ideas']),'ideas_after':len(right['ideas']),'rejected_before':len(left['rejected']),'rejected_after':len(right['rejected']),'new_ideas':sorted(set(right['worlds'])-set(left['worlds'])),'removed_ideas':sorted(set(left['worlds'])-set(right['worlds'])),'plan_before':[s['idea_id']for s in left['plan']['slots']],'plan_after':[s['idea_id']for s in right['plan']['slots']],'changed_worlds':sum(x['changed_player_moments']>0 for x in changes),'common_worlds':len(common),'world_changes':changes,'role_transport_before':{k:v for k,v in left['role_transport'].items()if k!='roles'},'role_transport_after':{k:v for k,v in right['role_transport'].items()if k!='roles'},'fits':0,'solves':0,'outcomes_loaded':False,'legacy_source_unchanged':True,'new_selected_portfolio':False}
(P/'comparison.json').write_text(json.dumps(results,indent=2)+'\n');(P/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items()if k not in ['world_changes','role_transport_before','role_transport_after']},indent=2));print('role',summary['role_transport_before']['status'],summary['role_transport_after']['status']);print('reason',summary['role_transport_after'].get('reason'))
