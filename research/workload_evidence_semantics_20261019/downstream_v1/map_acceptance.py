import json,hashlib
from pathlib import Path
from copy import deepcopy
from backend.app.product_services.full_game_breadth import build_states,role_universe,map_game
P=Path(__file__).parent;d=json.load(open(P/'comparison.json'));s=json.load(open(P/'summary.json'))
c=next(x['constraint_config_json']for x in json.load(open('/private/tmp/sunday_actual_review_20261018/stored_run_configs.json'))if x['optimizer_run_id'].startswith('398efe88'))
a=c['strategy_runtime']['football_analyst'];rows=a['input_snapshot']['players'];full=c['strategy_runtime']['player_pool']['rows'];new=json.load(open(P.parent/'v1/new_v2_evidence.json'));v2=deepcopy(full)
for r in v2:r['workload_evidence']=new[r['player_id']]
u1,_=role_universe(full,rows);u2,_=role_universe(v2,rows)
libpath=Path('research/full_game_candidate_breadth_20261018/v1/historical_templates_v2.json');lib=json.load(open(libpath));states,audit=build_states(lib,full,rows,seed=7);lookup={x['game_id']:x for x in lib['games']};contexts=audit['contexts'];out=[];maxdelta=0
missing=set(new)-{r['player_id']for r in json.load(open(P.parent/'v1/recovered_original_feature_fields.json'))['rows']};skillmissing={r['player_id']for r in full if r['player_id']in missing and r['position']in ['RB','WR','TE','QB']}
assert not skillmissing&{r['player_id']for values in u2.values()for r,_,_ in values}
for state in states:
 points={};ledger_delta=[]
 for game in state['games']:
  gid=game['game_id'];ct=contexts[gid];template=lookup[game['source_game_id']]
  oldpoints,oldledger=map_game(template,ct['home'],ct['away'],u1);newpoints,newledger=map_game(template,ct['home'],ct['away'],u2);points.update(newpoints)
  for l,r in zip(oldledger,newledger):
   delta=sum(x['dk_points']for x in r['actors'])-sum(x['dk_points']for x in l['actors']);maxdelta=max(maxdelta,abs(delta));assert abs(delta)<1e-8
   ledger_delta.append({'team':l['current_team'],'source_game_id':template['game_id'],'total_dk_delta':delta})
 original_scores=[]
 for candidate in a['candidates']:
  ids=[r['player_master_id']for r in candidate['roster']];old=sum(state['points'][pid]for pid in ids);after=sum(points[pid]for pid in ids);original_scores.append({'before':old,'after':after,'delta':after-old})
 out.append({'state_id':state['state_id'],'changed_eligible_scores':sum(abs(points[r['player_master_id']]-state['points'][r['player_master_id']])>1e-9 for r in rows),'original_five':original_scores,'ledger':ledger_delta})
s['frozen_analog_acceptance']={'library_sha256':hashlib.sha256(libpath.read_bytes()).hexdigest(),'historical_game_templates':len(lib['games']),'states':len(states),'source_game_plans_fixed':True,'states_with_changed_eligible_scores':sum(x['changed_eligible_scores']>0 for x in out),'max_whole_ledger_dk_delta':maxdelta,'missing_skill_actor_ids_still_unmapped':len(skillmissing),'same_roster_score_cells_changed':sum(abs(x['delta'])>1e-8 for st in out for x in st['original_five']),'same_roster_score_cells':len(out)*5,'solver_calls':0,'interpretation':'Different anonymous/identified role-rank allocation under identical physical games; no performance claim, no new forecast/selection.'}
(P/'analog_mapping.json').write_text(json.dumps(out,indent=2)+'\n');(P/'summary.json').write_text(json.dumps(s,indent=2)+'\n');print(json.dumps(s['frozen_analog_acceptance'],indent=2))
