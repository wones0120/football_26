from pathlib import Path
from collections import Counter
from itertools import combinations
import json,hashlib
P=Path(__file__).resolve().parent
load=lambda n:json.loads((P/(n+'.json')).read_text())
d=load('saved_run');a=d['results'];b=load('ensemble_replay_local_run')['results'];c=load('incumbent_counterfactual_local_run')['results']
ids=lambda rs:frozenset(r['player_id'] for r in rs)
assert [ids(x) for x in a]==[ids(x) for x in b]
assert len({ids(x) for x in a})==5
for rs in a:
 assert len(rs)==len(ids(rs))==9
 counts=Counter(r['position'] for r in rs)
 assert counts['QB']==counts['TE']==counts['DST']==1 and counts['RB']>=2 and counts['WR']>=3 and counts['RB']+counts['WR']==6
 assert sum(r['salary'] for r in rs)<=50000
 assert max(Counter(r['player_team'] for r in rs).values())<=3
 assert max(Counter(r['canonical_game_id'] for r in rs).values())<=4
 assert all(r['opponent_team']!='DEN' for r in rs)
 assert all(not r['entry_ready'] for r in rs)
 assert all(str(r.get('injury_status','')).upper()!='Q' for r in rs)
excluded=set(load('snapshot_response')['assumption_manifest']['exclude_player_ids'])
assert len(excluded)==4 and not excluded.intersection({r['player_id'] for rs in a for r in rs})
exp=Counter(r['player_id'] for rs in a for r in rs)
assert max(exp.values())<=4
assert max(len(ids(x)&ids(y)) for x,y in combinations(a,2))<=5
assert d['params']['analyst_joint_opportunity_enabled'] is False
assert d['projection_run_id']=='c8869a96-440c-4c36-aead-3614d6ef4d97'
report={'status':'PASS','requested_and_achieved':5,'canonical_ordered_replay_exact':True,'canonical_rosters_changed_by_dst_generation_intervention':sum(ids(x)!=ids(y) for x,y in zip(a,c)),'checks':['9 distinct canonical players','legal Classic positions; single TE','salary <=50000','team <=3','game <=4','exposure <=80%','overlap <=5','DEN opponent exclusion','Q exclusion','entry_ready false','new joint prototype false','accepted projection ID'],'max_exposure_count':max(exp.values()),'max_overlap':max(len(ids(x)&ids(y)) for x,y in combinations(a,2)),'source_sha256':hashlib.sha256((P/'saved_run.json').read_bytes()).hexdigest(),'browser_reopened_run':d['job_id']}
(P/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
