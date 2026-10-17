import json
from pathlib import Path
from collections import Counter
from copy import deepcopy
from backend.app.product_services.analyst_packets import load_packet,packet_digest
from backend.app.product_services.analyst_scenarios import select_portfolio
root=Path(__file__).resolve().parent
prep=json.loads((root/'preparation_job.json').read_text())['result']
labels=['control_expected','control_contrarian','broad_expected','broad_contrarian']
jobs={k:json.loads((root/(k+'_job.json')).read_text()) for k in labels}
controls=json.loads(Path('research/thursday_eight_refresh_20261015/FINAL_COMPARISON.json').read_text())['user_controls']
controls['captain_position_exception_ids']=['480d4188-7bf6-4684-b2b5-1d47f93d542a'];controls['questionable_eligible_player_ids']=['1838dd60-35e8-4018-b307-39cde90e1f03'];controls.pop('captain_max_exposure')
summary={};names={};all_sigs={};baseline_model=None;baseline_rows=None
for label,j in jobs.items():
 p=j['params'];r=p['strategy_runtime']['football_analyst'];intent='EXPECTED_GAME' if label.endswith('expected') else 'CONTRARIAN';broad=label.startswith('broad')
 assert j['status']=='completed' and len(j['results'])==4
 assert all(p.get(k)==v for k,v in controls.items()),(label,[(k,p.get(k),v) for k,v in controls.items() if p.get(k)!=v])
 assert p['captain_max_exposure']==(.5 if broad else .25)
 assert p['captain_positions']==['WR','RB'] and p['require_team_leader'] and not p['require_home_team_leader']
 assert p['exclude_questionable'] and p['exclude_opponent_teams']==[]
 assert p['captain_position_exception_ids']==['480d4188-7bf6-4684-b2b5-1d47f93d542a']
 assert p['questionable_eligible_player_ids']==['1838dd60-35e8-4018-b307-39cde90e1f03']
 assert j['projection_run_id']==prep['projection_run_id'] and p['ownership_run_id']==prep['ownership_run_id']
 assert p['prepared_input_evidence']['source_sha256']==prep['source_sha256']
 handoff=p['analyst_handoff_applied'];expected=prep['analyst_intent_handoffs'][intent]
 assert handoff['mode']=='AUTO' and handoff['optimization_intent']==intent
 assert handoff['checked_packet_sha256']==expected['checked_packet_sha256']==r['packet_sha256']
 assert handoff['compatibility_sha256']==expected['compatibility_sha256'] and r['preparation_compatibility']==expected
 assert r['prepared_research']==handoff
 packet=load_packet(handoff['checked_packet_sha256']);assert packet_digest(packet)==handoff['checked_packet_sha256']
 if intent=='EXPECTED_GAME':assert not any(s.get('explicit_user_what_if') for s in packet['scenario_assumptions']['scenarios'])
 assert {s['scenario_id'] for s in r['scenario_definitions']}==set(expected['scenario_ids'])
 assert r['selection']['solver_status']=='Optimal' and r['selection']['constraints_relaxed'] is False
 assert not p['entry_readiness']['entry_ready']
 if baseline_model is None:baseline_model=r['input_snapshot']['model'];baseline_rows=r['input_snapshot']['players']
 assert baseline_model==r['input_snapshot']['model'] and baseline_rows==r['input_snapshot']['players']
 leaders=set(p['strategy_runtime']['team_leader_preference']['required_player_ids']);counts=Counter();caps=Counter();sigs=set();lines=[]
 for index,lineup in enumerate(j['results'],1):
  ids={x['player_id'] for x in lineup};assert len(ids)==6 and ids&leaders
  assert len([x for x in lineup if x['roster_position']=='CPT'])==1
  captain=next(x for x in lineup if x['roster_position']=='CPT');caps[captain['player_id']]+=1;counts.update(x['player_id'] for x in lineup)
  assert captain['position'] in ['WR','RB'] or captain['player_id']=='480d4188-7bf6-4684-b2b5-1d47f93d542a'
  assert all(x['base_salary']>=1700 and x['identity_resolved'] and (x.get('player_status')!='Q' or x['player_id']=='1838dd60-35e8-4018-b307-39cde90e1f03') for x in lineup)
  assert sum(x['salary'] for x in lineup)<=50000 and max(Counter(x['player_team'] for x in lineup).values())<=4
  if captain['position']=='WR':assert any(x['position']=='QB' and x['player_team']==captain['player_team'] for x in lineup)
  if intent=='CONTRARIAN':assert sum(x['player_team']=='DEN' and x['position'] in ['WR','TE'] for x in lineup)>=2 and any(x['position']=='QB' and x['player_team']=='DEN' for x in lineup)
  names.update({x['player_id']:x['name'] for x in lineup});sigs.add(tuple(sorted((x['player_id'],x['roster_position']) for x in lineup)))
  lines.append(dict(number=index,captain=captain['name'],salary=sum(x['salary'] for x in lineup),base_model_mean=sum(x['projection'] for x in lineup),scenario_scores=lineup[0]['analyst_scenario_scores'],players=[{k:x[k] for k in ['player_id','name','player_team','position','roster_position','salary','projection']} for x in lineup]))
 assert len(sigs)==4 and max(caps.values())<=(2 if broad else 1)
 candidate_sigs={tuple(sorted((x['player_master_id'],x['role']) for x in c['roster'])) for c in r['candidates']};assert len(candidate_sigs)==len(r['candidates'])
 all_sigs[label]=sigs
 record=dict(run_id=j['job_id'],intent=intent,captain_cap=p['captain_max_exposure'],candidate_count=len(candidate_sigs),candidate_captain_count=len({pid for sig in candidate_sigs for pid,role in sig if role=='CPT'}),captain_exposure=dict(caps),player_exposure=dict(counts),lineups=lines,selection=r['selection'],initial_generated_candidates=r['initial_generated_candidate_count'],source_packet_sha256=handoff['source_packet_sha256'],checked_packet_sha256=handoff['checked_packet_sha256'],compatibility_sha256=handoff['compatibility_sha256'])
 if broad:
  search=r['captain_candidate_search'];assert search['enabled'] and search['policy_id']=='analyst_eligible_captain_support_v1'
  assert search['supporting_rosters_per_captain']>=2 and not search['budget_exhausted'] and search['solves_used']<=search['maximum_solves']
  assert all(row['distinct_supporting_rosters']>=2 or row['status']!='target_reached' for row in search['coverage'])
  assert record['candidate_count']>summary['control_'+label.split('_')[1]]['candidate_count']
  # Cheap controlled selector replay on exactly this broad pool, changing only cap.
  selected,replay=select_portfolio(deepcopy(r['candidates']),r['scenario_definitions'],r['input_snapshot']['players'],requested=4,params={**p,'captain_max_exposure':.25},fmt='SHOWDOWN')
  assert replay['achieved']==4 and replay['constraints_relaxed'] is False
  replay_caps=Counter(next(x['player_master_id'] for x in c['roster'] if x['role']=='CPT') for c in selected)
  record.update(captain_search=search,broad_pool_25pct_selector_replay=dict(classification='Offline selector comparison on the exact frozen broad pool; only Captain cap differs, no new saved optimizer run',captain_exposure=dict(replay_caps),selection=replay,selected_candidates=selected))
 summary[label]=record
for intent in ['expected','contrarian']:
 c=summary['control_'+intent];b=summary['broad_'+intent];assert c['checked_packet_sha256']==b['checked_packet_sha256'] and c['compatibility_sha256']==b['compatibility_sha256']
 b['shared_rosters_with_control']=len(all_sigs['control_'+intent]&all_sigs['broad_'+intent])
for suffix, filename in [('expected','expected_game_job.json'),('contrarian','contrarian_job.json')]:
 old=json.loads((Path('research/thursday_eight_refresh_20261015')/filename).read_text())
 old_sigs={tuple(sorted((x['player_id'],x['roster_position']) for x in l)) for l in old['results']}
 assert old_sigs==all_sigs['control_'+suffix]
 for label in ['broad_'+suffix]:
  assert summary[label]['run_id'] in (root/(label+'_reopened_dom.txt')).read_text()
out=dict(status='PASS',prepared_job_id=json.loads((root/'preparation_job.json').read_text())['job_id'],projection_run_id=prep['projection_run_id'],ownership_run_id=prep['ownership_run_id'],source_sha256=prep['source_sha256'],all_four_runs_same_frozen_model_and_rows=True,controls_preserved_except_captain_cap=True,comparison='Matched-build combined broader-generation plus50pctCaptain treatment; offline broad-pool25pct replay isolates cap under that pool',player_names=names,runs=summary)
(root/'FINAL_COMPARISON.json').write_text(json.dumps(out,indent=2)+'\n')
print('PASS',[(k,v['run_id'],v['candidate_count'],v['candidate_captain_count'],{names[pid]:n for pid,n in v['captain_exposure'].items()}) for k,v in summary.items()])
