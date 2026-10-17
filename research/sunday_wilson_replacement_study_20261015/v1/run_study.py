"""Read-only frozen-model full-roster generation experiment; writes this version's research only."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,UTC
import json,hashlib,collections,time
import pulp
from backend.app.product_services.scenario_allocation import apply_idea,audit_construction,AllocationControls
from backend.app.product_services.cbc_solver import make_cbc_solver
ROOT=Path('research/sunday_refresh_20261015');OUT=Path(__file__).resolve().parent
source=ROOT/'normal_saved_result.json';data=json.loads(source.read_text());cfg=data['run']['constraint_config_json'];report=cfg['strategy_runtime']['football_analyst'];snapshot=report['input_snapshot'];pool={p['player_id']:p for p in snapshot['players']};mapping=snapshot['variable_players'];pidvar={r['player_master_id']:n for n,r in mapping.items()};baseline=data['lineups'][0];baseline_ids={p['player_id'] for p in baseline};world=next(x for x in report['scenario_definitions'] if x['scenario_id']=='2026_06_ARI_LA:LAR:passing');mom=world['moments'];idea=next(x for x in report['scenario_allocation_plan']['ideas'] if x['idea_id']==world['scenario_id']);controls=AllocationControls.model_validate(report['scenario_allocation_plan']['controls']);locked={'30cb73fd-8a62-419b-bcdd-1f505531caeb','a7d14336-632e-48c8-b0c1-45916b8476e4','319a7e5c-7967-4405-90f9-36ddfea66dfd'};wilson='d0ae658e-ab5e-49ad-bec3-5ae2c19867f1'
# Candidate selection names identify explicit pool rows; all solving/joining below uses canonical UUID.
labels=['Germie Bernard','Makai Lemon','Xavier Worthy','Keon Coleman','Chris Godwin Jr.','DK Metcalf','Davante Adams','Malik Nabers','Devaughn Vele',"Wan'Dale Robinson",'Kendrick Bourne','Laquon Treadwell']
chosen={p['name']:p['player_id'] for p in pool.values() if p['name'] in labels};assert len(chosen)==len(labels)
usage={p['player_master_id']:p for p in json.loads((ROOT/'v1/usage_summary.json').read_text())};runs=[]
def score(ids):
 return dict(salary=sum(pool[p]['salary'] for p in ids),base_mean=sum(pool[p]['projection'] for p in ids),conditional_mean=sum(mom[p]['mean'] for p in ids),conditional_objective=sum(mom[p]['mean']+.35*(mom[p]['p90']-mom[p]['mean']) for p in ids))
bs=score(baseline_ids);assert abs(bs['conditional_objective']-report['candidates'][0]['scores'][world['scenario_id']])<1e-8

def solve(label,mode,required=None,keep=False,exact=False):
 start=time.monotonic();variables,model=pulp.LpProblem.fromDict(deepcopy(snapshot['model']));v={pid:variables[name] for pid,name in pidvar.items()};usedidea=deepcopy(idea)
 if mode=='optional_ari_response':usedidea['bringback_required']=False
 apply_idea(model,variables,mapping,list(pool.values()),usedidea,controls)
 for pid in locked:model+=v[pid]==1,'review_lock_'+pid
 if keep:model+=v[wilson]==1,'keep_wilson'
 elif not exact:model+=v[wilson]==0,'exclude_wilson'
 if required:model+=v[required]==1,'required_replacement'
 if exact:
  for pid in baseline_ids:model+=v[pid]==1,'exact_baseline_'+pid
 model.setObjective(pulp.lpSum((mom[p]['mean']+.35*(mom[p]['p90']-mom[p]['mean']))*var for p,var in v.items()))
 solver=make_cbc_solver();solver.msg=False;solver.timeLimit=12;solver.options.extend(['randomSeed 7','randomCbcSeed 7']);status=model.solve(solver);result=dict(label=label,arm=mode,required_replacement_id=required,solver_status=pulp.LpStatus[status],solution_status=pulp.LpSolution.get(model.sol_status),elapsed_seconds=time.monotonic()-start,objective_definition='sum frozen LAR-passing mean +0.35*(p90-mean); no scoring changes',constraints_relaxed=mode=='optional_ari_response',constraint_relaxation_scope='generated ARI-response scenario constraint only' if mode=='optional_ari_response' else None,user_constraints_relaxed=False,user_constraints_unchanged=True,scenario_bringback_required=usedidea['bringback_required'])
 if status==pulp.LpStatusOptimal:
  ids={pid for pid,var in v.items() if pulp.value(var)>.5};assert locked<=ids;assert exact or (wilson in ids)==keep;assert len(ids)==9
  positions=collections.Counter(pool[p]['position'] for p in ids);assert positions['QB']==1 and positions['TE']==1 and positions['DST']==1 and positions['RB']>=2 and positions['WR']>=3 and positions['RB']+positions['WR']==6
  assert sum(pool[p]['salary'] for p in ids)<=50000;assert max(collections.Counter(pool[p]['player_team'] for p in ids).values())<=4;assert max(collections.Counter(pool[p]['canonical_game_id'] for p in ids).values())<=5
  for pid in ids:
   p=pool[pid];assert pid not in cfg['exclude_player_ids'];assert p['position'] not in ['QB','RB'] or p['salary']>=4500
   if p['position']=='DST':assert not any(pool[q]['position']!='DST' and pool[q]['player_team']==p['opponent_team'] for q in ids)
  audit=audit_construction(ids,list(pool.values()),usedidea,controls);assert audit['passed'];metrics=score(ids);removed=baseline_ids-ids;added=ids-baseline_ids
  result.update(**metrics,delta_saved_baseline={k:metrics[k]-bs[k] for k in ['salary','base_mean','conditional_mean','conditional_objective']},canonical_roster_sha256=hashlib.sha256('|'.join(sorted(ids)).encode()).hexdigest(),player_ids=sorted(ids),construction_audit=audit,removed=[dict(id=p,name=pool[p]['name'],salary=pool[p]['salary']) for p in sorted(removed)],added=[dict(id=p,name=pool[p]['name'],salary=pool[p]['salary']) for p in sorted(added)],unused_salary=50000-metrics['salary'],ari_receivers=[pool[p]['name'] for p in ids if pool[p]['player_team']=='ARI' and pool[p]['position'] in ['WR','TE']],game_salary={g:sum(pool[p]['salary'] for p in ids if pool[p]['canonical_game_id']==g) for g in sorted({pool[p]['canonical_game_id'] for p in ids})},players=[dict(player_master_id=p,dk_native_id=pool[p]['dk_player_id'],name=pool[p]['name'],team=pool[p]['player_team'],position=pool[p]['position'],salary=pool[p]['salary'],base_mean=pool[p]['projection'],conditional_mean=mom[p]['mean'],conditional_p90=mom[p]['p90'],observed_usage=usage.get(p)) for p in sorted(ids)])
  if required and required not in baseline_ids:
   released=pool[wilson]['salary']-pool[required]['salary'];other_removed=sum(pool[p]['salary'] for p in removed if p!=wilson);other_added=sum(pool[p]['salary'] for p in added if p!=required);assert released==other_added-other_removed+result['unused_salary'];result['salary_flow']=dict(wilson_salary=6700,replacement_salary=pool[required]['salary'],released=released,other_removed_salary=other_removed,other_added_salary=other_added,net_reinvested=other_added-other_removed,unspent=result['unused_salary'])
 runs.append(result);print(label,mode,result['solver_status'],round(result.get('base_mean',0),2),round(result.get('conditional_objective',0),2),flush=True)
 (OUT/'progress.json').write_text(json.dumps(runs,indent=2)+'\n')
solve('exact_saved_baseline','required_ari_response',exact=True)
for mode in ['required_ari_response','optional_ari_response']:
 solve('optimized_keep_wilson',mode,keep=True)
 solve('optimized_without_wilson',mode)
 for label,pid in chosen.items():solve(label,mode,required=pid)
output=dict(contract='wilson_full_roster_frozen_study_v1',created_at=datetime.now(UTC).isoformat(),original_optimizer_run_id=data['run']['optimizer_run_id'],source_file=str(source),source_file_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),projection_run_id=data['run']['projection_run_id'],ownership_run_id=cfg['ownership_run_id'],preliminary_snapshot_sha256=json.loads((ROOT/'fresh_snapshot_metadata.json').read_text())['sha256'],legal_model_snapshot_sha256=snapshot['sha256'],original_generated_candidates=6,original_selected_rosters=5,scope='single-lineup generation experiment; not portfolio selector comparison or exhaustive best proof',fixed_core=sorted(locked),wilson_id=wilson,frozen_scenario=world['scenario_id'],opportunity_budget=report['candidates'][0]['opportunity_budget'],saved_baseline_metrics=bs,user_settings={k:cfg[k] for k in ['stack_policy','max_exposure','minimum_qb_salary','minimum_rb_salary','force_favored_rb','force_favored_dst','enforce_single_te','exclude_questionable','exclude_player_ids','exclude_opponent_teams','avoid_dst_opponents','max_players_per_game','max_players_per_team','preliminary_rank_preference']},arm_difference='required ARI response exactly retains generated normal-LAR idea; optional arm removes only scenario-inferred response constraint, not a user setting; objective and all other legal/scenario constraints identical',budget=dict(requested_solver_calls=29,actual_solver_calls=len(runs),per_solve_time_limit_seconds=12,seed=7),eligible_candidate_ids=chosen,missing_requested_role_candidate='Tyquan Thornton absent from exact frozen legal pool: not admitted or given new clearance',runs=runs,live_writes=False,final_entry_ready=False)
(OUT/'RESULTS.json').write_text(json.dumps(output,indent=2)+'\n');print('COMPLETE',len(runs),len({r.get('canonical_roster_sha256') for r in runs if r['solver_status']=='Optimal'}),flush=True)
