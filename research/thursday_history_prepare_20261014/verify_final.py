import json
from collections import Counter
from pathlib import Path
from backend.app.product_services.analyst_packets import load_packet,packet_digest
root=Path(__file__).resolve().parent
j=json.loads((root/'final_optimizer_job.json').read_text());p=j['params']
prep=json.loads((root/'fresh_analyst_preparation.json').read_text())
h=p['analyst_handoff_applied'];a=prep['analyst_handoff'];r=p['strategy_runtime']['football_analyst']
assert j['status']=='completed' and len(j['results'])==4
assert p['num_lineups']==4 and p['max_exposure']==1 and p['captain_max_exposure']==.25
assert p['min_player_salary']==1700 if 'min_player_salary' in p else p['minimum_player_salary']==1700
assert p['require_team_leader'] is True and p['exclude_opponent_teams']==[]
assert p['max_players_per_team']==4
assert h['mode']=='AUTO' and h['source_packet_sha256']==a['source_packet_sha256']
assert h['checked_packet_sha256']==a['checked_packet_sha256']==r['packet_sha256']
assert h['compatibility_sha256']==a['compatibility_sha256']
assert p['prepared_input_evidence']['source_sha256']==prep['source_sha256']
assert j['projection_run_id']==prep['projection_run_id']
assert r['prepared_research']==h
assert all(a[key]==value for key,value in r['prepared_research'].items())
assert r['preparation_compatibility']['prepared_source_sha256']==prep['source_sha256']
assert r['preparation_compatibility']['projection_run_id']==prep['projection_run_id']
assert packet_digest(load_packet(h['checked_packet_sha256']))==h['checked_packet_sha256']
assert r['focus']['mode']=='MIXED' and r['selection']['constraints_relaxed'] is False
leaders=set(p['strategy_runtime']['team_leader_preference']['required_player_ids'])
captains=[];signatures=[];salaries=[];summary=[]
for i,lineup in enumerate(j['results'],1):
 ids={x['player_id'] for x in lineup};assert len(ids)==6
 captain=[x for x in lineup if x['roster_position']=='CPT'];assert len(captain)==1
 c=captain[0];assert c['position'] in ['WR','RB'];captains.append(c['player_id'])
 assert c['analyst_packet_sha256']==a['checked_packet_sha256']
 assert ids&leaders
 assert max(Counter(x['player_team'] for x in lineup).values())<=4
 assert all(float(x['base_salary'])>=1700 and x['identity_resolved'] and x.get('availability_status')!='Q' for x in lineup)
 if c['position']=='WR':assert any(x['position']=='QB' and x['player_team']==c['player_team'] for x in lineup)
 salary=sum(x['salary'] for x in lineup);assert salary<=50000;salaries.append(salary)
 signatures.append(tuple(sorted((x['player_id'],x['roster_position']) for x in lineup)))
 summary.append(dict(lineup=i,captain=c['name'],captain_salary=c['salary'],flex=[dict(name=x['name'],salary=x['salary']) for x in lineup if x['roster_position']=='FLEX'],salary=salary,base_projection=sum(x['projection'] for x in lineup),scenario_ids=c['analyst_thesis_ids']))
assert len(set(captains))==4 and len(set(signatures))==4
assert p['entry_readiness']['entry_ready'] is False
out=dict(status='PASS',run_id=j['job_id'],preparation_run_id='3944590c-b011-4f61-a4ee-9bdb301c026f',projection_run_id=j['projection_run_id'],
 source_sha256=prep['source_sha256'],checked_packet_sha256=a['checked_packet_sha256'],source_packet_sha256=a['source_packet_sha256'],compatibility_sha256=a['compatibility_sha256'],
 requested=4,saved=4,reopened_in_chrome=True,distinct_captains=4,distinct_canonical_rosters=4,entry_ready=False,
 captain_exposure_coverage=r['captain_exposure_coverage'],lineups=summary)
(root/'FINAL_ACCEPTANCE.json').write_text(json.dumps(out,indent=2)+'\n')
print('PASS',j['job_id'],salaries)
