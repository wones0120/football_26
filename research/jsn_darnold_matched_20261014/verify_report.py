import json
from collections import Counter
from pathlib import Path
from backend.app.product_services.analyst_packets import load_packet,packet_digest
root=Path(__file__).resolve().parent
prep=json.loads((root/'preparation.json').read_text());jobs={k:json.loads((root/f).read_text()) for k,f in [('Expected Game','expected_job.json'),('Original CONSTRUCTION','construction_final_job.json')]}
a,b=jobs.values();controls=['num_lineups','max_exposure','captain_max_exposure','minimum_player_salary','require_team_leader','require_home_team_leader','captain_positions','captain_position_exception_ids','questionable_eligible_player_ids','exclude_questionable','exclude_opponent_teams','exclude_player_ids','exclude_players','locked_player_ids','locked_players','flex_only_players','no_qbs','no_qb_captain','no_two_qbs','max_players_per_team','avoid_dst_opponents','availability_overrides','analyst_candidates_per_thesis']
assert all(a['params'].get(k)==b['params'].get(k) for k in controls)
receipt=prep['analyst_intent_handoffs']['EXPECTED_GAME'];packet=load_packet(receipt['checked_packet_sha256']);assert packet_digest(packet)==receipt['checked_packet_sha256']
assert not any(s.get('explicit_user_what_if') for s in packet['scenario_assumptions']['scenarios'])
ids={'jsn':'1838dd60-35e8-4018-b307-39cde90e1f03','darnold':'480d4188-7bf6-4684-b2b5-1d47f93d542a'}
poolfields=['salary','projection','p90','player_status','pregame_injury_status','pregame_availability_probability','workload_evidence']
pools=[{r['player_id']:{k:r.get(k) for k in poolfields} for r in j['params']['strategy_runtime']['player_pool']['rows']} for j in jobs.values()];assert pools[0]==pools[1]
summary={};signatures={};names={}
for label,j in jobs.items():
 p=j['params'];r=p['strategy_runtime']['football_analyst'];h=p['analyst_handoff_applied'];assert j['status']=='completed' and len(j['results'])==4
 assert p['num_lineups']==4 and p['max_exposure']==1 and p['captain_max_exposure']==.25 and p['minimum_player_salary']==1700
 assert p['captain_positions']==['WR','RB'] and p['captain_position_exception_ids']==[ids['darnold']]
 assert p['questionable_eligible_player_ids']==[ids['jsn']] and p['exclude_questionable'] and p['exclude_opponent_teams']==[]
 assert p['require_team_leader'] and not p['require_home_team_leader'] and not p['entry_readiness']['entry_ready']
 assert h['mode']=='AUTO' and h['checked_packet_sha256']==receipt['checked_packet_sha256']==r['packet_sha256']
 assert h['compatibility_sha256']==receipt['compatibility_sha256'] and r['preparation_compatibility']==receipt and r['prepared_research']==h
 assert j['projection_run_id']==prep['projection_run_id'] and p['ownership_run_id']==prep['ownership_run_id']
 assert p['prepared_input_evidence']['source_sha256']==prep['source_sha256']
 pool={row['player_id']:row for row in p['strategy_runtime']['player_pool']['rows']}
 assert pool[ids['jsn']]['included'] and pool[ids['jsn']]['player_status']=='Q' and pool[ids['jsn']]['questionable_eligibility_assumption']['source_status_unchanged']
 assert pool[ids['darnold']]['included'] and not pool[ids['darnold']]['captain_user_preference_exclusions']
 leaders=set(p['strategy_runtime']['team_leader_preference']['required_player_ids']);counts=Counter();caps=Counter();lines=[];sigs=set()
 for i,lineup in enumerate(j['results'],1):
  captain=next(x for x in lineup if x['roster_position']=='CPT');caps[captain['name']]+=1;counts.update(x['name'] for x in lineup);names.update({x['player_id']:x['name'] for x in lineup})
  assert len({x['player_id'] for x in lineup})==6 and {x['player_id'] for x in lineup}&leaders
  assert captain['position'] in ['WR','RB'] or captain['player_id']==ids['darnold']
  assert all(x['base_salary']>=1700 for x in lineup) and sum(x['salary'] for x in lineup)<=50000
  assert max(Counter(x['player_team'] for x in lineup).values())<=4
  if captain['position']=='WR':assert any(x['position']=='QB' and x['player_team']==captain['player_team'] for x in lineup)
  sigs.add(tuple(sorted((x['player_id'],x['roster_position']) for x in lineup)))
  lines.append(dict(number=i,captain=captain['name'],salary=sum(x['salary'] for x in lineup),model_mean=sum(x['projection'] for x in lineup),individual_p90_sum=sum(x['p90'] for x in lineup),scenarios=lineup[0].get('analyst_thesis_ids',[]),scenario_scores=lineup[0].get('analyst_scenario_scores',{}),players=[{k:x[k] for k in ['player_id','name','player_team','position','roster_position','salary']} for x in lineup]))
 assert len(caps)==4 and max(caps.values())==1 and len(sigs)==4
 signatures[label]=sigs
 if label=='Expected Game':
  assert r['mode']=='MERGED_SCENARIOS' and r['selection']['constraints_relaxed'] is False
  candidates=len(r['candidates']);assert candidates==4
  generation=dict(candidate_count=candidates,initial_candidate_count=r['initial_generated_candidate_count'],coverage=r['captain_exposure_coverage'],seed=r['seed'],policy=r['selection'])
 else:
  assert r['mode']=='ORIGINAL_CONSTRUCTION_BASELINE' and r['analyst_directives_applied'] is False
  assert r['baseline_selected_lineup_count']==4 and r['baseline_candidate_attempt_count']==4
  generation=dict(checked_research_recorded_only=True,captain_attempt_count=4,saved_rosters=4,complete_candidate_pool_available=False,seed='deterministic original coverage policy; no stochastic scenario seed',policy=r['baseline_generation_evidence'])
 summary[label]=dict(run_id=j['job_id'],status=j['status'],mode=r['mode'],lineups=lines,exposure=dict(counts),captain_exposure=dict(caps),generation=generation)
 assert j['job_id'] in (root/('expected_reopened_dom.txt' if label=='Expected Game' else 'construction_final_reopened_dom.txt')).read_text()
out=dict(status='PASS',prepared_job_id='afcd12ad-951e-4507-9917-172706d3368c',projection_run_id=prep['projection_run_id'],ownership_run_id=prep['ownership_run_id'],source_sha256=prep['source_sha256'],checked_packet_sha256=receipt['checked_packet_sha256'],compatibility_sha256=receipt['compatibility_sha256'],same_frozen_model_and_source_rows=True,controls={k:a['params'].get(k) for k in controls},identical_role_rosters=len(signatures['Expected Game']&signatures['Original CONSTRUCTION']),classification='Matched-input separate generation/scoring-policy experiment, not a fixed-pool selector experiment or calibrated EV comparison',runs=summary)
(root/'FINAL_COMPARISON.json').write_text(json.dumps(out,indent=2)+'\n')
md=['# JSN / Darnold matched Thursday research comparison','', 'PASS: both Chrome Prepare → Optimize runs saved and reopened 4/4. Research only; final entry readiness remains false.','', '**Official status:** Seahawks final Wednesday report says JSN practiced fully and has no final game designation. Team statement captured 2026-10-15 02:56:28.961056 UTC; NFL refresh observed 02:57:22 UTC, snapshot `b6d5c888-819d-5bca-84f2-67f9d420cb0c`. Thursday October 15, SEA at DEN, kickoff 8:15 PM EDT / 6:15 PM MDT. [Official team statement](https://www.seahawks.com/news/jaxon-smith-njigba-good-to-go-drake-thomas-ruled-out-for-seahawks-week-6-game-at-denver). This is distinct from the later inactive list.','', '**Why omitted before:** JSN’s raw DK salary Q triggered the user exclude-Q gate; canonical context was ACT. A named user research exception now bypasses only that stale Q gate and preserves raw Q, official facts and projections. Darnold was FLEX-only under WR/RB Captain preference; only Darnold now has a named position exception. Neither is forced into a lineup. Other settings match: 4 lineups, player cap100%, CPT25%, min$1700 base, leader required, team max4; DEN opponent exclusion OFF.','',f'**Frozen lineage:** preparation `{out["prepared_job_id"]}`; projection `{out["projection_run_id"]}`; ownership `{out["ownership_run_id"]}`; checked Expected packet `{out["checked_packet_sha256"]}`. Both runs have identical full source-model rows and all user controls.','', '**Experimental distinction:** Expected uses two authored equal-weight opportunity worlds (competitive reference and SEA drive upside), with no DEN breakout story. Original CONSTRUCTION records the same checked research for provenance only and uses the original top-four P90 Captain coverage policy, role-specific scoring and quality floors. Its four Captain attempts and saved rosters are recorded; a complete candidate-pool manifest is unavailable. Expected generated four distinct candidates after bounded Captain coverage. Different pools and scoring policies; no claim of calibrated EV or a fixed-pool selector test. The candidate-per-thesis request is2 in both; the old baseline does not consume that Analyst budget.','', '**Primary research candidate:** Darnold CPT / Nix, JSN, Myers, Barner, Engram FLEX ($49,100) is shared by both policies, ranks first under Expected’s scenario coverage and has the highest unchanged base-model mean of these saved rosters (81.90). This agreement is useful, not outcome validation.','', '| # | Expected Game CPT · FLEX | Salary | Original CONSTRUCTION CPT · FLEX | Salary |','|---|---|---:|---|---:|']
def roster(line):
 c=next(x for x in line['players'] if x['roster_position']=='CPT');return '**'+c['name']+' CPT $'+format(c['salary'],',.0f')+'** · '+', '.join(x['name']+' $'+format(x['salary'],',.0f') for x in line['players'] if x['roster_position']=='FLEX')
for left,right in zip(summary['Expected Game']['lineups'],summary['Original CONSTRUCTION']['lineups']):md.append(f'| {left["number"]} | {roster(left)} | ${left["salary"]:,.0f} | {roster(right)} | ${right["salary"]:,.0f} |')
md+=['',f'Exactly {out["identical_role_rosters"]} role-specific rosters are shared; order differs. Expected’s Harvey/Kupp slots replace original Dobbins/Sutton Captain rosters. All Expected rosters use four SEA/two DEN; the original fourth is3–3. These are conditional opportunity/affordability differences, not a forced Seattle Captain rule.','', '| Player | Expected exposure | Original exposure |','|---|---:|---:|']
for name in sorted(set(summary['Expected Game']['exposure'])|set(summary['Original CONSTRUCTION']['exposure'])):md.append(f'| {name} | {summary["Expected Game"]["exposure"].get(name,0)}/4 | {summary["Original CONSTRUCTION"]["exposure"].get(name,0)}/4 |')
md+=['','## Expected scenario contributions','','| CPT | Competitive reference score | SEA drive upside score |','|---|---:|---:|']
for line in summary['Expected Game']['lineups']:md.append(f'| {line["captain"]} | {line["scenario_scores"].get("expected_competitive_reference",0):.2f} | {line["scenario_scores"].get("expected_sea_drive_upside",0):.2f} |')
md+=['','These are research conditional scores; do not compare them numerically to original P90/mean or interpret them as forecast DK points. SEA passing/rushing factors1.10/1.05 and elasticity0.6 remain uncalibrated local sensitivities.','',f'Expected saved run `{summary["Expected Game"]["run_id"]}`. Original saved run `{summary["Original CONSTRUCTION"]["run_id"]}`. Original predecessor `a6f021ab-f76d-47cf-9c2c-826edc5e36fa` is preserved; final rerun only makes intentional-baseline audit labeling explicit.','', 'Validation: targeted Captain preference, safety, official injury, intent/isolation and construction tests passed;18 UI tests passed; TypeScript/Vite build, Python compilation and diff check passed. No entries/exports, baseline projection changes or unrelated tree cleanup.']
(root/'FINAL_REPORT.md').write_text('\n'.join(md)+'\n');print('PASS',out['identical_role_rosters'],[(k,v['run_id']) for k,v in summary.items()])
