import json
from collections import Counter
from pathlib import Path
from backend.app.product_services.analyst_packets import load_packet,packet_digest
root=Path(__file__).resolve().parent
prep=json.loads((root/'preparation.json').read_text())
jobs={intent:json.loads((root/file).read_text()) for intent,file in [('EXPECTED_GAME','expected_final_job.json'),('CONTRARIAN','contrarian_final_job.json')]}
controls=['num_lineups','max_exposure','captain_max_exposure','minimum_player_salary','captain_positions','max_players_per_team','max_players_per_game','require_team_leader','require_home_team_leader','no_qbs','no_qb_captain','no_two_qbs','exclude_questionable','avoid_dst_opponents','exclude_opponent_teams','exclude_players','exclude_player_ids','locked_players','locked_player_ids','flex_only_players','flex_only_player_ids','availability_overrides','exclusions_assumed_out','core_player_max_exposure','starting_qb_max_exposure','cheap_punt_max_exposure','soft_scenario_diversity','require_scenario_diversity','showdown_decisive_margin']
a,b=jobs.values();assert all(a['params'].get(k)==b['params'].get(k) for k in controls)
old=json.loads(Path('research/thursday_history_prepare_20261014/final_optimizer_job.json').read_text())
assert all(a['params'].get(k)==old['params'].get(k) for k in controls)
ra=a['params']['strategy_runtime']['football_analyst'];rb=b['params']['strategy_runtime']['football_analyst']
assert ra['input_snapshot']['model']==rb['input_snapshot']['model']
assert ra['input_snapshot']['players']==rb['input_snapshot']['players']
summary={};roster_sets={};candidate_sets={};player_names={}
for intent,j in jobs.items():
 p=j['params'];r=p['strategy_runtime']['football_analyst'];h=p['analyst_handoff_applied'];frozen=prep['analyst_intent_handoffs'][intent]
 assert j['status']=='completed' and len(j['results'])==4
 assert p['num_lineups']==4 and p['max_exposure']==1 and p['captain_max_exposure']==.25 and p['minimum_player_salary']==1700
 assert p['captain_positions']==['WR','RB'] and p['require_team_leader'] is True and p['exclude_opponent_teams']==[]
 assert h['mode']=='AUTO' and h['optimization_intent']==intent
 assert h['checked_packet_sha256']==frozen['checked_packet_sha256']==r['packet_sha256']
 assert h['compatibility_sha256']==frozen['compatibility_sha256']
 assert r['prepared_research']==h
 assert j['projection_run_id']==prep['projection_run_id']
 assert p['ownership_run_id']==prep['ownership_run_id']
 assert p['prepared_input_evidence']['source_sha256']==prep['source_sha256']
 assert r['preparation_compatibility']['prepared_source_sha256']==prep['source_sha256']
 assert r['preparation_compatibility']==frozen
 packet=load_packet(h['checked_packet_sha256']);assert packet_digest(packet)==h['checked_packet_sha256']
 assert packet['preparation_compatibility']['original_packet_sha256']==frozen['scoped_packet_sha256']
 assert packet['intent_scope']['authoring_packet_sha256']==frozen['source_packet_sha256']
 ids=set(frozen['scenario_ids']);assert {s['scenario_id'] for s in r['scenario_definitions']}==ids
 assert r['optimization_intent']['intent']==intent and set(r['optimization_intent']['scenario_ids'])==ids
 assert r['selection']['constraints_relaxed'] is False and p['entry_readiness']['entry_ready'] is False
 if intent=='EXPECTED_GAME':
  assert not packet['intent_scope'].get('story_requirements')
  assert not any(s.get('explicit_user_what_if') for s in packet['scenario_assumptions']['scenarios'])
 leaders=set(p['strategy_runtime']['team_leader_preference']['required_player_ids'])
 captains=Counter();players=Counter();rows=[];signatures=set();sets=set()
 for index,lineup in enumerate(j['results'],1):
  players.update(row['player_id'] for row in lineup);player_names.update({row['player_id']:row['name'] for row in lineup})
  selected_ids={row['player_id'] for row in lineup};assert len(selected_ids)==6 and selected_ids&leaders
  captain=next(row for row in lineup if row['roster_position']=='CPT');captains[captain['player_id']]+=1
  assert captain['position'] in ['WR','RB'] and captain['analyst_optimization_intent']==intent and captain['analyst_intent_story_compliance'] is True
  assert set(captain['analyst_thesis_ids'])<=ids and captain['analyst_packet_sha256']==h['checked_packet_sha256']
  assert all(row['base_salary']>=1700 and row['identity_resolved'] and row.get('player_status')!='Q' for row in lineup)
  assert max(Counter(row['player_team'] for row in lineup).values())<=4
  if captain['position']=='WR':assert any(row['position']=='QB' and row['player_team']==captain['player_team'] for row in lineup)
  receivers=sum(row['player_team']=='DEN' and row['position'] in ['WR','TE'] for row in lineup)
  if intent=='CONTRARIAN':assert receivers>=2 and any(row['player_team']=='DEN' and row['position']=='QB' for row in lineup)
  salary=sum(row['salary'] for row in lineup);assert salary<=50000
  signature=tuple(sorted((row['player_id'],row['roster_position']) for row in lineup));signatures.add(signature);sets.add(tuple(sorted(selected_ids)))
  rows.append(dict(lineup=index,captain=captain['name'],salary=salary,den_receivers=receivers,
    model_mean=sum(row['projection'] for row in lineup),scenarios=captain['analyst_thesis_ids'],
    players=[{k:row[k] for k in ('player_id','name','player_team','position','roster_position','salary')} for row in lineup]))
 assert len(captains)==4 and max(captains.values())==1 and len(signatures)==4
 roster_sets[intent]=signatures
 candidate_sets[intent]={tuple(sorted((row['player_master_id'],row['role']) for row in candidate['roster'])) for candidate in r['candidates']}
 summary[intent]=dict(run_id=j['job_id'],status=j['status'],requested=4,saved=4,entry_ready=False,
  source_packet_sha256=h['source_packet_sha256'],checked_packet_sha256=h['checked_packet_sha256'],scoped_packet_sha256=h['scoped_packet_sha256'],compatibility_sha256=h['compatibility_sha256'],scenario_ids=sorted(ids),
  candidate_count=len(candidate_sets[intent]),role_distinct_rosters=len(signatures),canonical_player_sets=len(sets),
  captain_exposure=dict(captains),player_exposure=dict(players),lineups=rows)
assert set(summary['EXPECTED_GAME']['scenario_ids']).isdisjoint(summary['CONTRARIAN']['scenario_ids'])
assert summary['EXPECTED_GAME']['checked_packet_sha256']!=summary['CONTRARIAN']['checked_packet_sha256']
assert candidate_sets['EXPECTED_GAME']!=candidate_sets['CONTRARIAN']
out=dict(status='PASS',prepared_run_id='bd681f04-f75f-4064-9754-615425544053',projection_run_id=prep['projection_run_id'],ownership_run_id=prep['ownership_run_id'],source_sha256=prep['source_sha256'],
 user_controls={k:a['params'].get(k) for k in controls},controls_match_prior_mixed_run=True,matched_base_legal_model=True,matched_prepared_player_rows=True,
 identical_selected_role_rosters=len(roster_sets['EXPECTED_GAME']&roster_sets['CONTRARIAN']),candidate_pools_differ=True,
 comparison_classification='Matched-input separate generation experiments, not a frozen-pool selector comparison',player_names=player_names,runs=summary)
comparison=(root/'final_comparison_text.txt').read_text()
assert all(run['run_id'] in comparison for run in summary.values())
assert 'Matched salary, projection, ownership and source inputs' in comparison
for filename,intent in [('expected_final_reopened_dom.txt','EXPECTED_GAME'),('contrarian_final_reopened_dom.txt','CONTRARIAN')]:
 assert summary[intent]['run_id'] in (root/filename).read_text()
reloaded=(root/'final_reloaded_dom.txt').read_text()
assert all(run['run_id'] in reloaded for run in summary.values())
out['browser_evidence']=dict(both_saved_runs_reopened=True,comparison_survives_reload=True,
    files=['expected_final_reopened_dom.txt','contrarian_final_reopened_dom.txt','final_reloaded_dom.txt','final_comparison_text.txt'])
(root/'FINAL_COMPARISON.json').write_text(json.dumps(out,indent=2)+'\n')
print('PASS',[(intent,s['run_id'],s['candidate_count'],[l['salary'] for l in s['lineups']]) for intent,s in summary.items()]);print('shared role rosters',out['identical_selected_role_rosters'])
