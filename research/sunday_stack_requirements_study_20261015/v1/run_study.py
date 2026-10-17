"""Frozen matched stack/bringback diagnostics. No service or live database writes."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,UTC
from collections import Counter
import json,hashlib,time
import pulp
from backend.app.product_services.scenario_allocation import apply_idea,AllocationControls
from backend.app.product_services.cbc_solver import make_cbc_solver
P=Path(__file__).resolve().parent;source=Path('research/sunday_refresh_20261015/normal_saved_result.json');d=json.loads(source.read_text());cfg=d['run']['constraint_config_json'];a=cfg['strategy_runtime']['football_analyst'];snap=a['input_snapshot'];rows=snap['players'];pool={r['player_id']:r for r in rows};mapping=snap['variable_players'];pidname={ref['player_master_id']:name for name,ref in mapping.items()};world=next(x for x in a['scenario_definitions'] if x['scenario_id']=='2026_06_ARI_LA:LAR:passing');mom=world['moments'];idea=next(x for x in a['scenario_allocation_plan']['ideas'] if x['idea_id']==world['scenario_id']);controls=AllocationControls.model_validate(a['scenario_allocation_plan']['controls']);STAFFORD='30cb73fd-8a62-419b-bcdd-1f505531caeb';locks={'a7d14336-632e-48c8-b0c1-45916b8476e4','319a7e5c-7967-4405-90f9-36ddfea66dfd'};baseline={r['player_id'] for r in d['lineups'][0]};qbids=[pid for pid,r in pool.items() if r['position']=='QB'];removed=[]
for pid in qbids:
 r=pool[pid];expected={pidname[p]:1 for p,x in pool.items() if x['player_team']==r['player_team'] and x['position'] in ['WR','TE','RB']};expected[pidname[pid]]=-1
 match=[i for i,c in enumerate(snap['model']['constraints']) if c['sense']==1 and c['constant']==0 and {z['name']:z['value'] for z in c['coefficients']}==expected];assert len(match)==1
 removed.append(dict(index=match[0],qb_id=pid,qb_name=r['name'],constraint=snap['model']['constraints'][match[0]]))
assert len(removed)==17 and len({x['index'] for x in removed})==17
original_qbs={r['player_id'] for r in a['projection_distribution_eligibility']['original_input_rows'] if r['position']=='QB'};assert original_qbs==set(qbids)
runs=[]
def metrics(ids):return dict(salary=sum(pool[p]['salary'] for p in ids),base_mean=sum(pool[p]['projection'] for p in ids),conditional_mean=sum(mom[p]['mean'] for p in ids),conditional_objective=sum(mom[p]['mean']+.35*(mom[p]['p90']-mom[p]['mean']) for p in ids))
base=metrics(baseline);assert abs(base['conditional_objective']-a['candidates'][0]['scores'][world['scenario_id']])<1e-8

def solve(label,hard_stack,ari_response,qb_mode,forced_qb=None,exact=False,ban_stack=None,optimize='conditional_objective',keep_generated_pin=False):
 modeldict=deepcopy(snap['model']);dropped={x['index'] for x in removed} if not hard_stack else set();modeldict['constraints']=[c for i,c in enumerate(modeldict['constraints']) if i not in dropped];variables,model=pulp.LpProblem.fromDict(modeldict);v={pid:variables[name] for pid,name in pidname.items()};used=deepcopy(idea);used['bringback_required']=ari_response;apply_idea(model,variables,mapping,rows,used,controls)
 unpin=qb_mode=='free' and not keep_generated_pin
 if unpin:del model.constraints['idea_primary_qb']
 if not hard_stack:del model.constraints['idea_receivers']
 for pid in locks:model+=v[pid]==1
 if qb_mode=='held':model+=v[STAFFORD]==1
 if forced_qb:model+=v[forced_qb]==1
 if exact:
  for pid in baseline:model+=v[pid]==1
 if ban_stack:
  positions={'WR','TE'} if ban_stack=='no_wr_te' else {'WR','TE','RB'}
  for q in qbids:
   partners=[v[p] for p,r in pool.items() if r['player_team']==pool[q]['player_team'] and r['position'] in positions]
   model+=pulp.lpSum(partners)<=len(partners)*(1-v[q]),'diagnostic_unstacked_'+q
 if optimize=='conditional_objective':coefs={p:mom[p]['mean']+.35*(mom[p]['p90']-mom[p]['mean']) for p in pool}
 elif optimize=='base_mean':coefs={p:pool[p]['projection'] for p in pool}
 else:raise ValueError(optimize)
 model.setObjective(pulp.lpSum(coefs[p]*var for p,var in v.items()));solver=make_cbc_solver();solver.msg=False;solver.timeLimit=12;solver.options.extend(['randomSeed 7','randomCbcSeed 7']);start=time.monotonic();status=model.solve(solver)
 r=dict(label=label,hard_qb_stack=hard_stack,mandatory_ari_response=ari_response,qb_mode=qb_mode,forced_qb_id=forced_qb,generated_lar_qb_pin_removed=unpin,generated_lar_receiver_requirement_removed=not hard_stack,exact_baseline_replay=exact,unstacked_diagnostic=ban_stack,objective_optimized=optimize,solver_status=pulp.LpStatus[status],solution_status=pulp.LpSolution.get(model.sol_status),elapsed_seconds=time.monotonic()-start,deleted_frozen_constraint_indices=sorted(dropped),other_user_constraints_unchanged=True,scenario_secondary_offense_limit=controls.secondary_offense_limit)
 if status==pulp.LpStatusOptimal:
  assert model.valid(1e-5);ids={p for p,var in v.items() if pulp.value(var)>.5};assert locks<=ids and len(ids)==9
  pos=Counter(pool[p]['position'] for p in ids);assert pos['QB']==pos['TE']==pos['DST']==1 and pos['RB']>=2 and pos['WR']>=3 and pos['RB']+pos['WR']==6
  met=metrics(ids);assert met['salary']<=50000;assert max(Counter(pool[p]['player_team'] for p in ids).values())<=4;assert max(Counter(pool[p]['canonical_game_id'] for p in ids).values())<=5
  qb=next(p for p in ids if pool[p]['position']=='QB');team=pool[qb]['player_team'];partners=[p for p in ids if pool[p]['player_team']==team and pool[p]['position'] in ['WR','TE']];skillpartners=[p for p in ids if pool[p]['player_team']==team and pool[p]['position'] in ['WR','TE','RB']]
  assert qb_mode!='held' or qb==STAFFORD;assert not hard_stack or skillpartners
  if ban_stack=='no_wr_te':assert not partners
  if ban_stack=='no_skill_partner':assert not skillpartners
  for pid in ids:
   assert pid not in cfg['exclude_player_ids'];pr=pool[pid];assert pr['position'] not in ['RB','QB'] or pr['salary']>=4500
   if pr['position']=='DST':assert not any(pool[j]['position']!='DST' and pool[j]['player_team']==pr['opponent_team'] for j in ids)
  r.update(**met,delta_baseline={k:met[k]-base[k] for k in ['base_mean','conditional_mean','conditional_objective','salary']},qb_id=qb,qb_name=pool[qb]['name'],qb_salary=pool[qb]['salary'],wr_te_stack_names=[pool[p]['name'] for p in partners],skill_stack_names=[pool[p]['name'] for p in skillpartners],ari_response_names=[pool[p]['name'] for p in ids if pool[p]['player_team']=='ARI' and pool[p]['position'] in ['WR','TE']],salary_unused=50000-met['salary'],canonical_roster_sha256=hashlib.sha256('|'.join(sorted(ids)).encode()).hexdigest(),players=[dict(player_master_id=p,dk_native_id=pool[p]['dk_player_id'],name=pool[p]['name'],team=pool[p]['player_team'],position=pool[p]['position'],salary=pool[p]['salary'],base_mean=pool[p]['projection'],conditional_mean=mom[p]['mean'],conditional_p90=mom[p]['p90']) for p in sorted(ids)])
 runs.append(r);(P/'progress.json').write_text(json.dumps(runs,indent=2)+'\n');print(label,r['solver_status'],r.get('qb_name'),round(r.get('base_mean',0),2),round(r.get('conditional_objective',0),2),flush=True)
solve('exact_saved_baseline',True,True,'held',exact=True)
for stack in [True,False]:
 for ari in [True,False]:
  for mode in ['held','free']:solve(f"factorial_stack_{stack}_ari_{ari}_qb_{mode}",stack,ari,mode)
solve('free_label_but_original_scenario_pin_retained',True,False,'free',keep_generated_pin=True)
for pid in qbids:solve('optional_forced_'+pool[pid]['name'],False,False,'free',forced_qb=pid)
solve('genuinely_no_qb_wr_te',False,False,'free',ban_stack='no_wr_te')
solve('genuinely_no_qb_skill_partner',False,False,'free',ban_stack='no_skill_partner')
solve('both_optional_base_mean_objective',False,False,'free',optimize='base_mean')
solve('both_optional_stafford_held_base_mean_objective',False,False,'held',optimize='base_mean')
output=dict(contract='stack_requirements_frozen_study_v1',created_at=datetime.now(UTC).isoformat(),original_run_id=d['run']['optimizer_run_id'],projection_run_id=d['run']['projection_run_id'],ownership_run_id=cfg['ownership_run_id'],frozen_source=str(source),frozen_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),input_snapshot_sha256=snap['sha256'],fixed_core_ids=sorted(locks),saved_baseline=base,original_user_stack_policy=cfg['stack_policy'],original_generated_idea=idea,exact_removed_stack_constraints=removed,eligible_qbs=list(qbids),stack_filter_eligible_qbs_unchanged=True,soft_objective_audit=dict(captured_objective_coefficient_count=len(snap['model']['objective']['coefficients']),captured_auxiliary_coefficient_count=sum(not c['name'].startswith('player_') for c in snap['model']['objective']['coefficients']),normal_scenario_actual_objective='per-player mean+0.35*(p90-mean)',actual_auxiliary_bonus_coefficients=0,consequence='Hard stack constraints survive capture, but original soft correlation auxiliary bonuses are replaced before actual normal scenario solves.'),factorial_note='Held variants retain generated Stafford pin; free-QB variants explicitly remove it to prevent fake freedom. WR/TE LAR floor additionally removed in hard-stack-optional arms; Puka lock already satisfies it. Secondary-team offense cap2 retained in all arms.',solver_budget=dict(calls=len(runs),seed=7,time_limit_seconds_per_call=12),runs=runs,live_writes=False,permanent_settings_changes=False,entry_ready=False)
(P/'RESULTS.json').write_text(json.dumps(output,indent=2)+'\n');print('COMPLETE',len(runs),len({r.get('canonical_roster_sha256') for r in runs if r['solver_status']=='Optimal'}),flush=True)
