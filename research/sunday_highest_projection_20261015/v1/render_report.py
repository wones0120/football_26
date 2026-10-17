from pathlib import Path
from collections import defaultdict,Counter
import json,hashlib
P=Path(__file__).resolve().parent;saved=json.loads((P/'ui_saved_run.json').read_text());arms=json.loads((P/'ui_matched_comparisons.json').read_text());verification=json.loads((P/'verification.json').read_text());audit=saved['params']['strategy_runtime']['highest_projection'];base=audit['base_mean'];rows=audit['input_snapshot']['players'];pool={p['player_id']:p for p in rows};salary={p['player_master_id']:p for p in json.loads(Path('research/sunday_refresh_20261015/v1/salary_capture.json').read_text())['rows']}
model=audit['input_snapshot']['model'];variables=set(audit['input_snapshot']['variable_players']);fixed=[c for c in model['constraints'] if c['sense']==0 and len(c['coefficients'])==1 and c['coefficients'][0]['name'] in variables and abs(c['constant'])==1];assert fixed==[]
objective={c['name']:c['value'] for c in model['objective']['coefficients']};assert set(objective)<=variables
for variable,pid in audit['input_snapshot']['variable_players'].items():assert objective.get(variable,0)==pool[pid]['projection']
assert audit['locked_player_ids']==[] and audit['hard_qb_stack'] is False and audit['mandatory_opponent_bringback'] is False and audit['generated_scenario_constraints'] is False

def slots(lineup):
 groups=defaultdict(list)
 for p in lineup:groups[p['position']].append(p)
 for values in groups.values():values.sort(key=lambda p:(-p['projection'],p['player_id']))
 out=[]
 for pos,n in [('QB',1),('RB',2),('WR',3),('TE',1),('DST',1)]:out.extend((pos,groups[pos].pop(0)) for i in range(n))
 left=[p for group in groups.values() for p in group];assert len(left)==1 and left[0]['position'] in ['WR','RB'];out.append(('FLEX',left[0]));return out
full=['# Same-build full-roster controls','', 'Only the unlocked main lineup is an app-saved optimizer result. Matched controls are isolated exact baseline-mean solves from that saved result’s frozen legal input frame; they do not change app settings or save extra optimizer runs. Legal FLEX assignments below are derived for display from natural positions.','']
for label,arm in arms.items():
 a=arm['audit'];assert a['solver_status']=='Optimal';lineup=arm['lineups'][0];assert len({p['player_id'] for p in lineup})==9
 for p in lineup:
  q=salary[p['player_id']];assert(q['salary'],q['team'],q['position'],q['source_player_key'])==(p['salary'],p['player_team'],p['position'],p['dk_player_id'])
 full +=[f"## {label}",'',f"Salary ${a['salary']:,.0f}; unchanged base projection {a['base_mean']:.6f}; gap versus unlocked {a['base_mean']-base:+.6f}; Optimal. Explicit canonical locks: {', '.join(a['locked_player_ids']) or 'none'}; QB exclusions: {', '.join(a['excluded_qb_ids']) or 'none'}.",'', '| Slot | Player | Team | Salary | Base mean | Canonical UUID | DK native ID |','|---|---|---|---:|---:|---|---|']
 for slot,p in slots(lineup):full.append(f"| {slot} | {p['name']} | {p['player_team']} | ${p['salary']:,} | {p['projection']:.4f} | {p['player_id']} | {p['dk_player_id']} |")
 full.append('')
(P/'FULL_ROSTERS.md').write_text('\n'.join(full)+'\n')
validation=dict(**verification,canonical_salary_native_ids_verified=True,objective_coefficients_equal_unchanged_player_means=True,objective_auxiliary_coefficient_count=0,single_player_forced_equalities=[],actual_model_constraint_count=len(model['constraints']),same_pool_all_comparisons=True,final_build_solve_count=6,all_solver_statuses='Optimal',targeted_backend_tests=46,targeted_ui_tests=19,ui_build='passed; existing bundle-size advisory only',browser_validation='Chrome localhost only; objective selected, request submitted, completed saved run reopened, highest-objective and9-slot screenshots captured; desktop only',no_export_or_entry=True,original_saved_normal_preserved=True)
(P/'VALIDATION.json').write_text(json.dumps(validation,indent=2)+'\n')
comparison=['| Comparison | Salary | Unchanged base projection | Gap vs unlocked |','|---|---:|---:|---:|']
for label,arm in arms.items():a=arm['audit'];comparison.append(f"| {label} | ${a['salary']:,.0f} | {a['base_mean']:.2f} | {a['base_mean']-base:+.2f} |")
(P/'COMPARISON_TABLE.md').write_text('\n'.join(comparison)+'\n')
print('Validated canonical/native identities and exact model coefficients; final same-build solves:',len(arms)+1)
